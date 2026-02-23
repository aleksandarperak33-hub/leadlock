"""
Backfill email discovery for existing pattern-guessed prospect emails.

Runs discover_email() on all prospects with email_source='pattern_guess'
and email_verified=False, replacing guessed emails with real ones found
through deep website scraping, Brave Search, and enrichment candidates.

Replaces the old SMTP-based backfill (backfill_verify_emails.py) which
cannot work when port 25 is blocked on the VPS.

Processes in batches with fresh DB sessions to avoid idle-in-transaction.
Commits per-batch so progress survives interruptions.

Usage:
    python -m scripts.backfill_discover_emails                           # dry-run
    python -m scripts.backfill_discover_emails --commit                  # persist changes
    python -m scripts.backfill_discover_emails --limit 100               # process 100 only
    python -m scripts.backfill_discover_emails --commit --concurrency 5  # parallel
"""
import argparse
import asyncio
import logging
import time

from sqlalchemy import select, and_, func

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 50
INTER_BATCH_PAUSE_S = 2.0

# Exclude terminal statuses that should not be re-processed
_ELIGIBLE_STATUSES_EXCLUDE = [
    "lost", "won", "no_verified_email", "duplicate_email", "unreachable",
]


def _mask_email(email: str) -> str:
    """Mask email for PII-safe logging: first 3 chars of local part + ***@domain."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[:3]}***@{domain}"


def _eligible_filter(Outreach):
    """Return SQLAlchemy filter for backfill-eligible prospects."""
    return and_(
        Outreach.email_source == "pattern_guess",
        Outreach.email_verified == False,  # noqa: E712
        Outreach.prospect_email.isnot(None),
        Outreach.website.isnot(None),
        Outreach.status.notin_(_ELIGIBLE_STATUSES_EXCLUDE),
    )


async def _discover_one(
    prospect_id,
    website: str,
    company_name: str,
    enrichment_data: dict | None,
    semaphore: asyncio.Semaphore,
) -> dict:
    """
    Run discover_email for a single prospect, guarded by a concurrency semaphore.

    Returns a result dict with prospect_id and discovery outcome.
    """
    from src.services.email_discovery import discover_email

    async with semaphore:
        try:
            discovery = await discover_email(
                website=website,
                company_name=company_name,
                enrichment_data=enrichment_data,
            )
            return {
                "prospect_id": prospect_id,
                "discovery": discovery,
                "error": None,
            }
        except Exception as e:
            return {
                "prospect_id": prospect_id,
                "discovery": None,
                "error": str(e),
            }


async def backfill(
    limit: int = 0,
    commit: bool = False,
    concurrency: int = 5,
) -> None:
    """Discover real emails for unverified pattern-guessed prospects in batches."""
    from src.database import async_session_factory
    from src.models.outreach import Outreach
    from src.services.enrichment import extract_domain

    # Count eligible prospects in a short-lived session
    async with async_session_factory() as db:
        count_q = (
            select(func.count())
            .select_from(Outreach)
            .where(_eligible_filter(Outreach))
        )
        total = (await db.execute(count_q)).scalar() or 0

    effective = min(total, limit) if limit > 0 else total
    mode_label = " [DRY RUN]" if not commit else ""
    logger.info(
        "Found %d unverified pattern-guessed prospects (processing %d, concurrency=%d)%s",
        total, effective, concurrency, mode_label,
    )

    if effective == 0:
        logger.info("Nothing to do.")
        return

    # Counters
    stats = {"found": 0, "kept": 0, "skipped": 0, "failed": 0}
    total_cost = 0.0
    processed = 0
    offset = 0
    semaphore = asyncio.Semaphore(concurrency)

    while processed < effective:
        batch_limit = min(BATCH_SIZE, effective - processed)
        batch_start = time.monotonic()

        # Fresh session per batch to avoid idle-in-transaction
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

            # Launch concurrent discovery tasks for the batch
            tasks = [
                _discover_one(
                    prospect_id=prospect.id,
                    website=prospect.website,
                    company_name=prospect.prospect_company or prospect.prospect_name,
                    enrichment_data=prospect.enrichment_data,
                    semaphore=semaphore,
                )
                for prospect in batch
            ]
            results = await asyncio.gather(*tasks)

            # Build lookup: prospect_id -> discovery result
            results_by_id = {r["prospect_id"]: r for r in results}

            # Apply results to prospects
            for prospect in batch:
                processed += 1
                disc_result = results_by_id.get(prospect.id)

                if disc_result is None:
                    stats["failed"] += 1
                    continue

                if disc_result["error"] is not None:
                    domain = extract_domain(prospect.website) if prospect.website else "?"
                    logger.warning(
                        "  [%d/%d] Discovery failed for %s (%s): %s",
                        processed, effective, prospect.prospect_name,
                        domain, disc_result["error"],
                    )
                    stats["failed"] += 1
                    continue

                discovery = disc_result["discovery"]
                new_email = discovery.get("email")
                source = discovery.get("source")
                confidence = discovery.get("confidence")
                cost = discovery.get("cost_usd", 0.0)
                current_email = prospect.prospect_email
                domain = extract_domain(prospect.website) if prospect.website else "?"

                if not new_email:
                    logger.info(
                        "  [%d/%d] No email found for %s (%s)",
                        processed, effective, prospect.prospect_name, domain,
                    )
                    stats["failed"] += 1
                    continue

                # If discovery only returned another pattern guess, skip
                if source == "pattern_guess":
                    logger.debug(
                        "  [%d/%d] Only pattern guess for %s, keeping current",
                        processed, effective, prospect.prospect_name,
                    )
                    stats["skipped"] += 1
                    continue

                # Same email but better source: upgrade attribution
                if new_email.lower() == (current_email or "").lower():
                    logger.info(
                        "  [%d/%d] Confirmed %s via %s (same email, better source)",
                        processed, effective, _mask_email(new_email), source,
                    )
                    stats["kept"] += 1
                    if commit:
                        prospect.email_source = source
                        prospect.email_verified = confidence == "high"
                        if cost > 0:
                            prospect.total_cost_usd = (prospect.total_cost_usd or 0) + cost
                    total_cost += cost
                    continue

                # Different email from better source: replace
                logger.info(
                    "  [%d/%d] Replaced %s -> %s via %s",
                    processed, effective,
                    _mask_email(current_email or ""),
                    _mask_email(new_email),
                    source,
                )
                stats["found"] += 1
                if commit:
                    prospect.prospect_email = new_email
                    prospect.email_source = source
                    prospect.email_verified = confidence == "high"
                    if cost > 0:
                        prospect.total_cost_usd = (prospect.total_cost_usd or 0) + cost
                total_cost += cost

            if commit:
                await db.commit()
                logger.info(
                    "Batch committed (%d/%d processed)", processed, effective,
                )

        # Advance offset (committed changes may shift rows out of result set)
        offset += batch_limit

        # Rate-limit between batches
        if processed < effective:
            elapsed = time.monotonic() - batch_start
            pause = max(0, INTER_BATCH_PAUSE_S - elapsed)
            if pause > 0:
                logger.debug("Pausing %.1fs between batches", pause)
                await asyncio.sleep(pause)

    if not commit:
        logger.info("DRY RUN -- no changes persisted. Use --commit to apply.")

    logger.info(
        "Summary: %d found (replaced), %d kept (upgraded source), "
        "%d skipped (pattern_guess only), %d failed | total cost: $%.4f",
        stats["found"], stats["kept"], stats["skipped"], stats["failed"],
        total_cost,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Backfill email discovery for unverified pattern-guessed prospects",
    )
    parser.add_argument(
        "--commit", action="store_true",
        help="Persist changes (default: dry-run)",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max prospects to process (0=all)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=5,
        help="Max parallel discovery tasks (default: 5)",
    )
    args = parser.parse_args()

    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")

    asyncio.run(backfill(limit=args.limit, commit=args.commit, concurrency=args.concurrency))


if __name__ == "__main__":
    main()
