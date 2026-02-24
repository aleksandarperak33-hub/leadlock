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
from src.prompts.humanizer import EMAIL_HUMANIZER

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

ANTI-REPETITION (critical):
- NEVER open with "I noticed", "I came across", "I found your", "I was looking at", "I saw that"
- NEVER start two emails in the same sequence with the same sentence structure
- NEVER reuse subject line angles across steps
- Alternative openers: start with a question, a stat, their name + direct observation, or "Quick question"

JSON format:
{{"subject": "...", "body_html": "...", "body_text": "..."}}

body_html: simple <p> tags only. No complex HTML.
body_text: plain text version (no HTML tags) with \\n\\n between paragraphs. End with {sender_name} on its own line.

""" + EMAIL_HUMANIZER

async def _get_reply_rate_by_trade(trade_type: str) -> float:
    """Query learning signals for email_replied rate by trade."""
    try:
        from src.services.learning import get_open_rate_by_dimension

        # Reuse the dimension query but for reply signals
        from sqlalchemy import select, func, and_, text
        from src.database import async_session_factory
        from src.models.learning_signal import LearningSignal

        async with async_session_factory() as db:
            result = await db.execute(
                select(func.avg(LearningSignal.value))
                .where(
                    and_(
                        LearningSignal.signal_type == "email_replied",
                        func.jsonb_extract_path_text(
                            LearningSignal.dimensions, "trade"
                        ) == trade_type,
                    )
                )
            )
            rate = result.scalar()
            return float(rate) if rate is not None else 0.0
    except Exception as e:
        logger.debug("Reply rate query failed for %s: %s", trade_type, str(e))
        return 0.0


async def _get_best_day_of_week(trade_type: str, state: str) -> str:
    """Query learning signals for the best day_of_week to send emails."""
    try:
        from sqlalchemy import select, func, and_, text
        from src.database import async_session_factory
        from src.models.learning_signal import LearningSignal

        async with async_session_factory() as db:
            result = await db.execute(
                select(
                    func.jsonb_extract_path_text(
                        LearningSignal.dimensions, "day_of_week"
                    ).label("dow"),
                    func.avg(LearningSignal.value).label("avg_val"),
                    func.count().label("cnt"),
                )
                .where(
                    and_(
                        LearningSignal.signal_type == "email_opened",
                        func.jsonb_extract_path_text(
                            LearningSignal.dimensions, "trade"
                        ) == trade_type,
                    )
                )
                .group_by(text("dow"))
                .having(func.count() >= 5)
                .order_by(text("avg_val DESC"))
                .limit(1)
            )
            row = result.first()
            if row and row.dow:
                return row.dow
    except Exception as e:
        logger.debug("Best day query failed for %s: %s", trade_type, str(e))
    return ""


def _prescriptive_open_rate(open_rate: float) -> str:
    """Turn an open rate number into an actionable instruction for the AI."""
    if open_rate > 0.20:
        return "Current subject line approach is working well - keep the same tone and length."
    if open_rate > 0.10:
        return "Try more specific subject lines referencing their city or Google rating."
    return "Change approach: shorter, more direct subjects. Ask a question in the subject."


def _prescriptive_reply_rate(reply_rate: float) -> str:
    """Turn a reply rate number into an actionable instruction for the AI."""
    if reply_rate > 0.05:
        return "CTAs are generating replies - keep the same conversational ask."
    return "Make CTA more specific - ask about their response time or team size."


async def _get_learning_context(trade_type: str, state: str, step: int = 1) -> str:
    """
    Fetch learning insights and convert them into prescriptive AI instructions.
    Returns actionable guidance, not raw stats.
    """
    parts: list[str] = []

    try:
        from src.services.learning import get_open_rate_by_dimension, get_best_send_time

        open_rate = await get_open_rate_by_dimension("trade", trade_type)
        if open_rate > 0:
            parts.append(_prescriptive_open_rate(open_rate))

        # Step-level open rate
        step_open = await get_open_rate_by_dimension("step", str(step))
        if step_open > 0 and step_open != open_rate:
            parts.append(
                f"Step {step} open rate is {step_open:.0%} - "
                + ("this step is strong, maintain approach." if step_open > 0.15
                   else "this step underperforms, try a different angle.")
            )

        reply_rate = await _get_reply_rate_by_trade(trade_type)
        if reply_rate > 0:
            parts.append(_prescriptive_reply_rate(reply_rate))

        best_day = await _get_best_day_of_week(trade_type, state)
        if best_day:
            parts.append(f"Best performing send day: {best_day}")

        best_time = await get_best_send_time(trade_type, state)
        if best_time:
            parts.append(f"Best send time: {best_time}")
    except Exception as e:
        logger.debug("Learning context query failed for %s: %s", trade_type, str(e))

    # Add winning patterns
    try:
        from src.services.winning_patterns import format_patterns_for_prompt

        patterns = await format_patterns_for_prompt(trade=trade_type, step=step)
        if patterns:
            parts.append(patterns)
    except Exception as e:
        logger.debug("Winning patterns query failed: %s", str(e))

    # Cap at 5 insight lines to avoid prompt bloat
    if parts:
        capped = parts[:5]
        return "Writing instructions from past performance:\n" + "\n".join(
            f"- {p}" if not p.startswith("Proven") else p for p in capped
        )

    return ""


STEP_INSTRUCTIONS = {
    1: """STEP 1 — CURIOSITY / PAIN (first contact).
Angle: Lead with a question or observation about THEIR business specifically.
- Reference one concrete detail: their Google rating, their city, or their trade.
- Mention a specific dollar amount contractors lose from slow lead response (e.g. "$2,400/month in missed revenue").
- End with a genuine question about their business, not a pitch.
- Subject line must create curiosity or reference a specific observation about them.
- Do NOT start with "I noticed", "I came across", "I found your", "I was looking at", or "I saw that".
Under 120 words. Subject under 50 chars - must include their company name or city.""",

    2: """STEP 2 — SOCIAL PROOF (follow-up, they didn't reply to step 1).
Angle: Do NOT rehash the pain point from step 1. Lead with what similar contractors are doing.
- Share what other contractors in their trade or city are doing differently.
- Include a specific result or stat (e.g. "78% of homeowners go with the first contractor who calls back").
- Ask a different question than step 1 - focus on their team's workflow, not revenue.
- Subject line must use a completely different angle than step 1.
- Do NOT start with "I noticed", "I came across", "I found your", "I was looking at", or "I saw that".
- Do NOT mention that you emailed before or "following up" - just lead with the new angle.
Under 90 words. Subject under 50 chars.""",

    3: """STEP 3 — FAREWELL (final email).
Angle: Short and final. No new stats, no new value props.
- 3-4 sentences max. State this is the last email.
- No selling. Just "if this ever matters, reply."
- Subject line should feel short and final.
- Do NOT start with "I noticed", "I came across", "I found your", "I was looking at", or "I saw that".
Under 60 words. Subject under 40 chars.""",
}

STEP_SUBJECT_EXAMPLES = {
    1: [
        "Quick question for {company}",
        "{city} {trade} shops losing $12k/month",
        "saw your {rating} rating, {first_name}",
    ],
    2: [
        "what {trade} teams in {city} are doing differently",
        "78% stat that surprised me, {first_name}",
        "{trade} response times in {city}",
    ],
    3: [
        "closing the loop, {first_name}",
        "last note from me",
        "one more thing, {first_name}",
    ],
}

STEP_TEMPERATURE = {1: 0.4, 2: 0.6, 3: 0.7}


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


GENERIC_EMAIL_PREFIXES = frozenset({
    "info", "contact", "admin", "support", "sales", "hello", "help",
    "team", "office", "service", "billing", "marketing", "hr", "careers",
    "jobs", "noreply", "no-reply", "webmaster", "customer", "general",
    "enquiries", "inquiries", "solutions", "hvac", "plumbing", "roofing",
    "electrical", "solar", "dispatch", "accounts", "bookings", "booking",
    "mail", "payments", "operations", "ops", "quotes", "estimate",
    "estimates", "scheduling", "repairs", "maintenance", "install",
})


def _extract_name_from_email(email: str) -> str:
    """
    Extract a first name from the local part of an email address.

    Common patterns:
        tracy@domain.com → "Tracy"
        joeochoa@domain.com → "Joeochoa" (no splitting on concatenated names)
        joe.ochoa@domain.com → "Joe"
        j.smith@domain.com → "" (single initial, ambiguous)
        info@domain.com → "" (generic prefix)

    Returns:
        Capitalized first name, or empty string if extraction fails.
    """
    if not email or "@" not in email:
        return ""

    local_part = email.split("@")[0].lower().strip()
    if not local_part:
        return ""

    # Strip plus-alias suffix (e.g. mike+leadgen@ → mike@)
    local_part = local_part.split("+")[0]

    # Skip if the entire local part is a generic prefix
    if local_part in GENERIC_EMAIL_PREFIXES:
        return ""

    # Split on common separators: . - _
    parts = [p for p in local_part.replace("-", ".").replace("_", ".").split(".") if p]
    if not parts:
        return ""

    candidate = parts[0]

    # Skip generic prefixes even when followed by separators (e.g. info.smith@)
    if candidate in GENERIC_EMAIL_PREFIXES:
        return ""

    # Skip if too short (1-2 chars = likely an initial like "j" or "ms")
    if len(candidate) < 3:
        return ""

    # Must be all alpha (no digits, no special chars)
    if not candidate.isalpha():
        return ""

    return candidate.capitalize()


def _build_fallback_outreach_email(
    prospect_name: str,
    company_name: str,
    trade_type: str,
    city: str,
    state: str,
    sequence_step: int,
    sender_name: str,
    rating: Optional[float] = None,
    review_count: Optional[int] = None,
) -> dict:
    """Deterministic fallback when AI providers are unavailable."""
    first_name = _extract_first_name(prospect_name)
    greeting = f"Hey {first_name}," if first_name else "Hey,"

    location = ", ".join([v for v in [city, state] if v])
    trade = (trade_type or "home services").strip()
    company = (company_name or "your business").strip()

    # Build a rating hook when data is available
    rating_line = ""
    if rating and review_count:
        rating_line = (
            f"Your {rating}/5 rating with {review_count} reviews caught my eye."
        )
    elif rating:
        rating_line = f"Your {rating}/5 Google rating stood out."

    step = min(max(sequence_step, 1), 3)
    if step == 1:
        subject = f"Quick question for {company}"[:60]
        if rating_line:
            step_line = rating_line
        else:
            step_line = (
                f"I work with {trade} teams in {location or 'your market'} "
                f"and {company} came up."
            )
        value_line = (
            "Most contractors lose about $2,400 a month because leads wait "
            "too long for a callback."
        )
        ask_line = "How fast is your team currently getting back to brand-new leads?"
    elif step == 2:
        subject = f"{trade.capitalize()} teams in {city or 'your area'}"[:60]
        step_line = (
            f"78% of homeowners go with the first contractor who calls back."
        )
        value_line = (
            f"A few {trade} shops in {location or 'your area'} already reply "
            f"to every lead in under 60 seconds."
        )
        ask_line = "Is your crew getting to new inquiries same-day right now?"
    else:
        subject = f"Closing the loop, {first_name or company}"[:60]
        step_line = (
            f"Last note from me. If faster lead response ever becomes a "
            f"priority for {company}, just reply and I will circle back."
        )
        value_line = ""
        ask_line = ""

    stop_line = "If this isn't relevant, just reply 'stop' and I won't reach out again."

    body_parts = [p for p in [
        greeting,
        step_line,
        value_line,
        ask_line,
        stop_line,
        sender_name,
    ] if p]
    body_text = "\n\n".join(body_parts)
    body_html = "".join(f"<p>{part}</p>" for part in body_parts)

    return {
        "subject": subject,
        "body_html": body_html,
        "body_text": body_text,
        "ai_cost_usd": 0.0,
        "fallback_used": True,
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
    sender_name: str = "Alek",
    enrichment_data: Optional[dict] = None,
    prospect_email: Optional[str] = None,
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
        prospect_email: Prospect email address, used as last-resort name source (optional)

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

    # Last resort: extract first name from email address
    if not first_name and prospect_email:
        email_name = _extract_name_from_email(prospect_email)
        if email_name:
            first_name = email_name
            # Only replace effective_name if decision_maker_name was absent,
            # to avoid misattributing email-derived names in the AI prompt
            if not decision_maker_name:
                effective_name = email_name

    prospect_details = f"""Prospect details:
- First name: {first_name or '(no first name available - use company name in greeting)'}
- Company: {company_name}
- Trade: {trade_type}
- Location: {city}, {state}"""

    if website:
        prospect_details += f"\n- Website: {website}"

    # Structured personalization instructions from enrichment data
    personalization: list[str] = []
    if decision_maker_title:
        personalization.append(
            f"Decision-maker is {effective_name}, {decision_maker_title} "
            f"- use their first name and acknowledge their role."
        )
    if rating and review_count:
        personalization.append(
            f"Their Google rating is {rating}/5 with {review_count} reviews "
            f"- reference this specifically."
        )
    elif rating:
        personalization.append(
            f"Their Google rating is {rating}/5 - reference this specifically."
        )

    website_summary = enrichment.get("website_summary")
    if website_summary:
        personalization.append(
            f"About their business: {website_summary[:200]}. "
            f"Reference something specific from this."
        )

    if personalization:
        prospect_details += "\n\nPersonalization instructions:\n" + "\n".join(
            f"- {p}" for p in personalization
        )

    # Enrich with learning insights
    learning_context = await _get_learning_context(trade_type, state, step)
    if learning_context:
        prospect_details += f"\n\n{learning_context}"

    if extra_instructions:
        prospect_details += f"\n\nAdditional instructions: {extra_instructions}"

    # Append subject line examples for inspiration
    subject_examples = STEP_SUBJECT_EXAMPLES.get(step, [])
    if subject_examples:
        filled_examples = []
        subs = {
            "{first_name}": first_name or company_name,
            "{company}": company_name,
            "{city}": city or "your area",
            "{trade}": trade_type or "home services",
            "{rating}": str(rating) if rating else "4.5",
        }
        for ex in subject_examples:
            filled = ex
            for key, val in subs.items():
                filled = filled.replace(key, val)
            filled_examples.append(filled)
        step_instruction = (
            step_instruction
            + "\n\nExample subjects (for inspiration, don't copy exactly): "
            + " | ".join(f'"{e}"' for e in filled_examples)
        )

    user_message = f"{step_instruction}\n\n{prospect_details}"

    # Inject sender_name into system prompt
    system_prompt = SYSTEM_PROMPT.replace("{sender_name}", sender_name)

    result = await generate_response(
        system_prompt=system_prompt,
        user_message=user_message,
        model_tier="fast",
        max_tokens=500,
        temperature=STEP_TEMPERATURE.get(step, 0.5),
    )

    fallback_kwargs = dict(
        prospect_name=effective_name,
        company_name=company_name,
        trade_type=trade_type,
        city=city,
        state=state,
        sequence_step=step,
        sender_name=sender_name,
        rating=rating,
        review_count=review_count,
    )

    if result.get("error"):
        logger.warning(
            "AI email generation failed, using deterministic fallback: %s",
            result["error"],
        )
        return _build_fallback_outreach_email(**fallback_kwargs)

    # Parse JSON response
    try:
        content = result["content"].strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        email_data = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        logger.warning("Failed to parse AI email response, using fallback: %s", str(e))
        return _build_fallback_outreach_email(**fallback_kwargs)

    subject = email_data.get("subject", "").strip()
    body_html = email_data.get("body_html", "").strip()
    body_text = email_data.get("body_text", "").strip()

    if not subject or not body_html:
        logger.warning("AI generated empty content for step %d, using fallback", step)
        return _build_fallback_outreach_email(**fallback_kwargs)

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
body_text: plain text version with raw URL. End with {sender_name} on its own line.

""" + EMAIL_HUMANIZER


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
