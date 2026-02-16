"""
Scraping service — local business discovery via Brave Search API.
Two-step process: web search for location IDs → POI details for business data.
"""
import logging
import re
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_POI_URL = "https://api.search.brave.com/res/v1/local/pois"
BRAVE_COST_PER_SEARCH = 0.005  # ~$5/1k requests


async def search_local_businesses(
    query: str,
    location: str,
    api_key: str,
) -> dict:
    """
    Search for local businesses via Brave Search API.
    Step 1: Web search with location filter to get POI IDs.
    Step 2: Fetch full POI details (phone, website, rating, etc).

    Args:
        query: Search term, e.g. "HVAC contractors"
        location: Location string, e.g. "Austin, TX"
        api_key: Brave Search API key

    Returns:
        {"results": [...], "cost_usd": float}
    """
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }

    total_cost = 0.0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Web search to get location IDs
            search_params = {
                "q": f"{query} {location}",
                "result_filter": "locations",
                "count": 20,
            }
            response = await client.get(
                BRAVE_SEARCH_URL, params=search_params, headers=headers
            )
            response.raise_for_status()
            search_data = response.json()
            total_cost += BRAVE_COST_PER_SEARCH

            # Extract location IDs
            locations = search_data.get("locations", {}).get("results", [])
            if not locations:
                logger.info("Brave search: no local results for %s %s", query, location)
                return {"results": [], "cost_usd": total_cost}

            location_ids = [loc["id"] for loc in locations if loc.get("id")]
            if not location_ids:
                logger.info("Brave search: no location IDs for %s %s", query, location)
                return {"results": [], "cost_usd": total_cost}

            # Step 2: Fetch POI details (max 20 per request)
            poi_params = [("ids", lid) for lid in location_ids[:20]]
            poi_response = await client.get(
                BRAVE_POI_URL, params=poi_params, headers=headers
            )
            poi_response.raise_for_status()
            poi_data = poi_response.json()
            total_cost += BRAVE_COST_PER_SEARCH

        # Parse POI results into our standard format
        results = []
        for poi in poi_data.get("results", []):
            # Build address string from components
            address_obj = poi.get("address", {})
            address_parts = []
            if address_obj.get("streetAddress"):
                address_parts.append(address_obj["streetAddress"])
            if address_obj.get("addressLocality"):
                address_parts.append(address_obj["addressLocality"])
            if address_obj.get("addressRegion"):
                address_parts.append(address_obj["addressRegion"])
            if address_obj.get("postalCode"):
                address_parts.append(address_obj["postalCode"])
            full_address = ", ".join(address_parts)

            # Extract phone — Brave puts it in various places
            phone = ""
            if poi.get("phone"):
                phone = poi["phone"]
            elif poi.get("contact", {}).get("telephone"):
                phone = poi["contact"]["telephone"]

            # Extract rating
            rating = None
            rating_obj = poi.get("rating", {})
            if isinstance(rating_obj, dict):
                rating = rating_obj.get("ratingValue")
            elif isinstance(rating_obj, (int, float)):
                rating = rating_obj

            review_count = None
            if isinstance(rating_obj, dict):
                review_count = rating_obj.get("ratingCount")

            results.append({
                "name": poi.get("name", poi.get("title", "")),
                "place_id": f"brave_{poi.get('id', '')}",
                "address": full_address,
                "phone": phone,
                "website": poi.get("website", poi.get("url", "")),
                "rating": rating,
                "reviews": review_count,
                "type": ", ".join(poi.get("categories", [])) if poi.get("categories") else "",
            })

        logger.info(
            "Brave search: query='%s %s' location_ids=%d results=%d cost=$%.3f",
            query, location, len(location_ids), len(results), total_cost,
        )
        return {"results": results, "cost_usd": total_cost}

    except Exception as e:
        logger.error("Brave search failed: %s", str(e))
        return {"results": [], "cost_usd": total_cost, "error": str(e)}


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
