"""
Backfill prospect research for existing prospects.

Enqueues `enrich_prospect` tasks for all prospects that have a website
but no enrichment_data yet. Batched with rate limiting to avoid
overwhelming the task queue.

Usage:
    python scripts/backfill_research.py
    python scripts/backfill_research.py --limit 100
    python scripts/backfill_research.py --dry-run
"""
import argparse
import asyncio
import logging
import sys

from sqlalchemy import select, and_, or_
from sqlalchemy.sql import func

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 50


async def backfill(limit: int = 0, dry_run: bool = False):
    """Enqueue research tasks for un-researched prospects with websites."""
    from src.database import async_session_factory
    from src.models.outreach import Outreach
    from src.services.task_dispatch import enqueue_task

    async with async_session_factory() as db:
        # Count total eligible
        count_query = select(func.count()).select_from(Outreach).where(
            and_(
                Outreach.website.isnot(None),
                Outreach.website != "",
                or_(
                    Outreach.enrichment_data.is_(None),
                    Outreach.enrichment_data == {},
                ),
            )
        )
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        effective_limit = min(total, limit) if limit > 0 else total
        logger.info(
            "Found %d prospects eligible for research (processing %d)%s",
            total, effective_limit, " [DRY RUN]" if dry_run else "",
        )

        if total == 0:
            logger.info("Nothing to backfill")
            return

        # Fetch prospects in batches
        enqueued = 0
        offset = 0

        while enqueued < effective_limit:
            batch_limit = min(BATCH_SIZE, effective_limit - enqueued)
            query = (
                select(Outreach.id, Outreach.prospect_name, Outreach.website)
                .where(
                    and_(
                        Outreach.website.isnot(None),
                        Outreach.website != "",
                        or_(
                            Outreach.enrichment_data.is_(None),
                            Outreach.enrichment_data == {},
                        ),
                    )
                )
                .order_by(Outreach.created_at)
                .offset(offset)
                .limit(batch_limit)
            )

            result = await db.execute(query)
            rows = result.all()
            if not rows:
                break

            for row in rows:
                prospect_id, name, website = row
                if dry_run:
                    logger.info(
                        "  [DRY RUN] Would enqueue: %s (%s) - %s",
                        str(prospect_id)[:8], name or "?", website or "?",
                    )
                else:
                    await enqueue_task(
                        task_type="enrich_prospect",
                        payload={"outreach_id": str(prospect_id)},
                        priority=3,  # Low priority - backfill shouldn't block real-time
                        delay_seconds=enqueued * 2,  # Stagger: 2s apart
                    )
                enqueued += 1

            offset += len(rows)
            logger.info("  Enqueued %d/%d research tasks...", enqueued, effective_limit)

    logger.info(
        "Backfill complete: %d tasks %s",
        enqueued,
        "would be enqueued [DRY RUN]" if dry_run else "enqueued",
    )


def main():
    parser = argparse.ArgumentParser(description="Backfill prospect research")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Max number of prospects to research (0 = all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be enqueued without actually enqueuing",
    )
    args = parser.parse_args()

    asyncio.run(backfill(limit=args.limit, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
