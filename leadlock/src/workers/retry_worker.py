"""
Retry worker — processes failed leads from the dead letter queue.
Runs every 60 seconds, picks oldest pending retries where next_retry_at <= now.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60
BATCH_SIZE = 10


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        from datetime import datetime, timezone
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:retry_worker",
            datetime.now(timezone.utc).isoformat(),
            ex=300,
        )
    except Exception:
        pass


async def run_retry_worker():
    """Main retry worker loop. Runs continuously."""
    logger.info("Retry worker started")

    while True:
        try:
            processed = await _process_pending_retries()
            if processed > 0:
                logger.info("Retry worker processed %d failed leads", processed)
        except Exception as e:
            logger.error("Retry worker error: %s", str(e), exc_info=True)

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _process_pending_retries() -> int:
    """Find and retry pending failed leads. Returns count processed."""
    from src.database import async_session_factory
    from src.models.failed_lead import FailedLead
    from src.utils.dead_letter import mark_retry_attempted, resolve_failed_lead

    now = datetime.now(timezone.utc)
    processed = 0

    async with async_session_factory() as db:
        # Find pending retries that are due
        result = await db.execute(
            select(FailedLead)
            .where(
                FailedLead.status.in_(["pending", "retrying"]),
                FailedLead.next_retry_at <= now,
            )
            .order_by(FailedLead.next_retry_at)
            .limit(BATCH_SIZE)
        )
        failed_leads = result.scalars().all()

        for failed in failed_leads:
            failed.status = "retrying"
            await db.flush()

            try:
                await _retry_lead(db, failed)
                await resolve_failed_lead(db, failed)
                processed += 1
            except Exception as e:
                logger.warning(
                    "Retry failed for %s (attempt %d): %s",
                    str(failed.id)[:8], failed.retry_count + 1, str(e),
                )
                failed.error_message = str(e)
                await mark_retry_attempted(db, failed)

        await db.commit()

    return processed


async def _retry_lead(db, failed_lead) -> None:
    """Attempt to reprocess a failed lead through the pipeline."""
    from src.schemas.lead_envelope import LeadEnvelope
    from src.agents.conductor import handle_new_lead

    payload = failed_lead.original_payload
    if not payload:
        raise ValueError("No original payload to retry")

    # Reconstruct envelope from saved payload
    stage = failed_lead.failure_stage

    if stage in ("webhook", "intake"):
        # Re-process as new lead
        envelope = LeadEnvelope(**payload)
        result = await handle_new_lead(db, envelope)

        if result.get("status") in ("intake_sent", "duplicate"):
            return  # Success or already handled
        if "error" in result.get("status", ""):
            raise RuntimeError(f"Retry failed: {result.get('status')}")
    else:
        # For qualify/book failures, we'd need the lead record
        # For now, log and mark as needing manual resolution
        raise NotImplementedError(
            f"Automatic retry for stage '{stage}' not yet implemented"
        )
