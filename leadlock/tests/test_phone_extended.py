"""
Extended tests for src/utils/phone.py - covers regex fallback paths,
phonenumbers library branches (mocked since library is not installed),
and is_valid_us_phone regex fallback.
"""
import pytest
from unittest.mock import patch, MagicMock
import importlib


# ---------------------------------------------------------------------------
# _normalize_with_phonenumbers (lines 48-56) - mocked phonenumbers
# ---------------------------------------------------------------------------

class TestNormalizeWithPhonenumbers:
    """Test _normalize_with_phonenumbers by mocking the phonenumbers module."""

    def test_valid_us_number(self):
        """Valid number through phonenumbers returns E.164 (lines 50-54)."""
        mock_pn = MagicMock()
        mock_parsed = MagicMock()
        mock_pn.parse.return_value = mock_parsed
        mock_pn.is_valid_number.return_value = True
        mock_pn.format_number.return_value = "+15125551234"
        mock_pn.PhoneNumberFormat.E164 = 0
        mock_pn.NumberParseException = Exception

        with patch.dict("sys.modules", {"phonenumbers": mock_pn}):
            # Reload the module so it picks up the mock
            import src.utils.phone as phone_mod
            # Manually set up the state
            original_has = phone_mod._HAS_PHONENUMBERS
            phone_mod._HAS_PHONENUMBERS = True
            phone_mod.phonenumbers = mock_pn

            try:
                result = phone_mod._normalize_with_phonenumbers("(512) 555-1234", "US")
                assert result == "+15125551234"
                mock_pn.parse.assert_called_once_with("(512) 555-1234", "US")
                mock_pn.is_valid_number.assert_called_once_with(mock_parsed)
            finally:
                phone_mod._HAS_PHONENUMBERS = original_has

    def test_invalid_number_returns_none(self):
        """Invalid number (is_valid_number=False) returns None (line 52-53)."""
        mock_pn = MagicMock()
        mock_pn.parse.return_value = MagicMock()
        mock_pn.is_valid_number.return_value = False
        mock_pn.NumberParseException = Exception

        with patch.dict("sys.modules", {"phonenumbers": mock_pn}):
            import src.utils.phone as phone_mod
            original_has = phone_mod._HAS_PHONENUMBERS
            phone_mod._HAS_PHONENUMBERS = True
            phone_mod.phonenumbers = mock_pn

            try:
                result = phone_mod._normalize_with_phonenumbers("12345", "US")
                assert result is None
            finally:
                phone_mod._HAS_PHONENUMBERS = original_has

    def test_parse_exception_returns_none(self):
        """NumberParseException returns None (lines 55-56)."""
        mock_pn = MagicMock()

        class FakeParseException(Exception):
            pass

        mock_pn.NumberParseException = FakeParseException
        mock_pn.parse.side_effect = FakeParseException("bad number")

        with patch.dict("sys.modules", {"phonenumbers": mock_pn}):
            import src.utils.phone as phone_mod
            original_has = phone_mod._HAS_PHONENUMBERS
            phone_mod._HAS_PHONENUMBERS = True
            phone_mod.phonenumbers = mock_pn

            try:
                result = phone_mod._normalize_with_phonenumbers("not-a-number", "US")
                assert result is None
            finally:
                phone_mod._HAS_PHONENUMBERS = original_has


# ---------------------------------------------------------------------------
# normalize_phone_e164 routing through phonenumbers (line 44)
# ---------------------------------------------------------------------------

class TestNormalizePhoneE164Routing:
    """Test normalize_phone_e164 routing when _HAS_PHONENUMBERS is True."""

    def test_routes_to_phonenumbers_when_available(self):
        """When _HAS_PHONENUMBERS is True, calls _normalize_with_phonenumbers (line 44)."""
        import src.utils.phone as phone_mod

        with patch.object(
            phone_mod, "_HAS_PHONENUMBERS", True
        ), patch.object(
            phone_mod, "_normalize_with_phonenumbers", return_value="+15125551234"
        ) as mock_norm:
            result = phone_mod.normalize_phone_e164("(512) 555-1234")
            assert result == "+15125551234"
            mock_norm.assert_called_once_with("(512) 555-1234", "US")

    def test_routes_to_regex_when_phonenumbers_unavailable(self):
        """When _HAS_PHONENUMBERS is False, uses regex (line 45)."""
        import src.utils.phone as phone_mod

        with patch.object(phone_mod, "_HAS_PHONENUMBERS", False):
            result = phone_mod.normalize_phone_e164("5125551234")
            assert result == "+15125551234"


# ---------------------------------------------------------------------------
# _normalize_with_regex - fallback paths (lines 65-68, 70-71)
# ---------------------------------------------------------------------------

class TestNormalizeWithRegex:
    """Test _normalize_with_regex edge cases for full coverage."""

    def test_10_digit_number(self):
        """10 digits get +1 prefix (lines 63-64)."""
        from src.utils.phone import _normalize_with_regex

        result = _normalize_with_regex("5125551234")
        assert result == "+15125551234"

    def test_11_digit_with_leading_1(self):
        """11 digits starting with 1 (lines 65-66)."""
        from src.utils.phone import _normalize_with_regex

        result = _normalize_with_regex("15125551234")
        assert result == "+15125551234"

    def test_more_than_11_digits_starting_with_1(self):
        """More than 11 digits starting with 1 - truncates to 11 (lines 67-68)."""
        from src.utils.phone import _normalize_with_regex

        result = _normalize_with_regex("151255512349999")
        assert result == "+15125551234"

    def test_plus_prefix_with_10_or_more_digits(self):
        """Phone starting with '+' and has >= 10 digits (lines 70-71)."""
        from src.utils.phone import _normalize_with_regex

        result = _normalize_with_regex("+442071234567")
        assert result == "+442071234567"

    def test_plus_prefix_with_fewer_than_10_digits(self):
        """Phone starting with '+' but fewer than 10 digits returns None."""
        from src.utils.phone import _normalize_with_regex

        result = _normalize_with_regex("+12345")
        assert result is None

    def test_short_number_returns_none(self):
        """Short digit string returns None."""
        from src.utils.phone import _normalize_with_regex

        result = _normalize_with_regex("123")
        assert result is None


# ---------------------------------------------------------------------------
# is_valid_us_phone - phonenumbers path (lines 81-86) and regex fallback (88-89)
# ---------------------------------------------------------------------------

class TestIsValidUsPhoneWithPhonenumbers:
    """Cover is_valid_us_phone through mocked phonenumbers."""

    def test_valid_us_phone_with_phonenumbers(self):
        """Valid US E.164 through phonenumbers (lines 82-84)."""
        mock_pn = MagicMock()
        mock_pn.parse.return_value = MagicMock()
        mock_pn.is_valid_number.return_value = True
        mock_pn.NumberParseException = Exception

        import src.utils.phone as phone_mod
        original_has = phone_mod._HAS_PHONENUMBERS
        phone_mod._HAS_PHONENUMBERS = True
        phone_mod.phonenumbers = mock_pn

        try:
            result = phone_mod.is_valid_us_phone("+15125551234")
            assert result is True
            mock_pn.parse.assert_called_once_with("+15125551234", "US")
        finally:
            phone_mod._HAS_PHONENUMBERS = original_has

    def test_invalid_us_phone_with_phonenumbers(self):
        """Invalid US phone through phonenumbers returns False."""
        mock_pn = MagicMock()
        mock_pn.parse.return_value = MagicMock()
        mock_pn.is_valid_number.return_value = False
        mock_pn.NumberParseException = Exception

        import src.utils.phone as phone_mod
        original_has = phone_mod._HAS_PHONENUMBERS
        phone_mod._HAS_PHONENUMBERS = True
        phone_mod.phonenumbers = mock_pn

        try:
            result = phone_mod.is_valid_us_phone("+10000000000")
            assert result is False
        finally:
            phone_mod._HAS_PHONENUMBERS = original_has

    def test_parse_exception_returns_false(self):
        """NumberParseException in is_valid_us_phone returns False (lines 85-86)."""
        mock_pn = MagicMock()

        class FakeParseException(Exception):
            pass

        mock_pn.NumberParseException = FakeParseException
        mock_pn.parse.side_effect = FakeParseException("bad")

        import src.utils.phone as phone_mod
        original_has = phone_mod._HAS_PHONENUMBERS
        phone_mod._HAS_PHONENUMBERS = True
        phone_mod.phonenumbers = mock_pn

        try:
            result = phone_mod.is_valid_us_phone("+15125551234")
            assert result is False
        finally:
            phone_mod._HAS_PHONENUMBERS = original_has

    def test_regex_fallback_valid(self):
        """When phonenumbers not available, uses regex path (lines 88-89)."""
        import src.utils.phone as phone_mod
        # phonenumbers not installed so _HAS_PHONENUMBERS should be False already
        assert phone_mod._HAS_PHONENUMBERS is False

        assert phone_mod.is_valid_us_phone("+15125551234") is True
        assert phone_mod.is_valid_us_phone("+1512") is False
