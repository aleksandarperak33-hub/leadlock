"""
Extended tests for src/workers/health_monitor.py — covers _heartbeat (lines 13-18)
and run_health_monitor loop (lines 23-31).
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _heartbeat — Redis heartbeat storage (lines 13-18)
# ---------------------------------------------------------------------------

class TestHeartbeat:
    """Cover the _heartbeat function."""

    async def test_heartbeat_stores_timestamp_in_redis(self):
        """_heartbeat sets a key in Redis with 600s expiry (lines 14-16)."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            from src.workers.health_monitor import _heartbeat

            await _heartbeat()

            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            key = call_args[0][0]
            assert key == "leadlock:worker_health:health_monitor"
            assert call_args[1]["ex"] == 600

    async def test_heartbeat_swallows_redis_errors(self):
        """_heartbeat catches exceptions silently (lines 17-18)."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis gone"),
        ):
            from src.workers.health_monitor import _heartbeat

            # Should not raise
            await _heartbeat()


# ---------------------------------------------------------------------------
# run_health_monitor — loop behavior (lines 23-31)
# ---------------------------------------------------------------------------

class TestRunHealthMonitor:
    """Cover the run_health_monitor loop."""

    async def test_loop_calls_check_health_and_heartbeat(self):
        """run_health_monitor calls check_health, _heartbeat, and sleeps (lines 23-31)."""
        call_order = []

        async def mock_check_health():
            call_order.append("check_health")

        async def mock_heartbeat():
            call_order.append("heartbeat")

        iteration = 0

        original_sleep = asyncio.sleep

        async def mock_sleep(seconds):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise asyncio.CancelledError("Stop loop after 1 iteration")

        with (
            patch("src.workers.health_monitor.check_health", mock_check_health),
            patch("src.workers.health_monitor._heartbeat", mock_heartbeat),
            patch("src.workers.health_monitor.asyncio.sleep", mock_sleep),
        ):
            from src.workers.health_monitor import run_health_monitor

            with pytest.raises(asyncio.CancelledError):
                await run_health_monitor()

        assert "check_health" in call_order
        assert "heartbeat" in call_order

    async def test_loop_handles_check_health_exception(self, caplog):
        """run_health_monitor logs error if check_health raises (lines 28-29)."""
        async def failing_check():
            raise RuntimeError("Check failed")

        async def mock_heartbeat():
            pass

        iteration = 0

        async def mock_sleep(seconds):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise asyncio.CancelledError("Stop loop")

        with (
            patch("src.workers.health_monitor.check_health", failing_check),
            patch("src.workers.health_monitor._heartbeat", mock_heartbeat),
            patch("src.workers.health_monitor.asyncio.sleep", mock_sleep),
        ):
            from src.workers.health_monitor import run_health_monitor

            with caplog.at_level(logging.ERROR, logger="src.workers.health_monitor"):
                with pytest.raises(asyncio.CancelledError):
                    await run_health_monitor()

            assert any("Health monitor error" in r.message for r in caplog.records)
