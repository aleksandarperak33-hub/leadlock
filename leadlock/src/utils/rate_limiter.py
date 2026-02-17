"""
Redis-based rate limiter for webhook endpoints.
Uses sliding window counter pattern for accurate rate limiting.
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Default limits
DEFAULT_IP_LIMIT = 100  # requests per minute per IP
DEFAULT_CLIENT_LIMIT = 30  # requests per minute per client_id
WINDOW_SECONDS = 60


async def check_rate_limit(
    key: str,
    limit: int = DEFAULT_IP_LIMIT,
    window: int = WINDOW_SECONDS,
) -> tuple[bool, Optional[int]]:
    """
    Check if a request is within rate limits using Redis sliding window.

    Returns: (allowed: bool, retry_after_seconds: int | None)
    """
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        redis_key = f"leadlock:ratelimit:{key}"
        now = time.time()
        window_start = now - window

        pipe = redis.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(redis_key, 0, window_start)
        # Add current request
        pipe.zadd(redis_key, {str(now): now})
        # Count requests in window
        pipe.zcard(redis_key)
        # Set expiry on the key
        pipe.expire(redis_key, window + 1)

        results = await pipe.execute()
        request_count = results[2]

        if request_count > limit:
            retry_after = int(window - (now - window_start))
            logger.warning(
                "Rate limit exceeded: key=%s count=%d limit=%d",
                key, request_count, limit,
            )
            return False, max(retry_after, 1)

        return True, None
    except Exception as e:
        # Redis failure should not block webhooks — allow through
        logger.warning("Rate limiter Redis error: %s. Allowing request.", str(e))
        return True, None


async def check_webhook_rate_limits(
    client_ip: str,
    client_id: Optional[str] = None,
) -> tuple[bool, Optional[int]]:
    """
    Check both IP and client-level rate limits.
    Returns (allowed, retry_after_seconds).
    """
    # Check IP limit
    ip_allowed, ip_retry = await check_rate_limit(
        f"ip:{client_ip}", DEFAULT_IP_LIMIT
    )
    if not ip_allowed:
        return False, ip_retry

    # Check client limit if client_id is provided
    if client_id:
        client_allowed, client_retry = await check_rate_limit(
            f"client:{client_id}", DEFAULT_CLIENT_LIMIT
        )
        if not client_allowed:
            return False, client_retry

    return True, None
