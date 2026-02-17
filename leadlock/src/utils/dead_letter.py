"""
Dead letter queue — captures failed leads for retry.
When any pipeline stage fails, the full context is saved for later retry.
"""
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.failed_lead import FailedLead
from src.utils.logging import get_correlation_id

logger = logging.getLogger(__name__)

# Exponential backoff schedule (minutes)
RETRY_DELAYS_MINUTES = [1, 5, 15, 60, 240]
MAX_RETRIES = 5


def _next_retry_at(retry_count: int) -> Optional[datetime]:
    """Calculate next retry time using exponential backoff."""
    if retry_count >= MAX_RETRIES:
        return None
    delay_idx = min(retry_count, len(RETRY_DELAYS_MINUTES) - 1)
    delay = RETRY_DELAYS_MINUTES[delay_idx]
    return datetime.now(timezone.utc) + timedelta(minutes=delay)


async def capture_failed_lead(
    db: AsyncSession,
    payload: dict,
    source: str,
    failure_stage: str,
    error: Exception,
    client_id: Optional[str] = None,
) -> FailedLead:
    """
    Capture a failed lead into the dead letter queue.
    Automatically schedules first retry.
    """
    import uuid

    client_uuid = None
    if client_id:
        try:
            client_uuid = uuid.UUID(client_id)
        except ValueError:
            pass

    failed = FailedLead(
        original_payload=payload,
        source=source,
        client_id=client_uuid,
        error_message=str(error),
        error_traceback=traceback.format_exc(),
        failure_stage=failure_stage,
        retry_count=0,
        max_retries=MAX_RETRIES,
        next_retry_at=_next_retry_at(0),
        status="pending",
        correlation_id=get_correlation_id(),
    )
    db.add(failed)
    await db.flush()

    logger.warning(
        "Lead captured in dead letter queue: stage=%s source=%s error=%s id=%s",
        failure_stage, source, str(error)[:100], str(failed.id)[:8],
    )
    return failed


async def mark_retry_attempted(
    db: AsyncSession,
    failed_lead: FailedLead,
) -> None:
    """Increment retry count and schedule next retry or mark as dead."""
    new_count = failed_lead.retry_count + 1
    failed_lead.retry_count = new_count

    if new_count >= failed_lead.max_retries:
        failed_lead.status = "dead"
        failed_lead.next_retry_at = None
        logger.error(
            "Failed lead %s exhausted retries (%d/%d) — marked as dead",
            str(failed_lead.id)[:8], new_count, failed_lead.max_retries,
        )
    else:
        failed_lead.status = "pending"
        failed_lead.next_retry_at = _next_retry_at(new_count)
        logger.info(
            "Failed lead %s retry %d/%d scheduled for %s",
            str(failed_lead.id)[:8], new_count, failed_lead.max_retries,
            failed_lead.next_retry_at.isoformat(),
        )


async def resolve_failed_lead(
    db: AsyncSession,
    failed_lead: FailedLead,
    resolved_by: str = "retry_worker",
) -> None:
    """Mark a failed lead as successfully resolved."""
    failed_lead.status = "resolved"
    failed_lead.resolved_at = datetime.now(timezone.utc)
    failed_lead.resolved_by = resolved_by
    logger.info(
        "Failed lead %s resolved by %s",
        str(failed_lead.id)[:8], resolved_by,
    )
