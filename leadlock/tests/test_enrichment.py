"""
Tests for src/services/enrichment.py - SSRF protection, domain extraction,
email pattern guessing, business email validation, website scraping,
and SMTP-verified enrichment.
"""
import pytest
import socket
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.enrichment import (
    _is_safe_url,
    extract_domain,
    guess_email_patterns,
    _is_valid_business_email,
    scrape_contact_emails,
    enrich_prospect_email,
)


# ---------------------------------------------------------------------------
# _is_safe_url - SSRF protection
# ---------------------------------------------------------------------------

class TestIsSafeUrl:
    """URL safety checks to prevent SSRF attacks."""

    async def test_https_public_domain_allowed(self):
        """Normal HTTPS URL to a public domain is safe."""
        with patch("src.services.enrichment.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            assert await _is_safe_url("https://example.com") is True

    async def test_http_allowed(self):
        """HTTP scheme is also allowed."""
        with patch("src.services.enrichment.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            assert await _is_safe_url("http://example.com") is True

    async def test_file_scheme_blocked(self):
        """file:// scheme is blocked."""
        assert await _is_safe_url("file:///etc/passwd") is False

    async def test_ftp_scheme_blocked(self):
        """ftp:// scheme is blocked."""
        assert await _is_safe_url("ftp://example.com") is False

    async def test_localhost_blocked(self):
        """localhost is blocked by hostname check."""
        assert await _is_safe_url("http://localhost/admin") is False

    async def test_127_0_0_1_blocked(self):
        """127.0.0.1 is blocked by hostname check."""
        assert await _is_safe_url("http://127.0.0.1/admin") is False

    async def test_private_ip_10_x_blocked(self):
        """10.x.x.x private range is blocked by IP validation."""
        with patch("src.services.enrichment.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("10.0.0.1", 0))]
            assert await _is_safe_url("http://internal.corp.com") is False

    async def test_private_ip_192_168_x_blocked(self):
        """192.168.x.x private range is blocked."""
        with patch("src.services.enrichment.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("192.168.1.1", 0))]
            assert await _is_safe_url("http://router.local") is False

    async def test_private_ip_172_16_blocked(self):
        """172.16.x.x private range is blocked."""
        with patch("src.services.enrichment.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("172.16.0.1", 0))]
            assert await _is_safe_url("http://internal-service") is False

    async def test_metadata_endpoint_blocked(self):
        """Cloud metadata endpoint is blocked."""
        assert await _is_safe_url("http://169.254.169.254/latest/meta-data") is False

    async def test_dns_failure_returns_false(self):
        """DNS resolution failure returns False (safe)."""
        with patch(
            "src.services.enrichment.socket.getaddrinfo",
            side_effect=socket.gaierror("Name resolution failed"),
        ):
            assert await _is_safe_url("http://nonexistent.example.com") is False

    async def test_non_standard_port_blocked(self):
        """Non-standard ports like 9200 (Elasticsearch) are blocked."""
        assert await _is_safe_url("http://example.com:9200") is False

    async def test_allowed_port_8080(self):
        """Port 8080 is in the allowed set."""
        with patch("src.services.enrichment.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 0))]
            assert await _is_safe_url("http://example.com:8080") is True

    async def test_no_hostname_returns_false(self):
        """URL with no hostname is not safe."""
        assert await _is_safe_url("http://") is False

    async def test_empty_string_returns_false(self):
        assert await _is_safe_url("") is False


# ---------------------------------------------------------------------------
# extract_domain
# ---------------------------------------------------------------------------

class TestExtractDomain:
    def test_full_url_with_path(self):
        assert extract_domain("https://www.hvacpro.com/contact") == "hvacpro.com"

    def test_strips_www(self):
        assert extract_domain("https://www.example.com") == "example.com"

    def test_bare_domain(self):
        assert extract_domain("hvacpro.com") == "hvacpro.com"

    def test_http_url(self):
        assert extract_domain("http://plumbing-co.com/about") == "plumbing-co.com"

    def test_none_returns_none(self):
        assert extract_domain(None) is None

    def test_empty_returns_none(self):
        assert extract_domain("") is None

    def test_preserves_subdomains(self):
        assert extract_domain("https://shop.example.com/products") == "shop.example.com"


# ---------------------------------------------------------------------------
# guess_email_patterns
# ---------------------------------------------------------------------------

class TestGuessEmailPatterns:
    def test_basic_patterns_without_name(self):
        patterns = guess_email_patterns("hvacpro.com")
        assert "info@hvacpro.com" in patterns
        assert "contact@hvacpro.com" in patterns
        assert "hello@hvacpro.com" in patterns
        assert "service@hvacpro.com" in patterns
        assert "sales@hvacpro.com" in patterns

    def test_with_name_generates_personal_patterns(self):
        patterns = guess_email_patterns("hvacpro.com", name="John Smith")
        assert "john@hvacpro.com" in patterns
        assert "john.smith@hvacpro.com" in patterns
        assert "jsmith@hvacpro.com" in patterns
        # Generic patterns should still be present
        assert "info@hvacpro.com" in patterns

    def test_name_patterns_first(self):
        """When a name is provided, personal patterns come first."""
        patterns = guess_email_patterns("example.com", name="Jane Doe")
        assert patterns[0] == "jane@example.com"
        assert patterns[1] == "jane.doe@example.com"
        assert patterns[2] == "jdoe@example.com"

    def test_single_name_no_personal_patterns(self):
        """Single word name (no last name) does not add personal patterns."""
        patterns = guess_email_patterns("example.com", name="Alice")
        assert "alice@example.com" not in patterns
        # Only generic patterns
        assert patterns[0] == "info@example.com"

    def test_name_with_special_chars_cleaned(self):
        """Names with special characters are cleaned before pattern generation."""
        patterns = guess_email_patterns("example.com", name="O'Brien Jr.")
        # Should still generate something reasonable
        assert any("obrien" in p for p in patterns)


# ---------------------------------------------------------------------------
# _is_valid_business_email
# ---------------------------------------------------------------------------

class TestIsValidBusinessEmail:
    def test_normal_business_email(self):
        assert _is_valid_business_email("info@hvacpro.com") is True

    def test_noreply_filtered(self):
        assert _is_valid_business_email("noreply@example.com") is False

    def test_no_reply_with_dash_filtered(self):
        assert _is_valid_business_email("no-reply@example.com") is False

    def test_donotreply_filtered(self):
        assert _is_valid_business_email("donotreply@example.com") is False

    def test_mailer_daemon_filtered(self):
        assert _is_valid_business_email("mailer-daemon@example.com") is False

    def test_ignored_domain_filtered(self):
        assert _is_valid_business_email("user@sentry.io") is False

    def test_ignored_domain_wixpress(self):
        assert _is_valid_business_email("user@wixpress.com") is False

    def test_target_domain_mismatch_filtered(self):
        """When target_domain is given, emails from other domains are rejected."""
        assert _is_valid_business_email("info@otherdomain.com", target_domain="hvacpro.com") is False

    def test_target_domain_match_passes(self):
        assert _is_valid_business_email("contact@hvacpro.com", target_domain="hvacpro.com") is True

    def test_info_address_allowed(self):
        """info@ is a valid generic local part (not filtered)."""
        assert _is_valid_business_email("info@acmeplumbing.com") is True

    def test_support_address_allowed(self):
        """support@ is a valid local part (only noreply variants are filtered)."""
        assert _is_valid_business_email("support@acmeplumbing.com") is True


# ---------------------------------------------------------------------------
# scrape_contact_emails (with mocked httpx)
# ---------------------------------------------------------------------------

class TestScrapeContactEmails:
    @pytest.mark.asyncio
    async def test_empty_website_returns_empty(self):
        result = await scrape_contact_emails("")
        assert result == []

    @pytest.mark.asyncio
    async def test_unsafe_url_returns_empty(self):
        """SSRF-blocked URL returns empty list."""
        with patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=False):
            result = await scrape_contact_emails("http://169.254.169.254")
        assert result == []

    @pytest.mark.asyncio
    async def test_extracts_mailto_emails(self):
        """Emails from mailto: links are extracted."""
        html = '<html><body><a href="mailto:contact@hvacpro.com">Email us</a></body></html>'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert "contact@hvacpro.com" in result

    @pytest.mark.asyncio
    async def test_filters_ignored_domains(self):
        """Emails from ignored domains (e.g., sentry.io) are excluded."""
        html = '<html><body>Email: user@sentry.io and contact@hvacpro.com</body></html>'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert "user@sentry.io" not in result
        assert "contact@hvacpro.com" in result


# ---------------------------------------------------------------------------
# enrich_prospect_email - SMTP-verified enrichment
# ---------------------------------------------------------------------------

class TestEnrichProspectEmail:
    @pytest.mark.asyncio
    async def test_scraped_email_smtp_verified(self):
        """Scraped email that passes SMTP verification returns verified=True."""
        with (
            patch(
                "src.services.enrichment.scrape_contact_emails",
                new_callable=AsyncMock,
                return_value=["contact@hvacpro.com"],
            ),
            patch(
                "src.utils.email_validation.verify_smtp_mailbox",
                new_callable=AsyncMock,
                return_value={"exists": True, "reason": "smtp_accepted"},
            ),
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "contact@hvacpro.com"
        assert result["source"] == "website_scrape"
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_scraped_email_smtp_inconclusive(self):
        """Scraped email with inconclusive SMTP returns verified=False but email is present."""
        with (
            patch(
                "src.services.enrichment.scrape_contact_emails",
                new_callable=AsyncMock,
                return_value=["contact@hvacpro.com"],
            ),
            patch(
                "src.utils.email_validation.verify_smtp_mailbox",
                new_callable=AsyncMock,
                return_value={"exists": None, "reason": "all_mx_unreachable"},
            ),
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "contact@hvacpro.com"
        assert result["verified"] is False

    @pytest.mark.asyncio
    async def test_scraped_email_rejected_falls_through(self):
        """If scraped email is SMTP-rejected, try alternatives then fall to pattern guessing."""
        with (
            patch(
                "src.services.enrichment.scrape_contact_emails",
                new_callable=AsyncMock,
                return_value=["noreply-scraped@hvacpro.com"],
            ),
            patch(
                "src.utils.email_validation.verify_smtp_mailbox",
                new_callable=AsyncMock,
                side_effect=[
                    # First scraped email rejected
                    {"exists": False, "reason": "smtp_rejected_550"},
                    # Pattern guess: info@ accepted
                    {"exists": True, "reason": "smtp_accepted"},
                ],
            ),
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "info@hvacpro.com"
        assert result["source"] == "pattern_guess"
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_pattern_guess_first_rejected_second_accepted(self):
        """Pattern guessing tries multiple patterns until one is SMTP-verified."""
        with (
            patch(
                "src.services.enrichment.scrape_contact_emails",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.utils.email_validation.verify_smtp_mailbox",
                new_callable=AsyncMock,
                side_effect=[
                    # info@ rejected
                    {"exists": False, "reason": "smtp_rejected_550"},
                    # contact@ accepted
                    {"exists": True, "reason": "smtp_accepted"},
                ],
            ),
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "contact@hvacpro.com"
        assert result["source"] == "pattern_guess"
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_all_patterns_rejected_returns_none(self):
        """If all patterns are SMTP-rejected, return email=None."""
        with (
            patch(
                "src.services.enrichment.scrape_contact_emails",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.utils.email_validation.verify_smtp_mailbox",
                new_callable=AsyncMock,
                return_value={"exists": False, "reason": "smtp_rejected_550"},
            ),
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] is None
        assert result["source"] == "pattern_guess_all_rejected"

    @pytest.mark.asyncio
    async def test_pattern_guess_inconclusive_returns_first(self):
        """If SMTP is inconclusive (timeout), return first pattern unverified."""
        with (
            patch(
                "src.services.enrichment.scrape_contact_emails",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.utils.email_validation.verify_smtp_mailbox",
                new_callable=AsyncMock,
                return_value={"exists": None, "reason": "all_mx_unreachable"},
            ),
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "info@hvacpro.com"
        assert result["verified"] is False

    @pytest.mark.asyncio
    async def test_no_website_no_domain_returns_none(self):
        """No website and no domain returns email=None."""
        result = await enrich_prospect_email("", "Some Company")

        assert result["email"] is None
        assert result["source"] is None
