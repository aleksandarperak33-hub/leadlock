"""
Scraping service — Google Maps & Yelp via SerpAPI.
Discovers home services contractors by trade type and location.
"""
import logging
import re
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

SERPAPI_BASE = "https://serpapi.com/search"
SERPAPI_COST_PER_SEARCH = 0.01  # ~$0.01/search


async def search_google_maps(
    query: str,
    location: str,
    api_key: str,
) -> dict:
    """
    Search Google Maps for businesses via SerpAPI.

    Args:
        query: Search term, e.g. "HVAC contractors"
        location: Location string, e.g. "Austin, TX"
        api_key: SerpAPI API key

    Returns:
        {"results": [...], "cost_usd": float}
    """
    params = {
        "engine": "google_maps",
        "q": query,
        "location": location,
        "type": "search",
        "api_key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(SERPAPI_BASE, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for place in data.get("local_results", []):
            results.append({
                "name": place.get("title", ""),
                "place_id": place.get("place_id", ""),
                "address": place.get("address", ""),
                "phone": place.get("phone", ""),
                "website": place.get("website", ""),
                "rating": place.get("rating"),
                "reviews": place.get("reviews"),
                "type": place.get("type", ""),
            })

        logger.info(
            "Google Maps search: query=%s location=%s results=%d",
            query, location, len(results),
        )
        return {"results": results, "cost_usd": SERPAPI_COST_PER_SEARCH}

    except Exception as e:
        logger.error("Google Maps search failed: %s", str(e))
        return {"results": [], "cost_usd": SERPAPI_COST_PER_SEARCH, "error": str(e)}


async def search_yelp(
    query: str,
    location: str,
    api_key: str,
) -> dict:
    """
    Search Yelp for businesses via SerpAPI.

    Args:
        query: Search term, e.g. "plumbing contractors"
        location: Location string, e.g. "Austin, TX"
        api_key: SerpAPI API key

    Returns:
        {"results": [...], "cost_usd": float}
    """
    params = {
        "engine": "yelp",
        "find_desc": query,
        "find_loc": location,
        "api_key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(SERPAPI_BASE, params=params)
            response.raise_for_status()
            data = response.json()

        results = []
        for biz in data.get("organic_results", []):
            results.append({
                "name": biz.get("title", ""),
                "place_id": f"yelp_{biz.get('place_ids', [''])[0]}" if biz.get("place_ids") else "",
                "address": biz.get("neighborhoods", ""),
                "phone": biz.get("phone", ""),
                "website": biz.get("link", ""),
                "rating": biz.get("rating"),
                "reviews": biz.get("reviews"),
                "type": ", ".join(biz.get("categories", [])) if biz.get("categories") else "",
            })

        logger.info(
            "Yelp search: query=%s location=%s results=%d",
            query, location, len(results),
        )
        return {"results": results, "cost_usd": SERPAPI_COST_PER_SEARCH}

    except Exception as e:
        logger.error("Yelp search failed: %s", str(e))
        return {"results": [], "cost_usd": SERPAPI_COST_PER_SEARCH, "error": str(e)}


def parse_address_components(address: str) -> dict:
    """
    Parse a full address string into city, state, zip components.

    Args:
        address: Full address string, e.g. "123 Main St, Austin, TX 78701"

    Returns:
        {"city": str, "state": str, "zip": str}
    """
    result = {"city": "", "state": "", "zip": ""}

    if not address:
        return result

    # Try to extract ZIP code
    zip_match = re.search(r"\b(\d{5})(?:-\d{4})?\b", address)
    if zip_match:
        result["zip"] = zip_match.group(1)

    # Try to extract state code (2-letter abbreviation)
    state_match = re.search(r"\b([A-Z]{2})\b", address)
    if state_match:
        result["state"] = state_match.group(1)

    # Try to extract city (typically before state code in comma-separated format)
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 2:
        # City is usually the second-to-last part before state+zip
        city_candidate = parts[-2] if len(parts) >= 3 else parts[0]
        # Clean up any numbers (street numbers)
        city_clean = re.sub(r"^\d+\s+\w+\s+(St|Ave|Blvd|Dr|Rd|Ln|Way|Ct)\b.*", "", city_candidate).strip()
        result["city"] = city_clean if city_clean else city_candidate.strip()

    return result
