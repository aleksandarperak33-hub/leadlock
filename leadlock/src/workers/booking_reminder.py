"""
Booking reminder worker — sends day-before appointment reminders.
Runs every 30 minutes. Auto-schedules reminders for confirmed bookings.

Process:
1. Find confirmed bookings for tomorrow that haven't had a reminder sent
2. Generate and send reminder SMS via the followup agent
3. Mark reminder as sent to prevent duplicates
"""
import asyncio
import logging
from datetime import datetime, timezone, date, timedelta

from sqlalchemy import select, and_

from src.database import async_session_factory
from src.models.booking import Booking
from src.models.lead import Lead
from src.models.client import Client
from src.models.conversation import Conversation
from src.models.event_log import EventLog
from src.services.compliance import full_compliance_check
from src.services.sms import send_sms
from src.agents.followup import process_followup
from src.schemas.client_config import ClientConfig

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1800  # 30 minutes


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:booking_reminder",
            datetime.now(timezone.utc).isoformat(),
            ex=3600,
        )
    except Exception:
        pass


async def run_booking_reminder():
    """Main loop — check for bookings needing reminders."""
    logger.info("Booking reminder worker started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            sent = await _send_due_reminders()
            if sent > 0:
                logger.info("Sent %d booking reminders", sent)
        except Exception as e:
            logger.error("Booking reminder error: %s", str(e), exc_info=True)

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _send_due_reminders() -> int:
    """Find and send reminders for tomorrow's bookings."""
    tomorrow = date.today() + timedelta(days=1)
    sent_count = 0

    async with async_session_factory() as db:
        # Find confirmed bookings for tomorrow that haven't been reminded
        result = await db.execute(
            select(Booking)
            .where(
                and_(
                    Booking.appointment_date == tomorrow,
                    Booking.status == "confirmed",
                    Booking.reminder_sent == False,
                )
            )
            .limit(50)
        )
        bookings = result.scalars().all()

        if not bookings:
            return 0

        for booking in bookings:
            try:
                success = await _send_single_reminder(db, booking)
                if success:
                    sent_count += 1
            except Exception as e:
                logger.error(
                    "Failed to send reminder for booking %s: %s",
                    str(booking.id)[:8], str(e),
                )

        await db.commit()

    return sent_count


async def _send_single_reminder(db, booking: Booking) -> bool:
    """Send a reminder for a single booking. Returns True if sent."""
    lead = await db.get(Lead, booking.lead_id)
    client = await db.get(Client, booking.client_id)

    if not lead or not client:
        return False

    # Skip if lead opted out
    if lead.state == "opted_out":
        booking.reminder_sent = True
        booking.extra_data = {**(booking.extra_data or {}), "reminder_skipped": "opted_out"}
        return False

    config = ClientConfig(**client.config) if client.config else ClientConfig()

    # Compliance check
    compliance = full_compliance_check(
        has_consent=True,
        consent_type="pec",
        is_opted_out=False,
        state_code=lead.state_code,
        is_emergency=False,
        is_reply_to_inbound=False,
        message="",
        is_first_message=False,
        business_name=client.business_name,
    )

    if not compliance:
        logger.info(
            "Reminder blocked for booking %s: %s",
            str(booking.id)[:8], compliance.reason,
        )
        return False

    # Generate reminder message
    time_window = None
    if booking.time_window_start:
        start_str = booking.time_window_start.strftime("%I:%M %p")
        end_str = booking.time_window_end.strftime("%I:%M %p") if booking.time_window_end else ""
        time_window = f"{start_str} - {end_str}" if end_str else start_str

    response = await process_followup(
        lead_first_name=lead.first_name,
        service_type=booking.service_type,
        business_name=client.business_name,
        rep_name=config.persona.rep_name,
        followup_type="day_before_reminder",
        sequence_number=1,
        appointment_date=booking.appointment_date.strftime("%A, %B %d"),
        time_window=time_window,
        tech_name=booking.tech_name,
    )

    # Send SMS
    sms_result = await send_sms(
        to=lead.phone,
        body=response.message,
        from_phone=client.twilio_phone,
    )

    # Record conversation
    db.add(Conversation(
        lead_id=lead.id,
        client_id=client.id,
        direction="outbound",
        content=response.message,
        from_phone=client.twilio_phone or "",
        to_phone=lead.phone,
        agent_id="followup",
        sms_provider=sms_result.get("provider"),
        sms_sid=sms_result.get("sid"),
        delivery_status=sms_result.get("status", "sent"),
        segment_count=sms_result.get("segments", 1),
        sms_cost_usd=sms_result.get("cost_usd", 0.0),
    ))

    # Mark reminder as sent
    booking.reminder_sent = True
    booking.reminder_sent_at = datetime.now(timezone.utc)

    # Update lead costs
    lead.total_messages_sent += 1
    lead.total_sms_cost_usd += sms_result.get("cost_usd", 0.0)
    lead.last_outbound_at = datetime.now(timezone.utc)

    db.add(EventLog(
        lead_id=lead.id,
        client_id=client.id,
        action="booking_reminder_sent",
        message=f"Day-before reminder sent for {booking.appointment_date}",
    ))

    return True
