"""
Extended tests for src/utils/dedup.py - covers get_redis initialization (lines 20-27).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# get_redis - lazy initialization (lines 20-27)
# ---------------------------------------------------------------------------

class TestGetRedis:
    """Cover the get_redis lazy initialization code path."""

    async def test_get_redis_initializes_on_first_call(self):
        """First call to get_redis creates a new Redis connection (lines 20-27)."""
        import src.utils.dedup as dedup_module

        # Reset the global to None to force initialization
        original = dedup_module._redis_client
        dedup_module._redis_client = None

        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"

        mock_redis_instance = MagicMock()

        try:
            with (
                patch("src.config.get_settings", return_value=mock_settings),
                patch("redis.asyncio.from_url", return_value=mock_redis_instance) as mock_from_url,
            ):
                result = await dedup_module.get_redis()

                mock_from_url.assert_called_once_with(
                    "redis://localhost:6379/0",
                    decode_responses=True,
                )
                assert result is mock_redis_instance
        finally:
            # Restore original state
            dedup_module._redis_client = original

    async def test_get_redis_returns_cached_on_subsequent_calls(self):
        """Second call to get_redis returns the cached client (line 20-21 skip)."""
        import src.utils.dedup as dedup_module

        original = dedup_module._redis_client
        fake_redis = MagicMock()
        dedup_module._redis_client = fake_redis

        try:
            result = await dedup_module.get_redis()
            assert result is fake_redis
        finally:
            dedup_module._redis_client = original
