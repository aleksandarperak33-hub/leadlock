"""
Tests for channel script generation service.
"""
import pytest
from unittest.mock import AsyncMock, patch


class TestGenerateLinkedinScript:
    @pytest.mark.asyncio
    async def test_generates_linkedin_dm(self):
        from src.services.channel_script_generation import generate_linkedin_script

        ai_response = {
            "content": '{"connection_request": "Hey Mike, fellow contractor here.", "followup_dm": "Wanted to share something about lead response."}',
            "cost_usd": 0.002,
            "error": None,
        }

        with patch("src.services.channel_script_generation.generate_response", new_callable=AsyncMock, return_value=ai_response):
            result = await generate_linkedin_script(
                prospect_name="Mike Johnson",
                company_name="Johnson Plumbing",
                trade_type="plumbing",
                city="Austin",
                state="TX",
            )

        assert result["channel"] == "linkedin_dm"
        assert "CONNECTION REQUEST" in result["script_text"]
        assert "FOLLOW-UP DM" in result["script_text"]

    @pytest.mark.asyncio
    async def test_returns_error_on_failure(self):
        from src.services.channel_script_generation import generate_linkedin_script

        ai_response = {"content": "", "cost_usd": 0.0, "error": "timeout"}

        with patch("src.services.channel_script_generation.generate_response", new_callable=AsyncMock, return_value=ai_response):
            result = await generate_linkedin_script(
                prospect_name="Test", company_name="Co",
                trade_type="hvac", city="Dallas", state="TX",
            )

        assert "error" in result


class TestGenerateColdCallScript:
    @pytest.mark.asyncio
    async def test_generates_call_script(self):
        from src.services.channel_script_generation import generate_cold_call_script

        ai_response = {
            "content": '{"opening": "Hi Mike", "value_prop": "78% stat", "discovery_questions": ["Q1", "Q2", "Q3"], "objections": [{"objection": "Too expensive", "response": "It pays for itself"}], "close": "Can we grab 15 min?"}',
            "cost_usd": 0.003,
            "error": None,
        }

        with patch("src.services.channel_script_generation.generate_response", new_callable=AsyncMock, return_value=ai_response):
            result = await generate_cold_call_script(
                prospect_name="Mike", company_name="Mike Co",
                trade_type="plumbing", city="Austin", state="TX",
            )

        assert result["channel"] == "cold_call"
        assert "OPENING" in result["script_text"]
        assert "OBJECTION HANDLING" in result["script_text"]
        assert "CLOSE" in result["script_text"]


class TestGenerateFacebookPost:
    @pytest.mark.asyncio
    async def test_generates_fb_post(self):
        from src.services.channel_script_generation import generate_facebook_post

        ai_response = {
            "content": '{"post_text": "Anyone else notice slow lead response in their area?"}',
            "cost_usd": 0.001,
            "error": None,
        }

        with patch("src.services.channel_script_generation.generate_response", new_callable=AsyncMock, return_value=ai_response):
            result = await generate_facebook_post(trade_type="plumbing", city="Austin")

        assert result["channel"] == "facebook_group"
        assert "slow lead response" in result["script_text"]


class TestBuildExtraContext:
    def test_empty_on_none(self):
        from src.services.channel_script_generation import _build_extra_context
        assert _build_extra_context(None) == ""

    def test_includes_website_summary(self):
        from src.services.channel_script_generation import _build_extra_context
        result = _build_extra_context({"website_summary": "Full service plumbing company"})
        assert "Full service plumbing" in result

    def test_includes_title(self):
        from src.services.channel_script_generation import _build_extra_context
        result = _build_extra_context({"decision_maker_title": "Owner"})
        assert "Owner" in result
