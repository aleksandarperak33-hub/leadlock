"""
Lead scraper worker — discovers home services contractors from Google Maps and Yelp.
Runs every 6 hours. Respects daily scrape limits and deduplicates by place_id/phone.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.scrape_job import ScrapeJob
from src.models.sales_config import SalesEngineConfig
from src.services.scraping import search_google_maps, search_yelp, parse_address_components
from src.services.enrichment import find_email_hunter, guess_email_patterns, extract_domain
from src.config import get_settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
RESCRAPE_COOLDOWN_DAYS = 30

TRADE_QUERIES = {
    "hvac": "HVAC contractors",
    "plumbing": "plumbing contractors",
    "roofing": "roofing contractors",
    "electrical": "electrical contractors",
    "solar": "solar installation companies",
    "general": "home services contractors",
}


async def run_scraper():
    """Main loop — scrape for new prospects every 6 hours."""
    logger.info("Lead scraper started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            await scrape_cycle()
        except Exception as e:
            logger.error("Scraper cycle error: %s", str(e))

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
        if not settings.serpapi_api_key:
            logger.warning("SerpAPI key not configured, skipping scrape")
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

                # Check if recently scraped
                recent = await db.execute(
                    select(ScrapeJob).where(
                        and_(
                            ScrapeJob.city == city,
                            ScrapeJob.state_code == state,
                            ScrapeJob.trade_type == trade,
                            ScrapeJob.status == "completed",
                            ScrapeJob.created_at >= datetime.utcnow() - timedelta(days=RESCRAPE_COOLDOWN_DAYS),
                        )
                    ).limit(1)
                )
                if recent.scalar_one_or_none():
                    logger.debug("Skipping %s in %s — scraped within %d days", trade, location_str, RESCRAPE_COOLDOWN_DAYS)
                    continue

                await scrape_location_trade(db, config, settings, city, state, location_str, trade)
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
):
    """Scrape a single location+trade combination."""
    query = TRADE_QUERIES.get(trade, f"{trade} contractors")

    # Create scrape job record
    job = ScrapeJob(
        platform="google_maps",
        trade_type=trade,
        location_query=f"{query} in {location_str}",
        city=city,
        state_code=state,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(job)
    await db.flush()

    total_cost = 0.0
    new_count = 0
    dupe_count = 0
    all_results = []

    try:
        # Search Google Maps
        gm_results = await search_google_maps(query, location_str, settings.serpapi_api_key)
        total_cost += gm_results.get("cost_usd", 0)
        all_results.extend(gm_results.get("results", []))

        # Search Yelp
        yelp_results = await search_yelp(query, location_str, settings.serpapi_api_key)
        total_cost += yelp_results.get("cost_usd", 0)
        all_results.extend(yelp_results.get("results", []))

        # Process results
        for biz in all_results:
            place_id = biz.get("place_id", "")
            phone = biz.get("phone", "")

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

            # Create outreach prospect
            prospect = Outreach(
                prospect_name=biz.get("name", "Unknown"),
                prospect_company=biz.get("name"),
                prospect_email=email,
                prospect_phone=phone,
                prospect_trade_type=trade,
                status="cold",
                source="google_maps" if not place_id.startswith("yelp_") else "yelp",
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
            "Scrape completed: %s in %s — found=%d new=%d dupes=%d cost=$%.3f",
            trade, location_str, len(all_results), new_count, dupe_count, total_cost,
        )

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        job.api_cost_usd = total_cost
        logger.error("Scrape failed for %s in %s: %s", trade, location_str, str(e))
