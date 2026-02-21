"""
Task processor worker - polls the task_queue table and dispatches tasks.
Handles retries with exponential backoff. Runs every 10 seconds.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.task_queue import TaskQueue

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 10
MAX_TASKS_PER_CYCLE = 10


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set("leadlock:worker_health:task_processor", datetime.now(timezone.utc).isoformat(), ex=120)
    except Exception:
        pass


async def run_task_processor():
    """Main loop - process pending tasks every 10 seconds."""
    logger.info("Task processor started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            await process_cycle()
        except Exception as e:
            logger.error("Task processor cycle error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def process_cycle():
    """Find and execute pending tasks that are due."""
    now = datetime.now(timezone.utc)

    async with async_session_factory() as db:
        # Fetch pending tasks that are due, ordered by priority (high first)
        result = await db.execute(
            select(TaskQueue)
            .where(
                and_(
                    TaskQueue.status == "pending",
                    TaskQueue.scheduled_at <= now,
                )
            )
            .order_by(TaskQueue.priority.desc(), TaskQueue.created_at)
            .limit(MAX_TASKS_PER_CYCLE)
        )
        tasks = result.scalars().all()

        if not tasks:
            return

        logger.info("Processing %d pending tasks", len(tasks))

        for task in tasks:
            await _execute_task(db, task)

        await db.commit()


async def _execute_task(db: AsyncSession, task: TaskQueue) -> None:
    """Execute a single task and handle success/failure."""
    task.status = "processing"
    task.started_at = datetime.now(timezone.utc)
    await db.flush()

    try:
        result = await _dispatch_task(task.task_type, task.payload or {})
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.result_data = result
        logger.info("Task completed: id=%s type=%s", str(task.id)[:8], task.task_type)

    except Exception as e:
        task.retry_count = task.retry_count + 1
        error_msg = str(e)

        if task.retry_count >= task.max_retries:
            task.status = "failed"
            task.error_message = error_msg
            task.completed_at = datetime.now(timezone.utc)
            logger.error(
                "Task failed (max retries): id=%s type=%s error=%s",
                str(task.id)[:8], task.task_type, error_msg,
            )
        else:
            # Exponential backoff: 30s, 120s, 480s
            backoff = 30 * (4 ** (task.retry_count - 1))
            task.status = "pending"
            task.scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
            task.error_message = error_msg
            logger.warning(
                "Task retry %d/%d: id=%s type=%s backoff=%ds",
                task.retry_count, task.max_retries,
                str(task.id)[:8], task.task_type, backoff,
            )


async def _dispatch_task(task_type: str, payload: dict) -> dict:
    """
    Route task to its handler function.
    Each handler receives the payload dict and returns a result dict.
    """
    handlers = {
        "enrich_email": _handle_enrich_email,
        "record_signal": _handle_record_signal,
        "classify_reply": _handle_classify_reply,
        "send_sms_followup": _handle_send_sms_followup,
        "send_sequence_email": _handle_send_sequence_email,
    }

    handler = handlers.get(task_type)
    if not handler:
        logger.warning("Unknown task type: %s", task_type)
        return {"status": "skipped", "reason": f"unknown task type: {task_type}"}

    return await handler(payload)


async def _handle_enrich_email(payload: dict) -> dict:
    """Enrich a prospect's email via website scraping."""
    from src.services.enrichment import enrich_prospect_email

    website = payload.get("website", "")
    company_name = payload.get("company_name", "")

    result = await enrich_prospect_email(website, company_name)
    return result


async def _handle_record_signal(payload: dict) -> dict:
    """Record a learning signal."""
    from src.services.learning import record_signal

    await record_signal(
        signal_type=payload.get("signal_type", ""),
        dimensions=payload.get("dimensions", {}),
        value=payload.get("value", 0.0),
        outreach_id=payload.get("outreach_id"),
    )
    return {"status": "recorded"}


async def _handle_classify_reply(payload: dict) -> dict:
    """Classify an inbound email reply."""
    from src.agents.sales_outreach import classify_reply

    result = await classify_reply(payload.get("text", ""))
    return result


async def _handle_send_sms_followup(payload: dict) -> dict:
    """Send a deferred SMS follow-up to a warm prospect."""
    import uuid
    from src.models.outreach import Outreach
    from src.models.sales_config import SalesEngineConfig
    from src.services.outreach_sms import (
        is_within_sms_quiet_hours,
        send_outreach_sms,
        generate_followup_sms_body,
    )

    outreach_id = payload.get("outreach_id")
    if not outreach_id:
        return {"status": "skipped", "reason": "no outreach_id"}

    async with async_session_factory() as db:
        prospect = await db.get(Outreach, uuid.UUID(outreach_id))
        if not prospect:
            return {"status": "skipped", "reason": "prospect not found"}

        if not prospect.prospect_phone:
            return {"status": "skipped", "reason": "no phone"}

        if prospect.email_unsubscribed:
            return {"status": "skipped", "reason": "unsubscribed"}

        # Still in quiet hours? Re-queue for later
        if not is_within_sms_quiet_hours(prospect.state_code):
            from src.services.task_dispatch import enqueue_task

            await enqueue_task(
                task_type="send_sms_followup",
                payload={"outreach_id": outreach_id},
                priority=7,
                delay_seconds=3600,
            )
            return {"status": "re-queued", "reason": "still quiet hours"}

        result = await db.execute(
            select(SalesEngineConfig).limit(1)
        )
        config = result.scalar_one_or_none()
        if not config:
            return {"status": "skipped", "reason": "no config"}

        body = await generate_followup_sms_body(prospect)
        sms_result = await send_outreach_sms(db, prospect, config, body)
        await db.commit()

        if sms_result.get("error"):
            raise Exception(sms_result["error"])

        return {"status": "sent", "twilio_sid": sms_result.get("twilio_sid")}


async def _handle_send_sequence_email(payload: dict) -> dict:
    """Send a deferred outreach email (smart timing). Re-runs the send logic."""
    import uuid
    from sqlalchemy import func as sqla_func
    from src.models.outreach import Outreach
    from src.models.outreach_email import OutreachEmail
    from src.models.sales_config import SalesEngineConfig
    from src.workers.outreach_sequencer import send_sequence_email, is_within_send_window
    from src.config import get_settings

    outreach_id = payload.get("outreach_id")
    if not outreach_id:
        return {"status": "skipped", "reason": "no outreach_id"}

    async with async_session_factory() as db:
        prospect = await db.get(Outreach, uuid.UUID(outreach_id))
        if not prospect:
            return {"status": "skipped", "reason": "prospect not found"}

        if prospect.email_unsubscribed:
            return {"status": "skipped", "reason": "unsubscribed"}

        if not prospect.prospect_email:
            return {"status": "skipped", "reason": "no email"}

        result = await db.execute(
            select(SalesEngineConfig).limit(1)
        )
        config = result.scalar_one_or_none()
        if not config or not config.is_active:
            return {"status": "skipped", "reason": "engine inactive"}

        # Check business hours before sending
        if not is_within_send_window(config):
            from src.services.task_dispatch import enqueue_task

            await enqueue_task(
                task_type="send_sequence_email",
                payload={"outreach_id": outreach_id},
                priority=5,
                delay_seconds=1800,
            )
            return {"status": "re-queued", "reason": "outside send window"}

        # Check daily limit before sending deferred email
        daily_limit = config.daily_email_limit or 50
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        count_result = await db.execute(
            select(sqla_func.count()).select_from(OutreachEmail).where(
                and_(
                    OutreachEmail.sent_at >= today_start,
                    OutreachEmail.direction == "outbound",
                )
            )
        )
        today_count = count_result.scalar() or 0

        if today_count >= daily_limit:
            # Re-enqueue for tomorrow morning
            from src.services.task_dispatch import enqueue_task

            tomorrow_9am = (today_start + timedelta(days=1)).replace(hour=9)
            delay_seconds = int((tomorrow_9am - datetime.now(timezone.utc)).total_seconds())
            delay_seconds = max(60, delay_seconds)  # At least 60 seconds

            await enqueue_task(
                task_type="send_sequence_email",
                payload={"outreach_id": outreach_id},
                priority=5,
                delay_seconds=delay_seconds,
            )
            logger.info(
                "Daily email limit (%d) reached - deferring task for prospect %s to tomorrow",
                daily_limit, outreach_id[:8],
            )
            return {"status": "re-queued", "reason": "daily limit reached"}

        settings = get_settings()
        await send_sequence_email(db, config, settings, prospect)
        await db.commit()

        return {"status": "sent", "prospect_id": outreach_id}
