"""
Webhook signature validation tests.
These protect the authentication boundary for all inbound data.
"""
import hashlib
import hmac

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.utils.webhook_signatures import (
    validate_twilio_signature,
    validate_hmac_sha256,
    compute_payload_hash,
    get_webhook_url,
    validate_webhook_source,
)


class TestValidateTwilioSignature:
    """Test Twilio HMAC-SHA1 signature validation."""

    def test_missing_signature_returns_false(self):
        result = validate_twilio_signature(
            auth_token="test_token",
            signature="",
            url="https://example.com/webhook",
            params={},
        )
        assert result is False

    def test_none_signature_returns_false(self):
        result = validate_twilio_signature(
            auth_token="test_token",
            signature=None,
            url="https://example.com/webhook",
            params={},
        )
        assert result is False

    @patch("src.utils.webhook_signatures.RequestValidator", create=True)
    def test_valid_signature_returns_true(self, mock_validator_cls):
        """Valid Twilio signature should return True."""
        # Import is inside the function, so we patch via the module
        with patch("twilio.request_validator.RequestValidator") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.validate.return_value = True
            mock_cls.return_value = mock_instance

            result = validate_twilio_signature(
                auth_token="test_token",
                signature="valid_sig",
                url="https://example.com/webhook",
                params={"Body": "test"},
            )
            assert result is True
            mock_instance.validate.assert_called_once_with(
                "https://example.com/webhook", {"Body": "test"}, "valid_sig"
            )

    @patch("twilio.request_validator.RequestValidator")
    def test_invalid_signature_returns_false(self, mock_cls):
        mock_instance = MagicMock()
        mock_instance.validate.return_value = False
        mock_cls.return_value = mock_instance

        result = validate_twilio_signature(
            auth_token="test_token",
            signature="invalid_sig",
            url="https://example.com/webhook",
            params={},
        )
        assert result is False

    @patch("twilio.request_validator.RequestValidator")
    def test_exception_returns_false(self, mock_cls):
        mock_cls.side_effect = Exception("import error")
        result = validate_twilio_signature(
            auth_token="test_token",
            signature="some_sig",
            url="https://example.com/webhook",
            params={},
        )
        assert result is False


class TestValidateHmacSha256:
    """Test generic HMAC-SHA256 signature validation."""

    def test_valid_signature(self):
        secret = "my_secret"
        body = b'{"event": "test"}'
        expected_sig = hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

        result = validate_hmac_sha256(secret, f"sha256={expected_sig}", body)
        assert result is True

    def test_valid_signature_without_prefix(self):
        secret = "my_secret"
        body = b'{"event": "test"}'
        expected_sig = hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

        result = validate_hmac_sha256(
            secret, expected_sig, body, header_prefix=""
        )
        assert result is True

    def test_invalid_signature(self):
        result = validate_hmac_sha256(
            "my_secret", "sha256=invalid_hex", b"body"
        )
        assert result is False

    def test_empty_secret_returns_false(self):
        result = validate_hmac_sha256("", "sha256=abc", b"body")
        assert result is False

    def test_empty_signature_returns_false(self):
        result = validate_hmac_sha256("secret", "", b"body")
        assert result is False

    def test_none_secret_returns_false(self):
        result = validate_hmac_sha256(None, "sha256=abc", b"body")
        assert result is False


class TestComputePayloadHash:
    def test_consistent_hash(self):
        body = b'{"test": true}'
        h1 = compute_payload_hash(body)
        h2 = compute_payload_hash(body)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_different_payloads_different_hashes(self):
        assert compute_payload_hash(b"a") != compute_payload_hash(b"b")


class TestGetWebhookUrl:
    @pytest.mark.asyncio
    async def test_reconstructs_url_from_forwarded_headers(self):
        request = MagicMock()
        request.headers = {
            "x-forwarded-proto": "https",
            "x-forwarded-host": "api.leadlock.org",
        }
        request.url.path = "/api/v1/webhook/twilio/sms/123"
        request.url.query = ""

        url = await get_webhook_url(request)
        assert url == "https://api.leadlock.org/api/v1/webhook/twilio/sms/123"

    @pytest.mark.asyncio
    async def test_includes_query_params(self):
        request = MagicMock()
        request.headers = {
            "x-forwarded-proto": "https",
            "x-forwarded-host": "api.leadlock.org",
        }
        request.url.path = "/webhook"
        request.url.query = "foo=bar"

        url = await get_webhook_url(request)
        assert url == "https://api.leadlock.org/webhook?foo=bar"

    @pytest.mark.asyncio
    async def test_defaults_to_https_when_no_forwarded_proto(self):
        request = MagicMock()
        request.headers = {"host": "localhost:8000"}
        request.url.path = "/webhook"
        request.url.query = ""

        url = await get_webhook_url(request)
        assert url == "https://localhost:8000/webhook"


class TestValidateWebhookSource:
    @pytest.mark.asyncio
    async def test_twilio_with_no_auth_token_accepts(self):
        """When twilio_auth_token is not configured, accept the webhook."""
        request = MagicMock()
        request.headers = {}

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value.twilio_auth_token = None
            result = await validate_webhook_source("twilio", request, b"", {})
            assert result is True

    @pytest.mark.asyncio
    async def test_unknown_source_without_signing_key_accepts(self):
        """Unknown source without webhook_signing_key accepts (soft enforcement)."""
        request = MagicMock()
        request.headers = {}

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value.webhook_signing_key = None
            result = await validate_webhook_source("custom_source", request, b"", {})
            assert result is True

    @pytest.mark.asyncio
    async def test_google_lsa_without_secret_accepts(self):
        request = MagicMock()
        request.headers = {}

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value.webhook_secret_google = None
            result = await validate_webhook_source("google_lsa", request, b"", {})
            assert result is True

    @pytest.mark.asyncio
    async def test_angi_without_secret_accepts(self):
        request = MagicMock()
        request.headers = {}

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value.webhook_secret_angi = None
            result = await validate_webhook_source("angi", request, b"", {})
            assert result is True

    @pytest.mark.asyncio
    async def test_facebook_without_secret_accepts(self):
        request = MagicMock()
        request.headers = {}

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value.webhook_secret_facebook = None
            result = await validate_webhook_source("facebook", request, b"", {})
            assert result is True
