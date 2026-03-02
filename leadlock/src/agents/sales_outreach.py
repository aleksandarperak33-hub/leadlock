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

SYSTEM_PROMPT = """You write short cold emails from {sender_name} to home services contractors.

RULES:
- You ARE {sender_name}. Write like you're texting someone you met at a trade show. Not a marketer. Not a salesperson. Just a guy.
- GREETING: Follow the GREETING instruction in prospect details word-for-word. NEVER change it. NEVER use just "Hey," alone.
- SIGN-OFF: Always end with just "{sender_name}" on its own line. Nothing before it - no "Best," no "Thanks," no "Cheers,".
- NEVER say what you do or who you work for. No company name. No product pitch. No "I work with contractors." You're just asking a question.
- NEVER use stats, dollar amounts, percentages, or data points. No "78% of homeowners." No "$8,000 a month." None. Zero.
- NEVER use marketing words: "game-changer", "transform", "unlock", "streamline", "optimize", "leverage", "revenue", "ROI", "solution", "platform"
- NEVER use phrases: "show you the numbers", "happy to show you", "I help", "I work with", "we help", "I noticed", "I came across", "I found your"
- No exclamation marks. No emojis. No em dashes. No ellipsis.
- NEVER include the prospect's website URL as a link. Website is context only.
- body_text: plain text with \\n\\n between paragraphs. End with {sender_name} on its own line.
- body_html: wrap each paragraph in <p> tags. Links as <a href="URL">text</a>. No bold, colors, images.
- Subject: under 40 chars. Lowercase feel. Their name or company. No $ or % or numbers.
- Output valid JSON: {{"subject": "...", "body_html": "...", "body_text": "..."}}

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
    1: """STEP 1 — First contact. Pure curiosity. No selling.

Write 2-3 sentences max (after greeting, before sign-off). This email should feel like a text, not a pitch.

APPROACH (pick ONE based on VARIATION instruction):
  A) Observation + question: Reference something specific about their business (rating, reviews, city, trade) and ask a genuine question about how they handle leads. Example tone: "You've got solid reviews in {city}. Curious - when someone fills out your website form at 9pm, what happens?"
  B) Competitor observation: Make a casual observation about their local market. Example tone: "Lot of {trade} shops popping up in {city}. The ones booking the most jobs aren't doing anything fancy - they're just the first to call back."
  C) Direct question: Skip the setup entirely. Just ask. Example tone: "Random question - when a new lead comes in, how long before someone on your team calls them back?"
  D) Specific detail: Use their Google rating, review count, or website info to make it personal. Example tone: "Looked up {company} the other day. {rating} stars, {review_count} reviews - clearly you guys do good work. Just wondering how you handle the inbound side."

NO booking link in step 1. NO pitch. Just a question.
NO opt-out text in step 1.
Subject: casual, under 40 chars. Use their first name or company name.""",

    2: """STEP 2 — Follow-up. They didn't reply. Give them a reason to.

Write 2-3 sentences max. Different angle from step 1 - don't repeat yourself.

APPROACH (pick ONE based on VARIATION instruction):
  A) Quick insight: Share one specific, concrete thing you've seen in their market. Not a stat - an observation. Example tone: "Talked to a {trade} guy in {city} last week. He was losing two jobs a week just because his office took 3 hours to call people back. That was it - nothing else wrong."
  B) The question they haven't thought about: Ask something that reframes how they think about leads. Example tone: "Quick thought on {company} - do you know how long it actually takes your team to get back to a new lead? Most guys think 30 minutes. Reality is usually 3-4 hours."
  C) Straight shooter: Be direct about what you do, briefly. Example tone: "I'll be straight with you - I build systems that get your team calling leads back in under a minute. Not complicated. Just fast."

If booking_url provided, include naturally: "Worth a 10 min call? {booking_url}"
If no booking_url, ask a question. Do NOT include any link.

OPT-OUT (body_text only): "If this isn't your thing, just say the word and I'll back off."
Subject: new angle, under 40 chars. Do NOT prefix with "Re:".""",

    3: """STEP 3 — Last email. Be real. Leave the door open.

Write 2-3 sentences max. No desperation. No guilt. Just straight talk.

TONE: You're not begging. You're a busy person too. If they're not interested, that's fine.

APPROACH: Be direct. Tell them this is your last email. Give them one simple way to continue the conversation if they want.

Example tone: "Last one from me. If faster lead response ever becomes a priority for {company}, I'm around. Just reply whenever."

If booking_url provided: "If you ever want to see how it works, here's my calendar: {booking_url}"

OPT-OUT (body_text only): "Either way, no more emails from me."
Subject: short, their name. Under 30 chars.

BANNED: "closing the loop", "wrapping up", "just checking in", "no hard feelings", "I understand you're busy".""",
}

STEP_SUBJECT_EXAMPLES = {
    1: [
        "hey {first_name}",
        "question about {company}",
        "{first_name} - quick one",
        "{trade} in {city}",
    ],
    2: [
        "{first_name}, one more thing",
        "re: {company}",
        "thought about {company}",
    ],
    3: [
        "last note, {first_name}",
        "{first_name}",
        "{company}",
    ],
}

STEP_TEMPERATURE = {1: 0.7, 2: 0.7, 3: 0.8}

# Hook variants for forced variation (indexed by hash of prospect identifier)
_STEP1_HOOKS = ["A", "B", "C", "D"]
_STEP2_HOOKS = ["A", "B", "C"]


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
        # Plural forms that _extract_first_name was missing
        "electricians", "plumbers", "roofers", "installers",
        "technicians", "experts", "specialists", "professionals",
        "enterprises", "associates", "partners", "group", "company",
        "restoration", "maintenance", "repair", "remodeling",
        "lighting", "power", "contracting", "brothers",
        # Geographic words that are not first names
        "northeast", "northwest", "southeast", "southwest",
        "north", "south", "east", "west", "central", "metro",
        "dallas", "houston", "austin", "phoenix", "tucson",
        "san", "las", "los", "fort", "cape", "cedar",
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


_LEGAL_SUFFIXES_RE = None


def _clean_company_name(name: str) -> str:
    """Strip legal suffixes (Inc., LLC, Co., etc.) for cleaner greetings."""
    global _LEGAL_SUFFIXES_RE
    if _LEGAL_SUFFIXES_RE is None:
        import re
        # Match trailing legal entity suffixes, with optional commas/periods
        _LEGAL_SUFFIXES_RE = re.compile(
            r"[,\s]+"
            r"(?:Inc\.?|LLC\.?|L\.?L\.?C\.?|Corp\.?|Corporation|Ltd\.?|"
            r"Co\.?|Company|LP|L\.?P\.?|PLLC|P\.?L\.?L\.?C\.?|"
            r"DBA|d/b/a|Group|Holdings|Enterprises)"
            r"[\s.,]*$",
            re.IGNORECASE,
        )
    cleaned = _LEGAL_SUFFIXES_RE.sub("", name).strip().rstrip(",. ")
    return cleaned or name


GENERIC_EMAIL_PREFIXES = frozenset({
    "info", "contact", "admin", "support", "sales", "hello", "help",
    "team", "office", "service", "billing", "marketing", "hr", "careers",
    "jobs", "noreply", "no-reply", "webmaster", "customer", "general",
    "enquiries", "inquiries", "solutions", "hvac", "plumbing", "roofing",
    "electrical", "solar", "dispatch", "accounts", "bookings", "booking",
    "mail", "payments", "operations", "ops", "quotes", "estimate",
    "estimates", "scheduling", "repairs", "maintenance", "install",
    # Compound generic prefixes (no separator)
    "customerservice", "customercare", "customersupport",
    "frontdesk", "helpdesk", "techsupport", "webadmin",
    "servicedesk", "salesteam", "officemgr", "officemanager",
    "appraisal", "usinfo",
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

    # Reject concatenated names (e.g. "jbutler", "cmewis", "mgarcia")
    # Real first names in emails either stand alone ("tracy@") or are
    # separated by dots ("joe.ochoa@"). A single initial + surname
    # concatenation like "jbutler" is not a usable first name.
    # Heuristic: unseparated local parts > 7 chars are likely concatenated.
    # For 6-7 char unseparated names, they could be real (e.g. "dennis",
    # "becky") or concatenated (e.g. "cmewis"). Accept them as-is since
    # most 6-7 char strings are real first names.
    if len(parts) == 1 and len(candidate) > 7:
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
    raw_company = _clean_company_name(company_name) if company_name else (company_name or "")
    # Normalize ALL CAPS (e.g. "FORTRESS ROOFING" → "Fortress Roofing")
    if raw_company == raw_company.upper() and len(raw_company) > 3:
        raw_company = raw_company.title()
    first_name = _extract_first_name(prospect_name)
    company = (raw_company or "your business").strip()
    greeting = f"Hey {first_name}," if first_name else f"Hey {company} team,"

    location = ", ".join([v for v in [city, state] if v])
    trade = (trade_type or "home services").strip()

    step = min(max(sequence_step, 1), 3)
    subject_name = first_name or company

    if step == 1:
        subject = f"hey {subject_name}"[:40]
        if rating and review_count:
            step_line = (
                f"{rating} stars, {review_count} reviews - clearly {company} "
                f"does solid work. Just wondering how you handle the inbound side."
            )
        elif city:
            step_line = (
                f"Random question about {company}. When a new lead comes in "
                f"after hours, how long before someone on your team calls them back?"
            )
        else:
            step_line = (
                f"Quick question - when a new lead comes in for {company}, "
                f"how long before someone calls them back?"
            )
        value_line = ""
        ask_line = ""
        stop_line = ""
    elif step == 2:
        subject = f"{subject_name}, one more thing"[:40]
        step_line = (
            f"Talked to a {trade} contractor in {location or 'your area'} "
            f"recently. He was losing two jobs a week because his office took "
            f"3 hours to call people back. That was the only problem."
        )
        value_line = ""
        if booking_url:
            ask_line = f"Worth a quick call? {booking_url}"
        else:
            ask_line = (
                f"Do you know how long it actually takes your team to get "
                f"back to a new lead?"
            )
        stop_line = "If this isn't your thing, just say the word and I'll back off."
    else:
        subject = f"last note, {subject_name}"[:40]
        if booking_url:
            step_line = (
                f"Last one from me. If faster lead response ever becomes a "
                f"priority for {company}, here's my calendar: {booking_url}"
            )
        else:
            step_line = (
                f"Last one from me. If faster lead response ever becomes a "
                f"priority for {company}, just reply whenever."
            )
        value_line = ""
        ask_line = ""
        stop_line = "Either way, no more emails from me."

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

    raw_company = _clean_company_name(company_name) if company_name else ""
    # Normalize ALL CAPS names (e.g. "FORTRESS ROOFING" → "Fortress Roofing")
    clean_company = raw_company.title() if raw_company == raw_company.upper() and len(raw_company) > 3 else raw_company

    # Build greeting instruction with robust fallbacks
    # Cap company name to avoid "Hey Alamo Plumbing Solutions drain & sewer experts team,"
    greeting_company = clean_company[:30].rsplit(" ", 1)[0] if len(clean_company) > 30 else clean_company
    if first_name:
        greeting_instruction = f'Open with: "Hey {first_name},"'
    elif greeting_company:
        greeting_instruction = f'Open with: "Hey {greeting_company} team,"'
    else:
        greeting_instruction = 'Open with: "Quick question -" (no name available, do NOT use "Hey there")'

    prospect_details = f"""Prospect details:
- First name: {first_name or '(unavailable)'}
- Company: {clean_company or '(unknown)'}
- Trade: {trade_type}
- Location: {city}, {state}
- GREETING: {greeting_instruction}"""

    # Include website for personalization context only (NOT as a CTA link)
    if website:
        prospect_details += f"\n- Website (for context only, NEVER use as CTA link): {website}"

    if booking_url:
        prospect_details += f"\n- booking_url (use this as CTA link): {booking_url}"
    else:
        prospect_details += "\n- booking_url: (none — do NOT include any link, ask a question instead)"

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

    # Force hook variation based on prospect identity to prevent repetitive openers
    # Use hashlib (not hash()) for stable results across process restarts
    import hashlib
    variation_seed = int(
        hashlib.md5(f"{clean_company}:{city}:{trade_type}".encode()).hexdigest(), 16
    ) % 100
    if step == 1:
        hook_idx = variation_seed % len(_STEP1_HOOKS)
        prospect_details += f"\n\nVARIATION (mandatory): Use hook {_STEP1_HOOKS[hook_idx]} from the HOOK options above. Do NOT use a different hook."
    elif step == 2:
        hook_idx = variation_seed % len(_STEP2_HOOKS)
        prospect_details += f"\n\nVARIATION (mandatory): Use hook {_STEP2_HOOKS[hook_idx]} from the HOOK options above. Do NOT use a different hook."

    if extra_instructions:
        prospect_details += f"\n\nAdditional instructions: {extra_instructions}"

    # Append subject line examples for inspiration
    subject_examples = STEP_SUBJECT_EXAMPLES.get(step, [])
    if subject_examples:
        filled_examples = []
        subs = {
            "{first_name}": first_name or clean_company,
            "{company}": clean_company,
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


def _looks_tentatively_interested(reply_text: str) -> bool:
    text = (reply_text or "").strip().lower()
    return any(phrase in text for phrase in ("i'll think about", "i will think about", "let me think"))


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
        error_text = str(result["error"]).strip().lower()
        fallback = "interested" if "api error" in error_text else "auto_reply"
        return {"classification": fallback, "ai_cost_usd": result.get("cost_usd", 0.0)}

    classification = result["content"].strip().lower().replace(" ", "_")

    if classification not in VALID_CLASSIFICATIONS:
        fallback = "interested" if _looks_tentatively_interested(reply_text) else "auto_reply"
        logger.warning("Unknown classification '%s', defaulting to '%s'", classification, fallback)
        classification = fallback

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
