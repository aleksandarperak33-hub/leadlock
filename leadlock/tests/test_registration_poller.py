"""
Tests for src/workers/registration_poller.py - registration status poller.
Covers the full state machine: profile_pending, profile_approved,
brand_pending, brand_approved, campaign_pending, tf_verification_pending,
plus heartbeat, main loop, alert webhook, and error paths.
"""
import uuid
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from datetime import datetime, timezone

from src.models.client import Client
from src.workers.registration_poller import (
    _heartbeat,
    _advance_single_client,
    _handle_profile_pending,
    _handle_profile_approved,
    _handle_brand_pending,
    _handle_brand_approved,
    _handle_campaign_pending,
    _handle_tf_pending,
    _send_status_alert,
    poll_registration_statuses,
    run_registration_poller,
    POLL_INTERVAL_SECONDS,
    BATCH_LIMIT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(**overrides) -> Client:
    """Create a Client instance with sensible defaults for poller tests."""
    defaults = {
        "id": uuid.uuid4(),
        "business_name": "Test HVAC Co",
        "trade_type": "hvac",
        "is_active": True,
        "ten_dlc_status": "profile_pending",
        "ten_dlc_profile_sid": "BU_profile_123",
        "ten_dlc_brand_id": None,
        "ten_dlc_campaign_id": None,
        "ten_dlc_verification_sid": None,
        "twilio_messaging_service_sid": None,
        "config": {},
    }
    defaults.update(overrides)
    client = Client(**defaults)
    return client


# ---------------------------------------------------------------------------
# _heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:
    async def test_heartbeat_sets_redis_key(self):
        """Heartbeat stores UTC timestamp in Redis with 600s TTL."""
        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=True)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=redis_mock):
            await _heartbeat()

        redis_mock.set.assert_called_once()
        args, kwargs = redis_mock.set.call_args
        assert args[0] == "leadlock:worker_health:registration_poller"
        assert kwargs.get("ex") == 600

    async def test_heartbeat_suppresses_exceptions(self):
        """Heartbeat silently swallows errors (must not crash poller)."""
        with patch("src.utils.dedup.get_redis", side_effect=Exception("Redis down")):
            # Should not raise
            await _heartbeat()


# ---------------------------------------------------------------------------
# _handle_profile_pending
# ---------------------------------------------------------------------------

class TestHandleProfilePending:
    async def test_no_profile_sid_returns_early(self):
        """If client has no profile SID, do nothing."""
        client = _make_client(ten_dlc_profile_sid=None, ten_dlc_status="profile_pending")
        with patch(
            "src.workers.registration_poller.check_customer_profile_status",
            new_callable=AsyncMock,
        ) as mock_check:
            await _handle_profile_pending(client)
            mock_check.assert_not_called()
        assert client.ten_dlc_status == "profile_pending"

    async def test_api_error_no_change(self):
        """If the API returns an error, status stays unchanged."""
        client = _make_client(ten_dlc_status="profile_pending")
        with patch(
            "src.workers.registration_poller.check_customer_profile_status",
            new_callable=AsyncMock,
            return_value={"result": None, "error": "timeout"},
        ):
            await _handle_profile_pending(client)
        assert client.ten_dlc_status == "profile_pending"

    async def test_twilio_approved_advances(self):
        """Twilio-approved profile moves to profile_approved."""
        client = _make_client(ten_dlc_status="profile_pending")
        with patch(
            "src.workers.registration_poller.check_customer_profile_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "twilio-approved"}, "error": None},
        ):
            await _handle_profile_pending(client)
        assert client.ten_dlc_status == "profile_approved"

    async def test_twilio_rejected_sets_rejected(self):
        """Twilio-rejected profile moves to profile_rejected."""
        client = _make_client(ten_dlc_status="profile_pending")
        with patch(
            "src.workers.registration_poller.check_customer_profile_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "twilio-rejected"}, "error": None},
        ):
            await _handle_profile_pending(client)
        assert client.ten_dlc_status == "profile_rejected"

    async def test_in_review_no_change(self):
        """An in-review status keeps profile_pending."""
        client = _make_client(ten_dlc_status="profile_pending")
        with patch(
            "src.workers.registration_poller.check_customer_profile_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "in-review"}, "error": None},
        ):
            await _handle_profile_pending(client)
        assert client.ten_dlc_status == "profile_pending"


# ---------------------------------------------------------------------------
# _handle_profile_approved
# ---------------------------------------------------------------------------

class TestHandleProfileApproved:
    async def test_no_profile_sid_returns_early(self):
        """If client has no profile SID, do nothing."""
        client = _make_client(
            ten_dlc_profile_sid=None,
            ten_dlc_status="profile_approved",
        )
        with patch(
            "src.workers.registration_poller.create_brand_registration",
            new_callable=AsyncMock,
        ) as mock_create:
            await _handle_profile_approved(client)
            mock_create.assert_not_called()
        assert client.ten_dlc_status == "profile_approved"

    async def test_brand_creation_error(self):
        """If brand registration returns error, status stays unchanged."""
        client = _make_client(ten_dlc_status="profile_approved")
        with patch(
            "src.workers.registration_poller.create_brand_registration",
            new_callable=AsyncMock,
            return_value={"result": None, "error": "Twilio error"},
        ):
            await _handle_profile_approved(client)
        assert client.ten_dlc_status == "profile_approved"
        assert client.ten_dlc_brand_id is None

    async def test_brand_created_advances(self):
        """Successful brand creation sets brand_id and advances to brand_pending."""
        client = _make_client(ten_dlc_status="profile_approved")
        with patch(
            "src.workers.registration_poller.create_brand_registration",
            new_callable=AsyncMock,
            return_value={"result": {"brand_sid": "BRAND_123"}, "error": None},
        ):
            await _handle_profile_approved(client)
        assert client.ten_dlc_status == "brand_pending"
        assert client.ten_dlc_brand_id == "BRAND_123"


# ---------------------------------------------------------------------------
# _handle_brand_pending
# ---------------------------------------------------------------------------

class TestHandleBrandPending:
    async def test_no_brand_id_returns_early(self):
        """If client has no brand ID, do nothing."""
        client = _make_client(ten_dlc_brand_id=None, ten_dlc_status="brand_pending")
        with patch(
            "src.workers.registration_poller.check_brand_status",
            new_callable=AsyncMock,
        ) as mock_check:
            await _handle_brand_pending(client)
            mock_check.assert_not_called()
        assert client.ten_dlc_status == "brand_pending"

    async def test_api_error_no_change(self):
        """If the API returns an error, status stays unchanged."""
        client = _make_client(
            ten_dlc_brand_id="BRAND_X",
            ten_dlc_status="brand_pending",
        )
        with patch(
            "src.workers.registration_poller.check_brand_status",
            new_callable=AsyncMock,
            return_value={"result": None, "error": "timeout"},
        ):
            await _handle_brand_pending(client)
        assert client.ten_dlc_status == "brand_pending"

    async def test_approved_advances(self):
        """APPROVED brand moves to brand_approved."""
        client = _make_client(
            ten_dlc_brand_id="BRAND_X",
            ten_dlc_status="brand_pending",
        )
        with patch(
            "src.workers.registration_poller.check_brand_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "APPROVED"}, "error": None},
        ):
            await _handle_brand_pending(client)
        assert client.ten_dlc_status == "brand_approved"

    async def test_failed_sets_rejected(self):
        """FAILED brand moves to brand_rejected."""
        client = _make_client(
            ten_dlc_brand_id="BRAND_X",
            ten_dlc_status="brand_pending",
        )
        with patch(
            "src.workers.registration_poller.check_brand_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "FAILED"}, "error": None},
        ):
            await _handle_brand_pending(client)
        assert client.ten_dlc_status == "brand_rejected"

    async def test_rejected_sets_rejected(self):
        """REJECTED brand moves to brand_rejected."""
        client = _make_client(
            ten_dlc_brand_id="BRAND_X",
            ten_dlc_status="brand_pending",
        )
        with patch(
            "src.workers.registration_poller.check_brand_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "REJECTED"}, "error": None},
        ):
            await _handle_brand_pending(client)
        assert client.ten_dlc_status == "brand_rejected"

    async def test_pending_no_change(self):
        """A PENDING status keeps brand_pending."""
        client = _make_client(
            ten_dlc_brand_id="BRAND_X",
            ten_dlc_status="brand_pending",
        )
        with patch(
            "src.workers.registration_poller.check_brand_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "PENDING"}, "error": None},
        ):
            await _handle_brand_pending(client)
        assert client.ten_dlc_status == "brand_pending"


# ---------------------------------------------------------------------------
# _handle_brand_approved
# ---------------------------------------------------------------------------

class TestHandleBrandApproved:
    async def test_no_messaging_service_returns_early(self):
        """If client has no messaging service SID, do nothing."""
        client = _make_client(
            ten_dlc_brand_id="BRAND_X",
            twilio_messaging_service_sid=None,
            ten_dlc_status="brand_approved",
        )
        with patch(
            "src.workers.registration_poller.create_campaign",
            new_callable=AsyncMock,
        ) as mock_create:
            await _handle_brand_approved(client)
            mock_create.assert_not_called()

    async def test_no_brand_id_returns_early(self):
        """If client has no brand ID, do nothing."""
        client = _make_client(
            ten_dlc_brand_id=None,
            twilio_messaging_service_sid="MG_service_abc",
            ten_dlc_status="brand_approved",
        )
        with patch(
            "src.workers.registration_poller.create_campaign",
            new_callable=AsyncMock,
        ) as mock_create:
            await _handle_brand_approved(client)
            mock_create.assert_not_called()

    async def test_campaign_creation_error(self):
        """If campaign creation errors, status stays unchanged."""
        client = _make_client(
            ten_dlc_brand_id="BRAND_X",
            twilio_messaging_service_sid="MG_service_abc",
            ten_dlc_status="brand_approved",
        )
        with patch(
            "src.workers.registration_poller.create_campaign",
            new_callable=AsyncMock,
            return_value={"result": None, "error": "Campaign fail"},
        ):
            await _handle_brand_approved(client)
        assert client.ten_dlc_status == "brand_approved"
        assert client.ten_dlc_campaign_id is None

    async def test_campaign_created_advances(self):
        """Successful campaign creation sets campaign_id and advances."""
        client = _make_client(
            ten_dlc_brand_id="BRAND_X",
            twilio_messaging_service_sid="MG_service_abc",
            ten_dlc_status="brand_approved",
        )
        with patch(
            "src.workers.registration_poller.create_campaign",
            new_callable=AsyncMock,
            return_value={"result": {"campaign_sid": "CAMP_456"}, "error": None},
        ):
            await _handle_brand_approved(client)
        assert client.ten_dlc_status == "campaign_pending"
        assert client.ten_dlc_campaign_id == "CAMP_456"


# ---------------------------------------------------------------------------
# _handle_campaign_pending
# ---------------------------------------------------------------------------

class TestHandleCampaignPending:
    async def test_no_campaign_id_returns_early(self):
        """If client has no campaign ID, do nothing."""
        client = _make_client(
            ten_dlc_campaign_id=None,
            twilio_messaging_service_sid="MG_svc",
            ten_dlc_status="campaign_pending",
        )
        with patch(
            "src.workers.registration_poller.check_campaign_status",
            new_callable=AsyncMock,
        ) as mock_check:
            await _handle_campaign_pending(client)
            mock_check.assert_not_called()

    async def test_no_messaging_service_returns_early(self):
        """If client has no messaging service SID, do nothing."""
        client = _make_client(
            ten_dlc_campaign_id="CAMP_X",
            twilio_messaging_service_sid=None,
            ten_dlc_status="campaign_pending",
        )
        with patch(
            "src.workers.registration_poller.check_campaign_status",
            new_callable=AsyncMock,
        ) as mock_check:
            await _handle_campaign_pending(client)
            mock_check.assert_not_called()

    async def test_api_error_no_change(self):
        """If the API returns an error, status stays unchanged."""
        client = _make_client(
            ten_dlc_campaign_id="CAMP_X",
            twilio_messaging_service_sid="MG_svc",
            ten_dlc_status="campaign_pending",
        )
        with patch(
            "src.workers.registration_poller.check_campaign_status",
            new_callable=AsyncMock,
            return_value={"result": None, "error": "oops"},
        ):
            await _handle_campaign_pending(client)
        assert client.ten_dlc_status == "campaign_pending"

    async def test_verified_sets_active(self):
        """VERIFIED campaign moves to active."""
        client = _make_client(
            ten_dlc_campaign_id="CAMP_X",
            twilio_messaging_service_sid="MG_svc",
            ten_dlc_status="campaign_pending",
        )
        with patch(
            "src.workers.registration_poller.check_campaign_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "VERIFIED"}, "error": None},
        ):
            await _handle_campaign_pending(client)
        assert client.ten_dlc_status == "active"

    async def test_failed_sets_rejected(self):
        """FAILED campaign moves to campaign_rejected."""
        client = _make_client(
            ten_dlc_campaign_id="CAMP_X",
            twilio_messaging_service_sid="MG_svc",
            ten_dlc_status="campaign_pending",
        )
        with patch(
            "src.workers.registration_poller.check_campaign_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "FAILED"}, "error": None},
        ):
            await _handle_campaign_pending(client)
        assert client.ten_dlc_status == "campaign_rejected"

    async def test_rejected_sets_rejected(self):
        """REJECTED campaign moves to campaign_rejected."""
        client = _make_client(
            ten_dlc_campaign_id="CAMP_X",
            twilio_messaging_service_sid="MG_svc",
            ten_dlc_status="campaign_pending",
        )
        with patch(
            "src.workers.registration_poller.check_campaign_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "REJECTED"}, "error": None},
        ):
            await _handle_campaign_pending(client)
        assert client.ten_dlc_status == "campaign_rejected"

    async def test_in_progress_no_change(self):
        """An IN_PROGRESS status keeps campaign_pending."""
        client = _make_client(
            ten_dlc_campaign_id="CAMP_X",
            twilio_messaging_service_sid="MG_svc",
            ten_dlc_status="campaign_pending",
        )
        with patch(
            "src.workers.registration_poller.check_campaign_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "IN_PROGRESS"}, "error": None},
        ):
            await _handle_campaign_pending(client)
        assert client.ten_dlc_status == "campaign_pending"


# ---------------------------------------------------------------------------
# _handle_tf_pending
# ---------------------------------------------------------------------------

class TestHandleTfPending:
    async def test_no_verification_sid_returns_early(self):
        """If client has no verification SID, do nothing."""
        client = _make_client(
            ten_dlc_verification_sid=None,
            ten_dlc_status="tf_verification_pending",
        )
        with patch(
            "src.workers.registration_poller.check_tollfree_status",
            new_callable=AsyncMock,
        ) as mock_check:
            await _handle_tf_pending(client)
            mock_check.assert_not_called()

    async def test_api_error_no_change(self):
        """If the API returns an error, status stays unchanged."""
        client = _make_client(
            ten_dlc_verification_sid="VER_abc",
            ten_dlc_status="tf_verification_pending",
        )
        with patch(
            "src.workers.registration_poller.check_tollfree_status",
            new_callable=AsyncMock,
            return_value={"result": None, "error": "fail"},
        ):
            await _handle_tf_pending(client)
        assert client.ten_dlc_status == "tf_verification_pending"

    async def test_twilio_approved_sets_active(self):
        """TWILIO_APPROVED moves to active."""
        client = _make_client(
            ten_dlc_verification_sid="VER_abc",
            ten_dlc_status="tf_verification_pending",
        )
        with patch(
            "src.workers.registration_poller.check_tollfree_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "TWILIO_APPROVED"}, "error": None},
        ):
            await _handle_tf_pending(client)
        assert client.ten_dlc_status == "active"

    async def test_twilio_rejected_sets_tf_rejected(self):
        """TWILIO_REJECTED moves to tf_rejected."""
        client = _make_client(
            ten_dlc_verification_sid="VER_abc",
            ten_dlc_status="tf_verification_pending",
        )
        with patch(
            "src.workers.registration_poller.check_tollfree_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "TWILIO_REJECTED"}, "error": None},
        ):
            await _handle_tf_pending(client)
        assert client.ten_dlc_status == "tf_rejected"

    async def test_pending_review_no_change(self):
        """PENDING_REVIEW keeps tf_verification_pending."""
        client = _make_client(
            ten_dlc_verification_sid="VER_abc",
            ten_dlc_status="tf_verification_pending",
        )
        with patch(
            "src.workers.registration_poller.check_tollfree_status",
            new_callable=AsyncMock,
            return_value={"result": {"status": "PENDING_REVIEW"}, "error": None},
        ):
            await _handle_tf_pending(client)
        assert client.ten_dlc_status == "tf_verification_pending"


# ---------------------------------------------------------------------------
# _advance_single_client - dispatch + logging + alert
# ---------------------------------------------------------------------------

class TestAdvanceSingleClient:
    async def test_dispatches_profile_pending(self):
        """profile_pending dispatches to _handle_profile_pending."""
        client = _make_client(ten_dlc_status="profile_pending")
        with patch(
            "src.workers.registration_poller._handle_profile_pending",
            new_callable=AsyncMock,
        ) as mock_handler, patch(
            "src.workers.registration_poller._send_status_alert",
            new_callable=AsyncMock,
        ):
            await _advance_single_client(client)
            mock_handler.assert_called_once_with(client)

    async def test_dispatches_profile_approved(self):
        """profile_approved dispatches to _handle_profile_approved."""
        client = _make_client(ten_dlc_status="profile_approved")
        with patch(
            "src.workers.registration_poller._handle_profile_approved",
            new_callable=AsyncMock,
        ) as mock_handler, patch(
            "src.workers.registration_poller._send_status_alert",
            new_callable=AsyncMock,
        ):
            await _advance_single_client(client)
            mock_handler.assert_called_once_with(client)

    async def test_dispatches_brand_pending(self):
        """brand_pending dispatches to _handle_brand_pending."""
        client = _make_client(ten_dlc_status="brand_pending")
        with patch(
            "src.workers.registration_poller._handle_brand_pending",
            new_callable=AsyncMock,
        ) as mock_handler, patch(
            "src.workers.registration_poller._send_status_alert",
            new_callable=AsyncMock,
        ):
            await _advance_single_client(client)
            mock_handler.assert_called_once_with(client)

    async def test_dispatches_brand_approved(self):
        """brand_approved dispatches to _handle_brand_approved."""
        client = _make_client(ten_dlc_status="brand_approved")
        with patch(
            "src.workers.registration_poller._handle_brand_approved",
            new_callable=AsyncMock,
        ) as mock_handler, patch(
            "src.workers.registration_poller._send_status_alert",
            new_callable=AsyncMock,
        ):
            await _advance_single_client(client)
            mock_handler.assert_called_once_with(client)

    async def test_dispatches_campaign_pending(self):
        """campaign_pending dispatches to _handle_campaign_pending."""
        client = _make_client(ten_dlc_status="campaign_pending")
        with patch(
            "src.workers.registration_poller._handle_campaign_pending",
            new_callable=AsyncMock,
        ) as mock_handler, patch(
            "src.workers.registration_poller._send_status_alert",
            new_callable=AsyncMock,
        ):
            await _advance_single_client(client)
            mock_handler.assert_called_once_with(client)

    async def test_dispatches_tf_verification_pending(self):
        """tf_verification_pending dispatches to _handle_tf_pending."""
        client = _make_client(ten_dlc_status="tf_verification_pending")
        with patch(
            "src.workers.registration_poller._handle_tf_pending",
            new_callable=AsyncMock,
        ) as mock_handler, patch(
            "src.workers.registration_poller._send_status_alert",
            new_callable=AsyncMock,
        ):
            await _advance_single_client(client)
            mock_handler.assert_called_once_with(client)

    async def test_status_change_triggers_alert(self):
        """When status changes, _send_status_alert is called."""
        client = _make_client(ten_dlc_status="profile_pending")

        async def _fake_handler(c):
            c.ten_dlc_status = "profile_approved"

        with patch(
            "src.workers.registration_poller._handle_profile_pending",
            side_effect=_fake_handler,
        ), patch(
            "src.workers.registration_poller._send_status_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await _advance_single_client(client)
            mock_alert.assert_called_once_with(
                client, "profile_pending", "profile_approved",
            )

    async def test_no_status_change_no_alert(self):
        """When status is unchanged, no alert is sent."""
        client = _make_client(ten_dlc_status="profile_pending")
        with patch(
            "src.workers.registration_poller._handle_profile_pending",
            new_callable=AsyncMock,
        ), patch(
            "src.workers.registration_poller._send_status_alert",
            new_callable=AsyncMock,
        ) as mock_alert:
            await _advance_single_client(client)
            mock_alert.assert_not_called()


# ---------------------------------------------------------------------------
# _send_status_alert
# ---------------------------------------------------------------------------

class TestSendStatusAlert:
    async def test_no_webhook_url_returns_early(self):
        """If alert_webhook_url is empty, skip sending."""
        client = _make_client()
        settings_mock = MagicMock()
        settings_mock.alert_webhook_url = ""

        with patch("src.config.get_settings", return_value=settings_mock):
            # Should not raise; httpx never imported
            await _send_status_alert(client, "profile_pending", "profile_approved")

    async def test_sends_update_alert(self):
        """Normal status transitions send [UPDATE] prefix."""
        client = _make_client(business_name="Acme HVAC")
        settings_mock = MagicMock()
        settings_mock.alert_webhook_url = "https://hooks.example.com/webhook"

        http_mock = AsyncMock()
        http_mock.post = AsyncMock()
        http_client_ctx = AsyncMock()
        http_client_ctx.__aenter__ = AsyncMock(return_value=http_mock)
        http_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.config.get_settings", return_value=settings_mock), \
             patch("httpx.AsyncClient", return_value=http_client_ctx):
            await _send_status_alert(client, "brand_pending", "brand_approved")

        http_mock.post.assert_called_once()
        call_args = http_mock.post.call_args
        assert call_args[0][0] == "https://hooks.example.com/webhook"
        payload = call_args[1]["json"]
        assert "[UPDATE]" in payload["content"]
        assert "Acme HVAC" in payload["content"]

    async def test_sends_error_alert_for_rejection(self):
        """Rejected statuses send [ERROR] prefix."""
        client = _make_client(business_name="FailCo")
        settings_mock = MagicMock()
        settings_mock.alert_webhook_url = "https://hooks.example.com/webhook"

        http_mock = AsyncMock()
        http_mock.post = AsyncMock()
        http_client_ctx = AsyncMock()
        http_client_ctx.__aenter__ = AsyncMock(return_value=http_mock)
        http_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.config.get_settings", return_value=settings_mock), \
             patch("httpx.AsyncClient", return_value=http_client_ctx):
            await _send_status_alert(client, "brand_pending", "brand_rejected")

        payload = http_mock.post.call_args[1]["json"]
        assert "[ERROR]" in payload["content"]

    async def test_sends_ok_alert_for_active(self):
        """Active status sends [OK] prefix."""
        client = _make_client(business_name="GoodCo")
        settings_mock = MagicMock()
        settings_mock.alert_webhook_url = "https://hooks.example.com/webhook"

        http_mock = AsyncMock()
        http_mock.post = AsyncMock()
        http_client_ctx = AsyncMock()
        http_client_ctx.__aenter__ = AsyncMock(return_value=http_mock)
        http_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("src.config.get_settings", return_value=settings_mock), \
             patch("httpx.AsyncClient", return_value=http_client_ctx):
            await _send_status_alert(client, "campaign_pending", "active")

        payload = http_mock.post.call_args[1]["json"]
        assert "[OK]" in payload["content"]

    async def test_exception_suppressed(self):
        """If webhook call fails, error is logged but not raised."""
        client = _make_client()
        settings_mock = MagicMock()
        settings_mock.alert_webhook_url = "https://hooks.example.com/webhook"

        with patch("src.config.get_settings", return_value=settings_mock), \
             patch("httpx.AsyncClient", side_effect=Exception("network error")):
            # Should not raise
            await _send_status_alert(client, "old", "new")


# ---------------------------------------------------------------------------
# poll_registration_statuses (integration-level - mocks DB session)
# ---------------------------------------------------------------------------

class TestPollRegistrationStatuses:
    async def test_no_clients_returns_early(self):
        """If no clients match the pending query, exit immediately."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.workers.registration_poller.async_session_factory",
            return_value=mock_ctx,
        ):
            await poll_registration_statuses()

        mock_session.commit.assert_not_called()

    async def test_processes_all_clients_and_commits(self):
        """All matched clients are processed and session is committed."""
        client_a = _make_client(ten_dlc_status="profile_pending")
        client_b = _make_client(ten_dlc_status="brand_pending", ten_dlc_brand_id="BR")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [client_a, client_b]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.workers.registration_poller.async_session_factory",
            return_value=mock_ctx,
        ), patch(
            "src.workers.registration_poller._advance_single_client",
            new_callable=AsyncMock,
        ) as mock_advance:
            await poll_registration_statuses()

        assert mock_advance.call_count == 2
        mock_session.commit.assert_called_once()

    async def test_single_client_error_does_not_abort_batch(self):
        """If one client raises, others still get processed and commit happens."""
        client_a = _make_client(ten_dlc_status="profile_pending")
        client_b = _make_client(ten_dlc_status="brand_pending", ten_dlc_brand_id="BR")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [client_a, client_b]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        async def _advance_side_effect(c):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Simulated error for first client")

        with patch(
            "src.workers.registration_poller.async_session_factory",
            return_value=mock_ctx,
        ), patch(
            "src.workers.registration_poller._advance_single_client",
            side_effect=_advance_side_effect,
        ):
            await poll_registration_statuses()

        assert call_count == 2
        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# run_registration_poller - main loop
# ---------------------------------------------------------------------------

class TestRunRegistrationPoller:
    async def test_loop_calls_poll_heartbeat_sleep(self):
        """Main loop calls poll, heartbeat, and sleep, and catches errors."""
        iteration = 0

        async def _poll_side_effect():
            nonlocal iteration
            iteration += 1
            if iteration == 1:
                raise RuntimeError("Transient error")
            # Second iteration succeeds

        with patch(
            "src.workers.registration_poller.poll_registration_statuses",
            side_effect=_poll_side_effect,
        ), patch(
            "src.workers.registration_poller._heartbeat",
            new_callable=AsyncMock,
        ) as mock_hb, patch(
            "src.workers.registration_poller.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=[None, asyncio.CancelledError()],
        ) as mock_sleep:
            with pytest.raises(asyncio.CancelledError):
                await run_registration_poller()

        # Two iterations: error logged on first, success on second
        assert iteration == 2
        assert mock_hb.call_count == 2
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_poll_interval(self):
        assert POLL_INTERVAL_SECONDS == 300

    def test_batch_limit(self):
        assert BATCH_LIMIT == 50
