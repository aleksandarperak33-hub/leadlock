"""
Extended tests for src/main.py - covers Sentry init failure, sales engine config
branches (auto-create, inactive, exception), brave_api_key warning, and shutdown
with pending worker tasks.
"""
import asyncio
import contextlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.main import lifespan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings(**overrides):
    """Build a mock Settings object with sensible defaults."""
    defaults = {
        "app_env": "test",
        "app_base_url": "http://localhost:8000",
        "log_level": "WARNING",
        "dashboard_jwt_secret": "test_jwt_secret",
        "encryption_key": "test_encryption_key",
        "sentry_dsn": "",
        "sales_engine_enabled": False,
        "brave_api_key": "",
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


_CORE_WORKER_PATHS = [
    "src.workers.system_health.run_system_health",
    "src.workers.retry_worker.run_retry_worker",
    "src.workers.lead_state_manager.run_lead_state_manager",
    "src.workers.crm_sync.run_crm_sync",
    "src.workers.sms_dispatch.run_sms_dispatch",
    "src.workers.registration_poller.run_registration_poller",
]

_SALES_WORKER_PATHS = [
    "src.workers.scraper.run_scraper",
    "src.workers.outreach_sequencer.run_outreach_sequencer",
    "src.workers.outreach_monitor.run_outreach_monitor",
    "src.workers.task_processor.run_task_processor",
]


def _enter_worker_patches(stack, paths):
    """Enter patch context managers for worker paths into the ExitStack."""
    for p in paths:
        stack.enter_context(patch(p, return_value=AsyncMock()()))


def _dummy_create_task(coro):
    """Replace asyncio.create_task: close the coroutine, return a mock Task."""
    coro.close()
    task = MagicMock(spec=asyncio.Task)
    task.cancel = MagicMock()
    return task


class _FakeDbCtx:
    """Async context manager that yields a mock db session."""

    def __init__(self, mock_db):
        self._db = mock_db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Sentry init failure branch (lines 62-63)
# ---------------------------------------------------------------------------


class TestSentryInitFailure:
    @pytest.mark.asyncio
    async def test_sentry_init_exception_logs_warning(self):
        """When sentry_sdk.init raises, lifespan logs a warning and continues."""
        mock_settings = _make_mock_settings(sentry_dsn="https://sentry.io/test")
        mock_app = MagicMock()

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("src.main.get_settings", return_value=mock_settings))
            mock_logger = stack.enter_context(patch("src.main.logger"))
            stack.enter_context(patch("asyncio.create_task", side_effect=_dummy_create_task))
            stack.enter_context(patch("asyncio.wait", new_callable=AsyncMock, return_value=(set(), set())))
            stack.enter_context(patch("sentry_sdk.init", side_effect=RuntimeError("Sentry connection failed")))
            _enter_worker_patches(stack, _CORE_WORKER_PATHS)

            async with lifespan(mock_app):
                pass

            warning_calls = [
                c for c in mock_logger.warning.call_args_list
                if "Sentry initialization failed" in str(c)
            ]
            assert len(warning_calls) == 1


# ---------------------------------------------------------------------------
# Sales engine - brave_api_key warning (line 116)
# ---------------------------------------------------------------------------


class TestSalesEngineBraveKeyWarning:
    @pytest.mark.asyncio
    async def test_logs_error_when_brave_key_missing(self):
        """Sales engine enabled but BRAVE_API_KEY not set logs an error."""
        mock_settings = _make_mock_settings(
            sales_engine_enabled=True,
            brave_api_key="",
        )
        mock_app = MagicMock()

        mock_db = AsyncMock()
        mock_config = MagicMock()
        mock_config.is_active = True
        mock_config.target_locations = ["Austin"]
        mock_config.target_trade_types = ["hvac"]
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("src.main.get_settings", return_value=mock_settings))
            mock_logger = stack.enter_context(patch("src.main.logger"))
            stack.enter_context(patch("asyncio.create_task", side_effect=_dummy_create_task))
            stack.enter_context(patch("asyncio.wait", new_callable=AsyncMock, return_value=(set(), set())))
            stack.enter_context(patch("src.database.async_session_factory", return_value=_FakeDbCtx(mock_db)))
            _enter_worker_patches(stack, _CORE_WORKER_PATHS)
            _enter_worker_patches(stack, _SALES_WORKER_PATHS)

            async with lifespan(mock_app):
                pass

            error_calls = [
                c for c in mock_logger.error.call_args_list
                if "BRAVE_API_KEY" in str(c)
            ]
            assert len(error_calls) == 1


# ---------------------------------------------------------------------------
# Sales engine config - auto-create (lines 131-134)
# ---------------------------------------------------------------------------


class TestSalesEngineConfigAutoCreate:
    @pytest.mark.asyncio
    async def test_auto_creates_config_when_none_exists(self):
        """When no SalesEngineConfig row exists, one is auto-created inactive."""
        mock_settings = _make_mock_settings(
            sales_engine_enabled=True,
            brave_api_key="brave_key_123",
        )
        mock_app = MagicMock()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("src.main.get_settings", return_value=mock_settings))
            mock_logger = stack.enter_context(patch("src.main.logger"))
            stack.enter_context(patch("asyncio.create_task", side_effect=_dummy_create_task))
            stack.enter_context(patch("asyncio.wait", new_callable=AsyncMock, return_value=(set(), set())))
            stack.enter_context(patch("src.database.async_session_factory", return_value=_FakeDbCtx(mock_db)))
            _enter_worker_patches(stack, _CORE_WORKER_PATHS)
            _enter_worker_patches(stack, _SALES_WORKER_PATHS)

            async with lifespan(mock_app):
                pass

            mock_db.add.assert_called_once()
            mock_db.commit.assert_awaited_once()
            info_calls = [
                c for c in mock_logger.info.call_args_list
                if "Auto-created SalesEngineConfig" in str(c)
            ]
            assert len(info_calls) == 1


# ---------------------------------------------------------------------------
# Sales engine config - inactive (line 139)
# ---------------------------------------------------------------------------


class TestSalesEngineConfigInactive:
    @pytest.mark.asyncio
    async def test_logs_info_when_config_inactive(self):
        """When SalesEngineConfig exists but is_active=False, info is logged."""
        mock_settings = _make_mock_settings(
            sales_engine_enabled=True,
            brave_api_key="brave_key_123",
        )
        mock_app = MagicMock()

        mock_config = MagicMock()
        mock_config.is_active = False

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("src.main.get_settings", return_value=mock_settings))
            mock_logger = stack.enter_context(patch("src.main.logger"))
            stack.enter_context(patch("asyncio.create_task", side_effect=_dummy_create_task))
            stack.enter_context(patch("asyncio.wait", new_callable=AsyncMock, return_value=(set(), set())))
            stack.enter_context(patch("src.database.async_session_factory", return_value=_FakeDbCtx(mock_db)))
            _enter_worker_patches(stack, _CORE_WORKER_PATHS)
            _enter_worker_patches(stack, _SALES_WORKER_PATHS)

            async with lifespan(mock_app):
                pass

            info_calls = [
                c for c in mock_logger.info.call_args_list
                if "is_active=False" in str(c)
            ]
            assert len(info_calls) == 1


# ---------------------------------------------------------------------------
# Sales engine config - verification failure (lines 150-151)
# ---------------------------------------------------------------------------


class TestSalesEngineConfigVerifyFailure:
    @pytest.mark.asyncio
    async def test_logs_warning_on_db_error(self):
        """When DB query fails, a warning is logged and startup continues."""
        mock_settings = _make_mock_settings(
            sales_engine_enabled=True,
            brave_api_key="brave_key_123",
        )
        mock_app = MagicMock()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB connect failed"))

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("src.main.get_settings", return_value=mock_settings))
            mock_logger = stack.enter_context(patch("src.main.logger"))
            stack.enter_context(patch("asyncio.create_task", side_effect=_dummy_create_task))
            stack.enter_context(patch("asyncio.wait", new_callable=AsyncMock, return_value=(set(), set())))
            stack.enter_context(patch("src.database.async_session_factory", return_value=_FakeDbCtx(mock_db)))
            _enter_worker_patches(stack, _CORE_WORKER_PATHS)
            _enter_worker_patches(stack, _SALES_WORKER_PATHS)

            async with lifespan(mock_app):
                pass

            warning_calls = [
                c for c in mock_logger.warning.call_args_list
                if "Failed to verify SalesEngineConfig" in str(c)
            ]
            assert len(warning_calls) == 1


# ---------------------------------------------------------------------------
# Shutdown with pending tasks (lines 176, 178)
# ---------------------------------------------------------------------------


class TestShutdownPendingTasks:
    @pytest.mark.asyncio
    async def test_shutdown_cancels_pending_tasks_and_gathers(self):
        """When asyncio.wait returns pending tasks, they are cancelled and gathered."""
        mock_settings = _make_mock_settings(sales_engine_enabled=False)
        mock_app = MagicMock()

        mock_tasks = []

        def capture_create_task(coro):
            mock_task = MagicMock(spec=asyncio.Task)
            mock_task.cancel = MagicMock()
            mock_tasks.append(mock_task)
            coro.close()
            return mock_task

        pending_task = MagicMock(spec=asyncio.Task)
        pending_task.cancel = MagicMock()

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("src.main.get_settings", return_value=mock_settings))
            stack.enter_context(patch("src.main.logger"))
            stack.enter_context(patch("asyncio.create_task", side_effect=capture_create_task))
            stack.enter_context(patch("asyncio.wait", new_callable=AsyncMock, return_value=(set(), {pending_task})))
            mock_gather = stack.enter_context(patch("asyncio.gather", new_callable=AsyncMock))
            _enter_worker_patches(stack, _CORE_WORKER_PATHS)

            async with lifespan(mock_app):
                pass

            mock_gather.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_pending_tasks_cancelled_individually(self):
        """Each pending task returned by asyncio.wait gets cancel() called."""
        mock_settings = _make_mock_settings(sales_engine_enabled=False)
        mock_app = MagicMock()

        def capture_create_task(coro):
            mock_task = MagicMock(spec=asyncio.Task)
            mock_task.cancel = MagicMock()
            coro.close()
            return mock_task

        pending_task_1 = MagicMock(spec=asyncio.Task)
        pending_task_1.cancel = MagicMock()
        pending_task_2 = MagicMock(spec=asyncio.Task)
        pending_task_2.cancel = MagicMock()

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch("src.main.get_settings", return_value=mock_settings))
            stack.enter_context(patch("src.main.logger"))
            stack.enter_context(patch("asyncio.create_task", side_effect=capture_create_task))
            stack.enter_context(
                patch("asyncio.wait", new_callable=AsyncMock, return_value=(set(), {pending_task_1, pending_task_2}))
            )
            stack.enter_context(patch("asyncio.gather", new_callable=AsyncMock))
            _enter_worker_patches(stack, _CORE_WORKER_PATHS)

            async with lifespan(mock_app):
                pass

        pending_task_1.cancel.assert_called()
        pending_task_2.cancel.assert_called()
