"""
Production activation script — configure the sales engine for full operation.

This script:
1. Expands target_locations to 10 high-growth home services states
2. Raises campaign daily limits from 3 to 15 per campaign
3. Raises global daily email limit to 150
4. Activates the sales engine (is_active=True)
5. Sets daily scrape limit to 500
6. Generates a SendGrid webhook verification key (if missing from .env)

Usage:
    python -m scripts.activate_production                  # dry-run
    python -m scripts.activate_production --commit         # apply changes
    python -m scripts.activate_production --commit --key   # also generate webhook key
"""
import argparse
import asyncio
import logging
import secrets

from sqlalchemy import select, update

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Top 10 high-growth home services markets in the US.
# Each state lists 3-6 metro areas where contractor density is highest.
TARGET_LOCATIONS = [
    # Texas (existing)
    {"city": "Austin", "state": "TX"},
    {"city": "Houston", "state": "TX"},
    {"city": "Dallas", "state": "TX"},
    {"city": "San Antonio", "state": "TX"},
    {"city": "Fort Worth", "state": "TX"},
    # Florida
    {"city": "Miami", "state": "FL"},
    {"city": "Tampa", "state": "FL"},
    {"city": "Orlando", "state": "FL"},
    {"city": "Jacksonville", "state": "FL"},
    # Arizona
    {"city": "Phoenix", "state": "AZ"},
    {"city": "Tucson", "state": "AZ"},
    {"city": "Scottsdale", "state": "AZ"},
    # Georgia
    {"city": "Atlanta", "state": "GA"},
    {"city": "Savannah", "state": "GA"},
    {"city": "Augusta", "state": "GA"},
    # North Carolina
    {"city": "Charlotte", "state": "NC"},
    {"city": "Raleigh", "state": "NC"},
    {"city": "Durham", "state": "NC"},
    # Colorado
    {"city": "Denver", "state": "CO"},
    {"city": "Colorado Springs", "state": "CO"},
    {"city": "Aurora", "state": "CO"},
    # Tennessee
    {"city": "Nashville", "state": "TN"},
    {"city": "Memphis", "state": "TN"},
    {"city": "Knoxville", "state": "TN"},
    # Nevada
    {"city": "Las Vegas", "state": "NV"},
    {"city": "Henderson", "state": "NV"},
    {"city": "Reno", "state": "NV"},
    # South Carolina
    {"city": "Charleston", "state": "SC"},
    {"city": "Columbia", "state": "SC"},
    {"city": "Greenville", "state": "SC"},
    # California
    {"city": "Los Angeles", "state": "CA"},
    {"city": "San Diego", "state": "CA"},
    {"city": "Sacramento", "state": "CA"},
    {"city": "San Jose", "state": "CA"},
]

# All supported trade types
TARGET_TRADES = ["hvac", "plumbing", "roofing", "electrical", "solar", "general"]

# New limits
DAILY_EMAIL_LIMIT = 150
DAILY_SCRAPE_LIMIT = 500
CAMPAIGN_DAILY_LIMIT = 15


async def activate(commit: bool = False, generate_key: bool = False) -> None:
    """Activate the sales engine with expanded targeting and raised limits."""
    from src.database import async_session_factory
    from src.models.sales_config import SalesEngineConfig
    from src.models.campaign import Campaign

    mode = "[COMMIT]" if commit else "[DRY RUN]"

    # Generate webhook key if requested — printed to stdout only (not logger)
    # to avoid shipping the secret to external log aggregators.
    webhook_key = None
    if generate_key:
        webhook_key = secrets.token_urlsafe(32)
        print(f"\n{mode} Generated SendGrid webhook verification key:")
        print(f"  SENDGRID_WEBHOOK_VERIFICATION_KEY={webhook_key}")
        print(f"\n  Add to .env, then configure in SendGrid dashboard:")
        print(f"  Event Webhook:  https://api.leadlock.org/api/v1/sales/email-events?token={webhook_key}")
        print(f"  Inbound Parse:  https://api.leadlock.org/api/v1/sales/inbound-email?token={webhook_key}")
        print()

    async with async_session_factory() as db:
        # Find all sales engine configs
        result = await db.execute(select(SalesEngineConfig))
        configs = list(result.scalars().all())

        if not configs:
            logger.error("No SalesEngineConfig rows found. Create one first.")
            return

        for config in configs:
            tenant = str(config.tenant_id)[:8] if config.tenant_id else "global"
            logger.info("\n=== Tenant: %s ===", tenant)

            # Current state
            logger.info("  Current: is_active=%s, daily_email_limit=%d, daily_scrape_limit=%d",
                        config.is_active, config.daily_email_limit, config.daily_scrape_limit)
            logger.info("  Current locations: %d cities", len(config.target_locations or []))
            logger.info("  Current trades: %s", config.target_trade_types or [])

            # New state
            logger.info("  -> Setting is_active=True")
            logger.info("  -> Setting daily_email_limit=%d", DAILY_EMAIL_LIMIT)
            logger.info("  -> Setting daily_scrape_limit=%d", DAILY_SCRAPE_LIMIT)
            logger.info("  -> Setting target_locations=%d cities across 10 states", len(TARGET_LOCATIONS))
            logger.info("  -> Setting target_trade_types=%s", TARGET_TRADES)

            if commit:
                config.is_active = True
                config.daily_email_limit = DAILY_EMAIL_LIMIT
                config.daily_scrape_limit = DAILY_SCRAPE_LIMIT
                config.target_locations = TARGET_LOCATIONS
                config.target_trade_types = TARGET_TRADES

        # Raise campaign daily limits
        camp_result = await db.execute(select(Campaign))
        campaigns = list(camp_result.scalars().all())

        if campaigns:
            logger.info("\n=== Campaign Limits ===")
            for camp in campaigns:
                old_limit = camp.daily_limit
                logger.info(
                    "  %s [%s]: daily_limit %d -> %d",
                    camp.name, camp.status, old_limit, CAMPAIGN_DAILY_LIMIT,
                )
                if commit:
                    camp.daily_limit = CAMPAIGN_DAILY_LIMIT

        if commit:
            await db.commit()
            logger.info("\nChanges committed successfully.")
        else:
            logger.info("\nDRY RUN — no changes persisted. Use --commit to apply.")

    # Summary
    combos = len(TARGET_LOCATIONS) * len(TARGET_TRADES)
    logger.info("\n=== Scaling Summary ===")
    logger.info("  Locations: %d cities across 10 states", len(TARGET_LOCATIONS))
    logger.info("  Trades: %d", len(TARGET_TRADES))
    logger.info("  Scrape combos: %d (round-robin, 1 per cycle)", combos)
    logger.info("  Full rotation: %.1f days at %d scrapes/day", combos / DAILY_SCRAPE_LIMIT, DAILY_SCRAPE_LIMIT)
    logger.info("  Daily email capacity: %d (warmup may reduce initially)", DAILY_EMAIL_LIMIT)
    logger.info("  Campaign limits: %d/day per campaign", CAMPAIGN_DAILY_LIMIT)


def main():
    parser = argparse.ArgumentParser(
        description="Activate sales engine with expanded targeting and raised limits",
    )
    parser.add_argument(
        "--commit", action="store_true",
        help="Persist changes (default: dry-run)",
    )
    parser.add_argument(
        "--key", action="store_true",
        help="Generate a new SendGrid webhook verification key",
    )
    args = parser.parse_args()
    asyncio.run(activate(commit=args.commit, generate_key=args.key))


if __name__ == "__main__":
    main()
