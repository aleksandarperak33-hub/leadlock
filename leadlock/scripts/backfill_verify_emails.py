"""
Backfill SMTP verification for existing pattern-guessed prospect emails.

Runs verify_smtp_mailbox() on all prospects with email_source='pattern_guess'
and email_verified=False. Marks verified emails, replaces rejected ones with
alternate patterns, and flags unreachable prospects.

Processes in batches to avoid holding a DB session open for hours.
Commits per-batch so progress survives interruptions.

Usage:
    python scripts/backfill_verify_emails.py                  # dry-run
    python scripts/backfill_verify_emails.py --commit         # persist changes
    python scripts/backfill_verify_emails.py --limit 100      # process 100 only
    python scripts/backfill_verify_emails.py --commit --limit 50
"""
import argparse
import asyncio
import logging
import time
from collections import defaultdict

from sqlalchemy import select, and_, func

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 50
# Rate limit: minimum seconds between SMTP checks to the same domain
DOMAIN_COOLDOWN_S = 1.5

# Shared filter for eligible prospects
_ELIGIBLE_STATUSES_EXCLUDE = ["lost", "won", "no_verified_email", "duplicate_email"]


def _mask_local(email: str) -> str:
    """Mask email local part for logging (3 chars + ***)."""
    local = email.split("@")[0] if "@" in email else email
    return local[:3] + "***"


def _eligible_filter(Outreach):
    """Return SQLAlchemy filter for backfill-eligible prospects."""
    return and_(
        Outreach.email_source == "pattern_guess",
        Outreach.email_verified == False,  # noqa: E712
        Outreach.prospect_email.isnot(None),
        Outreach.status.notin_(_ELIGIBLE_STATUSES_EXCLUDE),
    )


async def backfill(limit: int = 0, commit: bool = False):
    """SMTP-verify unverified pattern-guessed prospect emails in batches."""
    from src.database import async_session_factory
    from src.models.outreach import Outreach
    from src.services.enrichment import extract_domain
    from src.utils.email_validation import verify_smtp_mailbox

    # Get total count in a short-lived session
    async with async_session_factory() as db:
        count_q = select(func.count()).select_from(Outreach).where(_eligible_filter(Outreach))
        total = (await db.execute(count_q)).scalar() or 0

    effective = min(total, limit) if limit > 0 else total
    logger.info(
        "Found %d unverified pattern-guessed prospects (processing %d)%s",
        total, effective, " [DRY RUN]" if not commit else "",
    )

    if effective == 0:
        logger.info("Nothing to do.")
        return

    # Counters
    stats = {"verified": 0, "replaced": 0, "rejected": 0, "inconclusive": 0, "error": 0}
    domain_last_check: dict[str, float] = defaultdict(float)
    processed = 0
    offset = 0

    while processed < effective:
        batch_limit = min(BATCH_SIZE, effective - processed)

        # Fresh session per batch — avoids idle-in-transaction timeout
        async with async_session_factory() as db:
            fetch_q = (
                select(Outreach)
                .where(_eligible_filter(Outreach))
                .order_by(Outreach.created_at.asc())
                .offset(offset)
                .limit(batch_limit)
            )
            result = await db.execute(fetch_q)
            batch = list(result.scalars().all())

            if not batch:
                break

            for prospect in batch:
                processed += 1
                email = prospect.prospect_email
                domain = extract_domain(prospect.website) if prospect.website else None
                if not domain and "@" in (email or ""):
                    domain = email.split("@")[1]

                if not domain:
                    logger.debug(
                        "  [%d/%d] No domain — skip", processed, effective,
                    )
                    stats["inconclusive"] += 1
                    continue

                # Rate limit per domain
                elapsed = time.monotonic() - domain_last_check[domain]
                if elapsed < DOMAIN_COOLDOWN_S:
                    await asyncio.sleep(DOMAIN_COOLDOWN_S - elapsed)
                domain_last_check[domain] = time.monotonic()

                logger.info(
                    "  [%d/%d] Checking %s@%s",
                    processed, effective, _mask_local(email), domain,
                )

                try:
                    smtp_result = await verify_smtp_mailbox(email)
                except Exception as e:
                    logger.warning("  SMTP error: %s", str(e))
                    stats["error"] += 1
                    continue

                if smtp_result["exists"] is True:
                    logger.info("  -> VERIFIED")
                    stats["verified"] += 1
                    if commit:
                        prospect.email_verified = True

                elif smtp_result["exists"] is False:
                    logger.info("  -> REJECTED, trying alternates...")
                    replacement, was_confirmed = await _try_alternate_patterns(
                        domain, email, prospect.prospect_name,
                        verify_smtp_mailbox, domain_last_check,
                    )

                    if replacement is not None:
                        logger.info(
                            "  -> REPLACED with %s@%s (confirmed=%s)",
                            _mask_local(replacement), domain, was_confirmed,
                        )
                        stats["replaced"] += 1
                        if commit:
                            prospect.prospect_email = replacement
                            prospect.email_verified = was_confirmed
                    else:
                        logger.info("  -> ALL PATTERNS REJECTED")
                        stats["rejected"] += 1
                        if commit:
                            prospect.status = "no_verified_email"

                else:
                    logger.info("  -> INCONCLUSIVE (%s)", smtp_result.get("reason", ""))
                    stats["inconclusive"] += 1

            if commit:
                await db.commit()
                logger.info("Batch committed (%d/%d processed)", processed, effective)

        # Advance offset by batch size (not by processed count, since
        # committed status changes may shift rows out of the result set)
        offset += batch_limit

    if not commit:
        logger.info("DRY RUN — no changes persisted. Use --commit to apply.")

    logger.info(
        "Summary: %d verified, %d replaced, %d rejected (no_verified_email), "
        "%d inconclusive (skipped), %d errors",
        stats["verified"], stats["replaced"], stats["rejected"],
        stats["inconclusive"], stats["error"],
    )


async def _try_alternate_patterns(
    domain: str,
    current_email: str,
    prospect_name: str | None,
    verify_fn,
    domain_last_check: dict,
) -> tuple[str | None, bool]:
    """
    Try alternate email patterns for a domain.

    Returns:
        (email, was_confirmed): email is the best alternate found (or None),
        was_confirmed is True only if SMTP returned exists=True.
    """
    from src.services.enrichment import guess_email_patterns

    patterns = guess_email_patterns(domain, name=prospect_name)
    # Skip the pattern we already know is rejected
    patterns = [p for p in patterns if p.lower() != current_email.lower()]

    inconclusive_fallback: str | None = None
    for pattern_email in patterns:
        # Rate limit per domain
        elapsed = time.monotonic() - domain_last_check[domain]
        if elapsed < DOMAIN_COOLDOWN_S:
            await asyncio.sleep(DOMAIN_COOLDOWN_S - elapsed)
        domain_last_check[domain] = time.monotonic()

        try:
            smtp_result = await verify_fn(pattern_email)

            if smtp_result["exists"] is True:
                return pattern_email, True

            if smtp_result["exists"] is False:
                continue

            # Inconclusive — save first as fallback, keep searching for confirmed
            if inconclusive_fallback is None:
                inconclusive_fallback = pattern_email

        except Exception as e:
            logger.debug(
                "  SMTP error for alternate %s@%s: %s",
                _mask_local(pattern_email), domain, str(e),
            )
            continue

    if inconclusive_fallback is not None:
        return inconclusive_fallback, False
    return None, False


def main():
    parser = argparse.ArgumentParser(description="Backfill SMTP email verification for prospects")
    parser.add_argument("--commit", action="store_true", help="Persist changes (default: dry-run)")
    parser.add_argument("--limit", type=int, default=0, help="Max prospects to process (0=all)")
    args = parser.parse_args()

    asyncio.run(backfill(limit=args.limit, commit=args.commit))


if __name__ == "__main__":
    main()
