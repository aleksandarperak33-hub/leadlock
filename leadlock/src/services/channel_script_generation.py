"""
Channel script generation service - AI prompts for LinkedIn DM, cold call, and Facebook.
Generates copy-ready scripts for manual outreach on non-email channels.
"""
import json
import logging
from typing import Optional

from src.services.ai import generate_response
from src.utils.agent_cost import track_agent_cost

logger = logging.getLogger(__name__)

LINKEDIN_DM_PROMPT = """Write a LinkedIn connection request message + follow-up DM for a home services contractor.

Prospect details:
- Name: {prospect_name}
- Company: {company_name}
- Trade: {trade_type}
- Location: {city}, {state}
{extra_context}

RULES:
- Connection request: Under 300 characters. Reference something specific about them.
- Follow-up DM: Under 200 words. Casual, direct. One clear value prop about speed-to-lead.
- No selling in the connection request - just establish relevance.
- DM should feel like a natural conversation, not a pitch.
- No emojis, no exclamation marks.

Output valid JSON:
{{"connection_request": "...", "followup_dm": "..."}}"""

COLD_CALL_PROMPT = """Write a cold call script for calling a home services contractor about speed-to-lead.

Prospect details:
- Name: {prospect_name}
- Company: {company_name}
- Trade: {trade_type}
- Location: {city}, {state}
{extra_context}

RULES:
- Opening: 15 seconds max. State who you are, why you're calling, ask permission to continue.
- Value prop: 30 seconds. One specific pain point with a number.
- Discovery questions: 3 questions to understand their current lead response process.
- Objection handling: 3 common objections with responses (too expensive, already have something, not interested).
- Close: Ask for a 15-minute demo call, not a sale.
- Conversational, not scripted-sounding.

Output valid JSON:
{{"opening": "...", "value_prop": "...", "discovery_questions": ["...", "...", "..."], "objections": [{{"objection": "...", "response": "..."}}], "close": "..."}}"""

FACEBOOK_GROUP_PROMPT = """Write a Facebook group engagement post for home services contractors in {city}.

Target trade: {trade_type}

RULES:
- Value-first. Share an insight about lead response that sparks discussion.
- Non-promotional. Do NOT mention any product or company.
- Ask a question to drive comments.
- 50-100 words. Casual, like a fellow contractor sharing an observation.
- Reference local market conditions if possible.

Output valid JSON:
{{"post_text": "..."}}"""


async def generate_linkedin_script(
    prospect_name: str,
    company_name: str,
    trade_type: str,
    city: str,
    state: str,
    enrichment_data: Optional[dict] = None,
) -> dict:
    """Generate LinkedIn connection request + DM script."""
    extra = _build_extra_context(enrichment_data)

    result = await generate_response(
        system_prompt="You write personalized LinkedIn outreach scripts for B2B sales.",
        user_message=LINKEDIN_DM_PROMPT.format(
            prospect_name=prospect_name,
            company_name=company_name,
            trade_type=trade_type,
            city=city,
            state=state,
            extra_context=extra,
        ),
        model_tier="fast",
        max_tokens=400,
        temperature=0.5,
    )

    return _parse_script_result(result, "linkedin_dm")


async def generate_cold_call_script(
    prospect_name: str,
    company_name: str,
    trade_type: str,
    city: str,
    state: str,
    enrichment_data: Optional[dict] = None,
) -> dict:
    """Generate cold call script with talk track and objection handling."""
    extra = _build_extra_context(enrichment_data)

    result = await generate_response(
        system_prompt="You write cold call scripts for B2B sales.",
        user_message=COLD_CALL_PROMPT.format(
            prospect_name=prospect_name,
            company_name=company_name,
            trade_type=trade_type,
            city=city,
            state=state,
            extra_context=extra,
        ),
        model_tier="fast",
        max_tokens=600,
        temperature=0.5,
    )

    return _parse_script_result(result, "cold_call")


async def generate_facebook_post(
    trade_type: str,
    city: str,
) -> dict:
    """Generate Facebook group engagement post."""
    result = await generate_response(
        system_prompt="You write engaging Facebook group posts for contractor communities.",
        user_message=FACEBOOK_GROUP_PROMPT.format(
            trade_type=trade_type,
            city=city,
        ),
        model_tier="fast",
        max_tokens=200,
        temperature=0.6,
    )

    return _parse_script_result(result, "facebook_group")


def _build_extra_context(enrichment_data: Optional[dict]) -> str:
    """Build extra context string from enrichment data."""
    if not enrichment_data:
        return ""

    parts = []
    if enrichment_data.get("website_summary"):
        parts.append(f"- About: {enrichment_data['website_summary'][:200]}")
    if enrichment_data.get("decision_maker_title"):
        parts.append(f"- Title: {enrichment_data['decision_maker_title']}")

    return "\n".join(parts) if parts else ""


def _parse_script_result(result: dict, channel: str) -> dict:
    """Parse AI response into script dict."""
    ai_cost = result.get("cost_usd", 0.0)

    if result.get("error"):
        logger.error("Script generation failed for %s: %s", channel, result["error"])
        return {"error": result["error"], "ai_cost_usd": ai_cost, "channel": channel}

    try:
        content = result["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error("Failed to parse %s script: %s", channel, str(e))
        return {"error": f"JSON parse error: {str(e)}", "ai_cost_usd": ai_cost, "channel": channel}

    # Format as readable script text
    if channel == "linkedin_dm":
        script_text = (
            f"--- CONNECTION REQUEST ---\n{parsed.get('connection_request', '')}\n\n"
            f"--- FOLLOW-UP DM ---\n{parsed.get('followup_dm', '')}"
        )
    elif channel == "cold_call":
        script_text = _format_call_script(parsed)
    elif channel == "facebook_group":
        script_text = parsed.get("post_text", "")
    else:
        script_text = json.dumps(parsed, indent=2)

    # Track cost
    _track_cost_sync("channel_expander", ai_cost)

    return {
        "script_text": script_text,
        "ai_cost_usd": ai_cost,
        "channel": channel,
    }


def _format_call_script(parsed: dict) -> str:
    """Format cold call script into readable text."""
    lines = []
    lines.append(f"--- OPENING ---\n{parsed.get('opening', '')}\n")
    lines.append(f"--- VALUE PROP ---\n{parsed.get('value_prop', '')}\n")

    questions = parsed.get("discovery_questions", [])
    if questions:
        lines.append("--- DISCOVERY QUESTIONS ---")
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. {q}")
        lines.append("")

    objections = parsed.get("objections", [])
    if objections:
        lines.append("--- OBJECTION HANDLING ---")
        for obj in objections:
            lines.append(f'"{obj.get("objection", "")}"')
            lines.append(f'  -> {obj.get("response", "")}\n')

    lines.append(f"--- CLOSE ---\n{parsed.get('close', '')}")
    return "\n".join(lines)


def _track_cost_sync(agent_name: str, cost_usd: float) -> None:
    """Schedule async cost tracking (fire-and-forget from sync context)."""
    if cost_usd <= 0:
        return
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(track_agent_cost(agent_name, cost_usd))
    except RuntimeError:
        pass
