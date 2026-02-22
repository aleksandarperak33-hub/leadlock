"""
Shared agent cost tracking utility.

All agent workers use this to record per-agent AI spend in Redis.
Stored as daily hash: leadlock:agent_costs:{YYYY-MM-DD} with 30-day TTL.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_COST_KEY_PREFIX = "leadlock:agent_costs"
_COST_TTL_SECONDS = 30 * 86400  # 30 days


async def track_agent_cost(agent_name: str, cost_usd: float) -> None:
    """Increment the per-agent cost counter in Redis for today.

    Args:
        agent_name: Worker identifier (e.g. "ab_test_engine").
        cost_usd: Dollar amount of the AI call.
    """
    if cost_usd <= 0:
        return
    try:
        from src.utils.dedup import get_redis

        redis = await get_redis()
        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hash_key = f"{_COST_KEY_PREFIX}:{date_key}"
        await redis.hincrbyfloat(hash_key, agent_name, cost_usd)
        await redis.expire(hash_key, _COST_TTL_SECONDS)
    except Exception as e:
        logger.debug("Failed to track agent cost: %s", str(e))
