"""
Tests for src/api/health.py — health check endpoints (liveness, readiness, deep).
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.health import (
    health_check,
    readiness_check,
    deep_health_check,
    _check_database,
    _check_redis,
    _check_twilio,
    _check_ai_service,
    _check_workers,
    _twilio_cache,
    TWILIO_CACHE_TTL_SECONDS,
)


# ---------------------------------------------------------------------------
# GET /health — basic liveness
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_returns_healthy(self):
        """Liveness check always returns healthy with timestamp and version."""
        result = await health_check()
        assert result["status"] == "healthy"
        assert result["version"] == "2.0.0"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_timestamp_is_utc_iso(self):
        """Timestamp should be parseable ISO format."""
        result = await health_check()
        ts = result["timestamp"]
        # Should not raise
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# GET /health/ready — readiness check (DB + Redis)
# ---------------------------------------------------------------------------


class TestReadinessCheck:
    @pytest.mark.asyncio
    async def test_all_healthy_returns_ready(self):
        """When both DB and Redis are healthy, status is 'ready'."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await readiness_check(db=mock_db)

        assert result["status"] == "ready"
        assert result["checks"]["database"] is True
        assert result["checks"]["redis"] is True

    @pytest.mark.asyncio
    async def test_db_failure_returns_degraded(self):
        """When DB fails, status is 'degraded'."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("connection refused"))

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await readiness_check(db=mock_db)

        assert result["status"] == "degraded"
        assert result["checks"]["database"] is False
        assert result["checks"]["redis"] is True

    @pytest.mark.asyncio
    async def test_redis_failure_returns_degraded(self):
        """When Redis fails, status is 'degraded'."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=Exception("redis down"),
        ):
            result = await readiness_check(db=mock_db)

        assert result["status"] == "degraded"
        assert result["checks"]["database"] is True
        assert result["checks"]["redis"] is False

    @pytest.mark.asyncio
    async def test_both_fail_returns_degraded(self):
        """When both DB and Redis fail, status is 'degraded'."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("db error"))

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=Exception("redis error"),
        ):
            result = await readiness_check(db=mock_db)

        assert result["status"] == "degraded"
        assert result["checks"]["database"] is False
        assert result["checks"]["redis"] is False


# ---------------------------------------------------------------------------
# _check_database (helper)
# ---------------------------------------------------------------------------


class TestCheckDatabase:
    @pytest.mark.asyncio
    async def test_healthy_database(self):
        """Successful DB query returns healthy."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await _check_database(mock_db)
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_database_error(self):
        """DB error returns unhealthy with error message."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("timeout"))

        result = await _check_database(mock_db)
        assert result["healthy"] is False
        assert "timeout" in result["error"]


# ---------------------------------------------------------------------------
# _check_redis (helper)
# ---------------------------------------------------------------------------


class TestCheckRedis:
    @pytest.mark.asyncio
    async def test_healthy_redis(self):
        """Successful Redis ping returns healthy."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _check_redis()

        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_redis_error(self):
        """Redis error returns unhealthy with error message."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ):
            result = await _check_redis()

        assert result["healthy"] is False
        assert "connection refused" in result["error"]


# ---------------------------------------------------------------------------
# _check_twilio (helper with caching)
# ---------------------------------------------------------------------------


class TestCheckTwilio:
    def _reset_twilio_cache(self):
        """Reset the global Twilio cache between tests."""
        import src.api.health as health_mod
        health_mod._twilio_cache = {"status": None, "checked_at": None}

    @pytest.mark.asyncio
    async def test_twilio_not_configured(self):
        """When Twilio SID is empty, return unhealthy."""
        self._reset_twilio_cache()
        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = ""

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await _check_twilio()

        assert result["healthy"] is False
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_twilio_active_account(self):
        """Active Twilio account returns healthy."""
        self._reset_twilio_cache()
        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = "AC_test_123"
        mock_settings.twilio_auth_token = "auth_test"

        mock_account = MagicMock()
        mock_account.status = "active"

        mock_client = MagicMock()
        mock_client.api.accounts.return_value.fetch.return_value = mock_account

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("twilio.rest.Client", return_value=mock_client),
        ):
            result = await _check_twilio()

        assert result["healthy"] is True
        assert result["account_status"] == "active"

    @pytest.mark.asyncio
    async def test_twilio_suspended_account(self):
        """Suspended Twilio account returns unhealthy."""
        self._reset_twilio_cache()
        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = "AC_test_123"
        mock_settings.twilio_auth_token = "auth_test"

        mock_account = MagicMock()
        mock_account.status = "suspended"

        mock_client = MagicMock()
        mock_client.api.accounts.return_value.fetch.return_value = mock_account

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("twilio.rest.Client", return_value=mock_client),
        ):
            result = await _check_twilio()

        assert result["healthy"] is False
        assert result["account_status"] == "suspended"

    @pytest.mark.asyncio
    async def test_twilio_cache_hit(self):
        """Cached Twilio result is returned without re-checking."""
        import src.api.health as health_mod
        cached_result = {"healthy": True, "account_status": "active"}
        health_mod._twilio_cache = {
            "status": cached_result,
            "checked_at": datetime.now(timezone.utc),
        }

        result = await _check_twilio()
        assert result == cached_result

    @pytest.mark.asyncio
    async def test_twilio_cache_expired(self):
        """Expired cache triggers a fresh check."""
        import src.api.health as health_mod
        old_time = datetime.now(timezone.utc) - timedelta(seconds=TWILIO_CACHE_TTL_SECONDS + 60)
        health_mod._twilio_cache = {
            "status": {"healthy": True, "account_status": "active"},
            "checked_at": old_time,
        }

        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = ""

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await _check_twilio()

        # Should have re-checked and found not configured
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_twilio_api_exception(self):
        """Twilio API exception returns unhealthy."""
        self._reset_twilio_cache()
        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = "AC_test_123"
        mock_settings.twilio_auth_token = "auth_test"

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("twilio.rest.Client", side_effect=Exception("auth failed")),
        ):
            result = await _check_twilio()

        assert result["healthy"] is False
        assert "auth failed" in result["error"]


# ---------------------------------------------------------------------------
# _check_ai_service (helper)
# ---------------------------------------------------------------------------


class TestCheckAiService:
    @pytest.mark.asyncio
    async def test_ai_has_heartbeat(self):
        """AI service with a heartbeat timestamp is healthy."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="2025-01-01T00:00:00Z")

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _check_ai_service()

        assert result["healthy"] is True
        assert result["last_success"] == "2025-01-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_ai_no_heartbeat_yet(self):
        """AI service with no heartbeat (never used) is still healthy."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _check_ai_service()

        assert result["healthy"] is True
        assert result["last_success"] is None

    @pytest.mark.asyncio
    async def test_ai_redis_error_still_healthy(self):
        """Redis failure for AI check still returns healthy with note."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=Exception("redis down"),
        ):
            result = await _check_ai_service()

        assert result["healthy"] is True
        assert "note" in result


# ---------------------------------------------------------------------------
# _check_workers (helper)
# ---------------------------------------------------------------------------


class TestCheckWorkers:
    @pytest.mark.asyncio
    async def test_all_workers_have_heartbeats(self):
        """All workers with heartbeats returns healthy."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="2025-01-01T00:00:00Z")

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _check_workers()

        assert result["healthy"] is True
        assert "workers" in result
        assert all(w["healthy"] for w in result["workers"].values())

    @pytest.mark.asyncio
    async def test_some_workers_missing_heartbeats(self):
        """Workers with missing heartbeats returns unhealthy."""
        async def mock_get(key):
            if "health_monitor" in key:
                return "2025-01-01T00:00:00Z"
            return None

        mock_redis = AsyncMock()
        mock_redis.get = mock_get

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _check_workers()

        assert result["healthy"] is False
        assert result["workers"]["health_monitor"]["healthy"] is True
        assert result["workers"]["retry_worker"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_redis_error_returns_healthy_with_note(self):
        """Redis error for worker check still returns healthy with note."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=Exception("redis down"),
        ):
            result = await _check_workers()

        assert result["healthy"] is True
        assert "note" in result


# ---------------------------------------------------------------------------
# GET /health/deep — deep health check (orchestration)
# ---------------------------------------------------------------------------


class TestDeepHealthCheck:
    @pytest.mark.asyncio
    async def test_all_healthy_returns_healthy(self):
        """When all checks pass, overall status is 'healthy'."""
        mock_db = AsyncMock()

        with (
            patch("src.api.health._check_database", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_redis", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_twilio", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_ai_service", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_workers", new_callable=AsyncMock, return_value={"healthy": True}),
        ):
            result = await deep_health_check(db=mock_db)

        assert result["status"] == "healthy"
        assert result["version"] == "2.0.0"
        assert len(result["checks"]) == 5

    @pytest.mark.asyncio
    async def test_non_critical_failure_returns_degraded(self):
        """When only non-critical checks fail (e.g., Twilio), status is 'degraded'."""
        mock_db = AsyncMock()

        with (
            patch("src.api.health._check_database", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_redis", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_twilio", new_callable=AsyncMock, return_value={"healthy": False}),
            patch("src.api.health._check_ai_service", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_workers", new_callable=AsyncMock, return_value={"healthy": True}),
        ):
            result = await deep_health_check(db=mock_db)

        assert result["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_critical_failure_returns_unhealthy(self):
        """When a critical check (DB or Redis) fails, status is 'unhealthy'."""
        mock_db = AsyncMock()

        with (
            patch("src.api.health._check_database", new_callable=AsyncMock, return_value={"healthy": False}),
            patch("src.api.health._check_redis", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_twilio", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_ai_service", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_workers", new_callable=AsyncMock, return_value={"healthy": True}),
        ):
            result = await deep_health_check(db=mock_db)

        assert result["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_redis_critical_failure_returns_unhealthy(self):
        """When Redis (critical) fails, status is 'unhealthy'."""
        mock_db = AsyncMock()

        with (
            patch("src.api.health._check_database", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_redis", new_callable=AsyncMock, return_value={"healthy": False}),
            patch("src.api.health._check_twilio", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_ai_service", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_workers", new_callable=AsyncMock, return_value={"healthy": True}),
        ):
            result = await deep_health_check(db=mock_db)

        assert result["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_everything_down_returns_unhealthy(self):
        """All checks failing returns 'unhealthy'."""
        mock_db = AsyncMock()

        with (
            patch("src.api.health._check_database", new_callable=AsyncMock, return_value={"healthy": False}),
            patch("src.api.health._check_redis", new_callable=AsyncMock, return_value={"healthy": False}),
            patch("src.api.health._check_twilio", new_callable=AsyncMock, return_value={"healthy": False}),
            patch("src.api.health._check_ai_service", new_callable=AsyncMock, return_value={"healthy": False}),
            patch("src.api.health._check_workers", new_callable=AsyncMock, return_value={"healthy": False}),
        ):
            result = await deep_health_check(db=mock_db)

        assert result["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_response_includes_timestamp(self):
        """Deep health check includes ISO timestamp."""
        mock_db = AsyncMock()

        with (
            patch("src.api.health._check_database", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_redis", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_twilio", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_ai_service", new_callable=AsyncMock, return_value={"healthy": True}),
            patch("src.api.health._check_workers", new_callable=AsyncMock, return_value={"healthy": True}),
        ):
            result = await deep_health_check(db=mock_db)

        assert "timestamp" in result
        # Verify it's parseable
        datetime.fromisoformat(result["timestamp"])
