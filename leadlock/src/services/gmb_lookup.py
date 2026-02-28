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


def detect_trade_type(categories: list[str]) -> str:
    """
    Map Brave POI categories to a LeadLock trade type.

    Scans each category for known keywords and returns the first match.
    Falls back to 'other' if no match found.
    """
    for cat in categories:
        cat_lower = cat.lower()
        for keyword, trade in CATEGORY_TRADE_MAP.items():
            if keyword in cat_lower:
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
    trade_type = detect_trade_type(categories_raw)
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

    # Use Brave Search to find the business (limit to 1 batch for speed)
    search_result = await search_local_businesses(
        query=business_name,
        location="",  # No location filter — the name from the URL is specific enough
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
