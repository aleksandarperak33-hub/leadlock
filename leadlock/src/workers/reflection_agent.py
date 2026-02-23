"""
Reflection agent worker - daily review of all agent performance.
Skeleton per AgentOS spec. Proposes SOUL.md improvements and logs regressions.

Changed from weekly (604,800s) to daily (86,400s) so winning patterns
flow into outreach within 24h instead of 7 days.
"""
import asyncio
import logging
from datetime import datetime, timezone

from src.services.analytics import (
    get_ab_test_results,
    get_email_performance_by_step,
    get_agent_costs,
    get_pipeline_waterfall,
)
from src.services.reflection_analysis import run_reflection_analysis

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 86400  # Daily


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:reflection_agent",
            datetime.now(timezone.utc).isoformat(),
            ex=2 * 86400,
        )
    except Exception as e:
        logger.debug("Heartbeat write failed: %s", str(e))


async def run_reflection_agent():
    """Main loop - run daily reflection."""
    logger.info("Reflection agent started (poll every %ds)", POLL_INTERVAL_SECONDS)

    # Wait 1 hour on startup
    await asyncio.sleep(3600)

    while True:
        await _heartbeat()
        try:
            if not await _should_run_today():
                logger.debug("Reflection agent: already ran today")
            else:
                await reflection_cycle()
        except Exception as e:
            logger.error("Reflection agent cycle error: %s", str(e))

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _should_run_today() -> bool:
    """Check if reflection was already done today."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ran_key = f"leadlock:reflection:ran:{date_key}"
        return await redis.get(ran_key) is None
    except Exception as e:
        logger.debug("Reflection schedule check failed: %s", str(e))
        return True


async def reflection_cycle():
    """Gather all agent metrics and run reflection analysis."""
    logger.info("Reflection agent: starting daily analysis")

    # Gather performance data from all agents
    performance_data = {}

    try:
        performance_data["ab_tests"] = await get_ab_test_results()
    except Exception as e:
        logger.warning("Reflection: failed to get A/B test data: %s", str(e))

    try:
        performance_data["email_performance"] = await get_email_performance_by_step()
    except Exception as e:
        logger.warning("Reflection: failed to get email performance: %s", str(e))

    try:
        performance_data["agent_costs"] = await get_agent_costs(days=7)
    except Exception as e:
        logger.warning("Reflection: failed to get agent costs: %s", str(e))

    try:
        performance_data["pipeline"] = await get_pipeline_waterfall()
    except Exception as e:
        logger.warning("Reflection: failed to get pipeline data: %s", str(e))

    # Run AI analysis
    result = await run_reflection_analysis(performance_data)

    if result.get("error"):
        logger.error("Reflection analysis failed: %s", result["error"])
        return

    # Log summary
    logger.info(
        "Reflection complete: %s | %d regressions | %d recommendations | cost=$%.4f",
        result.get("summary", "N/A")[:100],
        len(result.get("regressions", [])),
        len(result.get("recommendations", [])),
        result.get("ai_cost_usd", 0.0),
    )

    # Mark day complete
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await redis.set(f"leadlock:reflection:ran:{date_key}", "1", ex=2 * 86400)
    except Exception as e:
        logger.debug("Reflection ran-marker write failed: %s", str(e))
