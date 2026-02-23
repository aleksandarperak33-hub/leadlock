"""
Extended tests for src/services/outreach_sms.py - generate_followup_sms_body.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGenerateFollowupSmsBody:
    def _make_prospect(self, **overrides):
        defaults = {
            "prospect_name": "John Smith",
            "prospect_company": "Acme HVAC",
            "prospect_trade_type": "HVAC",
            "city": "Austin",
            "state_code": "TX",
        }
        defaults.update(overrides)
        prospect = MagicMock()
        for key, value in defaults.items():
            setattr(prospect, key, value)
        return prospect

    async def test_ai_success_returns_generated_text(self):
        with patch(
            "src.services.outreach_sms.generate_response",
            new_callable=AsyncMock,
            return_value={"content": "  Saw your reply - want to hop on a quick call this week?  ", "error": None},
        ) as mock_ai:
            from src.services.outreach_sms import generate_followup_sms_body

            result = await generate_followup_sms_body(self._make_prospect())

        assert result == "Saw your reply - want to hop on a quick call this week?"
        mock_ai.assert_awaited_once()

    async def test_ai_empty_content_falls_back_to_template(self):
        with patch(
            "src.services.outreach_sms.generate_response",
            new_callable=AsyncMock,
            return_value={"content": "", "error": "OpenAI request failed"},
        ):
            from src.services.outreach_sms import generate_followup_sms_body

            result = await generate_followup_sms_body(self._make_prospect())

        assert "Thanks for your interest" in result
        assert "Acme HVAC" in result
        assert "15 min" in result

    async def test_ai_exception_falls_back_to_template(self):
        with patch(
            "src.services.outreach_sms.generate_response",
            new_callable=AsyncMock,
            side_effect=Exception("API down"),
        ):
            from src.services.outreach_sms import generate_followup_sms_body

            result = await generate_followup_sms_body(self._make_prospect())

        assert "Thanks for your interest" in result

    async def test_fallback_uses_prospect_name_when_no_company(self):
        with patch(
            "src.services.outreach_sms.generate_response",
            new_callable=AsyncMock,
            return_value={"content": "", "error": "OpenAI API key not configured"},
        ):
            from src.services.outreach_sms import generate_followup_sms_body

            result = await generate_followup_sms_body(self._make_prospect(prospect_company=None))

        assert "John Smith" in result

    async def test_prompt_includes_prospect_details(self):
        with patch(
            "src.services.outreach_sms.generate_response",
            new_callable=AsyncMock,
            return_value={"content": "Quick call about your leads?", "error": None},
        ) as mock_ai:
            from src.services.outreach_sms import generate_followup_sms_body

            prospect = self._make_prospect(
                prospect_trade_type="plumbing",
                prospect_company="Fix-It Plumbing",
                city="Dallas",
                state_code="TX",
            )
            await generate_followup_sms_body(prospect)

        kwargs = mock_ai.call_args.kwargs
        assert kwargs["system_prompt"].startswith("You write concise")
        prompt = kwargs["user_message"]
        assert "plumbing" in prompt
        assert "Fix-It Plumbing" in prompt
        assert "Dallas" in prompt

    async def test_prompt_handles_missing_fields(self):
        with patch(
            "src.services.outreach_sms.generate_response",
            new_callable=AsyncMock,
            return_value={"content": "Let's chat about leads.", "error": None},
        ) as mock_ai:
            from src.services.outreach_sms import generate_followup_sms_body

            prospect = self._make_prospect(
                prospect_trade_type=None,
                prospect_company=None,
                prospect_name="Jane Doe",
                city=None,
                state_code=None,
            )
            result = await generate_followup_sms_body(prospect)

        assert result == "Let's chat about leads."
        prompt = mock_ai.call_args.kwargs["user_message"]
        assert "home services" in prompt
        assert "Jane Doe" in prompt
        assert "their area" in prompt
