"""
System health worker — merged from health_monitor + deliverability_monitor.
Runs every 5 minutes.

Phase 1: Database + Redis connectivity checks (from health_monitor)
Phase 2: SMS/email reputation monitoring (from deliverability_monitor)
"""
import asyncio
import logging
from datetime import datetime, timezone

from src.services.deliverability import (
    get_deliverability_summary,
    get_email_reputation,
    DELIVERY_RATE_WARNING,
    DELIVERY_RATE_CRITICAL,
)
from src.utils.alerting import send_alert, AlertType

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 300  # 5 minutes


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:system_health",
            datetime.now(timezone.utc).isoformat(),
            ex=600,
        )
    except Exception as e:
        logger.debug("Heartbeat write failed: %s", str(e))


async def run_system_health():
    """Main loop — connectivity checks + deliverability monitoring every 5 min."""
    logger.info("System health worker started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            # Phase 1: Infrastructure connectivity
            await _check_connectivity()
            # Phase 2: SMS + email reputation
            await _check_deliverability()
        except Exception as e:
            logger.error("System health worker error: %s", str(e), exc_info=True)

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Phase 1: Connectivity checks (from health_monitor)
# ---------------------------------------------------------------------------

async def _check_connectivity():
    """Check database and Redis connectivity."""
    # Database
    try:
        from src.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error("Database health check failed: %s", str(e))
        await send_alert(
            AlertType.HEALTH_CHECK_FAILED,
            f"Database connectivity check failed: {str(e)}",
            severity="critical",
        )

    # Redis
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.ping()
    except Exception as e:
        logger.warning("Redis health check failed: %s", str(e))
        await send_alert(
            AlertType.HEALTH_CHECK_FAILED,
            f"Redis connectivity check failed: {str(e)}",
            severity="critical",
        )


# ---------------------------------------------------------------------------
# Phase 2: Deliverability monitoring (from deliverability_monitor)
# ---------------------------------------------------------------------------

async def _check_deliverability():
    """Check SMS and email deliverability metrics and alert on issues."""
    # === SMS reputation ===
    try:
        summary = await get_deliverability_summary()

        overall_rate = summary.get("overall_delivery_rate")
        total_sent = summary.get("total_sent_24h", 0)

        if total_sent == 0 or overall_rate is None:
            return

        logger.info(
            "Deliverability check: rate=%.1f%% sent=%d delivered=%d numbers=%d",
            (overall_rate or 0) * 100,
            total_sent,
            summary.get("total_delivered_24h", 0),
            len(summary.get("numbers", [])),
        )

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
                f"Monitor closely - may need content or number review.",
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
    except Exception as e:
        logger.warning("SMS deliverability check failed: %s", str(e))

    # === Email reputation ===
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        email_rep = await get_email_reputation(redis)

        if email_rep["status"] in ("poor", "critical"):
            logger.error(
                "EMAIL REPUTATION %s (score: %.1f) - bounce: %.2f%%, complaints: %.4f%%",
                email_rep["status"].upper(),
                email_rep["score"],
                email_rep["metrics"].get("bounce_rate", 0) * 100,
                email_rep["metrics"].get("complaint_rate", 0) * 100,
            )
            await send_alert(
                AlertType.SMS_DELIVERY_FAILED,
                f"EMAIL REPUTATION {email_rep['status'].upper()} - score {email_rep['score']:.1f}. "
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
                "Email reputation warning (score: %.1f) - bounce: %.2f%%",
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
