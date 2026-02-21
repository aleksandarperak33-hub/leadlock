"""
Sales outreach agent - generates personalized cold emails for prospects.
Uses Claude Haiku for fast, cost-effective email generation.
3-step sequence: pain-point → follow-up → break-up.
Also classifies inbound replies (interested, rejection, auto_reply, etc).
"""
import json
import logging
from typing import Optional
from src.services.ai import generate_response

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a sales copywriter for LeadLock, an AI speed-to-lead platform for home services contractors.
Your job is to write cold outreach emails to contractors (HVAC, plumbing, roofing, electrical, solar).

RULES:
- Write in a casual, peer-to-peer tone - NOT salesy or corporate
- Reference specific details about their business (trade, city, reviews)
- Focus on ONE pain point: slow lead response = lost revenue
- No exclamation marks. No "game-changer" or "revolutionary"
- No emojis
- NEVER use em dashes or en dashes. Use regular hyphens (-) or rewrite the sentence instead
- Keep it SHORT - contractors are busy
- End with a soft CTA (reply or link to learn more)
- Output valid JSON only

You must output JSON with these fields:
{"subject": "...", "body_html": "...", "body_text": "..."}

body_html should use simple <p> tags. No complex HTML.
body_text is the plain text version (no HTML tags)."""

async def _get_learning_context(trade_type: str, state: str) -> str:
    """
    Fetch learning insights to include in AI prompt context.
    Returns a short string with best-performing patterns, or empty string.
    """
    try:
        from src.services.learning import get_open_rate_by_dimension, get_best_send_time

        parts = []

        open_rate = await get_open_rate_by_dimension("trade", trade_type)
        if open_rate > 0:
            parts.append(f"Avg open rate for {trade_type}: {open_rate:.0%}")

        best_time = await get_best_send_time(trade_type, state)
        if best_time:
            parts.append(f"Best send time: {best_time}")

        if parts:
            return "Performance insights:\n" + "\n".join(f"- {p}" for p in parts)
    except Exception:
        pass

    return ""


STEP_INSTRUCTIONS = {
    1: """Write a STEP 1 email (first contact).
Focus on a specific pain point for their trade in their city. Reference their Google rating/reviews if available.
Under 150 words. Subject line under 50 chars.""",

    2: """Write a STEP 2 email (follow-up, they didn't reply to step 1).
Casual tone, mention you reached out before. Include a brief case study or stat about speed-to-lead.
Under 100 words. Subject line under 50 chars.""",

    3: """Write a STEP 3 email (break-up email, final attempt).
Short and direct. Let them know this is your last email. No pressure.
Under 80 words. Subject line under 40 chars.""",
}


async def generate_outreach_email(
    prospect_name: str,
    company_name: str,
    trade_type: str,
    city: str,
    state: str,
    rating: Optional[float] = None,
    review_count: Optional[int] = None,
    website: Optional[str] = None,
    sequence_step: int = 1,
    extra_instructions: Optional[str] = None,
) -> dict:
    """
    Generate a personalized outreach email for a prospect.

    Args:
        prospect_name: Contact name
        company_name: Business name
        trade_type: hvac, plumbing, roofing, electrical, solar
        city: Business city
        state: State code
        rating: Google rating (optional)
        review_count: Number of reviews (optional)
        website: Business website (optional)
        sequence_step: 1, 2, or 3

    Returns:
        {"subject": str, "body_html": str, "body_text": str, "ai_cost_usd": float}
    """
    step = min(max(sequence_step, 1), 3)
    step_instruction = STEP_INSTRUCTIONS[step]

    prospect_details = f"""Prospect details:
- Name: {prospect_name}
- Company: {company_name}
- Trade: {trade_type}
- Location: {city}, {state}"""

    if rating:
        prospect_details += f"\n- Google Rating: {rating}/5"
    if review_count:
        prospect_details += f"\n- Reviews: {review_count}"
    if website:
        prospect_details += f"\n- Website: {website}"

    # Enrich with learning insights
    learning_context = await _get_learning_context(trade_type, state)
    if learning_context:
        prospect_details += f"\n\n{learning_context}"

    if extra_instructions:
        prospect_details += f"\n\nAdditional instructions: {extra_instructions}"

    user_message = f"{step_instruction}\n\n{prospect_details}"

    result = await generate_response(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        model_tier="fast",
        max_tokens=500,
        temperature=0.7,
    )

    if result.get("error"):
        logger.error("AI email generation failed: %s", result["error"])
        return {
            "subject": "",
            "body_html": "",
            "body_text": "",
            "ai_cost_usd": result.get("cost_usd", 0.0),
            "error": result["error"],
        }

    # Parse JSON response
    try:
        content = result["content"].strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        email_data = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error("Failed to parse AI email response: %s", str(e))
        return {
            "subject": "",
            "body_html": "",
            "body_text": "",
            "ai_cost_usd": result.get("cost_usd", 0.0),
            "error": f"JSON parse error: {str(e)}",
        }

    subject = email_data.get("subject", "").strip()
    body_html = email_data.get("body_html", "").strip()
    body_text = email_data.get("body_text", "").strip()

    if not subject or not body_html:
        logger.error("AI generated empty subject or body_html for step %d", step)
        return {
            "subject": "",
            "body_html": "",
            "body_text": "",
            "ai_cost_usd": result.get("cost_usd", 0.0),
            "error": "AI generated empty email content",
        }

    return {
        "subject": subject,
        "body_html": body_html,
        "body_text": body_text,
        "ai_cost_usd": result.get("cost_usd", 0.0),
    }


CLASSIFY_SYSTEM_PROMPT = """You classify email replies from sales prospects.
Respond with ONLY one of these labels:
- interested: They want to learn more, schedule a call, or ask questions
- rejection: They explicitly say no, not interested, or go away
- auto_reply: Automated out-of-office, vacation, or auto-responder
- out_of_office: Specifically out of office / on vacation
- unsubscribe: They want to stop receiving emails (stop, unsubscribe, remove me)

Respond with a single word - the label only."""

VALID_CLASSIFICATIONS = {"interested", "rejection", "auto_reply", "out_of_office", "unsubscribe"}


async def classify_reply(reply_text: str) -> dict:
    """
    Classify an inbound email reply using AI.

    Args:
        reply_text: The reply email text

    Returns:
        {"classification": str, "ai_cost_usd": float}
    """
    if not reply_text or not reply_text.strip():
        return {"classification": "auto_reply", "ai_cost_usd": 0.0}

    result = await generate_response(
        system_prompt=CLASSIFY_SYSTEM_PROMPT,
        user_message=f"Classify this email reply:\n\n{reply_text[:500]}",
        model_tier="fast",
        max_tokens=10,
        temperature=0.0,
    )

    if result.get("error"):
        logger.warning("Reply classification failed: %s", result["error"])
        return {"classification": "interested", "ai_cost_usd": result.get("cost_usd", 0.0)}

    classification = result["content"].strip().lower().replace(" ", "_")

    if classification not in VALID_CLASSIFICATIONS:
        logger.warning("Unknown classification '%s', defaulting to 'interested'", classification)
        classification = "interested"

    return {
        "classification": classification,
        "ai_cost_usd": result.get("cost_usd", 0.0),
    }
