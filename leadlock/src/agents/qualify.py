"""
Qualify Agent — conversational AI that extracts 4 qualification fields.
Uses Claude Sonnet for intelligence, structured JSON output.
Must qualify lead in ≤4 messages.

Target fields:
1. service_type — What service do they need?
2. urgency — How urgent? (emergency, today, this_week, flexible, just_quote)
3. property_type — Residential or commercial?
4. preferred_date — When do they want service?
"""
import json
import logging
from typing import Optional
from src.services.ai import generate_response
from src.schemas.agent_responses import QualifyResponse, QualificationData

logger = logging.getLogger(__name__)

QUALIFY_SYSTEM_PROMPT = """You are {rep_name}, a friendly and professional customer service representative for {business_name}, a {trade_type} company.

Your job is to qualify this lead by collecting 4 pieces of information through natural conversation:
1. Service type — What specific service do they need?
2. Urgency — How urgent? (emergency, today, this_week, flexible, just_quote)
3. Property type — Residential or commercial?
4. Preferred date/time — When do they want service?

RULES:
- Be warm, conversational, and helpful. You're texting, not writing an essay.
- Keep messages SHORT (2-3 sentences max). This is SMS, not email.
- Ask only ONE question at a time. Don't overwhelm them.
- If they've already provided info, don't ask again. Use what they gave you.
- If they mention an emergency, immediately set urgency to "emergency" and skip other questions.
- After collecting all 4 fields, set is_qualified to true and next_action to "ready_to_book".
- If they seem unresponsive or uninterested after 2+ exchanges, set next_action to "mark_cold".
- NEVER mention that you're an AI unless directly asked.
- NEVER discuss pricing — say "our team will provide a detailed estimate on-site."

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


async def process_qualify(
    lead_message: str,
    conversation_history: list[dict],
    current_qualification: dict,
    business_name: str,
    rep_name: str,
    trade_type: str,
    services: dict,
    conversation_turn: int,
) -> QualifyResponse:
    """
    Process a lead message through the qualify agent.
    Uses Claude Sonnet for conversational intelligence.
    """
    # Format conversation history for the prompt
    history_text = ""
    for msg in conversation_history[-8:]:  # Last 8 messages for context
        direction = "Customer" if msg.get("direction") == "inbound" else rep_name
        history_text += f"{direction}: {msg.get('content', '')}\n"

    # Format current qualification data
    qual_text = json.dumps(current_qualification, indent=2) if current_qualification else "{}"

    # Build the system prompt
    system = QUALIFY_SYSTEM_PROMPT.format(
        rep_name=rep_name,
        business_name=business_name,
        trade_type=trade_type,
        primary_services=", ".join(services.get("primary", [])),
        secondary_services=", ".join(services.get("secondary", [])),
        do_not_quote=", ".join(services.get("do_not_quote", [])),
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

    # Parse JSON response — strip markdown fences if present
    raw = result["content"].strip()
    if raw.startswith("```"):
        # Remove ```json ... ``` wrapper
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

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
        # Try to extract just the message from the response
        response = QualifyResponse(
            message=raw[:300] if raw else _fallback_response(conversation_turn).message,
            internal_notes=f"Parse error: {str(e)}",
        )
        response.ai_cost_usd = ai_cost
        response.ai_latency_ms = ai_latency
        return response


def _fallback_response(turn: int) -> QualifyResponse:
    """Fallback when AI fails — ask a generic qualifying question."""
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
