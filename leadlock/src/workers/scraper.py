"""
Lead scraper worker — discovers home services contractors via Brave Search API.
Runs every 6 hours. Uses query rotation + offset pagination so re-scrapes
always return fresh results instead of duplicates.
Deduplicates by place_id and phone number.
"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.scrape_job import ScrapeJob
from src.models.sales_config import SalesEngineConfig
from src.services.scraping import search_local_businesses, parse_address_components
from src.services.enrichment import find_email_hunter, guess_email_patterns, extract_domain
from src.services.phone_validation import normalize_phone
from src.utils.email_validation import validate_email
from src.config import get_settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
MAX_BRAVE_OFFSET = 9  # Brave Search API max offset

# Multiple query variations per trade — each produces different Brave results.
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
        await redis.set("leadlock:worker_health:scraper", datetime.utcnow().isoformat(), ex=7200)
    except Exception:
        pass


def get_query_variants(trade: str) -> list[str]:
    """Get query variations for a trade type."""
    return TRADE_QUERY_VARIANTS.get(trade, [f"{trade} contractors"])


async def get_next_variant_and_offset(
    db: AsyncSession,
    city: str,
    state: str,
    trade: str,
) -> tuple[int, int]:
    """
    Determine the next query_variant + search_offset to use for a location+trade.
    Looks at all completed scrape jobs for this combo and picks the next unused slot.

    Rotation order:
      variant=0 offset=0 → variant=1 offset=0 → ... → variant=N offset=0
      → variant=0 offset=1 → variant=1 offset=1 → ... → variant=N offset=1
      → ... up to MAX_BRAVE_OFFSET

    Returns:
        (query_variant_index, search_offset) or (-1, -1) if all exhausted.
    """
    num_variants = len(get_query_variants(trade))
    if num_variants == 0:
        return -1, -1

    # Get all completed scrape jobs for this location+trade
    result = await db.execute(
        select(ScrapeJob.query_variant, ScrapeJob.search_offset).where(
            and_(
                ScrapeJob.city == city,
                ScrapeJob.state_code == state,
                ScrapeJob.trade_type == trade,
                ScrapeJob.status == "completed",
            )
        )
    )
    used_slots = {(row[0], row[1]) for row in result.all()}

    # Find the next unused slot: iterate offsets, then variants within each offset
    for offset in range(MAX_BRAVE_OFFSET + 1):
        for variant in range(num_variants):
            if (variant, offset) not in used_slots:
                return variant, offset

    # All slots exhausted
    return -1, -1


async def run_scraper():
    """Main loop — scrape for new prospects every 6 hours."""
    logger.info("Lead scraper started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            await scrape_cycle()
        except Exception as e:
            logger.error("Scraper cycle error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def scrape_cycle():
    """Execute one full scrape cycle across all configured locations and trades."""
    async with async_session_factory() as db:
        # Load config
        result = await db.execute(select(SalesEngineConfig).limit(1))
        config = result.scalar_one_or_none()

        if not config or not config.is_active:
            logger.debug("Sales engine is disabled, skipping scrape cycle")
            return

        settings = get_settings()
        if not settings.brave_api_key:
            logger.warning("Brave API key not configured, skipping scrape")
            return

        locations = config.target_locations or []
        trade_types = config.target_trade_types or []

        if not locations or not trade_types:
            logger.debug("No target locations or trade types configured")
            return

        # Count today's scrapes
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        count_result = await db.execute(
            select(func.count()).select_from(ScrapeJob).where(
                ScrapeJob.created_at >= today_start
            )
        )
        today_scrapes = count_result.scalar() or 0

        if today_scrapes >= config.daily_scrape_limit:
            logger.info("Daily scrape limit reached (%d)", config.daily_scrape_limit)
            return

        for loc in locations:
            city = loc.get("city", "")
            state = loc.get("state", "")
            location_str = f"{city}, {state}"

            for trade in trade_types:
                if today_scrapes >= config.daily_scrape_limit:
                    logger.info("Daily scrape limit reached during cycle")
                    return

                # Find the next unused query variant + offset for this location+trade
                variant_idx, offset = await get_next_variant_and_offset(db, city, state, trade)

                if variant_idx == -1:
                    logger.info(
                        "All query variants exhausted for %s in %s "
                        "(%d variants x %d offsets). Skipping.",
                        trade, location_str,
                        len(get_query_variants(trade)), MAX_BRAVE_OFFSET + 1,
                    )
                    continue

                variants = get_query_variants(trade)
                query = variants[variant_idx]

                await scrape_location_trade(
                    db, config, settings, city, state, location_str,
                    trade, query, variant_idx, offset,
                )
                today_scrapes += 1

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
    """Scrape a single location+trade combination with specific query variant and offset."""
    # Create scrape job record
    job = ScrapeJob(
        platform="brave",
        trade_type=trade,
        location_query=f"{query} in {location_str}",
        city=city,
        state_code=state,
        query_variant=query_variant,
        search_offset=search_offset,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(job)
    await db.flush()

    total_cost = 0.0
    new_count = 0
    dupe_count = 0

    try:
        # Search via Brave with offset for pagination
        search_results = await search_local_businesses(
            query, location_str, settings.brave_api_key, offset=search_offset,
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
                    select(Outreach).where(Outreach.source_place_id == place_id).limit(1)
                )
                if existing.scalar_one_or_none():
                    dupe_count += 1
                    continue

            # Check for duplicates by phone
            if phone:
                existing = await db.execute(
                    select(Outreach).where(Outreach.prospect_phone == phone).limit(1)
                )
                if existing.scalar_one_or_none():
                    dupe_count += 1
                    continue

            # Parse address
            addr_parts = parse_address_components(biz.get("address", ""))

            # Try to find email
            email = None
            email_source = None
            email_verified = False
            website = biz.get("website", "")
            domain = extract_domain(website) if website else None

            if domain and settings.hunter_api_key:
                hunter_result = await find_email_hunter(domain, biz["name"], settings.hunter_api_key)
                total_cost += hunter_result.get("cost_usd", 0)
                if hunter_result.get("email"):
                    email = hunter_result["email"]
                    email_source = "hunter"
                    email_verified = hunter_result.get("confidence", 0) >= 80

            # Fallback: guess email pattern
            if not email and domain:
                patterns = guess_email_patterns(domain)
                if patterns:
                    email = patterns[0]  # Use info@domain as best guess
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
            new_count += 1

        # Update job
        job.status = "completed"
        job.results_found = len(all_results)
        job.new_prospects_created = new_count
        job.duplicates_skipped = dupe_count
        job.api_cost_usd = total_cost
        job.completed_at = datetime.utcnow()

        logger.info(
            "Scrape completed: %s in %s (variant=%d offset=%d query='%s') — "
            "found=%d new=%d dupes=%d cost=$%.3f",
            trade, location_str, query_variant, search_offset, query,
            len(all_results), new_count, dupe_count, total_cost,
        )

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        job.api_cost_usd = total_cost
        logger.error("Scrape failed for %s in %s: %s", trade, location_str, str(e))
