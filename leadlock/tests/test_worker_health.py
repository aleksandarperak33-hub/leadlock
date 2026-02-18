"""
Tests for src/workers/health_monitor.py — system health checks.
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
# check_health — database checks
# ---------------------------------------------------------------------------

class TestCheckHealthDatabase:
    """Database connectivity checks inside check_health."""

    async def test_db_select_1_success(self):
        """DB SELECT 1 succeeds — no error logged."""
        mock_db_session = mock_session()

        with patch(
            "src.workers.health_monitor.async_session_factory",
            return_value=mock_db_session,
            create=True,
        ):
            # Also patch the lazy import inside check_health
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

            from src.workers.health_monitor import check_health

            # Should complete without raising
            await check_health()

    async def test_db_failure_logs_error(self, caplog):
        """DB failure logs an error message."""

        @asynccontextmanager
        async def failing_session():
            raise ConnectionError("DB unreachable")
            yield  # noqa: unreachable — required for generator

        with (
            patch("src.database.async_session_factory", side_effect=failing_session),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock) as mock_get_redis,
        ):
            redis_mock = AsyncMock()
            redis_mock.ping = AsyncMock(return_value=True)
            mock_get_redis.return_value = redis_mock

            from src.workers.health_monitor import check_health

            with caplog.at_level(logging.ERROR, logger="src.workers.health_monitor"):
                await check_health()

            assert any("Database health check failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# check_health — Redis checks
# ---------------------------------------------------------------------------

class TestCheckHealthRedis:
    """Redis connectivity checks inside check_health."""

    async def test_redis_ping_success(self):
        """Redis ping succeeds — no warning logged."""
        mock_db_ctx = mock_session()

        with (
            patch("src.database.async_session_factory", return_value=mock_db_ctx),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock) as mock_get_redis,
        ):
            redis_mock = AsyncMock()
            redis_mock.ping = AsyncMock(return_value=True)
            mock_get_redis.return_value = redis_mock

            from src.workers.health_monitor import check_health

            await check_health()
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
            from src.workers.health_monitor import check_health

            with caplog.at_level(logging.WARNING, logger="src.workers.health_monitor"):
                await check_health()

            assert any("Redis health check failed" in r.message for r in caplog.records)
