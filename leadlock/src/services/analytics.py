"""
Analytics service - SQL aggregation queries for dashboard visualizations.
All queries computed on-demand with 5-minute Redis cache.
No AI calls. Pure SQL analytics.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.ab_test import ABTestExperiment, ABTestVariant

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutes


async def _cached_query(cache_key: str, query_fn, ttl: int = CACHE_TTL_SECONDS) -> dict:
    """Execute query with Redis caching."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        cached = await redis.get(f"leadlock:analytics:{cache_key}")
        if cached:
            raw = cached.decode() if isinstance(cached, bytes) else str(cached)
            return json.loads(raw)
    except Exception as e:
        logger.debug("Analytics cache read failed for %s: %s", cache_key, str(e))

    result = await query_fn()

    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            f"leadlock:analytics:{cache_key}",
            json.dumps(result, default=str),
            ex=ttl,
        )
    except Exception as e:
        logger.debug("Analytics cache write failed for %s: %s", cache_key, str(e))

    return result


async def get_trade_funnel(trade: Optional[str] = None) -> dict:
    """
    Per-trade conversion funnel: cold -> contacted -> demo_scheduled -> won.
    """
    cache_key = f"trade_funnel:{trade or 'all'}"

    async def _query():
        async with async_session_factory() as db:
            base_filter = []
            if trade:
                base_filter.append(Outreach.prospect_trade_type == trade)

            stages = ["cold", "contacted", "demo_scheduled", "demo_completed", "proposal_sent", "won", "lost"]
            counts = {}

            for status in stages:
                result = await db.execute(
                    select(func.count()).select_from(Outreach).where(
                        and_(
                            Outreach.status == status,
                            *base_filter,
                        )
                    )
                )
                counts[status] = result.scalar() or 0

            # Total prospects
            total_result = await db.execute(
                select(func.count()).select_from(Outreach).where(
                    and_(*base_filter) if base_filter else True
                )
            )
            total = total_result.scalar() or 0

            return {
                "trade": trade or "all",
                "total": total,
                "stages": counts,
            }

    return await _cached_query(cache_key, _query)


async def get_cost_per_lead(trade: Optional[str] = None) -> dict:
    """Cost-per-lead breakdown by trade."""
    cache_key = f"cost_per_lead:{trade or 'all'}"

    async def _query():
        async with async_session_factory() as db:
            base_filter = []
            if trade:
                base_filter.append(Outreach.prospect_trade_type == trade)

            result = await db.execute(
                select(
                    Outreach.prospect_trade_type,
                    func.count(Outreach.id).label("prospect_count"),
                    func.sum(Outreach.total_cost_usd).label("total_cost"),
                    func.avg(Outreach.total_cost_usd).label("avg_cost"),
                ).where(
                    and_(*base_filter) if base_filter else True
                ).group_by(Outreach.prospect_trade_type)
            )
            rows = result.fetchall()

            return {
                "by_trade": [
                    {
                        "trade": row[0] or "unknown",
                        "prospect_count": row[1],
                        "total_cost_usd": round(float(row[2] or 0), 4),
                        "avg_cost_per_lead": round(float(row[3] or 0), 4),
                    }
                    for row in rows
                ],
            }

    return await _cached_query(cache_key, _query)


async def get_email_performance_by_step() -> dict:
    """Email open/reply rates broken down by sequence step."""
    cache_key = "email_perf_by_step"

    async def _query():
        async with async_session_factory() as db:
            result = await db.execute(
                select(
                    OutreachEmail.sequence_step,
                    func.count(OutreachEmail.id).label("total_sent"),
                    func.count(OutreachEmail.opened_at).label("total_opened"),
                    func.count(
                        case(
                            (OutreachEmail.direction == "inbound", OutreachEmail.id),
                        )
                    ).label("total_replied"),
                ).where(
                    OutreachEmail.direction == "outbound",
                ).group_by(OutreachEmail.sequence_step).order_by(
                    OutreachEmail.sequence_step
                )
            )
            rows = result.fetchall()

            steps = []
            for row in rows:
                sent = row[1] or 0
                opened = row[2] or 0
                steps.append({
                    "step": row[0],
                    "total_sent": sent,
                    "total_opened": opened,
                    "open_rate": round(opened / sent, 4) if sent > 0 else 0.0,
                    "total_replied": row[3] or 0,
                    "reply_rate": round((row[3] or 0) / sent, 4) if sent > 0 else 0.0,
                })

            return {"steps": steps}

    return await _cached_query(cache_key, _query)


async def get_ab_test_results() -> dict:
    """Get all A/B test experiments with variant performance."""
    cache_key = "ab_test_results"

    async def _query():
        async with async_session_factory() as db:
            experiments_result = await db.execute(
                select(ABTestExperiment).order_by(ABTestExperiment.created_at.desc()).limit(20)
            )
            experiments = experiments_result.scalars().all()

            results = []
            for exp in experiments:
                variants_result = await db.execute(
                    select(ABTestVariant).where(
                        ABTestVariant.experiment_id == exp.id
                    ).order_by(ABTestVariant.variant_label)
                )
                variants = variants_result.scalars().all()

                results.append({
                    "id": str(exp.id),
                    "name": exp.name,
                    "status": exp.status,
                    "sequence_step": exp.sequence_step,
                    "target_trade": exp.target_trade,
                    "created_at": exp.created_at.isoformat() if exp.created_at else None,
                    "completed_at": exp.completed_at.isoformat() if exp.completed_at else None,
                    "variants": [
                        {
                            "id": str(v.id),
                            "label": v.variant_label,
                            "instruction": v.subject_instruction[:100],
                            "total_sent": v.total_sent,
                            "total_opened": v.total_opened,
                            "total_replied": v.total_replied,
                            "open_rate": round(v.open_rate, 4),
                            "is_winner": v.is_winner,
                        }
                        for v in variants
                    ],
                })

            return {"experiments": results}

    return await _cached_query(cache_key, _query)


async def get_pipeline_waterfall() -> dict:
    """Outreach pipeline waterfall showing progression through stages."""
    cache_key = "pipeline_waterfall"

    async def _query():
        async with async_session_factory() as db:
            # Count by status
            result = await db.execute(
                select(
                    Outreach.status,
                    func.count(Outreach.id).label("count"),
                ).group_by(Outreach.status)
            )
            rows = result.fetchall()

            return {
                "stages": {row[0]: row[1] for row in rows},
            }

    return await _cached_query(cache_key, _query)


async def get_agent_costs(days: int = 7) -> dict:
    """Get per-agent AI cost breakdown from Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        costs_by_agent: dict[str, float] = {}
        daily_costs: list[dict] = []

        for i in range(days):
            date = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
            hash_key = f"leadlock:agent_costs:{date}"
            day_costs = await redis.hgetall(hash_key)

            day_data = {"date": date}
            for agent_bytes, cost_bytes in day_costs.items():
                agent = agent_bytes.decode() if isinstance(agent_bytes, bytes) else str(agent_bytes)
                cost = float(cost_bytes.decode() if isinstance(cost_bytes, bytes) else cost_bytes)
                day_data[agent] = round(cost, 6)
                costs_by_agent[agent] = costs_by_agent.get(agent, 0.0) + cost

            daily_costs.append(day_data)

        return {
            "period_days": days,
            "total_by_agent": {k: round(v, 6) for k, v in costs_by_agent.items()},
            "total_usd": round(sum(costs_by_agent.values()), 4),
            "daily": list(reversed(daily_costs)),
        }
    except Exception as e:
        logger.warning("Failed to get agent costs: %s", str(e))
        return {"period_days": days, "total_by_agent": {}, "total_usd": 0.0, "daily": []}
