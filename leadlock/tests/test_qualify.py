"""
Qualify Agent tests - variant selection, prompt building, and main process_qualify flow.

Tests cover:
1. select_variant() - deterministic hash-based variant selection
2. _build_qualify_prompt() - variant-specific prompt assembly
3. _escape_braces() - format injection prevention
4. process_qualify() - full async pipeline (success, AI errors, parse errors)
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.agents.qualify import (
    select_variant,
    _build_qualify_prompt,
    process_qualify,
    _escape_braces,
    QUALIFY_VARIANTS,
    _VARIANT_INTROS,
    _QUALIFY_PROMPT_SUFFIX,
)
from src.schemas.agent_responses import QualifyResponse, QualificationData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ai_result(
    message: str = "test reply",
    qualification: dict | None = None,
    internal_notes: str = "",
    next_action: str = "continue_qualifying",
    score_adjustment: int = 0,
    is_qualified: bool = False,
    cost_usd: float = 0.001,
    latency_ms: int = 500,
    error: str | None = None,
) -> dict:
    """Build a mock AI return value matching generate_response() shape."""
    payload = {
        "message": message,
        "qualification": qualification or {},
        "internal_notes": internal_notes,
        "next_action": next_action,
        "score_adjustment": score_adjustment,
        "is_qualified": is_qualified,
    }
    return {
        "content": json.dumps(payload),
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
        "error": error,
    }


_DEFAULT_SERVICES = {
    "primary": ["AC Repair", "Heating Repair"],
    "secondary": ["Duct Cleaning"],
    "do_not_quote": ["Duct Replacement"],
}

_DEFAULT_KWARGS = dict(
    lead_message="My AC is broken",
    conversation_history=[],
    current_qualification={},
    business_name="Austin HVAC",
    rep_name="Sarah",
    trade_type="HVAC",
    services=_DEFAULT_SERVICES,
    conversation_turn=0,
    variant="A",
)


# ---------------------------------------------------------------------------
# 1. select_variant()
# ---------------------------------------------------------------------------

class TestSelectVariant:
    """Deterministic variant selection via hash-based index."""

    def test_returns_valid_variant(self):
        """select_variant always returns one of QUALIFY_VARIANTS."""
        for i in range(100):
            variant = select_variant(str(i))
            assert variant in QUALIFY_VARIANTS

    def test_deterministic_same_lead(self):
        """Same lead_id always maps to the same variant."""
        lead_id = "abc-123-xyz"
        first = select_variant(lead_id)
        for _ in range(50):
            assert select_variant(lead_id) == first

    def test_different_leads_distribute(self):
        """A range of lead_ids should produce more than one variant."""
        variants_seen = {select_variant(str(i)) for i in range(200)}
        # With 200 distinct ids and 3 buckets, all 3 must appear
        assert variants_seen == {"A", "B", "C"}

    def test_uuid_style_ids(self):
        """UUIDs should also produce valid, deterministic variants."""
        import uuid
        uid = str(uuid.uuid4())
        result = select_variant(uid)
        assert result in QUALIFY_VARIANTS
        assert select_variant(uid) == result

    def test_integer_and_string_same_result(self):
        """Passing an int vs its string representation should give the same variant
        because select_variant stringifies with str()."""
        assert select_variant(42) == select_variant("42")


# ---------------------------------------------------------------------------
# 2. _escape_braces()
# ---------------------------------------------------------------------------

class TestEscapeBraces:
    """Escaping curly braces prevents .format() injection."""

    def test_no_braces_unchanged(self):
        assert _escape_braces("hello world") == "hello world"

    def test_single_open_brace(self):
        assert _escape_braces("{") == "{{"

    def test_single_close_brace(self):
        assert _escape_braces("}") == "}}"

    def test_pair(self):
        assert _escape_braces("{key}") == "{{key}}"

    def test_nested_braces(self):
        assert _escape_braces("{{already}}") == "{{{{already}}}}"

    def test_mixed_text(self):
        assert _escape_braces("Hello {name}, score: {score}!") == "Hello {{name}}, score: {{score}}!"

    def test_empty_string(self):
        assert _escape_braces("") == ""

    def test_format_injection_payload(self):
        """A malicious payload with format placeholders should be neutralized."""
        payload = "{__class__.__init__.__globals__}"
        escaped = _escape_braces(payload)
        # After escaping, .format() should not raise or resolve the placeholder
        assert "{{" in escaped
        assert "}}" in escaped


# ---------------------------------------------------------------------------
# 3. _build_qualify_prompt()
# ---------------------------------------------------------------------------

class TestBuildQualifyPrompt:
    """Prompt assembly per variant."""

    def test_variant_a_uses_control_intro(self):
        prompt = _build_qualify_prompt("A")
        # Variant A intro mentions "natural conversation"
        assert "natural conversation" in prompt

    def test_variant_b_uses_urgency_intro(self):
        prompt = _build_qualify_prompt("B")
        # Variant B mentions leading with urgency
        assert "Lead with urgency" in prompt or "urgency and enthusiasm" in prompt

    def test_variant_c_uses_concise_intro(self):
        prompt = _build_qualify_prompt("C")
        # Variant C mentions 2-question approach
        assert "2-question" in prompt

    def test_all_variants_include_suffix(self):
        """Every variant must include the shared suffix with JSON schema."""
        for v in QUALIFY_VARIANTS:
            prompt = _build_qualify_prompt(v)
            assert "Respond with a JSON object" in prompt
            assert '"message"' in prompt
            assert '"qualification"' in prompt
            assert '"next_action"' in prompt

    def test_all_variants_contain_format_placeholders(self):
        """Prompts must have the format placeholders for .format() substitution."""
        for v in QUALIFY_VARIANTS:
            prompt = _build_qualify_prompt(v)
            assert "{rep_name}" in prompt
            assert "{business_name}" in prompt
            assert "{trade_type}" in prompt
            assert "{primary_services}" in prompt
            assert "{secondary_services}" in prompt
            assert "{do_not_quote}" in prompt
            assert "{current_qualification}" in prompt
            assert "{conversation_history}" in prompt

    def test_invalid_variant_defaults_to_a(self):
        """Unknown variant key should fall back to variant A intro."""
        prompt_unknown = _build_qualify_prompt("Z")
        prompt_a = _build_qualify_prompt("A")
        assert prompt_unknown == prompt_a

    def test_each_variant_is_different(self):
        """A, B, and C must produce distinct prompts."""
        prompts = {v: _build_qualify_prompt(v) for v in QUALIFY_VARIANTS}
        assert prompts["A"] != prompts["B"]
        assert prompts["B"] != prompts["C"]
        assert prompts["A"] != prompts["C"]

    def test_prompt_starts_with_persona(self):
        """All prompts should open with the persona line."""
        for v in QUALIFY_VARIANTS:
            prompt = _build_qualify_prompt(v)
            assert prompt.startswith("You are {rep_name}")


# ---------------------------------------------------------------------------
# 4. process_qualify() — async
# ---------------------------------------------------------------------------

class TestProcessQualify:
    """Main pipeline: AI call, parsing, fallback paths."""

    @pytest.mark.asyncio
    async def test_success_returns_qualify_response(self):
        """Happy path: valid JSON from AI -> QualifyResponse."""
        ai_result = _make_ai_result(
            message="What kind of AC trouble are you having?",
            qualification={"service_type": "AC Repair"},
            next_action="continue_qualifying",
        )
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert isinstance(resp, QualifyResponse)
        assert resp.message == "What kind of AC trouble are you having?"
        assert resp.qualification.service_type == "AC Repair"
        assert resp.next_action == "continue_qualifying"
        assert resp.ai_cost_usd == 0.001
        assert resp.ai_latency_ms == 500

    @pytest.mark.asyncio
    async def test_qualified_lead_response(self):
        """When AI signals is_qualified=True and ready_to_book."""
        ai_result = _make_ai_result(
            message="Great, let me get you scheduled!",
            qualification={
                "service_type": "AC Repair",
                "urgency": "today",
                "property_type": "residential",
                "preferred_date": "tomorrow morning",
            },
            next_action="ready_to_book",
            is_qualified=True,
            score_adjustment=10,
        )
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert resp.is_qualified is True
        assert resp.next_action == "ready_to_book"
        assert resp.score_adjustment == 10
        assert resp.qualification.urgency == "today"
        assert resp.qualification.property_type == "residential"

    @pytest.mark.asyncio
    async def test_ai_error_returns_fallback(self):
        """When AI returns an error, a fallback response is returned."""
        ai_result = {"error": "API rate limited", "content": "", "cost_usd": 0.0, "latency_ms": 0}
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert isinstance(resp, QualifyResponse)
        assert resp.ai_cost_usd == 0.0
        assert resp.ai_latency_ms == 0
        assert "AI fallback response used" in resp.internal_notes

    @pytest.mark.asyncio
    async def test_fallback_turn_0(self):
        """Turn 0 fallback asks about service type."""
        ai_result = {"error": "timeout", "content": "", "cost_usd": 0.0, "latency_ms": 0}
        kwargs = {**_DEFAULT_KWARGS, "conversation_turn": 0}
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**kwargs)

        assert "what you need help with" in resp.message.lower()

    @pytest.mark.asyncio
    async def test_fallback_turn_1(self):
        """Turn 1 fallback asks about urgency."""
        ai_result = {"error": "timeout", "content": "", "cost_usd": 0.0, "latency_ms": 0}
        kwargs = {**_DEFAULT_KWARGS, "conversation_turn": 1}
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**kwargs)

        assert "urgent" in resp.message.lower()

    @pytest.mark.asyncio
    async def test_fallback_turn_high_clamps(self):
        """Turn >= 4 still returns a valid fallback (clamped to last item)."""
        ai_result = {"error": "timeout", "content": "", "cost_usd": 0.0, "latency_ms": 0}
        kwargs = {**_DEFAULT_KWARGS, "conversation_turn": 99}
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**kwargs)

        assert isinstance(resp, QualifyResponse)
        assert resp.message  # Not empty

    @pytest.mark.asyncio
    async def test_json_parse_error_returns_raw_message(self):
        """When AI returns non-JSON, the raw content becomes the message."""
        ai_result = {
            "content": "Sorry, I can't help with that right now.",
            "cost_usd": 0.002,
            "latency_ms": 300,
            "error": None,
        }
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert isinstance(resp, QualifyResponse)
        assert resp.message == "Sorry, I can't help with that right now."
        assert "Parse error" in resp.internal_notes
        assert resp.ai_cost_usd == 0.002

    @pytest.mark.asyncio
    async def test_json_with_markdown_fences(self):
        """AI sometimes wraps JSON in ```json ... ```. Parser should strip it."""
        payload = {
            "message": "Sounds good, is this for your home?",
            "qualification": {"service_type": "Plumbing"},
            "internal_notes": "",
            "next_action": "continue_qualifying",
            "score_adjustment": 0,
            "is_qualified": False,
        }
        wrapped = f"```json\n{json.dumps(payload)}\n```"
        ai_result = {"content": wrapped, "cost_usd": 0.001, "latency_ms": 400, "error": None}

        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert resp.message == "Sounds good, is this for your home?"
        assert resp.qualification.service_type == "Plumbing"

    @pytest.mark.asyncio
    async def test_missing_qualification_key_defaults(self):
        """If AI omits 'qualification' key, defaults to empty QualificationData."""
        payload = {
            "message": "Tell me more about the issue.",
            "internal_notes": "first turn",
            "next_action": "continue_qualifying",
            "score_adjustment": 0,
            "is_qualified": False,
        }
        ai_result = {"content": json.dumps(payload), "cost_usd": 0.001, "latency_ms": 200, "error": None}

        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert resp.qualification.service_type is None
        assert resp.qualification.urgency is None

    @pytest.mark.asyncio
    async def test_variant_b_prompt_sent_to_ai(self):
        """When variant='B', the system prompt passed to AI includes urgency-first text."""
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            kwargs = {**_DEFAULT_KWARGS, "variant": "B"}
            await process_qualify(**kwargs)

        call_kwargs = mock_gen.call_args.kwargs
        system_prompt = call_kwargs.get("system_prompt", mock_gen.call_args[0][0] if mock_gen.call_args[0] else "")
        assert "urgency and enthusiasm" in system_prompt

    @pytest.mark.asyncio
    async def test_variant_c_prompt_sent_to_ai(self):
        """When variant='C', the system prompt passed to AI includes concise text."""
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            kwargs = {**_DEFAULT_KWARGS, "variant": "C"}
            await process_qualify(**kwargs)

        call_kwargs = mock_gen.call_args.kwargs
        system_prompt = call_kwargs.get("system_prompt", mock_gen.call_args[0][0] if mock_gen.call_args[0] else "")
        assert "2-question" in system_prompt

    @pytest.mark.asyncio
    async def test_ai_called_with_smart_tier(self):
        """process_qualify must request model_tier='smart' (Claude Sonnet)."""
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            await process_qualify(**_DEFAULT_KWARGS)

        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs.get("model_tier") == "smart"

    @pytest.mark.asyncio
    async def test_conversation_history_included(self):
        """Conversation history should appear in the system prompt."""
        history = [
            {"direction": "outbound", "content": "Hey, this is Sarah from Austin HVAC!"},
            {"direction": "inbound", "content": "Hi, my AC is making a weird noise"},
        ]
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            kwargs = {**_DEFAULT_KWARGS, "conversation_history": history}
            await process_qualify(**kwargs)

        call_kwargs = mock_gen.call_args.kwargs
        system_prompt = call_kwargs.get("system_prompt", mock_gen.call_args[0][0] if mock_gen.call_args[0] else "")
        assert "weird noise" in system_prompt
        assert "Customer:" in system_prompt

    @pytest.mark.asyncio
    async def test_conversation_history_capped_at_8(self):
        """Only last 8 messages of history are included."""
        history = [
            {"direction": "inbound", "content": f"msg-{i}"}
            for i in range(12)
        ]
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            kwargs = {**_DEFAULT_KWARGS, "conversation_history": history}
            await process_qualify(**kwargs)

        call_kwargs = mock_gen.call_args.kwargs
        system_prompt = call_kwargs.get("system_prompt", mock_gen.call_args[0][0] if mock_gen.call_args[0] else "")
        # msg-0 through msg-3 should be excluded (only last 8: msg-4..msg-11)
        assert "msg-0" not in system_prompt
        assert "msg-4" in system_prompt
        assert "msg-11" in system_prompt

    @pytest.mark.asyncio
    async def test_escape_braces_in_user_content(self):
        """Curly braces in conversation history must be escaped to prevent format injection."""
        history = [
            {"direction": "inbound", "content": "I need help with {__class__}"},
        ]
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            kwargs = {**_DEFAULT_KWARGS, "conversation_history": history}
            # Should not raise a KeyError from .format()
            await process_qualify(**kwargs)

        # If we got here, no format injection occurred
        assert mock_gen.called

    @pytest.mark.asyncio
    async def test_escape_braces_in_business_name(self):
        """Business name with braces must not break .format()."""
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            kwargs = {**_DEFAULT_KWARGS, "business_name": "Cool {HVAC} Co"}
            await process_qualify(**kwargs)

        assert mock_gen.called

    @pytest.mark.asyncio
    async def test_services_rendered_in_prompt(self):
        """Primary, secondary, and do_not_quote services should appear in the system prompt."""
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            await process_qualify(**_DEFAULT_KWARGS)

        call_kwargs = mock_gen.call_args.kwargs
        system_prompt = call_kwargs.get("system_prompt", mock_gen.call_args[0][0] if mock_gen.call_args[0] else "")
        assert "AC Repair" in system_prompt
        assert "Duct Cleaning" in system_prompt
        assert "Duct Replacement" in system_prompt

    @pytest.mark.asyncio
    async def test_current_qualification_in_prompt(self):
        """Already-collected qualification data appears in the system prompt."""
        existing_qual = {"service_type": "Plumbing", "urgency": "today"}
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            kwargs = {**_DEFAULT_KWARGS, "current_qualification": existing_qual}
            await process_qualify(**kwargs)

        call_kwargs = mock_gen.call_args.kwargs
        system_prompt = call_kwargs.get("system_prompt", mock_gen.call_args[0][0] if mock_gen.call_args[0] else "")
        assert "Plumbing" in system_prompt
        assert "today" in system_prompt

    @pytest.mark.asyncio
    async def test_user_message_sent_to_ai(self):
        """The lead_message is forwarded as the user_message to generate_response."""
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            await process_qualify(**_DEFAULT_KWARGS)

        call_kwargs = mock_gen.call_args.kwargs
        assert "My AC is broken" in call_kwargs.get("user_message", "")

    @pytest.mark.asyncio
    async def test_empty_content_on_parse_error_uses_fallback_message(self):
        """If AI returns empty content and it fails to parse, fallback message is used."""
        ai_result = {"content": "", "cost_usd": 0.0, "latency_ms": 100, "error": None}
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert isinstance(resp, QualifyResponse)
        # Empty raw string triggers fallback branch: raw[:300] is "", so fallback message used
        assert resp.message  # Should not be empty

    @pytest.mark.asyncio
    async def test_key_error_in_parsed_json(self):
        """JSON that parses but lacks 'message' key triggers parse-error path."""
        payload = {"qualification": {"service_type": "AC"}, "internal_notes": "missing message key"}
        ai_result = {"content": json.dumps(payload), "cost_usd": 0.001, "latency_ms": 200, "error": None}

        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert isinstance(resp, QualifyResponse)
        assert "Parse error" in resp.internal_notes

    @pytest.mark.asyncio
    async def test_temperature_is_03(self):
        """Qualify agent should use temperature=0.3 for consistent outputs."""
        ai_result = _make_ai_result()
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result) as mock_gen:
            await process_qualify(**_DEFAULT_KWARGS)

        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs.get("temperature") == 0.3

    @pytest.mark.asyncio
    async def test_mark_cold_next_action(self):
        """AI returning mark_cold should propagate to response."""
        ai_result = _make_ai_result(
            message="No worries, reach out anytime!",
            next_action="mark_cold",
        )
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert resp.next_action == "mark_cold"

    @pytest.mark.asyncio
    async def test_escalate_emergency_next_action(self):
        """AI returning escalate_emergency should propagate."""
        ai_result = _make_ai_result(
            message="I'm dispatching someone right now!",
            next_action="escalate_emergency",
            qualification={"urgency": "emergency"},
        )
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert resp.next_action == "escalate_emergency"
        assert resp.qualification.urgency == "emergency"

    @pytest.mark.asyncio
    async def test_long_raw_content_truncated_to_300(self):
        """If parse fails on long non-JSON content, message is truncated to 300 chars."""
        long_text = "x" * 500
        ai_result = {"content": long_text, "cost_usd": 0.001, "latency_ms": 100, "error": None}

        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**_DEFAULT_KWARGS)

        assert len(resp.message) == 300

    @pytest.mark.asyncio
    async def test_empty_services_dict(self):
        """Empty services dict should not crash prompt formatting."""
        ai_result = _make_ai_result()
        kwargs = {**_DEFAULT_KWARGS, "services": {}}
        with patch("src.agents.qualify.generate_response", new_callable=AsyncMock, return_value=ai_result):
            resp = await process_qualify(**kwargs)

        assert isinstance(resp, QualifyResponse)
