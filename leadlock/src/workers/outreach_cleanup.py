"""
Outreach cleanup worker — marks exhausted sequences as lost.
Runs every 4 hours. Prospects with max steps reached and no reply → status "lost".
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
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
        await redis.set("leadlock:worker_health:outreach_cleanup", datetime.now(timezone.utc).isoformat(), ex=18000)
    except Exception:
        pass


async def run_outreach_cleanup():
    """Main loop — clean up exhausted outreach sequences every 4 hours."""
    logger.info("Outreach cleanup worker started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            # Check if cleanup is paused
            async with async_session_factory() as db:
                from sqlalchemy import select as sel
                result = await db.execute(sel(SalesEngineConfig).limit(1))
                config = result.scalar_one_or_none()
                if config and hasattr(config, "cleanup_paused") and config.cleanup_paused:
                    logger.debug("Outreach cleanup is paused, skipping cycle")
                else:
                    await cleanup_cycle()
        except Exception as e:
            logger.error("Outreach cleanup error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def cleanup_cycle():
    """
    Mark exhausted outreach sequences as lost.

    Two passes:
    1. Campaign-bound prospects — use each campaign's sequence_steps length.
    2. Unbound prospects — use global config.max_sequence_steps.
    """
    async with async_session_factory() as db:
        # Load config
        result = await db.execute(select(SalesEngineConfig).limit(1))
        config = result.scalar_one_or_none()

        if not config or not config.is_active:
            return

        delay_cutoff = datetime.now(timezone.utc) - timedelta(hours=config.sequence_delay_hours)
        total_marked = 0

        # === PASS 1: Campaign-bound prospects ===
        # Each campaign defines its own step count via sequence_steps JSON array.
        from src.models.campaign import Campaign

        campaigns_result = await db.execute(
            select(Campaign).where(
                Campaign.status.in_(["active", "paused", "completed"])
            )
        )
        all_campaigns = campaigns_result.scalars().all()

        for campaign in all_campaigns:
            steps = campaign.sequence_steps or []
            campaign_max_steps = len(steps)
            if campaign_max_steps == 0:
                continue

            stmt = (
                update(Outreach)
                .where(
                    and_(
                        Outreach.campaign_id == campaign.id,
                        Outreach.outreach_sequence_step >= campaign_max_steps,
                        Outreach.status.in_(["cold", "contacted"]),
                        Outreach.last_email_replied_at.is_(None),
                        Outreach.last_email_sent_at.isnot(None),
                        Outreach.last_email_sent_at <= delay_cutoff,
                    )
                )
                .values(status="lost", updated_at=datetime.now(timezone.utc))
            )
            result = await db.execute(stmt)
            campaign_marked = result.rowcount
            if campaign_marked > 0:
                logger.info(
                    "Campaign %s: marked %d exhausted sequences as lost (max_steps=%d)",
                    str(campaign.id)[:8], campaign_marked, campaign_max_steps,
                )
                total_marked += campaign_marked

        # === PASS 2: Unbound prospects (no campaign) ===
        # Use global config.max_sequence_steps
        stmt = (
            update(Outreach)
            .where(
                and_(
                    Outreach.campaign_id.is_(None),
                    Outreach.outreach_sequence_step >= config.max_sequence_steps,
                    Outreach.status.in_(["cold", "contacted"]),
                    Outreach.last_email_replied_at.is_(None),
                    Outreach.last_email_sent_at.isnot(None),
                    Outreach.last_email_sent_at <= delay_cutoff,
                )
            )
            .values(status="lost", updated_at=datetime.now(timezone.utc))
        )

        result = await db.execute(stmt)
        unbound_marked = result.rowcount
        total_marked += unbound_marked

        if unbound_marked > 0:
            logger.info(
                "Unbound prospects: marked %d exhausted sequences as lost (max_steps=%d)",
                unbound_marked, config.max_sequence_steps,
            )

        if total_marked > 0:
            logger.info("Total marked %d exhausted outreach sequences as lost", total_marked)

        await db.commit()
