"""
Competitive analysis service - scrapes and analyzes competitor pages.
Uses Sonnet for deeper analysis of pricing, features, and positioning.
"""
import json
import logging
from typing import Optional

from src.services.ai import generate_response
from src.database import async_session_factory
from src.models.competitive_intel import CompetitiveIntel

logger = logging.getLogger(__name__)

COMPETITORS = [
    {"name": "ServiceTitan", "url": "https://www.servicetitan.com/pricing"},
    {"name": "Hatch", "url": "https://www.usehatchapp.com/pricing"},
    {"name": "Podium", "url": "https://www.podium.com/pricing/"},
    {"name": "Housecall Pro", "url": "https://www.housecallpro.com/pricing/"},
    {"name": "GoHighLevel", "url": "https://www.gohighlevel.com/pricing"},
    {"name": "Jobber", "url": "https://getjobber.com/pricing/"},
]

ANALYSIS_PROMPT = """Analyze this competitor's pricing page content for a competitive intelligence report.

Competitor: {competitor_name}
URL: {competitor_url}

Page content (may be partial):
{page_content}

Previous analysis summary (for change detection):
{previous_summary}

Provide a structured analysis:
1. PRICING: Extract all visible pricing tiers, features per tier, and any hidden costs
2. FEATURES: Key features highlighted, especially related to lead response/management
3. POSITIONING: How they position themselves (target market, main value prop, messaging tone)
4. CHANGES: What changed since the previous analysis (if any)
5. BATTLE CARD: 3-4 bullet points on how LeadLock differentiates (sub-60s response, AI-powered, lower cost)

Output valid JSON:
{{
  "pricing_summary": "...",
  "features_summary": "...",
  "positioning_summary": "...",
  "changes_from_previous": "...",
  "battle_card": "..."
}}"""


async def analyze_competitor(
    competitor_name: str,
    competitor_url: str,
    page_content: str,
    previous_summary: Optional[str] = None,
) -> dict:
    """
    Analyze a competitor's page content using AI.

    Returns:
        Analysis dict with pricing, features, positioning, battle card.
    """
    result = await generate_response(
        system_prompt="You are a competitive intelligence analyst for a B2B SaaS company.",
        user_message=ANALYSIS_PROMPT.format(
            competitor_name=competitor_name,
            competitor_url=competitor_url,
            page_content=page_content[:3000],  # Limit content length
            previous_summary=previous_summary or "No previous analysis available.",
        ),
        model_tier="smart",
        max_tokens=1000,
        temperature=0.3,
    )

    ai_cost = result.get("cost_usd", 0.0)
    await _track_agent_cost("competitive_intel", ai_cost)

    if result.get("error"):
        logger.error("Competitor analysis failed for %s: %s", competitor_name, result["error"])
        return {"error": result["error"], "ai_cost_usd": ai_cost}

    try:
        content = result["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error("Failed to parse competitor analysis: %s", str(e))
        return {"error": f"JSON parse error: {str(e)}", "ai_cost_usd": ai_cost}

    # Store in DB
    async with async_session_factory() as db:
        intel = CompetitiveIntel(
            competitor_name=competitor_name,
            competitor_url=competitor_url,
            pricing_summary=parsed.get("pricing_summary"),
            features_summary=parsed.get("features_summary"),
            positioning_summary=parsed.get("positioning_summary"),
            battle_card=parsed.get("battle_card"),
            changes_from_previous=parsed.get("changes_from_previous"),
            raw_analysis=parsed,
            ai_cost_usd=ai_cost,
        )
        db.add(intel)
        await db.commit()

        return {
            "intel_id": str(intel.id),
            "competitor": competitor_name,
            "ai_cost_usd": ai_cost,
            "has_changes": bool(parsed.get("changes_from_previous", "").strip()),
        }


async def get_previous_analysis(competitor_name: str) -> Optional[str]:
    """Get the most recent analysis summary for a competitor."""
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(CompetitiveIntel).where(
                CompetitiveIntel.competitor_name == competitor_name
            ).order_by(CompetitiveIntel.created_at.desc()).limit(1)
        )
        intel = result.scalar_one_or_none()
        if not intel:
            return None

        return (
            f"Pricing: {intel.pricing_summary or 'N/A'}\n"
            f"Features: {intel.features_summary or 'N/A'}\n"
            f"Positioning: {intel.positioning_summary or 'N/A'}"
        )


async def _track_agent_cost(agent_name: str, cost_usd: float) -> None:
    """Track per-agent AI cost in Redis hash."""
    if cost_usd <= 0:
        return
    try:
        from src.utils.dedup import get_redis
        from datetime import datetime, timezone
        redis = await get_redis()
        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hash_key = f"leadlock:agent_costs:{date_key}"
        await redis.hincrbyfloat(hash_key, agent_name, cost_usd)
        await redis.expire(hash_key, 30 * 86400)
    except Exception:
        pass
