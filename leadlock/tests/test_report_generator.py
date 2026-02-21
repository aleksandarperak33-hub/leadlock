"""
Tests for src/workers/report_generator.py - weekly report generation worker.

Covers:
- run_report_generator loop (start, error handling, sleep)
- generate_weekly_reports (Monday 8am gate, client iteration, metrics logging, email dispatch)
- _send_report_email (SendGrid integration, missing API key, send failure)
- _render_report_html (HTML rendering with all metric fields)
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.workers.report_generator import (
    _render_report_html,
    _send_report_email,
    generate_weekly_reports,
    run_report_generator,
)
from src.models.client import Client
from src.schemas.api_responses import DashboardMetrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(
    business_name: str = "Acme HVAC",
    owner_email: str | None = "owner@acme.com",
    is_active: bool = True,
) -> Client:
    """Create a minimal Client instance for testing."""
    client = Client(
        id=uuid.uuid4(),
        business_name=business_name,
        trade_type="hvac",
        is_active=is_active,
        owner_email=owner_email,
        config={},
    )
    return client


def _make_metrics(
    total_leads: int = 20,
    total_booked: int = 8,
    conversion_rate: float = 0.4,
    avg_response_time_ms: int = 5000,
    leads_under_60s_pct: float = 95.0,
) -> DashboardMetrics:
    """Create a DashboardMetrics instance with sensible defaults."""
    return DashboardMetrics(
        total_leads=total_leads,
        total_booked=total_booked,
        conversion_rate=conversion_rate,
        avg_response_time_ms=avg_response_time_ms,
        leads_under_60s=int(total_leads * leads_under_60s_pct / 100),
        leads_under_60s_pct=leads_under_60s_pct,
        total_messages=40,
        total_ai_cost=0.50,
        total_sms_cost=0.30,
        leads_by_source={},
        leads_by_state={},
        leads_by_day=[],
        response_time_distribution=[],
        conversion_by_source={},
    )


# ---------------------------------------------------------------------------
# _render_report_html
# ---------------------------------------------------------------------------

class TestRenderReportHtml:
    """Tests for _render_report_html."""

    def test_contains_business_name(self):
        client = _make_client(business_name="Cool Plumbing")
        metrics = _make_metrics()
        html = _render_report_html(client, metrics)
        assert "Cool Plumbing" in html

    def test_contains_total_leads(self):
        client = _make_client()
        metrics = _make_metrics(total_leads=42)
        html = _render_report_html(client, metrics)
        assert "42" in html

    def test_contains_total_booked(self):
        client = _make_client()
        metrics = _make_metrics(total_booked=15)
        html = _render_report_html(client, metrics)
        assert "15" in html

    def test_contains_conversion_rate(self):
        client = _make_client()
        metrics = _make_metrics(conversion_rate=0.35)
        html = _render_report_html(client, metrics)
        assert "35.0%" in html

    def test_contains_avg_response_time(self):
        client = _make_client()
        metrics = _make_metrics(avg_response_time_ms=8500)
        html = _render_report_html(client, metrics)
        # 8500 / 1000 = 8.5
        assert "8.5s" in html

    def test_contains_under_60s_pct(self):
        client = _make_client()
        metrics = _make_metrics(leads_under_60s_pct=92.0)
        html = _render_report_html(client, metrics)
        assert "92%" in html

    def test_contains_leadlock_branding(self):
        client = _make_client()
        metrics = _make_metrics()
        html = _render_report_html(client, metrics)
        assert "LeadLock Weekly Report" in html
        assert "Powered by LeadLock AI" in html

    def test_returns_string(self):
        client = _make_client()
        metrics = _make_metrics()
        result = _render_report_html(client, metrics)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _send_report_email
# ---------------------------------------------------------------------------

class TestSendReportEmail:
    """Tests for _send_report_email."""

    async def test_returns_false_when_sendgrid_key_missing(self):
        """No SendGrid key configured -- should log warning and return False."""
        client = _make_client()
        metrics = _make_metrics()

        mock_settings = MagicMock()
        mock_settings.sendgrid_api_key = ""

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await _send_report_email(client, metrics)

        assert result is False

    async def test_returns_true_on_successful_send(self):
        """Happy path -- SendGrid key present, send succeeds."""
        client = _make_client()
        metrics = _make_metrics()

        mock_settings = MagicMock()
        mock_settings.sendgrid_api_key = "SG.test_key"
        mock_settings.sendgrid_from_email = "reports@leadlock.io"
        mock_settings.sendgrid_from_name = "LeadLock"

        mock_sg_instance = MagicMock()
        mock_sg_instance.send = MagicMock(return_value=MagicMock(status_code=202))
        mock_sg_class = MagicMock(return_value=mock_sg_instance)

        mock_mail_class = MagicMock()

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch.dict("sys.modules", {
                "sendgrid": MagicMock(SendGridAPIClient=mock_sg_class),
                "sendgrid.helpers": MagicMock(),
                "sendgrid.helpers.mail": MagicMock(Mail=mock_mail_class),
            }),
        ):
            result = await _send_report_email(client, metrics)

        assert result is True

    async def test_returns_false_on_send_exception(self):
        """SendGrid send raises -- should catch, log error, return False."""
        client = _make_client()
        metrics = _make_metrics()

        mock_settings = MagicMock()
        mock_settings.sendgrid_api_key = "SG.test_key"
        mock_settings.sendgrid_from_email = "reports@leadlock.io"
        mock_settings.sendgrid_from_name = "LeadLock"

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch.dict("sys.modules", {
                "sendgrid": MagicMock(
                    SendGridAPIClient=MagicMock(side_effect=Exception("API down"))
                ),
                "sendgrid.helpers": MagicMock(),
                "sendgrid.helpers.mail": MagicMock(Mail=MagicMock()),
            }),
        ):
            result = await _send_report_email(client, metrics)

        assert result is False

    async def test_logs_warning_when_no_sendgrid_key(self, caplog):
        """Verify the warning log message when SendGrid is not configured."""
        client = _make_client(business_name="Test Biz")
        metrics = _make_metrics()

        mock_settings = MagicMock()
        mock_settings.sendgrid_api_key = ""

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            caplog.at_level(logging.WARNING),
        ):
            await _send_report_email(client, metrics)

        assert "SendGrid not configured" in caplog.text
        assert "Test Biz" in caplog.text

    async def test_logs_info_on_successful_send(self, caplog):
        """Verify the info log on successful email delivery."""
        client = _make_client(owner_email="test@example.com")
        metrics = _make_metrics()

        mock_settings = MagicMock()
        mock_settings.sendgrid_api_key = "SG.test_key"
        mock_settings.sendgrid_from_email = "reports@leadlock.io"
        mock_settings.sendgrid_from_name = "LeadLock"

        mock_sg_instance = MagicMock()
        mock_sg_instance.send = MagicMock(return_value=MagicMock(status_code=202))
        mock_sg_class = MagicMock(return_value=mock_sg_instance)
        mock_mail_class = MagicMock()

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch.dict("sys.modules", {
                "sendgrid": MagicMock(SendGridAPIClient=mock_sg_class),
                "sendgrid.helpers": MagicMock(),
                "sendgrid.helpers.mail": MagicMock(Mail=mock_mail_class),
            }),
            caplog.at_level(logging.INFO),
        ):
            await _send_report_email(client, metrics)

        assert "Weekly report emailed to" in caplog.text

    async def test_logs_error_on_send_failure(self, caplog):
        """Verify the error log when SendGrid send fails."""
        client = _make_client()
        metrics = _make_metrics()

        mock_settings = MagicMock()
        mock_settings.sendgrid_api_key = "SG.test_key"
        mock_settings.sendgrid_from_email = "reports@leadlock.io"
        mock_settings.sendgrid_from_name = "LeadLock"

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch.dict("sys.modules", {
                "sendgrid": MagicMock(
                    SendGridAPIClient=MagicMock(side_effect=Exception("Boom"))
                ),
                "sendgrid.helpers": MagicMock(),
                "sendgrid.helpers.mail": MagicMock(Mail=MagicMock()),
            }),
            caplog.at_level(logging.ERROR),
        ):
            await _send_report_email(client, metrics)

        assert "SendGrid email failed" in caplog.text


# ---------------------------------------------------------------------------
# generate_weekly_reports
# ---------------------------------------------------------------------------

class TestGenerateWeeklyReports:
    """Tests for generate_weekly_reports."""

    async def test_skips_when_not_monday(self):
        """Should return early if the current day is not Monday."""
        # Tuesday at 8am UTC
        fake_now = datetime(2026, 2, 17, 8, 0, 0, tzinfo=timezone.utc)  # Tuesday
        with patch("src.workers.report_generator.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            # If it actually tried to query, it would fail because we didn't mock the DB
            await generate_weekly_reports()

    async def test_skips_when_not_8am(self):
        """Should return early if the hour is not 8."""
        # Monday at 10am UTC
        fake_now = datetime(2026, 2, 16, 10, 0, 0, tzinfo=timezone.utc)  # Monday
        with patch("src.workers.report_generator.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await generate_weekly_reports()

    async def test_processes_active_clients_on_monday_8am(self):
        """On Monday 8am, queries active clients and generates reports."""
        fake_now = datetime(2026, 2, 16, 8, 0, 0, tzinfo=timezone.utc)  # Monday 8am
        client = _make_client(owner_email=None)
        metrics = _make_metrics()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [client]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.report_generator.datetime") as mock_dt,
            patch(
                "src.workers.report_generator.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "src.workers.report_generator.get_dashboard_metrics",
                new_callable=AsyncMock,
                return_value=metrics,
            ),
        ):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await generate_weekly_reports()

        # Metrics were fetched for the client
        # No email because owner_email is None

    async def test_sends_email_when_owner_email_present(self):
        """When a client has owner_email, _send_report_email is called."""
        fake_now = datetime(2026, 2, 16, 8, 0, 0, tzinfo=timezone.utc)
        client = _make_client(owner_email="boss@acme.com")
        metrics = _make_metrics()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [client]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.report_generator.datetime") as mock_dt,
            patch(
                "src.workers.report_generator.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "src.workers.report_generator.get_dashboard_metrics",
                new_callable=AsyncMock,
                return_value=metrics,
            ),
            patch(
                "src.workers.report_generator._send_report_email",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_send,
        ):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await generate_weekly_reports()

        mock_send.assert_called_once_with(client, metrics)

    async def test_does_not_send_email_when_owner_email_missing(self):
        """When owner_email is None, _send_report_email is NOT called."""
        fake_now = datetime(2026, 2, 16, 8, 0, 0, tzinfo=timezone.utc)
        client = _make_client(owner_email=None)
        metrics = _make_metrics()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [client]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.report_generator.datetime") as mock_dt,
            patch(
                "src.workers.report_generator.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "src.workers.report_generator.get_dashboard_metrics",
                new_callable=AsyncMock,
                return_value=metrics,
            ),
            patch(
                "src.workers.report_generator._send_report_email",
                new_callable=AsyncMock,
            ) as mock_send,
        ):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await generate_weekly_reports()

        mock_send.assert_not_called()

    async def test_continues_on_per_client_error(self, caplog):
        """If metrics retrieval fails for one client, other clients still proceed."""
        fake_now = datetime(2026, 2, 16, 8, 0, 0, tzinfo=timezone.utc)
        client_ok = _make_client(business_name="Good Client", owner_email=None)
        client_bad = _make_client(business_name="Bad Client", owner_email=None)
        metrics = _make_metrics()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [client_bad, client_ok]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        async def metrics_side_effect(db, client_id, period):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB timeout")
            return metrics

        with (
            patch("src.workers.report_generator.datetime") as mock_dt,
            patch(
                "src.workers.report_generator.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "src.workers.report_generator.get_dashboard_metrics",
                side_effect=metrics_side_effect,
            ),
            caplog.at_level(logging.ERROR),
        ):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await generate_weekly_reports()

        # Error logged for bad client
        assert "Report failed for Bad Client" in caplog.text
        # But good client was still processed (metrics called twice)
        assert call_count == 2

    async def test_logs_report_metrics(self, caplog):
        """Verify INFO log with metrics details for each client."""
        fake_now = datetime(2026, 2, 16, 8, 0, 0, tzinfo=timezone.utc)
        client = _make_client(business_name="Log Test Biz", owner_email=None)
        metrics = _make_metrics(total_leads=50, total_booked=10, conversion_rate=0.2)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [client]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.report_generator.datetime") as mock_dt,
            patch(
                "src.workers.report_generator.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "src.workers.report_generator.get_dashboard_metrics",
                new_callable=AsyncMock,
                return_value=metrics,
            ),
            caplog.at_level(logging.INFO),
        ):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await generate_weekly_reports()

        assert "Log Test Biz" in caplog.text
        assert "50 leads" in caplog.text
        assert "10 booked" in caplog.text
        assert "20.0% conversion" in caplog.text

    async def test_handles_no_active_clients(self):
        """When no active clients exist, should complete without error."""
        fake_now = datetime(2026, 2, 16, 8, 0, 0, tzinfo=timezone.utc)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.report_generator.datetime") as mock_dt,
            patch(
                "src.workers.report_generator.async_session_factory",
                return_value=mock_session_ctx,
            ),
        ):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await generate_weekly_reports()  # Should not raise

    async def test_multiple_clients_all_processed(self):
        """All active clients get their metrics fetched."""
        fake_now = datetime(2026, 2, 16, 8, 0, 0, tzinfo=timezone.utc)
        clients = [
            _make_client(business_name=f"Client {i}", owner_email=None)
            for i in range(3)
        ]
        metrics = _make_metrics()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = clients
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.report_generator.datetime") as mock_dt,
            patch(
                "src.workers.report_generator.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch(
                "src.workers.report_generator.get_dashboard_metrics",
                new_callable=AsyncMock,
                return_value=metrics,
            ) as mock_get_metrics,
        ):
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await generate_weekly_reports()

        assert mock_get_metrics.call_count == 3


# ---------------------------------------------------------------------------
# run_report_generator
# ---------------------------------------------------------------------------

class TestRunReportGenerator:
    """Tests for run_report_generator."""

    async def test_calls_generate_and_sleeps(self):
        """The loop calls generate_weekly_reports then sleeps."""
        call_count = 0

        async def fake_generate():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt("stop test loop")

        with (
            patch(
                "src.workers.report_generator.generate_weekly_reports",
                side_effect=fake_generate,
            ),
            patch("src.workers.report_generator.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            # The second call raises KeyboardInterrupt which propagates out
            with pytest.raises(KeyboardInterrupt):
                await run_report_generator()

        # First iteration completed, sleep was called at least once
        mock_sleep.assert_called_with(3600)

    async def test_logs_error_and_continues(self, caplog):
        """When generate_weekly_reports raises, error is logged and loop continues."""
        call_count = 0

        async def fake_generate():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB connection lost")
            # Second call: break the loop
            raise KeyboardInterrupt("stop")

        with (
            patch(
                "src.workers.report_generator.generate_weekly_reports",
                side_effect=fake_generate,
            ),
            patch("src.workers.report_generator.asyncio.sleep", new_callable=AsyncMock),
            caplog.at_level(logging.ERROR),
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_report_generator()

        assert "Report generation error" in caplog.text
        assert "DB connection lost" in caplog.text
        # Loop continued past the first error
        assert call_count == 2

    async def test_logs_startup_message(self, caplog):
        """Verify the INFO 'Report generator started' log on startup."""
        async def fake_generate():
            raise KeyboardInterrupt("stop")

        with (
            patch(
                "src.workers.report_generator.generate_weekly_reports",
                side_effect=fake_generate,
            ),
            patch("src.workers.report_generator.asyncio.sleep", new_callable=AsyncMock),
            caplog.at_level(logging.INFO),
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_report_generator()

        assert "Report generator started" in caplog.text
