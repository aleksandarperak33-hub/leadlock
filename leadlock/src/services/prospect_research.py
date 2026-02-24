"""
Prospect researcher - finds decision-maker names and emails from business websites.

Visits team/about pages, uses Haiku to extract owner/manager names and titles,
generates email pattern candidates, and stores findings in Outreach.enrichment_data.

Cost: ~$0.001/prospect (1 Haiku call for name extraction).
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx

from src.services.enrichment import _is_safe_url, extract_domain

logger = logging.getLogger(__name__)

# Pages most likely to have team/leadership info
_TEAM_PATHS = [
    "/about", "/about-us", "/our-team", "/team", "/leadership",
    "/staff", "/meet-the-team", "/who-we-are", "/company",
]

# Max HTML to send to Haiku (keep costs low)
_MAX_HTML_LENGTH = 8000

_EXTRACTION_PROMPT = """Extract the owner, president, or general manager name and title from this business website page.

Rules:
- Only extract REAL person names (not company names)
- Prefer titles: Owner, President, Founder, General Manager, CEO
- If multiple people, pick the most senior one
- If no clear decision-maker is found, return null for both fields

Respond with ONLY valid JSON:
{{"name": "Mike Johnson", "title": "Owner"}}

If no decision-maker found:
{{"name": null, "title": null}}"""


def _clean_html_for_extraction(html: str) -> str:
    """
    Strip scripts, styles, and tags to get readable text for AI extraction.
    Keeps enough structure to identify names and titles.
    """
    # Remove script and style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # Replace tags with spaces
    text = re.sub(r'<[^>]+>', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:_MAX_HTML_LENGTH]


async def _fetch_team_page(website: str) -> tuple[Optional[str], str]:
    """
    Try to fetch team/about pages from a business website.

    Returns:
        (page_text, source_path) or (None, "") if no team page found.
    """
    if not website:
        return None, ""

    if not website.startswith(("http://", "https://")):
        website = f"https://{website}"

    if not await _is_safe_url(website):
        logger.warning("SSRF protection blocked research of: %s", website)
        return None, ""

    base = website.rstrip("/")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LeadLock/1.0; business research)",
        "Accept": "text/html,application/xhtml+xml",
    }

    async with httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=True,
        max_redirects=3,
        headers=headers,
    ) as client:
        for path in _TEAM_PATHS:
            url = f"{base}{path}"
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    continue

                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue

                text = _clean_html_for_extraction(response.text)

                # Quick heuristic: does this page mention people-like content?
                people_signals = [
                    "owner", "president", "founder", "manager", "ceo",
                    "team", "staff", "about us", "our story", "meet",
                ]
                text_lower = text.lower()
                if any(signal in text_lower for signal in people_signals):
                    return text, path

            except (httpx.HTTPError, httpx.InvalidURL, Exception) as e:
                logger.debug("Failed to fetch %s: %s", url, str(e))
                continue

    return None, ""


async def _extract_decision_maker(page_text: str) -> dict:
    """
    Use Haiku to extract decision-maker name and title from page text.

    Returns:
        {"name": str|None, "title": str|None, "ai_cost_usd": float}
    """
    import json
    from src.services.ai import generate_response

    result = await generate_response(
        system_prompt=_EXTRACTION_PROMPT,
        user_message=f"Website page content:\n\n{page_text}",
        model_tier="fast",
        max_tokens=50,
        temperature=0.0,
    )

    cost = result.get("cost_usd", 0.0)

    if result.get("error"):
        logger.warning("AI extraction failed: %s", result["error"])
        return {"name": None, "title": None, "ai_cost_usd": cost}

    try:
        content = result["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(content)
        return {
            "name": data.get("name"),
            "title": data.get("title"),
            "ai_cost_usd": cost,
        }
    except (json.JSONDecodeError, IndexError) as e:
        logger.warning("Failed to parse AI extraction: %s", str(e))
        return {"name": None, "title": None, "ai_cost_usd": cost}


def generate_email_candidates(domain: str, name: Optional[str] = None) -> list[str]:
    """
    Generate decision-maker email pattern candidates from a name and domain.

    Args:
        domain: Business domain (e.g., "acmehvac.com")
        name: Decision-maker full name (e.g., "Mike Johnson")

    Returns:
        List of email candidates ordered by likelihood.
    """
    if not domain or not name:
        return []

    parts = name.lower().strip().split()
    if not parts:
        return []

    # Clean name parts (remove non-alpha characters)
    cleaned = [re.sub(r"[^a-z]", "", p) for p in parts]
    cleaned = [p for p in cleaned if p]
    if not cleaned:
        return []

    first = cleaned[0]
    last = cleaned[-1] if len(cleaned) > 1 else ""

    candidates = [f"{first}@{domain}"]
    if last:
        candidates.extend([
            f"{first}.{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first}{last[0]}@{domain}",
            f"{first}_{last}@{domain}",
        ])

    return candidates


async def research_prospect(
    website: str,
    company_name: str,
    google_rating: Optional[float] = None,
    review_count: Optional[int] = None,
) -> dict:
    """
    Research a prospect's website to find decision-maker info.

    Visits team/about pages, extracts decision-maker name via AI,
    generates email candidates based on name patterns.

    Args:
        website: Business website URL
        company_name: Company name for context
        google_rating: Google rating if available
        review_count: Review count if available

    Returns:
        Enrichment data dict ready to store in Outreach.enrichment_data
    """
    enrichment = {
        "researched_at": datetime.now(timezone.utc).isoformat(),
        "research_source": None,
        "decision_maker_name": None,
        "decision_maker_title": None,
        "email_candidates": [],
        "website_summary": None,
        "ai_cost_usd": 0.0,
    }

    if not website:
        enrichment["research_source"] = "no_website"
        return enrichment

    # Step 1: Fetch team/about page
    page_text, source_path = await _fetch_team_page(website)

    if not page_text:
        enrichment["research_source"] = "no_team_page"
        return enrichment

    # Step 2: Extract decision-maker via Haiku
    extraction = await _extract_decision_maker(page_text)
    enrichment["ai_cost_usd"] = extraction["ai_cost_usd"]

    if extraction["name"]:
        enrichment["decision_maker_name"] = extraction["name"]
        enrichment["decision_maker_title"] = extraction.get("title")
        enrichment["research_source"] = "team_page"

        # Step 3: Generate email candidates
        domain = extract_domain(website)
        if domain:
            enrichment["email_candidates"] = generate_email_candidates(
                domain, extraction["name"],
            )
    else:
        enrichment["research_source"] = "team_page_no_match"

    # Build a brief website summary from the page text
    summary_text = page_text[:500].strip()
    if summary_text:
        enrichment["website_summary"] = summary_text

    # Include Google rating context if available
    if google_rating is not None:
        enrichment["google_rating"] = google_rating
    if review_count is not None:
        enrichment["review_count"] = review_count

    return enrichment
