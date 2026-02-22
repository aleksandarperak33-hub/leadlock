"""
Win-back email generation service - creates re-engagement emails with alternative angles.
Uses completely different value props from the original outreach sequence.

Angles: competitor comparison, industry stats, social proof, ROI calculator, case study.
"""
import json
import logging
from typing import Optional

from src.services.ai import generate_response

logger = logging.getLogger(__name__)

WINBACK_SYSTEM_PROMPT = """You write win-back emails from {sender_name} at LeadLock to home services contractors
who were previously contacted but never replied.

CRITICAL: This is NOT a follow-up to the original pitch. Use a COMPLETELY DIFFERENT angle.
The original emails were about speed-to-lead and response time. This email must use one of these angles:
{angle}

VOICE:
- You ARE {sender_name}. Casual, direct, zero fluff.
- If you have their first name, use it: "Hey Mike,"
- If not, open with "Hey," and reference their company.
- Sign off with just "{sender_name}" on its own line.

FORMATTING:
- Shorter than original emails - under 80 words max.
- More direct. Get to the point faster.
- One clear insight or value prop.
- Soft CTA: a question, not a demand.
- No exclamation marks, no emojis, no em dashes.
- In body_text, include "If this isn't relevant, reply 'stop' and I won't reach out again." before sign-off.
- body_text must have \\n\\n between paragraphs.

JSON format:
{{"subject": "...", "body_html": "...", "body_text": "..."}}

body_html: simple <p> tags only.
body_text: plain text with \\n\\n between paragraphs."""

WINBACK_ANGLES = [
    {
        "name": "competitor_comparison",
        "instruction": (
            "ANGLE: Competitor comparison. Mention that you noticed they might be using "
            "[competitor] or handling leads manually. Don't bash competitors - just highlight "
            "what's different about automated speed-to-lead (the 60-second guarantee). "
            "Reference a specific competitor weakness if relevant to their trade."
        ),
    },
    {
        "name": "industry_stat",
        "instruction": (
            "ANGLE: Industry statistic. Lead with a surprising stat about their specific trade: "
            "how many leads the average contractor loses per month, what the cost of a missed "
            "call is in their trade, or what percentage of leads go to the first responder. "
            "Make it feel like sharing knowledge, not selling."
        ),
    },
    {
        "name": "social_proof",
        "instruction": (
            "ANGLE: Social proof / case study. Mention a result from another contractor in their area "
            "or trade (you can be general: 'a plumber in Texas' or 'an HVAC shop we work with'). "
            "Focus on a specific outcome: response time improvement, revenue recovered, leads saved."
        ),
    },
    {
        "name": "roi_calculator",
        "instruction": (
            "ANGLE: ROI / cost of inaction. Calculate a rough monthly cost of slow lead response "
            "for their business based on their trade and location. Use specific but reasonable numbers. "
            "Frame it as 'I ran some numbers on what slow response costs [trade] shops in [city].' "
            "Make it feel like a personalized analysis, not a pitch."
        ),
    },
    {
        "name": "seasonal_trigger",
        "instruction": (
            "ANGLE: Seasonal urgency. Reference the upcoming busy season for their trade "
            "(HVAC: summer/winter, plumbing: winter, roofing: spring/summer). "
            "Frame it as: now is when you want your lead response dialed in, not mid-season. "
            "Short, timely, relevant."
        ),
    },
]


def select_winback_angle(prospect_trade: str, prospect_index: int = 0) -> dict:
    """
    Select a win-back angle for a prospect. Rotates through angles
    to ensure variety across the batch.

    Args:
        prospect_trade: Trade type for context
        prospect_index: Index in batch for rotation

    Returns:
        Angle dict with name and instruction
    """
    return WINBACK_ANGLES[prospect_index % len(WINBACK_ANGLES)]


async def generate_winback_email(
    prospect_name: str,
    company_name: str,
    trade_type: str,
    city: str,
    state: str,
    angle: dict,
    sender_name: str = "Alek",
    enrichment_data: Optional[dict] = None,
) -> dict:
    """
    Generate a win-back email with an alternative angle.

    Returns:
        {"subject": str, "body_html": str, "body_text": str, "ai_cost_usd": float, "angle": str}
    """
    from src.agents.sales_outreach import _extract_first_name

    enrichment = enrichment_data or {}
    decision_maker_name = enrichment.get("decision_maker_name")
    effective_name = decision_maker_name or prospect_name
    first_name = _extract_first_name(effective_name)

    system_prompt = WINBACK_SYSTEM_PROMPT.replace("{sender_name}", sender_name).replace(
        "{angle}", angle["instruction"]
    )

    user_message = f"""Prospect details:
- First name: {first_name or '(not available - use company name)'}
- Company: {company_name}
- Trade: {trade_type}
- Location: {city}, {state}"""

    website_summary = enrichment.get("website_summary")
    if website_summary:
        user_message += f"\n- About: {website_summary[:200]}"

    result = await generate_response(
        system_prompt=system_prompt,
        user_message=user_message,
        model_tier="fast",
        max_tokens=400,
        temperature=0.6,
    )

    if result.get("error"):
        logger.error("Win-back email generation failed: %s", result["error"])
        return {
            "subject": "",
            "body_html": "",
            "body_text": "",
            "ai_cost_usd": result.get("cost_usd", 0.0),
            "angle": angle["name"],
            "error": result["error"],
        }

    # Track cost
    ai_cost = result.get("cost_usd", 0.0)
    await _track_agent_cost("winback", ai_cost)

    try:
        content = result["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        email_data = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error("Failed to parse win-back email: %s", str(e))
        return {
            "subject": "",
            "body_html": "",
            "body_text": "",
            "ai_cost_usd": ai_cost,
            "angle": angle["name"],
            "error": f"JSON parse error: {str(e)}",
        }

    return {
        "subject": email_data.get("subject", "").strip(),
        "body_html": email_data.get("body_html", "").strip(),
        "body_text": email_data.get("body_text", "").strip(),
        "ai_cost_usd": ai_cost,
        "angle": angle["name"],
    }


async def _track_agent_cost(agent_name: str, cost_usd: float) -> None:
    """Track per-agent AI cost in Redis hash."""
    if cost_usd <= 0:
        return
    try:
        from src.utils.dedup import get_redis
        from datetime import datetime, timezone
        redis = await get_redis()
        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hash_key = f"leadlock:agent_costs:{date_key}"
        await redis.hincrbyfloat(hash_key, agent_name, cost_usd)
        await redis.expire(hash_key, 30 * 86400)
    except Exception as e:
        logger.debug("Failed to track agent cost: %s", str(e))
