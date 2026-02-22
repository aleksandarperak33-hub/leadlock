"""
Tests for win-back agent - generation and sending logic.
"""
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _make_prospect(**overrides):
    """Create a mock Outreach prospect for win-back testing."""
    defaults = {
        "id": uuid.uuid4(),
        "prospect_name": "Mike Johnson",
        "prospect_company": "Johnson Plumbing",
        "prospect_email": "mike@johnsonplumbing.com",
        "prospect_trade_type": "plumbing",
        "city": "Austin",
        "state_code": "TX",
        "status": "contacted",
        "last_email_sent_at": datetime.now(timezone.utc) - timedelta(days=35),
        "last_email_replied_at": None,
        "email_unsubscribed": False,
        "winback_sent_at": None,
        "winback_eligible": True,
        "enrichment_data": None,
        "total_emails_sent": 3,
        "total_cost_usd": 0.05,
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    p = MagicMock()
    for k, v in defaults.items():
        setattr(p, k, v)
    return p


# ---------------------------------------------------------------------------
# Angle selection
# ---------------------------------------------------------------------------

class TestSelectWinbackAngle:
    def test_rotates_through_angles(self):
        from src.services.winback_generation import select_winback_angle, WINBACK_ANGLES

        angles = [select_winback_angle("plumbing", i) for i in range(5)]
        assert len(set(a["name"] for a in angles)) == 5

    def test_returns_dict_with_name_and_instruction(self):
        from src.services.winback_generation import select_winback_angle

        angle = select_winback_angle("hvac", 0)
        assert "name" in angle
        assert "instruction" in angle


# ---------------------------------------------------------------------------
# Win-back email generation
# ---------------------------------------------------------------------------

class TestGenerateWinbackEmail:
    @pytest.mark.asyncio
    async def test_generates_email_on_success(self):
        from src.services.winback_generation import generate_winback_email

        ai_response = {
            "content": '{"subject": "Quick stat for Johnson Plumbing", "body_html": "<p>Hey Mike,</p>", "body_text": "Hey Mike,"}',
            "cost_usd": 0.002,
            "error": None,
        }

        angle = {"name": "industry_stat", "instruction": "ANGLE: Industry statistic."}

        with (
            patch("src.services.winback_generation.generate_response", new_callable=AsyncMock, return_value=ai_response),
            patch("src.services.winback_generation._track_agent_cost", new_callable=AsyncMock),
        ):
            result = await generate_winback_email(
                prospect_name="Mike Johnson",
                company_name="Johnson Plumbing",
                trade_type="plumbing",
                city="Austin",
                state="TX",
                angle=angle,
            )

        assert result["subject"] == "Quick stat for Johnson Plumbing"
        assert result["angle"] == "industry_stat"
        assert result["ai_cost_usd"] == 0.002
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_returns_error_on_ai_failure(self):
        from src.services.winback_generation import generate_winback_email

        ai_response = {"content": "", "cost_usd": 0.0, "error": "timeout"}
        angle = {"name": "industry_stat", "instruction": "test"}

        with patch("src.services.winback_generation.generate_response", new_callable=AsyncMock, return_value=ai_response):
            result = await generate_winback_email(
                prospect_name="Test",
                company_name="Test Co",
                trade_type="hvac",
                city="Dallas",
                state="TX",
                angle=angle,
            )

        assert result.get("error") == "timeout"

    @pytest.mark.asyncio
    async def test_returns_error_on_bad_json(self):
        from src.services.winback_generation import generate_winback_email

        ai_response = {"content": "not json at all", "cost_usd": 0.001, "error": None}
        angle = {"name": "roi_calculator", "instruction": "test"}

        with (
            patch("src.services.winback_generation.generate_response", new_callable=AsyncMock, return_value=ai_response),
            patch("src.services.winback_generation._track_agent_cost", new_callable=AsyncMock),
        ):
            result = await generate_winback_email(
                prospect_name="Test",
                company_name="Test Co",
                trade_type="hvac",
                city="Dallas",
                state="TX",
                angle=angle,
            )

        assert "error" in result


# ---------------------------------------------------------------------------
# Win-back send logic
# ---------------------------------------------------------------------------

class TestSendWinback:
    @pytest.mark.asyncio
    async def test_sends_and_records_email(self):
        from src.workers.winback_agent import _send_winback

        prospect = _make_prospect()
        config = MagicMock()
        config.from_email = "hello@leadlock.org"
        config.from_name = "LeadLock"
        config.reply_to_email = "hello@leadlock.org"
        config.company_address = "123 Main St"
        config.sender_name = "Alek"

        settings = MagicMock()
        settings.app_base_url = "https://app.leadlock.org"

        email_result = {
            "subject": "Test subject",
            "body_html": "<p>Hey</p>",
            "body_text": "Hey",
            "ai_cost_usd": 0.002,
            "angle": "industry_stat",
        }

        send_result = {"message_id": "msg123", "error": None}

        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        with (
            patch("src.workers.winback_agent.generate_winback_email", new_callable=AsyncMock, return_value=email_result),
            patch("src.workers.winback_agent.send_cold_email", new_callable=AsyncMock, return_value=send_result),
        ):
            success = await _send_winback(mock_db, config, settings, prospect, 0)

        assert success is True
        assert prospect.winback_sent_at is not None
        assert prospect.total_emails_sent == 4  # Was 3
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_generation_failure(self):
        from src.workers.winback_agent import _send_winback

        prospect = _make_prospect()
        config = MagicMock()
        config.from_email = "hello@leadlock.org"
        config.sender_name = "Alek"

        settings = MagicMock()
        settings.app_base_url = "https://app.leadlock.org"

        email_result = {
            "subject": "",
            "body_html": "",
            "body_text": "",
            "ai_cost_usd": 0.0,
            "angle": "test",
            "error": "timeout",
        }

        with patch("src.workers.winback_agent.generate_winback_email", new_callable=AsyncMock, return_value=email_result):
            success = await _send_winback(MagicMock(), config, settings, prospect, 0)

        assert success is False
