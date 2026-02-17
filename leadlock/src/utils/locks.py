"""
Redis distributed locks — prevents race conditions on lead processing.
Uses Redis SET NX with TTL for automatic expiration.
"""
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 30
LOCK_WAIT_SECONDS = 5
LOCK_POLL_INTERVAL = 0.1  # 100ms


@asynccontextmanager
async def lead_lock(
    lead_id: str,
    ttl: int = LOCK_TTL_SECONDS,
    wait: float = LOCK_WAIT_SECONDS,
):
    """
    Acquire a distributed lock for a lead.
    Prevents two webhooks from processing the same lead simultaneously.

    Usage:
        async with lead_lock(lead_id):
            # process lead safely
    """
    lock_key = f"leadlock:lock:lead:{lead_id}"
    lock_value = uuid.uuid4().hex  # Unique value to ensure we only release our own lock

    acquired = False
    try:
        acquired = await _acquire_lock(lock_key, lock_value, ttl, wait)
        if not acquired:
            raise LockTimeoutError(f"Could not acquire lock for lead {lead_id[:8]}*** within {wait}s")
        yield
    finally:
        if acquired:
            await _release_lock(lock_key, lock_value)


async def _acquire_lock(
    key: str,
    value: str,
    ttl: int,
    wait: float,
) -> bool:
    """Try to acquire a Redis lock with polling."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        # Immediate attempt
        was_set = await redis.set(key, value, nx=True, ex=ttl)
        if was_set:
            return True

        # Poll until timeout
        elapsed = 0.0
        while elapsed < wait:
            await asyncio.sleep(LOCK_POLL_INTERVAL)
            elapsed += LOCK_POLL_INTERVAL
            was_set = await redis.set(key, value, nx=True, ex=ttl)
            if was_set:
                return True

        logger.warning("Lock acquisition timed out for %s", key)
        return False
    except Exception as e:
        # Redis failure should not block lead processing
        logger.warning("Redis lock error for %s: %s. Proceeding without lock.", key, str(e))
        return True  # Proceed without lock (graceful degradation)


async def _release_lock(key: str, value: str) -> None:
    """Release a Redis lock only if we still own it (compare-and-delete)."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        # Lua script for atomic compare-and-delete
        lua_script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        await redis.eval(lua_script, 1, key, value)
    except Exception as e:
        logger.warning("Redis lock release error for %s: %s", key, str(e))


class LockTimeoutError(Exception):
    """Raised when a lock cannot be acquired within the timeout."""
    pass
