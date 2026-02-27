"""
Smart warmup optimizer - replaces static warmup schedule with dynamic pacing.

Rules:
- Reputation > 90 AND bounce rate < 2% -> Accelerate 1.5x (cut warmup to ~18 days)
- Reputation < 75 OR bounce rate > 5% -> Decelerate 0.5x
- Otherwise: use standard schedule

No AI calls. Pure algorithmic optimization using existing Redis reputation data.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Standard warmup schedule (same as outreach_sequencer)
STANDARD_SCHEDULE = [
    (0, 2, 20),
    (3, 6, 50),
    (7, 13, 100),
    (14, 20, 150),
    (21, None, None),
]

# Acceleration/deceleration thresholds
ACCELERATE_REP_THRESHOLD = 90
ACCELERATE_BOUNCE_THRESHOLD = 0.02  # 2%
DECELERATE_REP_THRESHOLD = 75
DECELERATE_BOUNCE_THRESHOLD = 0.05  # 5%

ACCELERATE_FACTOR = 1.5
DECELERATE_FACTOR = 0.5


def _get_standard_limit(days_since_start: int) -> Optional[int]:
    """Get the standard warmup limit for a given day."""
    for day_start, day_end, max_daily in STANDARD_SCHEDULE:
        if day_end is None:
            return None  # Past warmup period
        if day_start <= days_since_start <= day_end:
            return max_daily
    return None


async def get_optimized_warmup_limit(
    configured_limit: int,
    days_since_start: int,
) -> int:
    """
    Calculate optimized daily email limit based on reputation signals.

    Args:
        configured_limit: User-configured daily limit
        days_since_start: Days since warmup started

    Returns:
        Effective daily email limit
    """
    standard_limit = _get_standard_limit(days_since_start)

    if standard_limit is None:
        # Past warmup period - use configured limit
        return configured_limit

    # Get reputation data from Redis
    try:
        from src.utils.dedup import get_redis
        from src.services.deliverability import get_email_reputation

        redis = await get_redis()
        reputation = await get_email_reputation(redis)

        score = reputation.get("score", 80)
        metrics = reputation.get("metrics", {})
        bounce_rate = metrics.get("bounce_rate", 0.0)

        # Determine pacing factor
        if score > ACCELERATE_REP_THRESHOLD and bounce_rate < ACCELERATE_BOUNCE_THRESHOLD:
            factor = ACCELERATE_FACTOR
            pacing = "accelerated"
        elif score < DECELERATE_REP_THRESHOLD or bounce_rate > DECELERATE_BOUNCE_THRESHOLD:
            factor = DECELERATE_FACTOR
            pacing = "decelerated"
        else:
            factor = 1.0
            pacing = "standard"

        optimized = max(1, int(standard_limit * factor))
        effective = min(optimized, configured_limit)

        logger.info(
            "Warmup optimizer: day=%d standard=%d factor=%.1fx optimized=%d effective=%d "
            "pacing=%s reputation=%.0f bounce=%.2f%%",
            days_since_start, standard_limit, factor, optimized, effective,
            pacing, score, bounce_rate * 100,
        )

        return effective

    except Exception as e:
        logger.warning("Warmup optimizer failed (using standard): %s", str(e))
        return min(standard_limit, configured_limit)
