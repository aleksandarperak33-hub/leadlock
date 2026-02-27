"""
Dashboard reports, metrics, activity, compliance, settings, onboarding, and bookings.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, case, text

from src.database import get_db
from src.api.dash_auth import get_current_client
from src.api.dash_phone import _mask_ein
from src.models.lead import Lead
from src.models.client import Client
from src.models.booking import Booking
from src.models.consent import ConsentRecord
from src.models.event_log import EventLog
from src.models.followup import FollowupTask
from src.schemas.api_responses import (
    DashboardMetrics,
    ActivityEvent,
    ComplianceSummary,
)
from src.services.reporting import get_dashboard_metrics

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


# === METRICS ===

@router.get("/api/v1/dashboard/metrics", response_model=DashboardMetrics)
async def get_metrics(
    period: str = Query(default="7d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get aggregated KPI metrics for the dashboard."""
    return await get_dashboard_metrics(db, str(client.id), period)


# === ACTIVITY ===

@router.get("/api/v1/dashboard/activity")
async def get_activity(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get recent activity feed."""
    result = await db.execute(
        select(EventLog)
        .where(EventLog.client_id == client.id)
        .order_by(desc(EventLog.created_at))
        .limit(limit)
    )
    events = result.scalars().all()

    activity = []
    for e in events:
        event_type = "lead_created"
        if "sms_sent" in (e.action or ""):
            event_type = "sms_sent"
        elif "sms_received" in (e.action or ""):
            event_type = "sms_received"
        elif "booking" in (e.action or ""):
            event_type = "booking_confirmed"
        elif "opt_out" in (e.action or ""):
            event_type = "opt_out"
        elif "intake" in (e.action or ""):
            event_type = "sms_sent"

        activity.append(ActivityEvent(
            type=event_type,
            lead_id=str(e.lead_id) if e.lead_id else None,
            message=e.message or e.action,
            timestamp=e.created_at,
        ))

    return activity


# === REPORTS ===

@router.get("/api/v1/dashboard/reports/weekly")
async def get_weekly_report(
    week: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get weekly report data."""
    # Default to current week
    metrics = await get_dashboard_metrics(db, str(client.id), "7d")
    return metrics


# === SETTINGS ===

@router.get("/api/v1/dashboard/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get current client configuration."""
    return {
        "business_name": client.business_name,
        "trade_type": client.trade_type,
        "tier": client.tier,
        "twilio_phone": client.twilio_phone,
        "ten_dlc_status": client.ten_dlc_status,
        "crm_type": client.crm_type,
        "config": client.config,
        "email_verified": getattr(client, 'email_verified', True),
        "billing_status": client.billing_status,
        "twilio_messaging_service_sid": client.twilio_messaging_service_sid,
        "business_website": client.business_website,
        "business_type": client.business_type,
        "business_ein": _mask_ein(client.business_ein),
        "business_address": client.business_address,
    }


@router.get("/api/v1/dashboard/readiness")
async def check_readiness(
    client: Client = Depends(get_current_client),
):
    """Check if client is fully configured and ready to receive leads."""
    config = client.config or {}
    checks = {
        "phone_provisioned": bool(client.twilio_phone),
        "billing_active": client.billing_status in ("active", "pilot", "trial"),
        "services_configured": bool(config.get("services", {}).get("primary")),
        "persona_set": bool(config.get("persona", {}).get("rep_name")),
        "crm_connected": client.crm_type != "google_sheets" or bool(client.crm_api_key_encrypted),
    }
    return {
        "ready": all([
            checks["phone_provisioned"],
            checks["billing_active"],
            checks["services_configured"],
            checks["persona_set"],
        ]),
        "checks": checks,
    }


@router.put("/api/v1/dashboard/settings")
async def update_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Update client configuration."""
    try:
        body = await request.body()
        if len(body) > 51200:  # 50KB max
            raise HTTPException(status_code=413, detail="Payload too large (max 50KB)")
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    except HTTPException:
        raise

    if "config" in payload:
        if not isinstance(payload["config"], dict):
            raise HTTPException(status_code=400, detail="config must be a JSON object")
        # Merge with existing config instead of overwriting to prevent data loss
        existing = client.config or {}
        client.config = {**existing, **payload["config"]}
    await db.commit()
    return {"status": "updated"}


@router.post("/api/v1/dashboard/onboarding")
async def complete_onboarding(
    request: Request,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Save onboarding configuration and mark client as onboarded."""
    try:
        body = await request.body()
        if len(body) > 51200:
            raise HTTPException(status_code=413, detail="Payload too large (max 50KB)")
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    except HTTPException:
        raise

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    if "config" in payload:
        if not isinstance(payload["config"], dict):
            raise HTTPException(status_code=400, detail="config must be a JSON object")

    if "config" in payload:
        existing = client.config or {}
        merged = {**existing, **payload["config"]}
        client.config = merged

    if "crm_type" in payload and payload["crm_type"]:
        client.crm_type = payload["crm_type"]

    if "crm_tenant_id" in payload and payload["crm_tenant_id"]:
        client.crm_tenant_id = payload["crm_tenant_id"]

    if "crm_api_key" in payload and payload["crm_api_key"]:
        from src.utils.encryption import encrypt_value
        client.crm_api_key_encrypted = encrypt_value(payload["crm_api_key"])

    # Save business registration info if provided (for later 10DLC submission)
    _valid_business_types = {"sole_proprietorship", "llc", "corporation", "partnership"}
    if payload.get("business_type"):
        if payload["business_type"] not in _valid_business_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid business_type. Must be one of: {', '.join(sorted(_valid_business_types))}",
            )
        client.business_type = payload["business_type"]
    if payload.get("business_ein"):
        client.business_ein = payload["business_ein"]
    if payload.get("business_website"):
        client.business_website = payload["business_website"]
    if payload.get("business_address"):
        client.business_address = payload["business_address"]

    # Allow partial saves during onboarding; only go live when explicitly requested
    go_live = payload.get("go_live", False)
    if go_live:
        client.onboarding_status = "live"
    elif client.onboarding_status == "pending":
        client.onboarding_status = "in_progress"

    await db.commit()
    logger.info(
        "Onboarding %s for client %s",
        "completed" if go_live else "updated",
        client.business_name,
    )
    return {"status": "onboarded" if go_live else "saved", "client_id": str(client.id)}


# === COMPLIANCE ===

@router.get("/api/v1/dashboard/compliance/summary", response_model=ComplianceSummary)
async def get_compliance_summary(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get compliance health check summary."""
    # Total consent records
    consent_count = (await db.execute(
        select(func.count(ConsentRecord.id)).where(ConsentRecord.client_id == client.id)
    )).scalar() or 0

    # Opted out count
    opted_out_count = (await db.execute(
        select(func.count(ConsentRecord.id)).where(
            and_(ConsentRecord.client_id == client.id, ConsentRecord.opted_out == True)
        )
    )).scalar() or 0

    # Pending followups
    pending_followups = (await db.execute(
        select(func.count(FollowupTask.id)).where(
            and_(FollowupTask.client_id == client.id, FollowupTask.status == "pending")
        )
    )).scalar() or 0

    return ComplianceSummary(
        total_consent_records=consent_count,
        opted_out_count=opted_out_count,
        messages_in_quiet_hours=0,
        cold_outreach_violations=0,
        pending_followups=pending_followups,
        last_audit=datetime.now(timezone.utc),
    )


@router.get("/api/v1/dashboard/compliance/details")
async def get_compliance_details(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get detailed compliance breakdown — consent records, opt-outs, quiet hours, cold outreach."""
    cid = client.id
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Consent records by type
    consent_type_result = await db.execute(
        select(ConsentRecord.consent_type, func.count(ConsentRecord.id))
        .where(ConsentRecord.client_id == cid)
        .group_by(ConsentRecord.consent_type)
    )
    consent_by_type = {row[0]: row[1] for row in consent_type_result.all()}

    # Recent opt-outs (last 30d)
    recent_optouts = (await db.execute(
        select(func.count(ConsentRecord.id)).where(
            and_(
                ConsentRecord.client_id == cid,
                ConsentRecord.opted_out == True,
                ConsentRecord.updated_at >= thirty_days_ago,
            )
        )
    )).scalar() or 0

    # All-time opt-outs
    total_optouts = (await db.execute(
        select(func.count(ConsentRecord.id)).where(
            and_(ConsentRecord.client_id == cid, ConsentRecord.opted_out == True)
        )
    )).scalar() or 0

    # Total consent records
    total_consent = (await db.execute(
        select(func.count(ConsentRecord.id)).where(ConsentRecord.client_id == cid)
    )).scalar() or 0

    # Messages sent in last 30d
    from src.models.conversation import Conversation
    messages_sent_30d = (await db.execute(
        select(func.count(Conversation.id)).where(
            and_(
                Conversation.client_id == cid,
                Conversation.direction == "outbound",
                Conversation.created_at >= thirty_days_ago,
            )
        )
    )).scalar() or 0

    # Pending followup tasks
    pending_followups = (await db.execute(
        select(func.count(FollowupTask.id)).where(
            and_(FollowupTask.client_id == cid, FollowupTask.status == "pending")
        )
    )).scalar() or 0

    # Compliance events (blocked sends, violations)
    compliance_events_result = await db.execute(
        select(EventLog)
        .where(
            and_(
                EventLog.client_id == cid,
                EventLog.action.in_([
                    "compliance_blocked", "quiet_hours_blocked",
                    "opt_out_processed", "cold_outreach_limit",
                ]),
                EventLog.created_at >= thirty_days_ago,
            )
        )
        .order_by(desc(EventLog.created_at))
        .limit(50)
    )
    compliance_events = [
        {
            "id": str(e.id),
            "action": e.action,
            "message": e.message,
            "lead_id": str(e.lead_id) if e.lead_id else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in compliance_events_result.scalars().all()
    ]

    return {
        "consent_by_type": consent_by_type,
        "total_consent_records": total_consent,
        "total_opted_out": total_optouts,
        "recent_opted_out_30d": recent_optouts,
        "opt_out_rate": round(total_optouts / total_consent, 4) if total_consent > 0 else 0.0,
        "messages_sent_30d": messages_sent_30d,
        "pending_followups": pending_followups,
        "compliance_events": compliance_events,
        "last_audit": now.isoformat(),
    }


# === BOOKINGS ===

@router.get("/api/v1/dashboard/bookings")
async def get_bookings(
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get bookings filtered by date range."""
    conditions = [Booking.client_id == client.id]

    if start:
        try:
            start_date = datetime.fromisoformat(start)
            conditions.append(Booking.appointment_date >= start_date.date())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start date format. Use ISO 8601.")

    if end:
        try:
            end_date = datetime.fromisoformat(end)
            conditions.append(Booking.appointment_date <= end_date.date())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end date format. Use ISO 8601.")

    result = await db.execute(
        select(Booking)
        .where(and_(*conditions))
        .order_by(desc(Booking.appointment_date))
    )
    bookings = result.scalars().all()

    return {
        "bookings": [
            {
                "id": str(b.id),
                "lead_id": str(b.lead_id) if b.lead_id else None,
                "appointment_date": str(b.appointment_date),
                "time_window_start": str(b.time_window_start) if b.time_window_start else None,
                "time_window_end": str(b.time_window_end) if b.time_window_end else None,
                "service_type": b.service_type,
                "tech_name": b.tech_name,
                "status": b.status,
                "crm_sync_status": b.crm_sync_status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bookings
        ],
        "total": len(bookings),
    }


# === ROI DASHBOARD ===

@router.get("/api/v1/dashboard/roi")
async def get_roi_dashboard(
    period: str = Query(default="30d", pattern="^(7d|30d|90d|all)$"),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get comprehensive ROI dashboard data — the showpiece endpoint."""
    if period == "all":
        since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    else:
        days = {"7d": 7, "30d": 30, "90d": 90}[period]
        since = datetime.now(timezone.utc) - timedelta(days=days)

    cid = client.id
    config = client.config or {}
    avg_job_value = config.get("avg_job_value") or 500.0

    # --- Hero KPIs (single pass for core counts) ---
    base_filter = and_(Lead.client_id == cid, Lead.created_at >= since)

    total_leads = (await db.execute(
        select(func.count(Lead.id)).where(base_filter)
    )).scalar() or 0

    leads_booked = (await db.execute(
        select(func.count(Lead.id)).where(
            and_(base_filter, Lead.state.in_(["booked", "completed"]))
        )
    )).scalar() or 0

    booking_rate = leads_booked / total_leads if total_leads > 0 else 0.0
    estimated_revenue = leads_booked * avg_job_value

    # Cost aggregates
    cost_row = (await db.execute(
        select(
            func.coalesce(func.sum(Lead.total_sms_cost_usd), 0.0),
            func.coalesce(func.sum(Lead.total_ai_cost_usd), 0.0),
        ).where(base_filter)
    )).one()
    total_sms_cost = float(cost_row[0])
    total_ai_cost = float(cost_row[1])
    total_cost = total_sms_cost + total_ai_cost

    cost_per_booked = total_cost / leads_booked if leads_booked > 0 else 0.0
    roi_multiplier = estimated_revenue / total_cost if total_cost > 0 else 0.0

    # Average response time
    avg_response = (await db.execute(
        select(func.avg(Lead.first_response_ms)).where(
            and_(base_filter, Lead.first_response_ms.isnot(None))
        )
    )).scalar()
    avg_response_seconds = (float(avg_response) / 1000) if avg_response else 0.0

    # Leads under 10s
    leads_with_response = (await db.execute(
        select(func.count(Lead.id)).where(
            and_(base_filter, Lead.first_response_ms.isnot(None))
        )
    )).scalar() or 0
    leads_under_10s = (await db.execute(
        select(func.count(Lead.id)).where(
            and_(base_filter, Lead.first_response_ms.isnot(None), Lead.first_response_ms < 10000)
        )
    )).scalar() or 0
    leads_under_10s_pct = leads_under_10s / leads_with_response if leads_with_response > 0 else 0.0

    hero_kpis = {
        "total_leads": total_leads,
        "leads_booked": leads_booked,
        "booking_rate": round(booking_rate, 3),
        "estimated_revenue": round(estimated_revenue, 2),
        "cost_per_booked_lead": round(cost_per_booked, 2),
        "roi_multiplier": round(roi_multiplier, 1),
        "avg_response_time_seconds": round(avg_response_seconds, 1),
        "leads_under_10s": round(leads_under_10s_pct, 2),
    }

    # --- Funnel ---
    funnel_result = await db.execute(
        select(Lead.state, func.count(Lead.id))
        .where(base_filter)
        .group_by(Lead.state)
    )
    funnel_raw = {row[0]: row[1] for row in funnel_result.all()}
    funnel = {
        state: funnel_raw.get(state, 0)
        for state in ["new", "intake_sent", "qualifying", "qualified", "booking", "booked", "completed"]
    }

    # --- Revenue by source ---
    source_result = await db.execute(
        select(
            Lead.source,
            func.count(Lead.id).label("leads"),
            func.count(case((Lead.state.in_(["booked", "completed"]), Lead.id))).label("booked"),
        )
        .where(base_filter)
        .group_by(Lead.source)
        .order_by(desc("leads"))
    )
    revenue_by_source = [
        {
            "source": row.source,
            "leads": row.leads,
            "booked": row.booked,
            "revenue": round(row.booked * avg_job_value, 2),
        }
        for row in source_result.all()
    ]

    # --- Revenue by month ---
    month_result = await db.execute(
        select(
            func.to_char(func.date_trunc("month", Lead.created_at), "YYYY-MM").label("month"),
            func.count(Lead.id).label("leads"),
            func.count(case((Lead.state.in_(["booked", "completed"]), Lead.id))).label("booked"),
        )
        .where(base_filter)
        .group_by(text("1"))
        .order_by(text("1"))
    )
    revenue_by_month = [
        {
            "month": row.month,
            "leads": row.leads,
            "booked": row.booked,
            "revenue": round(row.booked * avg_job_value, 2),
        }
        for row in month_result.all()
    ]

    # --- Per-lead economics ---
    avg_sms_per_lead = total_sms_cost / total_leads if total_leads > 0 else 0.0
    avg_ai_per_lead = total_ai_cost / total_leads if total_leads > 0 else 0.0
    avg_total_per_lead = avg_sms_per_lead + avg_ai_per_lead
    cost_to_revenue = avg_total_per_lead / avg_job_value if avg_job_value > 0 else 0.0

    per_lead_economics = {
        "avg_sms_cost": round(avg_sms_per_lead, 3),
        "avg_ai_cost": round(avg_ai_per_lead, 3),
        "avg_total_cost": round(avg_total_per_lead, 3),
        "avg_job_value": avg_job_value,
        "cost_to_revenue_ratio": round(cost_to_revenue, 6),
    }

    # --- Response time distribution ---
    rt_result = await db.execute(
        select(Lead.first_response_ms).where(
            and_(base_filter, Lead.first_response_ms.isnot(None))
        )
    )
    rt_buckets = {"0-5s": 0, "5-10s": 0, "10-30s": 0, "30s+": 0}
    for (ms,) in rt_result.all():
        if ms < 5000:
            rt_buckets["0-5s"] += 1
        elif ms < 10000:
            rt_buckets["5-10s"] += 1
        elif ms < 30000:
            rt_buckets["10-30s"] += 1
        else:
            rt_buckets["30s+"] += 1

    response_time_distribution = [
        {"bucket": k, "count": v} for k, v in rt_buckets.items()
    ]

    # --- Qualify variant performance ---
    variant_result = await db.execute(
        select(
            Lead.qualify_variant,
            func.count(Lead.id).label("leads"),
            func.count(case((Lead.state.in_(["booked", "completed"]), Lead.id))).label("booked"),
        )
        .where(and_(base_filter, Lead.qualify_variant.isnot(None)))
        .group_by(Lead.qualify_variant)
        .order_by(Lead.qualify_variant)
    )
    qualify_variant_performance = [
        {
            "variant": row.qualify_variant,
            "leads": row.leads,
            "booked": row.booked,
            "rate": round(row.booked / row.leads, 3) if row.leads > 0 else 0.0,
        }
        for row in variant_result.all()
    ]

    return {
        "hero_kpis": hero_kpis,
        "funnel": funnel,
        "revenue_by_source": revenue_by_source,
        "revenue_by_month": revenue_by_month,
        "per_lead_economics": per_lead_economics,
        "response_time_distribution": response_time_distribution,
        "qualify_variant_performance": qualify_variant_performance,
    }


# === CUSTOM REPORTS ===

@router.get("/api/v1/dashboard/reports/custom")
async def get_custom_report(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get custom date range report data."""
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601.")

    # Total leads in range
    lead_count = (await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.client_id == client.id, Lead.created_at >= start_date, Lead.created_at <= end_date)
        )
    )).scalar() or 0

    # Leads by state
    state_result = await db.execute(
        select(Lead.state, func.count()).where(
            and_(Lead.client_id == client.id, Lead.created_at >= start_date, Lead.created_at <= end_date)
        ).group_by(Lead.state)
    )
    by_state = {row[0]: row[1] for row in state_result.all()}

    # Bookings in range
    booking_count = (await db.execute(
        select(func.count(Booking.id)).where(
            and_(Booking.client_id == client.id, Booking.created_at >= start_date, Booking.created_at <= end_date)
        )
    )).scalar() or 0

    # Avg response time
    avg_response = (await db.execute(
        select(func.avg(Lead.first_response_ms)).where(
            and_(
                Lead.client_id == client.id,
                Lead.created_at >= start_date,
                Lead.created_at <= end_date,
                Lead.first_response_ms.isnot(None),
            )
        )
    )).scalar()

    return {
        "start": start,
        "end": end,
        "total_leads": lead_count,
        "by_state": by_state,
        "bookings": booking_count,
        "avg_response_ms": round(float(avg_response)) if avg_response else None,
    }
