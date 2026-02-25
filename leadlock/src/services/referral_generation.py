"""
Referral email generation service - generates personalized referral ask emails.
Skeleton: activates when first customer onboards.
"""
import logging
import secrets
from typing import Optional

from src.services.ai import generate_response, parse_json_content

logger = logging.getLogger(__name__)

REFERRAL_PROMPT = """Write a referral request email from {sender_name} at LeadLock to an existing client.

Client details:
- Name: {client_name}
- Trade: {trade_type}
- Location: {city}
- Days since onboarding: {days_since_onboard}

RULES:
- Casual, appreciative tone. Thank them for being a customer.
- Reference a specific result they've seen (faster lead response, more booked jobs).
- Ask if they know anyone in their trade or adjacent trades who could benefit.
- Include the referral link naturally.
- Mention any referral incentive (if applicable).
- Under 100 words.
- No exclamation marks, no emojis.
- Sign off with just "{sender_name}".

Output valid JSON:
{{"subject": "...", "body_html": "...", "body_text": "..."}}"""


async def generate_referral_email(
    client_name: str,
    trade_type: str,
    city: str,
    days_since_onboard: int,
    referral_url: str,
    sender_name: str = "Alek",
) -> dict:
    """
    Generate a referral request email for an existing client.

    Returns:
        {"subject": str, "body_html": str, "body_text": str, "ai_cost_usd": float}
    """
    result = await generate_response(
        system_prompt=REFERRAL_PROMPT.format(
            sender_name=sender_name,
            client_name=client_name,
            trade_type=trade_type,
            city=city,
            days_since_onboard=days_since_onboard,
        ),
        user_message=f"Generate a referral request email. Referral link: {referral_url}",
        model_tier="fast",
        max_tokens=300,
        temperature=0.5,
    )

    ai_cost = result.get("cost_usd", 0.0)

    if result.get("error"):
        logger.error("Referral email generation failed: %s", result["error"])
        return {"error": result["error"], "ai_cost_usd": ai_cost}

    parsed, parse_error = parse_json_content(result.get("content", ""))
    if parse_error or not isinstance(parsed, dict):
        err = parse_error or f"Expected JSON object, got {type(parsed).__name__}"
        logger.error("Failed to parse referral email: %s", err)
        return {"error": f"JSON parse error: {err}", "ai_cost_usd": ai_cost}

    return {
        "subject": parsed.get("subject", "").strip(),
        "body_html": parsed.get("body_html", "").strip(),
        "body_text": parsed.get("body_text", "").strip(),
        "ai_cost_usd": ai_cost,
    }


def generate_referral_code(client_id: str) -> str:
    """Generate a unique referral code."""
    short_id = client_id[:8]
    token = secrets.token_urlsafe(6)
    return f"ref-{short_id}-{token}"
