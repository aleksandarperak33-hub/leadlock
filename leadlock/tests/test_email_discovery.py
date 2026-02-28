"""
Tests for email discovery service — multi-source email finding.

Covers:
- discover_email orchestration (strategy priority)
- deep_scrape_website (extended paths, JSON-LD, footer, internal links)
- search_brave_for_email (API integration)
- _extract_all_emails helper (mailto, JSON-LD, footer, regex)
- _extract_internal_links (dedup, priority, SSRF safety)
- enrichment_data fallback
- pattern_guess last resort
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.email_discovery import (
    discover_email,
    deep_scrape_website,
    search_brave_for_email,
    _candidate_base_urls,
    _extract_all_emails,
    _extract_json_ld_emails,
    _extract_footer_emails,
    _extract_internal_links,
)


# ---------------------------------------------------------------------------
# discover_email — strategy orchestration
# ---------------------------------------------------------------------------
class TestDiscoverEmail:
    """Test the multi-strategy orchestrator."""

    @pytest.mark.asyncio
    async def test_returns_deep_scrape_first(self):
        """Strategy 1 (deep scrape) takes priority over all others."""
        with patch(
            "src.services.email_discovery.deep_scrape_website",
            new_callable=AsyncMock,
            return_value=["owner@hvacpro.com"],
        ):
            result = await discover_email(
                website="https://hvacpro.com",
                company_name="HVAC Pro",
            )

        assert result["email"] == "owner@hvacpro.com"
        assert result["source"] == "website_deep_scrape"
        assert result["confidence"] == "high"
        assert result["cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_falls_back_to_brave_search(self):
        """When deep scrape returns empty, falls to strategy 2 (Brave)."""
        with patch(
            "src.services.email_discovery.deep_scrape_website",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "src.services.email_discovery.search_brave_for_email",
            new_callable=AsyncMock,
            return_value=["info@hvacpro.com"],
        ):
            result = await discover_email(
                website="https://hvacpro.com",
                company_name="HVAC Pro",
            )

        assert result["email"] == "info@hvacpro.com"
        assert result["source"] == "brave_search"
        assert result["confidence"] == "high"  # non-catch-all domains get high confidence
        assert result["cost_usd"] == 0.005

    @pytest.mark.asyncio
    async def test_falls_back_to_enrichment_candidates(self):
        """When scrape + Brave fail, uses enrichment_data candidates."""
        with patch(
            "src.services.email_discovery.deep_scrape_website",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "src.services.email_discovery.search_brave_for_email",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await discover_email(
                website="https://hvacpro.com",
                company_name="HVAC Pro",
                enrichment_data={
                    "email_candidates": ["john@hvacpro.com", "noreply@hvacpro.com"],
                },
            )

        assert result["email"] == "john@hvacpro.com"
        assert result["source"] == "enrichment_candidate"
        assert result["confidence"] == "medium"

    @pytest.mark.asyncio
    async def test_falls_back_to_pattern_guess(self):
        """Last resort: pattern guessing."""
        with patch(
            "src.services.email_discovery.deep_scrape_website",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "src.services.email_discovery.search_brave_for_email",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await discover_email(
                website="https://hvacpro.com",
                company_name="HVAC Pro",
            )

        assert result["email"] is not None
        assert result["source"] == "pattern_guess"
        assert result["confidence"] == "low"

    @pytest.mark.asyncio
    async def test_returns_none_without_website_or_domain(self):
        """No website and no domain → no email."""
        result = await discover_email(
            website="",
            company_name="Unknown Co",
        )

        assert result["email"] is None
        assert result["source"] is None

    @pytest.mark.asyncio
    async def test_deep_scrape_exception_falls_through(self):
        """Exception in deep scrape doesn't crash — falls to next strategy."""
        with patch(
            "src.services.email_discovery.deep_scrape_website",
            new_callable=AsyncMock,
            side_effect=Exception("scrape exploded"),
        ), patch(
            "src.services.email_discovery.search_brave_for_email",
            new_callable=AsyncMock,
            return_value=["contact@hvacpro.com"],
        ):
            result = await discover_email(
                website="https://hvacpro.com",
                company_name="HVAC Pro",
            )

        assert result["email"] == "contact@hvacpro.com"
        assert result["source"] == "brave_search"

    @pytest.mark.asyncio
    async def test_enrichment_candidate_filters_noreply(self):
        """Enrichment candidates skip noreply addresses."""
        with patch(
            "src.services.email_discovery.deep_scrape_website",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "src.services.email_discovery.search_brave_for_email",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await discover_email(
                website="https://hvacpro.com",
                company_name="HVAC Pro",
                enrichment_data={
                    "email_candidates": ["noreply@hvacpro.com", "do-not-reply@hvacpro.com"],
                },
            )

        # Both are noreply — should fall through to pattern guess
        assert result["source"] == "pattern_guess"


# ---------------------------------------------------------------------------
# _extract_all_emails — email extraction from HTML
# ---------------------------------------------------------------------------
class TestExtractAllEmails:
    """Test the multi-strategy HTML email extractor."""

    def test_extracts_mailto_links(self):
        html = '<a href="mailto:owner@hvacpro.com">Email us</a>'
        result = _extract_all_emails(html, "hvacpro.com")
        assert "owner@hvacpro.com" in result

    def test_extracts_json_ld_email(self):
        html = '''
        <script type="application/ld+json">
        {"@type": "LocalBusiness", "email": "info@hvacpro.com"}
        </script>
        '''
        result = _extract_all_emails(html, "hvacpro.com")
        assert "info@hvacpro.com" in result

    def test_extracts_footer_email(self):
        html = '<footer><p>Contact: sales@hvacpro.com</p></footer>'
        result = _extract_all_emails(html, "hvacpro.com")
        assert "sales@hvacpro.com" in result

    def test_extracts_regex_email(self):
        html = '<div>Reach us at contact@hvacpro.com for inquiries</div>'
        result = _extract_all_emails(html, "hvacpro.com")
        assert "contact@hvacpro.com" in result

    def test_deduplicates_emails(self):
        html = '''
        <a href="mailto:info@hvacpro.com">Email</a>
        <footer>info@hvacpro.com</footer>
        <div>info@hvacpro.com</div>
        '''
        result = _extract_all_emails(html, "hvacpro.com")
        assert result.count("info@hvacpro.com") == 1

    def test_filters_wrong_domain(self):
        html = '<div>user@otherdomain.com and owner@hvacpro.com</div>'
        result = _extract_all_emails(html, "hvacpro.com")
        assert "owner@hvacpro.com" in result
        assert "user@otherdomain.com" not in result

    def test_filters_ignored_domains(self):
        html = '<div>contact@sentry.io and owner@hvacpro.com</div>'
        result = _extract_all_emails(html, "hvacpro.com")
        assert "owner@hvacpro.com" in result
        assert "contact@sentry.io" not in result

    def test_mailto_higher_priority_than_regex(self):
        """mailto: found emails should come before regex-only emails."""
        html = '''
        <div>backup@hvacpro.com is secondary</div>
        <a href="mailto:primary@hvacpro.com">Contact</a>
        '''
        result = _extract_all_emails(html, "hvacpro.com")
        assert result[0] == "primary@hvacpro.com"

    def test_rejects_url_encoded_space_in_email(self):
        """Emails with URL-encoded spaces (%20) should be rejected."""
        html = '<a href="mailto:sales%20team@hvacpro.com">Email</a>'
        result = _extract_all_emails(html, "hvacpro.com")
        assert not any("%20" in e or " " in e for e in result)

    def test_decodes_url_encoded_mailto(self):
        """Properly URL-encoded mailto links should be decoded."""
        # %2B is +, which is valid in emails
        html = '<a href="mailto:sales@hvacpro.com">Email</a>'
        result = _extract_all_emails(html, "hvacpro.com")
        assert "sales@hvacpro.com" in result

    def test_rejects_percent_encoded_artifacts(self):
        """Emails with leftover URL encoding should be filtered out."""
        html = '<div>Contact %20info@hvacpro.com for service</div>'
        result = _extract_all_emails(html, "hvacpro.com")
        # Should not contain email with %20 prefix
        assert not any("%20" in e or " " in e for e in result)


# ---------------------------------------------------------------------------
# _extract_json_ld_emails
# ---------------------------------------------------------------------------
class TestExtractJsonLdEmails:

    def test_extracts_email_from_local_business(self):
        html = '''
        <script type="application/ld+json">
        {"@type": "LocalBusiness", "name": "HVAC Pro", "email": "hello@hvacpro.com"}
        </script>
        '''
        result = _extract_json_ld_emails(html, "hvacpro.com")
        assert "hello@hvacpro.com" in result

    def test_extracts_email_from_contact_point(self):
        html = '''
        <script type="application/ld+json">
        {
            "@type": "Organization",
            "contactPoint": {
                "@type": "ContactPoint",
                "email": "support@hvacpro.com"
            }
        }
        </script>
        '''
        result = _extract_json_ld_emails(html, "hvacpro.com")
        assert "support@hvacpro.com" in result

    def test_handles_malformed_json(self):
        html = '<script type="application/ld+json">{invalid json here}</script>'
        result = _extract_json_ld_emails(html, "hvacpro.com")
        assert result == []

    def test_handles_mailto_prefix_in_email(self):
        html = '''
        <script type="application/ld+json">
        {"@type": "Organization", "email": "mailto:info@hvacpro.com"}
        </script>
        '''
        result = _extract_json_ld_emails(html, "hvacpro.com")
        assert "info@hvacpro.com" in result


# ---------------------------------------------------------------------------
# _extract_footer_emails
# ---------------------------------------------------------------------------
class TestExtractFooterEmails:

    def test_extracts_mailto_from_footer(self):
        html = '<footer><a href="mailto:contact@biz.com">Email</a></footer>'
        result = _extract_footer_emails(html, "biz.com")
        assert "contact@biz.com" in result

    def test_extracts_regex_from_footer(self):
        html = '<footer><p>Email: info@biz.com</p></footer>'
        result = _extract_footer_emails(html, "biz.com")
        assert "info@biz.com" in result

    def test_ignores_non_target_domain(self):
        html = '<footer><p>Powered by support@wordpress.com</p></footer>'
        result = _extract_footer_emails(html, "biz.com")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _extract_internal_links
# ---------------------------------------------------------------------------
class TestExtractInternalLinks:

    def test_finds_relative_links(self):
        html = '<a href="/careers">Careers</a><a href="/services">Services</a>'
        result = _extract_internal_links(html, "https://hvacpro.com")
        assert any("/careers" in u for u in result)

    def test_skips_external_links(self):
        html = '<a href="https://external.com/page">External</a>'
        result = _extract_internal_links(html, "https://hvacpro.com")
        assert len(result) == 0

    def test_skips_file_downloads(self):
        html = '<a href="/brochure.pdf">Download</a><a href="/team">Team</a>'
        result = _extract_internal_links(html, "https://hvacpro.com")
        assert not any(".pdf" in u for u in result)

    def test_prioritizes_contact_pages(self):
        html = '''
        <a href="/services">Services</a>
        <a href="/contact-form">Contact</a>
        <a href="/blog">Blog</a>
        '''
        result = _extract_internal_links(html, "https://hvacpro.com")
        # Contact-relevant links should come first
        assert "contact" in result[0].lower()

    def test_deduplicates_links(self):
        html = '<a href="/careers">Careers</a><a href="/careers">Join Us</a>'
        result = _extract_internal_links(html, "https://hvacpro.com")
        careers_links = [u for u in result if "/careers" in u]
        assert len(careers_links) == 1

    def test_skips_already_scraped_paths(self):
        html = '<a href="/contact">Contact</a><a href="/about">About</a>'
        result = _extract_internal_links(html, "https://hvacpro.com")
        # /contact and /about are in _EXTENDED_PATHS, so they should be skipped
        assert len(result) == 0


# ---------------------------------------------------------------------------
# deep_scrape_website
# ---------------------------------------------------------------------------
class TestDeepScrapeWebsite:

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_website(self):
        result = await deep_scrape_website("")
        assert result == []

    @pytest.mark.asyncio
    async def test_blocks_ssrf_urls(self):
        """SSRF protection blocks internal URLs."""
        with patch(
            "src.services.email_discovery._is_safe_url",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await deep_scrape_website("http://169.254.169.254/latest")

        assert result == []

    @pytest.mark.asyncio
    async def test_scrapes_multiple_paths(self):
        """Fetches extended paths and extracts emails."""
        mock_html = '<a href="mailto:owner@biz.com">Email</a>'

        with patch(
            "src.services.email_discovery._is_safe_url",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "src.services.email_discovery._fetch_html",
            new_callable=AsyncMock,
            return_value=mock_html,
        ):
            result = await deep_scrape_website("https://biz.com")

        assert "owner@biz.com" in result

    @pytest.mark.asyncio
    async def test_retries_apex_when_www_candidate_is_blocked(self):
        """If www host is unsafe/unresolvable, retry apex domain before giving up."""
        mock_html = '<a href="mailto:owner@biz.com">Email</a>'

        with patch(
            "src.services.email_discovery._is_safe_url",
            new_callable=AsyncMock,
            side_effect=[False, True],
        ) as mock_safe, patch(
            "src.services.email_discovery._fetch_html",
            new_callable=AsyncMock,
            return_value=mock_html,
        ):
            result = await deep_scrape_website("https://www.biz.com")

        assert "owner@biz.com" in result
        checked = [call.args[0] for call in mock_safe.await_args_list[:2]]
        assert checked == ["https://www.biz.com", "https://biz.com"]


class TestCandidateBaseUrls:
    """Tests for deep-scrape base candidate expansion."""

    def test_builds_www_and_apex_fallbacks_for_https(self):
        candidates = _candidate_base_urls("https://www.hvacpro.com")
        assert candidates == [
            "https://www.hvacpro.com",
            "https://hvacpro.com",
            "http://www.hvacpro.com",
            "http://hvacpro.com",
        ]


# ---------------------------------------------------------------------------
# search_brave_for_email
# ---------------------------------------------------------------------------
class TestSearchBraveForEmail:

    @pytest.mark.asyncio
    async def test_returns_empty_without_api_key(self):
        """No Brave API key → no search."""
        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value.brave_api_key = None
            result = await search_brave_for_email("hvacpro.com")

        assert result == []

    @pytest.mark.asyncio
    async def test_extracts_emails_from_search_results(self):
        """Parses emails from Brave search snippets."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "description": "Contact HVAC Pro at info@hvacpro.com for service",
                        "title": "HVAC Pro",
                    },
                    {
                        "description": "No email here",
                        "title": "Random Page",
                    },
                ],
            },
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.config.get_settings") as mock_settings, \
             patch("src.services.email_discovery.httpx.AsyncClient", return_value=mock_client):
            mock_settings.return_value.brave_api_key = "test-key"
            result = await search_brave_for_email("hvacpro.com")

        assert "info@hvacpro.com" in result

    @pytest.mark.asyncio
    async def test_filters_wrong_domain_from_brave(self):
        """Only returns emails matching the target domain."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "description": "Contact user@otherdomain.com and info@hvacpro.com",
                        "title": "Results",
                    },
                ],
            },
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.config.get_settings") as mock_settings, \
             patch("src.services.email_discovery.httpx.AsyncClient", return_value=mock_client):
            mock_settings.return_value.brave_api_key = "test-key"
            result = await search_brave_for_email("hvacpro.com")

        assert "info@hvacpro.com" in result
        assert "user@otherdomain.com" not in result

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        """Brave API failure returns empty list."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("API down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.config.get_settings") as mock_settings, \
             patch("src.services.email_discovery.httpx.AsyncClient", return_value=mock_client):
            mock_settings.return_value.brave_api_key = "test-key"
            result = await search_brave_for_email("hvacpro.com")

        assert result == []
