"""
Email validation tests - format checking, MX record, and SMTP mailbox verification.
Prevents sending to invalid emails, protects sender reputation.
"""
import sys
import types
import smtplib
import socket
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from src.utils.email_validation import (
    is_valid_email_format,
    has_mx_record,
    validate_email,
    validate_email_full,
    verify_smtp_mailbox,
    _smtp_verify_sync,
    _get_mx_hosts,
)


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


# ---------------------------------------------------------------------------
# SMTP mailbox verification
# ---------------------------------------------------------------------------

class TestSmtpVerifySync:
    """Test synchronous SMTP RCPT TO verification."""

    def test_mailbox_exists_returns_true(self):
        """SMTP 250 response means mailbox exists."""
        mock_smtp = MagicMock()
        mock_smtp.connect.return_value = (220, b"ready")
        mock_smtp.ehlo.return_value = (250, b"ok")
        mock_smtp.mail.return_value = (250, b"ok")
        mock_smtp.rcpt.return_value = (250, b"ok")

        with patch("src.utils.email_validation.smtplib.SMTP", return_value=mock_smtp):
            result = _smtp_verify_sync("info@example.com", ["mx.example.com"])

        assert result["exists"] is True
        assert result["reason"] == "smtp_accepted"

    def test_mailbox_rejected_550(self):
        """SMTP 550 means mailbox doesn't exist."""
        mock_smtp = MagicMock()
        mock_smtp.connect.return_value = (220, b"ready")
        mock_smtp.ehlo.return_value = (250, b"ok")
        mock_smtp.mail.return_value = (250, b"ok")
        mock_smtp.rcpt.return_value = (550, b"User unknown")

        with patch("src.utils.email_validation.smtplib.SMTP", return_value=mock_smtp):
            result = _smtp_verify_sync("info@example.com", ["mx.example.com"])

        assert result["exists"] is False
        assert "smtp_rejected_550" in result["reason"]

    def test_mailbox_rejected_553(self):
        """SMTP 553 also means rejection."""
        mock_smtp = MagicMock()
        mock_smtp.connect.return_value = (220, b"ready")
        mock_smtp.ehlo.return_value = (250, b"ok")
        mock_smtp.mail.return_value = (250, b"ok")
        mock_smtp.rcpt.return_value = (553, b"Relay not permitted")

        with patch("src.utils.email_validation.smtplib.SMTP", return_value=mock_smtp):
            result = _smtp_verify_sync("info@example.com", ["mx.example.com"])

        assert result["exists"] is False

    def test_greylisting_returns_inconclusive(self):
        """SMTP 450 (greylisting) returns inconclusive."""
        mock_smtp = MagicMock()
        mock_smtp.connect.return_value = (220, b"ready")
        mock_smtp.ehlo.return_value = (250, b"ok")
        mock_smtp.mail.return_value = (250, b"ok")
        mock_smtp.rcpt.return_value = (450, b"Try again later")

        with patch("src.utils.email_validation.smtplib.SMTP", return_value=mock_smtp):
            result = _smtp_verify_sync("info@example.com", ["mx.example.com"])

        assert result["exists"] is None
        assert "smtp_temp_450" in result["reason"]

    def test_timeout_tries_next_mx(self):
        """Timeout on first MX should try next MX host."""
        mock_smtp_fail = MagicMock()
        mock_smtp_fail.connect.side_effect = socket.timeout("timed out")

        mock_smtp_ok = MagicMock()
        mock_smtp_ok.connect.return_value = (220, b"ready")
        mock_smtp_ok.ehlo.return_value = (250, b"ok")
        mock_smtp_ok.mail.return_value = (250, b"ok")
        mock_smtp_ok.rcpt.return_value = (250, b"ok")

        call_count = 0

        def smtp_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_smtp_fail
            return mock_smtp_ok

        with patch("src.utils.email_validation.smtplib.SMTP", side_effect=smtp_factory):
            result = _smtp_verify_sync("info@example.com", ["mx1.example.com", "mx2.example.com"])

        assert result["exists"] is True

    def test_all_mx_unreachable(self):
        """If all MX hosts time out, return inconclusive."""
        mock_smtp = MagicMock()
        mock_smtp.connect.side_effect = ConnectionRefusedError()

        with patch("src.utils.email_validation.smtplib.SMTP", return_value=mock_smtp):
            result = _smtp_verify_sync("info@example.com", ["mx.example.com"])

        assert result["exists"] is None
        assert result["reason"] == "all_mx_unreachable"

    def test_mail_from_rejected_skips_to_next_mx(self):
        """If MAIL FROM is rejected, try next MX."""
        mock_smtp = MagicMock()
        mock_smtp.connect.return_value = (220, b"ready")
        mock_smtp.ehlo.return_value = (250, b"ok")
        mock_smtp.mail.return_value = (550, b"Sender rejected")
        mock_smtp.quit.return_value = None

        with patch("src.utils.email_validation.smtplib.SMTP", return_value=mock_smtp):
            result = _smtp_verify_sync("info@example.com", ["mx.example.com"])

        assert result["exists"] is None
        assert result["reason"] == "all_mx_unreachable"


class TestVerifySmtpMailbox:
    """Test async SMTP mailbox verification wrapper."""

    @patch("src.utils.email_validation._smtp_verify_sync")
    @patch("src.utils.email_validation._get_mx_hosts")
    async def test_verified_mailbox(self, mock_mx, mock_smtp):
        mock_mx.return_value = ["mx.example.com"]
        mock_smtp.return_value = {"exists": True, "reason": "smtp_accepted"}

        result = await verify_smtp_mailbox("info@example.com")
        assert result["exists"] is True

    @patch("src.utils.email_validation._smtp_verify_sync")
    @patch("src.utils.email_validation._get_mx_hosts")
    async def test_rejected_mailbox(self, mock_mx, mock_smtp):
        mock_mx.return_value = ["mx.example.com"]
        mock_smtp.return_value = {"exists": False, "reason": "smtp_rejected_550: User unknown"}

        result = await verify_smtp_mailbox("info@example.com")
        assert result["exists"] is False

    @patch("src.utils.email_validation._get_mx_hosts")
    async def test_no_mx_hosts(self, mock_mx):
        mock_mx.return_value = []

        result = await verify_smtp_mailbox("info@example.com")
        assert result["exists"] is None
        assert result["reason"] == "no_mx_hosts"


class TestValidateEmailFull:
    """Test full validation pipeline: format + MX + SMTP."""

    @patch("src.utils.email_validation.verify_smtp_mailbox", new_callable=AsyncMock)
    @patch("src.utils.email_validation.has_mx_record", new_callable=AsyncMock)
    async def test_fully_verified_email(self, mock_mx, mock_smtp):
        mock_mx.return_value = True
        mock_smtp.return_value = {"exists": True, "reason": "smtp_accepted"}

        result = await validate_email_full("john@example.com")
        assert result["valid"] is True
        assert result["smtp_verified"] is True

    @patch("src.utils.email_validation.verify_smtp_mailbox", new_callable=AsyncMock)
    @patch("src.utils.email_validation.has_mx_record", new_callable=AsyncMock)
    async def test_smtp_rejected_email(self, mock_mx, mock_smtp):
        mock_mx.return_value = True
        mock_smtp.return_value = {"exists": False, "reason": "smtp_rejected_550: User unknown"}

        result = await validate_email_full("info@example.com")
        assert result["valid"] is False
        assert "mailbox_not_found" in result["reason"]
        assert result["smtp_verified"] is False

    @patch("src.utils.email_validation.verify_smtp_mailbox", new_callable=AsyncMock)
    @patch("src.utils.email_validation.has_mx_record", new_callable=AsyncMock)
    async def test_smtp_inconclusive(self, mock_mx, mock_smtp):
        mock_mx.return_value = True
        mock_smtp.return_value = {"exists": None, "reason": "all_mx_unreachable"}

        result = await validate_email_full("info@example.com")
        assert result["valid"] is True
        assert result["smtp_verified"] is False

    async def test_invalid_format_skips_smtp(self):
        result = await validate_email_full("not-an-email")
        assert result["valid"] is False
        assert result["smtp_verified"] is False

    @patch("src.utils.email_validation.has_mx_record", new_callable=AsyncMock)
    async def test_no_mx_skips_smtp(self, mock_mx):
        mock_mx.return_value = False
        result = await validate_email_full("john@no-mx-domain.com")
        assert result["valid"] is False
        assert result["smtp_verified"] is False
