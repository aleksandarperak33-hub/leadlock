"""
Lead state manager — merged from stuck_lead_sweeper + lead_lifecycle.
Runs every 5 minutes. Single loop eliminates race conditions between
stuck-sweep and lifecycle transitions.

Phases per cycle:
1. Sweep stuck leads (from stuck_lead_sweeper)
2. Complete booked leads past appointment date
3. Archive old leads (from lead_lifecycle)
4. Mark dead leads (from lead_lifecycle)
5. Schedule cold recycling (from lead_lifecycle)
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, update

from src.database import async_session_factory
from src.models.lead import Lead
from src.models.booking import Booking
from src.models.client import Client
from src.models.followup import FollowupTask
from src.models.event_log import EventLog
from src.services.plan_limits import is_cold_followup_enabled

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 300  # 5 minutes

# Stuck lead thresholds
STATE_TIMEOUTS = {
    "intake_sent": timedelta(minutes=30),
    "qualifying": timedelta(hours=1),
    "qualified": timedelta(hours=1),
    "booking": timedelta(hours=2),
}

# Lifecycle configuration
ARCHIVE_AFTER_DAYS = 90
COLD_TO_DEAD_DAYS = 30
COLD_RECYCLE_DAYS = 7
MAX_COLD_OUTREACH = 3
COMPLETE_AFTER_DAYS = 1  # Mark booked→completed 1 day after appointment
REVIEW_REQUEST_DELAY_HOURS = 24  # Send review request 24h after completion


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:lead_state_manager",
            datetime.now(timezone.utc).isoformat(),
            ex=600,
        )
    except Exception as e:
        logger.debug("Heartbeat write failed: %s", str(e))


async def run_lead_state_manager():
    """Main loop — sweep stuck leads, then run lifecycle transitions."""
    logger.info("Lead state manager started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            # Phase 1: Sweep stuck leads
            stuck = await _sweep_stuck_leads()

            # Phase 2: Complete booked leads past appointment date
            completed = await _complete_booked_leads()

            # Phase 3-5: Lifecycle transitions
            archived = await _archive_old_leads()
            dead = await _mark_dead_leads()
            recycled = await _schedule_cold_recycling()

            total = stuck + completed + archived + dead + recycled
            if total > 0:
                logger.info(
                    "Lead state manager: stuck=%d completed=%d archived=%d dead=%d recycled=%d",
                    stuck, completed, archived, dead, recycled,
                )
        except Exception as e:
            logger.error("Lead state manager error: %s", str(e), exc_info=True)

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Phase 1: Sweep stuck leads (from stuck_lead_sweeper)
# ---------------------------------------------------------------------------

async def _sweep_stuck_leads() -> int:
    """Find and process stuck leads. Returns count found."""
    now = datetime.now(timezone.utc)
    total_found = 0

    async with async_session_factory() as db:
        for state, timeout in STATE_TIMEOUTS.items():
            cutoff = now - timeout
            result = await db.execute(
                select(Lead).where(
                    and_(
                        Lead.state == state,
                        Lead.updated_at < cutoff,
                    )
                ).limit(50)
            )
            stuck_leads = result.scalars().all()

            for lead in stuck_leads:
                total_found += 1
                _handle_stuck_lead(db, lead, state, now)

        if total_found > 0:
            await db.commit()

    return total_found


def _handle_stuck_lead(db, lead, state: str, now: datetime) -> None:
    """Take action on a single stuck lead based on its state."""
    lead_id_short = str(lead.id)[:8]
    age_minutes = int((now - lead.updated_at).total_seconds() / 60)

    logger.warning(
        "Stuck lead found: %s in state '%s' for %d minutes",
        lead_id_short, state, age_minutes,
    )

    if state == "intake_sent":
        lead.state = "qualifying"
        lead.current_agent = "qualify"
        db.add(EventLog(
            lead_id=lead.id,
            client_id=lead.client_id,
            action="stuck_lead_advanced",
            message=f"Auto-advanced from intake_sent after {age_minutes}min with no reply",
        ))

    elif state in ("qualifying", "qualified"):
        lead.state = "cold"
        lead.current_agent = "followup"
        db.add(EventLog(
            lead_id=lead.id,
            client_id=lead.client_id,
            action="stuck_lead_cold",
            message=f"Marked cold after {age_minutes}min in {state} with no activity",
        ))

    elif state == "booking":
        db.add(EventLog(
            lead_id=lead.id,
            client_id=lead.client_id,
            action="stuck_lead_alert",
            message=f"ALERT: Lead stuck in booking for {age_minutes}min - needs admin attention",
            data={"alert_type": "stuck_booking", "age_minutes": age_minutes},
        ))


# ---------------------------------------------------------------------------
# Phase 2: Complete booked leads past appointment date
# ---------------------------------------------------------------------------

async def _complete_booked_leads() -> int:
    """Transition booked leads to completed after appointment date has passed.

    Also schedules a review_request follow-up task for the next day.
    """
    today = datetime.now(timezone.utc).date()
    cutoff_date = today - timedelta(days=COMPLETE_AFTER_DAYS)
    now = datetime.now(timezone.utc)
    count = 0

    async with async_session_factory() as db:
        # Find booked leads with appointments that have passed
        result = await db.execute(
            select(Lead, Booking).join(
                Booking, Booking.lead_id == Lead.id
            ).where(
                and_(
                    Lead.state == "booked",
                    Lead.archived == False,  # noqa: E712
                    Booking.status == "confirmed",
                    Booking.appointment_date <= cutoff_date,
                )
            ).limit(50)
        )
        rows = result.all()

        for lead, booking in rows:
            lead.previous_state = lead.state
            lead.state = "completed"
            lead.current_agent = None
            booking.status = "completed"
            count += 1

            # Cancel any pending follow-up tasks (cold_nurture, etc.)
            await db.execute(
                update(FollowupTask)
                .where(
                    FollowupTask.lead_id == lead.id,
                    FollowupTask.status == "pending",
                    FollowupTask.task_type != "review_request",
                )
                .values(status="cancelled", skip_reason="Lead completed")
            )

            db.add(EventLog(
                lead_id=lead.id,
                client_id=lead.client_id,
                action="lead_completed",
                message=(
                    f"Auto-completed: appointment was {booking.appointment_date.isoformat()}, "
                    f"service={booking.service_type}"
                ),
            ))

            # Schedule review request (only if no existing pending review task)
            existing_review = await db.execute(
                select(FollowupTask).where(
                    and_(
                        FollowupTask.lead_id == lead.id,
                        FollowupTask.task_type == "review_request",
                        FollowupTask.status == "pending",
                    )
                ).limit(1)
            )
            if not existing_review.scalar_one_or_none():
                review_at = now + timedelta(hours=REVIEW_REQUEST_DELAY_HOURS)
                db.add(FollowupTask(
                    lead_id=lead.id,
                    client_id=lead.client_id,
                    task_type="review_request",
                    scheduled_at=review_at,
                    sequence_number=1,
                ))
                lead.next_followup_at = review_at

                db.add(EventLog(
                    lead_id=lead.id,
                    client_id=lead.client_id,
                    action="review_request_scheduled",
                    message=f"Review request scheduled for {review_at.isoformat()}",
                ))

            logger.info(
                "Lead %s completed (appointment %s, service=%s)",
                str(lead.id)[:8], booking.appointment_date, booking.service_type,
            )

        if count > 0:
            await db.commit()
            logger.info("Completed %d booked leads past appointment date", count)

    return count


# ---------------------------------------------------------------------------
# Phase 3: Archive old leads (from lead_lifecycle)
# ---------------------------------------------------------------------------

async def _archive_old_leads() -> int:
    """Archive leads in terminal states older than ARCHIVE_AFTER_DAYS."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_AFTER_DAYS)

    async with async_session_factory() as db:
        result = await db.execute(
            update(Lead)
            .where(
                and_(
                    Lead.state.in_(["completed", "dead", "opted_out"]),
                    Lead.archived == False,  # noqa: E712
                    Lead.updated_at < cutoff,
                )
            )
            .values(archived=True)
        )
        count = result.rowcount
        if count > 0:
            await db.commit()
        return count


# ---------------------------------------------------------------------------
# Phase 4: Mark dead leads (from lead_lifecycle)
# ---------------------------------------------------------------------------

async def _mark_dead_leads() -> int:
    """Mark cold leads as dead after COLD_TO_DEAD_DAYS or max outreach exhausted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=COLD_TO_DEAD_DAYS)
    count = 0

    async with async_session_factory() as db:
        result = await db.execute(
            select(Lead).where(
                and_(
                    Lead.state == "cold",
                    Lead.archived == False,  # noqa: E712
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


# ---------------------------------------------------------------------------
# Phase 5: Schedule cold recycling (from lead_lifecycle)
# ---------------------------------------------------------------------------

async def _schedule_cold_recycling() -> int:
    """Schedule re-engagement for cold leads after COLD_RECYCLE_DAYS."""
    now = datetime.now(timezone.utc)
    recycle_cutoff = now - timedelta(days=COLD_RECYCLE_DAYS)
    recycle_window = recycle_cutoff - timedelta(hours=1)
    count = 0

    async with async_session_factory() as db:
        result = await db.execute(
            select(Lead).where(
                and_(
                    Lead.state == "cold",
                    Lead.archived == False,  # noqa: E712
                    Lead.cold_outreach_count < MAX_COLD_OUTREACH,
                    Lead.updated_at >= recycle_window,
                    Lead.updated_at < recycle_cutoff,
                )
            ).limit(50)
        )
        leads = result.scalars().all()

        for lead in leads:
            client = await db.get(Client, lead.client_id)
            if not client or not is_cold_followup_enabled(client.tier):
                continue

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
                continue

            next_sequence = lead.cold_outreach_count + 1
            scheduled_at = now + timedelta(hours=1)

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
