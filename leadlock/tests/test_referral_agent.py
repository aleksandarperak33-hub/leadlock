"""
Tests for src/workers/referral_agent.py - referral email generation + sending.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_client(client_id="abc12345-1111-2222-3333-444455556666", days_ago=10, owner_email="owner@test.com"):
    """Create a mock Client object for testing."""
    client = MagicMock()
    client.id = client_id
    client.is_active = True
    client.business_name = "Test HVAC Co"
    client.owner_email = owner_email
    client.dashboard_email = "dash@test.com"
    client.created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    client.trade_type = "HVAC"
    client.city = "Austin"
    return client


def _make_mock_db(clients=None, has_existing_request=False):
    """Create a mock async DB session."""
    db = AsyncMock()

    # Client query result
    client_result = MagicMock()
    client_result.scalars.return_value.all.return_value = clients or []

    # Existing referral request check
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = MagicMock() if has_existing_request else None

    # Return different results per call
    db.execute = AsyncMock(side_effect=[client_result, existing_result])
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    return db


class TestReferralCycleSendsEmail:
    @pytest.mark.asyncio
    async def test_sends_email_via_transactional_service(self):
        """Verify referral_cycle actually calls _send_transactional after generating email."""
        client = _make_mock_client()
        db = _make_mock_db(clients=[client])

        email_gen_result = {
            "subject": "Know someone?",
            "body_html": "<p>Hey!</p>",
            "body_text": "Hey!",
            "ai_cost_usd": 0.001,
        }
        send_result = {"message_id": "msg123", "status": "sent", "error": None}

        mock_settings = MagicMock()
        mock_settings.app_base_url = "https://app.leadlock.io"

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.referral_agent.async_session_factory", return_value=ctx),
            patch("src.services.referral_generation.generate_referral_email", new_callable=AsyncMock, return_value=email_gen_result),
            patch("src.services.referral_generation.generate_referral_code", return_value="ref-abc12345-xyz"),
            patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock, return_value=send_result) as mock_send,
            patch("src.config.get_settings", return_value=mock_settings),
        ):
            from src.workers.referral_agent import referral_cycle
            await referral_cycle()

        # Verify _send_transactional was called with the generated email content
        mock_send.assert_awaited_once_with(
            to_email="owner@test.com",
            subject="Know someone?",
            html_content="<p>Hey!</p>",
            text_content="Hey!",
        )

        # Verify ReferralRequest was added (db.add called for link + request = 2 times)
        assert db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_does_not_record_sent_on_send_failure(self):
        """If email send fails, do NOT record status='sent'."""
        client = _make_mock_client()
        db = _make_mock_db(clients=[client])

        email_gen_result = {
            "subject": "Know someone?",
            "body_html": "<p>Hey!</p>",
            "body_text": "Hey!",
            "ai_cost_usd": 0.001,
        }
        send_result = {"message_id": None, "status": "error", "error": "SendGrid down"}

        mock_settings = MagicMock()
        mock_settings.app_base_url = "https://app.leadlock.io"

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.referral_agent.async_session_factory", return_value=ctx),
            patch("src.services.referral_generation.generate_referral_email", new_callable=AsyncMock, return_value=email_gen_result),
            patch("src.services.referral_generation.generate_referral_code", return_value="ref-abc12345-xyz"),
            patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock, return_value=send_result),
            patch("src.config.get_settings", return_value=mock_settings),
        ):
            from src.workers.referral_agent import referral_cycle
            await referral_cycle()

        # Only the ReferralLink should be added, NOT the ReferralRequest
        assert db.add.call_count == 1  # Only the link, no request recorded

    @pytest.mark.asyncio
    async def test_skips_client_without_email(self):
        """Client with no owner_email and no dashboard_email is skipped."""
        client = _make_mock_client(owner_email=None)
        client.dashboard_email = None
        db = _make_mock_db(clients=[client])

        email_gen_result = {
            "subject": "Know someone?",
            "body_html": "<p>Hey!</p>",
            "body_text": "Hey!",
            "ai_cost_usd": 0.001,
        }

        mock_settings = MagicMock()
        mock_settings.app_base_url = "https://app.leadlock.io"

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.referral_agent.async_session_factory", return_value=ctx),
            patch("src.services.referral_generation.generate_referral_email", new_callable=AsyncMock, return_value=email_gen_result),
            patch("src.services.referral_generation.generate_referral_code", return_value="ref-abc12345-xyz"),
            patch("src.services.transactional_email._send_transactional", new_callable=AsyncMock) as mock_send,
            patch("src.config.get_settings", return_value=mock_settings),
        ):
            from src.workers.referral_agent import referral_cycle
            await referral_cycle()

        mock_send.assert_not_awaited()
