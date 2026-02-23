"""
Email discovery service — find real business emails through multi-source scraping.

Strategy chain (ordered by confidence):
1. Deep website scrape — 15+ paths, footer, JSON-LD structured data
2. Brave Search — find "@domain" mentions across the web
3. Enrichment candidates — name-based patterns from prospect research
4. Pattern guessing — generic patterns (info@, contact@) as last resort

Zero external verification API cost. Replaces the old pattern-guess-then-SMTP
approach (which fails when port 25 is blocked on the VPS).
"""
import json
import logging
import re
from typing import Optional
from urllib.parse import urlparse, urljoin, unquote

import httpx

from src.services.enrichment import (
    _EMAIL_REGEX,
    _IGNORE_EMAIL_DOMAINS,
    _is_valid_business_email,
    _is_safe_url,
    extract_domain,
    guess_email_patterns,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extended contact paths (beyond the original 5)
# ---------------------------------------------------------------------------
_EXTENDED_PATHS = [
    "/contact", "/contact-us", "/about", "/about-us", "/",
    "/team", "/our-team", "/staff", "/people", "/leadership",
    "/privacy", "/privacy-policy", "/terms",
]

# Paths for internal link crawling (skip these patterns)
_SKIP_LINK_PATTERNS = re.compile(
    r"(\.pdf|\.jpg|\.png|\.gif|\.css|\.js|\.zip|\.mp4|\.mp3|#|mailto:|tel:|javascript:)",
    re.IGNORECASE,
)

# JSON-LD email extraction
_JSON_LD_PATTERN = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

# Footer element extraction
_FOOTER_PATTERN = re.compile(
    r'<footer[^>]*>(.*?)</footer>',
    re.DOTALL | re.IGNORECASE,
)

# HTTP client settings
_TIMEOUT = 8.0
_MAX_PAGES = 15
_MAX_INTERNAL_LINKS = 8

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LeadLock/1.0; business contact lookup)",
    "Accept": "text/html,application/xhtml+xml",
}


# ---------------------------------------------------------------------------
# Core discovery orchestrator
# ---------------------------------------------------------------------------
async def discover_email(
    website: str,
    company_name: str,
    enrichment_data: Optional[dict] = None,
) -> dict:
    """
    Multi-strategy email discovery for a prospect.

    Returns:
        {
            "email": str|None,
            "source": str,  # "website_deep_scrape"|"brave_search"|"enrichment_candidate"|"pattern_guess"
            "confidence": str,  # "high"|"medium"|"low"
            "cost_usd": float,
        }
    """
    domain = extract_domain(website) if website else None

    # Strategy 1: Deep website scrape (high confidence)
    if website:
        try:
            scraped = await deep_scrape_website(website)
            if scraped:
                return {
                    "email": scraped[0],
                    "source": "website_deep_scrape",
                    "confidence": "high",
                    "cost_usd": 0.0,
                }
        except Exception as e:
            logger.warning("Deep scrape failed for %s: %s", domain or website, str(e))

    # Strategy 2: Brave Search for emails (medium confidence)
    if domain:
        try:
            brave_emails = await search_brave_for_email(domain)
            if brave_emails:
                return {
                    "email": brave_emails[0],
                    "source": "brave_search",
                    "confidence": "medium",
                    "cost_usd": 0.005,
                }
        except Exception as e:
            logger.debug("Brave search failed for %s: %s", domain, str(e))

    # Strategy 3: Use enrichment_data email_candidates (medium confidence)
    if enrichment_data and domain:
        candidates = enrichment_data.get("email_candidates", [])
        for candidate in candidates:
            if _is_valid_business_email(candidate, target_domain=domain):
                return {
                    "email": candidate,
                    "source": "enrichment_candidate",
                    "confidence": "medium",
                    "cost_usd": 0.0,
                }

    # Strategy 4: Pattern guessing (low confidence — last resort)
    if domain:
        patterns = guess_email_patterns(domain, name=company_name)
        if patterns:
            return {
                "email": patterns[0],
                "source": "pattern_guess",
                "confidence": "low",
                "cost_usd": 0.0,
            }

    return {
        "email": None,
        "source": None,
        "confidence": None,
        "cost_usd": 0.0,
    }


# ---------------------------------------------------------------------------
# Strategy 1: Deep website scrape
# ---------------------------------------------------------------------------
async def deep_scrape_website(website: str) -> list[str]:
    """
    Scrape a business website for contact emails using extended paths,
    footer parsing, JSON-LD structured data, and internal link crawling.

    Returns list of unique emails ordered by confidence (mailto > JSON-LD > footer > regex).
    """
    if not website:
        return []

    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"

    if not await _is_safe_url(website):
        logger.warning("SSRF protection blocked: %s", website)
        return []

    base = website.rstrip("/")
    target_domain = extract_domain(website)
    found_emails: list[str] = []
    seen: set[str] = set()
    pages_fetched = 0

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        max_redirects=3,
        headers=_HEADERS,
    ) as client:
        # Phase 1: Scrape extended paths
        for path in _EXTENDED_PATHS:
            if pages_fetched >= _MAX_PAGES:
                break
            url = f"{base}{path}" if path != "/" else base
            emails = await _fetch_and_extract(client, url, target_domain)
            pages_fetched += 1
            for email in emails:
                if email not in seen:
                    found_emails.append(email)
                    seen.add(email)

        # Phase 2: Crawl internal links from homepage (find pages we missed)
        if pages_fetched < _MAX_PAGES:
            homepage_html = await _fetch_html(client, base)
            if homepage_html:
                internal_links = _extract_internal_links(homepage_html, base)
                for link_url in internal_links[:_MAX_INTERNAL_LINKS]:
                    if pages_fetched >= _MAX_PAGES:
                        break
                    link_emails = await _fetch_and_extract(client, link_url, target_domain)
                    pages_fetched += 1
                    for email in link_emails:
                        if email not in seen:
                            found_emails.append(email)
                            seen.add(email)

    if found_emails:
        logger.info(
            "Deep scrape found %d email(s) for %s across %d pages",
            len(found_emails), target_domain or website, pages_fetched,
        )

    return found_emails


async def _fetch_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """Fetch a URL and return HTML content, or None on failure."""
    try:
        response = await client.get(url)
        if response.status_code != 200:
            return None
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return None
        return response.text
    except (httpx.HTTPError, httpx.InvalidURL, Exception):
        return None


async def _fetch_and_extract(
    client: httpx.AsyncClient,
    url: str,
    target_domain: Optional[str],
) -> list[str]:
    """Fetch a page and extract all emails using multiple strategies."""
    html = await _fetch_html(client, url)
    if not html:
        return []
    return _extract_all_emails(html, target_domain)


def _extract_all_emails(html: str, target_domain: Optional[str]) -> list[str]:
    """
    Extract emails from HTML using all available strategies:
    1. mailto: links (highest confidence)
    2. JSON-LD structured data
    3. Footer content
    4. Full-page regex
    """
    found: list[str] = []
    seen: set[str] = set()

    def _add(email: str):
        # URL-decode (mailto: links can be encoded, e.g. %20 for space)
        email_clean = unquote(email).lower().strip()
        # Reject if whitespace or control chars remain after decoding
        if " " in email_clean or "\t" in email_clean or "\n" in email_clean:
            return
        if email_clean not in seen and _is_valid_business_email(email_clean, target_domain):
            found.append(email_clean)
            seen.add(email_clean)

    # 1. mailto: links (highest confidence)
    for email in re.findall(
        r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html
    ):
        _add(email)

    # 2. JSON-LD structured data
    for email in _extract_json_ld_emails(html, target_domain):
        _add(email)

    # 3. Footer-specific extraction
    for email in _extract_footer_emails(html, target_domain):
        _add(email)

    # 4. Full-page regex (lowest confidence, most noise)
    for email in _EMAIL_REGEX.findall(html):
        _add(email)

    return found


def _extract_json_ld_emails(html: str, target_domain: Optional[str]) -> list[str]:
    """Extract emails from schema.org JSON-LD blocks (LocalBusiness, Organization, etc.)."""
    emails: list[str] = []
    for match in _JSON_LD_PATTERN.finditer(html):
        try:
            data = json.loads(match.group(1))
            _walk_json_for_emails(data, emails, target_domain)
        except (json.JSONDecodeError, ValueError):
            continue
    return emails


def _walk_json_for_emails(obj, emails: list[str], target_domain: Optional[str]):
    """Recursively walk JSON-LD data looking for email fields."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in ("email", "contactemail", "contact_email"):
                if isinstance(value, str) and "@" in value:
                    email = value.lower().strip().replace("mailto:", "")
                    if _is_valid_business_email(email, target_domain):
                        emails.append(email)
            elif key.lower() == "contactpoint" or key.lower() == "contact_point":
                _walk_json_for_emails(value, emails, target_domain)
            elif isinstance(value, (dict, list)):
                _walk_json_for_emails(value, emails, target_domain)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json_for_emails(item, emails, target_domain)


def _extract_footer_emails(html: str, target_domain: Optional[str]) -> list[str]:
    """Extract emails from <footer> elements — a very common location for contact info."""
    emails: list[str] = []
    for match in _FOOTER_PATTERN.finditer(html):
        footer_html = match.group(1)
        # mailto: in footer
        for email in re.findall(
            r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', footer_html
        ):
            email_lower = email.lower()
            if _is_valid_business_email(email_lower, target_domain):
                emails.append(email_lower)
        # Regex in footer text
        for email in _EMAIL_REGEX.findall(footer_html):
            email_lower = email.lower()
            if _is_valid_business_email(email_lower, target_domain):
                emails.append(email_lower)
    return emails


def _extract_internal_links(html: str, base_url: str) -> list[str]:
    """
    Extract unique internal links from HTML that might contain contact info.
    Prioritizes links with contact-relevant text.
    """
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower()

    # Find all href links
    all_links = re.findall(r'href=["\']([^"\']+)["\']', html)

    internal_links: list[str] = []
    seen_paths: set[str] = set()
    priority_links: list[str] = []
    other_links: list[str] = []

    # Known extended paths (already scraped)
    already_scraped = {p.rstrip("/") for p in _EXTENDED_PATHS}

    for href in all_links:
        if _SKIP_LINK_PATTERNS.search(href):
            continue

        # Resolve relative URLs
        if href.startswith("/"):
            full_url = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
        elif href.startswith("http"):
            # Only follow same-domain links
            link_parsed = urlparse(href)
            if link_parsed.netloc.lower() != base_domain:
                continue
            full_url = href
        else:
            continue

        # Normalize path for dedup
        path = urlparse(full_url).path.rstrip("/") or "/"
        if path in seen_paths or path in already_scraped:
            continue
        seen_paths.add(path)

        # Prioritize contact-relevant pages
        path_lower = path.lower()
        if any(kw in path_lower for kw in (
            "contact", "team", "staff", "about", "people", "email",
            "support", "help", "reach", "connect", "owner", "manager",
        )):
            priority_links.append(full_url)
        else:
            other_links.append(full_url)

    return priority_links + other_links


# ---------------------------------------------------------------------------
# Strategy 2: Brave Search for emails
# ---------------------------------------------------------------------------
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_COST_PER_SEARCH = 0.005


async def search_brave_for_email(domain: str) -> list[str]:
    """
    Search Brave for publicly listed emails at a domain.
    Queries: "@{domain}" to find pages mentioning emails at the domain.

    Returns list of unique valid emails found in search snippets.
    Cost: $0.005 per search.
    """
    from src.config import get_settings

    settings = get_settings()
    api_key = settings.brave_api_key
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                BRAVE_SEARCH_URL,
                params={
                    "q": f'"@{domain}" email contact',
                    "count": 10,
                },
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.debug("Brave search for %s emails failed: %s", domain, str(e))
        return []

    # Extract emails from search result descriptions and titles
    found: list[str] = []
    seen: set[str] = set()

    web_results = data.get("web", {}).get("results", [])
    for result in web_results:
        # Search in description and title
        text = f"{result.get('description', '')} {result.get('title', '')}"
        for email in _EMAIL_REGEX.findall(text):
            email_clean = unquote(email).lower().strip()
            if " " in email_clean or "\t" in email_clean:
                continue
            if email_clean not in seen and _is_valid_business_email(email_clean, target_domain=domain):
                found.append(email_clean)
                seen.add(email_clean)

    if found:
        logger.info("Brave search found %d email(s) for %s", len(found), domain)

    return found
