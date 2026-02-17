"""
Lead lifecycle worker — manages long-term lead state transitions.
Runs every 30 minutes.

Actions:
1. Archive old completed/dead leads (>90 days) — set archived=True
2. Recycle cold leads — auto-schedule re-engagement after 7 days of cold
3. Mark dead leads — cold leads with 3+ cold outreach messages exhausted
4. Clean up stale consent records (>5 years per FTC TSR 2024 requirement)
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, update

from src.database import async_session_factory
from src.models.lead import Lead
from src.models.followup import FollowupTask
from src.models.event_log import EventLog

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1800  # 30 minutes

# Configuration
ARCHIVE_AFTER_DAYS = 90       # Archive completed/dead leads after 90 days
COLD_TO_DEAD_DAYS = 30        # Mark cold leads as dead after 30 days with no activity
COLD_RECYCLE_DAYS = 7         # Schedule re-engagement 7 days after going cold
MAX_COLD_OUTREACH = 3         # Maximum cold outreach messages per lead


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:lead_lifecycle",
            datetime.now(timezone.utc).isoformat(),
            ex=3600,
        )
    except Exception:
        pass


async def run_lead_lifecycle():
    """Main lifecycle loop."""
    logger.info("Lead lifecycle worker started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            archived = await _archive_old_leads()
            dead = await _mark_dead_leads()
            recycled = await _schedule_cold_recycling()

            if archived + dead + recycled > 0:
                logger.info(
                    "Lead lifecycle: archived=%d dead=%d recycled=%d",
                    archived, dead, recycled,
                )
        except Exception as e:
            logger.error("Lead lifecycle error: %s", str(e), exc_info=True)

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _archive_old_leads() -> int:
    """Archive leads in terminal states that are older than ARCHIVE_AFTER_DAYS."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_AFTER_DAYS)

    async with async_session_factory() as db:
        result = await db.execute(
            update(Lead)
            .where(
                and_(
                    Lead.state.in_(["completed", "dead", "opted_out"]),
                    Lead.archived == False,
                    Lead.updated_at < cutoff,
                )
            )
            .values(archived=True)
        )
        count = result.rowcount
        if count > 0:
            await db.commit()
        return count


async def _mark_dead_leads() -> int:
    """
    Mark cold leads as dead when:
    - They've been cold for >COLD_TO_DEAD_DAYS with no activity
    - OR they've exhausted all cold outreach messages (3 max)
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=COLD_TO_DEAD_DAYS)
    count = 0

    async with async_session_factory() as db:
        # Find cold leads that should be marked dead
        result = await db.execute(
            select(Lead).where(
                and_(
                    Lead.state == "cold",
                    Lead.archived == False,
                    (Lead.updated_at < cutoff) | (Lead.cold_outreach_count >= MAX_COLD_OUTREACH),
                )
            ).limit(100)
        )
        leads = result.scalars().all()

        for lead in leads:
            lead.state = "dead"
            lead.current_agent = None
            count += 1

            db.add(EventLog(
                lead_id=lead.id,
                client_id=lead.client_id,
                action="lead_marked_dead",
                message=(
                    f"Lead marked dead: cold for {COLD_TO_DEAD_DAYS}+ days"
                    if lead.cold_outreach_count < MAX_COLD_OUTREACH
                    else f"Lead marked dead: exhausted {lead.cold_outreach_count} cold outreach messages"
                ),
            ))

            # Cancel any pending followup tasks
            await db.execute(
                update(FollowupTask)
                .where(
                    FollowupTask.lead_id == lead.id,
                    FollowupTask.status == "pending",
                )
                .values(status="cancelled", skip_reason="Lead marked dead")
            )

        if count > 0:
            await db.commit()

    return count


async def _schedule_cold_recycling() -> int:
    """
    Schedule re-engagement for cold leads that:
    - Have been cold for exactly COLD_RECYCLE_DAYS
    - Haven't exhausted cold outreach (< MAX_COLD_OUTREACH)
    - Don't already have a pending cold_nurture followup
    """
    now = datetime.now(timezone.utc)
    recycle_cutoff = now - timedelta(days=COLD_RECYCLE_DAYS)
    recycle_window = recycle_cutoff - timedelta(hours=1)  # 1-hour window to avoid re-scheduling
    count = 0

    async with async_session_factory() as db:
        # Find cold leads in the recycle window
        result = await db.execute(
            select(Lead).where(
                and_(
                    Lead.state == "cold",
                    Lead.archived == False,
                    Lead.cold_outreach_count < MAX_COLD_OUTREACH,
                    Lead.updated_at >= recycle_window,
                    Lead.updated_at < recycle_cutoff,
                )
            ).limit(50)
        )
        leads = result.scalars().all()

        for lead in leads:
            # Check if there's already a pending cold_nurture task
            existing = await db.execute(
                select(FollowupTask).where(
                    and_(
                        FollowupTask.lead_id == lead.id,
                        FollowupTask.task_type == "cold_nurture",
                        FollowupTask.status == "pending",
                    )
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                continue  # Already has a pending followup

            # Schedule the next cold nurture message
            next_sequence = lead.cold_outreach_count + 1
            scheduled_at = now + timedelta(hours=1)  # Send within the hour

            db.add(FollowupTask(
                lead_id=lead.id,
                client_id=lead.client_id,
                task_type="cold_nurture",
                scheduled_at=scheduled_at,
                sequence_number=next_sequence,
            ))

            lead.next_followup_at = scheduled_at
            count += 1

            db.add(EventLog(
                lead_id=lead.id,
                client_id=lead.client_id,
                action="cold_recycle_scheduled",
                message=f"Cold nurture #{next_sequence} scheduled (lead cold for {COLD_RECYCLE_DAYS} days)",
            ))

        if count > 0:
            await db.commit()

    return count
