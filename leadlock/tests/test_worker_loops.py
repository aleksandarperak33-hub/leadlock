"""
Tests for worker heartbeat and main-loop coverage across five workers:
- deliverability_monitor: _heartbeat, run_deliverability_monitor
- stuck_lead_sweeper: _heartbeat, run_stuck_lead_sweeper
- retry_worker: _heartbeat, run_retry_worker
- lead_lifecycle: _heartbeat, run_lead_lifecycle
- crm_sync: _heartbeat, run_crm_sync

Covers the uncovered lines:
- _heartbeat: Redis set with TTL + silent exception handling
- run_*: logger.info on start, while-True loop body, error logging,
  heartbeat call, asyncio.sleep call
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# Deliverability Monitor
# ============================================================================


class TestDeliverabilityMonitorHeartbeat:
    """_heartbeat() — Redis health check storage and error handling."""

    async def test_heartbeat_stores_timestamp_in_redis(self):
        """Heartbeat sets key with 600s TTL in Redis."""
        redis_mock = AsyncMock()
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=redis_mock,
        ):
            from src.workers.deliverability_monitor import _heartbeat

            await _heartbeat()

        redis_mock.set.assert_awaited_once()
        args, kwargs = redis_mock.set.call_args
        assert args[0] == "leadlock:worker_health:deliverability_monitor"
        assert kwargs.get("ex") == 600

    async def test_heartbeat_swallows_redis_errors(self):
        """Heartbeat silently handles Redis connection failures."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("no redis"),
        ):
            from src.workers.deliverability_monitor import _heartbeat

            await _heartbeat()  # must not raise


class TestRunDeliverabilityMonitor:
    """run_deliverability_monitor() — main loop behaviour."""

    async def test_loop_calls_check_then_heartbeat_then_sleeps(self):
        """One iteration: _check_deliverability -> _heartbeat -> sleep."""
        call_order = []

        async def fake_check():
            call_order.append("check")

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append(("sleep", seconds))
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.deliverability_monitor._check_deliverability",
                side_effect=fake_check,
            ),
            patch(
                "src.workers.deliverability_monitor._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.deliverability_monitor.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.deliverability_monitor import (
                MONITOR_INTERVAL_SECONDS,
                run_deliverability_monitor,
            )

            with pytest.raises(KeyboardInterrupt):
                await run_deliverability_monitor()

        assert call_order == [
            "check",
            "heartbeat",
            ("sleep", MONITOR_INTERVAL_SECONDS),
        ]

    async def test_loop_catches_check_errors_and_continues(self, caplog):
        """Errors in _check_deliverability are logged, loop keeps going."""
        call_order = []

        async def fail_check():
            call_order.append("check_error")
            raise RuntimeError("service down")

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append("sleep")
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.deliverability_monitor._check_deliverability",
                side_effect=fail_check,
            ),
            patch(
                "src.workers.deliverability_monitor._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.deliverability_monitor.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.deliverability_monitor import run_deliverability_monitor

            with (
                caplog.at_level(
                    logging.ERROR, logger="src.workers.deliverability_monitor"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_deliverability_monitor()

        assert "check_error" in call_order
        assert "heartbeat" in call_order
        assert any(
            "Deliverability monitor error" in r.message for r in caplog.records
        )

    async def test_loop_logs_start_message(self, caplog):
        """run_deliverability_monitor logs an info message on start."""

        async def fake_sleep(seconds):
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.deliverability_monitor._check_deliverability",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.deliverability_monitor._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.deliverability_monitor.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.deliverability_monitor import run_deliverability_monitor

            with (
                caplog.at_level(
                    logging.INFO, logger="src.workers.deliverability_monitor"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_deliverability_monitor()

        assert any(
            "Deliverability monitor started" in r.message for r in caplog.records
        )


# ============================================================================
# Stuck Lead Sweeper
# ============================================================================


class TestStuckLeadSweeperHeartbeat:
    """_heartbeat() — Redis health check storage and error handling."""

    async def test_heartbeat_stores_timestamp_in_redis(self):
        """Heartbeat sets key with 600s TTL in Redis."""
        redis_mock = AsyncMock()
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=redis_mock,
        ):
            from src.workers.stuck_lead_sweeper import _heartbeat

            await _heartbeat()

        redis_mock.set.assert_awaited_once()
        args, kwargs = redis_mock.set.call_args
        assert args[0] == "leadlock:worker_health:stuck_lead_sweeper"
        assert kwargs.get("ex") == 600

    async def test_heartbeat_swallows_redis_errors(self):
        """Heartbeat silently handles Redis connection failures."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("no redis"),
        ):
            from src.workers.stuck_lead_sweeper import _heartbeat

            await _heartbeat()  # must not raise


class TestRunStuckLeadSweeper:
    """run_stuck_lead_sweeper() — main loop behaviour."""

    async def test_loop_calls_sweep_then_heartbeat_then_sleeps(self):
        """One iteration: _sweep_stuck_leads -> _heartbeat -> sleep."""
        call_order = []

        async def fake_sweep():
            call_order.append("sweep")
            return 0

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append(("sleep", seconds))
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.stuck_lead_sweeper._sweep_stuck_leads",
                side_effect=fake_sweep,
            ),
            patch(
                "src.workers.stuck_lead_sweeper._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.stuck_lead_sweeper.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.stuck_lead_sweeper import (
                SWEEP_INTERVAL_SECONDS,
                run_stuck_lead_sweeper,
            )

            with pytest.raises(KeyboardInterrupt):
                await run_stuck_lead_sweeper()

        assert call_order == [
            "sweep",
            "heartbeat",
            ("sleep", SWEEP_INTERVAL_SECONDS),
        ]

    async def test_loop_logs_found_count_when_positive(self, caplog):
        """When _sweep_stuck_leads returns > 0, an info message is logged."""
        call_order = []

        async def fake_sweep():
            call_order.append("sweep")
            return 3

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.stuck_lead_sweeper._sweep_stuck_leads",
                side_effect=fake_sweep,
            ),
            patch(
                "src.workers.stuck_lead_sweeper._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.stuck_lead_sweeper.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.stuck_lead_sweeper import run_stuck_lead_sweeper

            with (
                caplog.at_level(
                    logging.INFO, logger="src.workers.stuck_lead_sweeper"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_stuck_lead_sweeper()

        assert any(
            "found 3 stuck leads" in r.message for r in caplog.records
        )

    async def test_loop_catches_sweep_errors_and_continues(self, caplog):
        """Errors in _sweep_stuck_leads are logged, loop keeps going."""
        call_order = []

        async def fail_sweep():
            call_order.append("sweep_error")
            raise RuntimeError("db down")

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append("sleep")
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.stuck_lead_sweeper._sweep_stuck_leads",
                side_effect=fail_sweep,
            ),
            patch(
                "src.workers.stuck_lead_sweeper._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.stuck_lead_sweeper.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.stuck_lead_sweeper import run_stuck_lead_sweeper

            with (
                caplog.at_level(
                    logging.ERROR, logger="src.workers.stuck_lead_sweeper"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_stuck_lead_sweeper()

        assert "sweep_error" in call_order
        assert "heartbeat" in call_order
        assert any(
            "Stuck lead sweeper error" in r.message for r in caplog.records
        )

    async def test_loop_logs_start_message(self, caplog):
        """run_stuck_lead_sweeper logs an info message on start."""

        async def fake_sleep(seconds):
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.stuck_lead_sweeper._sweep_stuck_leads",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.workers.stuck_lead_sweeper._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.stuck_lead_sweeper.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.stuck_lead_sweeper import run_stuck_lead_sweeper

            with (
                caplog.at_level(
                    logging.INFO, logger="src.workers.stuck_lead_sweeper"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_stuck_lead_sweeper()

        assert any(
            "Stuck lead sweeper started" in r.message for r in caplog.records
        )


# ============================================================================
# Retry Worker
# ============================================================================


class TestRetryWorkerHeartbeat:
    """_heartbeat() — Redis health check storage and error handling."""

    async def test_heartbeat_stores_timestamp_in_redis(self):
        """Heartbeat sets key with 300s TTL in Redis."""
        redis_mock = AsyncMock()
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=redis_mock,
        ):
            from src.workers.retry_worker import _heartbeat

            await _heartbeat()

        redis_mock.set.assert_awaited_once()
        args, kwargs = redis_mock.set.call_args
        assert args[0] == "leadlock:worker_health:retry_worker"
        assert kwargs.get("ex") == 300

    async def test_heartbeat_swallows_redis_errors(self):
        """Heartbeat silently handles Redis connection failures."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("no redis"),
        ):
            from src.workers.retry_worker import _heartbeat

            await _heartbeat()  # must not raise


class TestRunRetryWorker:
    """run_retry_worker() — main loop behaviour."""

    async def test_loop_calls_process_then_heartbeat_then_sleeps(self):
        """One iteration: _process_pending_retries -> _heartbeat -> sleep."""
        call_order = []

        async def fake_process():
            call_order.append("process")
            return 0

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append(("sleep", seconds))
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.retry_worker._process_pending_retries",
                side_effect=fake_process,
            ),
            patch(
                "src.workers.retry_worker._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.retry_worker.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.retry_worker import (
                POLL_INTERVAL_SECONDS,
                run_retry_worker,
            )

            with pytest.raises(KeyboardInterrupt):
                await run_retry_worker()

        assert call_order == [
            "process",
            "heartbeat",
            ("sleep", POLL_INTERVAL_SECONDS),
        ]

    async def test_loop_logs_processed_count_when_positive(self, caplog):
        """When _process_pending_retries returns > 0, info is logged."""
        call_order = []

        async def fake_process():
            call_order.append("process")
            return 5

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.retry_worker._process_pending_retries",
                side_effect=fake_process,
            ),
            patch(
                "src.workers.retry_worker._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.retry_worker.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.retry_worker import run_retry_worker

            with (
                caplog.at_level(
                    logging.INFO, logger="src.workers.retry_worker"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_retry_worker()

        assert any(
            "processed 5 failed leads" in r.message for r in caplog.records
        )

    async def test_loop_catches_process_errors_and_continues(self, caplog):
        """Errors in _process_pending_retries are logged, loop keeps going."""
        call_order = []

        async def fail_process():
            call_order.append("process_error")
            raise RuntimeError("db down")

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append("sleep")
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.retry_worker._process_pending_retries",
                side_effect=fail_process,
            ),
            patch(
                "src.workers.retry_worker._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.retry_worker.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.retry_worker import run_retry_worker

            with (
                caplog.at_level(
                    logging.ERROR, logger="src.workers.retry_worker"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_retry_worker()

        assert "process_error" in call_order
        assert "heartbeat" in call_order
        assert any(
            "Retry worker error" in r.message for r in caplog.records
        )

    async def test_loop_logs_start_message(self, caplog):
        """run_retry_worker logs an info message on start."""

        async def fake_sleep(seconds):
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.retry_worker._process_pending_retries",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.workers.retry_worker._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.retry_worker.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.retry_worker import run_retry_worker

            with (
                caplog.at_level(
                    logging.INFO, logger="src.workers.retry_worker"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_retry_worker()

        assert any(
            "Retry worker started" in r.message for r in caplog.records
        )


# ============================================================================
# Lead Lifecycle
# ============================================================================


class TestLeadLifecycleHeartbeat:
    """_heartbeat() — Redis health check storage and error handling."""

    async def test_heartbeat_stores_timestamp_in_redis(self):
        """Heartbeat sets key with 3600s TTL in Redis."""
        redis_mock = AsyncMock()
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=redis_mock,
        ):
            from src.workers.lead_lifecycle import _heartbeat

            await _heartbeat()

        redis_mock.set.assert_awaited_once()
        args, kwargs = redis_mock.set.call_args
        assert args[0] == "leadlock:worker_health:lead_lifecycle"
        assert kwargs.get("ex") == 3600

    async def test_heartbeat_swallows_redis_errors(self):
        """Heartbeat silently handles Redis connection failures."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("no redis"),
        ):
            from src.workers.lead_lifecycle import _heartbeat

            await _heartbeat()  # must not raise


class TestRunLeadLifecycle:
    """run_lead_lifecycle() — main loop behaviour."""

    async def test_loop_calls_subroutines_then_heartbeat_then_sleeps(self):
        """One iteration: archive + dead + recycle -> _heartbeat -> sleep."""
        call_order = []

        async def fake_archive():
            call_order.append("archive")
            return 0

        async def fake_dead():
            call_order.append("dead")
            return 0

        async def fake_recycle():
            call_order.append("recycle")
            return 0

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append(("sleep", seconds))
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.lead_lifecycle._archive_old_leads",
                side_effect=fake_archive,
            ),
            patch(
                "src.workers.lead_lifecycle._mark_dead_leads",
                side_effect=fake_dead,
            ),
            patch(
                "src.workers.lead_lifecycle._schedule_cold_recycling",
                side_effect=fake_recycle,
            ),
            patch(
                "src.workers.lead_lifecycle._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.lead_lifecycle.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.lead_lifecycle import (
                POLL_INTERVAL_SECONDS,
                run_lead_lifecycle,
            )

            with pytest.raises(KeyboardInterrupt):
                await run_lead_lifecycle()

        assert call_order == [
            "archive",
            "dead",
            "recycle",
            "heartbeat",
            ("sleep", POLL_INTERVAL_SECONDS),
        ]

    async def test_loop_logs_summary_when_work_done(self, caplog):
        """When archived + dead + recycled > 0, summary info is logged."""
        async def fake_archive():
            return 2

        async def fake_dead():
            return 1

        async def fake_recycle():
            return 3

        async def fake_sleep(seconds):
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.lead_lifecycle._archive_old_leads",
                side_effect=fake_archive,
            ),
            patch(
                "src.workers.lead_lifecycle._mark_dead_leads",
                side_effect=fake_dead,
            ),
            patch(
                "src.workers.lead_lifecycle._schedule_cold_recycling",
                side_effect=fake_recycle,
            ),
            patch(
                "src.workers.lead_lifecycle._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.lead_lifecycle.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.lead_lifecycle import run_lead_lifecycle

            with (
                caplog.at_level(
                    logging.INFO, logger="src.workers.lead_lifecycle"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_lead_lifecycle()

        assert any(
            "archived=2" in r.message
            and "dead=1" in r.message
            and "recycled=3" in r.message
            for r in caplog.records
        )

    async def test_loop_no_summary_when_zero_work(self, caplog):
        """When all subroutines return 0, no summary line is logged."""
        async def fake_sleep(seconds):
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.lead_lifecycle._archive_old_leads",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.workers.lead_lifecycle._mark_dead_leads",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.workers.lead_lifecycle._schedule_cold_recycling",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.workers.lead_lifecycle._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.lead_lifecycle.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.lead_lifecycle import run_lead_lifecycle

            with (
                caplog.at_level(
                    logging.INFO, logger="src.workers.lead_lifecycle"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_lead_lifecycle()

        # The "Lead lifecycle:" summary line must not appear
        assert not any(
            "archived=" in r.message and "dead=" in r.message
            for r in caplog.records
        )

    async def test_loop_catches_errors_and_continues(self, caplog):
        """Errors in subroutines are logged, loop keeps going."""
        call_order = []

        async def fail_archive():
            call_order.append("archive_error")
            raise RuntimeError("db down")

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append("sleep")
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.lead_lifecycle._archive_old_leads",
                side_effect=fail_archive,
            ),
            patch(
                "src.workers.lead_lifecycle._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.lead_lifecycle.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.lead_lifecycle import run_lead_lifecycle

            with (
                caplog.at_level(
                    logging.ERROR, logger="src.workers.lead_lifecycle"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_lead_lifecycle()

        assert "archive_error" in call_order
        assert "heartbeat" in call_order
        assert any(
            "Lead lifecycle error" in r.message for r in caplog.records
        )

    async def test_loop_logs_start_message(self, caplog):
        """run_lead_lifecycle logs an info message on start."""

        async def fake_sleep(seconds):
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.lead_lifecycle._archive_old_leads",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.workers.lead_lifecycle._mark_dead_leads",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.workers.lead_lifecycle._schedule_cold_recycling",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "src.workers.lead_lifecycle._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.lead_lifecycle.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.lead_lifecycle import run_lead_lifecycle

            with (
                caplog.at_level(
                    logging.INFO, logger="src.workers.lead_lifecycle"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_lead_lifecycle()

        assert any(
            "Lead lifecycle worker started" in r.message for r in caplog.records
        )


# ============================================================================
# CRM Sync
# ============================================================================


class TestCrmSyncHeartbeat:
    """_heartbeat() — Redis health check storage and error handling."""

    async def test_heartbeat_stores_timestamp_in_redis(self):
        """Heartbeat sets key with 300s TTL in Redis."""
        redis_mock = AsyncMock()
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=redis_mock,
        ):
            from src.workers.crm_sync import _heartbeat

            await _heartbeat()

        redis_mock.set.assert_awaited_once()
        args, kwargs = redis_mock.set.call_args
        assert args[0] == "leadlock:worker_health:crm_sync"
        assert kwargs.get("ex") == 300

    async def test_heartbeat_swallows_redis_errors(self):
        """Heartbeat silently handles Redis connection failures."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("no redis"),
        ):
            from src.workers.crm_sync import _heartbeat

            await _heartbeat()  # must not raise


class TestRunCrmSync:
    """run_crm_sync() — main loop behaviour."""

    async def test_loop_calls_sync_then_heartbeat_then_sleeps(self):
        """One iteration: sync_pending_bookings -> _heartbeat -> sleep."""
        call_order = []

        async def fake_sync():
            call_order.append("sync")

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append(("sleep", seconds))
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.crm_sync.sync_pending_bookings",
                side_effect=fake_sync,
            ),
            patch(
                "src.workers.crm_sync._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.crm_sync.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.crm_sync import (
                POLL_INTERVAL_SECONDS,
                run_crm_sync,
            )

            with pytest.raises(KeyboardInterrupt):
                await run_crm_sync()

        assert call_order == [
            "sync",
            "heartbeat",
            ("sleep", POLL_INTERVAL_SECONDS),
        ]

    async def test_loop_catches_sync_errors_and_continues(self, caplog):
        """Errors in sync_pending_bookings are logged, loop keeps going."""
        call_order = []

        async def fail_sync():
            call_order.append("sync_error")
            raise RuntimeError("crm unreachable")

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append("sleep")
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.crm_sync.sync_pending_bookings",
                side_effect=fail_sync,
            ),
            patch(
                "src.workers.crm_sync._heartbeat",
                side_effect=fake_heartbeat,
            ),
            patch(
                "src.workers.crm_sync.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.crm_sync import run_crm_sync

            with (
                caplog.at_level(
                    logging.ERROR, logger="src.workers.crm_sync"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_crm_sync()

        assert "sync_error" in call_order
        assert "heartbeat" in call_order
        assert any(
            "CRM sync error" in r.message for r in caplog.records
        )

    async def test_loop_logs_start_message(self, caplog):
        """run_crm_sync logs an info message on start."""

        async def fake_sleep(seconds):
            raise KeyboardInterrupt()

        with (
            patch(
                "src.workers.crm_sync.sync_pending_bookings",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.crm_sync._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.crm_sync.asyncio.sleep",
                side_effect=fake_sleep,
            ),
        ):
            from src.workers.crm_sync import run_crm_sync

            with (
                caplog.at_level(
                    logging.INFO, logger="src.workers.crm_sync"
                ),
                pytest.raises(KeyboardInterrupt),
            ):
                await run_crm_sync()

        assert any(
            "CRM sync worker started" in r.message for r in caplog.records
        )


# ============================================================================
# Deliverability Monitor — line 76 (overall_rate is None early return)
# ============================================================================


class TestDeliverabilityMonitorNoneRate:
    """_check_deliverability when overall_delivery_rate is None but sends > 0."""

    async def test_none_rate_returns_early_without_alert(self):
        """When overall_delivery_rate is None (but total_sent > 0), returns after logging."""
        summary = {
            "overall_delivery_rate": None,
            "total_sent_24h": 10,
            "total_delivered_24h": 10,
            "numbers": [],
        }

        with (
            patch(
                "src.workers.deliverability_monitor.get_deliverability_summary",
                new_callable=AsyncMock,
                return_value=summary,
            ),
            patch(
                "src.workers.deliverability_monitor.send_alert",
                new_callable=AsyncMock,
            ) as mock_alert,
        ):
            from src.workers.deliverability_monitor import _check_deliverability

            await _check_deliverability()

            mock_alert.assert_not_awaited()


# ============================================================================
# Retry Worker — line 127 (qualify stage: client not found)
# ============================================================================


class TestRetryWorkerClientNotFound:
    """_retry_lead when lead exists but client is not found."""

    async def test_client_not_found_raises_valueerror(self):
        """When client is not found for a qualify/book retry, ValueError is raised."""
        import uuid

        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        payload = {"lead_id": str(lead_id), "last_message": "hi"}

        failed = MagicMock()
        failed.id = uuid.uuid4()
        failed.failure_stage = "qualify"
        failed.original_payload = payload
        failed.retry_count = 0

        lead = MagicMock()
        lead.id = lead_id
        lead.client_id = client_id

        db = MagicMock()
        # Return lead for Lead query, None for Client query
        db.get = AsyncMock(side_effect=lambda model, pk: lead if pk == str(lead_id) else None)

        from src.workers.retry_worker import _retry_lead

        with pytest.raises(ValueError, match="Client not found"):
            await _retry_lead(db, failed)
