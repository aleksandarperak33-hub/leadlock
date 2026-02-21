"""
Metrics API - lead funnel, deliverability, cost tracking, response times.
Used by the admin dashboard for real-time monitoring.
"""
import logging
import uuid as uuid_mod
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case

from src.database import get_db
from src.api.dashboard import get_current_admin
from src.models.client import Client
from src.models.lead import Lead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


@router.get("/deliverability")
async def get_deliverability_metrics(admin: Client = Depends(get_current_admin)):
    """
    Get SMS deliverability metrics - delivery rates, reputation scores, per-number stats.
    This is the key endpoint for diagnosing reputation issues.
    """
    from src.services.deliverability import get_deliverability_summary
    return await get_deliverability_summary()


@router.get("/deliverability/{phone}")
async def get_number_reputation(phone: str, admin: Client = Depends(get_current_admin)):
    """Get reputation score for a specific Twilio number."""
    from src.services.deliverability import get_reputation_score
    return await get_reputation_score(phone)


@router.get("/funnel")
async def get_lead_funnel(
    client_id: str = Query(None),
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """
    Lead funnel metrics - count of leads in each state over a time period.
    Shows conversion rates through the pipeline.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    filters = [Lead.created_at >= cutoff]
    if client_id:
        try:
            cid = uuid_mod.UUID(client_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid client_id format")
        filters.append(Lead.client_id == cid)

    # Count leads by state
    result = await db.execute(
        select(
            Lead.state,
            func.count(Lead.id).label("count"),
        )
        .where(and_(*filters))
        .group_by(Lead.state)
    )
    states = {row.state: row.count for row in result}

    # Count total leads
    total = sum(states.values())

    # Calculate conversion rates
    intake_sent = states.get("intake_sent", 0)
    qualifying = states.get("qualifying", 0)
    qualified = states.get("qualified", 0)
    booking = states.get("booking", 0)
    booked = states.get("booked", 0)
    completed = states.get("completed", 0)
    cold = states.get("cold", 0)
    dead = states.get("dead", 0)
    opted_out = states.get("opted_out", 0)

    engaged = qualifying + qualified + booking + booked + completed
    converted = booked + completed

    return {
        "period_days": days,
        "total_leads": total,
        "states": states,
        "funnel": {
            "new": states.get("new", 0),
            "intake_sent": intake_sent,
            "qualifying": qualifying,
            "qualified": qualified,
            "booking": booking,
            "booked": booked,
            "completed": completed,
            "cold": cold,
            "dead": dead,
            "opted_out": opted_out,
        },
        "rates": {
            "engagement_rate": round(engaged / total, 4) if total > 0 else 0,
            "qualification_rate": round((qualified + booking + booked + completed) / total, 4) if total > 0 else 0,
            "conversion_rate": round(converted / total, 4) if total > 0 else 0,
            "opt_out_rate": round(opted_out / total, 4) if total > 0 else 0,
            "cold_rate": round((cold + dead) / total, 4) if total > 0 else 0,
        },
    }


@router.get("/response-times")
async def get_response_times(
    client_id: str = Query(None),
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """
    Response time metrics - how fast we're responding to leads.
    Target: <10 seconds for first response.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    filters = [
        Lead.created_at >= cutoff,
        Lead.first_response_ms.isnot(None),
    ]
    if client_id:
        try:
            cid = uuid_mod.UUID(client_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid client_id format")
        filters.append(Lead.client_id == cid)

    result = await db.execute(
        select(
            func.count(Lead.id).label("total"),
            func.avg(Lead.first_response_ms).label("avg_ms"),
            func.min(Lead.first_response_ms).label("min_ms"),
            func.max(Lead.first_response_ms).label("max_ms"),
            func.percentile_cont(0.5).within_group(Lead.first_response_ms).label("p50_ms"),
            func.percentile_cont(0.95).within_group(Lead.first_response_ms).label("p95_ms"),
            func.percentile_cont(0.99).within_group(Lead.first_response_ms).label("p99_ms"),
        ).where(and_(*filters))
    )
    row = result.one()

    # Count by bucket
    bucket_result = await db.execute(
        select(
            case(
                (Lead.first_response_ms < 10000, "under_10s"),
                (Lead.first_response_ms < 30000, "10s_to_30s"),
                (Lead.first_response_ms < 60000, "30s_to_60s"),
                else_="over_60s",
            ).label("bucket"),
            func.count(Lead.id).label("count"),
        )
        .where(and_(*filters))
        .group_by("bucket")
    )
    buckets = {r.bucket: r.count for r in bucket_result}

    total = row.total or 0
    under_10s = buckets.get("under_10s", 0)

    return {
        "period_days": days,
        "total_leads": total,
        "avg_ms": int(row.avg_ms or 0),
        "min_ms": int(row.min_ms or 0),
        "max_ms": int(row.max_ms or 0),
        "p50_ms": int(row.p50_ms or 0),
        "p95_ms": int(row.p95_ms or 0),
        "p99_ms": int(row.p99_ms or 0),
        "sla_met_rate": round(under_10s / total, 4) if total > 0 else 0,
        "buckets": buckets,
    }


@router.get("/costs")
async def get_cost_metrics(
    client_id: str = Query(None),
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """
    Cost tracking - SMS and AI costs aggregated by period.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    filters = [Lead.created_at >= cutoff]
    if client_id:
        try:
            cid = uuid_mod.UUID(client_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid client_id format")
        filters.append(Lead.client_id == cid)

    result = await db.execute(
        select(
            func.count(Lead.id).label("total_leads"),
            func.sum(Lead.total_sms_cost_usd).label("total_sms_cost"),
            func.sum(Lead.total_ai_cost_usd).label("total_ai_cost"),
            func.sum(Lead.total_messages_sent).label("total_messages_sent"),
            func.sum(Lead.total_messages_received).label("total_messages_received"),
        ).where(and_(*filters))
    )
    row = result.one()

    total_leads = row.total_leads or 0
    sms_cost = float(row.total_sms_cost or 0)
    ai_cost = float(row.total_ai_cost or 0)
    total_cost = sms_cost + ai_cost

    return {
        "period_days": days,
        "total_leads": total_leads,
        "total_cost_usd": round(total_cost, 4),
        "sms_cost_usd": round(sms_cost, 4),
        "ai_cost_usd": round(ai_cost, 4),
        "cost_per_lead_usd": round(total_cost / total_leads, 4) if total_leads > 0 else 0,
        "total_messages_sent": int(row.total_messages_sent or 0),
        "total_messages_received": int(row.total_messages_received or 0),
    }


@router.get("/health/workers")
async def get_worker_health(admin: Client = Depends(get_current_admin)):
    """Check health of all background workers via Redis heartbeats."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        workers = [
            "health_monitor",
            "retry_worker",
            "stuck_lead_sweeper",
            "crm_sync",
            "followup_scheduler",
            "deliverability_monitor",
            "booking_reminder",
            "lead_lifecycle",
        ]

        statuses = {}
        now = datetime.now(timezone.utc)

        for worker in workers:
            key = f"leadlock:worker_health:{worker}"
            last_heartbeat = await redis.get(key)
            if last_heartbeat:
                hb_str = last_heartbeat if isinstance(last_heartbeat, str) else last_heartbeat.decode()
                ts = datetime.fromisoformat(hb_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_seconds = (now - ts).total_seconds()
                statuses[worker] = {
                    "status": "healthy" if age_seconds < 600 else "stale",
                    "last_heartbeat": hb_str,
                    "age_seconds": int(age_seconds),
                }
            else:
                statuses[worker] = {
                    "status": "unknown",
                    "last_heartbeat": None,
                    "age_seconds": None,
                }

        return {"workers": statuses}
    except Exception as e:
        logger.error("Failed to check worker health: %s", str(e))
        return {"workers": {}, "error": "Failed to check worker health"}
