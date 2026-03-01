"""
Scraping service — local business discovery via Google Maps scraping.

Delegates to google_scraper module for actual scraping. This module retains
normalize_biz_name() and parse_address_components() which are used across
the codebase.
"""
import logging
import re

logger = logging.getLogger(__name__)


def normalize_biz_name(name: str) -> str:
    """Normalize business name for stable dedup hashing.
    Strips punctuation, extra whitespace, common suffixes like Inc/LLC.
    """
    if not name:
        return ""
    # Lowercase
    s = name.lower().strip()
    # Remove common legal suffixes
    for suffix in [" llc", " inc", " inc.", " corp", " corp.", " co.", " ltd", " ltd."]:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    # Remove punctuation (keep alphanumeric and spaces)
    s = re.sub(r"[^\w\s]", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def search_local_businesses(
    query: str,
    location: str,
    api_key: str = "",
    max_poi_batches: int = 5,
) -> dict:
    """
    Search for local businesses by scraping Google Maps.

    Delegates to google_scraper. The api_key and max_poi_batches params
    are retained for backward compatibility but ignored.

    Args:
        query: Search term, e.g. "HVAC contractors"
        location: Location string, e.g. "Austin, TX"
        api_key: Unused (kept for backward compat)
        max_poi_batches: Unused (kept for backward compat)

    Returns:
        {"results": [...], "cost_usd": 0.0, "total_location_ids": int}
    """
    from src.services.google_scraper import search_local_businesses as _google_search

    return await _google_search(query=query, location=location)


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

    # Try to extract state code - anchor after comma and before ZIP to avoid
    # matching directional prefixes (NW, SE, etc.) or other 2-letter words
    state_match = re.search(r",\s*([A-Z]{2})\s+\d{5}", address)
    if state_match:
        result["state"] = state_match.group(1)
    else:
        # Fallback: last 2-letter uppercase word before ZIP
        state_fallback = re.search(r"\b([A-Z]{2})\b\s+\d{5}", address)
        if state_fallback:
            result["state"] = state_fallback.group(1)

    # Try to extract city (typically before state code in comma-separated format)
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 2:
        # City is usually the second-to-last part before state+zip
        city_candidate = parts[-2] if len(parts) >= 3 else parts[0]
        # Clean up any numbers (street numbers)
        city_clean = re.sub(r"^\d+\s+\w+\s+(St|Ave|Blvd|Dr|Rd|Ln|Way|Ct)\b.*", "", city_candidate).strip()
        result["city"] = city_clean if city_clean else city_candidate.strip()

    return result
