"""
Task processor worker - polls the task_queue table and dispatches tasks.
Handles retries with exponential backoff.

Uses BRPOP on a Redis notification key for near-instant wake on new tasks,
with a 30-second timeout falling back to DB poll as safety net.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.task_queue import TaskQueue

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30  # Fallback DB poll interval
MAX_TASKS_PER_CYCLE = 10
BRPOP_TIMEOUT = 30  # seconds to wait for Redis notification
from src.services.task_dispatch import TASK_NOTIFY_KEY  # noqa: F401 — single source of truth


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set("leadlock:worker_health:task_processor", datetime.now(timezone.utc).isoformat(), ex=120)
    except Exception as e:
        logger.debug("Heartbeat write failed: %s", str(e))


async def run_task_processor():
    """Main loop - wait for notification or poll every 30s."""
    logger.info("Task processor started (adaptive polling, BRPOP %ds timeout)", BRPOP_TIMEOUT)

    while True:
        try:
            await process_cycle()
        except Exception as e:
            logger.error("Task processor cycle error: %s", str(e))

        await _heartbeat()

        # Wait for either a Redis notification or timeout
        try:
            from src.utils.dedup import get_redis
            redis = await get_redis()
            # BRPOP blocks until a notification arrives or timeout expires
            result = await redis.brpop(TASK_NOTIFY_KEY, timeout=BRPOP_TIMEOUT)
            if result:
                # Drain any additional notifications to avoid stacking
                while await redis.rpop(TASK_NOTIFY_KEY):
                    pass
        except Exception as e:
            # If Redis is unavailable, fall back to sleep
            logger.debug("Redis BRPOP unavailable, falling back to sleep: %s", str(e))
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
        "enrich_prospect": _handle_enrich_prospect,
        "record_signal": _handle_record_signal,
        "classify_reply": _handle_classify_reply,
        "send_sms_followup": _handle_send_sms_followup,
        "send_sequence_email": _handle_send_sequence_email,
        "generate_ab_variants": _handle_generate_ab_variants,
        "send_winback_email": _handle_send_winback_email,
        "generate_content": _handle_generate_content,
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


async def _handle_enrich_prospect(payload: dict) -> dict:
    """Research a prospect to find decision-maker name and email candidates."""
    import uuid
    from src.models.outreach import Outreach
    from src.services.prospect_research import research_prospect

    outreach_id = payload.get("outreach_id")
    if not outreach_id:
        return {"status": "skipped", "reason": "no outreach_id"}

    try:
        prospect_uuid = uuid.UUID(outreach_id)
    except ValueError:
        logger.warning("enrich_prospect: invalid UUID '%s'", outreach_id)
        return {"status": "skipped", "reason": "invalid uuid"}

    async with async_session_factory() as db:
        prospect = await db.get(Outreach, prospect_uuid)
        if not prospect:
            return {"status": "skipped", "reason": "prospect not found"}

        # Skip if already researched
        existing = prospect.enrichment_data or {}
        if existing.get("researched_at"):
            return {"status": "skipped", "reason": "already researched"}

        enrichment = await research_prospect(
            website=prospect.website or "",
            company_name=prospect.prospect_company or prospect.prospect_name or "",
            google_rating=prospect.google_rating,
            review_count=prospect.review_count,
        )

        # Store enrichment data (immutable update)
        prospect.enrichment_data = {**(prospect.enrichment_data or {}), **enrichment}

        # Update prospect_name with decision-maker name if found and current name is generic
        if enrichment.get("decision_maker_name"):
            current_name = prospect.prospect_name or ""
            # Only update if current name looks like a company name (not a person)
            from src.agents.sales_outreach import _extract_first_name
            if not _extract_first_name(current_name):
                prospect.prospect_name = enrichment["decision_maker_name"]
                logger.info(
                    "Updated prospect %s name: %s -> %s",
                    str(prospect.id)[:8], current_name, enrichment["decision_maker_name"],
                )

        prospect.updated_at = datetime.now(timezone.utc)
        await db.commit()

        return {
            "status": "enriched",
            "decision_maker": enrichment.get("decision_maker_name"),
            "source": enrichment.get("research_source"),
            "email_candidates": len(enrichment.get("email_candidates", [])),
            "ai_cost_usd": enrichment.get("ai_cost_usd", 0.0),
        }


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


async def _handle_generate_ab_variants(payload: dict) -> dict:
    """Generate A/B test variants for a sequence step."""
    from src.services.ab_testing import create_experiment

    sequence_step = payload.get("sequence_step", 1)
    target_trade = payload.get("target_trade")
    variant_count = payload.get("variant_count", 3)

    result = await create_experiment(
        sequence_step=sequence_step,
        target_trade=target_trade,
        variant_count=variant_count,
    )

    if not result:
        return {"status": "failed", "reason": "variant generation failed"}

    return {
        "status": "created",
        "experiment_id": result["experiment_id"],
        "variant_count": len(result["variants"]),
        "ai_cost_usd": result["ai_cost_usd"],
    }


async def _handle_send_winback_email(payload: dict) -> dict:
    """Send a win-back email to a cold prospect."""
    import uuid as uuid_mod
    from src.models.outreach import Outreach
    from src.models.sales_config import SalesEngineConfig
    from src.workers.winback_agent import _send_winback
    from src.config import get_settings

    outreach_id = payload.get("outreach_id")
    if not outreach_id:
        return {"status": "skipped", "reason": "no outreach_id"}

    async with async_session_factory() as db:
        prospect = await db.get(Outreach, uuid_mod.UUID(outreach_id))
        if not prospect:
            return {"status": "skipped", "reason": "prospect not found"}

        if prospect.winback_sent_at:
            return {"status": "skipped", "reason": "already sent winback"}

        config_result = await db.execute(
            select(SalesEngineConfig).limit(1)
        )
        config = config_result.scalar_one_or_none()
        if not config or not config.is_active:
            return {"status": "skipped", "reason": "engine inactive"}

        settings = get_settings()
        success = await _send_winback(db, config, settings, prospect, 0)
        await db.commit()

        return {"status": "sent" if success else "failed", "prospect_id": outreach_id}


async def _handle_generate_content(payload: dict) -> dict:
    """Generate a content piece via the content factory."""
    from src.services.content_generation import generate_content_piece

    content_type = payload.get("content_type", "blog_post")
    target_trade = payload.get("target_trade")
    target_keyword = payload.get("target_keyword")

    result = await generate_content_piece(
        content_type=content_type,
        target_trade=target_trade,
        target_keyword=target_keyword,
    )

    if result.get("error"):
        return {"status": "failed", "reason": result["error"]}

    return {
        "status": "created",
        "content_id": result.get("content_id"),
        "word_count": result.get("word_count", 0),
        "ai_cost_usd": result.get("ai_cost_usd", 0.0),
    }
