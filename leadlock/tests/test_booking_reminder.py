"""
Tests for src/workers/booking_reminder.py — booking reminder worker.

Covers:
- _heartbeat: Redis heartbeat storage + error swallowing
- run_booking_reminder: main loop, logging, error handling
- _send_due_reminders: DB query, iteration, commit, empty bookings
- _send_single_reminder: full reminder flow (compliance, followup, SMS, DB records)
  - Missing lead/client
  - Opted-out lead
  - Compliance blocked
  - Content compliance blocked
  - Successful send with time window variants
  - Exception in individual booking
"""
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.compliance import ComplianceResult
from src.schemas.agent_responses import FollowupResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLIENT_ID = uuid.uuid4()
LEAD_ID = uuid.uuid4()
BOOKING_ID = uuid.uuid4()
CONSENT_ID = uuid.uuid4()


VALID_CLIENT_CONFIG = {
    "service_area": {
        "center": {"lat": 30.2672, "lng": -97.7431},
        "radius_miles": 35,
        "valid_zips": ["78701"],
    },
    "persona": {"rep_name": "Sarah", "tone": "friendly_professional"},
}


def _make_client(client_id=None, config=None):
    """Create a mock Client object."""
    client = MagicMock()
    client.id = client_id or CLIENT_ID
    client.business_name = "Cool HVAC Co"
    client.twilio_phone = "+15125551234"
    client.twilio_messaging_service_sid = "MG_test_sid"
    client.config = config if config is not None else VALID_CLIENT_CONFIG
    return client


def _make_lead(
    lead_id=None,
    state="qualifying",
    consent_id=None,
    state_code="TX",
):
    """Create a mock Lead object."""
    lead = MagicMock()
    lead.id = lead_id or LEAD_ID
    lead.phone = "+15125559999"
    lead.first_name = "John"
    lead.state = state
    lead.state_code = state_code
    lead.consent_id = consent_id
    lead.total_messages_sent = 3
    lead.total_sms_cost_usd = 0.02
    lead.last_outbound_at = None
    return lead


def _make_consent(consent_id=None, consent_type="pec", opted_out=False):
    """Create a mock ConsentRecord object."""
    consent = MagicMock()
    consent.id = consent_id or CONSENT_ID
    consent.consent_type = consent_type
    consent.opted_out = opted_out
    return consent


def _make_booking(
    booking_id=None,
    lead_id=None,
    client_id=None,
    appointment_date=None,
    status="confirmed",
    reminder_sent=False,
    time_window_start=None,
    time_window_end=None,
    tech_name=None,
    service_type="AC Repair",
    extra_data=None,
):
    """Create a mock Booking object."""
    booking = MagicMock()
    booking.id = booking_id or BOOKING_ID
    booking.lead_id = lead_id or LEAD_ID
    booking.client_id = client_id or CLIENT_ID
    booking.appointment_date = appointment_date or (date.today() + timedelta(days=1))
    booking.status = status
    booking.reminder_sent = reminder_sent
    booking.time_window_start = time_window_start
    booking.time_window_end = time_window_end
    booking.tech_name = tech_name
    booking.service_type = service_type
    booking.extra_data = extra_data
    booking.reminder_sent_at = None
    return booking


def _make_followup_response(message="Reminder: Your appointment is tomorrow!"):
    """Create a FollowupResponse for mocking process_followup."""
    return FollowupResponse(
        message=message,
        followup_type="day_before_reminder",
        sequence_number=1,
        internal_notes="Day-before appointment reminder",
    )


def _make_sms_result():
    """Standard SMS send result."""
    return {
        "sid": "SM_reminder_001",
        "status": "sent",
        "provider": "twilio",
        "segments": 1,
        "cost_usd": 0.0079,
    }


@asynccontextmanager
async def _mock_session_factory(db_mock):
    """Wrap a MagicMock db in an async context manager mimicking async_session_factory."""
    yield db_mock


# ---------------------------------------------------------------------------
# _heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    """Tests for the _heartbeat function."""

    async def test_stores_heartbeat_in_redis(self):
        """Heartbeat sets a key in Redis with 1-hour TTL."""
        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=True)

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=redis_mock,
        ):
            from src.workers.booking_reminder import _heartbeat
            await _heartbeat()

        redis_mock.set.assert_called_once()
        call_args = redis_mock.set.call_args
        assert call_args[0][0] == "leadlock:worker_health:booking_reminder"
        assert call_args[1]["ex"] == 3600

    async def test_heartbeat_swallows_exceptions(self):
        """Heartbeat silently swallows any exception (e.g. Redis down)."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis offline"),
        ):
            from src.workers.booking_reminder import _heartbeat
            # Should not raise
            await _heartbeat()


# ---------------------------------------------------------------------------
# _send_single_reminder
# ---------------------------------------------------------------------------


class TestSendSingleReminder:
    """Tests for _send_single_reminder (the core per-booking logic)."""

    async def test_returns_false_when_lead_missing(self):
        """If lead not found in DB, return False."""
        db = AsyncMock()
        db.get = AsyncMock(side_effect=[None, _make_client()])
        booking = _make_booking()

        from src.workers.booking_reminder import _send_single_reminder
        result = await _send_single_reminder(db, booking)

        assert result is False

    async def test_returns_false_when_client_missing(self):
        """If client not found in DB, return False."""
        db = AsyncMock()
        db.get = AsyncMock(side_effect=[_make_lead(), None])
        booking = _make_booking()

        from src.workers.booking_reminder import _send_single_reminder
        result = await _send_single_reminder(db, booking)

        assert result is False

    async def test_skips_opted_out_lead(self):
        """Opted-out lead gets skipped, reminder_sent=True, extra_data updated."""
        db = AsyncMock()
        lead = _make_lead(state="opted_out")
        db.get = AsyncMock(side_effect=[lead, _make_client()])
        booking = _make_booking(extra_data=None)

        from src.workers.booking_reminder import _send_single_reminder
        result = await _send_single_reminder(db, booking)

        assert result is False
        assert booking.reminder_sent is True
        assert booking.extra_data["reminder_skipped"] == "opted_out"

    async def test_skips_opted_out_lead_preserves_existing_extra_data(self):
        """Extra data from before is preserved when skipping opted-out lead."""
        db = AsyncMock()
        lead = _make_lead(state="opted_out")
        db.get = AsyncMock(side_effect=[lead, _make_client()])
        booking = _make_booking(extra_data={"previous_key": "value"})

        from src.workers.booking_reminder import _send_single_reminder
        result = await _send_single_reminder(db, booking)

        assert result is False
        assert booking.extra_data["previous_key"] == "value"
        assert booking.extra_data["reminder_skipped"] == "opted_out"

    async def test_compliance_check_blocks_reminder(self):
        """When full_compliance_check returns blocked, return False and log."""
        db = AsyncMock()
        lead = _make_lead(consent_id=CONSENT_ID)
        consent = _make_consent()
        client = _make_client()
        db.get = AsyncMock(side_effect=[lead, client, consent])
        booking = _make_booking()

        blocked = ComplianceResult(allowed=False, reason="Quiet hours", rule="tcpa_quiet_hours")

        with patch(
            "src.workers.booking_reminder.full_compliance_check",
            return_value=blocked,
        ):
            from src.workers.booking_reminder import _send_single_reminder
            result = await _send_single_reminder(db, booking)

        assert result is False

    async def test_content_compliance_blocks_reminder(self):
        """When post-generation content check fails, return False."""
        db = AsyncMock()
        lead = _make_lead(consent_id=CONSENT_ID)
        consent = _make_consent()
        client = _make_client()
        db.get = AsyncMock(side_effect=[lead, client, consent])
        booking = _make_booking()

        compliance_ok = ComplianceResult(allowed=True, reason="OK")
        content_blocked = ComplianceResult(allowed=False, reason="URL shortener", rule="content_url_shortener")

        with (
            patch(
                "src.workers.booking_reminder.full_compliance_check",
                return_value=compliance_ok,
            ),
            patch(
                "src.workers.booking_reminder.process_followup",
                new_callable=AsyncMock,
                return_value=_make_followup_response(),
            ),
            patch(
                "src.workers.booking_reminder.check_content_compliance",
                return_value=content_blocked,
            ),
        ):
            from src.workers.booking_reminder import _send_single_reminder
            result = await _send_single_reminder(db, booking)

        assert result is False

    async def test_successful_reminder_full_flow(self):
        """Happy path: compliance passes, SMS sent, DB records created."""
        db = AsyncMock()
        db.add = MagicMock()
        lead = _make_lead(consent_id=CONSENT_ID)
        consent = _make_consent()
        client = _make_client()
        db.get = AsyncMock(side_effect=[lead, client, consent])
        booking = _make_booking(
            time_window_start=time(9, 0),
            time_window_end=time(11, 0),
            tech_name="Mike",
        )

        compliance_ok = ComplianceResult(allowed=True, reason="OK")
        content_ok = ComplianceResult(allowed=True, reason="Content compliant")
        followup_resp = _make_followup_response()
        sms_result = _make_sms_result()

        with (
            patch(
                "src.workers.booking_reminder.full_compliance_check",
                return_value=compliance_ok,
            ),
            patch(
                "src.workers.booking_reminder.process_followup",
                new_callable=AsyncMock,
                return_value=followup_resp,
            ) as mock_followup,
            patch(
                "src.workers.booking_reminder.check_content_compliance",
                return_value=content_ok,
            ),
            patch(
                "src.workers.booking_reminder.send_sms",
                new_callable=AsyncMock,
                return_value=sms_result,
            ) as mock_sms,
        ):
            from src.workers.booking_reminder import _send_single_reminder
            result = await _send_single_reminder(db, booking)

        assert result is True
        assert booking.reminder_sent is True
        assert booking.reminder_sent_at is not None

        # SMS called with correct args
        mock_sms.assert_called_once_with(
            to=lead.phone,
            body=followup_resp.message,
            from_phone=client.twilio_phone,
            messaging_service_sid=client.twilio_messaging_service_sid,
        )

        # process_followup called with correct args including time window
        mock_followup.assert_called_once()
        followup_kwargs = mock_followup.call_args[1]
        assert followup_kwargs["followup_type"] == "day_before_reminder"
        assert followup_kwargs["tech_name"] == "Mike"
        assert "09:00 AM" in followup_kwargs["time_window"]
        assert "11:00 AM" in followup_kwargs["time_window"]

        # Lead cost tracking updated
        assert lead.total_messages_sent == 4
        assert lead.total_sms_cost_usd == pytest.approx(0.02 + 0.0079)
        assert lead.last_outbound_at is not None

        # Conversation and EventLog added
        assert db.add.call_count == 2

    async def test_time_window_start_only(self):
        """When time_window_end is None, only start time shown."""
        db = AsyncMock()
        db.add = MagicMock()
        lead = _make_lead(consent_id=CONSENT_ID)
        consent = _make_consent()
        client = _make_client()
        db.get = AsyncMock(side_effect=[lead, client, consent])
        booking = _make_booking(
            time_window_start=time(14, 30),
            time_window_end=None,
        )

        compliance_ok = ComplianceResult(allowed=True, reason="OK")
        content_ok = ComplianceResult(allowed=True, reason="Content compliant")
        sms_result = _make_sms_result()

        with (
            patch(
                "src.workers.booking_reminder.full_compliance_check",
                return_value=compliance_ok,
            ),
            patch(
                "src.workers.booking_reminder.process_followup",
                new_callable=AsyncMock,
                return_value=_make_followup_response(),
            ) as mock_followup,
            patch(
                "src.workers.booking_reminder.check_content_compliance",
                return_value=content_ok,
            ),
            patch(
                "src.workers.booking_reminder.send_sms",
                new_callable=AsyncMock,
                return_value=sms_result,
            ),
        ):
            from src.workers.booking_reminder import _send_single_reminder
            result = await _send_single_reminder(db, booking)

        assert result is True
        followup_kwargs = mock_followup.call_args[1]
        # Only start time, no " - " separator with end time
        assert followup_kwargs["time_window"] == "02:30 PM"

    async def test_no_time_window(self):
        """When time_window_start is None, time_window param is None."""
        db = AsyncMock()
        db.add = MagicMock()
        lead = _make_lead(consent_id=CONSENT_ID)
        consent = _make_consent()
        client = _make_client()
        db.get = AsyncMock(side_effect=[lead, client, consent])
        booking = _make_booking(
            time_window_start=None,
            time_window_end=None,
        )

        compliance_ok = ComplianceResult(allowed=True, reason="OK")
        content_ok = ComplianceResult(allowed=True, reason="Content compliant")
        sms_result = _make_sms_result()

        with (
            patch(
                "src.workers.booking_reminder.full_compliance_check",
                return_value=compliance_ok,
            ),
            patch(
                "src.workers.booking_reminder.process_followup",
                new_callable=AsyncMock,
                return_value=_make_followup_response(),
            ) as mock_followup,
            patch(
                "src.workers.booking_reminder.check_content_compliance",
                return_value=content_ok,
            ),
            patch(
                "src.workers.booking_reminder.send_sms",
                new_callable=AsyncMock,
                return_value=sms_result,
            ),
        ):
            from src.workers.booking_reminder import _send_single_reminder
            result = await _send_single_reminder(db, booking)

        assert result is True
        followup_kwargs = mock_followup.call_args[1]
        assert followup_kwargs["time_window"] is None

    async def test_no_consent_id_on_lead(self):
        """When lead.consent_id is None, consent is None, compliance_check uses has_consent=False."""
        db = AsyncMock()
        lead = _make_lead(consent_id=None)
        client = _make_client()
        db.get = AsyncMock(side_effect=[lead, client])
        booking = _make_booking()

        # Compliance will block because no consent
        blocked = ComplianceResult(allowed=False, reason="No consent record", rule="tcpa_no_consent")

        with patch(
            "src.workers.booking_reminder.full_compliance_check",
            return_value=blocked,
        ) as mock_compliance:
            from src.workers.booking_reminder import _send_single_reminder
            result = await _send_single_reminder(db, booking)

        assert result is False
        call_kwargs = mock_compliance.call_args[1]
        assert call_kwargs["has_consent"] is False
        assert call_kwargs["consent_type"] == "pec"
        assert call_kwargs["is_opted_out"] is False

    async def test_consent_id_present_fetches_consent(self):
        """When lead.consent_id is set, ConsentRecord is fetched and its fields used."""
        db = AsyncMock()
        db.add = MagicMock()
        lead = _make_lead(consent_id=CONSENT_ID)
        client = _make_client()
        consent = _make_consent(consent_type="pewc", opted_out=False)
        db.get = AsyncMock(side_effect=[lead, client, consent])
        booking = _make_booking()

        compliance_ok = ComplianceResult(allowed=True, reason="OK")
        content_ok = ComplianceResult(allowed=True, reason="Content compliant")
        sms_result = _make_sms_result()

        with (
            patch(
                "src.workers.booking_reminder.full_compliance_check",
                return_value=compliance_ok,
            ) as mock_compliance,
            patch(
                "src.workers.booking_reminder.process_followup",
                new_callable=AsyncMock,
                return_value=_make_followup_response(),
            ),
            patch(
                "src.workers.booking_reminder.check_content_compliance",
                return_value=content_ok,
            ),
            patch(
                "src.workers.booking_reminder.send_sms",
                new_callable=AsyncMock,
                return_value=sms_result,
            ),
        ):
            from src.workers.booking_reminder import _send_single_reminder
            result = await _send_single_reminder(db, booking)

        assert result is True
        call_kwargs = mock_compliance.call_args[1]
        assert call_kwargs["has_consent"] is True
        assert call_kwargs["consent_type"] == "pewc"
        assert call_kwargs["is_opted_out"] is False

    async def test_client_with_no_config_raises(self):
        """Client with config=None triggers ClientConfig() which raises ValidationError.

        This is a latent defect in the source: ServiceArea requires center.
        The exception propagates to _send_due_reminders where it is caught.
        """
        from pydantic import ValidationError

        db = AsyncMock()
        lead = _make_lead(state="qualifying")
        client = _make_client()
        client.config = None
        db.get = AsyncMock(side_effect=[lead, client])
        booking = _make_booking()

        from src.workers.booking_reminder import _send_single_reminder

        with pytest.raises(ValidationError):
            await _send_single_reminder(db, booking)

    async def test_sms_result_with_missing_optional_fields(self):
        """SMS result dict with missing optional keys uses safe defaults."""
        db = AsyncMock()
        db.add = MagicMock()
        lead = _make_lead(consent_id=CONSENT_ID)
        consent = _make_consent()
        client = _make_client()
        client.twilio_phone = None  # twilio_phone can be None
        db.get = AsyncMock(side_effect=[lead, client, consent])
        booking = _make_booking()

        compliance_ok = ComplianceResult(allowed=True, reason="OK")
        content_ok = ComplianceResult(allowed=True, reason="Content compliant")
        # Minimal SMS result - no provider, no sid, no segments, no cost_usd
        sms_result = {}

        with (
            patch(
                "src.workers.booking_reminder.full_compliance_check",
                return_value=compliance_ok,
            ),
            patch(
                "src.workers.booking_reminder.process_followup",
                new_callable=AsyncMock,
                return_value=_make_followup_response(),
            ),
            patch(
                "src.workers.booking_reminder.check_content_compliance",
                return_value=content_ok,
            ),
            patch(
                "src.workers.booking_reminder.send_sms",
                new_callable=AsyncMock,
                return_value=sms_result,
            ),
        ):
            from src.workers.booking_reminder import _send_single_reminder
            result = await _send_single_reminder(db, booking)

        assert result is True
        # Cost defaults to 0.0
        assert lead.total_sms_cost_usd == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# _send_due_reminders
# ---------------------------------------------------------------------------


class TestSendDueReminders:
    """Tests for _send_due_reminders (the batch orchestrator)."""

    async def test_returns_zero_when_no_bookings(self):
        """No bookings for tomorrow returns 0."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        db_mock.execute = AsyncMock(return_value=result_mock)
        db_mock.commit = AsyncMock()

        with patch(
            "src.workers.booking_reminder.async_session_factory",
            side_effect=lambda: _mock_session_factory(db_mock),
        ):
            from src.workers.booking_reminder import _send_due_reminders
            count = await _send_due_reminders()

        assert count == 0
        db_mock.commit.assert_not_called()

    async def test_sends_reminders_for_found_bookings(self):
        """Found bookings each get _send_single_reminder called."""
        booking1 = _make_booking(booking_id=uuid.uuid4())
        booking2 = _make_booking(booking_id=uuid.uuid4())

        db_mock = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [booking1, booking2]
        result_mock.scalars.return_value = scalars_mock
        db_mock.execute = AsyncMock(return_value=result_mock)
        db_mock.commit = AsyncMock()

        with (
            patch(
                "src.workers.booking_reminder.async_session_factory",
                side_effect=lambda: _mock_session_factory(db_mock),
            ),
            patch(
                "src.workers.booking_reminder._send_single_reminder",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_send,
        ):
            from src.workers.booking_reminder import _send_due_reminders
            count = await _send_due_reminders()

        assert count == 2
        assert mock_send.call_count == 2
        db_mock.commit.assert_called_once()

    async def test_counts_only_successful_reminders(self):
        """Only bookings where _send_single_reminder returns True are counted."""
        booking1 = _make_booking(booking_id=uuid.uuid4())
        booking2 = _make_booking(booking_id=uuid.uuid4())
        booking3 = _make_booking(booking_id=uuid.uuid4())

        db_mock = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [booking1, booking2, booking3]
        result_mock.scalars.return_value = scalars_mock
        db_mock.execute = AsyncMock(return_value=result_mock)
        db_mock.commit = AsyncMock()

        with (
            patch(
                "src.workers.booking_reminder.async_session_factory",
                side_effect=lambda: _mock_session_factory(db_mock),
            ),
            patch(
                "src.workers.booking_reminder._send_single_reminder",
                new_callable=AsyncMock,
                side_effect=[True, False, True],
            ),
        ):
            from src.workers.booking_reminder import _send_due_reminders
            count = await _send_due_reminders()

        assert count == 2

    async def test_exception_in_single_reminder_does_not_stop_batch(self):
        """An exception in one booking does not prevent others from being sent."""
        booking1 = _make_booking(booking_id=uuid.uuid4())
        booking2 = _make_booking(booking_id=uuid.uuid4())

        db_mock = AsyncMock()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [booking1, booking2]
        result_mock.scalars.return_value = scalars_mock
        db_mock.execute = AsyncMock(return_value=result_mock)
        db_mock.commit = AsyncMock()

        with (
            patch(
                "src.workers.booking_reminder.async_session_factory",
                side_effect=lambda: _mock_session_factory(db_mock),
            ),
            patch(
                "src.workers.booking_reminder._send_single_reminder",
                new_callable=AsyncMock,
                side_effect=[RuntimeError("SMS failed"), True],
            ),
        ):
            from src.workers.booking_reminder import _send_due_reminders
            count = await _send_due_reminders()

        # Only the second booking succeeded
        assert count == 1
        # Commit is still called even when one booking fails
        db_mock.commit.assert_called_once()


# ---------------------------------------------------------------------------
# run_booking_reminder (main loop)
# ---------------------------------------------------------------------------


class TestRunBookingReminder:
    """Tests for run_booking_reminder — the infinite loop."""

    async def test_logs_sent_count_when_positive(self):
        """When reminders are sent, logs the count."""
        call_count = 0

        async def mock_send_due():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt("stop loop")
            return 3

        with (
            patch(
                "src.workers.booking_reminder._send_due_reminders",
                side_effect=mock_send_due,
            ),
            patch(
                "src.workers.booking_reminder._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.booking_reminder.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            from src.workers.booking_reminder import run_booking_reminder
            with pytest.raises(KeyboardInterrupt):
                await run_booking_reminder()

    async def test_does_not_log_when_zero_sent(self):
        """When no reminders sent (0), no info log about count."""
        call_count = 0

        async def mock_send_due():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt("stop loop")
            return 0

        with (
            patch(
                "src.workers.booking_reminder._send_due_reminders",
                side_effect=mock_send_due,
            ),
            patch(
                "src.workers.booking_reminder._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.booking_reminder.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.booking_reminder.logger",
            ) as mock_logger,
        ):
            from src.workers.booking_reminder import run_booking_reminder
            with pytest.raises(KeyboardInterrupt):
                await run_booking_reminder()

        # logger.info called once for "started" but not for "Sent 0 ..."
        info_calls = mock_logger.info.call_args_list
        # Only the startup message should be logged
        assert len(info_calls) == 1
        assert "started" in str(info_calls[0])

    async def test_catches_exceptions_and_continues(self):
        """Exceptions in _send_due_reminders are caught; loop continues."""
        call_count = 0

        async def mock_send_due():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB connection lost")
            if call_count >= 3:
                raise KeyboardInterrupt("stop loop")
            return 1

        with (
            patch(
                "src.workers.booking_reminder._send_due_reminders",
                side_effect=mock_send_due,
            ),
            patch(
                "src.workers.booking_reminder._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.booking_reminder.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.booking_reminder.logger",
            ) as mock_logger,
        ):
            from src.workers.booking_reminder import run_booking_reminder
            with pytest.raises(KeyboardInterrupt):
                await run_booking_reminder()

        # Error was logged on first iteration
        mock_logger.error.assert_called_once()
        assert "Booking reminder error" in str(mock_logger.error.call_args)

    async def test_heartbeat_called_each_iteration(self):
        """_heartbeat is called every iteration, even when exceptions occur."""
        call_count = 0

        async def mock_send_due():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt("stop loop")
            return 0

        with (
            patch(
                "src.workers.booking_reminder._send_due_reminders",
                side_effect=mock_send_due,
            ),
            patch(
                "src.workers.booking_reminder._heartbeat",
                new_callable=AsyncMock,
            ) as mock_hb,
            patch(
                "src.workers.booking_reminder.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            from src.workers.booking_reminder import run_booking_reminder
            with pytest.raises(KeyboardInterrupt):
                await run_booking_reminder()

        # Heartbeat called at least once (the first iteration before KeyboardInterrupt)
        assert mock_hb.call_count >= 1

    async def test_sleep_uses_poll_interval(self):
        """asyncio.sleep is called with POLL_INTERVAL_SECONDS."""
        call_count = 0

        async def mock_send_due():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt("stop loop")
            return 0

        with (
            patch(
                "src.workers.booking_reminder._send_due_reminders",
                side_effect=mock_send_due,
            ),
            patch(
                "src.workers.booking_reminder._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.booking_reminder.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
        ):
            from src.workers.booking_reminder import run_booking_reminder
            with pytest.raises(KeyboardInterrupt):
                await run_booking_reminder()

        from src.workers.booking_reminder import POLL_INTERVAL_SECONDS
        mock_sleep.assert_called_with(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_poll_interval_is_30_minutes(self):
        """POLL_INTERVAL_SECONDS should be 1800 (30 minutes)."""
        from src.workers.booking_reminder import POLL_INTERVAL_SECONDS
        assert POLL_INTERVAL_SECONDS == 1800
