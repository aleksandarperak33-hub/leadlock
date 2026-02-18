"""
Deduplication tests.
"""
import pytest
from unittest.mock import AsyncMock, patch
from src.utils.dedup import make_dedup_key, is_duplicate


class TestDedupKey:
    def test_same_input_same_key(self):
        """Same client + phone + source should produce same key."""
        key1 = make_dedup_key("client1", "+15125559876", "website")
        key2 = make_dedup_key("client1", "+15125559876", "website")
        assert key1 == key2

    def test_different_phone_different_key(self):
        """Different phone numbers should produce different keys."""
        key1 = make_dedup_key("client1", "+15125559876", "website")
        key2 = make_dedup_key("client1", "+15125551234", "website")
        assert key1 != key2

    def test_different_source_different_key(self):
        """Different sources should produce different keys."""
        key1 = make_dedup_key("client1", "+15125559876", "website")
        key2 = make_dedup_key("client1", "+15125559876", "angi")
        assert key1 != key2

    def test_different_client_different_key(self):
        """Different clients should produce different keys."""
        key1 = make_dedup_key("client1", "+15125559876", "website")
        key2 = make_dedup_key("client2", "+15125559876", "website")
        assert key1 != key2

    def test_key_format(self):
        """Keys should have the correct prefix."""
        key = make_dedup_key("client1", "+15125559876", "website")
        assert key.startswith("leadlock:dedup:")


class TestIsDuplicate:
    """Test the async is_duplicate function with mocked Redis."""

    async def test_new_lead_returns_false(self, mock_redis):
        """New lead (SET NX succeeds) should return False."""
        mock_redis.set = AsyncMock(return_value=True)
        result = await is_duplicate("client1", "+15125559876", "website")
        assert result is False

    async def test_duplicate_lead_returns_true(self, mock_redis):
        """Duplicate lead (SET NX returns None) should return True."""
        mock_redis.set = AsyncMock(return_value=None)
        result = await is_duplicate("client1", "+15125559876", "website")
        assert result is True

    async def test_redis_failure_returns_false(self):
        """Redis failure should fail-open (assume not duplicate)."""
        with patch("src.utils.dedup.get_redis") as mock_get_redis:
            mock_get_redis.side_effect = Exception("Redis connection refused")
            result = await is_duplicate("client1", "+15125559876", "website")
            assert result is False
