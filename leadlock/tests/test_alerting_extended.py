"""
Extended tests for src/utils/alerting.py - covers webhook with extra/correlation,
and the full _send_email_alert function.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _send_webhook_alert - extra and correlation_id formatting (lines 112-116)
# ---------------------------------------------------------------------------

class TestSendWebhookAlertFormatting:
    """Cover lines 112-116: correlation_id and extra in webhook content."""

    async def test_webhook_includes_correlation_id_and_extra(self):
        """Webhook content includes correlation_id and extra key-value pairs."""
        mock_settings = MagicMock()
        mock_settings.alert_webhook_url = "https://hooks.example.com/test"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            from src.utils.alerting import _send_webhook_alert

            await _send_webhook_alert(
                alert_type="test_type",
                message="Test webhook",
                correlation_id="corr-abc-123",
                extra={"lead_id": "lead-999", "phone": "+1555***"},
            )

            # Verify the post was called
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
            content = payload["content"]

            assert "corr-abc-123" in content
            assert "lead_id" in content
            assert "lead-999" in content
            assert "phone" in content


# ---------------------------------------------------------------------------
# _send_email_alert - full function (lines 134-163)
# ---------------------------------------------------------------------------

class TestSendEmailAlert:
    """Cover _send_email_alert: success path, exception path, with/without extras."""

    async def test_sends_email_with_correlation_and_extra(self):
        """Full success path with correlation_id and extra."""
        mock_settings = MagicMock()
        mock_settings.from_email_transactional = "alerts@leadlock.org"

        mock_send = AsyncMock()

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch(
                "src.services.transactional_email._send_transactional",
                mock_send,
            ),
        ):
            from src.utils.alerting import _send_email_alert

            await _send_email_alert(
                alert_type="sms_delivery_failed",
                message="SMS failed for lead X",
                correlation_id="corr-email-123",
                extra={"lead_id": "abc", "provider": "twilio"},
            )

            mock_send.assert_called_once()
            args = mock_send.call_args[0]
            # args: (to_email, subject, html, text)
            assert args[0] == "alerts@leadlock.org"
            assert "sms_delivery_failed" in args[1]
            assert "corr-email-123" in args[2]
            assert "lead_id" in args[2]
            assert "twilio" in args[2]
            assert "corr-email-123" in args[3]

    async def test_sends_email_without_correlation_or_extra(self):
        """Sends email with no correlation_id and no extra."""
        mock_settings = MagicMock()
        mock_settings.from_email_transactional = "alerts@leadlock.org"

        mock_send = AsyncMock()

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch(
                "src.services.transactional_email._send_transactional",
                mock_send,
            ),
        ):
            from src.utils.alerting import _send_email_alert

            await _send_email_alert(
                alert_type="health_check_failed",
                message="DB unreachable",
                correlation_id=None,
                extra=None,
            )

            mock_send.assert_called_once()
            args = mock_send.call_args[0]
            assert "health_check_failed" in args[1]
            assert "N/A" in args[3]

    async def test_uses_default_email_when_not_configured(self):
        """Falls back to noreply@leadlock.org when from_email_transactional is empty."""
        mock_settings = MagicMock()
        mock_settings.from_email_transactional = ""

        mock_send = AsyncMock()

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch(
                "src.services.transactional_email._send_transactional",
                mock_send,
            ),
        ):
            from src.utils.alerting import _send_email_alert

            await _send_email_alert(
                alert_type="test",
                message="Test",
                correlation_id=None,
                extra=None,
            )

            mock_send.assert_called_once()
            assert mock_send.call_args[0][0] == "noreply@leadlock.org"

    async def test_email_exception_is_swallowed(self):
        """_send_email_alert catches exceptions and does not raise (line 162-163)."""
        mock_settings = MagicMock()
        mock_settings.from_email_transactional = "alerts@leadlock.org"

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch(
                "src.services.transactional_email._send_transactional",
                AsyncMock(side_effect=Exception("SMTP down")),
            ),
        ):
            from src.utils.alerting import _send_email_alert

            # Should not raise
            await _send_email_alert(
                alert_type="test",
                message="Should not crash",
                correlation_id="corr-fail",
                extra={"key": "value"},
            )

    async def test_send_alert_calls_email_for_error_severity(self):
        """send_alert dispatches to _send_email_alert for error severity."""
        mock_webhook = AsyncMock()
        mock_email = AsyncMock()

        with (
            patch("src.utils.alerting._acquire_cooldown", return_value=True),
            patch("src.utils.logging.get_correlation_id", return_value="corr-test"),
            patch("src.utils.alerting._send_webhook_alert", mock_webhook),
            patch("src.utils.alerting._send_email_alert", mock_email),
        ):
            from src.utils.alerting import send_alert

            await send_alert(
                alert_type="test_email",
                message="Error severity",
                severity="error",
            )

            mock_email.assert_called_once_with(
                "test_email", "Error severity", "corr-test", None
            )

    async def test_send_alert_skips_email_for_warning_severity(self):
        """send_alert does NOT call _send_email_alert for warning severity."""
        mock_webhook = AsyncMock()
        mock_email = AsyncMock()

        with (
            patch("src.utils.alerting._acquire_cooldown", return_value=True),
            patch("src.utils.logging.get_correlation_id", return_value="corr-test"),
            patch("src.utils.alerting._send_webhook_alert", mock_webhook),
            patch("src.utils.alerting._send_email_alert", mock_email),
        ):
            from src.utils.alerting import send_alert

            await send_alert(
                alert_type="test_warn",
                message="Warning severity",
                severity="warning",
            )

            mock_email.assert_not_called()


# ---------------------------------------------------------------------------
# Per-type cooldown overrides
# ---------------------------------------------------------------------------

class TestCooldownOverrides:
    """Tests for per-alert-type cooldown durations."""

    def test_sms_delivery_failed_has_1_hour_cooldown(self):
        """SMS delivery failed uses 1-hour cooldown instead of default 5 minutes."""
        from src.utils.alerting import (
            _get_cooldown_seconds,
            ALERT_COOLDOWN_SECONDS,
        )

        cooldown = _get_cooldown_seconds("sms_delivery_failed")
        assert cooldown == 3600
        assert cooldown > ALERT_COOLDOWN_SECONDS

    def test_default_cooldown_for_unknown_type(self):
        """Unknown alert types use the default 5-minute cooldown."""
        from src.utils.alerting import (
            _get_cooldown_seconds,
            ALERT_COOLDOWN_SECONDS,
        )

        cooldown = _get_cooldown_seconds("some_unknown_type")
        assert cooldown == ALERT_COOLDOWN_SECONDS

    def test_health_check_failed_uses_default(self):
        """Health check alerts use the short default cooldown (infrastructure issues)."""
        from src.utils.alerting import (
            _get_cooldown_seconds,
            ALERT_COOLDOWN_SECONDS,
        )

        cooldown = _get_cooldown_seconds("health_check_failed")
        assert cooldown == ALERT_COOLDOWN_SECONDS

    def test_all_overrides_are_longer_than_default(self):
        """Every cooldown override should be longer than the default."""
        from src.utils.alerting import (
            ALERT_COOLDOWN_OVERRIDES,
            ALERT_COOLDOWN_SECONDS,
        )

        for alert_type, override in ALERT_COOLDOWN_OVERRIDES.items():
            assert override > ALERT_COOLDOWN_SECONDS, (
                f"{alert_type} override ({override}s) should be > default ({ALERT_COOLDOWN_SECONDS}s)"
            )

    async def test_acquire_cooldown_uses_override_in_redis(self):
        """_acquire_cooldown passes the per-type TTL to Redis SET NX EX."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            from src.utils.alerting import _acquire_cooldown

            result = await _acquire_cooldown("sms_delivery_failed")

            assert result is True
            mock_redis.set.assert_called_once_with(
                "leadlock:alert_cooldown:sms_delivery_failed",
                "1",
                nx=True,
                ex=3600,  # 1-hour override, not 300s default
            )

    async def test_acquire_cooldown_uses_default_for_unknown(self):
        """_acquire_cooldown uses default cooldown for types without overrides."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            from src.utils.alerting import _acquire_cooldown

            result = await _acquire_cooldown("lead_processing_failed")

            assert result is True
            mock_redis.set.assert_called_once_with(
                "leadlock:alert_cooldown:lead_processing_failed",
                "1",
                nx=True,
                ex=300,  # default 5-minute cooldown
            )
