"""
Lead deduplication - Redis-based with 30-minute window.
Prevents duplicate lead processing from webhook retries or multiple form submissions.
"""
import hashlib
import logging
from typing import Optional
logger = logging.getLogger(__name__)

# Dedup window in seconds (30 minutes)
DEDUP_WINDOW_SECONDS = 1800

# Redis client (lazily initialized)
_redis_client = None


async def get_redis():
    """Get or create Redis connection."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis
        from src.config import get_settings
        _redis_client = aioredis.from_url(
            get_settings().redis_url,
            decode_responses=True,
        )
    return _redis_client


def make_dedup_key(client_id: str, phone: str, source: str) -> str:
    """
    Create a deduplication key from client_id + phone + source.
    Uses SHA-256 hash for consistent key length.
    """
    raw = f"{client_id}:{phone}:{source}"
    hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"leadlock:dedup:{hash_val}"


async def is_duplicate(
    client_id: str,
    phone: str,
    source: str,
) -> bool:
    """
    Check if this lead is a duplicate (same client + phone + source within 30 minutes).
    If not a duplicate, marks it in Redis to prevent future duplicates.

    Returns True if duplicate, False if new.
    """
    key = make_dedup_key(client_id, phone, source)

    try:
        redis = await get_redis()
        # SET NX = only set if not exists. Returns True if set (new), None if exists (dupe).
        was_set = await redis.set(key, "1", nx=True, ex=DEDUP_WINDOW_SECONDS)
        if was_set:
            return False  # New lead
        else:
            logger.info(
                "Duplicate lead detected: client=%s phone=%s source=%s",
                client_id, phone[:6] + "***", source,
            )
            return True  # Duplicate
    except Exception as e:
        # Redis failure should NOT block lead processing - assume not duplicate
        logger.warning("Redis dedup check failed: %s. Assuming not duplicate.", str(e))
        return False
