"""
Tests for src/services/twilio_registration.py — Twilio A2P registration service.

Covers:
  - is_tollfree() helper
  - _get_twilio_client() factory
  - _run_sync() executor wrapper
  - create_messaging_service (success + error)
  - add_phone_to_messaging_service (success + error)
  - create_customer_profile (success + error)
  - submit_customer_profile (success + error)
  - check_customer_profile_status (success + error)
  - create_brand_registration (success + error)
  - check_brand_status (success + error)
  - create_campaign (success + error)
  - check_campaign_status (success + error)
  - submit_tollfree_verification (success + error, with/without website)
  - check_tollfree_status (success + error)
  - Module-level constants
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.services.twilio_registration import (
    is_tollfree,
    TOLLFREE_PREFIXES,
    TERMINAL_STATES,
    PENDING_STATES,
    TWILIO_API_TIMEOUT,
    _get_twilio_client,
    _run_sync,
    create_messaging_service,
    add_phone_to_messaging_service,
    create_customer_profile,
    submit_customer_profile,
    check_customer_profile_status,
    create_brand_registration,
    check_brand_status,
    create_campaign,
    check_campaign_status,
    submit_tollfree_verification,
    check_tollfree_status,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are correct."""

    def test_tollfree_prefixes(self):
        assert TOLLFREE_PREFIXES == {"800", "833", "844", "855", "866", "877", "888"}

    def test_terminal_states(self):
        assert "active" in TERMINAL_STATES
        assert "profile_rejected" in TERMINAL_STATES
        assert "brand_rejected" in TERMINAL_STATES
        assert "campaign_rejected" in TERMINAL_STATES
        assert "tf_rejected" in TERMINAL_STATES

    def test_pending_states(self):
        assert "collecting_info" in PENDING_STATES
        assert "profile_pending" in PENDING_STATES
        assert "tf_verification_pending" in PENDING_STATES

    def test_twilio_api_timeout(self):
        assert TWILIO_API_TIMEOUT == 10


# ---------------------------------------------------------------------------
# is_tollfree
# ---------------------------------------------------------------------------

class TestIsTollfree:
    """Test toll-free detection based on area code."""

    @pytest.mark.parametrize("prefix", ["800", "833", "844", "855", "866", "877", "888"])
    def test_tollfree_numbers(self, prefix):
        phone = f"+1{prefix}5551234"
        assert is_tollfree(phone) is True

    def test_regular_number_is_not_tollfree(self):
        assert is_tollfree("+15125551234") is False

    def test_without_plus_prefix(self):
        assert is_tollfree("18005551234") is True

    def test_short_number_returns_false(self):
        # Less than 4 digits after stripping '+'
        assert is_tollfree("+12") is False

    def test_non_us_number_returns_false(self):
        # Does not start with '1'
        assert is_tollfree("+448005551234") is False

    def test_empty_string_returns_false(self):
        assert is_tollfree("") is False

    def test_plus_only_returns_false(self):
        assert is_tollfree("+") is False

    def test_exact_four_digits_tollfree(self):
        # Exactly 4 digits (1 + 3-digit area code) — minimum valid length
        assert is_tollfree("+1800") is True

    def test_exact_four_digits_not_tollfree(self):
        assert is_tollfree("+1512") is False


# ---------------------------------------------------------------------------
# _get_twilio_client
# ---------------------------------------------------------------------------

class TestGetTwilioClient:
    """Test the Twilio client factory function."""

    @patch("src.config.get_settings")
    @patch("twilio.http.http_client.TwilioHttpClient")
    @patch("twilio.rest.Client")
    def test_creates_client_with_settings(
        self, mock_client_cls, mock_http_cls, mock_get_settings
    ):
        """_get_twilio_client should use settings credentials and timeout."""
        settings = MagicMock()
        settings.twilio_account_sid = "ACtest123"
        settings.twilio_auth_token = "token_abc"
        mock_get_settings.return_value = settings

        mock_http_instance = MagicMock()
        mock_http_cls.return_value = mock_http_instance

        mock_client_instance = MagicMock()
        mock_client_cls.return_value = mock_client_instance

        result = _get_twilio_client()

        mock_http_cls.assert_called_once_with(timeout=TWILIO_API_TIMEOUT)
        mock_client_cls.assert_called_once_with(
            "ACtest123",
            "token_abc",
            http_client=mock_http_instance,
        )
        assert result is mock_client_instance


# ---------------------------------------------------------------------------
# _run_sync
# ---------------------------------------------------------------------------

class TestRunSync:
    """Test the executor wrapper for synchronous functions."""

    async def test_runs_sync_function_in_executor(self):
        def add(a, b):
            return a + b

        result = await _run_sync(add, 3, 5)
        assert result == 8

    async def test_runs_sync_with_kwargs(self):
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}"

        result = await _run_sync(greet, "World", greeting="Hi")
        assert result == "Hi, World"

    async def test_propagates_exception(self):
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await _run_sync(fail)


# ---------------------------------------------------------------------------
# Shared helper: build a mock Twilio client
# ---------------------------------------------------------------------------

def _make_twilio_mock():
    """Return a fresh MagicMock that mimics the Twilio client shape."""
    return MagicMock()


def _patch_client(mock_client):
    """Context manager that patches _get_twilio_client to return mock_client."""
    return patch(
        "src.services.twilio_registration._get_twilio_client",
        return_value=mock_client,
    )


def _patch_run_sync():
    """Patch _run_sync so it calls the callable directly (no executor)."""
    async def _direct_call(func, *args, **kwargs):
        return func(*args, **kwargs)

    return patch(
        "src.services.twilio_registration._run_sync",
        side_effect=_direct_call,
    )


# ---------------------------------------------------------------------------
# create_messaging_service
# ---------------------------------------------------------------------------

class TestCreateMessagingService:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_service = MagicMock(sid="MGtest_sid_123")
        mock_twilio.messaging.v1.services.create.return_value = mock_service

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_messaging_service(
                client_id="client-abc-12345678",
                business_name="Acme HVAC",
            )

        assert result["error"] is None
        assert result["result"]["messaging_service_sid"] == "MGtest_sid_123"
        mock_twilio.messaging.v1.services.create.assert_called_once_with(
            friendly_name="LeadLock-Acme HVAC-client-a",
            inbound_request_url=None,
            use_inbound_webhook_on_number=True,
        )

    async def test_error_returns_error_dict(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.messaging.v1.services.create.side_effect = RuntimeError("Twilio down")

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_messaging_service(
                client_id="client-abc",
                business_name="Acme HVAC",
            )

        assert result["result"] is None
        assert "Twilio down" in result["error"]


# ---------------------------------------------------------------------------
# add_phone_to_messaging_service
# ---------------------------------------------------------------------------

class TestAddPhoneToMessagingService:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_phone = MagicMock(sid="PN_phone_sid")
        mock_twilio.messaging.v1.services.return_value.phone_numbers.create.return_value = (
            mock_phone
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await add_phone_to_messaging_service(
                messaging_service_sid="MG_service_sid",
                phone_sid="PN_phone_sid",
            )

        assert result["error"] is None
        assert result["result"]["phone_sid"] == "PN_phone_sid"

    async def test_error(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.messaging.v1.services.return_value.phone_numbers.create.side_effect = (
            RuntimeError("bad phone")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await add_phone_to_messaging_service(
                messaging_service_sid="MG_service_sid",
                phone_sid="PN_phone_sid",
            )

        assert result["result"] is None
        assert "bad phone" in result["error"]


# ---------------------------------------------------------------------------
# create_customer_profile
# ---------------------------------------------------------------------------

class TestCreateCustomerProfile:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_profile = MagicMock(sid="BU_profile_sid")
        mock_end_user = MagicMock(sid="IT_enduser_sid")

        mock_twilio.trusthub.v1.customer_profiles.create.return_value = mock_profile
        mock_twilio.trusthub.v1.end_users.create.return_value = mock_end_user
        mock_twilio.trusthub.v1.customer_profiles.return_value.customer_profiles_entity_assignments.create.return_value = (
            MagicMock()
        )

        business_info = {
            "business_type": "llc",
            "ein": "12-3456789",
            "phone": "+15125551234",
            "website": "https://acme.com",
            "street": "123 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
        }

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_customer_profile(
                business_name="Acme HVAC",
                email="admin@acme.com",
                business_info=business_info,
            )

        assert result["error"] is None
        assert result["result"]["profile_sid"] == "BU_profile_sid"

        # Verify profile creation
        mock_twilio.trusthub.v1.customer_profiles.create.assert_called_once_with(
            friendly_name="LeadLock-Acme HVAC",
            email="admin@acme.com",
            policy_sid="RNdfbf3fae0e1107f8abad0571f9b0e3a7",
        )

        # Verify end-user creation
        mock_twilio.trusthub.v1.end_users.create.assert_called_once()
        call_kwargs = mock_twilio.trusthub.v1.end_users.create.call_args[1]
        assert call_kwargs["friendly_name"] == "Acme HVAC"
        assert call_kwargs["type"] == "authorized_representative_1"
        assert call_kwargs["attributes"]["business_name"] == "Acme HVAC"
        assert call_kwargs["attributes"]["ein"] == "12-3456789"

        # Verify entity assignment
        mock_twilio.trusthub.v1.customer_profiles.return_value.customer_profiles_entity_assignments.create.assert_called_once_with(
            object_sid="IT_enduser_sid",
        )

    async def test_success_with_missing_business_info_keys(self):
        """When business_info keys are missing, defaults should be used."""
        mock_twilio = _make_twilio_mock()
        mock_profile = MagicMock(sid="BU_profile_sid")
        mock_end_user = MagicMock(sid="IT_enduser_sid")

        mock_twilio.trusthub.v1.customer_profiles.create.return_value = mock_profile
        mock_twilio.trusthub.v1.end_users.create.return_value = mock_end_user
        mock_twilio.trusthub.v1.customer_profiles.return_value.customer_profiles_entity_assignments.create.return_value = (
            MagicMock()
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_customer_profile(
                business_name="Acme HVAC",
                email="admin@acme.com",
                business_info={},  # empty — all defaults
            )

        assert result["error"] is None
        call_kwargs = mock_twilio.trusthub.v1.end_users.create.call_args[1]
        assert call_kwargs["attributes"]["business_type"] == "llc"
        assert call_kwargs["attributes"]["ein"] == ""

    async def test_error_on_profile_creation(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.trusthub.v1.customer_profiles.create.side_effect = RuntimeError(
            "profile fail"
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_customer_profile(
                business_name="Acme",
                email="a@b.com",
                business_info={},
            )

        assert result["result"] is None
        assert "profile fail" in result["error"]

    async def test_error_on_end_user_creation(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.trusthub.v1.customer_profiles.create.return_value = MagicMock(
            sid="BU1"
        )
        mock_twilio.trusthub.v1.end_users.create.side_effect = RuntimeError(
            "end user fail"
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_customer_profile(
                business_name="Acme",
                email="a@b.com",
                business_info={},
            )

        assert result["result"] is None
        assert "end user fail" in result["error"]

    async def test_error_on_entity_assignment(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.trusthub.v1.customer_profiles.create.return_value = MagicMock(
            sid="BU1"
        )
        mock_twilio.trusthub.v1.end_users.create.return_value = MagicMock(sid="IT1")
        mock_twilio.trusthub.v1.customer_profiles.return_value.customer_profiles_entity_assignments.create.side_effect = (
            RuntimeError("assignment fail")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_customer_profile(
                business_name="Acme",
                email="a@b.com",
                business_info={},
            )

        assert result["result"] is None
        assert "assignment fail" in result["error"]


# ---------------------------------------------------------------------------
# submit_customer_profile
# ---------------------------------------------------------------------------

class TestSubmitCustomerProfile:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_evaluation = MagicMock(status="pending-review")
        mock_twilio.trusthub.v1.customer_profiles.return_value.customer_profiles_evaluations.create.return_value = (
            mock_evaluation
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await submit_customer_profile(profile_sid="BU_profile_sid")

        assert result["error"] is None
        assert result["result"]["status"] == "pending-review"

    async def test_error(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.trusthub.v1.customer_profiles.return_value.customer_profiles_evaluations.create.side_effect = (
            RuntimeError("submit failed")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await submit_customer_profile(profile_sid="BU_profile_sid")

        assert result["result"] is None
        assert "submit failed" in result["error"]


# ---------------------------------------------------------------------------
# check_customer_profile_status
# ---------------------------------------------------------------------------

class TestCheckCustomerProfileStatus:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_profile = MagicMock(status="twilio-approved")
        mock_twilio.trusthub.v1.customer_profiles.return_value.fetch.return_value = (
            mock_profile
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await check_customer_profile_status(profile_sid="BU_sid")

        assert result["error"] is None
        assert result["result"]["status"] == "twilio-approved"

    async def test_error(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.trusthub.v1.customer_profiles.return_value.fetch.side_effect = (
            RuntimeError("fetch failed")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await check_customer_profile_status(profile_sid="BU_sid")

        assert result["result"] is None
        assert "fetch failed" in result["error"]


# ---------------------------------------------------------------------------
# create_brand_registration
# ---------------------------------------------------------------------------

class TestCreateBrandRegistration:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_brand = MagicMock(sid="BN_brand_sid")
        mock_twilio.messaging.v1.brand_registrations.create.return_value = mock_brand

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_brand_registration(
                customer_profile_sid="BU_profile_sid"
            )

        assert result["error"] is None
        assert result["result"]["brand_sid"] == "BN_brand_sid"
        mock_twilio.messaging.v1.brand_registrations.create.assert_called_once_with(
            customer_profile_bundle_sid="BU_profile_sid",
            a2p_profile_bundle_sid="BU_profile_sid",
        )

    async def test_error(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.messaging.v1.brand_registrations.create.side_effect = (
            RuntimeError("brand fail")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_brand_registration(
                customer_profile_sid="BU_profile_sid"
            )

        assert result["result"] is None
        assert "brand fail" in result["error"]


# ---------------------------------------------------------------------------
# check_brand_status
# ---------------------------------------------------------------------------

class TestCheckBrandStatus:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_brand = MagicMock(status="approved")
        mock_twilio.messaging.v1.brand_registrations.return_value.fetch.return_value = (
            mock_brand
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await check_brand_status(brand_sid="BN_brand_sid")

        assert result["error"] is None
        assert result["result"]["status"] == "approved"

    async def test_error(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.messaging.v1.brand_registrations.return_value.fetch.side_effect = (
            RuntimeError("brand fetch fail")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await check_brand_status(brand_sid="BN_brand_sid")

        assert result["result"] is None
        assert "brand fetch fail" in result["error"]


# ---------------------------------------------------------------------------
# create_campaign
# ---------------------------------------------------------------------------

class TestCreateCampaign:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_campaign = MagicMock(sid="QE_campaign_sid")
        mock_twilio.messaging.v1.services.return_value.us_app_to_person.create.return_value = (
            mock_campaign
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_campaign(
                brand_sid="BN_brand_sid",
                messaging_service_sid="MG_service_sid",
                business_name="Acme HVAC",
            )

        assert result["error"] is None
        assert result["result"]["campaign_sid"] == "QE_campaign_sid"

        call_kwargs = mock_twilio.messaging.v1.services.return_value.us_app_to_person.create.call_args[1]
        assert call_kwargs["brand_registration_sid"] == "BN_brand_sid"
        assert "Acme HVAC" in call_kwargs["description"]
        assert call_kwargs["has_embedded_links"] is False
        assert call_kwargs["has_embedded_phone"] is False
        assert call_kwargs["opt_in_type"] == "WEB_FORM"
        assert len(call_kwargs["message_samples"]) == 2

    async def test_error(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.messaging.v1.services.return_value.us_app_to_person.create.side_effect = (
            RuntimeError("campaign fail")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await create_campaign(
                brand_sid="BN1",
                messaging_service_sid="MG1",
                business_name="Acme",
            )

        assert result["result"] is None
        assert "campaign fail" in result["error"]


# ---------------------------------------------------------------------------
# check_campaign_status
# ---------------------------------------------------------------------------

class TestCheckCampaignStatus:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_campaign = MagicMock(campaign_status="verified")
        mock_twilio.messaging.v1.services.return_value.us_app_to_person.return_value.fetch.return_value = (
            mock_campaign
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await check_campaign_status(
                campaign_sid="QE_campaign_sid",
                messaging_service_sid="MG_service_sid",
            )

        assert result["error"] is None
        assert result["result"]["status"] == "verified"

    async def test_error(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.messaging.v1.services.return_value.us_app_to_person.return_value.fetch.side_effect = (
            RuntimeError("campaign status fail")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await check_campaign_status(
                campaign_sid="QE1",
                messaging_service_sid="MG1",
            )

        assert result["result"] is None
        assert "campaign status fail" in result["error"]


# ---------------------------------------------------------------------------
# submit_tollfree_verification
# ---------------------------------------------------------------------------

class TestSubmitTollfreeVerification:

    async def test_success_with_website(self):
        mock_twilio = _make_twilio_mock()
        mock_verification = MagicMock(sid="TF_verification_sid")
        mock_twilio.messaging.v1.tollfree_verifications.create.return_value = (
            mock_verification
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await submit_tollfree_verification(
                phone_sid="PN_phone_sid",
                business_name="Acme HVAC",
                email="admin@acme.com",
                website="https://acme.com",
            )

        assert result["error"] is None
        assert result["result"]["verification_sid"] == "TF_verification_sid"

        call_kwargs = mock_twilio.messaging.v1.tollfree_verifications.create.call_args[1]
        assert call_kwargs["tollfree_phone_number_sid"] == "PN_phone_sid"
        assert call_kwargs["business_name"] == "Acme HVAC"
        assert call_kwargs["business_contact_email"] == "admin@acme.com"
        assert call_kwargs["business_website"] == "https://acme.com"
        assert call_kwargs["notification_email"] == "admin@acme.com"
        assert call_kwargs["use_case_categories"] == ["CUSTOMER_CARE"]
        assert call_kwargs["opt_in_type"] == "VERBAL"
        assert call_kwargs["message_volume"] == "1,000"
        assert "Acme HVAC" in call_kwargs["production_message_sample"]

    async def test_success_without_website(self):
        """When website is None, empty string should be sent."""
        mock_twilio = _make_twilio_mock()
        mock_verification = MagicMock(sid="TF_verification_sid")
        mock_twilio.messaging.v1.tollfree_verifications.create.return_value = (
            mock_verification
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await submit_tollfree_verification(
                phone_sid="PN_phone_sid",
                business_name="Acme HVAC",
                email="admin@acme.com",
                # website omitted — defaults to None
            )

        assert result["error"] is None
        call_kwargs = mock_twilio.messaging.v1.tollfree_verifications.create.call_args[1]
        assert call_kwargs["business_website"] == ""

    async def test_error(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.messaging.v1.tollfree_verifications.create.side_effect = (
            RuntimeError("tf fail")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await submit_tollfree_verification(
                phone_sid="PN1",
                business_name="Acme",
                email="a@b.com",
            )

        assert result["result"] is None
        assert "tf fail" in result["error"]


# ---------------------------------------------------------------------------
# check_tollfree_status
# ---------------------------------------------------------------------------

class TestCheckTollfreeStatus:

    async def test_success(self):
        mock_twilio = _make_twilio_mock()
        mock_verification = MagicMock(status="TWILIO_APPROVED")
        mock_twilio.messaging.v1.tollfree_verifications.return_value.fetch.return_value = (
            mock_verification
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await check_tollfree_status(
                verification_sid="TF_verification_sid"
            )

        assert result["error"] is None
        assert result["result"]["status"] == "TWILIO_APPROVED"

    async def test_error(self):
        mock_twilio = _make_twilio_mock()
        mock_twilio.messaging.v1.tollfree_verifications.return_value.fetch.side_effect = (
            RuntimeError("tf status fail")
        )

        with _patch_client(mock_twilio), _patch_run_sync():
            result = await check_tollfree_status(
                verification_sid="TF_verification_sid"
            )

        assert result["result"] is None
        assert "tf status fail" in result["error"]
