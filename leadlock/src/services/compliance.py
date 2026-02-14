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

# STOP keyword variants — must be recognized case-insensitively
STOP_KEYWORDS = {"stop", "unsubscribe", "cancel", "end", "quit", "opt-out", "optout", "remove"}

# Federal holidays where Florida restricts SMS (FTSA)
# Updated annually — these are 2026 dates
FLORIDA_HOLIDAYS = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Day
    "2026-02-16",  # Presidents' Day
    "2026-05-25",  # Memorial Day
    "2026-07-04",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-10-12",  # Columbus Day
    "2026-11-11",  # Veterans Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
}

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
    """Check if a message is a STOP/opt-out keyword."""
    normalized = message.strip().lower()
    return normalized in STOP_KEYWORDS


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
    date_str = now.strftime("%Y-%m-%d")

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
        if date_str in FLORIDA_HOLIDAYS:
            return ComplianceResult(
                False,
                f"Florida FTSA: No messages on state holidays ({date_str})",
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
