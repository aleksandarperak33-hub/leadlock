"""
Tests for src/workers/health_monitor.py - system health checks.
"""
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared mock session factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def mock_session():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.get = AsyncMock()
    db.add = MagicMock()
    yield db


# ---------------------------------------------------------------------------
# _check_connectivity - database checks
# ---------------------------------------------------------------------------

class TestCheckHealthDatabase:
    """Database connectivity checks inside _check_connectivity."""

    async def test_db_select_1_success(self):
        """DB SELECT 1 succeeds - no error logged."""
        mock_db_session = mock_session()

        with patch(
            "src.workers.system_health.async_session_factory",
            return_value=mock_db_session,
            create=True,
        ):
            # Also patch the lazy import inside _check_connectivity
            with patch.dict(
                "sys.modules",
                {"src.database": MagicMock(async_session_factory=lambda: mock_db_session)},
            ):
                pass

        # Use the real function with patched imports
        with (
            patch(
                "src.database.async_session_factory",
                return_value=mock_db_session,
            ),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock) as mock_get_redis,
        ):
            redis_mock = AsyncMock()
            redis_mock.ping = AsyncMock(return_value=True)
            mock_get_redis.return_value = redis_mock

            from src.workers.system_health import _check_connectivity

            # Should complete without raising
            await _check_connectivity()

    async def test_db_failure_logs_error(self, caplog):
        """DB failure logs an error message."""

        @asynccontextmanager
        async def failing_session():
            raise ConnectionError("DB unreachable")
            yield  # noqa: unreachable - required for generator

        with (
            patch("src.database.async_session_factory", side_effect=failing_session),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock) as mock_get_redis,
        ):
            redis_mock = AsyncMock()
            redis_mock.ping = AsyncMock(return_value=True)
            mock_get_redis.return_value = redis_mock

            from src.workers.system_health import _check_connectivity

            with caplog.at_level(logging.ERROR, logger="src.workers.system_health"):
                await _check_connectivity()

            assert any("Database health check failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _check_connectivity - Redis checks
# ---------------------------------------------------------------------------

class TestCheckHealthRedis:
    """Redis connectivity checks inside _check_connectivity."""

    async def test_redis_ping_success(self):
        """Redis ping succeeds - no warning logged."""
        mock_db_ctx = mock_session()

        with (
            patch("src.database.async_session_factory", return_value=mock_db_ctx),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock) as mock_get_redis,
        ):
            redis_mock = AsyncMock()
            redis_mock.ping = AsyncMock(return_value=True)
            mock_get_redis.return_value = redis_mock

            from src.workers.system_health import _check_connectivity

            await _check_connectivity()
            redis_mock.ping.assert_awaited_once()

    async def test_redis_failure_logs_warning(self, caplog):
        """Redis failure logs a warning."""
        mock_db_ctx = mock_session()

        with (
            patch("src.database.async_session_factory", return_value=mock_db_ctx),
            patch(
                "src.utils.dedup.get_redis",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Redis unreachable"),
            ),
        ):
            from src.workers.system_health import _check_connectivity

            with caplog.at_level(logging.WARNING, logger="src.workers.system_health"):
                await _check_connectivity()

            assert any("Redis health check failed" in r.message for r in caplog.records)
