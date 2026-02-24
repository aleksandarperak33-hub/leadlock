"""
Deliverability service - tracks SMS delivery rates, reputation scoring, and auto-throttle.

This module is the CORE fix for reputation degradation:
1. Tracks delivery/failure rates per Twilio number (rolling 24h window)
2. Computes sender reputation score (0-100)
3. Auto-throttles when reputation drops below threshold
4. Alerts when delivery rate drops below acceptable levels

Why reputation drops:
- High failure rates signal to carriers that you're sending spam
- Repeated sends to invalid/landline numbers hurt reputation
- Carrier filtering (30007) indicates content issues
- No monitoring means problems compound silently
"""
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Reputation thresholds
REPUTATION_EXCELLENT = 90  # Green: business as usual
REPUTATION_GOOD = 75       # Yellow: monitor closely
REPUTATION_WARNING = 60    # Orange: reduce send rate, alert admin
REPUTATION_CRITICAL = 40   # Red: pause non-essential sends, alert immediately

# Delivery rate thresholds
DELIVERY_RATE_HEALTHY = 0.95  # 95%+ delivered
DELIVERY_RATE_WARNING = 0.85  # Below 85% triggers warning
DELIVERY_RATE_CRITICAL = 0.70  # Below 70% triggers critical alert

# Throttle config
THROTTLE_WINDOW_SECONDS = 60  # 1-minute sliding window
THROTTLE_MAX_NORMAL = 30      # Normal: max 30 SMS per minute per number
THROTTLE_MAX_WARNING = 15     # Warning: reduce to 15/min
THROTTLE_MAX_CRITICAL = 5     # Critical: reduce to 5/min


async def record_sms_outcome(
    from_phone: str,
    to_phone: str,
    status: str,
    error_code: Optional[str] = None,
    provider: str = "twilio",
    client_id: Optional[str] = None,
) -> None:
    """
    Record an SMS delivery outcome in Redis for real-time reputation tracking.
    Called after every SMS send attempt and every status callback.
    """
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        now = time.time()
        day_ago = now - 86400  # 24h window

        # Key structure: deliverability:{from_phone}:{outcome}
        base_key = f"leadlock:deliverability:{from_phone}"

        # Record outcome in sorted set (score = timestamp)
        outcome = _classify_outcome(status, error_code)
        await redis.zadd(f"{base_key}:{outcome}", {f"{now}:{to_phone}": now})

        # Record total sends
        await redis.zadd(f"{base_key}:total", {f"{now}:{to_phone}": now})

        # Clean up old entries (older than 24h)
        for suffix in ("delivered", "pending", "failed", "filtered", "invalid", "total"):
            await redis.zremrangebyscore(f"{base_key}:{suffix}", 0, day_ago)

        # Set TTL on all keys (48h to ensure cleanup)
        for suffix in ("delivered", "pending", "failed", "filtered", "invalid", "total"):
            await redis.expire(f"{base_key}:{suffix}", 172800)

        # Also track per-client stats if client_id provided
        if client_id:
            client_key = f"leadlock:deliverability:client:{client_id}"
            await redis.zadd(f"{client_key}:{outcome}", {f"{now}:{to_phone}": now})
            await redis.zadd(f"{client_key}:total", {f"{now}:{to_phone}": now})
            for suffix in ("delivered", "pending", "failed", "filtered", "invalid", "total"):
                await redis.zremrangebyscore(f"{client_key}:{suffix}", 0, day_ago)
                await redis.expire(f"{client_key}:{suffix}", 172800)

    except Exception as e:
        logger.warning("Failed to record SMS outcome: %s", str(e))


def _classify_outcome(status: str, error_code: Optional[str]) -> str:
    """Classify an SMS outcome for reputation tracking."""
    if status == "delivered":
        return "delivered"
    if status == "sent":
        # "sent" means accepted by Twilio/carrier, NOT confirmed delivered to handset.
        # Do not count as "delivered" - this avoids inflating delivery rate metrics.
        return "pending"
    if error_code in ("30007",):
        return "filtered"  # Carrier filtering - content issue
    if error_code in ("21211", "21612", "30006"):
        return "invalid"  # Invalid/landline - list quality issue
    return "failed"


async def get_reputation_score(from_phone: str) -> dict:
    """
    Calculate sender reputation score for a Twilio number.

    Returns: {
        "score": int (0-100),
        "level": str (excellent/good/warning/critical),
        "delivery_rate": float (0.0-1.0),
        "total_sent_24h": int,
        "delivered_24h": int,
        "failed_24h": int,
        "filtered_24h": int,
        "invalid_24h": int,
        "throttle_limit": int (max SMS per minute),
    }
    """
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        base_key = f"leadlock:deliverability:{from_phone}"
        now = time.time()
        day_ago = now - 86400

        # Count outcomes in last 24h
        total = await redis.zcount(f"{base_key}:total", day_ago, now)
        delivered = await redis.zcount(f"{base_key}:delivered", day_ago, now)
        failed = await redis.zcount(f"{base_key}:failed", day_ago, now)
        filtered = await redis.zcount(f"{base_key}:filtered", day_ago, now)
        invalid = await redis.zcount(f"{base_key}:invalid", day_ago, now)

        # Calculate delivery rate
        delivery_rate = delivered / total if total > 0 else 1.0

        # Calculate reputation score (weighted factors)
        score = _compute_score(delivery_rate, filtered, invalid, total)
        level = _score_to_level(score)
        throttle_limit = _get_throttle_limit(level)

        return {
            "score": score,
            "level": level,
            "delivery_rate": round(delivery_rate, 4),
            "total_sent_24h": total,
            "delivered_24h": delivered,
            "failed_24h": failed,
            "filtered_24h": filtered,
            "invalid_24h": invalid,
            "throttle_limit": throttle_limit,
        }
    except Exception as e:
        logger.warning("Failed to get reputation score: %s", str(e))
        return {
            "score": 100,
            "level": "excellent",
            "delivery_rate": 1.0,
            "total_sent_24h": 0,
            "delivered_24h": 0,
            "failed_24h": 0,
            "filtered_24h": 0,
            "invalid_24h": 0,
            "throttle_limit": THROTTLE_MAX_NORMAL,
        }


def _compute_score(
    delivery_rate: float,
    filtered_count: int,
    invalid_count: int,
    total_count: int,
) -> int:
    """
    Compute reputation score 0-100 based on delivery metrics.

    Factors:
    - Delivery rate (60% weight): 95%+ = full marks, drops linearly
    - Carrier filter rate (25% weight): 0% = full marks, >5% = zero
    - Invalid number rate (15% weight): 0% = full marks, >10% = zero
    """
    if total_count == 0:
        return 100  # No data = assume good

    # Delivery rate component (60 points max)
    if delivery_rate >= 0.95:
        delivery_score = 60
    elif delivery_rate >= 0.70:
        # Linear scale from 70% (0 points) to 95% (60 points)
        delivery_score = int(60 * (delivery_rate - 0.70) / 0.25)
    else:
        delivery_score = 0

    # Carrier filter component (25 points max)
    filter_rate = filtered_count / total_count
    if filter_rate <= 0.01:
        filter_score = 25
    elif filter_rate <= 0.05:
        filter_score = int(25 * (1 - (filter_rate - 0.01) / 0.04))
    else:
        filter_score = 0

    # Invalid number component (15 points max)
    invalid_rate = invalid_count / total_count
    if invalid_rate <= 0.02:
        invalid_score = 15
    elif invalid_rate <= 0.10:
        invalid_score = int(15 * (1 - (invalid_rate - 0.02) / 0.08))
    else:
        invalid_score = 0

    return max(0, min(100, delivery_score + filter_score + invalid_score))


def _score_to_level(score: int) -> str:
    """Map reputation score to level."""
    if score >= REPUTATION_EXCELLENT:
        return "excellent"
    if score >= REPUTATION_GOOD:
        return "good"
    if score >= REPUTATION_WARNING:
        return "warning"
    return "critical"


def _get_throttle_limit(level: str) -> int:
    """Get SMS throttle limit based on reputation level."""
    if level == "excellent":
        return THROTTLE_MAX_NORMAL
    if level in ("good", "warning"):
        return THROTTLE_MAX_WARNING
    return THROTTLE_MAX_CRITICAL


async def check_send_allowed(from_phone: str) -> tuple[bool, str]:
    """
    Check if sending from this number is allowed based on reputation and throttle.
    Returns: (allowed, reason)
    """
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        # Get current reputation
        rep = await get_reputation_score(from_phone)

        # Check throttle (sliding window)
        throttle_key = f"leadlock:throttle:{from_phone}"
        now = time.time()
        window_start = now - THROTTLE_WINDOW_SECONDS

        # Count sends in current window
        current_count = await redis.zcount(throttle_key, window_start, now)
        limit = rep["throttle_limit"]

        if current_count >= limit:
            return False, f"Throttled: {current_count}/{limit} sends in last {THROTTLE_WINDOW_SECONDS}s (reputation={rep['level']})"

        # Record this send attempt
        await redis.zadd(throttle_key, {str(now): now})
        await redis.zremrangebyscore(throttle_key, 0, window_start)
        await redis.expire(throttle_key, THROTTLE_WINDOW_SECONDS * 2)

        return True, f"OK (reputation={rep['score']}, {current_count + 1}/{limit})"

    except Exception as e:
        # On Redis failure, allow sending (fail open for delivery)
        logger.warning("Throttle check failed: %s - allowing send", str(e))
        return True, "Redis unavailable - fail open"


# ─── EMAIL REPUTATION ──────────────────────────────────
# Redis keys for email metrics (rolling 24h window)
# email:reputation:sent - total emails sent
# email:reputation:delivered - total delivered
# email:reputation:bounced - total bounced (hard only)
# email:reputation:complained - spam reports
# email:reputation:opened - total opened
# email:reputation:clicked - total clicked

EMAIL_REPUTATION_TTL = 86400  # 24 hour rolling window

# Throttle factor mapping for email reputation
EMAIL_THROTTLE_FACTORS = {
    "normal": 1.0,
    "reduced": 0.5,
    "critical": 0.25,
    "paused": 0.0,
}


async def record_email_event(redis_client, event_type: str) -> None:
    """
    Record an email event for reputation scoring.

    Args:
        redis_client: Active Redis connection.
        event_type: One of sent|delivered|bounced|complained|opened|clicked.
    """
    valid_types = {"sent", "delivered", "bounced", "complained", "opened", "clicked"}
    if event_type not in valid_types:
        logger.warning("Invalid email event type: %s", event_type)
        return

    try:
        key = f"email:reputation:{event_type}"
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, EMAIL_REPUTATION_TTL)
        await pipe.execute()
    except Exception as e:
        logger.warning("Failed to record email event '%s': %s", event_type, str(e))


async def get_email_reputation(redis_client) -> dict:
    """
    Get email reputation score and metrics from a rolling 24h window.

    Args:
        redis_client: Active Redis connection.

    Returns:
        Dict with score (0-100), status, throttle level, and detailed metrics.
    """
    metric_keys = ["sent", "delivered", "bounced", "complained", "opened", "clicked"]
    values = {}
    for k in metric_keys:
        val = await redis_client.get(f"email:reputation:{k}")
        if val is not None:
            val_str = val.decode() if isinstance(val, bytes) else str(val)
            values[k] = int(val_str)
        else:
            values[k] = 0

    sent = values["sent"]
    if sent == 0:
        return {"score": 100, "status": "no_data", "throttle": "normal", "metrics": values}

    # Guardrails for small samples: still allow warmup, but pause hard if we see
    # unmistakably bad early signals. This protects sender reputation immediately.
    MIN_SAMPLE_SIZE = 50
    MIN_GUARDRAIL_SAMPLE = 20
    BOUNCE_RATE_CRITICAL = 0.08  # 8% = severe throttle
    BOUNCE_RATE_PAUSE = 0.12     # 12% = immediate pause
    COMPLAINT_RATE_PAUSE = 0.005  # 0.5% spam complaint rate = immediate pause

    warmup_bounce_rate = values["bounced"] / sent if sent > 0 else 0.0
    warmup_complaint_rate = values["complained"] / sent if sent > 0 else 0.0

    if sent < MIN_SAMPLE_SIZE:
        if sent >= MIN_GUARDRAIL_SAMPLE and (
            warmup_bounce_rate >= BOUNCE_RATE_PAUSE
            or warmup_complaint_rate >= COMPLAINT_RATE_PAUSE
        ):
            return {
                "score": 25.0,
                "status": "critical",
                "throttle": "paused",
                "metrics": {
                    **values,
                    "delivery_rate": round((values["delivered"] / sent) if sent > 0 else 0.0, 4),
                    "bounce_rate": round(warmup_bounce_rate, 4),
                    "complaint_rate": round(warmup_complaint_rate, 4),
                    "open_rate": 0.0,
                },
            }
        return {"score": 100, "status": "warmup", "throttle": "normal", "metrics": values}

    # If "delivered" events aren't being reported by SendGrid webhook but we have
    # opens (which prove delivery), infer delivered = sent - bounced.
    # This prevents the reputation system from self-pausing on missing webhook data.
    delivered = values["delivered"]
    if delivered == 0 and (values["opened"] > 0 or values["bounced"] < sent):
        delivered = sent - values["bounced"]
        values["delivered"] = delivered
        values["delivered_inferred"] = True

    delivery_rate = delivered / sent if sent > 0 else 0.0
    bounce_rate = values["bounced"] / sent
    complaint_rate = values["complained"] / sent
    open_rate = values["opened"] / delivered if delivered > 0 else 0.0

    # Weighted score (0-100)
    score = 100.0
    # Bounce penalty: -5 per 1% bounce rate (heavy penalty)
    # Scale down at low volume (50-100 sends) to prevent a few bounces from
    # tanking the score — each bounce shifts the rate by several % at low N.
    confidence = min(1.0, sent / 100)
    score -= bounce_rate * 500 * confidence
    # Complaint penalty: -20 per 0.1% complaint rate (CRITICAL)
    score -= complaint_rate * 20000
    # Low delivery bonus/penalty
    if delivery_rate < 0.95:
        score -= (0.95 - delivery_rate) * 200
    # Open rate bonus (minor)
    if open_rate > 0.15:
        score += min(5, (open_rate - 0.15) * 50)
    # Low open-rate penalty at meaningful volume.
    if sent >= 50:
        if open_rate < 0.05:
            score -= 20
        elif open_rate < 0.08:
            score -= 10

    score = max(0.0, min(100.0, score))

    # Status and throttle
    if score >= 90:
        status, throttle = "excellent", "normal"
    elif score >= 75:
        status, throttle = "good", "normal"
    elif score >= 60:
        status, throttle = "warning", "reduced"  # 50% of limit
    elif score >= 40:
        status, throttle = "poor", "critical"  # 25% of limit
    else:
        status, throttle = "critical", "paused"  # STOP sending

    # Hard guardrails override score-based throttling.
    if complaint_rate >= COMPLAINT_RATE_PAUSE:
        score = min(score, 20.0)
        status, throttle = "critical", "paused"
    elif bounce_rate >= BOUNCE_RATE_PAUSE and sent >= MIN_GUARDRAIL_SAMPLE:
        score = min(score, 30.0)
        status, throttle = "critical", "paused"
    elif bounce_rate >= BOUNCE_RATE_CRITICAL and sent >= MIN_GUARDRAIL_SAMPLE and throttle == "normal":
        score = min(score, 45.0)
        status, throttle = "poor", "critical"
    elif open_rate < 0.05 and sent >= 100 and throttle in ("normal", "reduced"):
        # Protect sender reputation when opens collapse at scale.
        score = min(score, 55.0)
        status, throttle = "warning", "reduced"

    return {
        "score": round(score, 1),
        "status": status,
        "throttle": throttle,
        "metrics": {
            **values,
            "delivery_rate": round(delivery_rate, 4),
            "bounce_rate": round(bounce_rate, 4),
            "complaint_rate": round(complaint_rate, 4),
            "open_rate": round(open_rate, 4),
        },
    }


async def get_deliverability_summary() -> dict:
    """
    Get aggregate deliverability summary across all numbers.
    Used for the admin dashboard.
    """
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        # Find all tracked phone numbers
        keys = []
        async for key in redis.scan_iter("leadlock:deliverability:+*:total"):
            key_str = key if isinstance(key, str) else key.decode()
            phone = key_str.split(":")[2]
            if phone not in [k.get("phone") for k in keys]:
                keys.append({"phone": phone, "key": key_str})

        numbers = []
        total_sent = 0
        total_delivered = 0

        for entry in keys:
            rep = await get_reputation_score(entry["phone"])
            numbers.append({
                "phone": entry["phone"][:6] + "***",
                **rep,
            })
            total_sent += rep["total_sent_24h"]
            total_delivered += rep["delivered_24h"]

        overall_rate = total_delivered / total_sent if total_sent > 0 else 1.0

        return {
            "overall_delivery_rate": round(overall_rate, 4),
            "total_sent_24h": total_sent,
            "total_delivered_24h": total_delivered,
            "numbers": numbers,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning("Failed to get deliverability summary: %s", str(e))
        return {
            "overall_delivery_rate": None,
            "total_sent_24h": 0,
            "total_delivered_24h": 0,
            "numbers": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }
