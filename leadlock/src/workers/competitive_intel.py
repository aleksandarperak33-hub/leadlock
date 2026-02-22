"""
Competitive intelligence worker - weekly scrape and analysis of competitor pages.

Analyzes 6 competitors for pricing, features, and positioning changes.
Generates battle cards for sales conversations.
"""
import asyncio
import logging
from datetime import datetime, timezone

from src.services.competitive_analysis import (
    COMPETITORS,
    analyze_competitor,
    get_previous_analysis,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 7 * 24 * 3600  # Weekly


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:competitive_intel",
            datetime.now(timezone.utc).isoformat(),
            ex=8 * 24 * 3600,
        )
    except Exception:
        pass


async def run_competitive_intel():
    """Main loop - analyze competitors weekly."""
    logger.info("Competitive intel worker started (poll every %ds)", POLL_INTERVAL_SECONDS)

    # Wait 30 minutes on startup
    await asyncio.sleep(1800)

    while True:
        try:
            if not await _should_run_this_week():
                logger.debug("Competitive intel: already ran this week")
            else:
                await competitive_intel_cycle()
        except Exception as e:
            logger.error("Competitive intel cycle error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _should_run_this_week() -> bool:
    """Check if analysis was already done this week."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        week_key = datetime.now(timezone.utc).strftime("%Y-W%W")
        ran_key = f"leadlock:competitive_intel:ran:{week_key}"
        return await redis.get(ran_key) is None
    except Exception:
        return True


async def competitive_intel_cycle():
    """Scrape and analyze all competitors."""
    logger.info("Competitive intel: starting weekly analysis of %d competitors", len(COMPETITORS))

    results = {"analyzed": 0, "errors": 0, "total_cost_usd": 0.0}

    for competitor in COMPETITORS:
        try:
            # Fetch page content
            page_content = await _fetch_page(competitor["url"])
            if not page_content:
                logger.warning("Failed to fetch %s page", competitor["name"])
                results["errors"] += 1
                continue

            # Get previous analysis for change detection
            previous = await get_previous_analysis(competitor["name"])

            # Analyze with AI
            result = await analyze_competitor(
                competitor_name=competitor["name"],
                competitor_url=competitor["url"],
                page_content=page_content,
                previous_summary=previous,
            )

            if result.get("error"):
                results["errors"] += 1
            else:
                results["analyzed"] += 1
                results["total_cost_usd"] += result.get("ai_cost_usd", 0.0)

                if result.get("has_changes"):
                    logger.info(
                        "Competitor %s has changes since last analysis",
                        competitor["name"],
                    )

        except Exception as e:
            logger.error("Failed to analyze %s: %s", competitor["name"], str(e))
            results["errors"] += 1

        await asyncio.sleep(5)  # Rate limit between competitors

    # Mark week complete
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        week_key = datetime.now(timezone.utc).strftime("%Y-W%W")
        await redis.set(f"leadlock:competitive_intel:ran:{week_key}", "1", ex=8 * 86400)
    except Exception:
        pass

    logger.info(
        "Competitive intel complete: analyzed=%d errors=%d cost=$%.4f",
        results["analyzed"], results["errors"], results["total_cost_usd"],
    )


async def _fetch_page(url: str) -> str:
    """Fetch a web page and return its text content."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; LeadLock-Intel/1.0)",
                },
            )
            response.raise_for_status()

            # Simple HTML to text: strip tags
            text = response.text
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:5000]  # Limit to 5000 chars

    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, str(e))
        return ""
