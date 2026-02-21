"""
Tests for src/services/outreach_sms.py - TCPA-compliant outreach SMS.
Covers: quiet hours by state, send flow, prerequisite validation, timezone mapping.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from zoneinfo import ZoneInfo

from src.services.outreach_sms import (
    is_within_sms_quiet_hours,
    send_outreach_sms,
    _get_prospect_timezone,
    STATE_TIMEZONES,
)


# ---------------------------------------------------------------------------
# _get_prospect_timezone
# ---------------------------------------------------------------------------

class TestGetProspectTimezone:
    def test_known_state_returns_correct_tz(self):
        tz = _get_prospect_timezone("TX")
        assert tz == ZoneInfo("America/Chicago")

    def test_known_state_lowercase(self):
        """State codes are uppercased internally."""
        tz = _get_prospect_timezone("fl")
        assert tz == ZoneInfo("America/New_York")

    def test_california(self):
        tz = _get_prospect_timezone("CA")
        assert tz == ZoneInfo("America/Los_Angeles")

    def test_unknown_state_defaults_to_central(self):
        tz = _get_prospect_timezone("ZZ")
        assert tz == ZoneInfo("America/Chicago")

    def test_none_state_defaults_to_central(self):
        tz = _get_prospect_timezone(None)
        assert tz == ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# is_within_sms_quiet_hours
# ---------------------------------------------------------------------------

class TestIsWithinSmsQuietHours:
    """Tests for TCPA quiet hours - returns True when sending IS allowed."""

    def _patch_now(self, hour, minute=0, weekday=0, tz_name="America/Chicago"):
        """Create a patch that makes datetime.now(tz) return a specific time.
        weekday: 0=Monday, 6=Sunday
        """
        fake_dt = datetime(2026, 2, 16 + weekday, hour, minute, tzinfo=ZoneInfo(tz_name))
        # We patch datetime.now at module level in the outreach_sms module
        return patch("src.services.outreach_sms.datetime") if False else None

    def test_general_allowed_10am(self):
        """10 AM local time is within sending hours (8am-9pm)."""
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 18, 10, 0, tzinfo=ZoneInfo("America/Chicago"))
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = is_within_sms_quiet_hours("TX")
        assert result is True

    def test_general_blocked_7am(self):
        """7 AM local time is before 8am - quiet hours."""
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 18, 7, 30, tzinfo=ZoneInfo("America/Chicago"))
            result = is_within_sms_quiet_hours("TX")
        assert result is False

    def test_general_blocked_10pm(self):
        """10 PM (22:00) is after 9pm - quiet hours."""
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 18, 22, 0, tzinfo=ZoneInfo("America/Chicago"))
            result = is_within_sms_quiet_hours("TX")
        assert result is False

    def test_florida_blocked_at_8pm(self):
        """Florida FTSA: 8pm (20:00) is NOT allowed (8am-8pm window)."""
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 18, 20, 0, tzinfo=ZoneInfo("America/New_York"))
            result = is_within_sms_quiet_hours("FL")
        assert result is False

    def test_florida_allowed_at_3pm(self):
        """Florida: 3 PM is within 8am-8pm window."""
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 18, 15, 0, tzinfo=ZoneInfo("America/New_York"))
            result = is_within_sms_quiet_hours("FL")
        assert result is True

    def test_texas_sunday_before_noon_blocked(self):
        """Texas SB 140: Sunday before noon is quiet hours."""
        # weekday() == 6 is Sunday
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            sunday = datetime(2026, 2, 22, 10, 0, tzinfo=ZoneInfo("America/Chicago"))
            # Ensure it's a Sunday (Feb 22 2026 is a Sunday)
            assert sunday.weekday() == 6
            mock_dt.now.return_value = sunday
            result = is_within_sms_quiet_hours("TX")
        assert result is False

    def test_texas_sunday_after_noon_allowed(self):
        """Texas SB 140: Sunday after noon is allowed (noon-9pm)."""
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            sunday = datetime(2026, 2, 22, 14, 0, tzinfo=ZoneInfo("America/Chicago"))
            assert sunday.weekday() == 6
            mock_dt.now.return_value = sunday
            result = is_within_sms_quiet_hours("TX")
        assert result is True

    def test_none_state_uses_central_time(self):
        """No state defaults to Central timezone with general 8am-9pm."""
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 18, 12, 0, tzinfo=ZoneInfo("America/Chicago"))
            result = is_within_sms_quiet_hours(None)
        assert result is True

    def test_general_boundary_8am_allowed(self):
        """Exactly 8:00 AM is allowed."""
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 18, 8, 0, tzinfo=ZoneInfo("America/Chicago"))
            result = is_within_sms_quiet_hours("TX")
        assert result is True

    def test_general_boundary_9pm_blocked(self):
        """Exactly 9:00 PM (21:00) is blocked (hour >= 21)."""
        with patch("src.services.outreach_sms.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 18, 21, 0, tzinfo=ZoneInfo("America/Chicago"))
            result = is_within_sms_quiet_hours("TX")
        assert result is False


# ---------------------------------------------------------------------------
# send_outreach_sms
# ---------------------------------------------------------------------------

class TestSendOutreachSms:
    """Test the full send flow with mocked Twilio and DB."""

    def _make_prospect(self, **overrides):
        """Build a mock Outreach prospect."""
        defaults = {
            "id": "aaaa1111-bbbb-cccc-dddd-eeee22223333",
            "prospect_phone": "+15129876543",
            "email_unsubscribed": False,
            "last_email_replied_at": datetime(2026, 2, 15, tzinfo=timezone.utc),
            "state_code": "TX",
            "total_cost_usd": 0.0,
            "updated_at": None,
        }
        defaults.update(overrides)
        prospect = MagicMock()
        for k, v in defaults.items():
            setattr(prospect, k, v)
        return prospect

    def _make_config(self, **overrides):
        """Build a mock SalesEngineConfig."""
        defaults = {
            "sms_from_phone": "+15121111111",
            "sms_after_email_reply": True,
        }
        defaults.update(overrides)
        config = MagicMock()
        for k, v in defaults.items():
            setattr(config, k, v)
        return config

    @pytest.mark.asyncio
    async def test_no_phone_returns_error(self):
        """Prospect without phone number returns error immediately."""
        db = AsyncMock()
        prospect = self._make_prospect(prospect_phone=None)
        config = self._make_config()

        result = await send_outreach_sms(db, prospect, config, "Follow up!")

        assert result["error"] == "Prospect has no phone number"

    @pytest.mark.asyncio
    async def test_unsubscribed_returns_error(self):
        """Unsubscribed prospect returns error."""
        db = AsyncMock()
        prospect = self._make_prospect(email_unsubscribed=True)
        config = self._make_config()

        result = await send_outreach_sms(db, prospect, config, "Follow up!")

        assert result["error"] == "Prospect is unsubscribed"

    @pytest.mark.asyncio
    async def test_no_prior_email_reply_returns_error(self):
        """TCPA: Cannot SMS without prior email reply consent."""
        db = AsyncMock()
        prospect = self._make_prospect(last_email_replied_at=None)
        config = self._make_config()

        result = await send_outreach_sms(db, prospect, config, "Follow up!")

        assert "TCPA" in result["error"]
        assert "no consent" in result["error"]

    @pytest.mark.asyncio
    async def test_no_from_phone_returns_error(self):
        """Missing sms_from_phone in config returns error."""
        db = AsyncMock()
        prospect = self._make_prospect()
        config = self._make_config(sms_from_phone=None)

        result = await send_outreach_sms(db, prospect, config, "Follow up!")

        assert "SMS from phone not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_quiet_hours_deferred(self):
        """During quiet hours, SMS is deferred."""
        db = AsyncMock()
        prospect = self._make_prospect()
        config = self._make_config()

        with patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=False):
            result = await send_outreach_sms(db, prospect, config, "Follow up!")

        assert "quiet hours" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_success_sends_sms(self):
        """Happy path: SMS sent via Twilio, record created, cost tracked."""
        db = AsyncMock()
        db.add = MagicMock()
        prospect = self._make_prospect()
        config = self._make_config()

        mock_message = MagicMock()
        mock_message.sid = "SM_test_outreach_123"

        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = "ACtest"
        mock_settings.twilio_auth_token = "authtest"

        mock_twilio = MagicMock()
        mock_twilio.messages.create = MagicMock(return_value=mock_message)

        with (
            patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=True),
            patch("src.services.outreach_sms.get_settings", return_value=mock_settings),
            patch("twilio.rest.Client", return_value=mock_twilio),
            patch("asyncio.get_running_loop") as mock_loop,
        ):
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_message)

            result = await send_outreach_sms(db, prospect, config, "Follow up!")

        assert result["status"] == "sent"
        assert result["twilio_sid"] == "SM_test_outreach_123"
        assert result["cost_usd"] == pytest.approx(0.0079)

        # SMS record was added to DB
        assert db.add.called

    @pytest.mark.asyncio
    async def test_twilio_failure_records_failed_sms(self):
        """When Twilio raises, a failed SMS record is still persisted."""
        db = AsyncMock()
        db.add = MagicMock()
        prospect = self._make_prospect()
        config = self._make_config()

        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = "ACtest"
        mock_settings.twilio_auth_token = "authtest"

        with (
            patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=True),
            patch("src.services.outreach_sms.get_settings", return_value=mock_settings),
            patch("twilio.rest.Client", side_effect=Exception("Twilio down")),
        ):
            result = await send_outreach_sms(db, prospect, config, "Follow up!")

        assert "Twilio send failed" in result["error"]
        # Failed record should still be added to DB
        assert db.add.called
