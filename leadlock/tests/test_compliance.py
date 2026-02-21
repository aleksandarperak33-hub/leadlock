"""
Compliance tests - EVERY TCPA rule must have a test.
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
    is_california_number,
    needs_ai_disclosure,
    get_ai_disclosure,
    STOP_PHRASES,
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

    def test_quiet_hours_blocks(self):
        """Quiet hours should block within full_compliance_check."""
        now = datetime(2026, 2, 14, 3, 0, tzinfo=ZoneInfo("America/New_York"))
        result = full_compliance_check(
            has_consent=True,
            consent_type="pewc",
            state_code="NY",
            message="Test",
            now=now,
        )
        assert result.allowed is False
        assert "8 AM" in result.reason

    def test_message_limit_blocks(self):
        """Message limit should block within full_compliance_check."""
        now = datetime(2026, 2, 14, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        result = full_compliance_check(
            has_consent=True,
            consent_type="pewc",
            cold_outreach_count=3,
            max_cold_followups=3,
            message="Test",
            now=now,
        )
        assert result.allowed is False
        assert "max" in result.reason.lower()

    def test_content_compliance_blocks(self):
        """Content compliance should block within full_compliance_check."""
        now = datetime(2026, 2, 14, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        result = full_compliance_check(
            has_consent=True,
            consent_type="pewc",
            message="Hi there!",
            is_first_message=True,
            business_name="ACME",
            now=now,
        )
        assert result.allowed is False
        assert "stop" in result.reason.lower()

    def test_emergency_bypasses_quiet_hours_in_full_check(self):
        """Emergency should bypass quiet hours even in full_compliance_check."""
        now = datetime(2026, 2, 14, 3, 0, tzinfo=ZoneInfo("America/New_York"))
        result = full_compliance_check(
            has_consent=True,
            consent_type="pewc",
            state_code="NY",
            is_emergency=True,
            message="Emergency response",
            now=now,
        )
        assert result.allowed is True


# === STOP PHRASE TESTS (TCPA $500-$1,500/violation) ===

class TestStopPhrases:
    """Every phrase in STOP_PHRASES must be recognized as opt-out."""

    @pytest.mark.parametrize("phrase", STOP_PHRASES)
    def test_stop_phrase_detected(self, phrase):
        """Each STOP_PHRASES entry must trigger opt-out detection."""
        assert is_stop_keyword(phrase) is True, f"Failed to detect STOP phrase: '{phrase}'"

    @pytest.mark.parametrize("phrase", [
        "stop texting me please",
        "LEAVE ME ALONE",
        "Please stop contacting me",
        "I want out of this",
        "No more messages from you",
    ])
    def test_stop_phrase_in_context(self, phrase):
        assert is_stop_keyword(phrase) is True


class TestRepeatedCharacterStopDetection:
    """Layer 2: Repeated character collapsing (STOPPPP -> stop)."""

    def test_stopppp(self):
        assert is_stop_keyword("STOPPPP") is True

    def test_quiiit(self):
        assert is_stop_keyword("QUIIIT") is True

    def test_endddd(self):
        assert is_stop_keyword("ENDDDD") is True

    def test_cancellll(self):
        assert is_stop_keyword("CANCELLLL") is True

    def test_stooop(self):
        assert is_stop_keyword("STOOOP") is True


# === QUIET HOURS DEFAULT TIMEZONE ===

class TestQuietHoursDefaultTimezone:
    def test_no_state_code_defaults_to_eastern(self):
        """With no state_code, should default to Eastern timezone."""
        # 3 AM Eastern is quiet hours
        now = datetime(2026, 2, 14, 3, 0, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(now=now)
        assert result.allowed is False

    def test_no_state_code_during_business_hours(self):
        now = datetime(2026, 2, 14, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(now=now)
        assert result.allowed is True


# === FLORIDA HOLIDAY BLOCKING ===

class TestFloridaHolidayBlocking:
    def test_good_friday_2026_blocked(self):
        """Florida FTSA: No messages on Good Friday (April 3, 2026)."""
        # 12:00 PM on Good Friday 2026
        now = datetime(2026, 4, 3, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="FL", now=now)
        assert result.allowed is False
        assert "holiday" in result.reason.lower()

    def test_day_after_thanksgiving_blocked(self):
        """Florida FTSA: No messages on day after Thanksgiving (Nov 27, 2026)."""
        now = datetime(2026, 11, 27, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="FL", now=now)
        assert result.allowed is False
        assert "holiday" in result.reason.lower()

    def test_christmas_blocked(self):
        now = datetime(2026, 12, 25, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        result = check_quiet_hours(state_code="FL", now=now)
        assert result.allowed is False


# === CALIFORNIA SB 1001 AI DISCLOSURE ===

class TestCaliforniaAIDisclosure:
    def test_california_area_code_detected(self):
        assert is_california_number("+14155551234") is True  # 415 = SF

    def test_non_california_area_code(self):
        assert is_california_number("+15125551234") is False  # 512 = Austin TX

    def test_invalid_phone_returns_false(self):
        assert is_california_number("") is False
        assert is_california_number("+1") is False
        assert is_california_number(None) is False

    def test_needs_disclosure_for_ca_state_code(self):
        assert needs_ai_disclosure("+15125551234", state_code="CA") is True

    def test_needs_disclosure_for_ca_area_code(self):
        assert needs_ai_disclosure("+14155551234") is True

    def test_no_disclosure_for_tx(self):
        assert needs_ai_disclosure("+15125551234", state_code="TX") is False

    def test_no_disclosure_if_already_sent(self):
        assert needs_ai_disclosure("+14155551234", ai_disclosure_sent=True) is False

    def test_disclosure_text_includes_business_name(self):
        disclosure = get_ai_disclosure("Austin HVAC")
        assert "Austin HVAC" in disclosure
        assert "automated" in disclosure.lower() or "AI" in disclosure
