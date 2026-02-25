"""
Email finder worker — discovers real email addresses for unverified prospects.

Runs every 30 minutes, picks up prospects whose emails were pattern-guessed
and never verified, then runs multi-source email discovery (deep website scrape,
Brave Search, enrichment candidates) to replace guessed emails with real ones.

Tracks discovery attempts via email_discovery_attempted_at to avoid re-processing
the same prospects every cycle. Prospects are retried after RETRY_DAYS.

This is the solution for environments where port 25 is blocked and SMTP
verification cannot be used.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_, or_, func

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.services.email_discovery import discover_email
from src.utils.dedup import get_redis

logger = logging.getLogger(__name__)

POLL_INTERVAL = 1800  # 30 minutes
BATCH_SIZE = 20
HEARTBEAT_KEY = "leadlock:worker_health:email_finder"
RETRY_DAYS = 7  # Skip prospects attempted within this window


async def run_email_finder():
    """Main loop — find real emails for unverified pattern-guessed prospects."""
    logger.info("Email finder started (poll every %ds, retry after %dd)", POLL_INTERVAL, RETRY_DAYS)

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


def _eligible_filter():
    """Base WHERE clause for unverified pattern-guess prospects."""
    return and_(
        Outreach.email_source == "pattern_guess",
        Outreach.email_verified == False,  # noqa: E712
        Outreach.prospect_email.isnot(None),
        Outreach.website.isnot(None),
        Outreach.status.notin_([
            "lost", "won", "no_verified_email",
            "duplicate_email", "unreachable",
        ]),
    )


def _retry_cutoff() -> datetime:
    """Cutoff timestamp — prospects attempted before this can be retried."""
    return datetime.now(timezone.utc) - timedelta(days=RETRY_DAYS)


async def _process_batch():
    """Pick up unverified prospects and try to find real emails."""
    now = datetime.now(timezone.utc)
    cutoff = _retry_cutoff()

    async with async_session_factory() as db:
        # Count total eligible (regardless of attempt history)
        total_q = select(func.count()).select_from(Outreach).where(_eligible_filter())
        total = (await db.execute(total_q)).scalar() or 0

        if total == 0:
            logger.debug("Email finder: no unverified prospects to process")
            return

        # Count how many are actually due for (re)processing
        due_filter = and_(
            _eligible_filter(),
            or_(
                Outreach.email_discovery_attempted_at.is_(None),
                Outreach.email_discovery_attempted_at < cutoff,
            ),
        )
        due_q = select(func.count()).select_from(Outreach).where(due_filter)
        due = (await db.execute(due_q)).scalar() or 0

        if due == 0:
            logger.info(
                "Email finder: %d unverified prospects, but all attempted within %dd — waiting",
                total, RETRY_DAYS,
            )
            return

        logger.info(
            "Email finder: %d unverified total, %d due for processing, batch %d",
            total, due, min(due, BATCH_SIZE),
        )

        # Fetch batch — prioritize never-attempted, then oldest attempts first
        # Secondary sort: prospects WITH websites before those without (all have websites
        # per filter, but keep the pattern for future-proofing)
        fetch_q = (
            select(Outreach)
            .where(due_filter)
            .order_by(
                # Never-attempted first (NULL sorts first with nulls_first)
                Outreach.email_discovery_attempted_at.asc().nulls_first(),
                Outreach.created_at.asc(),
            )
            .limit(BATCH_SIZE)
        )
        result = await db.execute(fetch_q)
        prospects = list(result.scalars().all())

        found = 0
        kept = 0
        failed = 0

        for prospect in prospects:
            domain = _extract_prospect_domain(prospect)

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
                # Stamp the attempt so we don't retry immediately
                prospect.email_discovery_attempted_at = now
                failed += 1
                continue

            new_email = discovery.get("email")
            source = discovery.get("source")
            confidence = discovery.get("confidence")

            # Always stamp the attempt timestamp regardless of outcome
            prospect.email_discovery_attempted_at = now

            if not new_email:
                logger.debug("Email finder: no email found for %s", prospect.prospect_name)
                failed += 1
                continue

            # Did we find something better than the current pattern guess?
            current_email = prospect.prospect_email
            if source == "pattern_guess":
                # Same strategy — nothing better available, skip for now
                kept += 1
                logger.debug(
                    "Email finder: only pattern guess available for %s, will retry in %dd",
                    prospect.prospect_name, RETRY_DAYS,
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
            "Email finder cycle: %d found, %d kept, %d failed (of %d processed, %d remaining)",
            found, kept, failed, len(prospects), due - len(prospects),
        )


def _extract_prospect_domain(prospect: Outreach) -> str | None:
    """Extract domain from a prospect's website URL."""
    if not prospect.website:
        return None
    from src.services.enrichment import extract_domain
    return extract_domain(prospect.website)
