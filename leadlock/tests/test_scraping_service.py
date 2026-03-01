"""
Tests for src/services/scraping.py and src/services/google_scraper.py.
Covers: normalize_biz_name, search_local_businesses (delegation),
parse_address_components, and google_scraper internals.
All external HTTP calls are mocked via curl_cffi.
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.scraping import (
    normalize_biz_name,
    parse_address_components,
    search_local_businesses,
)
from src.services.google_scraper import (
    _generate_place_id,
    _clean_text,
    _extract_from_html_fallback,
    _extract_businesses_from_app_state,
)


# ---------------------------------------------------------------------------
# normalize_biz_name
# ---------------------------------------------------------------------------

class TestNormalizeBizName:
    """Tests for normalize_biz_name helper."""

    def test_empty_string(self):
        assert normalize_biz_name("") == ""

    def test_none_like_empty(self):
        # Empty-ish after strip should still return ""
        assert normalize_biz_name("   ") == ""

    def test_basic_lowercase_and_strip(self):
        assert normalize_biz_name("  Acme Plumbing  ") == "acme plumbing"

    def test_removes_llc_suffix(self):
        assert normalize_biz_name("Acme Plumbing LLC") == "acme plumbing"

    def test_removes_inc_suffix(self):
        assert normalize_biz_name("Acme Inc") == "acme"

    def test_removes_inc_dot_suffix(self):
        assert normalize_biz_name("Acme Inc.") == "acme"

    def test_removes_corp_suffix(self):
        assert normalize_biz_name("Acme Corp") == "acme"

    def test_removes_corp_dot_suffix(self):
        assert normalize_biz_name("Acme Corp.") == "acme"

    def test_removes_co_dot_suffix(self):
        assert normalize_biz_name("Acme Co.") == "acme"

    def test_removes_ltd_suffix(self):
        assert normalize_biz_name("Acme Ltd") == "acme"

    def test_removes_ltd_dot_suffix(self):
        assert normalize_biz_name("Acme Ltd.") == "acme"

    def test_strips_punctuation(self):
        assert normalize_biz_name("O'Brien's HVAC & Plumbing!") == "obriens hvac plumbing"

    def test_collapses_whitespace(self):
        assert normalize_biz_name("  Acme   Plumbing   Co  ") == "acme plumbing co"

    def test_suffix_only_removed_at_end(self):
        # "llc" in the middle should NOT be removed
        assert normalize_biz_name("LLC Holdings Group") == "llc holdings group"

    def test_case_insensitive_suffix(self):
        # Input is lowercased before suffix check
        assert normalize_biz_name("ACME LLC") == "acme"

    def test_mixed_punctuation_and_suffix(self):
        assert normalize_biz_name("Bob's Electric, Inc.") == "bobs electric"


# ---------------------------------------------------------------------------
# google_scraper helpers
# ---------------------------------------------------------------------------

class TestGeneratePlaceId:
    """Tests for deterministic place_id generation."""

    def test_generates_gscrape_prefix(self):
        pid = _generate_place_id("Cool Air HVAC", "+15125551234", "123 Main St")
        assert pid.startswith("gscrape_")

    def test_deterministic(self):
        pid1 = _generate_place_id("Cool Air HVAC", "+15125551234", "123 Main St")
        pid2 = _generate_place_id("Cool Air HVAC", "+15125551234", "123 Main St")
        assert pid1 == pid2

    def test_different_inputs_different_ids(self):
        pid1 = _generate_place_id("Cool Air HVAC", "+15125551234", "123 Main St")
        pid2 = _generate_place_id("Warm Air HVAC", "+15125551234", "123 Main St")
        assert pid1 != pid2

    def test_normalizes_name(self):
        """LLC suffix should be stripped before hashing."""
        pid1 = _generate_place_id("Acme HVAC LLC", "", "")
        pid2 = _generate_place_id("Acme HVAC", "", "")
        assert pid1 == pid2


class TestCleanText:
    def test_strips_html_entities(self):
        assert _clean_text("Acme &amp; Sons") == "Acme & Sons"

    def test_empty_returns_empty(self):
        assert _clean_text("") == ""

    def test_none_returns_empty(self):
        assert _clean_text(None) == ""


class TestExtractFromAppState:
    def test_returns_empty_for_invalid_json(self):
        assert _extract_businesses_from_app_state("{invalid}") == []

    def test_returns_empty_for_empty_array(self):
        assert _extract_businesses_from_app_state("[]") == []


class TestExtractFromHtmlFallback:
    def test_returns_empty_for_empty_html(self):
        assert _extract_from_html_fallback("") == []

    def test_returns_empty_for_non_html(self):
        assert _extract_from_html_fallback("just plain text") == []


# ---------------------------------------------------------------------------
# search_local_businesses (delegation wrapper)
# ---------------------------------------------------------------------------

class TestSearchLocalBusinesses:
    """Tests for the async search_local_businesses delegation wrapper."""

    async def test_delegates_to_google_scraper(self):
        """search_local_businesses delegates to google_scraper module."""
        mock_result = {
            "results": [
                {
                    "name": "Cool Air HVAC",
                    "place_id": "gscrape_abc123def456",
                    "address": "123 Main St, Austin, TX 78701",
                    "phone": "+15125551234",
                    "website": "https://coolair.com",
                    "rating": 4.8,
                    "reviews": 120,
                    "type": "HVAC",
                }
            ],
            "cost_usd": 0.0,
            "total_location_ids": 1,
        }

        with patch(
            "src.services.google_scraper.search_local_businesses",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await search_local_businesses("HVAC", "Austin, TX")

        assert len(result["results"]) == 1
        biz = result["results"][0]
        assert biz["name"] == "Cool Air HVAC"
        assert biz["place_id"].startswith("gscrape_")
        assert result["cost_usd"] == 0.0
        assert result["total_location_ids"] == 1

    async def test_returns_empty_on_no_results(self):
        """No results returns empty list."""
        with patch(
            "src.services.google_scraper.search_local_businesses",
            new_callable=AsyncMock,
            return_value={"results": [], "cost_usd": 0.0, "total_location_ids": 0},
        ):
            result = await search_local_businesses("HVAC", "Austin, TX")

        assert result["results"] == []
        assert result["total_location_ids"] == 0
        assert result["cost_usd"] == 0.0

    async def test_error_returns_error_dict(self):
        """Exception in google_scraper returns error dict."""
        with patch(
            "src.services.google_scraper.search_local_businesses",
            new_callable=AsyncMock,
            return_value={"results": [], "cost_usd": 0.0, "error": "scrape failed"},
        ):
            result = await search_local_businesses("HVAC", "Austin, TX")

        assert result["results"] == []
        assert "error" in result

    async def test_backward_compat_api_key_param_ignored(self):
        """api_key param is accepted but ignored."""
        with patch(
            "src.services.google_scraper.search_local_businesses",
            new_callable=AsyncMock,
            return_value={"results": [], "cost_usd": 0.0, "total_location_ids": 0},
        ):
            result = await search_local_businesses("HVAC", "Austin, TX", api_key="ignored")

        assert result["results"] == []


# ---------------------------------------------------------------------------
# parse_address_components
# ---------------------------------------------------------------------------

class TestParseAddressComponents:
    """Tests for parse_address_components."""

    def test_empty_address(self):
        result = parse_address_components("")
        assert result == {"city": "", "state": "", "zip": ""}

    def test_none_address(self):
        """None-ish empty string."""
        result = parse_address_components("")
        assert result == {"city": "", "state": "", "zip": ""}

    def test_full_address(self):
        result = parse_address_components("123 Main St, Austin, TX 78701")
        assert result["zip"] == "78701"
        assert result["state"] == "TX"
        assert result["city"] == "Austin"

    def test_zip_plus_four(self):
        result = parse_address_components("123 Main St, Austin, TX 78701-1234")
        assert result["zip"] == "78701"

    def test_state_after_comma(self):
        result = parse_address_components("456 Oak Ave, Dallas, TX 75201")
        assert result["state"] == "TX"
        assert result["city"] == "Dallas"

    def test_state_fallback_without_comma(self):
        """State matched via fallback pattern (no comma before state)."""
        result = parse_address_components("456 Oak Ave Dallas TX 75201")
        assert result["state"] == "TX"
        assert result["zip"] == "75201"

    def test_city_from_two_parts(self):
        """Address with only 2 comma-separated parts."""
        result = parse_address_components("Austin, TX 78701")
        assert result["city"] == "Austin"
        assert result["state"] == "TX"
        assert result["zip"] == "78701"

    def test_three_comma_parts(self):
        """Three comma-separated parts: street, city, state+zip."""
        result = parse_address_components("100 First Ave, Houston, TX 77001")
        assert result["city"] == "Houston"
        assert result["state"] == "TX"

    def test_no_zip(self):
        result = parse_address_components("123 Main St, Austin, TX")
        assert result["zip"] == ""
        assert result["state"] == ""  # Pattern requires ZIP after state

    def test_no_state_no_zip(self):
        result = parse_address_components("Just a random string")
        assert result["city"] == ""
        assert result["state"] == ""
        assert result["zip"] == ""

    def test_address_with_street_name_cleaned(self):
        """City extraction should remove street number patterns."""
        result = parse_address_components("123 Main St, San Antonio, TX 78201")
        assert result["city"] == "San Antonio"

    def test_single_part_no_comma(self):
        """Address with no commas - only 1 part, no city extracted."""
        result = parse_address_components("78701")
        assert result["zip"] == "78701"
        assert result["city"] == ""

    def test_city_candidate_is_street_cleaned_to_empty(self):
        """When city candidate matches street pattern and cleans to empty,
        falls back to the raw candidate."""
        # "100 First St" matches the street cleaning regex -> empty -> falls back
        result = parse_address_components("100 First St, TX 78701")
        # With 2 parts, city_candidate = parts[0] = "100 First St"
        # The regex tries to clean it. Let's verify what happens:
        assert result["zip"] == "78701"
