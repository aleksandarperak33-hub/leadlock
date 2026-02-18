"""
Cold email service tests — SendGrid sending with CAN-SPAM compliance.
All SendGrid calls are mocked.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.services.cold_email import (
    send_cold_email,
    CAN_SPAM_FOOTER_HTML,
    CAN_SPAM_FOOTER_TEXT,
    SENDGRID_COST_PER_EMAIL,
)


def _mock_settings(api_key="SG_test_key"):
    """Create a mock settings object."""
    settings = MagicMock()
    settings.sendgrid_api_key = api_key
    return settings


def _base_args():
    """Standard args for send_cold_email."""
    return {
        "to_email": "john@contractor.com",
        "to_name": "John Smith",
        "subject": "Quick question about your HVAC business",
        "body_html": "<p>Hi John, I noticed your business...</p>",
        "from_email": "alex@leadlock.io",
        "from_name": "Alex at LeadLock",
        "reply_to": "alex@leadlock.io",
        "unsubscribe_url": "https://leadlock.io/unsub/123",
        "company_address": "123 Main St, Austin TX 78701",
    }


class TestCanSpamFooter:
    """Test CAN-SPAM footer generation."""

    def test_html_footer_has_unsubscribe_link(self):
        footer = CAN_SPAM_FOOTER_HTML.format(
            company_name="LeadLock",
            company_address="123 Main St",
            unsubscribe_url="https://leadlock.io/unsub/1",
        )
        assert "Unsubscribe" in footer
        assert "https://leadlock.io/unsub/1" in footer

    def test_html_footer_has_company_info(self):
        footer = CAN_SPAM_FOOTER_HTML.format(
            company_name="LeadLock",
            company_address="123 Main St, Austin TX",
            unsubscribe_url="https://leadlock.io/unsub/1",
        )
        assert "LeadLock" in footer
        assert "123 Main St, Austin TX" in footer

    def test_text_footer_has_unsubscribe(self):
        footer = CAN_SPAM_FOOTER_TEXT.format(
            company_name="LeadLock",
            company_address="123 Main St",
            unsubscribe_url="https://leadlock.io/unsub/1",
        )
        assert "Unsubscribe" in footer
        assert "https://leadlock.io/unsub/1" in footer


class TestSendColdEmail:
    """Test the main send_cold_email function."""

    @patch("src.services.cold_email.get_settings")
    async def test_no_api_key_returns_error(self, mock_settings):
        """Missing API key should return error without calling SendGrid."""
        mock_settings.return_value = _mock_settings(api_key="")
        result = await send_cold_email(**_base_args())
        assert result["status"] == "error"
        assert result["message_id"] is None
        assert "not configured" in result["error"]

    @patch("src.services.cold_email.get_settings")
    async def test_successful_send(self, mock_get_settings):
        """Successful send should return message_id and cost."""
        mock_get_settings.return_value = _mock_settings()

        mock_response = MagicMock()
        mock_response.headers = {"X-Message-Id": "sg_msg_123"}

        with patch("sendgrid.SendGridAPIClient") as mock_sg_cls:
            mock_sg = MagicMock()
            mock_sg.send.return_value = mock_response
            mock_sg_cls.return_value = mock_sg

            result = await send_cold_email(**_base_args())

        assert result["status"] == "sent"
        assert result["message_id"] == "sg_msg_123"
        assert result["cost_usd"] == SENDGRID_COST_PER_EMAIL

    @patch("src.services.cold_email.get_settings")
    async def test_sendgrid_exception_returns_error(self, mock_get_settings):
        """SendGrid exception should be caught and returned as error."""
        mock_get_settings.return_value = _mock_settings()

        with patch("sendgrid.SendGridAPIClient") as mock_sg_cls:
            mock_sg = MagicMock()
            mock_sg.send.side_effect = Exception("SendGrid 403 Forbidden")
            mock_sg_cls.return_value = mock_sg

            result = await send_cold_email(**_base_args())

        assert result["status"] == "error"
        assert result["message_id"] is None
        assert result["cost_usd"] == 0.0
        assert "403" in result["error"]

    @patch("src.services.cold_email.get_settings")
    async def test_custom_args_passed(self, mock_get_settings):
        """Custom args should be included in the SendGrid message."""
        mock_get_settings.return_value = _mock_settings()

        mock_response = MagicMock()
        mock_response.headers = {"X-Message-Id": "sg_msg_456"}

        with patch("sendgrid.SendGridAPIClient") as mock_sg_cls:
            mock_sg = MagicMock()
            mock_sg.send.return_value = mock_response
            mock_sg_cls.return_value = mock_sg

            args = _base_args()
            args["custom_args"] = {"outreach_id": "abc-123", "step": "1"}
            result = await send_cold_email(**args)

        assert result["status"] == "sent"
        # Verify send was called (custom args are set on the Mail object)
        mock_sg.send.assert_called_once()

    @patch("src.services.cold_email.get_settings")
    async def test_threading_headers(self, mock_get_settings):
        """In-Reply-To and References headers should be set when provided."""
        mock_get_settings.return_value = _mock_settings()

        mock_response = MagicMock()
        mock_response.headers = {"X-Message-Id": "sg_msg_789"}

        with patch("sendgrid.SendGridAPIClient") as mock_sg_cls:
            mock_sg = MagicMock()
            mock_sg.send.return_value = mock_response
            mock_sg_cls.return_value = mock_sg

            args = _base_args()
            args["in_reply_to"] = "original-msg-id@sendgrid.net"
            args["references"] = "<original-msg-id@sendgrid.net>"
            result = await send_cold_email(**args)

        assert result["status"] == "sent"

    @patch("src.services.cold_email.get_settings")
    async def test_cost_is_correct(self, mock_get_settings):
        """Cost should be SENDGRID_COST_PER_EMAIL ($0.001)."""
        mock_get_settings.return_value = _mock_settings()

        mock_response = MagicMock()
        mock_response.headers = {"X-Message-Id": "test"}

        with patch("sendgrid.SendGridAPIClient") as mock_sg_cls:
            mock_sg = MagicMock()
            mock_sg.send.return_value = mock_response
            mock_sg_cls.return_value = mock_sg

            result = await send_cold_email(**_base_args())

        assert result["cost_usd"] == 0.001
