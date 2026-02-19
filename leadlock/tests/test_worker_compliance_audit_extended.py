"""
Extended tests for src/workers/compliance_audit.py — covers run_compliance_audit
loop behavior (lines 18-27).
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# run_compliance_audit — loop behavior (lines 18-27)
# ---------------------------------------------------------------------------

class TestRunComplianceAudit:
    """Cover the run_compliance_audit loop."""

    async def test_loop_runs_audit_at_2am(self, caplog):
        """run_compliance_audit calls audit_compliance when hour == 2 (lines 21-24)."""
        audit_called = False

        async def mock_audit():
            nonlocal audit_called
            audit_called = True

        # Mock datetime.now to return 2:00 AM UTC
        mock_now = datetime(2026, 2, 18, 2, 0, 0, tzinfo=timezone.utc)

        iteration = 0

        async def mock_sleep(seconds):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise asyncio.CancelledError("Stop loop")

        with (
            patch("src.workers.compliance_audit.audit_compliance", mock_audit),
            patch("src.workers.compliance_audit.datetime") as mock_dt,
            patch("src.workers.compliance_audit.asyncio.sleep", mock_sleep),
        ):
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            from src.workers.compliance_audit import run_compliance_audit

            with pytest.raises(asyncio.CancelledError):
                await run_compliance_audit()

        assert audit_called is True

    async def test_loop_skips_audit_outside_2am(self):
        """run_compliance_audit does NOT call audit when hour != 2 (line 22)."""
        audit_called = False

        async def mock_audit():
            nonlocal audit_called
            audit_called = True

        # Mock datetime.now to return 10:00 AM UTC (not 2 AM)
        mock_now = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)

        iteration = 0

        async def mock_sleep(seconds):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise asyncio.CancelledError("Stop loop")

        with (
            patch("src.workers.compliance_audit.audit_compliance", mock_audit),
            patch("src.workers.compliance_audit.datetime") as mock_dt,
            patch("src.workers.compliance_audit.asyncio.sleep", mock_sleep),
        ):
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            from src.workers.compliance_audit import run_compliance_audit

            with pytest.raises(asyncio.CancelledError):
                await run_compliance_audit()

        assert audit_called is False

    async def test_loop_handles_audit_exception(self, caplog):
        """run_compliance_audit logs error if audit raises (lines 25-26)."""
        async def failing_audit():
            raise RuntimeError("Audit crashed")

        mock_now = datetime(2026, 2, 18, 2, 0, 0, tzinfo=timezone.utc)

        iteration = 0

        async def mock_sleep(seconds):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise asyncio.CancelledError("Stop loop")

        with (
            patch("src.workers.compliance_audit.audit_compliance", failing_audit),
            patch("src.workers.compliance_audit.datetime") as mock_dt,
            patch("src.workers.compliance_audit.asyncio.sleep", mock_sleep),
        ):
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            from src.workers.compliance_audit import run_compliance_audit

            with caplog.at_level(logging.ERROR, logger="src.workers.compliance_audit"):
                with pytest.raises(asyncio.CancelledError):
                    await run_compliance_audit()

            assert any("Compliance audit error" in r.message for r in caplog.records)

    async def test_loop_sleeps_3600_seconds(self):
        """run_compliance_audit sleeps for 3600 seconds between iterations (line 27)."""
        mock_now = datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc)
        sleep_values = []

        async def mock_sleep(seconds):
            sleep_values.append(seconds)
            raise asyncio.CancelledError("Stop loop")

        with (
            patch("src.workers.compliance_audit.datetime") as mock_dt,
            patch("src.workers.compliance_audit.asyncio.sleep", mock_sleep),
        ):
            mock_dt.now.return_value = mock_now

            from src.workers.compliance_audit import run_compliance_audit

            with pytest.raises(asyncio.CancelledError):
                await run_compliance_audit()

        assert sleep_values == [3600]
