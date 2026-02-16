"""
Scraping service — local business discovery via Brave Search API.
Two-step process: web search for location IDs → POI details for business data.
"""
import hashlib
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
    offset: int = 0,
) -> dict:
    """
    Search for local businesses via Brave Search API.
    Step 1: Web search with location filter to get POI IDs.
    Step 2: Fetch full POI details (phone, website, rating, etc).

    Args:
        query: Search term, e.g. "HVAC contractors"
        location: Location string, e.g. "Austin, TX"
        api_key: Brave Search API key
        offset: Pagination offset (0-9) for deeper results

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
                "offset": min(offset, 9),  # Brave max offset is 9
            }
            response = await client.get(
                BRAVE_SEARCH_URL, params=search_params, headers=headers
            )
            response.raise_for_status()
            search_data = response.json()
            total_cost += BRAVE_COST_PER_SEARCH

            # Extract location IDs
            locations_obj = search_data.get("locations") or {}
            locations = locations_obj.get("results") or []
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
        # Brave POI response fields: title, url, postal_address, contact, categories, results (nested)
        results = []
        for poi in (poi_data.get("results") or []):
            if not poi:
                continue
            # Name — Brave uses "title" not "name"
            name = poi.get("title") or poi.get("name") or ""

            # Address — Brave uses postal_address.displayAddress
            postal_addr = poi.get("postal_address") or {}
            full_address = postal_addr.get("displayAddress") or ""

            # Phone — in contact.telephone
            phone = ""
            contact = poi.get("contact") or {}
            if contact.get("telephone"):
                phone = contact["telephone"]

            # Website — Brave uses "url"
            website = poi.get("url") or ""

            # Rating — check nested "results" array for aggregateRating
            rating = None
            review_count = None
            nested_results = poi.get("results") or []
            for nr in nested_results:
                if isinstance(nr, dict):
                    rating_obj = nr.get("rating") or {}
                    if isinstance(rating_obj, dict):
                        if rating_obj.get("ratingValue") is not None:
                            rating = rating_obj["ratingValue"]
                        if rating_obj.get("ratingCount") is not None:
                            review_count = rating_obj["ratingCount"]
                        break

            # Place ID — deterministic hash for stable dedup across runs
            hash_input = f"{name}|{phone}|{full_address}".lower()
            place_id = f"brave_{hashlib.sha256(hash_input.encode()).hexdigest()[:12]}"

            # Categories
            categories = poi.get("categories") or []
            cat_str = ", ".join(categories) if categories else ""

            results.append({
                "name": name,
                "place_id": place_id,
                "address": full_address,
                "phone": phone,
                "website": website,
                "rating": rating,
                "reviews": review_count,
                "type": cat_str,
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
