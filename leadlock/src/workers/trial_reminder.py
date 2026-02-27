"""
Trial reminder worker — sends email reminders as trial expiry approaches.

Runs every 6 hours. Sends reminders at 3 days and 1 day before trial ends.
Uses Redis dedup keys to prevent duplicate sends per client per threshold.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 6 * 3600  # 6 hours
REMINDER_THRESHOLDS_DAYS = [3, 1]
DEDUP_TTL_SECONDS = 7 * 86400  # Keep dedup keys for 7 days


async def _send_reminders() -> int:
    """Check for trials ending soon and send reminder emails. Returns count sent."""
    from src.database import async_session_factory
    from src.models.client import Client
    from src.services.transactional_email import send_trial_ending_soon

    now = datetime.now(timezone.utc)
    sent_count = 0

    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
    except Exception as e:
        logger.warning("Trial reminder: Redis unavailable, skipping cycle: %s", str(e))
        return 0

    async with async_session_factory() as db:
        result = await db.execute(
            select(Client).where(
                and_(
                    Client.billing_status == "trial",
                    Client.trial_ends_at.isnot(None),
                    Client.is_active == True,
                )
            )
        )
        clients = result.scalars().all()

        for client in clients:
            days_left = (client.trial_ends_at - now).days
            if days_left < 0:
                continue  # Trial already expired; Stripe handles the status transition
            for threshold in REMINDER_THRESHOLDS_DAYS:
                if days_left > threshold:
                    continue

                dedup_key = f"trial_reminder:{client.id}:{threshold}d"
                already_sent = await redis.get(dedup_key)
                if already_sent:
                    continue

                try:
                    await send_trial_ending_soon(
                        client.dashboard_email,
                        client.business_name,
                        max(days_left, 0),
                    )
                    await redis.setex(dedup_key, DEDUP_TTL_SECONDS, "1")
                    sent_count += 1
                    logger.info(
                        "Trial reminder sent: client=%s days_left=%d threshold=%d",
                        client.business_name, days_left, threshold,
                    )
                except Exception as e:
                    logger.error(
                        "Trial reminder failed: client=%s error=%s",
                        str(client.id)[:8], str(e),
                    )

    return sent_count


async def run_trial_reminder() -> None:
    """Main loop for trial reminder worker."""
    logger.info("Trial reminder worker started (interval=%ds)", POLL_INTERVAL_SECONDS)
    while True:
        try:
            sent = await _send_reminders()
            if sent > 0:
                logger.info("Trial reminder cycle complete: %d reminders sent", sent)
        except asyncio.CancelledError:
            logger.info("Trial reminder worker shutting down")
            return
        except Exception as e:
            logger.error("Trial reminder worker error: %s", str(e), exc_info=True)

        try:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Trial reminder worker shutting down")
            return
