"""
Extended tests for src/utils/webhook_signatures.py - covers HMAC exception path,
webhook source validation with secrets configured, and generic signing key path.
"""
import hashlib
import hmac

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.webhook_signatures import (
    validate_hmac_sha256,
    validate_webhook_source,
)


# ---------------------------------------------------------------------------
# validate_hmac_sha256 - exception path (lines 65-67)
# ---------------------------------------------------------------------------

class TestValidateHmacSha256Exception:
    """Cover the exception handling in validate_hmac_sha256."""

    def test_hmac_exception_returns_false(self):
        """When hmac.new raises, returns False (lines 65-67)."""
        with patch("src.utils.webhook_signatures.hmac.new", side_effect=Exception("HMAC error")):
            result = validate_hmac_sha256("secret", "sha256=abc123", b"body")
            assert result is False


# ---------------------------------------------------------------------------
# validate_webhook_source - with secrets configured (lines 111-112, 127-128, 138-139, 149-150, 154-156)
# ---------------------------------------------------------------------------

def _make_valid_signature(secret: str, body: bytes) -> str:
    """Helper: compute a valid HMAC-SHA256 signature with sha256= prefix."""
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


class TestValidateWebhookSourceWithSecrets:
    """Cover webhook source validation when secrets ARE configured."""

    async def test_twilio_with_auth_token_validates(self):
        """Twilio source with auth_token configured validates signature (lines 111-112)."""
        request = MagicMock()
        request.headers = {
            "X-Twilio-Signature": "valid_sig",
            "x-forwarded-proto": "https",
            "x-forwarded-host": "api.leadlock.org",
        }
        request.url.path = "/webhook"
        request.url.query = ""

        mock_settings = MagicMock()
        mock_settings.twilio_auth_token = "test_auth_token"

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch(
                "src.utils.webhook_signatures.validate_twilio_signature",
                return_value=True,
            ) as mock_validate,
        ):
            result = await validate_webhook_source("twilio", request, b"body", {"Body": "test"})

            assert result is True
            mock_validate.assert_called_once_with(
                "test_auth_token",
                "valid_sig",
                "https://api.leadlock.org/webhook",
                {"Body": "test"},
            )

    async def test_google_lsa_with_secret_valid_signature(self):
        """Google LSA source with valid signature (lines 127-128)."""
        secret = "google_secret_key"
        body = b'{"event": "lead_received"}'
        sig = _make_valid_signature(secret, body)

        request = MagicMock()
        request.headers = {"X-Webhook-Signature": sig}

        mock_settings = MagicMock()
        mock_settings.webhook_secret_google = secret

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await validate_webhook_source("google_lsa", request, body)
            assert result is True

    async def test_google_lsa_with_secret_invalid_signature(self):
        """Google LSA source with invalid signature returns False."""
        request = MagicMock()
        request.headers = {"X-Webhook-Signature": "sha256=invalid"}

        mock_settings = MagicMock()
        mock_settings.webhook_secret_google = "google_secret_key"

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await validate_webhook_source("google_lsa", request, b"body")
            assert result is False

    async def test_angi_with_secret_valid_signature(self):
        """Angi source with valid signature (lines 138-139)."""
        secret = "angi_secret_key"
        body = b'{"lead": "data"}'
        sig = _make_valid_signature(secret, body)

        request = MagicMock()
        request.headers = {"X-Webhook-Signature": sig}

        mock_settings = MagicMock()
        mock_settings.webhook_secret_angi = secret

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await validate_webhook_source("angi", request, body)
            assert result is True

    async def test_angi_with_secret_invalid_signature(self):
        """Angi source with invalid signature returns False."""
        request = MagicMock()
        request.headers = {"X-Webhook-Signature": "sha256=wrong"}

        mock_settings = MagicMock()
        mock_settings.webhook_secret_angi = "angi_secret_key"

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await validate_webhook_source("angi", request, b"body")
            assert result is False

    async def test_facebook_with_secret_valid_signature(self):
        """Facebook source with valid X-Hub-Signature-256 (lines 149-150)."""
        secret = "fb_secret_key"
        body = b'{"entry": []}'
        sig = _make_valid_signature(secret, body)

        request = MagicMock()
        request.headers = {"X-Hub-Signature-256": sig}

        mock_settings = MagicMock()
        mock_settings.webhook_secret_facebook = secret

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await validate_webhook_source("facebook", request, body)
            assert result is True

    async def test_facebook_with_secret_invalid_signature(self):
        """Facebook source with invalid signature returns False."""
        request = MagicMock()
        request.headers = {"X-Hub-Signature-256": "sha256=invalid"}

        mock_settings = MagicMock()
        mock_settings.webhook_secret_facebook = "fb_secret_key"

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await validate_webhook_source("facebook", request, b"body")
            assert result is False

    async def test_generic_source_with_signing_key_valid(self):
        """Generic source with webhook_signing_key and valid signature (lines 154-156)."""
        secret = "generic_signing_key"
        body = b'{"data": "payload"}'
        sig = _make_valid_signature(secret, body)

        request = MagicMock()
        request.headers = {"X-Webhook-Signature": sig}

        mock_settings = MagicMock()
        mock_settings.webhook_signing_key = secret

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await validate_webhook_source("custom_crm", request, body)
            assert result is True

    async def test_generic_source_with_signing_key_invalid(self):
        """Generic source with webhook_signing_key and invalid signature returns False."""
        request = MagicMock()
        request.headers = {"X-Webhook-Signature": "sha256=bad"}

        mock_settings = MagicMock()
        mock_settings.webhook_signing_key = "generic_signing_key"

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await validate_webhook_source("custom_crm", request, body=b"body")
            assert result is False

    async def test_generic_source_with_signing_key_no_signature_header(self):
        """Generic source with key configured but no signature header falls through."""
        request = MagicMock()
        request.headers = {}

        mock_settings = MagicMock()
        mock_settings.webhook_signing_key = "generic_signing_key"

        with patch("src.config.get_settings", return_value=mock_settings):
            result = await validate_webhook_source("custom_crm", request, b"body")
            # No X-Webhook-Signature header => sig is empty string => falls through
            # to the final warning + return True
            assert result is True
