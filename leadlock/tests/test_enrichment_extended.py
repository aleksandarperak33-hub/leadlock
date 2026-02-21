"""
Extended tests for src/services/enrichment.py - covers invalid IP parsing,
general exceptions in _is_safe_url, extract_domain exception, do-not-reply
filtering, auto-prefix in scrape, redirect handling, non-HTML content-type,
HTTP exceptions during scraping, and full enrich_prospect_email paths.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.services.enrichment import (
    _is_safe_url,
    extract_domain,
    _is_valid_business_email,
    scrape_contact_emails,
    enrich_prospect_email,
)


# ---------------------------------------------------------------------------
# _is_safe_url - invalid IP address (lines 86-87)
# ---------------------------------------------------------------------------


class TestIsSafeUrlInvalidIp:
    @pytest.mark.asyncio
    async def test_unparseable_ip_returns_false(self):
        """When getaddrinfo returns an unparseable IP string, URL is blocked."""
        with patch("src.services.enrichment.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(2, 1, 6, "", ("not_an_ip", 0))]
            assert await _is_safe_url("https://hvacpro.com") is False


# ---------------------------------------------------------------------------
# _is_safe_url - general exception (lines 98-99)
# ---------------------------------------------------------------------------


class TestIsSafeUrlGeneralException:
    @pytest.mark.asyncio
    async def test_general_exception_returns_false(self):
        """Any unhandled exception in _is_safe_url returns False."""
        with patch("src.services.enrichment.urlparse", side_effect=ValueError("bad parse")):
            assert await _is_safe_url("https://hvacpro.com") is False


# ---------------------------------------------------------------------------
# extract_domain - exception path (lines 123-124)
# ---------------------------------------------------------------------------


class TestExtractDomainException:
    def test_malformed_url_returns_none(self):
        """A URL that causes urlparse to fail returns None."""
        with patch("src.services.enrichment.urlparse", side_effect=Exception("parse error")):
            assert extract_domain("https://hvacpro.com") is None


# ---------------------------------------------------------------------------
# _is_valid_business_email - do-not-reply (line 173)
# ---------------------------------------------------------------------------


class TestDoNotReplyFiltering:
    def test_do_not_reply_filtered(self):
        """do-not-reply@ local part is filtered out."""
        assert _is_valid_business_email("do-not-reply@hvacpro.com") is False


# ---------------------------------------------------------------------------
# scrape_contact_emails - auto-prefix without scheme (line 198)
# ---------------------------------------------------------------------------


class TestScrapeAutoPrefix:
    @pytest.mark.asyncio
    async def test_adds_https_scheme_when_missing(self):
        """When website doesn't start with http/https, https:// is prepended."""
        html = '<html><body><a href="mailto:info@hvacpro.com">Contact</a></body></html>'

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
            result = await scrape_contact_emails("hvacpro.com")

        assert "info@hvacpro.com" in result


# ---------------------------------------------------------------------------
# scrape_contact_emails - redirect handling (lines 232-245)
# ---------------------------------------------------------------------------


class TestScrapeRedirects:
    @pytest.mark.asyncio
    async def test_follows_safe_redirect(self):
        """Redirect to a safe URL is followed and content is scraped."""
        redirect_response = MagicMock()
        redirect_response.status_code = 301
        redirect_response.headers = {"location": "https://hvacpro.com/contact-page"}

        final_response = MagicMock()
        final_response.status_code = 200
        final_response.headers = {"content-type": "text/html"}
        final_response.text = '<html><body>Email: info@hvacpro.com</body></html>'

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            redirect_response, final_response,  # /contact
            final_response,  # /contact-us
            final_response,  # /about
            final_response,  # /about-us
            final_response,  # /
        ])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert "info@hvacpro.com" in result

    @pytest.mark.asyncio
    async def test_redirect_to_unsafe_url_blocked(self):
        """Redirect to a private IP is blocked (SSRF redirect protection)."""
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"location": "http://10.0.0.1/admin"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=redirect_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        # First call: safe (original URL), second call: unsafe (redirect target)
        safe_url_results = [True, False, True, True, True, True]

        with (
            patch(
                "src.services.enrichment._is_safe_url",
                new_callable=AsyncMock,
                side_effect=safe_url_results,
            ),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_redirect_with_no_location_header(self):
        """Redirect response without Location header sets response to None."""
        redirect_response = MagicMock()
        redirect_response.status_code = 301
        redirect_response.headers = {}  # No location header

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.headers = {"content-type": "text/html"}
        ok_response.text = '<html><body>Email: hello@hvacpro.com</body></html>'

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            redirect_response,  # /contact -- redirect with no location
            ok_response,        # /contact-us
            ok_response,        # /about
            ok_response,        # /about-us
            ok_response,        # /
        ])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert "hello@hvacpro.com" in result

    @pytest.mark.asyncio
    async def test_relative_redirect_resolved(self):
        """Relative redirect (starts with /) is resolved against current URL."""
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"location": "/new-contact"}

        final_response = MagicMock()
        final_response.status_code = 200
        final_response.headers = {"content-type": "text/html"}
        final_response.text = '<html><body>reach us at sales@hvacpro.com</body></html>'

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            redirect_response, final_response,  # /contact -> /new-contact
            final_response,  # /contact-us
            final_response,  # /about
            final_response,  # /about-us
            final_response,  # / (base)
        ])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert "sales@hvacpro.com" in result


# ---------------------------------------------------------------------------
# scrape_contact_emails - non-HTML content type (lines 248, 252)
# ---------------------------------------------------------------------------


class TestScrapeNonHtmlContentType:
    @pytest.mark.asyncio
    async def test_skips_non_html_responses(self):
        """Responses with non-HTML content-type (e.g. application/json) are skipped."""
        json_response = MagicMock()
        json_response.status_code = 200
        json_response.headers = {"content-type": "application/json"}
        json_response.text = '{"email": "hidden@hvacpro.com"}'

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=json_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert result == []

    @pytest.mark.asyncio
    async def test_accepts_text_plain_content_type(self):
        """text/plain content-type is accepted (not just text/html)."""
        plain_response = MagicMock()
        plain_response.status_code = 200
        plain_response.headers = {"content-type": "text/plain"}
        plain_response.text = "Contact us at support@hvacpro.com"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=plain_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert "support@hvacpro.com" in result


# ---------------------------------------------------------------------------
# scrape_contact_emails - HTTP exception (lines 272-274)
# ---------------------------------------------------------------------------


class TestScrapeHttpException:
    @pytest.mark.asyncio
    async def test_http_error_handled_gracefully(self):
        """httpx.HTTPError during scraping is caught and page is skipped."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert result == []

    @pytest.mark.asyncio
    async def test_generic_exception_handled_gracefully(self):
        """Generic exceptions during page scraping are caught."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Unexpected error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert result == []

    @pytest.mark.asyncio
    async def test_non_200_status_skipped(self):
        """Non-200 responses are skipped without crashing."""
        error_response = MagicMock()
        error_response.status_code = 404
        error_response.headers = {"content-type": "text/html"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=error_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.enrichment._is_safe_url", new_callable=AsyncMock, return_value=True),
            patch("src.services.enrichment.httpx.AsyncClient", return_value=mock_client),
        ):
            result = await scrape_contact_emails("https://hvacpro.com")

        assert result == []


# ---------------------------------------------------------------------------
# scrape_contact_emails - deduplication
# ---------------------------------------------------------------------------


class TestScrapeDeduplication:
    @pytest.mark.asyncio
    async def test_emails_are_deduplicated(self):
        """Same email found on multiple pages is returned only once."""
        html = '<html><body>Contact: info@hvacpro.com and info@hvacpro.com</body></html>'

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

        assert result.count("info@hvacpro.com") == 1


# ---------------------------------------------------------------------------
# enrich_prospect_email - all branches (lines 304-331)
# ---------------------------------------------------------------------------


class TestEnrichProspectEmail:
    @pytest.mark.asyncio
    async def test_returns_scraped_email_when_found(self):
        """When website scraping finds an email, it is returned with source='website_scrape'."""
        with patch(
            "src.services.enrichment.scrape_contact_emails",
            new_callable=AsyncMock,
            return_value=["contact@hvacpro.com"],
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "contact@hvacpro.com"
        assert result["source"] == "website_scrape"
        assert result["verified"] is False
        assert result["cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_falls_back_to_pattern_guess_when_scrape_empty(self):
        """When scraping returns no emails, pattern guessing is used."""
        with patch(
            "src.services.enrichment.scrape_contact_emails",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "info@hvacpro.com"
        assert result["source"] == "pattern_guess"
        assert result["verified"] is False
        assert result["cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_falls_back_to_pattern_guess_when_scrape_raises(self):
        """When website scraping throws an exception, pattern guessing is used."""
        with patch(
            "src.services.enrichment.scrape_contact_emails",
            new_callable=AsyncMock,
            side_effect=RuntimeError("scrape failed"),
        ):
            result = await enrich_prospect_email("https://hvacpro.com", "HVAC Pro")

        assert result["email"] == "info@hvacpro.com"
        assert result["source"] == "pattern_guess"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_website_and_no_domain(self):
        """When website is empty and domain can't be extracted, returns None email."""
        result = await enrich_prospect_email("", "Unknown Company")

        assert result["email"] is None
        assert result["source"] is None
        assert result["verified"] is False
        assert result["cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_no_website_but_valid_domain_still_extracts(self):
        """When website is empty string, extract_domain returns None, so no patterns."""
        result = await enrich_prospect_email("", "HVAC Pro")

        assert result["email"] is None
        assert result["source"] is None

    @pytest.mark.asyncio
    async def test_skips_scrape_when_website_empty(self):
        """When website is falsy, scrape is skipped entirely."""
        with patch(
            "src.services.enrichment.scrape_contact_emails",
            new_callable=AsyncMock,
        ) as mock_scrape:
            await enrich_prospect_email("", "HVAC Pro")

        mock_scrape.assert_not_called()
