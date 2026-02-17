"""
Deliverability monitor worker — aggregates SMS delivery stats and alerts on issues.
Runs every 5 minutes. This is the CORE worker for fixing reputation degradation.

Actions:
- Computes per-number reputation scores
- Alerts when delivery rate drops below threshold
- Logs deliverability trends for dashboard
- Auto-throttle enforcement is handled in real-time by deliverability service
"""
import asyncio
import logging
from datetime import datetime, timezone

from src.services.deliverability import (
    get_deliverability_summary,
    get_reputation_score,
    DELIVERY_RATE_WARNING,
    DELIVERY_RATE_CRITICAL,
)
from src.utils.alerting import send_alert, AlertType

logger = logging.getLogger(__name__)

MONITOR_INTERVAL_SECONDS = 300  # 5 minutes


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:deliverability_monitor",
            datetime.now(timezone.utc).isoformat(),
            ex=600,
        )
    except Exception:
        pass


async def run_deliverability_monitor():
    """Main monitor loop. Checks delivery health every 5 minutes."""
    logger.info("Deliverability monitor started")

    while True:
        try:
            await _check_deliverability()
        except Exception as e:
            logger.error("Deliverability monitor error: %s", str(e), exc_info=True)

        await _heartbeat()
        await asyncio.sleep(MONITOR_INTERVAL_SECONDS)


async def _check_deliverability():
    """Check deliverability metrics and alert on issues."""
    summary = await get_deliverability_summary()

    # Log overall stats
    overall_rate = summary.get("overall_delivery_rate")
    total_sent = summary.get("total_sent_24h", 0)

    if total_sent == 0:
        return  # No sends in last 24h, nothing to check

    logger.info(
        "Deliverability check: rate=%.1f%% sent=%d delivered=%d numbers=%d",
        (overall_rate or 0) * 100,
        total_sent,
        summary.get("total_delivered_24h", 0),
        len(summary.get("numbers", [])),
    )

    if overall_rate is None:
        return

    # Alert on overall delivery rate issues
    if overall_rate < DELIVERY_RATE_CRITICAL:
        await send_alert(
            AlertType.SMS_DELIVERY_FAILED,
            f"CRITICAL: Overall SMS delivery rate is {overall_rate*100:.1f}% "
            f"({summary['total_delivered_24h']}/{total_sent} in 24h). "
            f"Carrier reputation is at risk. Auto-throttle is active.",
            severity="critical",
            extra={
                "delivery_rate": f"{overall_rate*100:.1f}%",
                "total_sent": total_sent,
                "action": "auto_throttle_active",
            },
        )
    elif overall_rate < DELIVERY_RATE_WARNING:
        await send_alert(
            AlertType.SMS_DELIVERY_FAILED,
            f"WARNING: SMS delivery rate dropped to {overall_rate*100:.1f}% "
            f"({summary['total_delivered_24h']}/{total_sent} in 24h). "
            f"Monitor closely — may need content or number review.",
            severity="warning",
            extra={
                "delivery_rate": f"{overall_rate*100:.1f}%",
                "total_sent": total_sent,
            },
        )

    # Check individual numbers
    for number_stats in summary.get("numbers", []):
        if number_stats.get("level") in ("warning", "critical"):
            logger.warning(
                "Number %s reputation: score=%d level=%s rate=%.1f%% filtered=%d invalid=%d",
                number_stats["phone"],
                number_stats["score"],
                number_stats["level"],
                number_stats["delivery_rate"] * 100,
                number_stats["filtered_24h"],
                number_stats["invalid_24h"],
            )

    # === Email reputation monitoring ===
    try:
        from src.utils.dedup import get_redis
        from src.services.deliverability import get_email_reputation

        redis = await get_redis()
        email_rep = await get_email_reputation(redis)

        if email_rep["status"] in ("poor", "critical"):
            logger.error(
                "EMAIL REPUTATION %s (score: %.1f) — bounce: %.2f%%, complaints: %.4f%%",
                email_rep["status"].upper(),
                email_rep["score"],
                email_rep["metrics"].get("bounce_rate", 0) * 100,
                email_rep["metrics"].get("complaint_rate", 0) * 100,
            )
            await send_alert(
                AlertType.SMS_DELIVERY_FAILED,
                f"EMAIL REPUTATION {email_rep['status'].upper()} — score {email_rep['score']:.1f}. "
                f"Bounce rate: {email_rep['metrics'].get('bounce_rate', 0) * 100:.2f}%, "
                f"Complaint rate: {email_rep['metrics'].get('complaint_rate', 0) * 100:.4f}%. "
                f"Email sending is {'PAUSED' if email_rep['throttle'] == 'paused' else 'throttled'}.",
                severity="critical",
                extra={
                    "channel": "email",
                    "reputation_score": email_rep["score"],
                    "throttle": email_rep["throttle"],
                },
            )
        elif email_rep["status"] == "warning":
            logger.warning(
                "Email reputation warning (score: %.1f) — bounce: %.2f%%",
                email_rep["score"],
                email_rep["metrics"].get("bounce_rate", 0) * 100,
            )
        else:
            logger.info(
                "Email reputation %s (score: %.1f, sent: %d, delivered: %d, opened: %d)",
                email_rep["status"],
                email_rep["score"],
                email_rep["metrics"].get("sent", 0),
                email_rep["metrics"].get("delivered", 0),
                email_rep["metrics"].get("opened", 0),
            )
    except Exception as e:
        logger.warning("Email reputation check failed: %s", str(e))
