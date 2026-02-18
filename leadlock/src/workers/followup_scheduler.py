"""
Follow-up scheduler worker — processes pending followup tasks.
Runs every 60 seconds. Compliance check before every send.
"""
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.followup import FollowupTask
from src.models.lead import Lead
from src.models.client import Client
from src.models.consent import ConsentRecord
from src.models.conversation import Conversation
from src.models.event_log import EventLog
from src.services.compliance import full_compliance_check
from src.services.sms import send_sms
from src.agents.followup import process_followup
from src.schemas.client_config import ClientConfig
from src.services.plan_limits import is_cold_followup_enabled

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        from datetime import timezone
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:followup_scheduler",
            datetime.now(timezone.utc).isoformat(),
            ex=300,
        )
    except Exception:
        pass


async def run_followup_scheduler():
    """Main loop — poll for due followup tasks and execute them."""
    logger.info("Follow-up scheduler started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            await process_due_tasks()
        except Exception as e:
            logger.error("Follow-up scheduler error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def process_due_tasks():
    """Find and process all due followup tasks."""
    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)

        # Get pending tasks that are due
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
        )
        tasks = result.scalars().all()

        if not tasks:
            return

        logger.info("Processing %d due followup tasks", len(tasks))

        for task in tasks:
            try:
                await execute_followup_task(db, task)
            except Exception as e:
                logger.error(
                    "Failed to execute followup task %s: %s",
                    str(task.id)[:8], str(e),
                )
                task.attempt_count += 1
                task.last_error = str(e)
                if task.attempt_count >= task.max_attempts:
                    task.status = "failed"

        await db.commit()


async def execute_followup_task(db: AsyncSession, task: FollowupTask):
    """Execute a single followup task with full compliance check."""
    # Load lead and client
    lead = await db.get(Lead, task.lead_id)
    client = await db.get(Client, task.client_id)

    if not lead or not client:
        task.status = "skipped"
        task.skip_reason = "Lead or client not found"
        return

    # Skip if lead opted out or is dead
    if lead.state in ("opted_out", "dead"):
        task.status = "skipped"
        task.skip_reason = f"Lead state: {lead.state}"
        return

    # Enforce plan-based follow-up gating (Starter: no cold follow-ups)
    if task.task_type == "cold_nurture" and not is_cold_followup_enabled(client.tier):
        task.status = "skipped"
        task.skip_reason = f"Cold follow-ups not available on {client.tier} plan"
        logger.info(
            "Followup skipped for lead %s: tier %s does not include cold follow-ups",
            str(lead.id)[:8], client.tier,
        )
        return

    # Skip if lead responded (cold nurture no longer needed)
    if task.task_type == "cold_nurture" and lead.state not in ("cold", "intake_sent"):
        task.status = "skipped"
        task.skip_reason = "Lead re-engaged"
        return

    config = ClientConfig(**client.config) if client.config else ClientConfig()

    # Check consent
    consent = None
    if lead.consent_id:
        consent = await db.get(ConsentRecord, lead.consent_id)

    # Full compliance check
    compliance = full_compliance_check(
        has_consent=consent is not None,
        consent_type=consent.consent_type if consent else None,
        is_opted_out=consent.opted_out if consent else False,
        state_code=lead.state_code,
        is_emergency=False,
        cold_outreach_count=lead.cold_outreach_count,
        is_reply_to_inbound=False,
        message="",  # Will check content after generation
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

    # Send SMS
    sms_result = await send_sms(
        to=lead.phone,
        body=response.message,
        from_phone=client.twilio_phone,
        messaging_service_sid=client.twilio_messaging_service_sid,
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

    # Update task
    task.status = "sent"
    task.sent_at = datetime.now(timezone.utc)
    task.message_content = response.message

    # Update lead
    lead.total_messages_sent += 1
    lead.total_sms_cost_usd += sms_result.get("cost_usd", 0.0)
    lead.last_outbound_at = datetime.now(timezone.utc)
    if task.task_type == "cold_nurture":
        lead.cold_outreach_count += 1

    # Log event
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
