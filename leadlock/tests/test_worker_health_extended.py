"""
Extended tests for src/workers/health_monitor.py - covers _heartbeat (lines 13-18)
and run_system_health loop (lines 23-31).
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _heartbeat - Redis heartbeat storage (lines 13-18)
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
            from src.workers.system_health import _heartbeat

            await _heartbeat()

            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            key = call_args[0][0]
            assert key == "leadlock:worker_health:system_health"
            assert call_args[1]["ex"] == 600

    async def test_heartbeat_swallows_redis_errors(self):
        """_heartbeat catches exceptions silently (lines 17-18)."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis gone"),
        ):
            from src.workers.system_health import _heartbeat

            # Should not raise
            await _heartbeat()


# ---------------------------------------------------------------------------
# run_system_health - loop behavior (lines 23-31)
# ---------------------------------------------------------------------------

class TestRunHealthMonitor:
    """Cover the run_system_health loop."""

    async def test_loop_calls_check_phases_and_heartbeat(self):
        """run_system_health calls _check_connectivity, _check_deliverability, _heartbeat, and sleeps."""
        call_order = []

        async def mock_connectivity():
            call_order.append("connectivity")

        async def mock_deliverability():
            call_order.append("deliverability")

        async def mock_heartbeat():
            call_order.append("heartbeat")

        iteration = 0

        async def mock_sleep(seconds):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise asyncio.CancelledError("Stop loop after 1 iteration")

        with (
            patch("src.workers.system_health._check_connectivity", mock_connectivity),
            patch("src.workers.system_health._check_deliverability", mock_deliverability),
            patch("src.workers.system_health._heartbeat", mock_heartbeat),
            patch("src.workers.system_health.asyncio.sleep", mock_sleep),
        ):
            from src.workers.system_health import run_system_health

            with pytest.raises(asyncio.CancelledError):
                await run_system_health()

        assert "connectivity" in call_order
        assert "deliverability" in call_order
        assert "heartbeat" in call_order

    async def test_loop_handles_check_health_exception(self, caplog):
        """run_system_health logs error if a check phase raises."""
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
            patch("src.workers.system_health._check_connectivity", failing_check),
            patch("src.workers.system_health._check_deliverability", AsyncMock()),
            patch("src.workers.system_health._heartbeat", mock_heartbeat),
            patch("src.workers.system_health.asyncio.sleep", mock_sleep),
        ):
            from src.workers.system_health import run_system_health

            with caplog.at_level(logging.ERROR, logger="src.workers.system_health"):
                with pytest.raises(asyncio.CancelledError):
                    await run_system_health()

            assert any("System health worker error" in r.message for r in caplog.records)
