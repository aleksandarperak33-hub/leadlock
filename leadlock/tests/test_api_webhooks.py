"""
Tests for src/api/webhooks.py - all webhook endpoint handlers.

Covers:
- Twilio inbound SMS (new lead + reply)
- Twilio delivery status callback
- Website form submission
- Google LSA lead
- Angi/HomeAdvisor lead
- Facebook Lead Ads
- Missed call notification
- Signature validation failures
- Rate limiting
- Payload validation / malformed input
- Internal helper functions (_record_webhook_event, _complete_webhook_event, etc.)
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import HTTPException

from src.api.webhooks import (
    _complete_webhook_event,
    _enforce_rate_limit,
    _record_webhook_event,
    _validate_signature,
    angi_webhook,
    facebook_webhook,
    google_lsa_webhook,
    missed_call_webhook,
    twilio_sms_webhook,
    twilio_status_webhook,
    website_form_webhook,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

CLIENT_ID = "11111111-1111-1111-1111-111111111111"
CLIENT_UUID = uuid.UUID(CLIENT_ID)


def _make_request(
    *,
    client_host: str = "127.0.0.1",
    headers: dict | None = None,
    body: bytes = b"",
    form_data: dict | None = None,
):
    """Build a mock FastAPI Request with the fields the webhook handlers access."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = client_host
    req.headers = headers or {}

    # body() returns a coroutine
    req.body = AsyncMock(return_value=body)

    # form() returns a coroutine that yields a dict-like form
    _form = form_data or {}
    form_mock = MagicMock()
    form_mock.get = _form.get
    form_mock.__iter__ = lambda s: iter(_form)
    form_mock.items = _form.items
    req.form = AsyncMock(return_value=form_mock)

    return req


def _make_client(client_id: str = CLIENT_ID) -> MagicMock:
    """Build a mock Client ORM object."""
    client = MagicMock()
    client.id = uuid.UUID(client_id)
    client.business_name = "Test HVAC Co"
    client.trade_type = "hvac"
    return client


def _make_lead(*, phone: str = "+15125559876", client_id: str = CLIENT_ID) -> MagicMock:
    """Build a mock Lead ORM object."""
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.client_id = uuid.UUID(client_id)
    lead.phone = phone
    lead.state = "qualifying"
    lead.created_at = datetime.now(timezone.utc)
    return lead


def _standard_patches():
    """Return a dict of commonly-used patch targets for all webhook tests."""
    return {
        "rate_limit": patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        "validate_sig": patch(
            "src.api.webhooks.validate_webhook_source",
            new_callable=AsyncMock,
            return_value=True,
        ),
        "compute_hash": patch(
            "src.api.webhooks.compute_payload_hash",
            return_value="a" * 64,
        ),
        "normalize_phone": patch(
            "src.api.webhooks.normalize_phone",
            return_value="+15125559876",
        ),
        "handle_new_lead": patch(
            "src.api.webhooks.handle_new_lead",
            new_callable=AsyncMock,
            return_value={"lead_id": str(uuid.uuid4()), "response_ms": 850},
        ),
        "handle_inbound_reply": patch(
            "src.api.webhooks.handle_inbound_reply",
            new_callable=AsyncMock,
            return_value={"lead_id": str(uuid.uuid4()), "response_ms": 450},
        ),
        "get_correlation_id": patch(
            "src.api.webhooks.get_correlation_id",
            return_value="test-correlation-id",
        ),
    }


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestRecordWebhookEvent:
    """Tests for _record_webhook_event helper."""

    @pytest.mark.asyncio
    async def test_creates_event_with_valid_client_id(self):
        db = AsyncMock()
        db.flush = AsyncMock()

        with patch("src.api.webhooks.get_correlation_id", return_value="cid-123"):
            event = await _record_webhook_event(
                db,
                source="twilio",
                event_type="inbound_sms",
                raw_payload={"Body": "hello"},
                payload_hash="abc123",
                client_id=CLIENT_ID,
            )

        assert event.source == "twilio"
        assert event.event_type == "inbound_sms"
        assert event.payload_hash == "abc123"
        assert event.client_id == CLIENT_UUID
        assert event.processing_status == "received"
        assert event.correlation_id == "cid-123"
        db.add.assert_called_once_with(event)
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_event_without_client_id(self):
        db = AsyncMock()
        db.flush = AsyncMock()

        with patch("src.api.webhooks.get_correlation_id", return_value=None):
            event = await _record_webhook_event(
                db,
                source="twilio",
                event_type="delivery_status",
                raw_payload={},
                payload_hash="def456",
                client_id=None,
            )

        assert event.client_id is None
        assert event.correlation_id is None

    @pytest.mark.asyncio
    async def test_invalid_client_id_uuid_does_not_raise(self):
        db = AsyncMock()
        db.flush = AsyncMock()

        with patch("src.api.webhooks.get_correlation_id", return_value=None):
            event = await _record_webhook_event(
                db,
                source="website",
                event_type="form_submission",
                raw_payload={},
                payload_hash="ghi789",
                client_id="not-a-uuid",
            )

        # Should gracefully set client_id to None instead of raising
        assert event.client_id is None


class TestCompleteWebhookEvent:
    """Tests for _complete_webhook_event helper."""

    @pytest.mark.asyncio
    async def test_marks_event_completed(self):
        event = MagicMock()
        await _complete_webhook_event(event)
        assert event.processing_status == "completed"
        assert event.error_message is None
        assert event.processed_at is not None

    @pytest.mark.asyncio
    async def test_marks_event_failed_with_error(self):
        event = MagicMock()
        await _complete_webhook_event(event, "failed", "Something broke")
        assert event.processing_status == "failed"
        assert event.error_message == "Something broke"
        assert event.processed_at is not None


class TestEnforceRateLimit:
    """Tests for _enforce_rate_limit helper."""

    @pytest.mark.asyncio
    async def test_allowed_request_does_not_raise(self):
        request = _make_request()
        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            # Should complete without exception
            await _enforce_rate_limit(request, CLIENT_ID)

    @pytest.mark.asyncio
    async def test_rate_limited_request_raises_429(self):
        request = _make_request()
        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(False, 30),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _enforce_rate_limit(request, CLIENT_ID)
            assert exc_info.value.status_code == 429
            assert exc_info.value.detail == "Rate limit exceeded"

    @pytest.mark.asyncio
    async def test_rate_limited_with_none_retry_after(self):
        request = _make_request()
        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(False, None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _enforce_rate_limit(request, CLIENT_ID)
            assert exc_info.value.status_code == 429
            assert exc_info.value.headers["Retry-After"] == "60"

    @pytest.mark.asyncio
    async def test_no_client_ip_uses_unknown(self):
        request = MagicMock()
        request.client = None
        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(True, None),
        ) as mock_rl:
            await _enforce_rate_limit(request, None)
            mock_rl.assert_awaited_once_with("unknown", None)


class TestValidateSignature:
    """Tests for _validate_signature helper."""

    @pytest.mark.asyncio
    async def test_valid_signature_passes(self):
        request = _make_request()
        with patch(
            "src.api.webhooks.validate_webhook_source",
            new_callable=AsyncMock,
            return_value=True,
        ):
            # Should not raise
            await _validate_signature("twilio", request, b"body", {"key": "val"})

    @pytest.mark.asyncio
    async def test_invalid_signature_raises_401(self):
        request = _make_request()
        with patch(
            "src.api.webhooks.validate_webhook_source",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _validate_signature("twilio", request, b"body")
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "Invalid webhook signature"

    @pytest.mark.asyncio
    async def test_invalid_signature_logs_ip(self):
        request = _make_request(client_host="10.0.0.42")
        with patch(
            "src.api.webhooks.validate_webhook_source",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(HTTPException):
                await _validate_signature("website", request, b"body")

    @pytest.mark.asyncio
    async def test_invalid_signature_with_no_client(self):
        request = MagicMock()
        request.client = None
        request.headers = {}
        with patch(
            "src.api.webhooks.validate_webhook_source",
            new_callable=AsyncMock,
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await _validate_signature("twilio", request, b"body")
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Twilio inbound SMS webhook
# ---------------------------------------------------------------------------


class TestTwilioSmsWebhook:
    """Tests for the twilio_sms_webhook endpoint."""

    @pytest.mark.asyncio
    async def test_new_lead_success(self):
        """A valid inbound SMS from a new phone number creates a new lead."""
        form_data = {
            "From": "+15125559876",
            "To": "+15125551234",
            "Body": "I need AC repair",
            "MessageSid": "SM_test_123",
        }
        body = b"From=%2B15125559876&Body=I+need+AC+repair"
        request = _make_request(body=body, form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()
        db.get = AsyncMock(return_value=_make_client())

        # No existing lead found
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=exec_result)

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await twilio_sms_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        assert result.lead_id is not None
        mock_new_lead.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_lead_reply(self):
        """An SMS from a phone that already has a lead triggers handle_inbound_reply."""
        form_data = {
            "From": "+15125559876",
            "Body": "Yes, tomorrow works!",
        }
        body = b"From=%2B15125559876&Body=Yes"
        request = _make_request(body=body, form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()

        existing_lead = _make_lead()
        mock_client = _make_client()
        db.get = AsyncMock(return_value=mock_client)

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = existing_lead
        db.execute = AsyncMock(return_value=exec_result)

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_inbound_reply"] as mock_reply,
            patches["get_correlation_id"],
        ):
            result = await twilio_sms_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        mock_reply.assert_awaited_once_with(
            db, existing_lead, mock_client, "Yes, tomorrow works!"
        )

    @pytest.mark.asyncio
    async def test_missing_from_field_returns_400(self):
        """Request missing the From field should return 400."""
        form_data = {"Body": "hello", "From": ""}
        request = _make_request(body=b"Body=hello", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await twilio_sms_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400
            assert "Missing From or Body" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_body_field_returns_400(self):
        """Request missing the Body field should return 400."""
        form_data = {"From": "+15125559876", "Body": ""}
        request = _make_request(body=b"From=%2B15125559876", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await twilio_sms_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_phone_returns_400(self):
        """An unrecognizable phone number should return 400."""
        form_data = {"From": "not-a-phone", "Body": "hello"}
        request = _make_request(body=b"From=bad&Body=hello", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patch("src.api.webhooks.normalize_phone", return_value=None),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await twilio_sms_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400
            assert "Invalid phone number" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_client_not_found_returns_404(self):
        """If client_id doesn't match a Client record, return 404."""
        form_data = {"From": "+15125559876", "Body": "hello"}
        request = _make_request(body=b"data", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()
        db.get = AsyncMock(return_value=None)

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await twilio_sms_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 404
            assert "Client not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self):
        """Invalid Twilio signature should return 401."""
        form_data = {"From": "+15125559876", "Body": "hi"}
        request = _make_request(body=b"data", form_data=form_data)
        db = AsyncMock()

        with (
            patch(
                "src.api.webhooks.check_webhook_rate_limits",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await twilio_sms_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_rate_limited_returns_429(self):
        """Rate-limited request should return 429."""
        request = _make_request()
        db = AsyncMock()

        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(False, 42),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await twilio_sms_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_internal_error_returns_500(self):
        """Unexpected exception during processing should return 500."""
        form_data = {"From": "+15125559876", "Body": "hello"}
        request = _make_request(body=b"data", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()
        db.get = AsyncMock(return_value=_make_client())

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=exec_result)

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patch(
                "src.api.webhooks.handle_new_lead",
                new_callable=AsyncMock,
                side_effect=RuntimeError("AI service down"),
            ),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await twilio_sms_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 500
            assert "Internal processing error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_response_includes_processing_time(self):
        """The response message should include processing time from conductor result."""
        form_data = {"From": "+15125559876", "Body": "Need plumbing help"}
        request = _make_request(body=b"data", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()
        db.get = AsyncMock(return_value=_make_client())

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=exec_result)

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patch(
                "src.api.webhooks.handle_new_lead",
                new_callable=AsyncMock,
                return_value={"lead_id": "test-id", "response_ms": 1234},
            ),
            patches["get_correlation_id"],
        ):
            result = await twilio_sms_webhook(CLIENT_ID, request, db)
            assert "1234" in result.message


# ---------------------------------------------------------------------------
# Twilio delivery status webhook
# ---------------------------------------------------------------------------


class TestTwilioStatusWebhook:
    """Tests for the twilio_status_webhook endpoint."""

    @pytest.mark.asyncio
    async def test_delivered_status_updates_conversation(self):
        """A 'delivered' status should set delivered_at on the conversation."""
        form_data = {
            "MessageSid": "SM_test_456",
            "MessageStatus": "delivered",
        }
        request = _make_request(body=b"data", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()

        conv = MagicMock()
        conv.from_phone = "+15125551234"
        conv.to_phone = "+15125559876"
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = conv
        db.execute = AsyncMock(return_value=exec_result)

        with (
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.webhooks.compute_payload_hash", return_value="h" * 64),
            patch("src.api.webhooks.get_correlation_id", return_value=None),
            patch(
                "src.services.deliverability.record_sms_outcome",
                new_callable=AsyncMock,
            ) as mock_record,
        ):
            result = await twilio_status_webhook(request, db)

        assert result == {"status": "ok"}
        assert conv.delivery_status == "delivered"
        assert conv.delivered_at is not None
        mock_record.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_status_records_error_code(self):
        """A 'failed' status with error code should update error fields."""
        form_data = {
            "MessageSid": "SM_fail_789",
            "MessageStatus": "failed",
            "ErrorCode": "30003",
            "ErrorMessage": "Unreachable destination handset",
        }
        request = _make_request(body=b"data", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()

        conv = MagicMock()
        conv.from_phone = "+15125551234"
        conv.to_phone = "+15125559876"
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = conv
        db.execute = AsyncMock(return_value=exec_result)

        with (
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.webhooks.compute_payload_hash", return_value="h" * 64),
            patch("src.api.webhooks.get_correlation_id", return_value=None),
            patch(
                "src.services.deliverability.record_sms_outcome",
                new_callable=AsyncMock,
            ),
        ):
            result = await twilio_status_webhook(request, db)

        assert result == {"status": "ok"}
        assert conv.delivery_status == "failed"
        assert conv.delivery_error_code == "30003"
        assert conv.delivery_error_message == "Unreachable destination handset"

    @pytest.mark.asyncio
    async def test_status_no_matching_conversation(self):
        """When no conversation matches the SID, the status webhook should still succeed."""
        form_data = {
            "MessageSid": "SM_unknown_999",
            "MessageStatus": "delivered",
        }
        request = _make_request(body=b"data", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=exec_result)

        with (
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.webhooks.compute_payload_hash", return_value="h" * 64),
            patch("src.api.webhooks.get_correlation_id", return_value=None),
        ):
            result = await twilio_status_webhook(request, db)

        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_status_missing_message_sid(self):
        """Missing MessageSid should still return ok (no crash)."""
        form_data = {"MessageSid": "", "MessageStatus": ""}
        request = _make_request(body=b"", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()

        with (
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.webhooks.compute_payload_hash", return_value="h" * 64),
            patch("src.api.webhooks.get_correlation_id", return_value=None),
        ):
            result = await twilio_status_webhook(request, db)

        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_status_invalid_signature_returns_401(self):
        """Invalid signature on status webhook should raise 401."""
        request = _make_request(body=b"data", form_data={"MessageSid": "SM123"})
        db = AsyncMock()

        with (
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await twilio_status_webhook(request, db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_status_internal_error_returns_error_status(self):
        """An unexpected exception returns {status: error} not 500."""
        form_data = {
            "MessageSid": "SM_boom",
            "MessageStatus": "delivered",
        }
        request = _make_request(body=b"data", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()

        db.execute = AsyncMock(side_effect=RuntimeError("DB connection lost"))

        with (
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("src.api.webhooks.compute_payload_hash", return_value="h" * 64),
            patch("src.api.webhooks.get_correlation_id", return_value=None),
        ):
            result = await twilio_status_webhook(request, db)

        # The status webhook catches all exceptions and returns error, not 500
        assert result == {"status": "error"}


# ---------------------------------------------------------------------------
# Website form webhook
# ---------------------------------------------------------------------------


class TestWebsiteFormWebhook:
    """Tests for the website_form_webhook endpoint."""

    @pytest.mark.asyncio
    async def test_valid_form_submission(self):
        """A complete web form submission should create a new lead."""
        payload = {
            "name": "John Smith",
            "phone": "+15125559876",
            "email": "john@example.com",
            "service": "AC Repair",
            "message": "AC stopped working",
            "zip": "78701",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await website_form_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        assert result.lead_id is not None
        mock_new_lead.assert_awaited_once()
        # Verify the envelope was constructed correctly
        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.source == "website"
        assert envelope_arg.consent_type == "pewc"
        assert envelope_arg.consent_method == "web_form"

    @pytest.mark.asyncio
    async def test_form_with_first_last_name(self):
        """Form using first_name/last_name instead of name should parse correctly."""
        payload = {
            "first_name": "Jane",
            "last_name": "Doe",
            "phone": "+15125559876",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await website_form_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.lead.first_name == "Jane"
        assert envelope_arg.lead.last_name == "Doe"

    @pytest.mark.asyncio
    async def test_form_name_splits_into_first_last(self):
        """When only 'name' is provided, it should be split into first and last."""
        payload = {"name": "Bob Builder", "phone": "+15125559876"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            await website_form_webhook(CLIENT_ID, request, db)

        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.lead.first_name == "Bob"
        assert envelope_arg.lead.last_name == "Builder"

    @pytest.mark.asyncio
    async def test_form_single_name(self):
        """A single-word name should only set first_name, not last_name."""
        payload = {"name": "Madonna", "phone": "+15125559876"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            await website_form_webhook(CLIENT_ID, request, db)

        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.lead.first_name == "Madonna"
        assert envelope_arg.lead.last_name is None

    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self):
        """Non-JSON body should return 400."""
        request = _make_request(body=b"not json at all")
        db = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await website_form_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400
            assert "Invalid JSON" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_phone_returns_400(self):
        """Invalid phone in form submission returns 400."""
        payload = {"phone": "not-a-phone"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patch("src.api.webhooks.normalize_phone", return_value=None),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await website_form_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400
            assert "Invalid phone number" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_form_with_utm_params(self):
        """UTM parameters should flow through to the LeadMetadata."""
        payload = {
            "phone": "+15125559876",
            "utm_source": "google",
            "utm_medium": "cpc",
            "utm_campaign": "spring_sale",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            await website_form_webhook(CLIENT_ID, request, db)

        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.metadata.utm_source == "google"
        assert envelope_arg.metadata.utm_medium == "cpc"
        assert envelope_arg.metadata.utm_campaign == "spring_sale"

    @pytest.mark.asyncio
    async def test_form_internal_error_returns_500(self):
        """Unexpected exception should return 500."""
        payload = {"phone": "+15125559876"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patch(
                "src.api.webhooks.handle_new_lead",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Boom"),
            ),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await website_form_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_form_rate_limited_returns_429(self):
        """Rate-limited form request should return 429."""
        request = _make_request(body=b'{"phone": "+15125559876"}')
        db = AsyncMock()

        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(False, 10),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await website_form_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# Google LSA webhook
# ---------------------------------------------------------------------------


class TestGoogleLsaWebhook:
    """Tests for the google_lsa_webhook endpoint."""

    @pytest.mark.asyncio
    async def test_valid_lsa_lead(self):
        """A valid Google LSA lead should be processed."""
        payload = {
            "lead_id": "lsa_abc123",
            "customer_name": "Jane Doe",
            "phone_number": "+15125559876",
            "email": "jane@example.com",
            "job_type": "hvac_repair",
            "postal_code": "78701",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await google_lsa_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.source == "google_lsa"
        assert envelope_arg.lead.first_name == "Jane"
        assert envelope_arg.lead.last_name == "Doe"
        assert envelope_arg.metadata.source_lead_id == "lsa_abc123"
        assert envelope_arg.consent_method == "google_lsa"

    @pytest.mark.asyncio
    async def test_lsa_single_name_customer(self):
        """Customer with a single name should only set first_name."""
        payload = {
            "lead_id": "lsa_single",
            "customer_name": "Cher",
            "phone_number": "+15125559876",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            await google_lsa_webhook(CLIENT_ID, request, db)

        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.lead.first_name == "Cher"
        assert envelope_arg.lead.last_name is None

    @pytest.mark.asyncio
    async def test_lsa_no_customer_name(self):
        """No customer name should result in None first/last name."""
        payload = {
            "lead_id": "lsa_anon",
            "phone_number": "+15125559876",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            await google_lsa_webhook(CLIENT_ID, request, db)

        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.lead.first_name is None
        assert envelope_arg.lead.last_name is None

    @pytest.mark.asyncio
    async def test_lsa_invalid_json_returns_400(self):
        """Non-JSON body should return 400."""
        request = _make_request(body=b"<xml>bad</xml>")
        db = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await google_lsa_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_lsa_invalid_phone_returns_400(self):
        """Invalid phone in LSA lead should return 400."""
        payload = {"lead_id": "lsa_bad", "phone_number": "invalid"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patch("src.api.webhooks.normalize_phone", return_value=None),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await google_lsa_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_lsa_internal_error_returns_500(self):
        """Conductor failure should return 500."""
        payload = {"lead_id": "lsa_err", "phone_number": "+15125559876"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patch(
                "src.api.webhooks.handle_new_lead",
                new_callable=AsyncMock,
                side_effect=RuntimeError("AI down"),
            ),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await google_lsa_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Angi webhook
# ---------------------------------------------------------------------------


class TestAngiWebhook:
    """Tests for the angi_webhook endpoint."""

    @pytest.mark.asyncio
    async def test_valid_angi_lead(self):
        """A valid Angi lead should be processed."""
        payload = {
            "leadId": "angi_xyz",
            "firstName": "Bob",
            "lastName": "Builder",
            "phone": "+15125559876",
            "email": "bob@builder.com",
            "serviceDescription": "Plumbing repair",
            "zipCode": "78702",
            "city": "Austin",
            "state": "TX",
            "urgency": "today",
            "propertyType": "residential",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await angi_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.source == "angi"
        assert envelope_arg.lead.first_name == "Bob"
        assert envelope_arg.lead.last_name == "Builder"
        assert envelope_arg.lead.service_type == "Plumbing repair"
        assert envelope_arg.metadata.source_lead_id == "angi_xyz"
        assert envelope_arg.consent_method == "angi"

    @pytest.mark.asyncio
    async def test_angi_invalid_json_returns_400(self):
        """Non-JSON body should return 400."""
        request = _make_request(body=b"garbage")
        db = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await angi_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_angi_invalid_phone_returns_400(self):
        """Invalid phone should return 400."""
        payload = {"leadId": "angi_bad", "phone": "invalid"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patch("src.api.webhooks.normalize_phone", return_value=None),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await angi_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_angi_internal_error_returns_500(self):
        """Processing failure should return 500."""
        payload = {"leadId": "angi_err", "phone": "+15125559876"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patch(
                "src.api.webhooks.handle_new_lead",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Fail"),
            ),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await angi_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Facebook webhook
# ---------------------------------------------------------------------------


class TestFacebookWebhook:
    """Tests for the facebook_webhook endpoint."""

    @pytest.mark.asyncio
    async def test_valid_facebook_lead(self):
        """A valid Facebook lead ads payload should create a lead."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "leadgen_data": {
                                    "phone": "+15125559876",
                                    "first_name": "Alice",
                                    "last_name": "Wonderland",
                                    "email": "alice@example.com",
                                    "leadgen_id": "fb_lead_123",
                                }
                            }
                        }
                    ]
                }
            ]
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await facebook_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        assert "1 lead(s)" in result.message
        mock_new_lead.assert_awaited_once()
        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.source == "facebook"
        assert envelope_arg.lead.first_name == "Alice"
        assert envelope_arg.consent_type == "pewc"
        assert envelope_arg.consent_method == "facebook"

    @pytest.mark.asyncio
    async def test_facebook_multiple_entries(self):
        """Multiple entries with valid leads should all be processed."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "phone": "+15125559876",
                                "first_name": "Lead1",
                                "id": "fb_1",
                            }
                        }
                    ]
                },
                {
                    "changes": [
                        {
                            "value": {
                                "phone_number": "+15125559999",
                                "first_name": "Lead2",
                                "id": "fb_2",
                            }
                        }
                    ]
                },
            ]
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await facebook_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        assert "2 lead(s)" in result.message
        assert mock_new_lead.await_count == 2

    @pytest.mark.asyncio
    async def test_facebook_empty_entries(self):
        """Empty entries list should return accepted with 'No entries' message."""
        payload = {"entry": []}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["get_correlation_id"],
        ):
            result = await facebook_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        assert result.message == "No entries"

    @pytest.mark.asyncio
    async def test_facebook_no_phone_in_lead_skipped(self):
        """Entries without phone numbers should be skipped."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "first_name": "NoPhone",
                                "email": "nophone@example.com",
                            }
                        }
                    ]
                }
            ]
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await facebook_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        assert result.message == "No valid leads found"
        mock_new_lead.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_facebook_invalid_phone_skipped(self):
        """Entries with invalid phone numbers should be skipped."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "phone": "invalid-phone",
                            }
                        }
                    ]
                }
            ]
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patch("src.api.webhooks.normalize_phone", return_value=None),
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await facebook_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        assert result.message == "No valid leads found"
        mock_new_lead.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_facebook_invalid_json_returns_400(self):
        """Non-JSON body should return 400."""
        request = _make_request(body=b"not json")
        db = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await facebook_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_facebook_uses_leadgen_data_subfield(self):
        """When leadgen_data is present inside value, it should be used."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "leadgen_data": {
                                    "phone": "+15125559876",
                                    "leadgen_id": "lg_123",
                                }
                            }
                        }
                    ]
                }
            ]
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            await facebook_webhook(CLIENT_ID, request, db)

        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.metadata.source_lead_id == "lg_123"

    @pytest.mark.asyncio
    async def test_facebook_uses_value_directly_when_no_leadgen_data(self):
        """When leadgen_data is not present, value dict should be used directly."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "phone": "+15125559876",
                                "first_name": "Direct",
                                "id": "val_lead_1",
                            }
                        }
                    ]
                }
            ]
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            await facebook_webhook(CLIENT_ID, request, db)

        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.lead.first_name == "Direct"
        assert envelope_arg.metadata.source_lead_id == "val_lead_1"

    @pytest.mark.asyncio
    async def test_facebook_internal_error_returns_500(self):
        """Internal error during Facebook lead processing should return 500."""
        payload = {
            "entry": [
                {
                    "changes": [
                        {"value": {"phone": "+15125559876"}}
                    ]
                }
            ]
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patch(
                "src.api.webhooks.handle_new_lead",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Boom"),
            ),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await facebook_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_facebook_no_entry_key(self):
        """Payload without 'entry' key should return accepted with no entries."""
        payload = {"other_field": "value"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["get_correlation_id"],
        ):
            result = await facebook_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        assert result.message == "No entries"


# ---------------------------------------------------------------------------
# Missed call webhook
# ---------------------------------------------------------------------------


class TestMissedCallWebhook:
    """Tests for the missed_call_webhook endpoint."""

    @pytest.mark.asyncio
    async def test_valid_missed_call(self):
        """A valid missed call should create a new lead."""
        payload = {
            "caller_phone": "+15125559876",
            "called_phone": "+15125551234",
            "call_duration": 0,
            "caller_name": "John Smith",
            "caller_city": "Austin",
            "caller_state": "TX",
            "caller_zip": "78701",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            result = await missed_call_webhook(CLIENT_ID, request, db)

        assert result.status == "accepted"
        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.source == "missed_call"
        assert envelope_arg.lead.first_name == "John"
        assert envelope_arg.lead.last_name == "Smith"
        assert envelope_arg.lead.city == "Austin"
        assert envelope_arg.lead.state_code == "TX"
        assert envelope_arg.lead.zip_code == "78701"
        assert envelope_arg.consent_method == "missed_call"

    @pytest.mark.asyncio
    async def test_missed_call_no_caller_name(self):
        """No caller name should result in None first/last name."""
        payload = {
            "caller_phone": "+15125559876",
            "called_phone": "+15125551234",
            "call_duration": 0,
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            await missed_call_webhook(CLIENT_ID, request, db)

        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.lead.first_name is None
        assert envelope_arg.lead.last_name is None

    @pytest.mark.asyncio
    async def test_missed_call_single_name(self):
        """Single-word caller name should only set first_name."""
        payload = {
            "caller_phone": "+15125559876",
            "called_phone": "+15125551234",
            "caller_name": "Prince",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"] as mock_new_lead,
            patches["get_correlation_id"],
        ):
            await missed_call_webhook(CLIENT_ID, request, db)

        envelope_arg = mock_new_lead.call_args[0][1]
        assert envelope_arg.lead.first_name == "Prince"
        assert envelope_arg.lead.last_name is None

    @pytest.mark.asyncio
    async def test_missed_call_invalid_json_returns_400(self):
        """Non-JSON body should return 400."""
        request = _make_request(body=b"not json")
        db = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await missed_call_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missed_call_invalid_phone_returns_400(self):
        """Invalid caller phone should return 400."""
        payload = {
            "caller_phone": "bad-number",
            "called_phone": "+15125551234",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patch("src.api.webhooks.normalize_phone", return_value=None),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await missed_call_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missed_call_internal_error_returns_500(self):
        """Internal error should return 500."""
        payload = {
            "caller_phone": "+15125559876",
            "called_phone": "+15125551234",
        }
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()
        db.flush = AsyncMock()

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patch(
                "src.api.webhooks.handle_new_lead",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Fail"),
            ),
            patches["get_correlation_id"],
        ):
            with pytest.raises(HTTPException) as exc_info:
                await missed_call_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Cross-cutting concerns
# ---------------------------------------------------------------------------


class TestSignatureValidationAcrossEndpoints:
    """Verify that each webhook endpoint rejects invalid signatures."""

    @pytest.mark.asyncio
    async def test_form_invalid_signature_returns_401(self):
        payload = {"phone": "+15125559876"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()

        with (
            patch(
                "src.api.webhooks.check_webhook_rate_limits",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("src.api.webhooks.compute_payload_hash", return_value="x" * 64),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await website_form_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_lsa_invalid_signature_returns_401(self):
        payload = {"lead_id": "lsa_1", "phone_number": "+15125559876"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()

        with (
            patch(
                "src.api.webhooks.check_webhook_rate_limits",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await google_lsa_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_angi_invalid_signature_returns_401(self):
        payload = {"leadId": "a1", "phone": "+15125559876"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()

        with (
            patch(
                "src.api.webhooks.check_webhook_rate_limits",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await angi_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_facebook_invalid_signature_returns_401(self):
        payload = {"entry": []}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()

        with (
            patch(
                "src.api.webhooks.check_webhook_rate_limits",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await facebook_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missed_call_invalid_signature_returns_401(self):
        payload = {"caller_phone": "+15125559876", "called_phone": "+15125551234"}
        body = json.dumps(payload).encode()
        request = _make_request(body=body)
        db = AsyncMock()

        with (
            patch(
                "src.api.webhooks.check_webhook_rate_limits",
                new_callable=AsyncMock,
                return_value=(True, None),
            ),
            patch(
                "src.api.webhooks.validate_webhook_source",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await missed_call_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 401


class TestRateLimitingAcrossEndpoints:
    """Verify rate limiting is enforced on all rate-limited endpoints."""

    @pytest.mark.asyncio
    async def test_lsa_rate_limited_returns_429(self):
        request = _make_request(body=b'{}')
        db = AsyncMock()

        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(False, 15),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await google_lsa_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_angi_rate_limited_returns_429(self):
        request = _make_request(body=b'{}')
        db = AsyncMock()

        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(False, 20),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await angi_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_facebook_rate_limited_returns_429(self):
        request = _make_request(body=b'{}')
        db = AsyncMock()

        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(False, 25),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await facebook_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_missed_call_rate_limited_returns_429(self):
        request = _make_request(body=b'{}')
        db = AsyncMock()

        with patch(
            "src.api.webhooks.check_webhook_rate_limits",
            new_callable=AsyncMock,
            return_value=(False, 30),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await missed_call_webhook(CLIENT_ID, request, db)
            assert exc_info.value.status_code == 429


class TestAuditTrailRecording:
    """Verify that webhook events are recorded for audit purposes."""

    @pytest.mark.asyncio
    async def test_twilio_sms_records_webhook_event(self):
        """The Twilio SMS handler should call db.add with a WebhookEvent."""
        form_data = {"From": "+15125559876", "Body": "test"}
        request = _make_request(body=b"data", form_data=form_data)
        db = AsyncMock()
        db.flush = AsyncMock()
        db.get = AsyncMock(return_value=_make_client())

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=exec_result)

        patches = _standard_patches()
        with (
            patches["rate_limit"],
            patches["validate_sig"],
            patches["compute_hash"],
            patches["normalize_phone"],
            patches["handle_new_lead"],
            patches["get_correlation_id"],
        ):
            await twilio_sms_webhook(CLIENT_ID, request, db)

        # db.add should have been called at least once (for the webhook event)
        assert db.add.called
        # First call arg should be a WebhookEvent
        from src.models.webhook_event import WebhookEvent
        first_add_arg = db.add.call_args_list[0][0][0]
        assert isinstance(first_add_arg, WebhookEvent)
        assert first_add_arg.source == "twilio"
        assert first_add_arg.event_type == "inbound_sms"
