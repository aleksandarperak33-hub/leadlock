"""
Local business discovery via DuckDuckGo Places API.

Replaces Brave Search API. Uses curl_cffi with Chrome TLS impersonation
to call the DuckDuckGo local places endpoint, which returns structured
business data sourced from Yelp and Apple Maps.

Returns the same shape as the old search_local_businesses():
    {"results": [...], "cost_usd": 0.0, "total_location_ids": int}

Also provides search_google_maps_place() for single-business GMB lookup.
"""
import hashlib
import logging
import re
from typing import Optional
from urllib.parse import quote_plus

from curl_cffi.requests import AsyncSession

from src.services.scraping import normalize_biz_name

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0

# DuckDuckGo Places API endpoint
_DDG_PLACES_URL = "https://duckduckgo.com/local.js"

# Phone normalization: strip to digits only
_DIGITS_RE = re.compile(r"\D")


def _generate_place_id(name: str, phone: str, address: str) -> str:
    """Generate deterministic place_id using gscrape_ prefix."""
    normalized_name = normalize_biz_name(name)
    hash_input = f"{normalized_name}|{phone}|{address}".lower()
    return f"gscrape_{hashlib.sha256(hash_input.encode()).hexdigest()[:12]}"


def _normalize_phone(raw: Optional[str]) -> str:
    """Normalize phone to digits-only string (e.g. '+15122668522' -> '15122668522')."""
    if not raw:
        return ""
    digits = _DIGITS_RE.sub("", raw)
    # Ensure US numbers have country code
    if len(digits) == 10:
        digits = "1" + digits
    return digits


def _format_phone(digits: str) -> str:
    """Format phone digits as (XXX) XXX-XXXX for display."""
    if len(digits) == 11 and digits.startswith("1"):
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return digits


def _parse_ddg_result(biz: dict) -> Optional[dict]:
    """Convert a single DDG places result to our standard business dict."""
    name = (biz.get("name") or "").strip()
    if not name:
        return None

    phone_raw = biz.get("phone") or biz.get("display_phone") or ""
    phone_digits = _normalize_phone(phone_raw)
    phone_display = _format_phone(phone_digits) if phone_digits else ""

    website = (biz.get("website") or "").strip()
    address = (biz.get("address") or "").strip()

    rating = biz.get("rating")
    if rating is not None:
        try:
            rating = float(rating)
        except (ValueError, TypeError):
            rating = None

    reviews = biz.get("reviews")
    if reviews is not None:
        try:
            reviews = int(reviews)
        except (ValueError, TypeError):
            reviews = None

    category = biz.get("ddg_category") or ""

    return {
        "name": name,
        "address": address,
        "phone": phone_display,
        "website": website,
        "rating": rating,
        "reviews": reviews,
        "categories": [category] if category else [],
    }


async def search_local_businesses(
    query: str,
    location: str,
) -> dict:
    """
    Search for local businesses using DuckDuckGo Places API.

    Args:
        query: Search term, e.g. "HVAC contractors"
        location: Location string, e.g. "Austin, TX"

    Returns:
        {"results": [...], "cost_usd": 0.0, "total_location_ids": int}
    """
    search_query = f"{query} in {location}" if location else query

    results: list[dict] = []
    seen_hashes: set[str] = set()

    try:
        async with AsyncSession(impersonate="chrome") as session:
            params = {
                "q": search_query,
                "tg": "maps_places",
                "rt": "D",
            }
            response = await session.get(
                _DDG_PLACES_URL,
                params=params,
                timeout=_TIMEOUT,
            )

            if response.status_code != 200:
                logger.warning(
                    "DDG Places returned status %d for query '%s'",
                    response.status_code,
                    search_query[:60],
                )
                return {"results": [], "cost_usd": 0.0, "total_location_ids": 0}

            data = response.json()
            raw_results = data.get("results", [])

            for biz_raw in raw_results:
                biz = _parse_ddg_result(biz_raw)
                if not biz:
                    continue

                # Skip closed businesses
                if biz_raw.get("closed"):
                    continue

                place_id = _generate_place_id(
                    biz["name"],
                    biz["phone"],
                    biz["address"],
                )
                if place_id in seen_hashes:
                    continue
                seen_hashes.add(place_id)

                cat_str = ", ".join(biz.get("categories", []))
                results.append({
                    "name": biz["name"],
                    "place_id": place_id,
                    "address": biz["address"],
                    "phone": biz["phone"],
                    "website": biz["website"],
                    "rating": biz["rating"],
                    "reviews": biz["reviews"],
                    "type": cat_str,
                })

        logger.info(
            "DDG Places: query='%s' results=%d",
            search_query[:60],
            len(results),
        )
        return {
            "results": results,
            "cost_usd": 0.0,
            "total_location_ids": len(results),
        }

    except Exception as e:
        logger.error(
            "DDG Places failed for '%s': %s",
            search_query[:60],
            str(e),
        )
        return {"results": [], "cost_usd": 0.0, "error": str(e)}


async def search_google_maps_place(name: str) -> list[dict]:
    """
    Search for a single business by name.
    Returns list of matching business dicts (same shape as results from
    search_local_businesses).

    Used by gmb_lookup for onboarding business pre-fill.
    """
    if not name or not name.strip():
        return []

    result = await search_local_businesses(query=name, location="")
    return result.get("results", [])
