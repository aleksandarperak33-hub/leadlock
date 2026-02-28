"""
Email finder worker — discovers real email addresses for unverified prospects.

Runs every 30 minutes, picks up prospects with unverified emails (including
those parked in no_verified_email), then runs multi-source email discovery
to try to find high-confidence, non-pattern addresses.

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
BATCH_SIZE = 75
HEARTBEAT_KEY = "leadlock:worker_health:email_finder"
RETRY_DAYS = 7  # Skip prospects attempted within this window

# Bounce retry: re-process "lost" prospects with a longer cooldown
BOUNCE_RETRY_DAYS = 14  # Longer than normal retry — give domain time to cool
BOUNCE_RETRY_BATCH = 15  # Reserve 15 slots (of 75 total) for bounce retries
NORMAL_BATCH_SIZE = BATCH_SIZE - BOUNCE_RETRY_BATCH  # 60 normal slots


async def run_email_finder():
    """Main loop — find real emails for unverified prospects."""
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


STALE_VERIFICATION_DAYS = 14  # Re-verify emails older than this


def _eligible_filter():
    """Base WHERE clause for unverified OR stale-verified prospects eligible for rediscovery."""
    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_VERIFICATION_DAYS)
    return and_(
        # Unverified OR stale verification (verified_at older than 14 days or NULL)
        or_(
            Outreach.email_verified == False,  # noqa: E712
            Outreach.verified_at.is_(None),
            Outreach.verified_at < stale_cutoff,
        ),
        Outreach.prospect_email.isnot(None),
        Outreach.prospect_email != "",
        Outreach.website.isnot(None),
        Outreach.website != "",
        Outreach.email_unsubscribed == False,  # noqa: E712
        Outreach.last_email_replied_at.is_(None),
        Outreach.status.in_(["cold", "contacted", "no_verified_email"]),
    )


def _retry_cutoff() -> datetime:
    """Cutoff timestamp — prospects attempted before this can be retried."""
    return datetime.now(timezone.utc) - timedelta(days=RETRY_DAYS)


def _bounce_retry_cutoff() -> datetime:
    """Cutoff timestamp for bounce-retry prospects (longer window)."""
    return datetime.now(timezone.utc) - timedelta(days=BOUNCE_RETRY_DAYS)


def _bounce_retry_filter():
    """
    WHERE clause for bounced ("lost") prospects eligible for email re-discovery.

    Selects prospects that:
    - Have status "lost" (set by hard-bounce handler)
    - Have email_verified=False (bounce invalidated the email)
    - Have a website (required for discovery strategies)
    - Haven't been attempted in BOUNCE_RETRY_DAYS
    - Haven't unsubscribed or replied
    """
    cutoff = _bounce_retry_cutoff()
    return and_(
        Outreach.status == "lost",
        Outreach.email_verified == False,  # noqa: E712
        Outreach.website.isnot(None),
        Outreach.website != "",
        Outreach.email_unsubscribed == False,  # noqa: E712
        Outreach.last_email_replied_at.is_(None),
        or_(
            Outreach.email_discovery_attempted_at.is_(None),
            Outreach.email_discovery_attempted_at < cutoff,
        ),
    )


async def _process_batch():
    """Pick up unverified prospects and bounced prospects, try to find real emails."""
    now = datetime.now(timezone.utc)
    cutoff = _retry_cutoff()

    async with async_session_factory() as db:
        # Count total eligible normal prospects (regardless of attempt history)
        total_q = select(func.count()).select_from(Outreach).where(_eligible_filter())
        total = (await db.execute(total_q)).scalar() or 0

        # Count how many normal prospects are actually due for (re)processing
        due_filter = and_(
            _eligible_filter(),
            or_(
                Outreach.email_discovery_attempted_at.is_(None),
                Outreach.email_discovery_attempted_at < cutoff,
            ),
        )
        due_q = select(func.count()).select_from(Outreach).where(due_filter)
        due = (await db.execute(due_q)).scalar() or 0

        # Count bounce-retry prospects
        bounce_due_q = select(func.count()).select_from(Outreach).where(_bounce_retry_filter())
        bounce_due = (await db.execute(bounce_due_q)).scalar() or 0

        if due == 0 and bounce_due == 0:
            if total > 0:
                logger.info(
                    "Email finder: %d unverified prospects, but all attempted within retry window — waiting",
                    total,
                )
            else:
                logger.debug("Email finder: no prospects to process")
            return

        logger.info(
            "Email finder: %d unverified due, %d bounce-retry due (normal batch %d, bounce batch %d)",
            due, bounce_due, min(due, NORMAL_BATCH_SIZE), min(bounce_due, BOUNCE_RETRY_BATCH),
        )

        # Fetch normal batch (60 slots)
        prospects: list[Outreach] = []
        bounce_retry_ids: set = set()

        if due > 0:
            fetch_q = (
                select(Outreach)
                .where(due_filter)
                .order_by(
                    Outreach.email_discovery_attempted_at.asc().nulls_first(),
                    Outreach.created_at.asc(),
                )
                .limit(NORMAL_BATCH_SIZE)
            )
            result = await db.execute(fetch_q)
            prospects.extend(result.scalars().all())

        # Fetch bounce-retry batch (15 slots)
        if bounce_due > 0:
            bounce_q = (
                select(Outreach)
                .where(_bounce_retry_filter())
                .order_by(
                    Outreach.email_discovery_attempted_at.asc().nulls_first(),
                    Outreach.created_at.asc(),
                )
                .limit(BOUNCE_RETRY_BATCH)
            )
            bounce_result = await db.execute(bounce_q)
            bounce_prospects = list(bounce_result.scalars().all())
            bounce_retry_ids = {p.id for p in bounce_prospects}
            prospects.extend(bounce_prospects)

        found = 0
        reactivated = 0
        kept = 0
        failed = 0
        bounce_reactivated = 0

        for prospect in prospects:
            domain = _extract_prospect_domain(prospect)
            is_bounce_retry = prospect.id in bounce_retry_ids

            logger.info(
                "Email finder: checking %s (%s)%s",
                prospect.prospect_name, domain or "no domain",
                " [bounce retry]" if is_bounce_retry else "",
            )

            try:
                # Pass db session for bounce-retry prospects to enable blacklist checks
                # 60s per-prospect timeout to prevent worker hangs on stuck domains
                discovery = await asyncio.wait_for(
                    discover_email(
                        website=prospect.website,
                        company_name=prospect.prospect_company or prospect.prospect_name,
                        enrichment_data=prospect.enrichment_data,
                        db=db if is_bounce_retry else None,
                    ),
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Email finder: discovery TIMED OUT for %s (%s) after 60s",
                    prospect.prospect_name, domain or "no domain",
                )
                prospect.email_discovery_attempted_at = now
                failed += 1
                continue
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
            cost = discovery.get("cost_usd", 0.0)
            if cost > 0:
                prospect.total_cost_usd = (prospect.total_cost_usd or 0) + cost

            if not new_email:
                logger.debug("Email finder: no email found for %s", prospect.prospect_name)
                failed += 1
                continue

            # Did we find something better than current unverified data?
            current_email = prospect.prospect_email
            if source == "pattern_guess" or confidence != "high":
                # Keep prospect parked; only high-confidence non-pattern addresses
                # are send-eligible for first-touch outreach.
                kept += 1
                logger.debug(
                    "Email finder: non-send-eligible result (%s/%s) for %s, retry in %dd",
                    source or "unknown",
                    confidence or "unknown",
                    prospect.prospect_name,
                    BOUNCE_RETRY_DAYS if is_bounce_retry else RETRY_DAYS,
                )
                continue

            # Found a real email from a better source
            if new_email.lower() == (current_email or "").lower():
                # Same email but from a better source — upgrade the source
                prospect.email_source = source
                prospect.email_verified = True
                prospect.verified_at = now
                kept += 1
                logger.info(
                    "Email finder: confirmed %s***@%s via %s",
                    new_email.split("@")[0][:3], domain or "?", source,
                )
            else:
                # Different (better) email found
                prospect.prospect_email = new_email.lower().strip()
                prospect.email_source = source
                prospect.email_verified = True
                prospect.verified_at = now
                found += 1
                logger.info(
                    "Email finder: replaced with %s***@%s via %s (was %s***)",
                    new_email.split("@")[0][:3], domain or "?", source,
                    (current_email or "").split("@")[0][:3],
                )

                # Bounce retry: reactivate to "cold" if we found a DIFFERENT high-confidence email
                if is_bounce_retry:
                    prospect.status = "cold"
                    bounce_reactivated += 1
                    logger.info(
                        "Email finder: bounce retry — reactivated %s to cold with new email",
                        prospect.prospect_name,
                    )

            if prospect.status == "no_verified_email":
                prospect.status = "cold"
                reactivated += 1

        await db.commit()

        logger.info(
            "Email finder cycle: %d found, %d reactivated, %d bounce-reactivated, %d kept, %d failed (of %d processed)",
            found, reactivated, bounce_reactivated, kept, failed, len(prospects),
        )


def _extract_prospect_domain(prospect: Outreach) -> str | None:
    """Extract domain from a prospect's website URL."""
    if not prospect.website:
        return None
    from src.services.enrichment import extract_domain
    return extract_domain(prospect.website)
