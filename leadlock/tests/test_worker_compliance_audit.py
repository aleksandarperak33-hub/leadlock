"""
Tests for src/workers/compliance_audit.py — periodic compliance checks.
"""
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
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
# audit_compliance — consent checks
# ---------------------------------------------------------------------------

class TestAuditCompliance:
    """Tests for audit_compliance function."""

    async def test_counts_leads_without_consent(self, caplog):
        """Logs warning when leads exist without consent records."""
        # First execute call: no-consent count = 5
        # Second execute call: expired-consent count = 0
        no_consent_result = MagicMock()
        no_consent_result.scalar.return_value = 5

        expired_result = MagicMock()
        expired_result.scalar.return_value = 0

        call_index = 0

        async def mock_execute(query):
            nonlocal call_index
            results = [no_consent_result, expired_result]
            result = results[call_index]
            call_index += 1
            return result

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            yield db

        with patch(
            "src.workers.compliance_audit.async_session_factory",
            side_effect=session_factory,
        ):
            from src.workers.compliance_audit import audit_compliance

            with caplog.at_level(logging.WARNING, logger="src.workers.compliance_audit"):
                await audit_compliance()

            assert any(
                "5 leads without consent" in r.message
                for r in caplog.records
            )

    async def test_counts_expired_consent_records(self, caplog):
        """Logs warning when expired consent records are still active."""
        no_consent_result = MagicMock()
        no_consent_result.scalar.return_value = 0

        expired_result = MagicMock()
        expired_result.scalar.return_value = 3

        call_index = 0

        async def mock_execute(query):
            nonlocal call_index
            results = [no_consent_result, expired_result]
            result = results[call_index]
            call_index += 1
            return result

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            yield db

        with patch(
            "src.workers.compliance_audit.async_session_factory",
            side_effect=session_factory,
        ):
            from src.workers.compliance_audit import audit_compliance

            with caplog.at_level(logging.WARNING, logger="src.workers.compliance_audit"):
                await audit_compliance()

            assert any(
                "3 expired consent records" in r.message
                for r in caplog.records
            )

    async def test_no_warnings_when_clean(self, caplog):
        """No warnings logged when all leads have valid consent."""
        no_consent_result = MagicMock()
        no_consent_result.scalar.return_value = 0

        expired_result = MagicMock()
        expired_result.scalar.return_value = 0

        call_index = 0

        async def mock_execute(query):
            nonlocal call_index
            results = [no_consent_result, expired_result]
            result = results[call_index]
            call_index += 1
            return result

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            yield db

        with patch(
            "src.workers.compliance_audit.async_session_factory",
            side_effect=session_factory,
        ):
            from src.workers.compliance_audit import audit_compliance

            with caplog.at_level(logging.WARNING, logger="src.workers.compliance_audit"):
                await audit_compliance()

            warning_records = [
                r for r in caplog.records
                if r.levelno >= logging.WARNING
                and "COMPLIANCE AUDIT" in r.message
            ]
            assert len(warning_records) == 0

    async def test_both_violations_logged(self, caplog):
        """Both no-consent and expired-consent violations are logged."""
        no_consent_result = MagicMock()
        no_consent_result.scalar.return_value = 10

        expired_result = MagicMock()
        expired_result.scalar.return_value = 7

        call_index = 0

        async def mock_execute(query):
            nonlocal call_index
            results = [no_consent_result, expired_result]
            result = results[call_index]
            call_index += 1
            return result

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            yield db

        with patch(
            "src.workers.compliance_audit.async_session_factory",
            side_effect=session_factory,
        ):
            from src.workers.compliance_audit import audit_compliance

            with caplog.at_level(logging.WARNING, logger="src.workers.compliance_audit"):
                await audit_compliance()

            messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
            assert any("10 leads without consent" in m for m in messages)
            assert any("7 expired consent records" in m for m in messages)
