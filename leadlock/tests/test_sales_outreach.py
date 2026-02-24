"""
Sales outreach agent tests - AI email generation and reply classification.
All AI calls are mocked.
"""
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from src.agents.sales_outreach import (
    generate_outreach_email,
    classify_reply,
    _extract_first_name,
    _extract_name_from_email,
    STEP_INSTRUCTIONS,
    VALID_CLASSIFICATIONS,
)


def _mock_ai_response(content, cost=0.001, error=None):
    """Create a mock AI response."""
    return {
        "content": content,
        "cost_usd": cost,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "error": error,
    }


def _valid_email_json(subject="Quick question", body_html="<p>Hi</p>", body_text="Hi"):
    return json.dumps({
        "subject": subject,
        "body_html": body_html,
        "body_text": body_text,
    })


class TestExtractFirstName:
    """Test first name extraction from prospect names."""

    def test_simple_first_name(self):
        assert _extract_first_name("John Smith") == "John"

    def test_single_name(self):
        assert _extract_first_name("Mike") == "Mike"

    def test_lowercase_capitalized(self):
        assert _extract_first_name("john doe") == "John"

    def test_empty_string(self):
        assert _extract_first_name("") == ""

    def test_none_input(self):
        assert _extract_first_name(None) == ""

    def test_whitespace_only(self):
        assert _extract_first_name("   ") == ""

    def test_company_name_llc(self):
        assert _extract_first_name("Smith HVAC LLC") == ""

    def test_company_name_services(self):
        assert _extract_first_name("Comfort Air Services") == ""

    def test_company_name_plumbing(self):
        assert _extract_first_name("ABC Plumbing") == ""

    def test_company_name_roofing(self):
        assert _extract_first_name("Top Roofing Co") == ""

    def test_all_caps_abbreviation(self):
        """All-caps first word (likely abbreviation) returns empty."""
        assert _extract_first_name("ABC Corp") == ""

    def test_single_char_too_short(self):
        assert _extract_first_name("J") == ""

    def test_name_with_digits(self):
        assert _extract_first_name("123 Heating") == ""

    def test_valid_name_with_company_word_later(self):
        """Company indicator must be a whole word match."""
        assert _extract_first_name("Mike Johnson") == "Mike"

    def test_strips_whitespace(self):
        assert _extract_first_name("  Sarah Connor  ") == "Sarah"


class TestExtractNameFromEmail:
    """Test first name extraction from email addresses."""

    def test_simple_first_name(self):
        assert _extract_name_from_email("tracy@hooperplumbing.com") == "Tracy"

    def test_first_last_dot_separated(self):
        assert _extract_name_from_email("joe.ochoa@ochoaroofing.com") == "Joe"

    def test_first_last_underscore(self):
        assert _extract_name_from_email("ashley_jones@plumbingoutfitters.com") == "Ashley"

    def test_first_last_hyphen(self):
        assert _extract_name_from_email("mike-smith@company.com") == "Mike"

    def test_concatenated_firstlast(self):
        """joeochoa@ — first segment is the full local part, 'joeochoa' is valid."""
        assert _extract_name_from_email("joeochoa@ochoaroofing.com") == "Joeochoa"

    def test_single_initial_skip(self):
        """Single initial + last name — too ambiguous, skip."""
        assert _extract_name_from_email("j.smith@domain.com") == ""

    def test_two_char_initial_skip(self):
        """Two-char prefix like 'ms' — ambiguous, skip."""
        assert _extract_name_from_email("ms.jones@domain.com") == ""

    def test_generic_info(self):
        assert _extract_name_from_email("info@company.com") == ""

    def test_generic_contact(self):
        assert _extract_name_from_email("contact@company.com") == ""

    def test_generic_admin(self):
        assert _extract_name_from_email("admin@company.com") == ""

    def test_generic_support(self):
        assert _extract_name_from_email("support@company.com") == ""

    def test_generic_sales(self):
        assert _extract_name_from_email("sales@company.com") == ""

    def test_generic_hello(self):
        assert _extract_name_from_email("hello@company.com") == ""

    def test_generic_noreply(self):
        assert _extract_name_from_email("noreply@company.com") == ""

    def test_generic_hvac(self):
        assert _extract_name_from_email("hvac@company.com") == ""

    def test_generic_with_separator(self):
        """Generic prefix even with separator should be skipped."""
        assert _extract_name_from_email("info.main@company.com") == ""

    def test_empty_string(self):
        assert _extract_name_from_email("") == ""

    def test_none_input(self):
        assert _extract_name_from_email(None) == ""

    def test_no_at_sign(self):
        assert _extract_name_from_email("notanemail") == ""

    def test_digits_in_local(self):
        """Email with digits in first part should be skipped."""
        assert _extract_name_from_email("123abc@domain.com") == ""

    def test_uppercase_preserved(self):
        """Output should always be capitalized regardless of input case."""
        assert _extract_name_from_email("TRACY@domain.com") == "Tracy"

    def test_dispatch_generic(self):
        assert _extract_name_from_email("dispatch@company.com") == ""

    def test_scheduling_generic(self):
        assert _extract_name_from_email("scheduling@company.com") == ""


class TestStepInstructions:
    """Verify step instruction configuration."""

    def test_three_steps_defined(self):
        assert 1 in STEP_INSTRUCTIONS
        assert 2 in STEP_INSTRUCTIONS
        assert 3 in STEP_INSTRUCTIONS

    def test_step_1_is_first_contact(self):
        assert "STEP 1" in STEP_INSTRUCTIONS[1]
        assert "120 words" in STEP_INSTRUCTIONS[1]

    def test_step_2_is_followup(self):
        assert "STEP 2" in STEP_INSTRUCTIONS[2]
        assert "90 words" in STEP_INSTRUCTIONS[2]

    def test_step_3_is_breakup(self):
        assert "STEP 3" in STEP_INSTRUCTIONS[3]
        assert "60 words" in STEP_INSTRUCTIONS[3]


class TestGenerateOutreachEmail:
    """Test AI email generation."""

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_successful_generation(self, mock_ai, mock_learning):
        """Successful AI call should return parsed email."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response(
            _valid_email_json("Test Subject", "<p>Hello John</p>", "Hello John")
        )

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Austin HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert result["subject"] == "Test Subject"
        assert result["body_html"] == "<p>Hello John</p>"
        assert result["body_text"] == "Hello John"
        assert result["ai_cost_usd"] == 0.001
        assert "error" not in result

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_ai_error_returns_error(self, mock_ai, mock_learning):
        """AI error should fall back to deterministic email."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response("", error="Rate limited")

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Austin HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert result["fallback_used"] is True
        assert result["subject"] != ""
        assert result["body_html"] != ""
        assert result["ai_cost_usd"] == 0.0

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_invalid_json_returns_error(self, mock_ai, mock_learning):
        """Malformed JSON from AI should fall back to deterministic email."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response("This is not JSON at all")

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Austin HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert result["fallback_used"] is True
        assert result["subject"] != ""
        assert result["body_html"] != ""

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_markdown_code_block_stripped(self, mock_ai, mock_learning):
        """AI response wrapped in ```json code block should be parsed."""
        mock_learning.return_value = ""
        wrapped = '```json\n' + _valid_email_json("Wrapped Subject") + '\n```'
        mock_ai.return_value = _mock_ai_response(wrapped)

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Austin HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert result["subject"] == "Wrapped Subject"

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_empty_subject_returns_error(self, mock_ai, mock_learning):
        """Empty subject from AI should fall back to deterministic email."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response(
            json.dumps({"subject": "", "body_html": "<p>Hi</p>", "body_text": "Hi"})
        )

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Austin HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert result["fallback_used"] is True
        assert result["subject"] != ""

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_step_clamped_to_1_3(self, mock_ai, mock_learning):
        """Sequence step should be clamped between 1 and 3."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response(_valid_email_json())

        # Step 0 → clamped to 1
        await generate_outreach_email(
            prospect_name="J", company_name="C", trade_type="hvac",
            city="Austin", state="TX", sequence_step=0,
        )
        call_args = mock_ai.call_args
        assert "STEP 1" in call_args.kwargs.get("user_message", call_args[1].get("user_message", ""))

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_step_5_clamped_to_3(self, mock_ai, mock_learning):
        """Step beyond 3 should be clamped to 3."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response(_valid_email_json())

        await generate_outreach_email(
            prospect_name="J", company_name="C", trade_type="hvac",
            city="Austin", state="TX", sequence_step=5,
        )
        call_args = mock_ai.call_args
        user_msg = call_args.kwargs.get("user_message", "")
        assert "STEP 3" in user_msg

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_rating_included_in_prompt(self, mock_ai, mock_learning):
        """Google rating should appear in the AI prompt."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response(_valid_email_json())

        await generate_outreach_email(
            prospect_name="John",
            company_name="Austin HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
            rating=4.8,
            review_count=125,
        )

        user_msg = mock_ai.call_args.kwargs.get("user_message", "")
        assert "4.8" in user_msg
        assert "125" in user_msg

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_email_name_extraction_in_prompt(self, mock_ai, mock_learning):
        """When prospect_name is a company, email-extracted name should appear in prompt."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response(_valid_email_json())

        await generate_outreach_email(
            prospect_name="Lighthouse Solar",
            company_name="Lighthouse Solar",
            trade_type="solar",
            city="Phoenix",
            state="AZ",
            prospect_email="tracy@lighthousesolar.com",
        )

        user_msg = mock_ai.call_args.kwargs.get("user_message", "")
        assert "Tracy" in user_msg

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_email_name_used_in_fallback(self, mock_ai, mock_learning):
        """Fallback email should use email-extracted name in greeting."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response("", error="Rate limited")

        result = await generate_outreach_email(
            prospect_name="Hooper Plumbing",
            company_name="Hooper Plumbing",
            trade_type="plumbing",
            city="Dallas",
            state="TX",
            prospect_email="tracy@hooperplumbing.com",
        )

        assert result["fallback_used"] is True
        assert "Hey Tracy," in result["body_text"]

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generic_email_no_name_in_prompt(self, mock_ai, mock_learning):
        """Generic email like info@ should NOT produce a first name."""
        mock_learning.return_value = ""
        mock_ai.return_value = _mock_ai_response(_valid_email_json())

        await generate_outreach_email(
            prospect_name="Some Solar LLC",
            company_name="Some Solar LLC",
            trade_type="solar",
            city="Phoenix",
            state="AZ",
            prospect_email="info@somesolar.com",
        )

        user_msg = mock_ai.call_args.kwargs.get("user_message", "")
        assert "no first name available" in user_msg


class TestClassifyReply:
    """Test inbound email reply classification."""

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_interested_classification(self, mock_ai):
        mock_ai.return_value = _mock_ai_response("interested")
        result = await classify_reply("Yes, I'd like to learn more about LeadLock")
        assert result["classification"] == "interested"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_rejection_classification(self, mock_ai):
        mock_ai.return_value = _mock_ai_response("rejection")
        result = await classify_reply("Not interested, please don't contact me again")
        assert result["classification"] == "rejection"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_auto_reply_classification(self, mock_ai):
        mock_ai.return_value = _mock_ai_response("auto_reply")
        result = await classify_reply("I am currently out of the office")
        assert result["classification"] == "auto_reply"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_unsubscribe_classification(self, mock_ai):
        mock_ai.return_value = _mock_ai_response("unsubscribe")
        result = await classify_reply("Please remove me from your mailing list")
        assert result["classification"] == "unsubscribe"

    async def test_empty_reply_defaults_to_auto_reply(self):
        """Empty reply text should return auto_reply without calling AI."""
        result = await classify_reply("")
        assert result["classification"] == "auto_reply"
        assert result["ai_cost_usd"] == 0.0

    async def test_none_reply_defaults_to_auto_reply(self):
        result = await classify_reply(None)
        assert result["classification"] == "auto_reply"

    async def test_whitespace_only_defaults_to_auto_reply(self):
        result = await classify_reply("   ")
        assert result["classification"] == "auto_reply"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_unknown_classification_defaults_to_interested(self, mock_ai):
        """Unknown AI output should default to 'interested' (safe fallback)."""
        mock_ai.return_value = _mock_ai_response("maybe_later")
        result = await classify_reply("We might be interested in Q3")
        assert result["classification"] == "interested"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_ai_error_defaults_to_interested(self, mock_ai):
        """AI failure should default to 'interested' to avoid missing leads."""
        mock_ai.return_value = _mock_ai_response("", error="Timeout")
        result = await classify_reply("Some reply text")
        assert result["classification"] == "interested"

    def test_valid_classifications_complete(self):
        """All expected classifications should be in the set."""
        assert "interested" in VALID_CLASSIFICATIONS
        assert "rejection" in VALID_CLASSIFICATIONS
        assert "auto_reply" in VALID_CLASSIFICATIONS
        assert "out_of_office" in VALID_CLASSIFICATIONS
        assert "unsubscribe" in VALID_CLASSIFICATIONS
        assert len(VALID_CLASSIFICATIONS) == 5
