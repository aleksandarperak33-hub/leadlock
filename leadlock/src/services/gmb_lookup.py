"""
GMB (Google Business Profile) lookup service.

Parses Google Maps URLs to extract business info, then uses Brave Search
POI data to return structured business details for onboarding pre-fill.
"""
import logging
import re
from typing import Optional
from urllib.parse import unquote_plus, urlparse, parse_qs

import httpx

from src.services.scraping import (
    search_local_businesses,
    normalize_biz_name,
    parse_address_components,
)

logger = logging.getLogger(__name__)

# Google category → LeadLock trade type mapping
CATEGORY_TRADE_MAP: dict[str, str] = {
    "hvac": "hvac",
    "air conditioning": "hvac",
    "heating": "hvac",
    "furnace": "hvac",
    "heat pump": "hvac",
    "plumber": "plumbing",
    "plumbing": "plumbing",
    "drain": "plumbing",
    "roofing": "roofing",
    "roof": "roofing",
    "electrician": "electrical",
    "electrical": "electrical",
    "electric": "electrical",
    "solar": "solar",
    "solar energy": "solar",
    "general contractor": "general contractor",
    "remodeling": "general contractor",
    "landscaping": "landscaping",
    "lawn care": "landscaping",
    "tree service": "landscaping",
    "pest control": "pest control",
    "exterminator": "pest control",
}

# Trade → suggested primary services (mirrors TRADE_SERVICES in Onboarding.jsx)
TRADE_SUGGESTED_SERVICES: dict[str, list[str]] = {
    "hvac": ["AC Repair", "AC Installation", "Furnace Repair", "Maintenance"],
    "plumbing": ["Drain Cleaning", "Water Heater", "Leak Repair", "Pipe Repair"],
    "electrical": ["Panel Upgrade", "Wiring", "Outlet Installation", "Lighting"],
    "roofing": ["Roof Repair", "Roof Replacement", "Inspection", "Storm Damage"],
    "solar": ["Solar Installation", "Panel Maintenance", "Battery Storage"],
    "general contractor": ["Remodeling", "Additions", "Bathroom", "Kitchen"],
    "landscaping": ["Lawn Care", "Tree Trimming", "Irrigation", "Hardscaping"],
    "pest control": ["General Pest", "Termite", "Rodent", "Mosquito"],
}


def parse_gmb_url(raw_url: str) -> dict:
    """
    Extract business name and optional lat/lng from a Google Maps URL.

    Supported formats:
      1. google.com/maps/place/Business+Name/@lat,lng,...
      2. google.com/maps?q=Business+Name
      3. g.page/business-name (resolved externally before calling this)
      4. Plain text business name (no URL scheme)

    Returns:
        {"business_name": str, "lat": float|None, "lng": float|None}
    """
    url = raw_url.strip()

    # Plain text (no scheme, no dots suggesting a domain)
    if not url.startswith("http") and "google.com" not in url and "g.page" not in url:
        return {"business_name": url, "lat": None, "lng": None}

    parsed = urlparse(url if url.startswith("http") else f"https://{url}")

    # Format 1: /maps/place/Business+Name/@lat,lng,...
    place_match = re.search(r"/place/([^/@]+)", parsed.path)
    if place_match:
        name = unquote_plus(place_match.group(1))
        lat, lng = None, None
        coord_match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", parsed.path + "?" + (parsed.query or ""))
        if coord_match:
            lat = float(coord_match.group(1))
            lng = float(coord_match.group(2))
        return {"business_name": name, "lat": lat, "lng": lng}

    # Format 2: /maps?q=Business+Name
    qs = parse_qs(parsed.query)
    if "q" in qs:
        return {"business_name": qs["q"][0], "lat": None, "lng": None}

    # Format 3: g.page/business-name
    if "g.page" in (parsed.hostname or ""):
        slug = parsed.path.strip("/").split("/")[0] if parsed.path else ""
        if slug:
            name = slug.replace("-", " ").title()
            return {"business_name": name, "lat": None, "lng": None}

    # Fallback: treat the whole thing as a business name
    return {"business_name": url, "lat": None, "lng": None}


def detect_trade_type(categories: list[str], business_name: str = "") -> str:
    """
    Map Brave POI categories to a LeadLock trade type.

    Scans each category for known keywords, then falls back to scanning
    the business name itself (e.g. "Baker Brothers Plumbing" → plumbing).
    Returns 'other' if no match found.
    """
    for cat in categories:
        cat_lower = cat.lower()
        for keyword, trade in CATEGORY_TRADE_MAP.items():
            if keyword in cat_lower:
                return trade

    # Fallback: scan business name for trade keywords
    if business_name:
        name_lower = business_name.lower()
        for keyword, trade in CATEGORY_TRADE_MAP.items():
            if keyword in name_lower:
                return trade

    return "other"


def map_to_onboarding_data(poi: dict) -> dict:
    """
    Transform a Brave POI result dict into the onboarding pre-fill shape.

    Args:
        poi: Single result from search_local_businesses()

    Returns:
        Structured dict ready for the frontend QuickSetup confirmation card.
    """
    categories_raw = [c.strip() for c in (poi.get("type") or "").split(",") if c.strip()]
    name = poi.get("name") or ""
    trade_type = detect_trade_type(categories_raw, business_name=name)
    address_parts = parse_address_components(poi.get("address") or "")

    return {
        "business_name": poi.get("name") or "",
        "trade_type": trade_type,
        "phone": poi.get("phone") or "",
        "website": poi.get("website") or "",
        "address": poi.get("address") or "",
        "city": address_parts.get("city") or "",
        "state": address_parts.get("state") or "",
        "zip": address_parts.get("zip") or "",
        "rating": poi.get("rating"),
        "reviews": poi.get("reviews"),
        "categories": categories_raw,
        "suggested_services": TRADE_SUGGESTED_SERVICES.get(trade_type, []),
    }


_ALLOWED_REDIRECT_HOSTS = frozenset({"g.page", "maps.app.goo.gl", "goo.gl"})


async def resolve_short_url(url: str) -> str:
    """Follow redirects on g.page / short URLs to get the full Google Maps URL.

    Only resolves URLs from known-safe Google redirect domains to prevent SSRF.
    """
    parsed_input = urlparse(url if url.startswith("http") else f"https://{url}")
    if parsed_input.hostname not in _ALLOWED_REDIRECT_HOSTS:
        logger.warning("Refusing to resolve non-allowlisted host: %s", parsed_input.hostname)
        return url

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.head(url)
            final = urlparse(str(resp.url))
            if not (final.hostname or "").endswith("google.com"):
                logger.warning("Redirect resolved to unexpected host: %s", final.hostname)
                return url
            return str(resp.url)
    except Exception as exc:
        logger.warning("Failed to resolve short URL %s: %s", url, exc)
        return url


def _parse_infobox_location(infobox: dict) -> Optional[dict]:
    """Extract business data from a Brave infobox with location info."""
    results = infobox.get("results") or []
    for item in results:
        if not isinstance(item, dict):
            continue
        # Check for location data in the infobox result
        location = item.get("location") or {}
        postal = location.get("postal_address") or item.get("postal_address") or {}
        contact = location.get("contact") or item.get("contact") or {}
        address = postal.get("displayAddress") or ""
        phone = contact.get("telephone") or ""
        name = item.get("title") or ""
        website = item.get("website_url") or item.get("url") or ""

        # Only use if we have at least a name and address or phone
        if name and (address or phone):
            return {
                "name": name,
                "address": address,
                "phone": phone,
                "website": website,
                "rating": None,
                "reviews": None,
                "type": "",
            }
    return None


async def _brave_web_search(query: str, api_key: str) -> list[dict]:
    """
    Broad Brave web search that extracts business data from either
    location IDs or the infobox knowledge graph.

    Brave's result_filter=locations misses specific business names,
    but often returns an infobox with address/phone for branded queries.
    """
    from src.services.scraping import (
        BRAVE_SEARCH_URL,
        BRAVE_POI_URL,
        POI_BATCH_SIZE,
    )

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                params={"q": query, "count": 10},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            # Strategy 1: Extract location IDs if Brave included them
            locations = (data.get("locations") or {}).get("results") or []
            location_ids = [loc["id"] for loc in locations if loc.get("id")]
            if location_ids:
                poi_params = [("ids", lid) for lid in location_ids[:POI_BATCH_SIZE]]
                poi_resp = await client.get(BRAVE_POI_URL, params=poi_params, headers=headers)
                poi_resp.raise_for_status()
                poi_results = poi_resp.json().get("results") or []
                results = []
                for poi in poi_results:
                    if not poi:
                        continue
                    name = poi.get("title") or poi.get("name") or ""
                    postal = poi.get("postal_address") or {}
                    contact_info = poi.get("contact") or {}
                    results.append({
                        "name": name,
                        "address": postal.get("displayAddress") or "",
                        "phone": contact_info.get("telephone") or "",
                        "website": poi.get("url") or "",
                        "rating": None,
                        "reviews": None,
                        "type": ", ".join(poi.get("categories") or []),
                    })
                if results:
                    return results

            # Strategy 2: Extract from infobox (knowledge graph)
            infobox = data.get("infobox") or {}
            infobox_result = _parse_infobox_location(infobox)
            if infobox_result:
                return [infobox_result]

            return []
    except Exception as exc:
        logger.warning("Brave web search failed for '%s': %s", query[:40], exc)
        return []


async def lookup_business(url_or_name: str, api_key: str) -> dict:
    """
    Full GMB lookup pipeline: parse URL → resolve redirects → Brave search → best match.

    Args:
        url_or_name: Google Maps URL or plain business name
        api_key: Brave Search API key

    Returns:
        {"success": True, "business": {...}} or {"success": False, "error": "..."}
    """
    raw = url_or_name.strip()
    if not raw:
        return {"success": False, "error": "No URL or business name provided"}

    # Resolve g.page short URLs
    if "g.page" in raw.lower():
        raw = await resolve_short_url(raw if raw.startswith("http") else f"https://{raw}")

    parsed = parse_gmb_url(raw)
    business_name = (parsed.get("business_name") or "")[:150].strip()

    if not business_name:
        return {"success": False, "error": "Could not extract business name from URL"}

    # For single-business GMB lookups, use the broader search first (without
    # result_filter=locations) since Brave's location filter often misses
    # specific business names. The broad search checks both location IDs and
    # the infobox knowledge graph. Fall back to location-filtered search only
    # if the broad search finds nothing.
    results = await _brave_web_search(business_name, api_key)

    if not results:
        search_result = await search_local_businesses(
            query=business_name,
            location="",
            api_key=api_key,
            max_poi_batches=1,
        )
        results = search_result.get("results") or []

    if not results:
        return {"success": False, "error": f"No business found for '{business_name}'"}

    # Pick the best match: prefer exact normalized name match, else first result
    normalized_query = normalize_biz_name(business_name)
    best = results[0]
    for r in results:
        if normalize_biz_name(r.get("name") or "") == normalized_query:
            best = r
            break

    business_data = map_to_onboarding_data(best)

    logger.info(
        "GMB lookup: query='%s' matched='%s' trade=%s",
        business_name[:40],
        business_data["business_name"][:40],
        business_data["trade_type"],
    )

    return {"success": True, "business": business_data}
