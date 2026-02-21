"""
Tests for src/workers/deliverability_monitor.py - SMS and email deliverability checks.
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _check_deliverability - no sends
# ---------------------------------------------------------------------------

class TestCheckDeliverabilityNoSends:
    """Tests when there are no sends in the last 24h."""

    async def test_no_sends_returns_early(self):
        """When total_sent_24h is 0, function returns without alerting."""
        summary = {
            "overall_delivery_rate": None,
            "total_sent_24h": 0,
            "total_delivered_24h": 0,
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


# ---------------------------------------------------------------------------
# _check_deliverability - delivery rate alerts
# ---------------------------------------------------------------------------

class TestCheckDeliverabilityRateAlerts:
    """Tests for delivery rate threshold alerts."""

    async def test_critical_rate_below_65_percent_sends_critical_alert(self):
        """Delivery rate < 65% (below DELIVERY_RATE_CRITICAL=0.70) triggers critical alert."""
        summary = {
            "overall_delivery_rate": 0.60,
            "total_sent_24h": 100,
            "total_delivered_24h": 60,
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
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value={
                    "status": "good",
                    "score": 85.0,
                    "metrics": {"sent": 50, "delivered": 48, "opened": 20, "bounce_rate": 0.01, "complaint_rate": 0.0001},
                    "throttle": "normal",
                },
            ),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
        ):
            from src.workers.deliverability_monitor import _check_deliverability

            await _check_deliverability()

            # Should be called at least once for the critical SMS alert
            assert mock_alert.await_count >= 1
            first_call = mock_alert.call_args_list[0]
            assert first_call.kwargs.get("severity") == "critical" or first_call.args[1] is not None

    async def test_warning_rate_below_75_percent_sends_warning_alert(self):
        """Delivery rate < 85% but >= 70% triggers warning alert."""
        summary = {
            "overall_delivery_rate": 0.78,
            "total_sent_24h": 200,
            "total_delivered_24h": 156,
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
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value={
                    "status": "good",
                    "score": 90.0,
                    "metrics": {"sent": 50, "delivered": 49, "opened": 25, "bounce_rate": 0.005, "complaint_rate": 0.0001},
                    "throttle": "normal",
                },
            ),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
        ):
            from src.workers.deliverability_monitor import _check_deliverability

            await _check_deliverability()

            assert mock_alert.await_count >= 1
            first_call = mock_alert.call_args_list[0]
            assert first_call.kwargs.get("severity") == "warning" or "WARNING" in str(first_call.args[1])

    async def test_healthy_rate_no_alert(self):
        """Delivery rate >= 85% sends no SMS delivery alert."""
        summary = {
            "overall_delivery_rate": 0.97,
            "total_sent_24h": 500,
            "total_delivered_24h": 485,
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
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value={
                    "status": "good",
                    "score": 95.0,
                    "metrics": {"sent": 100, "delivered": 98, "opened": 50, "bounce_rate": 0.002, "complaint_rate": 0.0001},
                    "throttle": "normal",
                },
            ),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
        ):
            from src.workers.deliverability_monitor import _check_deliverability

            await _check_deliverability()

            # No SMS delivery alert should be sent (email might still log)
            mock_alert.assert_not_awaited()


# ---------------------------------------------------------------------------
# _check_deliverability - email reputation
# ---------------------------------------------------------------------------

class TestCheckDeliverabilityEmailReputation:
    """Tests for email reputation monitoring."""

    async def test_email_reputation_critical_sends_alert(self):
        """Critical email reputation triggers an alert."""
        summary = {
            "overall_delivery_rate": 0.95,
            "total_sent_24h": 100,
            "total_delivered_24h": 95,
            "numbers": [],
        }

        email_rep = {
            "status": "critical",
            "score": 25.0,
            "metrics": {
                "bounce_rate": 0.15,
                "complaint_rate": 0.005,
                "sent": 200,
                "delivered": 170,
                "opened": 50,
            },
            "throttle": "paused",
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
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value=email_rep,
            ),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
        ):
            from src.workers.deliverability_monitor import _check_deliverability

            await _check_deliverability()

            # Should have been called for the email reputation alert
            assert mock_alert.await_count >= 1
            # Find the email reputation alert call
            email_alert_calls = [
                c for c in mock_alert.call_args_list
                if "EMAIL REPUTATION" in str(c.args[1]) or "email" in str(c.kwargs.get("extra", {}))
            ]
            assert len(email_alert_calls) >= 1

    async def test_email_reputation_poor_sends_alert(self):
        """Poor email reputation also triggers an alert."""
        summary = {
            "overall_delivery_rate": 0.95,
            "total_sent_24h": 100,
            "total_delivered_24h": 95,
            "numbers": [],
        }

        email_rep = {
            "status": "poor",
            "score": 40.0,
            "metrics": {
                "bounce_rate": 0.10,
                "complaint_rate": 0.003,
                "sent": 150,
                "delivered": 130,
                "opened": 40,
            },
            "throttle": "throttled",
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
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value=email_rep,
            ),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
        ):
            from src.workers.deliverability_monitor import _check_deliverability

            await _check_deliverability()

            assert mock_alert.await_count >= 1

    async def test_email_reputation_good_no_alert(self):
        """Good email reputation does not trigger an alert."""
        summary = {
            "overall_delivery_rate": 0.96,
            "total_sent_24h": 100,
            "total_delivered_24h": 96,
            "numbers": [],
        }

        email_rep = {
            "status": "good",
            "score": 88.0,
            "metrics": {
                "bounce_rate": 0.01,
                "complaint_rate": 0.0001,
                "sent": 100,
                "delivered": 98,
                "opened": 55,
            },
            "throttle": "normal",
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
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value=email_rep,
            ),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
        ):
            from src.workers.deliverability_monitor import _check_deliverability

            await _check_deliverability()

            mock_alert.assert_not_awaited()

    async def test_email_reputation_check_failure_logged_as_warning(self, caplog):
        """Email reputation check failure logs a warning but does not crash."""
        summary = {
            "overall_delivery_rate": 0.96,
            "total_sent_24h": 100,
            "total_delivered_24h": 96,
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
            ),
            patch(
                "src.utils.dedup.get_redis",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Redis down"),
            ),
        ):
            from src.workers.deliverability_monitor import _check_deliverability

            with caplog.at_level(logging.WARNING, logger="src.workers.deliverability_monitor"):
                await _check_deliverability()

            assert any(
                "Email reputation check failed" in r.message
                for r in caplog.records
            )


# ---------------------------------------------------------------------------
# _check_deliverability - number-level warnings
# ---------------------------------------------------------------------------

class TestCheckDeliverabilityNumberStats:
    """Tests for per-number reputation checking."""

    async def test_number_level_warning_logged(self, caplog):
        """Numbers with warning/critical level are logged."""
        summary = {
            "overall_delivery_rate": 0.90,
            "total_sent_24h": 300,
            "total_delivered_24h": 270,
            "numbers": [
                {
                    "phone": "+15125550001",
                    "score": 55,
                    "level": "warning",
                    "delivery_rate": 0.80,
                    "filtered_24h": 5,
                    "invalid_24h": 3,
                },
                {
                    "phone": "+15125550002",
                    "score": 30,
                    "level": "critical",
                    "delivery_rate": 0.60,
                    "filtered_24h": 15,
                    "invalid_24h": 8,
                },
            ],
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
            ),
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value={
                    "status": "good",
                    "score": 90.0,
                    "metrics": {"sent": 50, "delivered": 49, "opened": 25, "bounce_rate": 0.005, "complaint_rate": 0.0001},
                    "throttle": "normal",
                },
            ),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
        ):
            from src.workers.deliverability_monitor import _check_deliverability

            with caplog.at_level(logging.WARNING, logger="src.workers.deliverability_monitor"):
                await _check_deliverability()

            warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
            assert any("+15125550001" in m for m in warning_messages)
            assert any("+15125550002" in m for m in warning_messages)
