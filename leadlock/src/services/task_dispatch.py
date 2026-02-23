"""
Task dispatch service - enqueue tasks for event-driven processing.
Central helper for creating tasks in the task queue.

Also pushes a notification to Redis so the task processor can wake
immediately via BRPOP instead of polling every 10 seconds.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.database import async_session_factory
from src.models.task_queue import TaskQueue

logger = logging.getLogger(__name__)

TASK_NOTIFY_KEY = "leadlock:task_notify"


async def enqueue_task(
    task_type: str,
    payload: Optional[dict] = None,
    priority: int = 5,
    delay_seconds: int = 0,
    max_retries: int = 3,
) -> str:
    """
    Enqueue a task for background processing.

    Args:
        task_type: Type of task (enrich_email, send_sequence, classify_reply, etc)
        payload: Task-specific data as JSON-serializable dict
        priority: 0=low, 5=normal, 10=high
        delay_seconds: Delay before task becomes eligible for processing
        max_retries: Maximum retry attempts on failure

    Returns:
        Task ID as string
    """
    scheduled_at = datetime.now(timezone.utc)
    if delay_seconds > 0:
        scheduled_at = scheduled_at + timedelta(seconds=delay_seconds)

    task = TaskQueue(
        task_type=task_type,
        payload=payload or {},
        priority=priority,
        max_retries=max_retries,
        scheduled_at=scheduled_at,
    )

    async with async_session_factory() as db:
        db.add(task)
        await db.commit()
        task_id = str(task.id)

    logger.info(
        "Task enqueued: type=%s priority=%d delay=%ds id=%s",
        task_type, priority, delay_seconds, task_id[:8],
    )

    # Notify task processor to wake immediately (non-blocking, best-effort)
    if delay_seconds == 0:
        try:
            from src.utils.dedup import get_redis
            redis = await get_redis()
            await redis.lpush(TASK_NOTIFY_KEY, task_id)
        except Exception as e:
            logger.debug("Failed to notify task processor: %s", str(e))

    return task_id
