"""
Reflection analysis service - Sonnet-powered weekly performance review.
Analyzes all agent performance and proposes improvements.
"""
import json
import logging
from typing import Optional

from src.services.ai import generate_response
from src.database import async_session_factory
from src.models.agent_regression import AgentRegression

logger = logging.getLogger(__name__)

REFLECTION_PROMPT = """You are the Reflection Agent for LeadLock's agent army.
Review the following weekly performance data and provide analysis.

PERFORMANCE DATA:
{performance_data}

Analyze:
1. A/B TEST RESULTS: Which angles/approaches worked? What should we test next?
2. CONTENT QUALITY: Any content types consistently underperforming?
3. WIN-BACK EFFECTIVENESS: Which angles got the best response?
4. COST EFFICIENCY: Any agents spending more than expected?
5. REGRESSIONS: Any metrics that got worse compared to previous periods?

For each regression found, output a structured entry.

Output valid JSON:
{{
  "summary": "1-2 sentence executive summary",
  "ab_test_insights": "...",
  "content_insights": "...",
  "winback_insights": "...",
  "cost_insights": "...",
  "regressions": [
    {{"agent_name": "...", "text": "...", "severity": "info|warning|critical"}}
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
        max_tokens=1500,
        temperature=0.3,
    )

    ai_cost = result.get("cost_usd", 0.0)
    await _track_agent_cost("reflection", ai_cost)

    if result.get("error"):
        logger.error("Reflection analysis failed: %s", result["error"])
        return {"error": result["error"], "ai_cost_usd": ai_cost}

    try:
        content = result["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error("Failed to parse reflection analysis: %s", str(e))
        return {"error": f"JSON parse error: {str(e)}", "ai_cost_usd": ai_cost}

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

    return {
        "summary": parsed.get("summary", ""),
        "insights": {
            "ab_test": parsed.get("ab_test_insights"),
            "content": parsed.get("content_insights"),
            "winback": parsed.get("winback_insights"),
            "cost": parsed.get("cost_insights"),
        },
        "regressions": regressions,
        "recommendations": parsed.get("recommendations", []),
        "ai_cost_usd": ai_cost,
    }


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
