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
- If you have their first name, open with it: "Hey Mike," or "Mike,"
- If you only have a company name (no first name), open casually with the company: "Hey [Company] team," or just "Hey," and reference the company in the first sentence instead
- NEVER use "Hey there," - it screams mass email
- ALWAYS sign off with just "{sender_name}" on its own line at the end. No "Best," or "Thanks," prefix - just the name.

IDENTITY:
- {sender_name} works with home services contractors on their lead response. Briefly establish this in the first email.
- Sound like you've looked at their business specifically, not like you're blasting a list.
- One line of credibility is enough: "I work with a handful of [trade] shops in [city/state]" or "we've been helping contractors in [city] respond faster"

CONTENT:
- Reference something SPECIFIC about their business - their Google rating, their city, their trade
- One pain point per email: slow lead response kills revenue
- Include one specific number or stat that sounds researched, not made up (e.g. "$2,400/month in missed revenue" or "78% of homeowners go with the first contractor who calls back")
- Subject lines should create curiosity or reference a specific observation - never generic. Examples: "saw your 3.8 rating, Mike" or "Austin HVAC shops losing $12k/month"
- Soft CTA - ask a question, don't push a demo

FORMATTING:
- No exclamation marks. No "game-changer", "revolutionary", "transform", or "unlock"
- No emojis
- NEVER use em dashes or en dashes. Use hyphens (-) or commas instead
- NEVER use ellipsis (...)
- Subject lines must be unique and specific - reference their company name, city, or trade. NEVER reuse the same subject across prospects
- In body_text, include "If this isn't relevant, just reply 'stop' and I won't reach out again." as the second-to-last line (before {sender_name}). This is NOT needed in body_html (the footer handles it).
- body_text must have proper line breaks between paragraphs (use \\n\\n). Do NOT output a single blob of text.
- Output valid JSON only

JSON format:
{{"subject": "...", "body_html": "...", "body_text": "..."}}

body_html: simple <p> tags only. No complex HTML.
body_text: plain text version (no HTML tags) with \\n\\n between paragraphs. End with {sender_name} on its own line."""

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
Mention a specific dollar amount contractors lose from slow lead response (e.g. "$2,400/month in missed revenue").
End with a soft question about their current response time - not a demand.
Under 120 words. Subject under 50 chars - must include their company name or city.""",

    2: """STEP 2 - Follow-up (they didn't reply to step 1).
Open with their first name. Mention you sent them a note last week - keep it casual.
Share a specific stat: "78% of homeowners go with the first contractor who calls back."
Ask if they're happy with how fast their team gets back to leads.
Under 90 words. Subject under 50 chars - different angle than step 1.""",

    3: """STEP 3 - Final email.
Open with their first name. Keep it to 3-4 sentences max.
Mention this is the last email you'll send - creates urgency without pressure.
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
    sender_name: str = "Alek",
    enrichment_data: Optional[dict] = None,
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
        sender_name: Human first name for sign-off (default "Alek")
        enrichment_data: Prospect research data from enrichment pipeline (optional)

    Returns:
        {"subject": str, "body_html": str, "body_text": str, "ai_cost_usd": float}
    """
    step = min(max(sequence_step, 1), 3)
    step_instruction = STEP_INSTRUCTIONS[step]

    # Use enrichment data to enhance personalization
    enrichment = enrichment_data or {}
    decision_maker_name = enrichment.get("decision_maker_name")
    decision_maker_title = enrichment.get("decision_maker_title")

    # Prefer decision-maker name over generic prospect name
    effective_name = prospect_name
    if decision_maker_name:
        effective_name = decision_maker_name

    first_name = _extract_first_name(effective_name)

    prospect_details = f"""Prospect details:
- First name: {first_name or '(no first name available - use company name in greeting)'}
- Company: {company_name}
- Trade: {trade_type}
- Location: {city}, {state}"""

    if decision_maker_title:
        prospect_details += f"\n- Title: {decision_maker_title}"
    if rating:
        prospect_details += f"\n- Google Rating: {rating}/5"
    if review_count:
        prospect_details += f"\n- Reviews: {review_count}"
    if website:
        prospect_details += f"\n- Website: {website}"

    # Add enrichment context (website summary gives AI more to work with)
    website_summary = enrichment.get("website_summary")
    if website_summary:
        prospect_details += f"\n- About: {website_summary[:200]}"

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
        temperature=0.5,
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


BOOKING_REPLY_PROMPT = """You write a short reply email from {sender_name} at LeadLock to a prospect who just replied showing interest.

RULES:
- You ARE {sender_name}. Sound like a real person, not a marketer.
- Open with their first name.
- If the prospect asked a specific question in their reply, briefly acknowledge or answer it FIRST (1 sentence) before your pitch.
- Thank them for getting back to you - keep it casual (one sentence).
- Give ONE concrete benefit of LeadLock in 1-2 sentences: "We make sure every lead that comes in gets a response in under 60 seconds, so you never lose a job to a competitor who called back first."
- Include the booking link naturally: "Here's my calendar if you want to grab 15 minutes - [booking_link]"
- Sign off with just "{sender_name}" on its own line.
- No exclamation marks. No emojis. No em dashes or en dashes.
- Under 80 words total.
- Output valid JSON only.

JSON format:
{{"subject": "...", "body_html": "...", "body_text": "..."}}

body_html: simple <p> tags only. Booking link as <a href="...">booking_link_text</a>.
body_text: plain text version with raw URL. End with {sender_name} on its own line."""


async def generate_booking_reply(
    prospect_name: str,
    trade_type: str,
    city: str,
    booking_url: str,
    sender_name: str = "Alek",
    original_subject: str = "",
    reply_text: str = "",
    enrichment_data: Optional[dict] = None,
) -> dict:
    """
    Generate an auto-reply for a prospect who replied 'interested'.

    Args:
        prospect_name: Prospect's name
        trade_type: Their trade (hvac, plumbing, etc.)
        city: Their city
        booking_url: Cal.com/Calendly booking link
        sender_name: Human first name for sign-off
        original_subject: Subject of the email they replied to
        reply_text: The actual text of the prospect's reply (for context)
        enrichment_data: Prospect research data from enrichment pipeline (optional)

    Returns:
        {"subject": str, "body_html": str, "body_text": str, "ai_cost_usd": float}
    """
    enrichment = enrichment_data or {}
    decision_maker_name = enrichment.get("decision_maker_name")

    # Prefer decision-maker name from enrichment
    effective_name = prospect_name
    if decision_maker_name:
        effective_name = decision_maker_name

    first_name = _extract_first_name(effective_name)

    # Reply subject: prepend Re: if not already
    subject_prefix = "Re: " if original_subject and not original_subject.startswith("Re:") else ""
    reply_subject = f"{subject_prefix}{original_subject}" if original_subject else ""

    system_prompt = BOOKING_REPLY_PROMPT.replace("{sender_name}", sender_name)

    user_message = f"""Prospect details:
- First name: {first_name or '(not available - just say Hey,)'}
- Trade: {trade_type}
- City: {city}
- Booking link: {booking_url}
- Original email subject: {original_subject or 'N/A'}"""

    if reply_text and reply_text.strip():
        # Truncate to 300 chars to keep costs low
        truncated = reply_text.strip()[:300]
        user_message += f"\n\nThe prospect replied with: \"{truncated}\"\nAcknowledge what they said specifically. If they asked a question, answer briefly before including the booking link."
    else:
        user_message += "\n\nWrite a reply to their interested response. Include the booking link."

    # Add enrichment context for better personalization
    website_summary = enrichment.get("website_summary")
    if website_summary:
        user_message += f"\n\nAbout their business: {website_summary[:150]}"

    result = await generate_response(
        system_prompt=system_prompt,
        user_message=user_message,
        model_tier="fast",
        max_tokens=300,
        temperature=0.5,
    )

    if result.get("error"):
        logger.error("AI booking reply failed: %s", result["error"])
        return {
            "subject": reply_subject or "Re: LeadLock",
            "body_html": "",
            "body_text": "",
            "ai_cost_usd": result.get("cost_usd", 0.0),
            "error": result["error"],
        }

    try:
        content = result["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        email_data = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error("Failed to parse AI booking reply: %s", str(e))
        # Fallback: send a simple non-AI reply
        if booking_url and booking_url.startswith("http"):
            booking_link_html = (
                f'<p>Here\'s my calendar if you want to grab 15 minutes - '
                f'<a href="{booking_url}">{booking_url}</a></p>'
            )
            booking_link_text = f"Here's my calendar if you want to grab 15 minutes - {booking_url}\n\n"
        else:
            booking_link_html = ""
            booking_link_text = ""

        greeting = f"Hey {first_name}," if first_name else "Hey,"
        fallback_html = (
            f"<p>{greeting}</p>"
            f"<p>Thanks for getting back to me. Would love to show you how LeadLock "
            f"can help your {trade_type} business respond to every lead in under 60 seconds.</p>"
            f"{booking_link_html}"
            f"<p>{sender_name}</p>"
        )
        fallback_text = (
            f"{greeting}\n\n"
            f"Thanks for getting back to me. Would love to show you how LeadLock "
            f"can help your {trade_type} business respond to every lead in under 60 seconds.\n\n"
            f"{booking_link_text}"
            f"{sender_name}"
        )
        return {
            "subject": reply_subject or "Re: LeadLock",
            "body_html": fallback_html,
            "body_text": fallback_text,
            "ai_cost_usd": result.get("cost_usd", 0.0),
        }

    return {
        "subject": email_data.get("subject", reply_subject or "Re: LeadLock").strip(),
        "body_html": email_data.get("body_html", "").strip(),
        "body_text": email_data.get("body_text", "").strip(),
        "ai_cost_usd": result.get("cost_usd", 0.0),
    }
