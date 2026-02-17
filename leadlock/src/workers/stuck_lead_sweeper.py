"""
Stuck lead sweeper — finds and acts on leads stuck in non-terminal states.
Runs every 5 minutes. Prevents leads from being silently lost.

Actions by state:
- intake_sent for >30min → retry qualify
- qualifying for >1hr → send follow-up or mark cold
- booking for >2hr → alert admin
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 300  # 5 minutes

# Timeout thresholds per state
STATE_TIMEOUTS = {
    "intake_sent": timedelta(minutes=30),
    "qualifying": timedelta(hours=1),
    "qualified": timedelta(hours=1),
    "booking": timedelta(hours=2),
}


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:stuck_lead_sweeper",
            datetime.now(timezone.utc).isoformat(),
            ex=600,
        )
    except Exception:
        pass


async def run_stuck_lead_sweeper():
    """Main sweeper loop. Runs continuously every 5 minutes."""
    logger.info("Stuck lead sweeper started")

    while True:
        try:
            found = await _sweep_stuck_leads()
            if found > 0:
                logger.info("Stuck lead sweeper found %d stuck leads", found)
        except Exception as e:
            logger.error("Stuck lead sweeper error: %s", str(e), exc_info=True)

        await _heartbeat()
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)


async def _sweep_stuck_leads() -> int:
    """Find and process stuck leads. Returns count found."""
    from src.database import async_session_factory
    from src.models.lead import Lead

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
                await _handle_stuck_lead(db, lead, state, now)

        if total_found > 0:
            await db.commit()

    return total_found


async def _handle_stuck_lead(db, lead, state: str, now: datetime) -> None:
    """Take action on a single stuck lead based on its state."""
    from src.models.event_log import EventLog

    lead_id_short = str(lead.id)[:8]
    age_minutes = int((now - lead.updated_at).total_seconds() / 60)

    logger.warning(
        "Stuck lead found: %s in state '%s' for %d minutes",
        lead_id_short, state, age_minutes,
    )

    if state == "intake_sent":
        # No reply received within 30min — transition to qualifying anyway
        # The next inbound message will be routed to qualify agent
        lead.state = "qualifying"
        lead.current_agent = "qualify"
        db.add(EventLog(
            lead_id=lead.id,
            client_id=lead.client_id,
            action="stuck_lead_advanced",
            message=f"Auto-advanced from intake_sent after {age_minutes}min with no reply",
        ))

    elif state in ("qualifying", "qualified"):
        # No activity for >1hr — mark as cold
        lead.state = "cold"
        lead.current_agent = "followup"
        db.add(EventLog(
            lead_id=lead.id,
            client_id=lead.client_id,
            action="stuck_lead_cold",
            message=f"Marked cold after {age_minutes}min in {state} with no activity",
        ))

    elif state == "booking":
        # Booking stuck for >2hr — log alert for admin
        db.add(EventLog(
            lead_id=lead.id,
            client_id=lead.client_id,
            action="stuck_lead_alert",
            message=f"ALERT: Lead stuck in booking for {age_minutes}min — needs admin attention",
            data={"alert_type": "stuck_booking", "age_minutes": age_minutes},
        ))
