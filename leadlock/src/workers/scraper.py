"""
Lead scraper worker - discovers home services contractors via Brave Search API.
Runs every 15 minutes (configurable). Uses query rotation (6 variants per trade)
so re-scrapes always return fresh results instead of duplicates. Each query
fetches ALL location IDs from Brave (up to 100 POIs via batch requests).
Processes 1 location+trade combo per cycle (round-robin via Redis).
7-day cooldown on exhausted variants. Deduplicates by place_id and phone number.
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.scrape_job import ScrapeJob
from src.models.sales_config import SalesEngineConfig
from src.services.scraping import search_local_businesses, parse_address_components
from src.services.enrichment import enrich_prospect_email, extract_domain
from src.services.phone_validation import normalize_phone
from src.utils.email_validation import validate_email
from src.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 15 * 60  # 15 minutes
DEFAULT_VARIANT_COOLDOWN_DAYS = 7

# Multiple query variations per trade - each produces different Brave results.
# Rotated across scrape cycles so we always discover new businesses.
TRADE_QUERY_VARIANTS = {
    "hvac": [
        "HVAC contractors",
        "air conditioning repair companies",
        "heating and cooling services",
        "AC installation companies",
        "furnace repair contractors",
        "HVAC maintenance services",
    ],
    "plumbing": [
        "plumbing contractors",
        "plumber near me",
        "plumbing repair services",
        "emergency plumbing companies",
        "drain cleaning services",
        "water heater installation",
    ],
    "roofing": [
        "roofing contractors",
        "roof repair companies",
        "roof replacement services",
        "commercial roofing contractors",
        "residential roofers",
        "roof inspection services",
    ],
    "electrical": [
        "electrical contractors",
        "electrician services",
        "electrical repair companies",
        "licensed electricians",
        "commercial electrical contractors",
        "electrical wiring services",
    ],
    "solar": [
        "solar installation companies",
        "solar panel installers",
        "residential solar contractors",
        "solar energy companies",
        "solar power installation services",
        "solar panel repair",
    ],
    "general": [
        "home services contractors",
        "home repair companies",
        "general contractors",
        "home improvement contractors",
        "handyman services",
        "home maintenance companies",
    ],
}


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set("leadlock:worker_health:scraper", datetime.now(timezone.utc).isoformat(), ex=7200)
    except Exception as e:
        logger.debug("Heartbeat write failed: %s", str(e))


def get_query_variants(trade: str) -> list[str]:
    """Get query variations for a trade type."""
    return TRADE_QUERY_VARIANTS.get(trade, [f"{trade} contractors"])


async def get_next_variant_and_offset(
    db: AsyncSession,
    tenant_id,
    city: str,
    state: str,
    trade: str,
    cooldown_days: int = DEFAULT_VARIANT_COOLDOWN_DAYS,
) -> tuple[int, int]:
    """
    Determine the next query_variant to use for a location+trade.
    Looks at completed scrape jobs for this combo and picks the next unused variant.
    Variants older than cooldown_days are considered fresh again (businesses change).

    Returns:
        (query_variant_index, 0) or (-1, -1) if all variants exhausted within cooldown.
    """
    num_variants = len(get_query_variants(trade))
    if num_variants == 0:
        return -1, -1

    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)

    # Get variants used within cooldown period
    result = await db.execute(
        select(ScrapeJob.query_variant).where(
            and_(
                ScrapeJob.city == city,
                ScrapeJob.state_code == state,
                ScrapeJob.trade_type == trade,
                ScrapeJob.tenant_id == tenant_id,
                ScrapeJob.status == "completed",
                ScrapeJob.completed_at >= cooldown_cutoff,
            )
        )
    )
    used_variants = {row[0] for row in result.all()}

    # Find the next unused variant
    for variant in range(num_variants):
        if variant not in used_variants:
            return variant, 0

    # All variants exhausted within cooldown window
    return -1, -1


async def _get_poll_interval() -> int:
    """Get scraper poll interval from config, with fallback."""
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(SalesEngineConfig.scraper_interval_minutes).where(
                    and_(
                        SalesEngineConfig.is_active == True,  # noqa: E712
                        SalesEngineConfig.tenant_id.isnot(None),
                    )
                )
            )
            intervals = [
                int(row[0]) * 60
                for row in result.all()
                if row[0]
            ]
            if intervals:
                return max(60, min(intervals))
    except Exception as e:
        logger.debug("Config interval read failed: %s", str(e))
    return DEFAULT_POLL_INTERVAL_SECONDS


async def run_scraper():
    """Main loop - scrape for new prospects on configurable interval with jitter."""
    interval = await _get_poll_interval()
    logger.info("Lead scraper started (poll every %ds)", interval)

    while True:
        try:
            await scrape_cycle()
        except Exception as e:
            logger.error("Scraper cycle error: %s", str(e))

        await _heartbeat()
        interval = await _get_poll_interval()
        # Add jitter (0-5 min) to prevent thundering herd
        jitter = random.randint(0, 300)
        await asyncio.sleep(interval + jitter)


async def _get_round_robin_position(total_combos: int, tenant_id=None) -> int:
    """Get and increment the round-robin scraper position via Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        key_suffix = str(tenant_id) if tenant_id else "global"
        position = await redis.incr(f"leadlock:scraper:position:{key_suffix}")
        return (position - 1) % total_combos
    except Exception as e:
        logger.debug("Round-robin position read failed: %s", str(e))
        return 0


async def scrape_cycle():
    """
    Execute one scrape cycle. Processes 1 location+trade combo per cycle
    in round-robin fashion. Continuous scraping with smart throttling.
    """
    async with async_session_factory() as db:
        # Load active tenant configs
        result = await db.execute(
            select(SalesEngineConfig).where(
                and_(
                    SalesEngineConfig.is_active == True,  # noqa: E712
                    SalesEngineConfig.tenant_id.isnot(None),
                )
            )
        )
        configs = [c for c in result.scalars().all() if not getattr(c, "scraper_paused", False)]
        if not configs:
            logger.debug("No active tenant config for scraper cycle")
            return

        settings = get_settings()
        if not settings.brave_api_key:
            logger.warning("Brave API key not configured, skipping scrape")
            return

        for config in configs:
            tenant_id = config.tenant_id
            locations = config.target_locations or []
            trade_types = config.target_trade_types or []
            if not locations or not trade_types:
                continue

            # Count today's scrapes per tenant
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            count_result = await db.execute(
                select(func.count()).select_from(ScrapeJob).where(
                    and_(
                        ScrapeJob.tenant_id == tenant_id,
                        ScrapeJob.created_at >= today_start,
                    )
                )
            )
            today_scrapes = count_result.scalar() or 0
            if today_scrapes >= config.daily_scrape_limit:
                logger.info(
                    "Tenant %s daily scrape limit reached (%d)",
                    str(tenant_id)[:8], config.daily_scrape_limit,
                )
                continue

            combos = [
                (loc.get("city", ""), loc.get("state", ""), trade)
                for loc in locations
                for trade in trade_types
            ]
            if not combos:
                continue

            position = await _get_round_robin_position(len(combos), tenant_id=tenant_id)
            city, state, trade = combos[position]
            location_str = f"{city}, {state}"

            cooldown_days = getattr(config, "variant_cooldown_days", DEFAULT_VARIANT_COOLDOWN_DAYS)
            variant_idx, offset = await get_next_variant_and_offset(
                db,
                tenant_id,
                city,
                state,
                trade,
                cooldown_days=cooldown_days,
            )
            if variant_idx == -1:
                logger.info(
                    "Tenant %s all variants in cooldown for %s in %s",
                    str(tenant_id)[:8], trade, location_str,
                )
                continue

            variants = get_query_variants(trade)
            query = variants[variant_idx]

            await scrape_location_trade(
                db,
                config,
                settings,
                city,
                state,
                location_str,
                trade,
                query,
                variant_idx,
                offset,
            )
            await db.flush()

        await db.commit()


async def scrape_location_trade(
    db: AsyncSession,
    config: SalesEngineConfig,
    settings,
    city: str,
    state: str,
    location_str: str,
    trade: str,
    query: str,
    query_variant: int,
    search_offset: int,
):
    """Scrape a single location+trade combination with specific query variant."""
    # Create scrape job record
    job = ScrapeJob(
        tenant_id=config.tenant_id,
        platform="brave",
        trade_type=trade,
        location_query=f"{query} in {location_str}",
        city=city,
        state_code=state,
        query_variant=query_variant,
        search_offset=search_offset,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    total_cost = 0.0
    new_count = 0
    dupe_count = 0
    _prospects_to_research: list[str] = []

    try:
        # Search via Brave - fetches ALL location IDs in batches of 20
        search_results = await search_local_businesses(
            query, location_str, settings.brave_api_key,
        )
        total_cost += search_results.get("cost_usd", 0)
        all_results = search_results.get("results", [])

        # Process results
        for biz in all_results:
            place_id = biz.get("place_id", "")
            raw_phone = biz.get("phone", "")
            phone = normalize_phone(raw_phone) if raw_phone else ""

            if not place_id and not phone:
                continue

            # Check for duplicates by place_id
            if place_id:
                existing = await db.execute(
                    select(Outreach).where(
                        and_(
                            Outreach.tenant_id == config.tenant_id,
                            Outreach.source_place_id == place_id,
                        )
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    dupe_count += 1
                    continue

            # Check for duplicates by phone
            if phone:
                existing = await db.execute(
                    select(Outreach).where(
                        and_(
                            Outreach.tenant_id == config.tenant_id,
                            Outreach.prospect_phone == phone,
                        )
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    dupe_count += 1
                    continue

            # Parse address
            addr_parts = parse_address_components(biz.get("address", ""))

            # Try to find email via website scraping + pattern guessing
            email = None
            email_source = None
            email_verified = False
            website = biz.get("website", "")

            if website:
                enrichment = await enrich_prospect_email(website, biz.get("name", ""))
                if enrichment.get("email"):
                    email = enrichment["email"]
                    email_source = enrichment["source"]
                    email_verified = enrichment.get("verified", False)
            elif extract_domain(website):
                # No website but have domain somehow - pattern guess only
                from src.services.enrichment import guess_email_patterns
                domain = extract_domain(website)
                patterns = guess_email_patterns(domain)
                if patterns:
                    email = patterns[0]
                    email_source = "pattern_guess"

            # Validate email before storing
            if email:
                email_check = await validate_email(email)
                if not email_check["valid"]:
                    logger.info(
                        "Skipping invalid email for %s: %s (%s)",
                        biz.get("name", ""), email[:20] + "***", email_check["reason"],
                    )
                    email = None
                    email_source = None
                    email_verified = False

            # Create outreach prospect
            prospect = Outreach(
                tenant_id=config.tenant_id,
                prospect_name=biz.get("name", "Unknown"),
                prospect_company=biz.get("name"),
                prospect_email=email,
                prospect_phone=phone,
                prospect_trade_type=trade,
                status="cold",
                source="brave",
                source_place_id=place_id if place_id else None,
                website=website,
                google_rating=biz.get("rating"),
                review_count=biz.get("reviews"),
                address=biz.get("address"),
                city=addr_parts.get("city") or city,
                state_code=addr_parts.get("state") or state,
                zip_code=addr_parts.get("zip"),
                email_verified=email_verified,
                email_source=email_source,
                outreach_sequence_step=0,
            )
            db.add(prospect)
            await db.flush()  # Assign prospect.id within transaction
            new_count += 1

            # Collect prospects to research after commit
            if website:
                _prospects_to_research.append(str(prospect.id))

        # Update job
        job.status = "completed"
        job.results_found = len(all_results)
        job.new_prospects_created = new_count
        job.duplicates_skipped = dupe_count
        job.api_cost_usd = total_cost
        job.completed_at = datetime.now(timezone.utc)

        logger.info(
            "Scrape completed: %s in %s (variant=%d query='%s') - "
            "found=%d new=%d dupes=%d cost=$%.3f",
            trade, location_str, query_variant, query,
            len(all_results), new_count, dupe_count, total_cost,
        )

        # Enqueue prospect research tasks AFTER data is committed by caller.
        # Uses delay_seconds=10 so the outer commit has time to complete.
        if _prospects_to_research:
            from src.services.task_dispatch import enqueue_task
            for pid in _prospects_to_research:
                try:
                    await enqueue_task(
                        task_type="enrich_prospect",
                        payload={"outreach_id": pid},
                        priority=4,
                        delay_seconds=10,
                    )
                except Exception as enq_err:
                    logger.warning(
                        "Failed to enqueue research for %s: %s",
                        pid[:8], str(enq_err),
                    )
            logger.info("Enqueued %d prospect research tasks", len(_prospects_to_research))

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        job.api_cost_usd = total_cost
        logger.error("Scrape failed for %s in %s: %s", trade, location_str, str(e))
