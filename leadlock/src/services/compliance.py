"""
Compliance engine — THE GATEKEEPER.
Every outbound SMS MUST pass through this before sending.

TCPA penalties: $500/violation minimum, $1,500 willful, NO CAP, 4-year statute of limitations.
This module is the single most important piece of the entire system.

Checks performed:
1. Consent exists and is active
2. Phone not opted out
3. Quiet hours enforcement (federal 8am-9pm, TX Sunday noon-9pm, FL 8am-8pm + holidays)
4. Message limit enforcement (max 3 cold outreach)
5. Content compliance (STOP language, business name, no URL shorteners)
6. Emergency bypass (life safety exception)
"""
import logging
from datetime import datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Exact STOP keywords — recognized case-insensitively after normalization
STOP_KEYWORDS = {"stop", "unsubscribe", "cancel", "end", "quit", "opt-out", "optout", "remove"}

# Phrase patterns that indicate opt-out intent (substring matching)
STOP_PHRASES = [
    "stop it",
    "stop texting",
    "stop messaging",
    "stop contacting",
    "stop sending",
    "please stop",
    "dont text",
    "don't text",
    "do not text",
    "dont message",
    "don't message",
    "do not message",
    "do not contact",
    "dont contact",
    "don't contact",
    "take me off",
    "remove me",
    "leave me alone",
    "opt out",
    "opt me out",
    "unsubscribe me",
    "i want out",
    "no more texts",
    "no more messages",
    "go away",
]

# Florida holidays are now dynamically computed — see src/utils/holidays.py

# State timezone mapping
STATE_TIMEZONES = {
    "TX": "America/Chicago",
    "FL": "America/New_York",
    "CA": "America/Los_Angeles",
    "NY": "America/New_York",
    "AZ": "America/Phoenix",
    "HI": "Pacific/Honolulu",
    "AK": "America/Anchorage",
}


class ComplianceResult:
    """Result of a compliance check."""

    def __init__(self, allowed: bool, reason: str = "", rule: str = ""):
        self.allowed = allowed
        self.reason = reason
        self.rule = rule

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        status = "ALLOWED" if self.allowed else "BLOCKED"
        return f"<ComplianceResult {status}: {self.reason}>"


def is_stop_keyword(message: str) -> bool:
    """
    Check if a message indicates opt-out intent using fuzzy matching.

    Detection layers:
    1. Exact keyword match (after normalization: strip, lowercase, remove punctuation)
    2. Repeated character detection (e.g., "STOPPPP" → "stop")
    3. Substring phrase matching (e.g., "stop texting me", "leave me alone")

    CRITICAL: When in doubt, treat as opt-out.
    A false positive (unnecessary opt-out) costs us a lead.
    A false negative costs $500-$1,500 per TCPA violation.
    """
    import re

    if not message or not message.strip():
        return False

    # Normalize: strip whitespace, lowercase, remove leading/trailing punctuation
    normalized = message.strip().lower()
    # Remove all punctuation for keyword matching
    cleaned = re.sub(r"[^\w\s]", "", normalized).strip()

    # Layer 1: Exact keyword match on cleaned version
    if cleaned in STOP_KEYWORDS:
        return True

    # Layer 2: Collapse repeated characters (STOPPPP → stop, QUIIIT → quit)
    collapsed = re.sub(r"(.)\1{2,}", r"\1", cleaned)
    if collapsed in STOP_KEYWORDS:
        return True

    # Layer 3: Substring phrase matching
    for phrase in STOP_PHRASES:
        if phrase in normalized:
            return True

    # Layer 4: Check if any stop keyword appears as a standalone word,
    # but only in short messages (≤4 words). Longer sentences like
    # "Please don't stop the service" are NOT opt-out requests.
    words = cleaned.split()
    if len(words) <= 4 and set(words) & STOP_KEYWORDS:
        return True

    return False


def check_consent(
    has_consent: bool,
    consent_type: Optional[str] = None,
    is_opted_out: bool = False,
    is_marketing: bool = False,
) -> ComplianceResult:
    """
    Check if we have valid consent to message this phone number.
    - PEC (Prior Express Consent): allows informational messages
    - PEWC (Prior Express Written Consent): allows marketing messages
    """
    if is_opted_out:
        return ComplianceResult(
            False, "Phone number has opted out", "tcpa_opt_out"
        )

    if not has_consent:
        return ComplianceResult(
            False, "No consent record exists for this phone number", "tcpa_no_consent"
        )

    if is_marketing and consent_type == "pec":
        return ComplianceResult(
            False,
            "Marketing messages require PEWC consent, only PEC on file",
            "tcpa_consent_level",
        )

    return ComplianceResult(True, "Consent verified")


def check_quiet_hours(
    state_code: Optional[str] = None,
    timezone_str: Optional[str] = None,
    is_emergency: bool = False,
    now: Optional[datetime] = None,
) -> ComplianceResult:
    """
    Enforce quiet hours. Emergency messages bypass all quiet hours (life safety exception).

    Rules:
    - Federal: 8:00 AM – 9:00 PM local time
    - Texas SB 140: Sundays only noon – 9:00 PM
    - Florida FTSA: 8:00 AM – 8:00 PM, no state holidays
    """
    # Emergency bypass — life safety exception
    if is_emergency:
        return ComplianceResult(True, "Emergency bypass — life safety exception")

    # Determine timezone
    if timezone_str:
        tz = ZoneInfo(timezone_str)
    elif state_code and state_code in STATE_TIMEZONES:
        tz = ZoneInfo(STATE_TIMEZONES[state_code])
    else:
        # Default to Eastern (most restrictive common timezone)
        tz = ZoneInfo("America/New_York")

    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    local_time = now.time()
    day_of_week = now.weekday()  # 0=Monday, 6=Sunday
    local_date = now.date()

    # Texas SB 140: Sunday only noon–9 PM
    if state_code == "TX" and day_of_week == 6:
        if local_time < time(12, 0) or local_time >= time(21, 0):
            return ComplianceResult(
                False,
                f"Texas SB 140: Sunday texts only noon–9 PM. Current: {local_time.strftime('%H:%M')}",
                "tx_sb140_sunday",
            )

    # Florida FTSA: 8 AM–8 PM, no state holidays
    if state_code == "FL":
        from src.utils.holidays import is_florida_holiday
        if is_florida_holiday(local_date):
            return ComplianceResult(
                False,
                f"Florida FTSA: No messages on state holidays ({local_date.isoformat()})",
                "fl_ftsa_holiday",
            )
        if local_time < time(8, 0) or local_time >= time(20, 0):
            return ComplianceResult(
                False,
                f"Florida FTSA: Messages only 8 AM–8 PM. Current: {local_time.strftime('%H:%M')}",
                "fl_ftsa_hours",
            )

    # Federal TCPA: 8 AM–9 PM local time
    if local_time < time(8, 0) or local_time >= time(21, 0):
        return ComplianceResult(
            False,
            f"Federal TCPA: Messages only 8 AM–9 PM. Current: {local_time.strftime('%H:%M')}",
            "tcpa_quiet_hours",
        )

    return ComplianceResult(True, "Within allowed hours")


def check_message_limits(
    cold_outreach_count: int,
    max_cold_followups: int = 3,
    is_reply_to_inbound: bool = False,
) -> ComplianceResult:
    """
    Enforce message limits. Max 3 cold outreach messages per lead, ever.
    Reply messages (responding to an inbound) don't count against the limit.
    """
    if is_reply_to_inbound:
        return ComplianceResult(True, "Reply to inbound — no limit applies")

    if cold_outreach_count >= max_cold_followups:
        return ComplianceResult(
            False,
            f"Max cold outreach reached ({cold_outreach_count}/{max_cold_followups})",
            "max_cold_outreach",
        )

    return ComplianceResult(True, f"Cold outreach {cold_outreach_count}/{max_cold_followups}")


def check_content_compliance(
    message: str,
    is_first_message: bool = False,
    business_name: Optional[str] = None,
) -> ComplianceResult:
    """
    Check message content for compliance issues.
    - First message MUST include "Reply STOP to opt out" and business name
    - No URL shorteners (bit.ly, tinyurl, etc. — carriers filter them)
    """
    # URL shortener check — carriers block these
    shortener_domains = ["bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd", "buff.ly"]
    message_lower = message.lower()
    for domain in shortener_domains:
        if domain in message_lower:
            return ComplianceResult(
                False,
                f"URL shortener detected ({domain}) — carriers will filter this",
                "content_url_shortener",
            )

    # First message requirements
    if is_first_message:
        if "stop" not in message_lower:
            return ComplianceResult(
                False,
                'First message must include "Reply STOP to opt out"',
                "content_missing_stop",
            )
        if business_name and business_name.lower() not in message_lower:
            return ComplianceResult(
                False,
                f"First message must include business name ({business_name})",
                "content_missing_business_name",
            )

    return ComplianceResult(True, "Content compliant")


def full_compliance_check(
    has_consent: bool,
    consent_type: Optional[str] = None,
    is_opted_out: bool = False,
    is_marketing: bool = False,
    state_code: Optional[str] = None,
    timezone_str: Optional[str] = None,
    is_emergency: bool = False,
    cold_outreach_count: int = 0,
    max_cold_followups: int = 3,
    is_reply_to_inbound: bool = False,
    message: str = "",
    is_first_message: bool = False,
    business_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ComplianceResult:
    """
    Run ALL compliance checks. Returns the first failure, or success if all pass.
    Order matters — check opt-out first (immediate block), then consent, then hours, etc.
    """
    # 1. Consent check (includes opt-out)
    consent_result = check_consent(has_consent, consent_type, is_opted_out, is_marketing)
    if not consent_result:
        logger.warning("Compliance BLOCKED: %s", consent_result.reason)
        return consent_result

    # 2. Quiet hours (emergency bypasses)
    hours_result = check_quiet_hours(state_code, timezone_str, is_emergency, now)
    if not hours_result:
        logger.warning("Compliance BLOCKED: %s", hours_result.reason)
        return hours_result

    # 3. Message limits
    limits_result = check_message_limits(cold_outreach_count, max_cold_followups, is_reply_to_inbound)
    if not limits_result:
        logger.warning("Compliance BLOCKED: %s", limits_result.reason)
        return limits_result

    # 4. Content compliance
    content_result = check_content_compliance(message, is_first_message, business_name)
    if not content_result:
        logger.warning("Compliance BLOCKED: %s", content_result.reason)
        return content_result

    return ComplianceResult(True, "All compliance checks passed")


# California SB 1001 AI disclosure
CA_AI_DISCLOSURE_TEMPLATE = (
    "This is an automated AI assistant responding on behalf of {business_name}. "
)

# California area codes (comprehensive list)
CA_AREA_CODES = {
    "209", "213", "279", "310", "323", "341", "350", "408", "415", "424",
    "442", "510", "530", "559", "562", "619", "626", "628", "650", "657",
    "661", "669", "707", "714", "747", "760", "805", "818", "820", "831",
    "840", "858", "909", "916", "925", "949", "951",
}


def is_california_number(phone: str) -> bool:
    """Check if a phone number has a California area code."""
    if not phone or len(phone) < 5:
        return False
    # E.164 format: +1NXXNXXXXXX — area code is digits 2-4 (0-indexed)
    if phone.startswith("+1") and len(phone) >= 5:
        area_code = phone[2:5]
        return area_code in CA_AREA_CODES
    return False


def needs_ai_disclosure(
    phone: str,
    state_code: Optional[str] = None,
    ai_disclosure_sent: bool = False,
) -> bool:
    """
    Check if California SB 1001 AI disclosure is needed.
    Required on first message to California numbers.
    """
    if ai_disclosure_sent:
        return False

    # Check by state code first (most reliable)
    if state_code == "CA":
        return True

    # Fall back to area code detection
    return is_california_number(phone)


def get_ai_disclosure(business_name: str) -> str:
    """Get the AI disclosure text for California SB 1001."""
    return CA_AI_DISCLOSURE_TEMPLATE.format(business_name=business_name)
