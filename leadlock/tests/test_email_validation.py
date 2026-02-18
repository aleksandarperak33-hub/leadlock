"""
Email validation tests — format checking and MX record verification.
Prevents sending to invalid emails, protects sender reputation.
"""
import sys
import types
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from src.utils.email_validation import is_valid_email_format, has_mx_record, validate_email


class TestIsValidEmailFormat:
    """Test RFC 5322 simplified email format validation."""

    def test_valid_standard_email(self):
        assert is_valid_email_format("john@example.com") is True

    def test_valid_with_dots(self):
        assert is_valid_email_format("john.smith@example.com") is True

    def test_valid_with_plus(self):
        assert is_valid_email_format("john+tag@example.com") is True

    def test_valid_with_subdomain(self):
        assert is_valid_email_format("user@mail.example.co.uk") is True

    def test_valid_with_numbers(self):
        assert is_valid_email_format("user123@domain456.com") is True

    def test_invalid_no_at(self):
        assert is_valid_email_format("johndomain.com") is False

    def test_invalid_no_domain(self):
        assert is_valid_email_format("john@") is False

    def test_invalid_no_tld(self):
        assert is_valid_email_format("john@domain") is False

    def test_invalid_double_at(self):
        assert is_valid_email_format("john@@example.com") is False

    def test_invalid_spaces(self):
        assert is_valid_email_format("john @example.com") is False

    def test_empty_string(self):
        assert is_valid_email_format("") is False

    def test_none_returns_false(self):
        # Passing None will fail the `not email` check
        assert is_valid_email_format(None) is False

    def test_too_long_email(self):
        """Emails over 254 chars are invalid per RFC."""
        long_local = "a" * 245
        assert is_valid_email_format(f"{long_local}@example.com") is False

    def test_strips_whitespace(self):
        """Leading/trailing whitespace should be stripped before check."""
        assert is_valid_email_format("  john@example.com  ") is True

    def test_single_char_tld_invalid(self):
        """TLD must be at least 2 chars."""
        assert is_valid_email_format("john@example.c") is False


def _make_fake_dns():
    """Create fake dns.resolver module for testing without dnspython installed."""
    dns_mod = types.ModuleType("dns")
    resolver_mod = types.ModuleType("dns.resolver")

    class NXDOMAIN(Exception):
        pass

    class NoAnswer(Exception):
        pass

    resolver_mod.NXDOMAIN = NXDOMAIN
    resolver_mod.NoAnswer = NoAnswer
    resolver_mod.resolve = MagicMock()

    dns_mod.resolver = resolver_mod
    return dns_mod, resolver_mod


class TestHasMxRecord:
    """Test DNS MX record checking."""

    async def test_valid_mx_record(self):
        """Domain with MX records should return True."""
        dns_mod, resolver_mod = _make_fake_dns()
        resolver_mod.resolve = MagicMock(return_value=[MagicMock()])

        with patch.dict(sys.modules, {"dns": dns_mod, "dns.resolver": resolver_mod}):
            # Re-import to pick up the fake module
            result = await has_mx_record("example.com")
            assert result is True

    async def test_nxdomain_returns_false(self):
        """Non-existent domain should return False."""
        dns_mod, resolver_mod = _make_fake_dns()
        resolver_mod.resolve = MagicMock(side_effect=resolver_mod.NXDOMAIN())

        with patch.dict(sys.modules, {"dns": dns_mod, "dns.resolver": resolver_mod}):
            result = await has_mx_record("nonexistent-domain-xyz.com")
            assert result is False

    async def test_no_mx_falls_back_to_a_record(self):
        """If no MX, should check A record."""
        dns_mod, resolver_mod = _make_fake_dns()

        def side_effect(domain, record_type):
            if record_type == "MX":
                raise resolver_mod.NoAnswer()
            return [MagicMock()]  # A record found

        resolver_mod.resolve = MagicMock(side_effect=side_effect)

        with patch.dict(sys.modules, {"dns": dns_mod, "dns.resolver": resolver_mod}):
            result = await has_mx_record("example.com")
            assert result is True

    async def test_generic_exception_returns_true(self):
        """DNS errors should fail open (return True)."""
        dns_mod, resolver_mod = _make_fake_dns()
        resolver_mod.resolve = MagicMock(side_effect=Exception("DNS timeout"))

        with patch.dict(sys.modules, {"dns": dns_mod, "dns.resolver": resolver_mod}):
            result = await has_mx_record("example.com")
            assert result is True

    async def test_no_dnspython_returns_true(self):
        """When dnspython not installed, should fail open (return True)."""
        with patch.dict(sys.modules, {"dns": None, "dns.resolver": None}):
            result = await has_mx_record("example.com")
            assert result is True


class TestValidateEmail:
    """Test the full validate_email pipeline."""

    async def test_empty_email_invalid(self):
        result = await validate_email("")
        assert result["valid"] is False
        assert result["reason"] == "empty"

    async def test_none_email_invalid(self):
        result = await validate_email(None)
        assert result["valid"] is False
        assert result["reason"] == "empty"

    async def test_invalid_format(self):
        result = await validate_email("not-an-email")
        assert result["valid"] is False
        assert result["reason"] == "invalid_format"

    @patch("src.utils.email_validation.has_mx_record", new_callable=AsyncMock)
    async def test_valid_email_with_mx(self, mock_mx):
        mock_mx.return_value = True
        result = await validate_email("john@example.com")
        assert result["valid"] is True
        assert result["reason"] is None

    @patch("src.utils.email_validation.has_mx_record", new_callable=AsyncMock)
    async def test_no_mx_record(self, mock_mx):
        mock_mx.return_value = False
        result = await validate_email("john@no-mx-domain.com")
        assert result["valid"] is False
        assert result["reason"] == "no_mx_record"

    @patch("src.utils.email_validation.has_mx_record", new_callable=AsyncMock)
    async def test_email_lowercased(self, mock_mx):
        """Email should be lowercased before validation."""
        mock_mx.return_value = True
        result = await validate_email("John@Example.COM")
        assert result["valid"] is True
        # MX check should be called with lowercase domain
        mock_mx.assert_called_once_with("example.com")

    @patch("src.utils.email_validation.has_mx_record", new_callable=AsyncMock)
    async def test_email_stripped(self, mock_mx):
        """Whitespace should be stripped."""
        mock_mx.return_value = True
        result = await validate_email("  john@example.com  ")
        assert result["valid"] is True
