"""
Extended SMS service tests - covers async functions, Twilio/Telnyx integration,
retry logic, failover, error extraction, and phone provisioning/release.

Complements test_sms_service.py which covers pure utility functions.
"""
import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_settings(**overrides):
    """Build a fake Settings object with sensible defaults."""
    defaults = {
        "twilio_account_sid": "AC_test",
        "twilio_auth_token": "auth_test",
        "app_base_url": "https://app.leadlock.io",
        "twilio_messaging_service_sid": "MG_default",
        "telnyx_api_key": "TELNYX_KEY",
        "telnyx_messaging_profile_id": "TELNYX_PROFILE",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def fake_settings():
    return _make_settings()


@pytest.fixture
def fake_settings_no_telnyx():
    return _make_settings(telnyx_api_key="")


@pytest.fixture
def fake_settings_no_msgsvc():
    return _make_settings(twilio_messaging_service_sid="")


# ---------------------------------------------------------------------------
# _get_twilio_client
# ---------------------------------------------------------------------------

class TestGetTwilioClient:
    def test_creates_client_with_settings(self):
        """_get_twilio_client should create a TwilioClient with credentials from settings."""
        from src.services.sms import _get_twilio_client

        mock_http_client_cls = MagicMock()
        mock_twilio_client_cls = MagicMock()
        settings = _make_settings()

        with patch("src.config.get_settings", return_value=settings), \
             patch("twilio.rest.Client", mock_twilio_client_cls), \
             patch("twilio.http.http_client.TwilioHttpClient", mock_http_client_cls):
            client = _get_twilio_client()

        mock_http_client_cls.assert_called_once_with(timeout=10)
        mock_twilio_client_cls.assert_called_once_with(
            "AC_test",
            "auth_test",
            http_client=mock_http_client_cls.return_value,
        )
        assert client == mock_twilio_client_cls.return_value


# ---------------------------------------------------------------------------
# _run_sync
# ---------------------------------------------------------------------------

class TestRunSync:
    async def test_runs_sync_function_in_executor(self):
        """_run_sync wraps a blocking call through run_in_executor."""
        from src.services.sms import _run_sync

        def blocking_add(a, b):
            return a + b

        result = await _run_sync(blocking_add, 3, 7)
        assert result == 10

    async def test_passes_kwargs(self):
        """_run_sync forwards keyword arguments."""
        from src.services.sms import _run_sync

        def blocking_greet(name="world"):
            return f"hello {name}"

        result = await _run_sync(blocking_greet, name="pytest")
        assert result == "hello pytest"


# ---------------------------------------------------------------------------
# classify_error - cover the "permanent" branch (line 163)
# ---------------------------------------------------------------------------

class TestClassifyErrorPermanent:
    def test_permanent_via_30006_classified_as_landline_not_permanent(self):
        """30006 is in PERMANENT_ERRORS but hit landline branch first."""
        from src.services.sms import classify_error
        # 30006 is matched as landline before permanent
        assert classify_error("30006") == "landline"

    def test_permanent_via_21610_classified_as_opt_out_not_permanent(self):
        """21610 is in PERMANENT_ERRORS but classified more specifically."""
        from src.services.sms import classify_error
        assert classify_error("21610") == "opt_out"

    def test_permanent_branch_reached_with_exclusive_code(self):
        """Exercise the 'return permanent' branch (line 163) by adding a code
        that is in PERMANENT_ERRORS but not in any more-specific set."""
        from src.services.sms import classify_error

        # Add a code to PERMANENT_ERRORS that isn't in opt_out/landline/invalid
        with patch("src.services.sms.PERMANENT_ERRORS", {"21211", "21610", "30006", "21612", "99001"}):
            assert classify_error("99001") == "permanent"


# ---------------------------------------------------------------------------
# _extract_error_code
# ---------------------------------------------------------------------------

class TestExtractErrorCode:
    def test_extracts_code_attribute(self):
        """When exception has .code, use it."""
        from src.services.sms import _extract_error_code

        err = Exception("Twilio error")
        err.code = 21610
        assert _extract_error_code(err) == "21610"

    def test_extracts_code_from_message_permanent(self):
        """When no .code, scan the message for known codes."""
        from src.services.sms import _extract_error_code

        err = Exception("Error 30006: landline detected")
        assert _extract_error_code(err) == "30006"

    def test_extracts_code_from_message_transient(self):
        from src.services.sms import _extract_error_code

        err = Exception("Carrier filter 30007 blocked message")
        assert _extract_error_code(err) == "30007"

    def test_returns_none_for_unknown(self):
        from src.services.sms import _extract_error_code

        err = Exception("Something went wrong")
        assert _extract_error_code(err) is None

    def test_code_attribute_zero_is_returned(self):
        """code=0 is truthy for 'is not None' check."""
        from src.services.sms import _extract_error_code

        err = Exception("zero")
        err.code = 0
        assert _extract_error_code(err) == "0"


# ---------------------------------------------------------------------------
# search_available_numbers
# ---------------------------------------------------------------------------

class TestSearchAvailableNumbers:
    async def test_returns_formatted_list(self):
        from src.services.sms import search_available_numbers

        num1 = SimpleNamespace(
            phone_number="+15125551000",
            friendly_name="(512) 555-1000",
            locality="Austin",
            region="TX",
        )
        num2 = SimpleNamespace(
            phone_number="+15125551001",
            friendly_name="(512) 555-1001",
            locality="Round Rock",
            region="TX",
        )
        mock_local = MagicMock()
        mock_local.list = MagicMock(return_value=[num1, num2])
        mock_avail = MagicMock()
        mock_avail.local = mock_local
        mock_client = MagicMock()
        mock_client.available_phone_numbers.return_value = mock_avail

        with patch("src.services.sms._get_twilio_client", return_value=mock_client):
            result = await search_available_numbers("512")

        assert len(result) == 2
        assert result[0]["phone_number"] == "+15125551000"
        assert result[0]["locality"] == "Austin"
        assert result[1]["region"] == "TX"

    async def test_raises_on_twilio_error(self):
        from src.services.sms import search_available_numbers

        mock_local = MagicMock()
        mock_local.list = MagicMock(side_effect=RuntimeError("API down"))
        mock_avail = MagicMock()
        mock_avail.local = mock_local
        mock_client = MagicMock()
        mock_client.available_phone_numbers.return_value = mock_avail

        with patch("src.services.sms._get_twilio_client", return_value=mock_client):
            with pytest.raises(RuntimeError, match="API down"):
                await search_available_numbers("512")


# ---------------------------------------------------------------------------
# provision_phone_number
# ---------------------------------------------------------------------------

class TestProvisionPhoneNumber:
    async def test_success_full_path(self):
        """Happy path: number provisioned, messaging service created, phone attached."""
        from src.services.sms import provision_phone_number

        incoming = SimpleNamespace(sid="PN_abc", phone_number="+15125551000")
        mock_client = MagicMock()
        mock_client.incoming_phone_numbers.create = MagicMock(return_value=incoming)

        settings = _make_settings()
        ms_result = {"error": None, "result": {"messaging_service_sid": "MG_new"}}
        attach_result = {"error": None}

        with patch("src.services.sms._get_twilio_client", return_value=mock_client), \
             patch("src.config.get_settings", return_value=settings), \
             patch("src.services.twilio_registration.create_messaging_service",
                   new_callable=AsyncMock, return_value=ms_result) as mock_cms, \
             patch("src.services.twilio_registration.add_phone_to_messaging_service",
                   new_callable=AsyncMock, return_value=attach_result) as mock_attach, \
             patch("src.services.twilio_registration.is_tollfree", return_value=False):
            result = await provision_phone_number(
                "+15125551000", "client-id-1234-5678", "ACME HVAC"
            )

        assert result["phone_number"] == "+15125551000"
        assert result["phone_sid"] == "PN_abc"
        assert result["messaging_service_sid"] == "MG_new"
        assert result["error"] is None
        assert result["is_tollfree"] is False
        mock_cms.assert_called_once_with("client-id-1234-5678", "ACME HVAC")
        mock_attach.assert_called_once_with("MG_new", "PN_abc")

    async def test_provision_failure(self):
        """When Twilio incoming_phone_numbers.create throws, return error dict."""
        from src.services.sms import provision_phone_number

        mock_client = MagicMock()
        mock_client.incoming_phone_numbers.create = MagicMock(
            side_effect=RuntimeError("Payment required")
        )
        settings = _make_settings()

        with patch("src.services.sms._get_twilio_client", return_value=mock_client), \
             patch("src.config.get_settings", return_value=settings), \
             patch("src.services.twilio_registration.create_messaging_service",
                   new_callable=AsyncMock), \
             patch("src.services.twilio_registration.add_phone_to_messaging_service",
                   new_callable=AsyncMock), \
             patch("src.services.twilio_registration.is_tollfree"):
            result = await provision_phone_number("+15125551000", "client-id-1234-5678")

        assert result["phone_number"] is None
        assert result["error"] == "Payment required"

    async def test_messaging_service_creation_fails(self):
        """If messaging service creation fails, messaging_service_sid is None but no crash."""
        from src.services.sms import provision_phone_number

        incoming = SimpleNamespace(sid="PN_abc", phone_number="+15125551000")
        mock_client = MagicMock()
        mock_client.incoming_phone_numbers.create = MagicMock(return_value=incoming)

        settings = _make_settings()
        ms_result = {"error": "Rate limited", "result": None}

        with patch("src.services.sms._get_twilio_client", return_value=mock_client), \
             patch("src.config.get_settings", return_value=settings), \
             patch("src.services.twilio_registration.create_messaging_service",
                   new_callable=AsyncMock, return_value=ms_result), \
             patch("src.services.twilio_registration.add_phone_to_messaging_service",
                   new_callable=AsyncMock) as mock_attach, \
             patch("src.services.twilio_registration.is_tollfree", return_value=True):
            result = await provision_phone_number("+18005551000", "client-id-1234-5678")

        assert result["messaging_service_sid"] is None
        assert result["is_tollfree"] is True
        assert result["error"] is None
        mock_attach.assert_not_called()

    async def test_attach_phone_fails_non_blocking(self):
        """If attaching phone to messaging service fails, it's non-blocking."""
        from src.services.sms import provision_phone_number

        incoming = SimpleNamespace(sid="PN_abc", phone_number="+15125551000")
        mock_client = MagicMock()
        mock_client.incoming_phone_numbers.create = MagicMock(return_value=incoming)

        settings = _make_settings()
        ms_result = {"error": None, "result": {"messaging_service_sid": "MG_new"}}
        attach_result = {"error": "Attach failed"}

        with patch("src.services.sms._get_twilio_client", return_value=mock_client), \
             patch("src.config.get_settings", return_value=settings), \
             patch("src.services.twilio_registration.create_messaging_service",
                   new_callable=AsyncMock, return_value=ms_result), \
             patch("src.services.twilio_registration.add_phone_to_messaging_service",
                   new_callable=AsyncMock, return_value=attach_result), \
             patch("src.services.twilio_registration.is_tollfree", return_value=False):
            result = await provision_phone_number("+15125551000", "client-id-1234-5678")

        assert result["messaging_service_sid"] == "MG_new"
        assert result["error"] is None


# ---------------------------------------------------------------------------
# release_phone_number
# ---------------------------------------------------------------------------

class TestReleasePhoneNumber:
    async def test_success(self):
        from src.services.sms import release_phone_number

        mock_phone = MagicMock()
        mock_phone.delete = MagicMock(return_value=None)
        mock_client = MagicMock()
        mock_client.incoming_phone_numbers.return_value = mock_phone

        with patch("src.services.sms._get_twilio_client", return_value=mock_client):
            result = await release_phone_number("PN_abc")

        assert result == {"released": True, "error": None}

    async def test_failure(self):
        from src.services.sms import release_phone_number

        mock_phone = MagicMock()
        mock_phone.delete = MagicMock(side_effect=RuntimeError("Not found"))
        mock_client = MagicMock()
        mock_client.incoming_phone_numbers.return_value = mock_phone

        with patch("src.services.sms._get_twilio_client", return_value=mock_client):
            result = await release_phone_number("PN_bad")

        assert result["released"] is False
        assert "Not found" in result["error"]


# ---------------------------------------------------------------------------
# _send_twilio (internal)
# ---------------------------------------------------------------------------

class TestSendTwilio:
    async def test_uses_messaging_service_sid_from_arg(self):
        """When messaging_service_sid is passed directly, use it."""
        from src.services.sms import _send_twilio

        mock_msg = SimpleNamespace(sid="SM_123", status="queued")
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_msg)
        settings = _make_settings(twilio_messaging_service_sid="")

        with patch("src.services.sms._get_twilio_client", return_value=mock_client), \
             patch("src.config.get_settings", return_value=settings):
            result = await _send_twilio("+15125551000", "Hello", messaging_service_sid="MG_arg")

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs[1]["messaging_service_sid"] == "MG_arg"
        assert result == {"sid": "SM_123", "status": "queued"}

    async def test_uses_messaging_service_sid_from_settings(self):
        """When no messaging_service_sid arg, falls back to settings."""
        from src.services.sms import _send_twilio

        mock_msg = SimpleNamespace(sid="SM_456", status="queued")
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_msg)
        settings = _make_settings(twilio_messaging_service_sid="MG_default_setting")

        with patch("src.services.sms._get_twilio_client", return_value=mock_client), \
             patch("src.config.get_settings", return_value=settings):
            result = await _send_twilio("+15125551000", "Hello")

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs[1]["messaging_service_sid"] == "MG_default_setting"

    async def test_uses_from_phone_when_no_msgsvc(self):
        """When no messaging_service_sid at all, use from_phone."""
        from src.services.sms import _send_twilio

        mock_msg = SimpleNamespace(sid="SM_789", status="queued")
        mock_client = MagicMock()
        mock_client.messages.create = MagicMock(return_value=mock_msg)
        settings = _make_settings(twilio_messaging_service_sid="")

        with patch("src.services.sms._get_twilio_client", return_value=mock_client), \
             patch("src.config.get_settings", return_value=settings):
            result = await _send_twilio("+15125551000", "Hello", from_phone="+15125559999")

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs[1]["from_"] == "+15125559999"
        assert "messaging_service_sid" not in call_kwargs[1]

    async def test_raises_when_no_from_or_msgsvc(self):
        """When neither from_phone nor messaging_service_sid, raise ValueError."""
        from src.services.sms import _send_twilio

        mock_client = MagicMock()
        settings = _make_settings(twilio_messaging_service_sid="")

        with patch("src.services.sms._get_twilio_client", return_value=mock_client), \
             patch("src.config.get_settings", return_value=settings):
            with pytest.raises(ValueError, match="Either from_phone or messaging_service_sid"):
                await _send_twilio("+15125551000", "Hello")


# ---------------------------------------------------------------------------
# _send_telnyx (internal)
# ---------------------------------------------------------------------------

class TestSendTelnyx:
    async def test_sends_and_returns_id(self):
        from src.services.sms import _send_telnyx

        settings = _make_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"id": "telnyx_msg_001"}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("src.config.get_settings", return_value=settings), \
             patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await _send_telnyx("+15125551000", "Hello from Telnyx")

        assert result == {"id": "telnyx_msg_001"}
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert call_args[0][0] == "https://api.telnyx.com/v2/messages"
        assert call_args[1]["json"]["to"] == "+15125551000"
        assert call_args[1]["json"]["text"] == "Hello from Telnyx"

    async def test_raises_on_http_error(self):
        import httpx
        from src.services.sms import _send_telnyx

        settings = _make_settings()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock()
            )
        )

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("src.config.get_settings", return_value=settings), \
             patch("httpx.AsyncClient", return_value=mock_client_instance):
            with pytest.raises(httpx.HTTPStatusError):
                await _send_telnyx("+15125551000", "Will fail")


# ---------------------------------------------------------------------------
# send_sms - the main orchestration function
# ---------------------------------------------------------------------------

def _patch_deliverability(send_allowed=True, throttle_reason=""):
    """Context manager to mock deliverability checks."""
    return patch.multiple(
        "src.services.deliverability",
        check_send_allowed=AsyncMock(return_value=(send_allowed, throttle_reason)),
        record_sms_outcome=AsyncMock(),
    )


class TestSendSmsThrottle:
    async def test_throttled_returns_immediately(self):
        """When deliverability says no, return throttled status without trying Twilio."""
        from src.services.sms import send_sms

        with _patch_deliverability(send_allowed=False, throttle_reason="Error rate high"):
            result = await send_sms("+15125551000", "Hi", from_phone="+15125559999")

        assert result["status"] == "throttled"
        assert result["provider"] == "none"
        assert result["error"] == "Error rate high"
        assert result["sid"] is None
        assert result["cost_usd"] == 0.0


class TestSendSmsTwilioSuccess:
    async def test_first_attempt_success(self):
        """Twilio succeeds on first try - no retries, no failover."""
        from src.services.sms import send_sms

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   return_value={"sid": "SM_ok", "status": "queued"}):
            result = await send_sms("+15125551000", "Hello!", from_phone="+15125559999")

        assert result["status"] == "queued"
        assert result["provider"] == "twilio"
        assert result["sid"] == "SM_ok"
        assert result["error"] is None
        assert result["segments"] == 1
        assert result["encoding"] == "gsm7"
        assert result["is_landline"] is False


class TestSendSmsPermanentError:
    async def test_permanent_error_no_retry(self):
        """Permanent Twilio error should NOT retry."""
        from src.services.sms import send_sms

        err = Exception("Unsubscribed")
        err.code = 21610

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=err):
            result = await send_sms("+15125551000", "Hi", from_phone="+15125559999")

        assert result["status"] == "failed"
        assert result["provider"] == "twilio"
        assert result["error_code"] == "21610"
        assert result["is_landline"] is False

    async def test_landline_error_sets_flag(self):
        """Landline error code 30006 should set is_landline=True."""
        from src.services.sms import send_sms

        err = Exception("Landline")
        err.code = 30006

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=err):
            result = await send_sms("+15125551000", "Hi", from_phone="+15125559999")

        assert result["is_landline"] is True
        assert result["error_code"] == "30006"
        assert result["status"] == "failed"

    async def test_invalid_number_error(self):
        """Invalid number error code 21211 should be permanent."""
        from src.services.sms import send_sms

        err = Exception("Invalid To number")
        err.code = 21211

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=err):
            result = await send_sms("+10000000000", "Hi", from_phone="+15125559999")

        assert result["status"] == "failed"
        assert result["error_code"] == "21211"


class TestSendSmsTransientAndFailover:
    async def test_transient_error_retries_then_succeeds(self):
        """Transient error on first attempt, then Twilio succeeds on retry."""
        from src.services.sms import send_sms

        err = Exception("Filtered")
        err.code = 30007

        call_count = 0

        async def twilio_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise err
            return {"sid": "SM_retry", "status": "queued"}

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=twilio_side_effect), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await send_sms("+15125551000", "Hi", from_phone="+15125559999")

        assert result["status"] == "queued"
        assert result["provider"] == "twilio"
        assert call_count == 2

    async def test_all_retries_exhausted_telnyx_success(self):
        """All Twilio retries fail (transient), then Telnyx succeeds."""
        from src.services.sms import send_sms

        err = Exception("Unknown error")
        err.code = 30008

        settings = _make_settings()

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=err), \
             patch("src.services.sms._send_telnyx", new_callable=AsyncMock,
                   return_value={"id": "telnyx_ok"}) as mock_telnyx, \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("src.config.get_settings", return_value=settings):
            result = await send_sms("+15125551000", "Hi", from_phone="+15125559999")

        assert result["status"] == "sent"
        assert result["provider"] == "telnyx"
        assert result["sid"] == "telnyx_ok"
        assert result["error"] is None
        mock_telnyx.assert_called_once()

    async def test_all_retries_exhausted_telnyx_fails(self):
        """All Twilio retries fail, Telnyx also fails."""
        from src.services.sms import send_sms

        twilio_err = Exception("Carrier issue")
        twilio_err.code = 30008

        settings = _make_settings()

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=twilio_err), \
             patch("src.services.sms._send_telnyx", new_callable=AsyncMock,
                   side_effect=RuntimeError("Telnyx down")), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("src.config.get_settings", return_value=settings):
            result = await send_sms("+15125551000", "Hi", from_phone="+15125559999")

        assert result["status"] == "failed"
        assert result["provider"] == "none"
        assert "All providers failed" in result["error"]
        assert result["error_code"] == "30008"

    async def test_all_retries_exhausted_no_telnyx_configured(self):
        """All Twilio retries fail and Telnyx is not configured."""
        from src.services.sms import send_sms

        err = Exception("Carrier down")
        err.code = 30009

        settings = _make_settings(telnyx_api_key="")

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=err), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("src.config.get_settings", return_value=settings):
            result = await send_sms("+15125551000", "Hi", from_phone="+15125559999")

        assert result["status"] == "failed"
        assert result["provider"] == "none"
        assert "Telnyx not configured" in result["error"]
        assert result["error_code"] == "30009"


class TestSendSmsEncodingAndSegments:
    async def test_ucs2_message(self):
        """UCS-2 message should have correct encoding in result."""
        from src.services.sms import send_sms

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   return_value={"sid": "SM_ucs2", "status": "sent"}):
            result = await send_sms(
                "+15125551000",
                "\u2014" * 50,  # em dashes, UCS-2
                from_phone="+15125559999",
            )

        assert result["encoding"] == "ucs2"
        assert result["segments"] == 1

    async def test_multi_segment_cost(self):
        """Cost should be segments * per-segment cost."""
        from src.services.sms import send_sms, TWILIO_OUTBOUND_COST

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   return_value={"sid": "SM_multi", "status": "sent"}):
            result = await send_sms(
                "+15125551000",
                "x" * 300,  # 2 segments in GSM
                from_phone="+15125559999",
            )

        assert result["segments"] == 2
        assert result["cost_usd"] == pytest.approx(2 * TWILIO_OUTBOUND_COST)


class TestSendSmsDefaultFromPhone:
    async def test_none_from_phone_defaults_to_default_key(self):
        """When from_phone is None, deliverability uses 'default' key."""
        from src.services.sms import send_sms

        check_mock = AsyncMock(return_value=(True, ""))
        record_mock = AsyncMock()

        with patch("src.services.deliverability.check_send_allowed", check_mock), \
             patch("src.services.deliverability.record_sms_outcome", record_mock), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   return_value={"sid": "SM_def", "status": "sent"}):
            result = await send_sms(
                "+15125551000",
                "Hello",
                messaging_service_sid="MG_test",
            )

        check_mock.assert_called_once_with("default")
        record_mock.assert_called_once_with("default", "+15125551000", "sent", provider="twilio")
        assert result["status"] == "sent"


class TestSendSmsUnknownTransientError:
    async def test_unknown_error_retries_like_transient(self):
        """An error with no known code should still trigger retries."""
        from src.services.sms import send_sms

        err = Exception("Something weird happened")
        # No .code attribute, no known code in message => classify_error returns "unknown"

        call_count = 0

        async def twilio_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise err
            return {"sid": "SM_recovered", "status": "sent"}

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=twilio_side_effect), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await send_sms("+15125551000", "Hello", from_phone="+15125559999")

        assert result["status"] == "sent"
        assert call_count == 3  # 2 failures + 1 success


class TestSendSmsTelnyxCostCalculation:
    async def test_telnyx_uses_correct_cost(self):
        """Telnyx failover should use TELNYX_OUTBOUND_COST."""
        from src.services.sms import send_sms, TELNYX_OUTBOUND_COST

        err = Exception("Twilio down")
        err.code = 30008
        settings = _make_settings()

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=err), \
             patch("src.services.sms._send_telnyx", new_callable=AsyncMock,
                   return_value={"id": "tel_1"}), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("src.config.get_settings", return_value=settings):
            result = await send_sms("+15125551000", "Cost test", from_phone="+15125559999")

        assert result["cost_usd"] == pytest.approx(1 * TELNYX_OUTBOUND_COST)
        assert result["provider"] == "telnyx"


class TestSendSmsRecordsOutcome:
    async def test_records_failed_outcome_on_permanent_error(self):
        """Permanent error should call record_sms_outcome with 'failed'."""
        from src.services.sms import send_sms

        err = Exception("Invalid")
        err.code = 21211

        record_mock = AsyncMock()

        with patch("src.services.deliverability.check_send_allowed",
                   AsyncMock(return_value=(True, ""))), \
             patch("src.services.deliverability.record_sms_outcome", record_mock), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=err):
            await send_sms("+15125551000", "Hi", from_phone="+15125559999")

        record_mock.assert_called_once_with(
            "+15125559999", "+15125551000", "failed", "21211", "twilio"
        )

    async def test_records_telnyx_sent_outcome(self):
        """Telnyx success should record outcome with provider='telnyx'."""
        from src.services.sms import send_sms

        err = Exception("All Twilio failed")
        err.code = 30008
        settings = _make_settings()

        record_mock = AsyncMock()

        with patch("src.services.deliverability.check_send_allowed",
                   AsyncMock(return_value=(True, ""))), \
             patch("src.services.deliverability.record_sms_outcome", record_mock), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   side_effect=err), \
             patch("src.services.sms._send_telnyx", new_callable=AsyncMock,
                   return_value={"id": "tel_2"}), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("src.config.get_settings", return_value=settings):
            await send_sms("+15125551000", "Hi", from_phone="+15125559999")

        # record_sms_outcome called for telnyx success
        last_call = record_mock.call_args_list[-1]
        assert last_call[0] == ("+15125559999", "+15125551000", "sent")
        assert last_call[1] == {"provider": "telnyx"}


class TestSendSmsMessageTruncation:
    async def test_long_message_gets_truncated(self):
        """Very long messages should be truncated before sending."""
        from src.services.sms import send_sms, MAX_SEGMENTS

        with _patch_deliverability(), \
             patch("src.services.sms._send_twilio", new_callable=AsyncMock,
                   return_value={"sid": "SM_trunc", "status": "sent"}):
            result = await send_sms(
                "+15125551000",
                "x" * 1000,  # Way over 3 segments
                from_phone="+15125559999",
            )

        assert result["segments"] <= MAX_SEGMENTS
        assert result["status"] == "sent"
