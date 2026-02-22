"""
Outreach pipeline health monitor - checks pipeline health every 15 minutes
and sends SMS/email alerts when things break.

Alert conditions:
- Zero emails sent in 4h during send window
- Bounce rate > 10% in 24h
- Open rate < 5% over 48h (n > 20)
- Sequencer heartbeat stale for 90 minutes
- Reputation system paused sending (score < 40)
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_

from src.database import async_session_factory
from src.models.outreach_email import OutreachEmail
from src.utils.alerting import send_alert, AlertType

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15 * 60  # 15 minutes

# Alert thresholds
ZERO_SENDS_HOURS = 4
BOUNCE_RATE_THRESHOLD = 0.10  # 10%
OPEN_RATE_THRESHOLD = 0.05  # 5%
OPEN_RATE_MIN_SAMPLE = 20
OPEN_RATE_WINDOW_HOURS = 48
HEARTBEAT_STALE_MINUTES = 90


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:outreach_health",
            datetime.now(timezone.utc).isoformat(),
            ex=1800,
        )
    except Exception:
        pass


async def run_outreach_health():
    """Main loop - check outreach pipeline health every 15 minutes."""
    logger.info("Outreach health monitor started (poll every %ds)", POLL_INTERVAL_SECONDS)

    # Wait 2 minutes on startup to let other workers initialize
    await asyncio.sleep(120)

    while True:
        try:
            await check_outreach_health()
        except Exception as e:
            logger.error("Outreach health check error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def check_outreach_health():
    """Run all outreach health checks and send alerts for failures."""
    from src.models.sales_config import SalesEngineConfig
    from src.workers.outreach_sequencer import is_within_send_window

    async with async_session_factory() as db:
        result = await db.execute(select(SalesEngineConfig).limit(1))
        config = result.scalar_one_or_none()

        if not config or not config.is_active:
            return

        now = datetime.now(timezone.utc)

        # Only check send-related alerts during send window
        in_send_window = is_within_send_window(config)

        if in_send_window:
            await _check_zero_sends(db, now)

        await _check_bounce_rate(db, now)
        await _check_open_rate(db, now)
        await _check_sequencer_heartbeat()
        await _check_reputation_paused()


async def _check_zero_sends(db, now: datetime) -> None:
    """Alert if zero outbound emails sent in the last 4 hours during send window."""
    cutoff = now - timedelta(hours=ZERO_SENDS_HOURS)

    result = await db.execute(
        select(func.count()).select_from(OutreachEmail).where(
            and_(
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
            )
        )
    )
    count = result.scalar() or 0

    if count == 0:
        await send_alert(
            alert_type=AlertType.OUTREACH_ZERO_SENDS,
            message=(
                f"Zero outbound emails sent in the last {ZERO_SENDS_HOURS} hours "
                f"during the send window. The sequencer may be stuck or paused."
            ),
            severity="critical",
            extra={"window_hours": str(ZERO_SENDS_HOURS), "check_time": now.isoformat()},
        )


async def _check_bounce_rate(db, now: datetime) -> None:
    """Alert if bounce rate exceeds 10% in the last 24 hours."""
    cutoff = now - timedelta(hours=24)

    sent_result = await db.execute(
        select(func.count()).select_from(OutreachEmail).where(
            and_(
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
            )
        )
    )
    sent_count = sent_result.scalar() or 0

    if sent_count < 10:
        return  # Not enough data

    bounced_result = await db.execute(
        select(func.count()).select_from(OutreachEmail).where(
            and_(
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
                OutreachEmail.bounced_at.isnot(None),
            )
        )
    )
    bounced_count = bounced_result.scalar() or 0

    bounce_rate = bounced_count / sent_count
    if bounce_rate > BOUNCE_RATE_THRESHOLD:
        await send_alert(
            alert_type=AlertType.HIGH_BOUNCE_RATE,
            message=(
                f"Email bounce rate is {bounce_rate:.1%} in the last 24h "
                f"({bounced_count}/{sent_count} bounced). "
                f"Threshold: {BOUNCE_RATE_THRESHOLD:.0%}. Check email list quality."
            ),
            severity="critical",
            extra={
                "bounce_rate": f"{bounce_rate:.4f}",
                "bounced": str(bounced_count),
                "sent": str(sent_count),
            },
        )


async def _check_open_rate(db, now: datetime) -> None:
    """Alert if open rate is below 5% over 48 hours with sufficient sample size."""
    cutoff = now - timedelta(hours=OPEN_RATE_WINDOW_HOURS)

    sent_result = await db.execute(
        select(func.count()).select_from(OutreachEmail).where(
            and_(
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
            )
        )
    )
    sent_count = sent_result.scalar() or 0

    if sent_count < OPEN_RATE_MIN_SAMPLE:
        return  # Not enough data for meaningful open rate

    opened_result = await db.execute(
        select(func.count()).select_from(OutreachEmail).where(
            and_(
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
                OutreachEmail.opened_at.isnot(None),
            )
        )
    )
    opened_count = opened_result.scalar() or 0

    open_rate = opened_count / sent_count
    if open_rate < OPEN_RATE_THRESHOLD:
        await send_alert(
            alert_type=AlertType.OUTREACH_LOW_OPEN_RATE,
            message=(
                f"Email open rate is {open_rate:.1%} over the last {OPEN_RATE_WINDOW_HOURS}h "
                f"({opened_count}/{sent_count} opened). "
                f"Threshold: {OPEN_RATE_THRESHOLD:.0%}. "
                f"Review subject lines and sender reputation."
            ),
            severity="warning",
            extra={
                "open_rate": f"{open_rate:.4f}",
                "opened": str(opened_count),
                "sent": str(sent_count),
                "window_hours": str(OPEN_RATE_WINDOW_HOURS),
            },
        )


async def _check_sequencer_heartbeat() -> None:
    """Alert if the outreach sequencer hasn't heartbeated in 90 minutes."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        heartbeat_raw = await redis.get("leadlock:worker_health:outreach_sequencer")
        if heartbeat_raw is None:
            await send_alert(
                alert_type=AlertType.OUTREACH_SEQUENCER_STALE,
                message=(
                    "Outreach sequencer has no heartbeat in Redis. "
                    "The worker may not be running."
                ),
                severity="critical",
            )
            return

        heartbeat_str = heartbeat_raw.decode() if isinstance(heartbeat_raw, bytes) else str(heartbeat_raw)
        last_heartbeat = datetime.fromisoformat(heartbeat_str)
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=HEARTBEAT_STALE_MINUTES)

        if last_heartbeat < stale_cutoff:
            minutes_ago = int((datetime.now(timezone.utc) - last_heartbeat).total_seconds() / 60)
            await send_alert(
                alert_type=AlertType.OUTREACH_SEQUENCER_STALE,
                message=(
                    f"Outreach sequencer last heartbeat was {minutes_ago} minutes ago. "
                    f"Threshold: {HEARTBEAT_STALE_MINUTES} minutes. "
                    f"The worker may be stuck or crashed."
                ),
                severity="critical",
                extra={"last_heartbeat": heartbeat_str, "minutes_ago": str(minutes_ago)},
            )
    except Exception as e:
        logger.warning("Failed to check sequencer heartbeat: %s", str(e))


async def _check_reputation_paused() -> None:
    """Alert if the email reputation system has paused sending."""
    try:
        from src.utils.dedup import get_redis
        from src.services.deliverability import get_email_reputation

        redis = await get_redis()
        reputation = await get_email_reputation(redis)

        if reputation["throttle"] == "paused":
            await send_alert(
                alert_type=AlertType.OUTREACH_REPUTATION_PAUSED,
                message=(
                    f"Email reputation system has PAUSED sending. "
                    f"Score: {reputation['score']}/100. "
                    f"Bounce rate: {reputation['metrics'].get('bounce_rate', 0):.2%}, "
                    f"Complaint rate: {reputation['metrics'].get('complaint_rate', 0):.4%}. "
                    f"Sending will not resume until reputation improves."
                ),
                severity="critical",
                extra={
                    "reputation_score": str(reputation["score"]),
                    "throttle": reputation["throttle"],
                },
            )
        elif reputation["throttle"] == "critical":
            await send_alert(
                alert_type=AlertType.OUTREACH_REPUTATION_CRITICAL,
                message=(
                    f"Email reputation is CRITICAL - sending at 25% capacity. "
                    f"Score: {reputation['score']}/100. "
                    f"Investigate bounce/complaint sources immediately."
                ),
                severity="error",
                extra={
                    "reputation_score": str(reputation["score"]),
                    "throttle": reputation["throttle"],
                },
            )
    except Exception as e:
        logger.warning("Failed to check email reputation: %s", str(e))
