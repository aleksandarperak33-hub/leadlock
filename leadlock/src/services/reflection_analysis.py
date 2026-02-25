"""
Reflection analysis service - Sonnet-powered weekly performance review.
Analyzes all agent performance and proposes improvements.
"""
import json
import logging
from typing import Optional

from src.services.ai import generate_response, parse_json_content
from src.utils.agent_cost import track_agent_cost
from src.database import async_session_factory
from src.models.agent_regression import AgentRegression

logger = logging.getLogger(__name__)

REFLECTION_PROMPT = """You are the Reflection Agent for LeadLock's agent army.
Review the following weekly performance data and provide analysis.

PERFORMANCE DATA:
{performance_data}

Analyze:
1. A/B TEST RESULTS: Which angles/approaches worked? What should we test next?
2. EMAIL PERFORMANCE: Which trades/steps have best open and reply rates?
3. WIN-BACK EFFECTIVENESS: Which angles got the best response?
4. COST EFFICIENCY: Any agents spending more than expected?
5. REGRESSIONS: Any metrics that got worse compared to previous periods?
6. WINNING PATTERNS: Extract specific subject line instructions that demonstrably work.

For each regression found, output a structured entry.
For each winning pattern found, output a structured entry with the instruction that works.

Output valid JSON:
{{
  "summary": "1-2 sentence executive summary",
  "ab_test_insights": "...",
  "email_insights": "...",
  "winback_insights": "...",
  "cost_insights": "...",
  "regressions": [
    {{"agent_name": "...", "text": "...", "severity": "info|warning|critical"}}
  ],
  "winning_patterns": [
    {{"instruction": "...", "trade": "hvac|plumbing|roofing|null", "step": 1, "open_rate": 0.35, "reason": "..."}}
  ],
  "recommendations": ["...", "...", "..."]
}}"""


async def run_reflection_analysis(performance_data: dict) -> dict:
    """
    Run weekly reflection analysis on all agent performance.

    Args:
        performance_data: Aggregated metrics from all agents

    Returns:
        Analysis results with regressions and recommendations
    """
    result = await generate_response(
        system_prompt="You are a performance analyst for an AI agent system.",
        user_message=REFLECTION_PROMPT.format(
            performance_data=json.dumps(performance_data, indent=2, default=str),
        ),
        model_tier="smart",
        max_tokens=1000,
        temperature=0.3,
    )

    ai_cost = result.get("cost_usd", 0.0)
    await track_agent_cost("reflection", ai_cost)

    if result.get("error"):
        logger.error("Reflection analysis failed: %s", result["error"])
        return {"error": result["error"], "ai_cost_usd": ai_cost}

    parsed, parse_error = parse_json_content(result.get("content", ""))
    if parse_error or not isinstance(parsed, dict):
        err = parse_error or f"Expected JSON object, got {type(parsed).__name__}"
        logger.error("Failed to parse reflection analysis: %s", err)
        return {"error": f"JSON parse error: {err}", "ai_cost_usd": ai_cost}

    # Store regressions in DB
    regressions = parsed.get("regressions", [])
    if regressions:
        async with async_session_factory() as db:
            for reg in regressions:
                regression = AgentRegression(
                    agent_name=reg.get("agent_name", "unknown"),
                    regression_text=reg.get("text", ""),
                    severity=reg.get("severity", "info"),
                )
                db.add(regression)
            await db.commit()

        logger.info("Reflection: stored %d regressions", len(regressions))

    # Store discovered winning patterns via intelligence loop
    winning_patterns = parsed.get("winning_patterns", [])
    if winning_patterns:
        try:
            from src.services.winning_patterns import store_winning_pattern

            stored_count = 0
            for wp in winning_patterns:
                instruction = wp.get("instruction", "").strip()
                if not instruction:
                    continue
                trade = wp.get("trade")
                if trade == "null" or trade == "None":
                    trade = None
                await store_winning_pattern(
                    source="reflection",
                    instruction_text=instruction,
                    trade=trade,
                    step=wp.get("step"),
                    open_rate=float(wp.get("open_rate", 0.0)),
                    sample_size=0,  # Reflection-derived, no direct sample
                )
                stored_count += 1

            if stored_count:
                logger.info("Reflection: stored %d winning patterns", stored_count)
        except Exception as wp_err:
            logger.warning("Failed to store reflection winning patterns: %s", str(wp_err))

    # Cache latest insights summary in Redis for fast reads
    summary = parsed.get("summary", "")
    if summary:
        try:
            from src.utils.dedup import get_redis

            redis = await get_redis()
            cache_data = json.dumps({
                "summary": summary,
                "recommendations": parsed.get("recommendations", []),
                "patterns_count": len(winning_patterns),
                "regressions_count": len(regressions),
            })
            await redis.set(
                "leadlock:reflection:latest_insights",
                cache_data,
                ex=8 * 86400,  # 8-day TTL
            )
            logger.info("Reflection: cached insights summary in Redis")
        except Exception as cache_err:
            logger.debug("Failed to cache reflection insights: %s", str(cache_err))

    return {
        "summary": summary,
        "insights": {
            "ab_test": parsed.get("ab_test_insights"),
            "email": parsed.get("email_insights"),
            "winback": parsed.get("winback_insights"),
            "cost": parsed.get("cost_insights"),
        },
        "regressions": regressions,
        "winning_patterns": winning_patterns,
        "recommendations": parsed.get("recommendations", []),
        "ai_cost_usd": ai_cost,
    }

