"""
Extended tests for src/services/outreach_sms.py — covers generate_followup_sms_body
(lines 221-249): AI success path and fallback template.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# generate_followup_sms_body — AI success (lines 221-244)
# ---------------------------------------------------------------------------

class TestGenerateFollowupSmsBody:
    """Cover generate_followup_sms_body AI generation and fallback."""

    def _make_prospect(self, **overrides):
        """Build a mock Outreach prospect."""
        defaults = {
            "prospect_name": "John Smith",
            "prospect_company": "Acme HVAC",
            "prospect_trade_type": "HVAC",
            "city": "Austin",
            "state_code": "TX",
        }
        defaults.update(overrides)
        prospect = MagicMock()
        for k, v in defaults.items():
            setattr(prospect, k, v)
        return prospect

    async def test_ai_success_returns_generated_text(self):
        """When AI call succeeds, returns the generated SMS body (lines 223-244)."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.anthropic_model_fast = "claude-haiku"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="  Saw your reply — want to hop on a quick call this week?  ")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch("src.services.outreach_sms.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            from src.services.outreach_sms import generate_followup_sms_body

            prospect = self._make_prospect()
            result = await generate_followup_sms_body(prospect)

            assert result == "Saw your reply — want to hop on a quick call this week?"
            mock_client.messages.create.assert_called_once()

            # Verify model used
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs["model"] == "claude-haiku"
            assert call_kwargs["max_tokens"] == 100

    async def test_ai_failure_falls_back_to_template(self):
        """When AI call raises, uses fallback template (lines 246-253)."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.anthropic_model_fast = "claude-haiku"

        with (
            patch("src.services.outreach_sms.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", side_effect=Exception("API down")),
        ):
            from src.services.outreach_sms import generate_followup_sms_body

            prospect = self._make_prospect()
            result = await generate_followup_sms_body(prospect)

            assert "Thanks for your interest" in result
            assert "Acme HVAC" in result
            assert "15 min" in result

    async def test_fallback_uses_prospect_name_when_no_company(self):
        """Fallback template uses prospect_name when company is None (line 248)."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.anthropic_model_fast = "claude-haiku"

        with (
            patch("src.services.outreach_sms.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", side_effect=Exception("API error")),
        ):
            from src.services.outreach_sms import generate_followup_sms_body

            prospect = self._make_prospect(prospect_company=None)
            result = await generate_followup_sms_body(prospect)

            assert "John Smith" in result

    async def test_ai_prompt_includes_prospect_details(self):
        """The prompt sent to AI includes prospect trade type, company, and location."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.anthropic_model_fast = "claude-haiku"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Quick call about your leads?")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch("src.services.outreach_sms.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            from src.services.outreach_sms import generate_followup_sms_body

            prospect = self._make_prospect(
                prospect_trade_type="plumbing",
                prospect_company="Fix-It Plumbing",
                city="Dallas",
                state_code="TX",
            )
            await generate_followup_sms_body(prospect)

            # Verify prompt content
            call_kwargs = mock_client.messages.create.call_args[1]
            prompt = call_kwargs["messages"][0]["content"]
            assert "plumbing" in prompt
            assert "Fix-It Plumbing" in prompt
            assert "Dallas" in prompt

    async def test_ai_prompt_handles_missing_fields(self):
        """The prompt handles None trade type, city, state (lines 229-231)."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.anthropic_model_fast = "claude-haiku"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Let's chat about leads.")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with (
            patch("src.services.outreach_sms.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
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
