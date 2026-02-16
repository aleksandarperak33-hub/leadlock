"""
Outreach cleanup worker — marks exhausted sequences as lost.
Runs every 4 hours. Prospects with max steps reached and no reply → status "lost".
"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.sales_config import SalesEngineConfig

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 4 * 60 * 60  # 4 hours


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set("leadlock:worker_health:outreach_cleanup", datetime.utcnow().isoformat(), ex=18000)
    except Exception:
        pass


async def run_outreach_cleanup():
    """Main loop — clean up exhausted outreach sequences every 4 hours."""
    logger.info("Outreach cleanup worker started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            await cleanup_cycle()
        except Exception as e:
            logger.error("Outreach cleanup error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def cleanup_cycle():
    """Mark exhausted outreach sequences as lost."""
    async with async_session_factory() as db:
        # Load config
        result = await db.execute(select(SalesEngineConfig).limit(1))
        config = result.scalar_one_or_none()

        if not config or not config.is_active:
            return

        delay_cutoff = datetime.utcnow() - timedelta(hours=config.sequence_delay_hours)

        # Find prospects that have completed all steps with no reply
        # IMPORTANT: must check last_email_sent_at IS NOT NULL to avoid marking
        # never-contacted prospects as "lost"
        stmt = (
            update(Outreach)
            .where(
                and_(
                    Outreach.outreach_sequence_step >= config.max_sequence_steps,
                    Outreach.status.in_(["cold", "contacted"]),
                    Outreach.last_email_replied_at.is_(None),
                    Outreach.last_email_sent_at.isnot(None),
                    Outreach.last_email_sent_at <= delay_cutoff,
                )
            )
            .values(status="lost", updated_at=datetime.utcnow())
        )

        result = await db.execute(stmt)
        count = result.rowcount

        if count > 0:
            logger.info("Marked %d exhausted outreach sequences as lost", count)

        await db.commit()
