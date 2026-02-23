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
# enrich_prospect_email — delegates to discover_email
# ---------------------------------------------------------------------------

class TestEnrichProspectEmail:
    @pytest.mark.asyncio
    async def test_deep_scrape_returns_verified(self):
        """Deep scrape with high confidence → verified=True."""
        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": "contact@hvacpro.com",
                "source": "website_deep_scrape",
                "confidence": "high",
                "cost_usd": 0.0,
            },
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "contact@hvacpro.com"
        assert result["source"] == "website_deep_scrape"
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_brave_search_returns_unverified(self):
        """Brave search with medium confidence → verified=False."""
        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": "info@hvacpro.com",
                "source": "brave_search",
                "confidence": "medium",
                "cost_usd": 0.005,
            },
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "info@hvacpro.com"
        assert result["source"] == "brave_search"
        assert result["verified"] is False
        assert result["cost_usd"] == 0.005

    @pytest.mark.asyncio
    async def test_pattern_guess_returns_unverified(self):
        """Pattern guess with low confidence → verified=False."""
        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": "info@hvacpro.com",
                "source": "pattern_guess",
                "confidence": "low",
                "cost_usd": 0.0,
            },
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "info@hvacpro.com"
        assert result["source"] == "pattern_guess"
        assert result["verified"] is False

    @pytest.mark.asyncio
    async def test_no_email_found_returns_none(self):
        """When discover_email finds nothing → email=None."""
        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": None,
                "source": None,
                "confidence": None,
                "cost_usd": 0.0,
            },
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] is None
        assert result["source"] is None
        assert result["verified"] is False

    @pytest.mark.asyncio
    async def test_enrichment_candidate_returns_medium_confidence(self):
        """Enrichment candidate email → verified=False (medium, not high)."""
        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": "john@hvacpro.com",
                "source": "enrichment_candidate",
                "confidence": "medium",
                "cost_usd": 0.0,
            },
        ):
            result = await enrich_prospect_email(
                "https://hvacpro.com", "HVAC Pro",
                enrichment_data={"email_candidates": ["john@hvacpro.com"]},
            )

        assert result["email"] == "john@hvacpro.com"
        assert result["verified"] is False

    @pytest.mark.asyncio
    async def test_passes_enrichment_data_to_discover(self):
        """enrichment_data parameter is forwarded to discover_email."""
        enrichment_data = {"email_candidates": ["owner@biz.com"]}
        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": "owner@biz.com",
                "source": "enrichment_candidate",
                "confidence": "medium",
                "cost_usd": 0.0,
            },
        ) as mock_discover:
            await enrich_prospect_email(
                "https://biz.com", "Biz Co",
                enrichment_data=enrichment_data,
            )

        mock_discover.assert_called_once_with(
            website="https://biz.com",
            company_name="Biz Co",
            enrichment_data=enrichment_data,
        )

    @pytest.mark.asyncio
    async def test_no_website_no_domain_returns_none(self):
        """No website and no domain returns email=None."""
        result = await enrich_prospect_email("", "Some Company")

        assert result["email"] is None
        assert result["source"] is None
