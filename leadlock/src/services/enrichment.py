"""
Enrichment service — find and verify business emails.
Uses Hunter.io as primary source, with pattern guessing as fallback.
Rate-limited: max 2 concurrent requests, 15/minute, 20 per job.
"""
import asyncio
import logging
import re
import time
from typing import Optional
from urllib.parse import urlparse
import httpx

logger = logging.getLogger(__name__)

HUNTER_API_BASE = "https://api.hunter.io/v2"
HUNTER_COST_PER_LOOKUP = 0.049  # ~$0.049/lookup

# Rate limiting state
_hunter_semaphore = asyncio.Semaphore(2)  # Max 2 concurrent requests
_hunter_call_timestamps: list[float] = []
HUNTER_MAX_PER_MINUTE = 15


async def find_email_hunter(
    domain: str,
    company_name: str,
    api_key: str,
) -> dict:
    """
    Find business email via Hunter.io domain search.

    Args:
        domain: Business domain, e.g. "acmeplumbing.com"
        company_name: Company name for context
        api_key: Hunter.io API key

    Returns:
        {"email": str, "first_name": str, "last_name": str,
         "confidence": int, "cost_usd": float}
    """
    params = {
        "domain": domain,
        "api_key": api_key,
        "limit": 5,
    }

    try:
        # Per-minute rate limiting
        now = time.monotonic()
        _hunter_call_timestamps[:] = [t for t in _hunter_call_timestamps if now - t < 60]
        if len(_hunter_call_timestamps) >= HUNTER_MAX_PER_MINUTE:
            wait_time = 60 - (now - _hunter_call_timestamps[0])
            logger.info("Hunter.io rate limit — waiting %.1fs", wait_time)
            await asyncio.sleep(wait_time)

        async with _hunter_semaphore:
            _hunter_call_timestamps.append(time.monotonic())
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{HUNTER_API_BASE}/domain-search", params=params)
                response.raise_for_status()
                data = response.json()

        emails = data.get("data", {}).get("emails", [])
        if not emails:
            logger.info("Hunter.io: no emails found for %s", domain)
            return {
                "email": None,
                "first_name": None,
                "last_name": None,
                "confidence": 0,
                "cost_usd": HUNTER_COST_PER_LOOKUP,
            }

        # Pick the highest confidence email
        best = max(emails, key=lambda e: e.get("confidence", 0))
        logger.info(
            "Hunter.io: found email for %s (confidence=%d)",
            domain, best.get("confidence", 0),
        )

        return {
            "email": best.get("value"),
            "first_name": best.get("first_name"),
            "last_name": best.get("last_name"),
            "confidence": best.get("confidence", 0),
            "cost_usd": HUNTER_COST_PER_LOOKUP,
        }

    except Exception as e:
        logger.error("Hunter.io lookup failed for %s: %s", domain, str(e))
        return {
            "email": None,
            "first_name": None,
            "last_name": None,
            "confidence": 0,
            "cost_usd": HUNTER_COST_PER_LOOKUP,
            "error": str(e),
        }


def guess_email_patterns(domain: str, name: Optional[str] = None) -> list[str]:
    """
    Generate likely email addresses based on common patterns.
    Used as fallback when Hunter.io doesn't find results.

    Args:
        domain: Business domain
        name: Optional contact name

    Returns:
        List of likely email addresses, ordered by likelihood
    """
    patterns = [
        f"info@{domain}",
        f"contact@{domain}",
        f"hello@{domain}",
        f"service@{domain}",
        f"sales@{domain}",
    ]

    if name:
        # Clean and split name
        parts = name.lower().strip().split()
        if len(parts) >= 2:
            first = re.sub(r"[^a-z]", "", parts[0])
            last = re.sub(r"[^a-z]", "", parts[-1])
            if first and last:
                patterns = [
                    f"{first}@{domain}",
                    f"{first}.{last}@{domain}",
                    f"{first[0]}{last}@{domain}",
                ] + patterns

    return patterns


def extract_domain(url: str) -> Optional[str]:
    """
    Extract clean domain from a URL.

    Args:
        url: Full URL string

    Returns:
        Domain string without www prefix, or None if invalid
    """
    if not url:
        return None

    try:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        # Strip www prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower() if domain else None
    except Exception:
        return None
