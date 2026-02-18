"""
Transactional email tests — password reset, verification, welcome, billing.
All SendGrid calls are mocked.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.services.transactional_email import (
    _send_transactional,
    send_password_reset,
    send_email_verification,
    send_welcome_email,
    send_subscription_confirmation,
    send_payment_failed,
)


def _mock_settings(api_key="SG_transactional_key", transactional_key="", from_email=""):
    settings = MagicMock()
    settings.sendgrid_api_key = api_key
    settings.sendgrid_transactional_key = transactional_key
    settings.from_email_transactional = from_email
    return settings


class TestSendTransactional:
    """Test the core _send_transactional function."""

    @patch("src.services.transactional_email.get_settings")
    async def test_no_api_key_returns_error(self, mock_settings):
        """Missing API key should return error."""
        mock_settings.return_value = _mock_settings(api_key="", transactional_key="")
        result = await _send_transactional(
            "user@example.com", "Test Subject", "<p>HTML</p>", "Text"
        )
        assert result["status"] == "error"
        assert result["message_id"] is None

    @patch("src.services.transactional_email.get_settings")
    async def test_successful_send(self, mock_settings):
        mock_settings.return_value = _mock_settings()
        mock_response = MagicMock()
        mock_response.headers = {"X-Message-Id": "tx_msg_123"}

        with patch("sendgrid.SendGridAPIClient") as mock_sg_cls:
            mock_sg = MagicMock()
            mock_sg.send.return_value = mock_response
            mock_sg_cls.return_value = mock_sg

            result = await _send_transactional(
                "user@example.com", "Test Subject", "<p>HTML</p>", "Text"
            )

        assert result["status"] == "sent"
        assert result["message_id"] == "tx_msg_123"
        assert result["error"] is None

    @patch("src.services.transactional_email.get_settings")
    async def test_prefers_transactional_key(self, mock_settings):
        """Should use sendgrid_transactional_key over general key if available."""
        mock_settings.return_value = _mock_settings(
            api_key="SG_general", transactional_key="SG_transactional"
        )
        mock_response = MagicMock()
        mock_response.headers = {"X-Message-Id": "test"}

        with patch("sendgrid.SendGridAPIClient") as mock_sg_cls:
            mock_sg = MagicMock()
            mock_sg.send.return_value = mock_response
            mock_sg_cls.return_value = mock_sg

            await _send_transactional("u@e.com", "Sub", "<p>H</p>", "T")

        mock_sg_cls.assert_called_once_with(api_key="SG_transactional")

    @patch("src.services.transactional_email.get_settings")
    async def test_exception_returns_error(self, mock_settings):
        mock_settings.return_value = _mock_settings()

        with patch("sendgrid.SendGridAPIClient") as mock_sg_cls:
            mock_sg = MagicMock()
            mock_sg.send.side_effect = Exception("Connection refused")
            mock_sg_cls.return_value = mock_sg

            result = await _send_transactional("u@e.com", "Sub", "<p>H</p>", "T")

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]


class TestPasswordReset:
    """Test password reset email."""

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_constructs_reset_url(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_password_reset("u@e.com", "tok123", "https://leadlock.org/reset")

        call_args = mock_send.call_args
        html_content = call_args[0][2]  # 3rd positional arg
        text_content = call_args[0][3]
        assert "https://leadlock.org/reset?token=tok123" in html_content
        assert "https://leadlock.org/reset?token=tok123" in text_content

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_subject_contains_reset(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_password_reset("u@e.com", "tok", "https://leadlock.org/reset")
        subject = mock_send.call_args[0][1]
        assert "Reset" in subject or "reset" in subject.lower()

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_mentions_expiry(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_password_reset("u@e.com", "tok", "https://leadlock.org/reset")
        text_content = mock_send.call_args[0][3]
        assert "1 hour" in text_content


class TestEmailVerification:
    """Test email verification email."""

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_constructs_verify_url(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_email_verification("u@e.com", "verify_tok", "https://leadlock.org/verify")

        html_content = mock_send.call_args[0][2]
        assert "https://leadlock.org/verify?token=verify_tok" in html_content

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_mentions_24h_expiry(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_email_verification("u@e.com", "t", "https://leadlock.org/verify")
        text_content = mock_send.call_args[0][3]
        assert "24 hours" in text_content


class TestWelcomeEmail:
    """Test welcome email."""

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_includes_business_name(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_welcome_email("u@e.com", "Austin HVAC")

        text_content = mock_send.call_args[0][3]
        assert "Austin HVAC" in text_content

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_includes_onboarding_steps(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_welcome_email("u@e.com", "TestCo")

        text_content = mock_send.call_args[0][3]
        assert "onboarding" in text_content.lower() or "CRM" in text_content


class TestSubscriptionConfirmation:
    """Test subscription confirmation email."""

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_includes_plan_and_amount(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_subscription_confirmation("u@e.com", "Pro", "$497")

        text_content = mock_send.call_args[0][3]
        assert "Pro" in text_content
        assert "$497" in text_content


class TestPaymentFailed:
    """Test payment failure notification."""

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_includes_business_name(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_payment_failed("u@e.com", "Austin HVAC")

        text_content = mock_send.call_args[0][3]
        assert "Austin HVAC" in text_content

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_mentions_7_day_deadline(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_payment_failed("u@e.com", "TestCo")

        text_content = mock_send.call_args[0][3]
        assert "7 days" in text_content

    @patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock)
    async def test_subject_indicates_urgency(self, mock_send):
        mock_send.return_value = {"message_id": "m1", "status": "sent", "error": None}
        await send_payment_failed("u@e.com", "TestCo")

        subject = mock_send.call_args[0][1]
        assert "Failed" in subject or "Action" in subject
