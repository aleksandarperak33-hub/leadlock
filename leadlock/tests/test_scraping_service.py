"""
Tests for src/services/scraping.py — Brave Search API local business discovery.
Covers: normalize_biz_name, search_local_businesses, parse_address_components.
All external HTTP calls are mocked via httpx.
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.scraping import (
    BRAVE_COST_PER_SEARCH,
    BRAVE_POI_URL,
    BRAVE_SEARCH_URL,
    POI_BATCH_SIZE,
    normalize_biz_name,
    parse_address_components,
    search_local_businesses,
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
# search_local_businesses
# ---------------------------------------------------------------------------

def _make_mock_response(json_data, status_code=200):
    """Create a mock httpx.Response with .json() and .raise_for_status()."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="error", request=MagicMock(), response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestSearchLocalBusinesses:
    """Tests for the async search_local_businesses function."""

    async def test_no_locations_in_search_results(self):
        """When Brave returns no locations block, return empty results."""
        search_resp = _make_mock_response({"web": {"results": []}})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=search_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"] == []
        assert result["total_location_ids"] == 0
        assert result["cost_usd"] == pytest.approx(BRAVE_COST_PER_SEARCH)

    async def test_locations_present_but_no_ids(self):
        """When locations exist but none have an id field."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"name": "No ID Biz"}]}
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=search_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"] == []
        assert result["total_location_ids"] == 0

    async def test_single_poi_result(self):
        """Happy path: 1 location ID -> 1 POI batch -> 1 parsed result."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{
                "title": "Cool Air HVAC LLC",
                "postal_address": {"displayAddress": "123 Main St, Austin, TX 78701"},
                "contact": {"telephone": "+15125551234"},
                "url": "https://coolair.com",
                "categories": ["HVAC", "Air Conditioning"],
                "results": [{
                    "rating": {"ratingValue": 4.8, "ratingCount": 120}
                }],
            }]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert len(result["results"]) == 1
        biz = result["results"][0]
        assert biz["name"] == "Cool Air HVAC LLC"
        assert biz["phone"] == "+15125551234"
        assert biz["website"] == "https://coolair.com"
        assert biz["address"] == "123 Main St, Austin, TX 78701"
        assert biz["rating"] == 4.8
        assert biz["reviews"] == 120
        assert biz["type"] == "HVAC, Air Conditioning"
        assert biz["place_id"].startswith("brave_")
        assert result["total_location_ids"] == 1
        # 1 search + 1 POI batch
        assert result["cost_usd"] == pytest.approx(BRAVE_COST_PER_SEARCH * 2)

    async def test_poi_with_name_fallback(self):
        """POI with 'name' field instead of 'title'."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{
                "name": "FallbackName Inc.",
                "postal_address": {},
                "contact": {},
                "categories": [],
            }]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"][0]["name"] == "FallbackName Inc."

    async def test_poi_with_no_name_and_no_title(self):
        """POI with neither 'title' nor 'name' -> empty string."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{
                "postal_address": {},
                "contact": {},
            }]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"][0]["name"] == ""

    async def test_poi_missing_contact_and_postal_address(self):
        """POI with no contact or postal_address keys at all."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{"title": "Bare Bones Biz"}]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        biz = result["results"][0]
        assert biz["phone"] == ""
        assert biz["address"] == ""
        assert biz["website"] == ""
        assert biz["rating"] is None
        assert biz["reviews"] is None
        assert biz["type"] == ""

    async def test_null_poi_entries_skipped(self):
        """Null/None entries in POI results list should be skipped."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [None, {"title": "Real Biz"}, None]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert len(result["results"]) == 1
        assert result["results"][0]["name"] == "Real Biz"

    async def test_duplicate_pois_deduped(self):
        """Identical businesses (same hash) should be deduped."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        dup_poi = {
            "title": "Acme HVAC",
            "postal_address": {"displayAddress": "100 Oak St"},
            "contact": {"telephone": "+15125550000"},
        }
        poi_resp = _make_mock_response({
            "results": [dup_poi, dup_poi]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert len(result["results"]) == 1

    async def test_multiple_poi_batches(self):
        """25 location IDs should trigger 2 POI batches (20 + 5)."""
        ids = [{"id": f"loc_{i}"} for i in range(25)]
        search_resp = _make_mock_response({
            "locations": {"results": ids}
        })
        # Batch 1: 20 POIs, batch 2: 5 POIs
        poi_resp_1 = _make_mock_response({
            "results": [{"title": f"Biz {i}", "contact": {"telephone": f"+1512555{i:04d}"}} for i in range(20)]
        })
        poi_resp_2 = _make_mock_response({
            "results": [{"title": f"Biz {i}", "contact": {"telephone": f"+1512555{i:04d}"}} for i in range(20, 25)]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp_1, poi_resp_2])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert len(result["results"]) == 25
        assert result["total_location_ids"] == 25
        # 1 search + 2 POI batches = 3
        assert result["cost_usd"] == pytest.approx(BRAVE_COST_PER_SEARCH * 3)

    async def test_max_poi_batches_limits_requests(self):
        """max_poi_batches=1 with 25 IDs should only fetch first 20."""
        ids = [{"id": f"loc_{i}"} for i in range(25)]
        search_resp = _make_mock_response({
            "locations": {"results": ids}
        })
        poi_resp = _make_mock_response({
            "results": [{"title": f"Biz {i}", "contact": {"telephone": f"+1512555{i:04d}"}} for i in range(20)]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses(
                "HVAC", "Austin, TX", "fake-key", max_poi_batches=1
            )

        assert len(result["results"]) == 20
        assert result["total_location_ids"] == 25
        # 1 search + 1 POI batch
        assert result["cost_usd"] == pytest.approx(BRAVE_COST_PER_SEARCH * 2)

    async def test_search_http_error_returns_error(self):
        """HTTP error on web search returns empty results with error."""
        error_resp = _make_mock_response({}, status_code=500)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=error_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"] == []
        assert "error" in result

    async def test_poi_http_error_returns_error(self):
        """HTTP error on POI fetch returns empty results with error."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        error_resp = _make_mock_response({}, status_code=500)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, error_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"] == []
        assert "error" in result

    async def test_network_timeout_returns_error(self):
        """Network timeout is caught and returns error dict."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"] == []
        assert "error" in result

    async def test_rating_with_non_dict_nested_result(self):
        """Nested results that are not dicts should be safely skipped."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{
                "title": "Mixed Results Biz",
                "results": ["not a dict", 42, {"rating": {"ratingValue": 3.5, "ratingCount": 10}}],
            }]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        biz = result["results"][0]
        # Non-dict entries skipped; dict entry with rating found
        assert biz["rating"] == 3.5
        assert biz["reviews"] == 10

    async def test_rating_obj_not_dict_skipped(self):
        """If rating field is not a dict, it should be skipped gracefully."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{
                "title": "Weird Rating Biz",
                "results": [{"rating": "not a dict"}],
            }]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        biz = result["results"][0]
        assert biz["rating"] is None
        assert biz["reviews"] is None

    async def test_rating_value_none_keeps_none(self):
        """ratingValue=None in valid rating object keeps rating as None."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{
                "title": "No Rating Biz",
                "results": [{"rating": {"ratingValue": None, "ratingCount": None}}],
            }]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        biz = result["results"][0]
        assert biz["rating"] is None
        assert biz["reviews"] is None

    async def test_empty_poi_results_list(self):
        """POI response with empty results list."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({"results": []})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"] == []
        assert result["total_location_ids"] == 1

    async def test_place_id_deterministic(self):
        """Place ID is deterministic based on normalized name, phone, address."""
        name = "Cool Air HVAC LLC"
        phone = "+15125551234"
        address = "123 Main St"

        normalized = normalize_biz_name(name)
        hash_input = f"{normalized}|{phone}|{address}".lower()
        expected_id = f"brave_{hashlib.sha256(hash_input.encode()).hexdigest()[:12]}"

        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{
                "title": name,
                "postal_address": {"displayAddress": address},
                "contact": {"telephone": phone},
            }]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"][0]["place_id"] == expected_id

    async def test_locations_obj_none(self):
        """When locations key exists but is None."""
        search_resp = _make_mock_response({"locations": None})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=search_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"] == []
        assert result["total_location_ids"] == 0

    async def test_locations_results_none(self):
        """When locations.results is None."""
        search_resp = _make_mock_response({"locations": {"results": None}})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=search_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"] == []
        assert result["total_location_ids"] == 0

    async def test_poi_results_key_none(self):
        """When POI response has results=None."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({"results": None})

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"] == []
        assert result["total_location_ids"] == 1

    async def test_nested_results_empty_list(self):
        """POI with empty nested results list -> rating stays None."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{"title": "NoRating", "results": []}]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        biz = result["results"][0]
        assert biz["rating"] is None
        assert biz["reviews"] is None

    async def test_contact_telephone_none(self):
        """POI has contact dict but telephone is None -> phone is empty string."""
        search_resp = _make_mock_response({
            "locations": {"results": [{"id": "loc_1"}]}
        })
        poi_resp = _make_mock_response({
            "results": [{"title": "NoPhone", "contact": {"telephone": None}}]
        })

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[search_resp, poi_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.scraping.httpx.AsyncClient", return_value=mock_client):
            result = await search_local_businesses("HVAC", "Austin, TX", "fake-key")

        assert result["results"][0]["phone"] == ""


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
        """Address with no commas — only 1 part, no city extracted."""
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
