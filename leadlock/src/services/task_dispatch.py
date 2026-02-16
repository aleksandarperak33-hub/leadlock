"""
Task dispatch service — enqueue tasks for event-driven processing.
Central helper for creating tasks in the task queue.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from src.database import async_session_factory
from src.models.task_queue import TaskQueue

logger = logging.getLogger(__name__)


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
    scheduled_at = datetime.utcnow()
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
    return task_id
