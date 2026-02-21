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

SYSTEM_PROMPT = """You write cold outreach emails from {sender_name} at LeadLock to home services contractors.

VOICE:
- You ARE {sender_name}. Write like a real person texting a colleague, not a marketer.
- Casual, direct, zero fluff. Talk like you'd talk to a buddy in the trades.
- ALWAYS open with their first name: "Hey Mike," or "Mike," - never "Hey," or "Hey there,"
- ALWAYS sign off with just "{sender_name}" on its own line at the end. Nothing else after it.

CONTENT:
- Reference something SPECIFIC about their business - their Google rating, their city, their trade
- One pain point per email: slow lead response kills revenue
- Include a real-sounding stat or observation (e.g. "most HVAC shops in Austin take 3+ hours to call back")
- Soft CTA - ask a question, don't push a demo

FORMATTING:
- No exclamation marks. No "game-changer", "revolutionary", "transform", or "unlock"
- No emojis
- NEVER use em dashes or en dashes. Use hyphens (-) or commas instead
- NEVER use ellipsis (...)
- Subject lines must be unique and specific - reference their company name, city, or trade. NEVER reuse the same subject across prospects
- Output valid JSON only

JSON format:
{{"subject": "...", "body_html": "...", "body_text": "..."}}

body_html: simple <p> tags only. No complex HTML.
body_text: plain text version (no HTML tags). End with {sender_name} on its own line."""

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
    1: """STEP 1 - First contact.
Open with their first name. Reference something specific about their business (rating, reviews, city, trade).
Ask a question about their lead response time. Mention how contractors in their area are losing jobs.
Under 120 words. Subject under 50 chars - must include their company name or city.""",

    2: """STEP 2 - Follow-up (they didn't reply to step 1).
Open with their first name. Mention you sent them a note last week - keep it casual.
Share a specific stat: "contractors who respond in under 5 minutes close 40% more jobs."
Ask if they're happy with how fast their team gets back to leads.
Under 90 words. Subject under 50 chars - different angle than step 1.""",

    3: """STEP 3 - Final email.
Open with their first name. Keep it to 3-4 sentences max.
Say something like "last thing from me" - no guilt, no pressure.
Leave the door open: "if this ever becomes a priority, just reply."
Under 60 words. Subject under 40 chars.""",
}


def _extract_first_name(full_name: str) -> str:
    """Extract a usable first name from a full name or company name."""
    if not full_name or not full_name.strip():
        return ""
    # Common suffixes that indicate a company name, not a person
    company_indicators = [
        "llc", "inc", "corp", "ltd", "co", "services", "solutions",
        "hvac", "plumbing", "roofing", "electrical", "solar",
        "construction", "mechanical", "systems", "contractors",
        "heating", "cooling", "air", "electric", "energy",
    ]
    name = full_name.strip()
    # If name looks like a company (contains company indicators), return empty
    name_lower = name.lower()
    for indicator in company_indicators:
        if indicator in name_lower.split():
            return ""
    # Take first word as first name
    first = name.split()[0] if name else ""
    # Skip if it's too short, all caps (likely abbreviation), or has digits
    if len(first) < 2 or first.isupper() or any(c.isdigit() for c in first):
        return ""
    return first.capitalize()


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
    sender_name: str = "Alex",
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
        sender_name: Human first name for sign-off (default "Alex")

    Returns:
        {"subject": str, "body_html": str, "body_text": str, "ai_cost_usd": float}
    """
    step = min(max(sequence_step, 1), 3)
    step_instruction = STEP_INSTRUCTIONS[step]

    first_name = _extract_first_name(prospect_name)
    greeting_name = first_name or "there"

    prospect_details = f"""Prospect details:
- First name: {greeting_name}
- Full name: {prospect_name}
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

    # Inject sender_name into system prompt
    system_prompt = SYSTEM_PROMPT.replace("{sender_name}", sender_name)

    result = await generate_response(
        system_prompt=system_prompt,
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
