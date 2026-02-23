"""
Tests for SalesEngineConfig Redis cache.
Covers: cache hit, cache miss, invalidation, Redis failure fallback.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestConfigCache:
    """Tests for src.services.config_cache."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self):
        """Should return cached data without hitting DB."""
        from src.services.config_cache import get_sales_config

        cached = json.dumps({"is_active": True, "daily_email_limit": 50})
        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached

        with patch("src.services.config_cache.get_redis", return_value=mock_redis):
            result = await get_sales_config()

        assert result["is_active"] is True
        assert result["daily_email_limit"] == 50

    @pytest.mark.asyncio
    async def test_cache_miss_loads_from_db(self):
        """Should query DB and populate cache on miss."""
        from src.services.config_cache import get_sales_config

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True

        mock_config = MagicMock(spec=[])
        mock_config.is_active = True
        mock_config.target_trade_types = ["plumbing"]
        mock_config.target_locations = ["Austin, TX"]
        mock_config.daily_email_limit = 100
        mock_config.daily_scrape_limit = 50
        mock_config.sequence_delay_hours = 24
        mock_config.max_sequence_steps = 5
        mock_config.from_email = "test@example.com"
        mock_config.from_name = "Test"
        # Optional attrs used via getattr() — must be real values, not MagicMock
        mock_config.sender_name = None
        mock_config.booking_url = None
        mock_config.reply_to_email = None
        mock_config.company_address = None
        mock_config.sms_after_email_reply = False
        mock_config.sms_from_phone = None
        mock_config.email_templates = None
        mock_config.scraper_interval_minutes = 15
        mock_config.variant_cooldown_days = 7
        mock_config.send_hours_start = 9
        mock_config.send_hours_end = 17
        mock_config.send_timezone = "America/New_York"
        mock_config.send_weekdays_only = True
        mock_config.scraper_paused = False
        mock_config.sequencer_paused = False
        mock_config.cleanup_paused = False
        mock_config.monthly_budget_usd = None
        mock_config.budget_alert_threshold = 0.8

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.return_value = mock_result

        with patch("src.services.config_cache.get_redis", return_value=mock_redis), \
             patch("src.database.async_session_factory", return_value=mock_session):
            result = await get_sales_config()

        assert result is not None
        assert result["is_active"] is True
        assert result["daily_email_limit"] == 100
        # Should have cached the result
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_no_config_row(self):
        """Should return None and cache empty sentinel when no config exists."""
        from src.services.config_cache import get_sales_config

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.return_value = mock_result

        with patch("src.services.config_cache.get_redis", return_value=mock_redis), \
             patch("src.database.async_session_factory", return_value=mock_session):
            result = await get_sales_config()

        assert result is None

    @pytest.mark.asyncio
    async def test_invalidation_deletes_key(self):
        """invalidate_sales_config should delete the Redis key."""
        from src.services.config_cache import invalidate_sales_config, CACHE_KEY

        mock_redis = AsyncMock()
        with patch("src.services.config_cache.get_redis", return_value=mock_redis):
            await invalidate_sales_config()

        mock_redis.delete.assert_called_once_with(CACHE_KEY)

    @pytest.mark.asyncio
    async def test_cache_empty_sentinel(self):
        """Empty string sentinel in cache should return None."""
        from src.services.config_cache import get_sales_config

        mock_redis = AsyncMock()
        mock_redis.get.return_value = ""

        with patch("src.services.config_cache.get_redis", return_value=mock_redis):
            result = await get_sales_config()

        assert result is None


class TestEventBus:
    """Tests for src.services.event_bus."""

    @pytest.mark.asyncio
    async def test_publish_event(self):
        """Should publish to Redis channel and push to list."""
        from src.services.event_bus import publish_event

        mock_redis = AsyncMock()
        with patch("src.services.event_bus.get_redis", return_value=mock_redis):
            await publish_event("config_changed", {"field": "daily_email_limit"})

        mock_redis.publish.assert_called_once()
        mock_redis.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_drain_events_empty(self):
        """Should return empty list when no events pending."""
        from src.services.event_bus import drain_events

        mock_redis = AsyncMock()
        mock_redis.rpop.return_value = None

        with patch("src.services.event_bus.get_redis", return_value=mock_redis):
            events = await drain_events()

        assert events == []

    @pytest.mark.asyncio
    async def test_drain_events_returns_parsed(self):
        """Should return parsed JSON events."""
        from src.services.event_bus import drain_events

        mock_redis = AsyncMock()
        mock_redis.rpop.side_effect = [
            json.dumps({"type": "config_changed", "data": {}}),
            None,
        ]

        with patch("src.services.event_bus.get_redis", return_value=mock_redis):
            events = await drain_events()

        assert len(events) == 1
        assert events[0]["type"] == "config_changed"


class TestAlertingRedis:
    """Tests for Redis-backed alert cooldowns."""

    @pytest.mark.asyncio
    async def test_acquire_cooldown_first_call(self):
        """Should allow alert when SET NX succeeds (no cooldown key exists)."""
        from src.utils.alerting import _acquire_cooldown

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("src.utils.dedup.get_redis", return_value=mock_redis):
            result = await _acquire_cooldown("test_alert")

        assert result is True
        mock_redis.set.assert_called_once_with(
            "leadlock:alert_cooldown:test_alert", "1", nx=True, ex=300,
        )

    @pytest.mark.asyncio
    async def test_acquire_cooldown_during_cooldown(self):
        """Should block alert when SET NX fails (cooldown key already exists)."""
        from src.utils.alerting import _acquire_cooldown

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=None)

        with patch("src.utils.dedup.get_redis", return_value=mock_redis):
            result = await _acquire_cooldown("test_alert")

        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_cooldown_redis_failure_uses_fallback(self):
        """Should allow alert when Redis is down (in-memory fallback)."""
        from src.utils.alerting import _acquire_cooldown, _local_cooldowns

        test_key = "test_redis_down_fallback"
        _local_cooldowns.pop(test_key, None)

        with patch("src.utils.dedup.get_redis", side_effect=Exception("Redis down")):
            result = await _acquire_cooldown(test_key)

        assert result is True
        _local_cooldowns.pop(test_key, None)
