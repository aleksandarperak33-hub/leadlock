"""
SMS dispatch worker — merged from followup_scheduler + booking_reminder.
Runs every 60 seconds. Shared compliance pipeline for both followup and reminder sends.

Phase 1: Process due followup tasks (from followup_scheduler)
Phase 2: Send booking reminders (from booking_reminder)
"""
import asyncio
import logging
import re
from datetime import datetime, timezone, date, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.followup import FollowupTask
from src.models.lead import Lead
from src.models.client import Client
from src.models.booking import Booking
from src.models.consent import ConsentRecord
from src.models.conversation import Conversation
from src.models.event_log import EventLog
from src.services.compliance import full_compliance_check, check_content_compliance
from src.services.sms import send_sms
from src.agents.followup import process_followup
from src.schemas.client_config import ClientConfig
from src.services.plan_limits import is_cold_followup_enabled

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60

_PHONE_RE = re.compile(r'\+?\d[\d\-.\s]{7,}\d')


def _sanitize_error(msg: str) -> str:
    """Mask phone numbers in error messages to comply with PII logging standard."""
    return _PHONE_RE.sub(lambda m: m.group()[:6] + '***', msg)


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:sms_dispatch",
            datetime.now(timezone.utc).isoformat(),
            ex=300,
        )
    except Exception:
        pass


async def run_sms_dispatch():
    """Main loop — process followup tasks, then booking reminders."""
    logger.info("SMS dispatch worker started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            # Phase 1: Due followup tasks
            await _process_due_followups()

            # Phase 2: Booking reminders (cheap check — returns immediately when nothing due)
            await _send_due_reminders()
        except Exception as e:
            logger.error("SMS dispatch error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Shared compliance helper
# ---------------------------------------------------------------------------

async def _send_compliant_sms(
    db: AsyncSession,
    lead: Lead,
    client: Client,
    message: str,
    agent_id: str = "followup",
) -> dict | None:
    """
    Run compliance checks and send SMS. Returns SMS result dict on success, None if blocked.
    Shared by both followup tasks and booking reminders to eliminate duplication.
    """
    # Content compliance check
    content_check = check_content_compliance(
        message=message,
        is_first_message=False,
        business_name=client.business_name,
    )
    if not content_check:
        logger.warning(
            "SMS content blocked for lead %s: %s",
            str(lead.id)[:8], content_check.reason,
        )
        return None

    # Send SMS
    sms_result = await send_sms(
        to=lead.phone,
        body=message,
        from_phone=client.twilio_phone,
        messaging_service_sid=client.twilio_messaging_service_sid,
    )

    # Record conversation
    db.add(Conversation(
        lead_id=lead.id,
        client_id=client.id,
        direction="outbound",
        content=message,
        from_phone=client.twilio_phone or "",
        to_phone=lead.phone,
        agent_id=agent_id,
        sms_provider=sms_result.get("provider"),
        sms_sid=sms_result.get("sid"),
        delivery_status=sms_result.get("status", "sent"),
        segment_count=sms_result.get("segments", 1),
        sms_cost_usd=sms_result.get("cost_usd", 0.0),
    ))

    # Update lead cost tracking
    lead.total_messages_sent += 1
    lead.total_sms_cost_usd += sms_result.get("cost_usd", 0.0)
    lead.last_outbound_at = datetime.now(timezone.utc)

    return sms_result


# ---------------------------------------------------------------------------
# Phase 1: Followup tasks (from followup_scheduler)
# ---------------------------------------------------------------------------

async def _process_due_followups():
    """Find and process all due followup tasks."""
    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(FollowupTask)
            .where(
                and_(
                    FollowupTask.status == "pending",
                    FollowupTask.scheduled_at <= now,
                )
            )
            .order_by(FollowupTask.scheduled_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        )
        tasks = result.scalars().all()

        if not tasks:
            return

        logger.info("Processing %d due followup tasks", len(tasks))

        for task in tasks:
            try:
                await _execute_followup_task(db, task)
            except Exception as e:
                logger.error(
                    "Failed to execute followup task %s: %s",
                    str(task.id)[:8], str(e),
                )
                task.attempt_count += 1
                task.last_error = _sanitize_error(str(e))
                if task.attempt_count >= task.max_attempts:
                    task.status = "failed"

        await db.commit()


async def _execute_followup_task(db: AsyncSession, task: FollowupTask):
    """Execute a single followup task with full compliance check."""
    lead = await db.get(Lead, task.lead_id)
    client = await db.get(Client, task.client_id)

    if not lead or not client:
        task.status = "skipped"
        task.skip_reason = "Lead or client not found"
        return

    if lead.state in ("opted_out", "dead"):
        task.status = "skipped"
        task.skip_reason = f"Lead state: {lead.state}"
        return

    # Global kill-switch: skip cold outreach when sales engine is disabled
    if task.task_type == "cold_nurture":
        from src.services.config_cache import get_sales_config
        config_data = await get_sales_config()
        if config_data and not config_data.get("is_active", True):
            task.status = "skipped"
            task.skip_reason = "Sales engine disabled"
            return

    if task.task_type == "cold_nurture" and not is_cold_followup_enabled(client.tier):
        task.status = "skipped"
        task.skip_reason = f"Cold follow-ups not available on {client.tier} plan"
        logger.info(
            "Followup skipped for lead %s: tier %s does not include cold follow-ups",
            str(lead.id)[:8], client.tier,
        )
        return

    if task.task_type == "cold_nurture" and lead.state not in ("cold", "intake_sent"):
        task.status = "skipped"
        task.skip_reason = "Lead re-engaged"
        return

    config = ClientConfig(**client.config) if client.config else ClientConfig()

    # Check consent
    consent = None
    if lead.consent_id:
        consent = await db.get(ConsentRecord, lead.consent_id)

    compliance = full_compliance_check(
        has_consent=consent is not None,
        consent_type=consent.consent_type if consent else None,
        is_opted_out=consent.opted_out if consent else False,
        state_code=lead.state_code,
        is_emergency=False,
        cold_outreach_count=lead.cold_outreach_count,
        is_reply_to_inbound=False,
        message="",
        is_first_message=False,
        business_name=client.business_name,
    )

    if not compliance:
        task.status = "skipped"
        task.skip_reason = compliance.reason
        logger.info("Followup skipped for lead %s: %s", str(lead.id)[:8], compliance.reason)
        return

    # Generate followup message
    response = await process_followup(
        lead_first_name=lead.first_name,
        service_type=lead.service_type,
        business_name=client.business_name,
        rep_name=config.persona.rep_name,
        followup_type=task.task_type,
        sequence_number=task.sequence_number,
    )

    # Send via shared compliance helper
    sms_result = await _send_compliant_sms(db, lead, client, response.message)
    if sms_result is None:
        task.status = "skipped"
        task.skip_reason = "Content compliance failed"
        return

    # Update task
    task.status = "sent"
    task.sent_at = datetime.now(timezone.utc)
    task.message_content = response.message

    if task.task_type == "cold_nurture":
        lead.cold_outreach_count += 1

    db.add(EventLog(
        lead_id=lead.id,
        client_id=client.id,
        action=f"followup_{task.task_type}_sent",
        message=f"Followup #{task.sequence_number} sent",
        data={"task_type": task.task_type, "sequence": task.sequence_number},
    ))

    logger.info(
        "Followup sent: lead=%s type=%s seq=%d",
        str(lead.id)[:8], task.task_type, task.sequence_number,
    )


# ---------------------------------------------------------------------------
# Phase 2: Booking reminders (from booking_reminder)
# ---------------------------------------------------------------------------

async def _send_due_reminders():
    """Find and send reminders for tomorrow's bookings."""
    tomorrow = date.today() + timedelta(days=1)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Booking)
            .where(
                and_(
                    Booking.appointment_date == tomorrow,
                    Booking.status == "confirmed",
                    Booking.reminder_sent == False,  # noqa: E712
                )
            )
            .limit(50)
            .with_for_update(skip_locked=True)
        )
        bookings = result.scalars().all()

        if not bookings:
            return 0

        sent_count = 0
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

        if sent_count > 0:
            logger.info("Sent %d booking reminders", sent_count)

        await db.commit()

    return sent_count


async def _send_single_reminder(db: AsyncSession, booking: Booking) -> bool:
    """Send a reminder for a single booking. Returns True if sent."""
    lead = await db.get(Lead, booking.lead_id)
    client = await db.get(Client, booking.client_id)

    if not lead or not client:
        return False

    if lead.state == "opted_out":
        booking.reminder_sent = True
        booking.extra_data = {**(booking.extra_data or {}), "reminder_skipped": "opted_out"}
        return False

    config = ClientConfig(**client.config) if client.config else ClientConfig()

    consent = None
    if lead.consent_id:
        consent = await db.get(ConsentRecord, lead.consent_id)

    compliance = full_compliance_check(
        has_consent=consent is not None,
        consent_type=consent.consent_type if consent else "pec",
        is_opted_out=consent.opted_out if consent else False,
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

    # Send via shared compliance helper
    sms_result = await _send_compliant_sms(db, lead, client, response.message)
    if sms_result is None:
        return False

    # Mark reminder as sent
    booking.reminder_sent = True
    booking.reminder_sent_at = datetime.now(timezone.utc)

    db.add(EventLog(
        lead_id=lead.id,
        client_id=client.id,
        action="booking_reminder_sent",
        message=f"Day-before reminder sent for {booking.appointment_date}",
    ))

    return True
