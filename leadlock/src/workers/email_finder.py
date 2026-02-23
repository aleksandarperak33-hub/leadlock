"""
Email finder worker — discovers real email addresses for unverified prospects.

Runs every 30 minutes, picks up prospects whose emails were pattern-guessed
and never verified, then runs multi-source email discovery (deep website scrape,
Brave Search, enrichment candidates) to replace guessed emails with real ones.

This is the solution for environments where port 25 is blocked and SMTP
verification cannot be used.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_, func

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.services.email_discovery import discover_email
from src.utils.dedup import get_redis

logger = logging.getLogger(__name__)

POLL_INTERVAL = 1800  # 30 minutes
BATCH_SIZE = 20
HEARTBEAT_KEY = "leadlock:worker_health:email_finder"


async def run_email_finder():
    """Main loop — find real emails for unverified pattern-guessed prospects."""
    logger.info("Email finder started (poll every %ds)", POLL_INTERVAL)

    # Wait 3 minutes on startup to let other workers initialize
    await asyncio.sleep(180)

    while True:
        try:
            await _process_batch()
        except asyncio.CancelledError:
            logger.info("Email finder shutting down")
            return
        except Exception:
            logger.exception("Email finder cycle failed")

        # Heartbeat
        try:
            redis = await get_redis()
            await redis.set(
                HEARTBEAT_KEY,
                datetime.now(timezone.utc).isoformat(),
                ex=POLL_INTERVAL * 3,
            )
        except Exception as e:
            logger.debug("Heartbeat write failed: %s", str(e))

        await asyncio.sleep(POLL_INTERVAL)


async def _process_batch():
    """Pick up unverified prospects and try to find real emails."""
    async with async_session_factory() as db:
        # Count eligible
        count_q = select(func.count()).select_from(Outreach).where(
            and_(
                Outreach.email_source == "pattern_guess",
                Outreach.email_verified == False,  # noqa: E712
                Outreach.prospect_email.isnot(None),
                Outreach.website.isnot(None),
                Outreach.status.notin_([
                    "lost", "won", "no_verified_email",
                    "duplicate_email", "unreachable",
                ]),
            )
        )
        total = (await db.execute(count_q)).scalar() or 0

        if total == 0:
            logger.debug("Email finder: no unverified prospects to process")
            return

        logger.info("Email finder: %d unverified prospects, processing %d", total, min(total, BATCH_SIZE))

        # Fetch oldest first (FIFO)
        fetch_q = (
            select(Outreach)
            .where(
                and_(
                    Outreach.email_source == "pattern_guess",
                    Outreach.email_verified == False,  # noqa: E712
                    Outreach.prospect_email.isnot(None),
                    Outreach.website.isnot(None),
                    Outreach.status.notin_([
                        "lost", "won", "no_verified_email",
                        "duplicate_email", "unreachable",
                    ]),
                )
            )
            .order_by(Outreach.created_at.asc())
            .limit(BATCH_SIZE)
        )
        result = await db.execute(fetch_q)
        prospects = list(result.scalars().all())

        found = 0
        kept = 0
        failed = 0

        for prospect in prospects:
            domain = None
            if prospect.website:
                from src.services.enrichment import extract_domain
                domain = extract_domain(prospect.website)

            logger.info(
                "Email finder: checking %s (%s)",
                prospect.prospect_name, domain or "no domain",
            )

            try:
                discovery = await discover_email(
                    website=prospect.website,
                    company_name=prospect.prospect_company or prospect.prospect_name,
                    enrichment_data=prospect.enrichment_data,
                )
            except Exception as e:
                logger.warning(
                    "Email finder: discovery failed for %s: %s",
                    prospect.prospect_name, str(e),
                )
                failed += 1
                continue

            new_email = discovery.get("email")
            source = discovery.get("source")
            confidence = discovery.get("confidence")

            if not new_email:
                logger.debug("Email finder: no email found for %s", prospect.prospect_name)
                failed += 1
                continue

            # Did we find something better than the current pattern guess?
            current_email = prospect.prospect_email
            if source == "pattern_guess":
                # Same strategy, just keep what we have
                kept += 1
                logger.debug(
                    "Email finder: only pattern guess available for %s, keeping current",
                    prospect.prospect_name,
                )
                continue

            # Found a real email from a better source
            if new_email.lower() == (current_email or "").lower():
                # Same email but from a better source — upgrade the source
                prospect.email_source = source
                prospect.email_verified = confidence == "high"
                kept += 1
                logger.info(
                    "Email finder: confirmed %s***@%s via %s",
                    new_email.split("@")[0][:3], domain or "?", source,
                )
            else:
                # Different (better) email found
                prospect.prospect_email = new_email
                prospect.email_source = source
                prospect.email_verified = confidence == "high"
                found += 1
                logger.info(
                    "Email finder: replaced with %s***@%s via %s (was %s***)",
                    new_email.split("@")[0][:3], domain or "?", source,
                    (current_email or "").split("@")[0][:3],
                )

            # Track discovery cost
            cost = discovery.get("cost_usd", 0.0)
            if cost > 0:
                prospect.total_cost_usd = (prospect.total_cost_usd or 0) + cost

        await db.commit()

        logger.info(
            "Email finder cycle: %d found, %d kept, %d failed (of %d processed)",
            found, kept, failed, len(prospects),
        )

        # Track cost in Redis for dashboard
        if any(d.get("cost_usd", 0) > 0 for d in []):
            try:
                redis = await get_redis()
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                cost_key = f"leadlock:agent_costs:{today}"
                await redis.hincrbyfloat(cost_key, "email_finder", 0.0)
            except Exception as e:
                logger.debug("Cost tracking write failed: %s", str(e))
