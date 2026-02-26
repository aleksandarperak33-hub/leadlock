"""
Sales outreach agent - generates personalized cold emails for prospects.
Uses Claude Haiku for fast, cost-effective email generation.
3-step sequence: pain-point → follow-up → break-up.
Also classifies inbound replies (interested, rejection, auto_reply, etc).
"""
import json
import logging
from typing import Optional
from src.services.ai import generate_response, parse_json_content
from src.prompts.humanizer import EMAIL_HUMANIZER

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You write cold outreach emails from {sender_name} at LeadLock to home services contractors.

VOICE:
- You ARE {sender_name}. Write like a real person texting a colleague, not a marketer.
- Casual, direct, zero fluff. Talk like you'd talk to a buddy in the trades.
- GREETING RULE (non-negotiable): If you have their first name, open with "Hey [first_name]," — if you only have a company name, open with "Hey [Company] team," — NEVER use "Hey there," or just "Hey," alone
- ALWAYS sign off with just "{sender_name}" on its own line at the end. No "Best," or "Thanks," prefix - just the name.

IDENTITY:
- {sender_name} works with home services contractors on their lead response.
- Sound like you know their world. Use phrases like "I work with [trade] teams in [city/state]" or "I help a handful of [trade] shops in [area]."
- One line of credibility is enough - don't oversell yourself.

CONTENT:
- HOOK FIRST: Your first real sentence (after the greeting) should hit hard with a specific dollar amount or stat. Examples: "Most [trade] contractors lose about $8,000 a month in leads that go to whoever picks up first" or "78% of homeowners book with the first contractor who responds."
- Reference something SPECIFIC about their business - their Google rating, their city, their trade
- One pain point per email: slow lead response kills revenue
- CTA: Follow the step-specific CTA instructions exactly. If a booking_url is in the prospect details, you MUST include it as a clickable link. If no booking_url, ask a genuine question about their workflow.

FORMATTING:
- No exclamation marks. No "game-changer", "revolutionary", "transform", or "unlock"
- No emojis
- NEVER use em dashes or en dashes. Use hyphens (-) or commas instead
- NEVER use ellipsis (...)
- Subject lines must be unique and specific - reference their company name, city, first name, or trade. NEVER reuse the same subject across prospects
- In body_text, include "If this isn't relevant, just reply 'stop' and I won't reach out again." as the second-to-last line (before {sender_name}). This is NOT needed in body_html (the footer handles it).
- body_text must have proper line breaks between paragraphs (use \\n\\n). Do NOT output a single blob of text.
- Output valid JSON only

ANTI-REPETITION (critical):
- NEVER open with "I noticed", "I came across", "I found your", "I was looking at", "I saw that"
- NEVER start two emails in the same sequence with the same sentence structure
- NEVER reuse subject line angles across steps
- Alternative openers: start with their name + a stat, a question, a dollar amount, or a direct observation

JSON format:
{{"subject": "...", "body_html": "...", "body_text": "..."}}

body_html: simple <p> tags only. If a booking_url is provided, wrap it in an anchor tag: <a href="URL">URL</a>. No other complex HTML.
body_text: plain text version (no HTML tags) with \\n\\n between paragraphs. Include raw URL (no anchor tag). End with {sender_name} on its own line.

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

    # Add content intelligence (feature-engagement correlations)
    try:
        from src.services.email_intelligence import format_content_intelligence_for_prompt

        content_insights = await format_content_intelligence_for_prompt(
            trade=trade_type, step=step,
        )
        if content_insights:
            parts.append(content_insights)
    except Exception as e:
        logger.debug("Content intelligence query failed: %s", str(e))

    # Cap at 5 insight lines to avoid prompt bloat
    if parts:
        capped = parts[:5]
        return "Writing instructions from past performance:\n" + "\n".join(
            f"- {p}" if not p.startswith("Proven") else p for p in capped
        )

    return ""


STEP_INSTRUCTIONS = {
    1: """STEP 1 — CURIOSITY / PAIN (first contact).
GREETING: Start with "Hey {first_name}," if a first name is available. If no first name, use "Hey {company} team," — NEVER "Hey there,".
HOOK: Your very first sentence after the greeting MUST reference a specific dollar amount contractors lose from slow lead response. Use a number like "$8,000/month" or "$6,500/month" — frame it as "leads that go to the first contractor who picks up the phone" or "leads that went cold waiting for a callback". Make it feel like a fact you know, not a sales pitch.
CREDIBILITY: Include one line like "I work with {trade} teams in {city}" or "I help a few {trade} shops in {state} with this" — establish you know their world.
REFERENCE: Mention something specific about THEIR business — their Google rating, their city, their trade, their website.
CTA: End with a direct, low-friction call to action. If a booking_url is provided in the prospect details, use it: "I can show you exactly how much revenue is slipping through on slow follow-ups — takes 10 min: {booking_url}". If no booking_url, end with a genuine question about their workflow (e.g. "How fast is your crew getting back to new leads right now?"). NEVER say "would you be interested?" or "can I show you?"
SUBJECT: Must create curiosity or reference a specific observation about them. Must include their company name, city, or first name.
BANNED OPENERS: Do NOT start with "I noticed", "I came across", "I found your", "I was looking at", or "I saw that".
Under 100 words. Subject under 50 chars.""",

    2: """STEP 2 — SOCIAL PROOF (follow-up, they didn't reply to step 1).
GREETING: Same rule — "Hey {first_name}," or "Hey {company} team,".
HOOK: Lead with what similar contractors in their SPECIFIC CITY and TRADE are doing differently. Frame it as "a few {trade} shops in {city} already respond to leads in under 60 seconds — and they're closing 3x more jobs because of it." Make it about THEIR local competitors, not a generic stat.
ANGLE: Do NOT rehash the pain point from step 1. Talk about the competitive advantage — contractors who respond faster win the job. Frame it as an observation about their market, not a sales pitch.
REFERENCE: You MUST mention their city and trade in the body. Reference their Google rating or review count if available — e.g. "With {review_count} reviews and a {rating} rating, you're clearly doing the work — the leads just need faster follow-up."
CTA: If a booking_url is provided, use a short nudge: "Happy to show you how it works — 10 min: {booking_url}". If no booking_url, ask a question about their specific workflow.
SUBJECT: MUST include their company name, first name, OR city. Never use a generic stat as the subject line. Create curiosity about what their local competitors are doing.
BANNED: Do NOT mention that you emailed before or "following up" — just lead with the new angle.
BANNED OPENERS: Do NOT start with "I noticed", "I came across", "I found your", "I was looking at", or "I saw that".
Under 80 words. Subject under 50 chars.""",

    3: """STEP 3 — HAIL MARY CLOSE (final email — make it count).
GREETING: Same rule — "Hey {first_name}," or "Hey {company} team,".
TONE: Confident, direct, zero desperation. This is your last shot — deliver VALUE, not a goodbye.
CONTENT: Lead with ONE specific insight they haven't heard yet. Options:
  - A mini case study: "A {trade} shop in {city} similar to yours added $12K/month just by cutting their response time from 4 hours to 45 seconds."
  - An objection killer: "Most {trade} contractors think they respond fast enough. Then they see their average is 4+ hours and their competitors are at 30 seconds."
  - A bold question: "What would it mean for {company} if you never lost another lead to a slower competitor?"
End with a firm CTA: If booking_url provided, say "I've got one slot open this week if you want to see the numbers: {booking_url}". If no booking_url: "Reply with 'show me' and I'll send you the data."
SUBJECT: Must include their name or company. Create urgency without being cheesy — reference something specific about their business.
BANNED: Do NOT say "last email", "closing the loop", "wrapping up", or "just checking in". Do NOT apologize for emailing. Do NOT say "no hard feelings" or "I understand if you're busy."
BANNED OPENERS: Do NOT start with "I noticed", "I came across", "I found your", "I was looking at", or "I saw that".
Under 80 words. Subject under 40 chars.""",
}

STEP_SUBJECT_EXAMPLES = {
    1: [
        "{company}, what slow leads cost in {city}",
        "{first_name}, $8k question for {company}",
        "{trade} leads going cold in {city}",
    ],
    2: [
        "{first_name}, what {city} {trade} shops do differently",
        "{company} vs faster competitors in {city}",
        "your {city} competitors respond in 30 seconds",
    ],
    3: [
        "{first_name}, one thing about {company}",
        "{company} is leaving money on the table",
        "{first_name}, quick data point for you",
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
    booking_url: Optional[str] = None,
) -> dict:
    """Deterministic fallback when AI providers are unavailable."""
    first_name = _extract_first_name(prospect_name)
    company = (company_name or "your business").strip()
    greeting = f"Hey {first_name}," if first_name else f"Hey {company} team,"

    location = ", ".join([v for v in [city, state] if v])
    trade = (trade_type or "home services").strip()

    # Trade-specific revenue stats for fallback variation
    _trade_stats = {
        "hvac": ("$8,200", "AC repair"),
        "plumbing": ("$7,500", "emergency plumbing"),
        "roofing": ("$9,400", "roof replacement"),
        "electrical": ("$6,800", "electrical"),
        "solar": ("$11,000", "solar install"),
    }
    monthly_loss, trade_service = _trade_stats.get(
        trade.lower(), ("$8,000", "service")
    )

    step = min(max(sequence_step, 1), 3)
    if step == 1:
        subject_name = first_name or company
        subject = f"{subject_name}, quick question"[:60]
        hook_line = (
            f"Most {trade} contractors lose about {monthly_loss} a month "
            f"in leads that go to whoever picks up the phone first."
        )
        credibility_line = (
            f"I work with {trade} teams in {location or 'your market'} "
            f"on exactly this."
        )
        value_line = ""
        if rating and review_count:
            value_line = (
                f"Your {rating}/5 rating across {review_count} reviews tells me "
                f"you do solid work - just a matter of getting to leads faster."
            )
        elif rating:
            value_line = (
                f"Your {rating}/5 Google rating tells me you do solid work "
                f"- just a matter of getting to leads faster."
            )
        step_line = f"{hook_line}\n\n{credibility_line}"
        if value_line:
            step_line = f"{hook_line} {value_line}\n\n{credibility_line}"
        if booking_url:
            ask_line = (
                f"I can show you exactly how much revenue is slipping through "
                f"on slow follow-ups - takes 10 min: {booking_url}"
            )
        else:
            ask_line = "How fast is your crew getting back to new leads right now?"
    elif step == 2:
        subject = f"what {city or 'local'} {trade} shops are doing differently"[:60]
        step_line = (
            "78% of homeowners book with the first contractor who responds."
        )
        value_line = (
            f"A few {trade} shops in {location or 'your area'} already "
            f"respond to every lead in under 60 seconds."
        )
        if booking_url:
            ask_line = f"Happy to show you how it works - 10 min: {booking_url}"
        else:
            ask_line = "Is your team getting to new inquiries same-day right now?"
    else:
        subject = f"closing the loop, {first_name or company}"[:60]
        if booking_url:
            step_line = (
                f"Last note from me. If faster lead response ever becomes "
                f"a priority for {company}, here's my calendar: {booking_url}"
            )
        else:
            step_line = (
                f"Last note from me. If faster lead response ever becomes "
                f"a priority for {company}, just reply and I'll circle back."
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
    booking_url: Optional[str] = None,
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
        booking_url: Cal.com/Calendly link for direct booking CTA (optional)

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

    greeting_instruction = (
        f'Open with: "Hey {first_name},"'
        if first_name
        else f'Open with: "Hey {company_name} team,"'
    )

    prospect_details = f"""Prospect details:
- First name: {first_name or '(unavailable)'}
- Company: {company_name}
- Trade: {trade_type}
- Location: {city}, {state}
- GREETING: {greeting_instruction}"""

    if website:
        prospect_details += f"\n- Website: {website}"

    if booking_url:
        prospect_details += f"\n- booking_url: {booking_url}"

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
        max_tokens=400,
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
        booking_url=booking_url,
    )

    if result.get("error"):
        logger.warning(
            "AI email generation failed, using deterministic fallback: %s",
            result["error"],
        )
        return _build_fallback_outreach_email(**fallback_kwargs)

    email_data, parse_error = parse_json_content(result.get("content", ""))
    if parse_error or not isinstance(email_data, dict):
        err = parse_error or f"Expected JSON object, got {type(email_data).__name__}"
        logger.warning("Failed to parse AI email response, using fallback: %s", err)
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
        return {"classification": "auto_reply", "ai_cost_usd": result.get("cost_usd", 0.0)}

    classification = result["content"].strip().lower().replace(" ", "_")

    if classification not in VALID_CLASSIFICATIONS:
        logger.warning("Unknown classification '%s', defaulting to 'auto_reply'", classification)
        classification = "auto_reply"

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
        email_data, parse_error = parse_json_content(result.get("content", ""))
        if parse_error or not isinstance(email_data, dict):
            raise ValueError(parse_error or f"Expected JSON object, got {type(email_data).__name__}")
    except (json.JSONDecodeError, IndexError, ValueError) as e:
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
