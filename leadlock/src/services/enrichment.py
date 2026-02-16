"""
Enrichment service — find business emails via website scraping and pattern guessing.
Zero external API cost. Scrapes contact pages for mailto: links and text emails,
falls back to common pattern guessing (info@, contact@, etc).
"""
import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Regex to find email addresses in page content
_EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

# Pages most likely to contain contact emails
_CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us", "/"]

# Domains that are never valid business emails
_IGNORE_EMAIL_DOMAINS = frozenset({
    "example.com", "sentry.io", "wixpress.com", "squarespace.com",
    "wordpress.com", "godaddy.com", "googleapis.com", "google.com",
    "facebook.com", "twitter.com", "instagram.com", "schema.org",
    "w3.org", "cloudflare.com", "jquery.com", "bootstrapcdn.com",
})


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
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower() if domain else None
    except Exception:
        return None


def guess_email_patterns(domain: str, name: Optional[str] = None) -> list[str]:
    """
    Generate likely email addresses based on common patterns.
    Used as fallback when website scraping doesn't find results.

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


def _is_valid_business_email(email: str, target_domain: Optional[str] = None) -> bool:
    """Check if an email looks like a real business contact email."""
    email_lower = email.lower()
    email_domain = email_lower.split("@")[1] if "@" in email_lower else ""

    if email_domain in _IGNORE_EMAIL_DOMAINS:
        return False

    # Filter out noreply / donotreply addresses
    local_part = email_lower.split("@")[0]
    if any(skip in local_part for skip in ("noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon")):
        return False

    # If we have a target domain, prefer emails matching that domain
    if target_domain and email_domain != target_domain:
        return False

    return True


async def scrape_contact_emails(website: str) -> list[str]:
    """
    Scrape a business website for contact email addresses.
    Fetches /contact, /about, and / pages, extracts emails from
    mailto: links and visible text via regex. 10s timeout per page.

    Args:
        website: Business website URL

    Returns:
        List of unique email addresses found, ordered by page priority
    """
    if not website:
        return []

    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"

    base = website.rstrip("/")
    target_domain = extract_domain(website)
    found_emails: list[str] = []
    seen: set[str] = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LeadLock/1.0; business contact lookup)",
        "Accept": "text/html,application/xhtml+xml",
    }

    async with httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=True,
        max_redirects=3,
        headers=headers,
    ) as client:
        for path in _CONTACT_PATHS:
            url = f"{base}{path}" if path != "/" else base
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    continue

                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    continue

                text = response.text

                # Extract from mailto: links first (higher confidence)
                mailto_emails = re.findall(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', text)
                for email in mailto_emails:
                    email_lower = email.lower()
                    if email_lower not in seen and _is_valid_business_email(email_lower, target_domain):
                        found_emails.append(email_lower)
                        seen.add(email_lower)

                # Extract from page text
                text_emails = _EMAIL_REGEX.findall(text)
                for email in text_emails:
                    email_lower = email.lower()
                    if email_lower not in seen and _is_valid_business_email(email_lower, target_domain):
                        found_emails.append(email_lower)
                        seen.add(email_lower)

            except (httpx.HTTPError, httpx.InvalidURL, Exception) as e:
                logger.debug("Failed to scrape %s: %s", url, str(e))
                continue

    if found_emails:
        logger.info(
            "Website scrape found %d email(s) for %s",
            len(found_emails), target_domain or website,
        )

    return found_emails


async def enrich_prospect_email(
    website: str,
    company_name: str,
) -> dict:
    """
    Find a business email through website scraping with pattern guess fallback.
    Zero external API cost.

    Strategy:
    1. Scrape website contact pages for emails
    2. Fall back to pattern guessing (info@domain, contact@domain)

    Args:
        website: Business website URL
        company_name: Company name for context

    Returns:
        {"email": str|None, "source": str, "verified": bool, "cost_usd": 0.0}
    """
    domain = extract_domain(website)

    # Strategy 1: Website scraping
    if website:
        try:
            scraped = await scrape_contact_emails(website)
            if scraped:
                return {
                    "email": scraped[0],
                    "source": "website_scrape",
                    "verified": False,
                    "cost_usd": 0.0,
                }
        except Exception as e:
            logger.warning("Website scrape failed for %s: %s", website, str(e))

    # Strategy 2: Pattern guessing
    if domain:
        patterns = guess_email_patterns(domain)
        if patterns:
            return {
                "email": patterns[0],
                "source": "pattern_guess",
                "verified": False,
                "cost_usd": 0.0,
            }

    return {
        "email": None,
        "source": None,
        "verified": False,
        "cost_usd": 0.0,
    }
