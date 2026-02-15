"""
Compliance tests — EVERY TCPA rule must have a test.
TCPA penalties: $500/violation minimum, $1,500 willful, NO CAP.
"""
import pytest
from datetime import datetime, time
from zoneinfo import ZoneInfo
from src.services.compliance import (
    is_stop_keyword,
    check_consent,
    check_quiet_hours,
    check_message_limits,
    check_content_compliance,
    full_compliance_check,
)


# === STOP KEYWORD TESTS ===

class TestStopKeywords:
    def test_stop(self):
        assert is_stop_keyword("STOP") is True

    def test_stop_lowercase(self):
        assert is_stop_keyword("stop") is True

    def test_unsubscribe(self):
        assert is_stop_keyword("UNSUBSCRIBE") is True

    def test_cancel(self):
        assert is_stop_keyword("CANCEL") is True

    def test_end(self):
        assert is_stop_keyword("END") is True

    def test_quit(self):
        assert is_stop_keyword("QUIT") is True

    def test_opt_out_hyphen(self):
        assert is_stop_keyword("opt-out") is True

    def test_optout(self):
        assert is_stop_keyword("optout") is True

    def test_remove(self):
        assert is_stop_keyword("REMOVE") is True

    def test_stop_with_whitespace(self):
        assert is_stop_keyword("  STOP  ") is True

    def test_normal_message_not_stop(self):
        assert is_stop_keyword("I need AC repair") is False

    def test_stop_in_sentence_not_stop(self):
        """'STOP' embedded in a sentence should NOT trigger opt-out."""
        assert is_stop_keyword("Please don't stop the service") is False

    def test_empty_string_not_stop(self):
        assert is_stop_keyword("") is False


# === CONSENT TESTS ===

class TestConsent:
    def test_opted_out_blocked(self):
        """Opted-out phone must be blocked from ALL messages."""
        result = check_consent(has_consent=True, consent_type="pewc", is_opted_out=True)
        assert result.allowed is False
        assert "opted out" in result.reason.lower()

    def test_no_consent_blocked(self):
        """No consent record must block all messages."""
        result = check_consent(has_consent=False)
        assert result.allowed is False
        assert "no consent" in result.reason.lower()

    def test_marketing_without_pewc_blocked(self):
        """Marketing messages require PEWC, not just PEC."""
        result = check_consent(
            has_consent=True, consent_type="pec", is_marketing=True
        )
        assert result.allowed is False
        assert "pewc" in result.reason.lower()

    def test_marketing_with_pewc_allowed(self):
        result = check_consent(
            has_consent=True, consent_type="pewc", is_marketing=True
        )
        assert result.allowed is True

    def test_informational_with_pec_allowed(self):
        result = check_consent(
            has_consent=True, consent_type="pec", is_marketing=False
        )
        assert result.allowed is True

    def test_valid_consent_allowed(self):
        result = check_consent(has_consent=True, consent_type="pewc")
        assert result.allowed is True


# === QUIET HOURS TESTS ===

class TestQuietHours:
    def test_federal_before_8am_blocked(self):
        """Federal TCPA: No messages before 8 AM local time."""
        now = datetime(2026, 2, 14, 7, 30, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="NY", now=now)
        assert result.allowed is False
        assert "8 AM" in result.reason

    def test_federal_after_9pm_blocked(self):
        """Federal TCPA: No messages after 9 PM local time."""
        now = datetime(2026, 2, 14, 21, 30, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="NY", now=now)
        assert result.allowed is False

    def test_federal_during_hours_allowed(self):
        now = datetime(2026, 2, 14, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="NY", now=now)
        assert result.allowed is True

    def test_texas_sunday_before_noon_blocked(self):
        """Texas SB 140: Sunday texts only noon-9 PM."""
        # Feb 15, 2026 is a Sunday
        now = datetime(2026, 2, 15, 10, 0, tzinfo=ZoneInfo("America/Chicago"))
        result = check_quiet_hours(state_code="TX", now=now)
        assert result.allowed is False
        assert "Texas" in result.reason or "Sunday" in result.reason

    def test_texas_sunday_after_noon_allowed(self):
        now = datetime(2026, 2, 15, 14, 0, tzinfo=ZoneInfo("America/Chicago"))
        result = check_quiet_hours(state_code="TX", now=now)
        assert result.allowed is True

    def test_florida_after_8pm_blocked(self):
        """Florida FTSA: Messages only 8 AM-8 PM."""
        now = datetime(2026, 2, 14, 20, 30, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="FL", now=now)
        assert result.allowed is False
        assert "Florida" in result.reason

    def test_florida_during_hours_allowed(self):
        now = datetime(2026, 2, 14, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="FL", now=now)
        assert result.allowed is True

    def test_emergency_bypasses_quiet_hours(self):
        """Emergency messages bypass ALL quiet hours (life safety exception)."""
        now = datetime(2026, 2, 14, 3, 0, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="NY", is_emergency=True, now=now)
        assert result.allowed is True
        assert "emergency" in result.reason.lower()

    def test_emergency_bypasses_texas_sunday(self):
        now = datetime(2026, 2, 15, 8, 0, tzinfo=ZoneInfo("America/Chicago"))
        result = check_quiet_hours(state_code="TX", is_emergency=True, now=now)
        assert result.allowed is True

    def test_emergency_bypasses_florida_hours(self):
        now = datetime(2026, 2, 14, 22, 0, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="FL", is_emergency=True, now=now)
        assert result.allowed is True


# === MESSAGE LIMIT TESTS ===

class TestMessageLimits:
    def test_max_cold_outreach_enforced(self):
        """Max 3 cold outreach messages per lead, ever."""
        result = check_message_limits(cold_outreach_count=3, max_cold_followups=3)
        assert result.allowed is False
        assert "max" in result.reason.lower()

    def test_under_limit_allowed(self):
        result = check_message_limits(cold_outreach_count=1, max_cold_followups=3)
        assert result.allowed is True

    def test_reply_doesnt_count(self):
        """Replies to inbound messages don't count against the cold limit."""
        result = check_message_limits(
            cold_outreach_count=5, is_reply_to_inbound=True
        )
        assert result.allowed is True

    def test_zero_outreach_allowed(self):
        result = check_message_limits(cold_outreach_count=0)
        assert result.allowed is True

    def test_exactly_at_limit_blocked(self):
        result = check_message_limits(cold_outreach_count=3, max_cold_followups=3)
        assert result.allowed is False


# === CONTENT COMPLIANCE TESTS ===

class TestContentCompliance:
    def test_first_message_missing_stop_blocked(self):
        """First message MUST include 'Reply STOP to opt out'."""
        result = check_content_compliance(
            "Hi! We got your request.", is_first_message=True, business_name="ACME HVAC"
        )
        assert result.allowed is False
        assert "stop" in result.reason.lower()

    def test_first_message_missing_business_name_blocked(self):
        """First message MUST include business name."""
        result = check_content_compliance(
            "Hi! Reply STOP to opt out.", is_first_message=True, business_name="ACME HVAC"
        )
        assert result.allowed is False
        assert "business name" in result.reason.lower()

    def test_first_message_complete_allowed(self):
        result = check_content_compliance(
            "Hi from ACME HVAC! We got your request. Reply STOP to opt out.",
            is_first_message=True,
            business_name="ACME HVAC",
        )
        assert result.allowed is True

    def test_url_shortener_blocked(self):
        """URL shorteners are blocked by carriers."""
        result = check_content_compliance("Check out http://bit.ly/abc123")
        assert result.allowed is False
        assert "shortener" in result.reason.lower()

    def test_tinyurl_blocked(self):
        result = check_content_compliance("Visit tinyurl.com/abc")
        assert result.allowed is False

    def test_normal_url_allowed(self):
        result = check_content_compliance("Visit https://acmehvac.com/schedule")
        assert result.allowed is True

    def test_non_first_message_no_stop_required(self):
        """Non-first messages don't need STOP language."""
        result = check_content_compliance(
            "When would you like us to come out?", is_first_message=False
        )
        assert result.allowed is True


# === FULL COMPLIANCE CHECK ===

class TestFullComplianceCheck:
    def test_all_passing(self):
        now = datetime(2026, 2, 14, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        result = full_compliance_check(
            has_consent=True,
            consent_type="pewc",
            is_opted_out=False,
            state_code="TX",
            cold_outreach_count=0,
            message="Hi from ACME HVAC! How can we help? Reply STOP to opt out.",
            is_first_message=True,
            business_name="ACME HVAC",
            now=now,
        )
        assert result.allowed is True

    def test_opt_out_blocks_everything(self):
        result = full_compliance_check(
            has_consent=True,
            consent_type="pewc",
            is_opted_out=True,
            message="Hi!",
        )
        assert result.allowed is False
        assert "opted out" in result.reason.lower()
