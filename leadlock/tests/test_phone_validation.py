"""
Tests for src/services/phone_validation.py - phone normalization, validation, lookup, masking.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.phone_validation import (
    normalize_phone,
    is_valid_us_phone,
    lookup_phone,
    mask_phone_for_log,
)


# ---------------------------------------------------------------------------
# normalize_phone
# ---------------------------------------------------------------------------

class TestNormalizePhone:
    """Normalization delegates to src.utils.phone.normalize_phone_e164."""

    def test_valid_us_ten_digit(self):
        result = normalize_phone("5551234567")
        assert result == "+15551234567"

    def test_valid_us_with_country_code(self):
        result = normalize_phone("+15551234567")
        assert result == "+15551234567"

    def test_valid_formatted_with_dashes(self):
        result = normalize_phone("555-123-4567")
        assert result == "+15551234567"

    def test_valid_formatted_with_parens(self):
        result = normalize_phone("(555) 123-4567")
        assert result == "+15551234567"

    def test_valid_with_dots(self):
        result = normalize_phone("555.123.4567")
        assert result == "+15551234567"

    def test_invalid_too_short(self):
        result = normalize_phone("12345")
        assert result is None

    def test_empty_string(self):
        result = normalize_phone("")
        assert result is None

    def test_invalid_letters(self):
        result = normalize_phone("not-a-phone")
        assert result is None


# ---------------------------------------------------------------------------
# is_valid_us_phone
# ---------------------------------------------------------------------------

class TestIsValidUsPhone:
    def test_valid_e164(self):
        assert is_valid_us_phone("+15551234567") is True

    def test_missing_plus(self):
        assert is_valid_us_phone("15551234567") is False

    def test_non_us_country_code(self):
        assert is_valid_us_phone("+445551234567") is False

    def test_empty_string(self):
        assert is_valid_us_phone("") is False

    def test_too_short(self):
        assert is_valid_us_phone("+1555") is False


# ---------------------------------------------------------------------------
# lookup_phone
# ---------------------------------------------------------------------------

class TestLookupPhone:
    @pytest.mark.asyncio
    async def test_successful_lookup(self):
        """Twilio lookup returns phone type and carrier."""
        mock_lookup_result = MagicMock()
        mock_lookup_result.line_type_intelligence = {
            "type": "mobile",
            "carrier_name": "T-Mobile",
        }

        mock_twilio = MagicMock()
        mock_twilio.lookups.v2.phone_numbers.return_value.fetch = MagicMock(
            return_value=mock_lookup_result
        )

        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = "ACtest"
        mock_settings.twilio_auth_token = "authtest"

        with (
            patch("src.services.phone_validation.normalize_phone", return_value="+15551234567"),
            patch("src.config.get_settings", return_value=mock_settings),
            patch("twilio.rest.Client", return_value=mock_twilio),
            patch("asyncio.get_running_loop") as mock_loop,
        ):
            # Make run_in_executor call the lambda directly
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value=mock_lookup_result
            )

            result = await lookup_phone("+15551234567")

        assert result["valid"] is True
        assert result["phone_type"] == "mobile"
        assert result["carrier"] == "T-Mobile"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_lookup_failure_returns_valid_true(self):
        """When Twilio lookup fails, fail-open: valid=True, phone_type=unknown."""
        mock_settings = MagicMock()
        mock_settings.twilio_account_sid = "ACtest"
        mock_settings.twilio_auth_token = "authtest"

        with (
            patch("src.services.phone_validation.normalize_phone", return_value="+15551234567"),
            patch("src.config.get_settings", return_value=mock_settings),
            patch("twilio.rest.Client", side_effect=Exception("Twilio down")),
        ):
            result = await lookup_phone("+15551234567")

        assert result["valid"] is True
        assert result["phone_type"] == "unknown"
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_lookup_invalid_phone_returns_invalid(self):
        """Invalid phone number returns valid=False before hitting Twilio."""
        with patch("src.services.phone_validation.normalize_phone", return_value=None):
            result = await lookup_phone("bad-number")

        assert result["valid"] is False
        assert "Invalid phone number format" in result["error"]


# ---------------------------------------------------------------------------
# mask_phone_for_log
# ---------------------------------------------------------------------------

class TestMaskPhoneForLog:
    def test_masks_after_six_chars(self):
        assert mask_phone_for_log("+15551234567") == "+15551***"

    def test_short_phone_returned_as_is(self):
        assert mask_phone_for_log("+1555") == "+1555"

    def test_exactly_six_chars(self):
        assert mask_phone_for_log("+15551") == "+15551"

    def test_seven_chars(self):
        assert mask_phone_for_log("+155512") == "+15551***"
