"""
Enrichment service - find business emails via website scraping and pattern guessing.
Zero external API cost. Scrapes contact pages for mailto: links and text emails,
falls back to common pattern guessing (info@, contact@, etc).
"""
import asyncio
import ipaddress
import logging
import re
import socket
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


_ALLOWED_SCHEMES = frozenset({"http", "https"})
_ALLOWED_PORTS = frozenset({None, 80, 443, 8080, 8443})
_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
    "metadata.google.internal", "169.254.169.254",
})


async def _is_safe_url(url: str) -> bool:
    """
    Validate that a URL doesn't target internal/private networks (SSRF protection).

    Resolves the hostname and checks all resolved IPs are globally routable.
    Blocks private, loopback, link-local, reserved, CGNAT, and multicast ranges.

    Note: DNS rebinding is a residual risk. Network-level egress controls blocking
    RFC-1918 ranges provide the strongest defense against that attack.
    """
    try:
        parsed = urlparse(url)

        # Allowlist schemes - reject file://, gopher://, etc.
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return False

        # Allowlist ports - reject non-standard ports used for service probing
        if parsed.port not in _ALLOWED_PORTS:
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Block known-bad hostnames before DNS resolution
        if hostname.lower() in _BLOCKED_HOSTNAMES:
            return False

        # Resolve hostname to IP and validate every returned address
        # Use run_in_executor to avoid blocking the event loop
        try:
            loop = asyncio.get_running_loop()
            addr_infos = await loop.run_in_executor(
                None, socket.getaddrinfo, hostname, None,
            )
        except socket.gaierror:
            return False

        for addr_info in addr_infos:
            ip_str = addr_info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                return False

            # Block any IP that is not globally routable or is multicast
            # This catches: private, loopback, link-local, reserved, CGNAT (100.64/10)
            if not ip.is_global or ip.is_multicast:
                logger.warning(
                    "SSRF blocked: %s resolves to non-public IP %s", hostname, ip_str,
                )
                return False

        return True
    except Exception as e:
        logger.debug("URL safety check failed for input: %s", str(e))
        return False


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
    except Exception as e:
        logger.debug("Failed to extract domain from URL: %s", str(e))
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

    # Reject emails with whitespace or URL-encoded artifacts
    if " " in email_lower or "\t" in email_lower or "%" in email_lower:
        return False

    email_domain = email_lower.split("@")[1] if "@" in email_lower else ""

    if email_domain in _IGNORE_EMAIL_DOMAINS:
        return False

    # Filter out noreply, automated, and unmonitored addresses
    local_part = email_lower.split("@")[0]
    unmonitored_patterns = (
        "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon",
        "notifications", "alerts", "automated", "bot", "robot",
        "postmaster", "webmaster", "hostmaster", "abuse",
    )
    if any(skip in local_part for skip in unmonitored_patterns):
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

    # SSRF protection: block requests to internal/private networks
    if not await _is_safe_url(website):
        logger.warning("SSRF protection blocked scrape of: %s", website)
        return []

    base = website.rstrip("/")
    target_domain = extract_domain(website)
    found_emails: list[str] = []
    seen: set[str] = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LeadLock/1.0; business contact lookup)",
        "Accept": "text/html,application/xhtml+xml",
    }

    _REDIRECT_CODES = {301, 302, 303, 307, 308}
    _MAX_REDIRECTS = 3

    async with httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=False,
        headers=headers,
    ) as client:
        for path in _CONTACT_PATHS:
            url = f"{base}{path}" if path != "/" else base
            try:
                # Follow redirects manually, re-checking SSRF on each hop
                current_url = url
                response = await client.get(current_url)
                for _ in range(_MAX_REDIRECTS):
                    if response.status_code not in _REDIRECT_CODES:
                        break
                    location = response.headers.get("location", "")
                    if not location:
                        response = None
                        break
                    # Resolve relative redirects against the current URL
                    if location.startswith("/"):
                        parsed_current = urlparse(current_url)
                        location = f"{parsed_current.scheme}://{parsed_current.netloc}{location}"
                    if not await _is_safe_url(location):
                        logger.warning("SSRF redirect blocked: %s -> %s", current_url, location)
                        response = None
                        break
                    current_url = location
                    response = await client.get(current_url)

                if response is None or response.status_code != 200:
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
    enrichment_data: Optional[dict] = None,
) -> dict:
    """
    Find a business email through multi-source discovery.

    Delegates to email_discovery.discover_email() which uses:
    1. Deep website scrape (15+ paths, JSON-LD, footer, internal links)
    2. Brave Search for "@domain" mentions
    3. Enrichment candidate emails from prospect research
    4. Pattern guessing as last resort

    Args:
        website: Business website URL
        company_name: Company name for context
        enrichment_data: Optional enrichment data with email_candidates

    Returns:
        {"email": str|None, "source": str, "verified": bool, "cost_usd": float}
    """
    from src.services.email_discovery import discover_email

    discovery = await discover_email(
        website=website,
        company_name=company_name,
        enrichment_data=enrichment_data,
    )

    return {
        "email": discovery.get("email"),
        "source": discovery.get("source"),
        "verified": discovery.get("confidence") == "high",
        "cost_usd": discovery.get("cost_usd", 0.0),
    }
