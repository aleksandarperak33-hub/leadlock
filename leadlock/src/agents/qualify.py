"""
Qualify Agent - conversational AI that extracts 4 qualification fields.
Uses Claude Sonnet for intelligence, structured JSON output.
Must qualify lead in ≤4 messages.

Target fields:
1. service_type - What service do they need?
2. urgency - How urgent? (emergency, today, this_week, flexible, just_quote)
3. property_type - Residential or commercial?
4. preferred_date - When do they want service?
"""
import json
import logging
from typing import Optional
from src.services.ai import generate_response
from src.schemas.agent_responses import QualifyResponse, QualificationData
from src.prompts.humanizer import SMS_HUMANIZER

logger = logging.getLogger(__name__)

# Qualify prompt variants for A/B testing
QUALIFY_VARIANTS = ["A", "B", "C"]


def select_variant(lead_id: str) -> str:
    """Deterministic variant selection using hash — same lead always gets same variant."""
    return QUALIFY_VARIANTS[hash(str(lead_id)) % len(QUALIFY_VARIANTS)]


def _escape_braces(text: str) -> str:
    """Escape { and } in user-controlled text to prevent .format() injection."""
    return text.replace("{", "{{").replace("}", "}}")


# Variant A (control): Current conversational prompt
_VARIANT_A_INTRO = """Your job is to qualify this lead by collecting 4 pieces of information through natural conversation:
1. Service type - What specific service do they need?
2. Urgency - How urgent? (emergency, today, this_week, flexible, just_quote)
3. Property type - Residential or commercial?
4. Preferred date/time - When do they want service?

RULES:
- Be warm, conversational, and helpful. You're texting, not writing an essay.
- Keep messages SHORT (2-3 sentences max). This is SMS, not email.
- Ask only ONE question at a time. Don't overwhelm them.
- If they've already provided info, don't ask again. Use what they gave you.
- If they mention an emergency, immediately set urgency to "emergency" and skip other questions.
- After collecting all 4 fields, set is_qualified to true and next_action to "ready_to_book".
- If they seem unresponsive or uninterested after 2+ exchanges, set next_action to "mark_cold".
- NEVER mention that you're an AI unless directly asked.
- NEVER discuss pricing - say "our team will provide a detailed estimate on-site."
"""

# Variant B (urgency-first): Opens with time-sensitive framing
_VARIANT_B_INTRO = """Your job is to qualify this lead. Open with urgency and enthusiasm.

Your approach: Lead with availability. Start with something like "Great timing - I can get a tech out as early as tomorrow!" then naturally collect the remaining info.

Collect these 4 pieces of information:
1. Service type - What specific service do they need?
2. Urgency - How urgent? (emergency, today, this_week, flexible, just_quote)
3. Property type - Residential or commercial?
4. Preferred date/time - When do they want service?

RULES:
- Lead with urgency and enthusiasm - show them you're ready to help NOW.
- Keep messages SHORT (2-3 sentences max). This is SMS.
- Ask only ONE question at a time.
- If they've already provided info, don't ask again.
- If they mention an emergency, immediately set urgency to "emergency" and skip other questions.
- After collecting all 4 fields, set is_qualified to true and next_action to "ready_to_book".
- If they seem unresponsive after 2+ exchanges, set next_action to "mark_cold".
- NEVER mention that you're an AI unless directly asked.
- NEVER discuss pricing - say "our team will provide a detailed estimate on-site."
"""

# Variant C (concise): 2-question qualify — problem + timeframe, then book
_VARIANT_C_INTRO = """Your job is to qualify this lead as FAST as possible. Use a 2-question approach:
1. First message: Ask what the problem is and when they need service (combine service_type + urgency + preferred_date into one natural question).
2. Second message: Confirm property type if not obvious, then mark qualified.

Collect these 4 fields (but do it in 2 messages max):
1. Service type, 2. Urgency, 3. Property type, 4. Preferred date/time

RULES:
- Be concise and efficient. Respect their time.
- Keep messages SHORT (1-2 sentences max). This is SMS.
- Combine questions naturally. "What's going on and when do you need us?" covers 3 fields at once.
- If they give enough info in one reply, mark qualified immediately.
- If they mention an emergency, immediately set urgency to "emergency" and skip other questions.
- After collecting enough info, set is_qualified to true and next_action to "ready_to_book".
- If they seem unresponsive after 2+ exchanges, set next_action to "mark_cold".
- NEVER mention that you're an AI unless directly asked.
- NEVER discuss pricing - say "our team will provide a detailed estimate on-site."
"""

_VARIANT_INTROS = {"A": _VARIANT_A_INTRO, "B": _VARIANT_B_INTRO, "C": _VARIANT_C_INTRO}


_QUALIFY_PROMPT_SUFFIX = SMS_HUMANIZER + """

SERVICES OFFERED:
Primary: {primary_services}
Secondary: {secondary_services}
Do NOT quote: {do_not_quote}

CURRENT QUALIFICATION DATA (already collected):
{current_qualification}

CONVERSATION HISTORY:
{conversation_history}

Respond with a JSON object:
{{
    "message": "Your SMS response to the lead",
    "qualification": {{
        "service_type": "string or null",
        "urgency": "emergency|today|this_week|flexible|just_quote or null",
        "property_type": "residential|commercial or null",
        "preferred_date": "string or null"
    }},
    "internal_notes": "Brief internal notes about the conversation",
    "next_action": "continue_qualifying|ready_to_book|mark_cold|escalate_emergency",
    "score_adjustment": 0,
    "is_qualified": false
}}"""


def _build_qualify_prompt(variant: str) -> str:
    """Build the full qualify system prompt with the selected variant intro."""
    intro = _VARIANT_INTROS.get(variant, _VARIANT_A_INTRO)
    return (
        "You are {rep_name}, a friendly and professional customer service "
        "representative for {business_name}, a {trade_type} company.\n\n"
        + intro + "\n\n" + _QUALIFY_PROMPT_SUFFIX
    )


async def process_qualify(
    lead_message: str,
    conversation_history: list[dict],
    current_qualification: dict,
    business_name: str,
    rep_name: str,
    trade_type: str,
    services: dict,
    conversation_turn: int,
    variant: str = "A",
) -> QualifyResponse:
    """
    Process a lead message through the qualify agent.
    Uses Claude Sonnet for conversational intelligence.

    Args:
        variant: A/B/C test variant for prompt style selection.
    """
    # Format conversation history for the prompt
    # Escape braces in user-controlled content to prevent .format() injection
    history_text = ""
    for msg in conversation_history[-8:]:  # Last 8 messages for context
        direction = "Customer" if msg.get("direction") == "inbound" else _escape_braces(rep_name)
        history_text += f"{direction}: {_escape_braces(msg.get('content', ''))}\n"

    # Format current qualification data
    qual_text = _escape_braces(
        json.dumps(current_qualification, indent=2) if current_qualification else "{}"
    )

    # Build the system prompt with selected variant
    prompt_template = _build_qualify_prompt(variant)
    system = prompt_template.format(
        rep_name=_escape_braces(rep_name),
        business_name=_escape_braces(business_name),
        trade_type=_escape_braces(trade_type),
        primary_services=_escape_braces(", ".join(services.get("primary", []))),
        secondary_services=_escape_braces(", ".join(services.get("secondary", []))),
        do_not_quote=_escape_braces(", ".join(services.get("do_not_quote", []))),
        current_qualification=qual_text,
        conversation_history=history_text,
    )

    # Generate AI response
    result = await generate_response(
        system_prompt=system,
        user_message=f"Customer: {lead_message}",
        model_tier="smart",
        temperature=0.3,
    )

    if result.get("error"):
        logger.error("Qualify agent AI failed: %s", result["error"])
        fallback = _fallback_response(conversation_turn)
        fallback.ai_cost_usd = 0.0
        fallback.ai_latency_ms = 0
        return fallback

    # Parse JSON response - strip markdown fences if present
    raw = _strip_markdown_fences(result["content"].strip())

    ai_cost = result.get("cost_usd", 0.0)
    ai_latency = result.get("latency_ms", 0)

    try:
        parsed = json.loads(raw)
        qualification = QualificationData(**parsed.get("qualification", {}))

        response = QualifyResponse(
            message=parsed["message"],
            qualification=qualification,
            internal_notes=parsed.get("internal_notes", ""),
            next_action=parsed.get("next_action", "continue_qualifying"),
            score_adjustment=parsed.get("score_adjustment", 0),
            is_qualified=parsed.get("is_qualified", False),
        )
        response.ai_cost_usd = ai_cost
        response.ai_latency_ms = ai_latency
        return response
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Failed to parse qualify response: %s. Content: %s", str(e), raw[:200])
        # Try to extract the "message" field via string search before giving up
        extracted = _extract_message_field(raw)
        if extracted:
            response = QualifyResponse(
                message=extracted,
                internal_notes=f"Extracted message from malformed JSON: {str(e)}",
            )
        else:
            # Fall back to a safe canned response — NEVER send raw JSON to leads
            response = _fallback_response(conversation_turn)
            response.internal_notes = f"AI parse failure, used fallback. Raw: {raw[:200]}"
        response.ai_cost_usd = ai_cost
        response.ai_latency_ms = ai_latency
        return response


def _strip_markdown_fences(text: str) -> str:
    """Robustly strip markdown code fences from AI responses."""
    import re
    # Match ```json ... ``` or ``` ... ``` (possibly with language tag)
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: strip leading/trailing ``` lines
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        return "\n".join(lines).strip()
    return text


def _extract_message_field(raw: str) -> str | None:
    """Try to extract the 'message' value from malformed JSON using regex."""
    import re
    match = re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if match:
        # Unescape JSON string escapes
        try:
            return json.loads(f'"{match.group(1)}"')
        except (json.JSONDecodeError, ValueError):
            return match.group(1)
    return None


def _fallback_response(turn: int) -> QualifyResponse:
    """Fallback when AI fails - ask a generic qualifying question."""
    fallbacks = [
        "Could you tell me more about what you need help with?",
        "How urgent is this for you? Do you need someone out today?",
        "Is this for a home or a business?",
        "When would be a good time for us to come take a look?",
    ]
    msg = fallbacks[min(turn, len(fallbacks) - 1)]
    return QualifyResponse(
        message=msg,
        internal_notes="AI fallback response used",
    )
