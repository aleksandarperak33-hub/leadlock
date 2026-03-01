"""
Google Maps scraping service — local business discovery via direct scraping.

Replaces Brave Search API. Uses curl_cffi with Chrome TLS impersonation
to fetch Google Maps search results and extract embedded business data
from the page source (APP_INITIALIZATION_STATE JavaScript variable).

Returns the same shape as the old search_local_businesses():
    {"results": [...], "cost_usd": 0.0, "total_location_ids": int}

Also provides search_google_maps_place() for single-business GMB lookup.
"""
import asyncio
import hashlib
import json
import logging
import random
import re
from typing import Optional
from urllib.parse import quote_plus

from curl_cffi.requests import AsyncSession
from scrapling import Selector

from src.services.scraping import normalize_biz_name

logger = logging.getLogger(__name__)

# Rate limiting: random delay range (seconds) between Google requests
_MIN_DELAY = 2.0
_MAX_DELAY = 5.0
_TIMEOUT = 15.0

# Google Maps search URL template
_MAPS_SEARCH_URL = "https://www.google.com/maps/search/{query}/?hl=en"

# Regex to extract APP_INITIALIZATION_STATE from Google Maps page source
_APP_INIT_STATE_RE = re.compile(
    r"window\.APP_INITIALIZATION_STATE\s*=\s*(\[.+?\]);\s*(?:window\.|</script>)",
    re.DOTALL,
)

# Google local pack regex for fallback HTML parsing
_LOCAL_PACK_NAME_RE = re.compile(
    r'<div[^>]*class="[^"]*dbg0pd[^"]*"[^>]*>([^<]+)</div>', re.IGNORECASE
)

# Phone number pattern in Google Maps data
_PHONE_RE = re.compile(r'(\+?1?\s*[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})')


def _generate_place_id(name: str, phone: str, address: str) -> str:
    """Generate deterministic place_id using gscrape_ prefix."""
    normalized_name = normalize_biz_name(name)
    hash_input = f"{normalized_name}|{phone}|{address}".lower()
    return f"gscrape_{hashlib.sha256(hash_input.encode()).hexdigest()[:12]}"


def _clean_text(text: Optional[str]) -> str:
    """Strip HTML entities and extra whitespace from extracted text."""
    if not text:
        return ""
    # Remove common HTML entities
    cleaned = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    cleaned = cleaned.replace("&#39;", "'").replace("&quot;", '"')
    return cleaned.strip()


def _extract_businesses_from_app_state(raw_js: str) -> list[dict]:
    """
    Parse the nested array structure in APP_INITIALIZATION_STATE to extract
    business listings. Google Maps embeds structured data as deeply nested
    JSON arrays.

    The data structure varies but typically business entries are found at
    indices like [3][2] or deeper, containing arrays where each business
    has name, address, phone, website, rating, reviews, and categories.
    """
    results: list[dict] = []

    try:
        data = json.loads(raw_js)
    except (json.JSONDecodeError, ValueError):
        logger.debug("Failed to parse APP_INITIALIZATION_STATE JSON")
        return results

    # Navigate the nested structure to find business listing data.
    # Google Maps embeds results in deeply nested arrays. The structure
    # is: data[3][2] contains the serialized search results as a JSON string.
    try:
        # data[3][2] typically contains a JSON string with the actual results
        inner_json_str = data[3][2] if len(data) > 3 and isinstance(data[3], list) and len(data[3]) > 2 else None
        if inner_json_str and isinstance(inner_json_str, str):
            inner_data = json.loads(inner_json_str)
            results = _walk_inner_data(inner_data)
            if results:
                return results
    except (IndexError, TypeError, json.JSONDecodeError):
        pass

    # Fallback: try alternative positions in the nested structure
    try:
        # Sometimes data[1] or data[5] contains the listings
        for idx in [1, 5, 4]:
            if len(data) > idx and isinstance(data[idx], list):
                try:
                    candidate = data[idx]
                    if isinstance(candidate, str):
                        candidate = json.loads(candidate)
                    extracted = _walk_inner_data(candidate)
                    if extracted:
                        return extracted
                except (json.JSONDecodeError, TypeError):
                    continue
    except (IndexError, TypeError):
        pass

    return results


def _walk_inner_data(data) -> list[dict]:
    """
    Walk the inner data structure to extract business entries.

    Each business entry in Google Maps data is typically an array containing:
    - [11] or [14]: name
    - [18]: address
    - [7][0] or [178][0][0]: phone
    - [7][1]: website
    - [4][7]: rating
    - [4][8]: review count
    - [13]: categories list
    """
    results: list[dict] = []

    if not isinstance(data, list):
        return results

    # The inner data typically has listings at various positions.
    # Try to find the array that contains business listing arrays.
    candidates = _find_listing_arrays(data)

    for listing in candidates:
        biz = _parse_single_listing(listing)
        if biz and biz.get("name"):
            results.append(biz)

    return results


def _find_listing_arrays(data, depth: int = 0) -> list:
    """Recursively search for arrays that look like business listings."""
    if depth > 6 or not isinstance(data, list):
        return []

    listings = []

    # A business listing array typically has 20+ elements and contains
    # string elements at certain indices that look like names/addresses
    if len(data) > 10:
        parsed = _parse_single_listing(data)
        if parsed and parsed.get("name"):
            return [data]

    for item in data:
        if isinstance(item, list):
            found = _find_listing_arrays(item, depth + 1)
            listings.extend(found)

    return listings


def _parse_single_listing(arr) -> Optional[dict]:
    """Try to parse a single array as a business listing."""
    if not isinstance(arr, list) or len(arr) < 10:
        return None

    name = _safe_str(arr, 11) or _safe_str(arr, 14)
    if not name:
        return None

    address = _safe_str(arr, 18)
    phone = ""
    website = ""
    rating = None
    review_count = None
    categories: list[str] = []

    # Phone — try multiple known positions
    try:
        if len(arr) > 7 and isinstance(arr[7], list) and arr[7]:
            phone = str(arr[7][0]) if arr[7][0] else ""
    except (IndexError, TypeError):
        pass

    if not phone:
        try:
            if len(arr) > 178 and isinstance(arr[178], list):
                deep = arr[178]
                if isinstance(deep, list) and deep and isinstance(deep[0], list) and deep[0]:
                    phone = str(deep[0][0]) if deep[0][0] else ""
        except (IndexError, TypeError):
            pass

    # Website
    try:
        if len(arr) > 7 and isinstance(arr[7], list) and len(arr[7]) > 1:
            website = str(arr[7][1]) if arr[7][1] else ""
    except (IndexError, TypeError):
        pass

    # Rating and review count
    try:
        if len(arr) > 4 and isinstance(arr[4], list):
            rating_arr = arr[4]
            if len(rating_arr) > 7 and rating_arr[7] is not None:
                rating = float(rating_arr[7])
            if len(rating_arr) > 8 and rating_arr[8] is not None:
                review_count = int(rating_arr[8])
    except (IndexError, TypeError, ValueError):
        pass

    # Categories
    try:
        if len(arr) > 13 and isinstance(arr[13], list):
            categories = [str(c) for c in arr[13] if isinstance(c, str)]
    except (IndexError, TypeError):
        pass

    return {
        "name": _clean_text(name),
        "address": _clean_text(address),
        "phone": phone,
        "website": website,
        "rating": rating,
        "reviews": review_count,
        "categories": categories,
    }


def _safe_str(arr: list, idx: int) -> str:
    """Safely extract a string from an array at the given index."""
    try:
        val = arr[idx]
        return str(val) if val and isinstance(val, str) else ""
    except (IndexError, TypeError):
        return ""


def _extract_from_html_fallback(html: str) -> list[dict]:
    """
    Fallback: extract business data from Google search HTML using scrapling.
    Parses the local pack / map results when APP_INITIALIZATION_STATE fails.
    """
    results: list[dict] = []

    try:
        sel = Selector(html)
    except Exception:
        return results

    # Look for local business result cards
    # Google's local pack uses various class names; try common selectors
    for card in sel.css("div.VkpGBb, div.rllt__details, div.uQ4NLd"):
        name_el = card.css_first("span.OSrXXb, div.dbg0pd, span.fontHeadlineSmall")
        name = name_el.text() if name_el else ""
        if not name:
            continue

        # Address
        addr_el = card.css_first("span.LrzXr, div.rllt__wrapped")
        address = addr_el.text() if addr_el else ""

        # Phone from text content
        phone = ""
        card_text = card.text() or ""
        phone_match = _PHONE_RE.search(card_text)
        if phone_match:
            phone = phone_match.group(1)

        # Website from link
        website = ""
        for link in card.css("a[href]"):
            href = link.attrib.get("href", "")
            if href.startswith("http") and "google.com" not in href:
                website = href
                break

        # Rating from aria-label or text
        rating = None
        review_count = None
        rating_el = card.css_first("span.MW4etd, span.Y0A0hc")
        if rating_el:
            try:
                rating = float(rating_el.text())
            except (ValueError, TypeError):
                pass
        reviews_el = card.css_first("span.UY7F9, span.RDApEe")
        if reviews_el:
            reviews_text = reviews_el.text() or ""
            reviews_num = re.sub(r"[^\d]", "", reviews_text)
            if reviews_num:
                try:
                    review_count = int(reviews_num)
                except ValueError:
                    pass

        results.append({
            "name": _clean_text(name),
            "address": _clean_text(address),
            "phone": phone,
            "website": website,
            "rating": rating,
            "reviews": review_count,
            "categories": [],
        })

    return results


async def search_local_businesses(
    query: str,
    location: str,
) -> dict:
    """
    Search for local businesses by scraping Google Maps.

    Args:
        query: Search term, e.g. "HVAC contractors"
        location: Location string, e.g. "Austin, TX"

    Returns:
        {"results": [...], "cost_usd": 0.0, "total_location_ids": int}
    """
    search_query = f"{query} in {location}" if location else query
    encoded_query = quote_plus(search_query)
    url = _MAPS_SEARCH_URL.format(query=encoded_query)

    results: list[dict] = []
    seen_hashes: set[str] = set()

    try:
        async with AsyncSession(impersonate="chrome") as session:
            response = await session.get(url, timeout=_TIMEOUT)

            if response.status_code != 200:
                logger.warning(
                    "Google Maps returned status %d for query '%s'",
                    response.status_code, search_query[:50],
                )
                return {"results": [], "cost_usd": 0.0, "total_location_ids": 0}

            html = response.text

            # Strategy 1: Extract from APP_INITIALIZATION_STATE
            match = _APP_INIT_STATE_RE.search(html)
            if match:
                raw_businesses = _extract_businesses_from_app_state(match.group(1))
                for biz in raw_businesses:
                    place_id = _generate_place_id(
                        biz.get("name", ""),
                        biz.get("phone", ""),
                        biz.get("address", ""),
                    )
                    if place_id in seen_hashes:
                        continue
                    seen_hashes.add(place_id)

                    cat_str = ", ".join(biz.get("categories", []))
                    results.append({
                        "name": biz["name"],
                        "place_id": place_id,
                        "address": biz.get("address", ""),
                        "phone": biz.get("phone", ""),
                        "website": biz.get("website", ""),
                        "rating": biz.get("rating"),
                        "reviews": biz.get("reviews"),
                        "type": cat_str,
                    })

            # Strategy 2: Fallback to HTML parsing if no results from JS data
            if not results:
                html_businesses = _extract_from_html_fallback(html)
                for biz in html_businesses:
                    place_id = _generate_place_id(
                        biz.get("name", ""),
                        biz.get("phone", ""),
                        biz.get("address", ""),
                    )
                    if place_id in seen_hashes:
                        continue
                    seen_hashes.add(place_id)

                    cat_str = ", ".join(biz.get("categories", []))
                    results.append({
                        "name": biz["name"],
                        "place_id": place_id,
                        "address": biz.get("address", ""),
                        "phone": biz.get("phone", ""),
                        "website": biz.get("website", ""),
                        "rating": biz.get("rating"),
                        "reviews": biz.get("reviews"),
                        "type": cat_str,
                    })

        logger.info(
            "Google scrape: query='%s' results=%d",
            search_query[:50], len(results),
        )
        return {
            "results": results,
            "cost_usd": 0.0,
            "total_location_ids": len(results),
        }

    except Exception as e:
        logger.error("Google scrape failed for '%s': %s", search_query[:50], str(e))
        return {"results": [], "cost_usd": 0.0, "error": str(e)}


async def search_google_maps_place(name: str) -> list[dict]:
    """
    Search Google Maps for a single business by name.
    Returns list of matching business dicts (same shape as results from
    search_local_businesses).

    Used by gmb_lookup for onboarding business pre-fill.
    """
    if not name or not name.strip():
        return []

    result = await search_local_businesses(query=name, location="")
    return result.get("results", [])
