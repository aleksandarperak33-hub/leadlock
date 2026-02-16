"""
Admin Dashboard API — endpoints for the LeadLock operator dashboard.
All endpoints require admin-level JWT authentication.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from src.database import get_db
from src.models.client import Client
from src.models.lead import Lead
from src.models.outreach import Outreach
from src.models.event_log import EventLog
from src.api.dashboard import get_current_admin
from src.services.admin_reporting import (
    get_system_overview,
    get_client_list_with_metrics,
    get_revenue_breakdown,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["admin-dashboard"])


# === OVERVIEW ===

@router.get("/overview")
async def admin_overview(
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """System-wide KPIs for the admin dashboard."""
    return await get_system_overview(db)


# === CLIENTS ===

@router.get("/clients")
async def admin_clients(
    search: Optional[str] = None,
    tier: Optional[str] = None,
    billing_status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """All clients with per-client metrics."""
    return await get_client_list_with_metrics(
        db, search=search, tier=tier, billing_status=billing_status,
        page=page, per_page=per_page,
    )


@router.get("/clients/{client_id}")
async def admin_client_detail(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """Deep-dive on a single client."""
    from datetime import timedelta
    from src.services.reporting import get_dashboard_metrics

    client = await db.get(Client, uuid.UUID(client_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    metrics = await get_dashboard_metrics(db, client_id, "30d")

    # Recent leads
    recent_leads = await db.execute(
        select(Lead)
        .where(Lead.client_id == uuid.UUID(client_id))
        .order_by(desc(Lead.created_at))
        .limit(20)
    )
    leads = recent_leads.scalars().all()

    return {
        "client": {
            "id": str(client.id),
            "business_name": client.business_name,
            "trade_type": client.trade_type,
            "tier": client.tier,
            "monthly_fee": client.monthly_fee,
            "billing_status": client.billing_status,
            "onboarding_status": client.onboarding_status,
            "owner_name": client.owner_name,
            "owner_email": client.owner_email,
            "owner_phone": client.owner_phone,
            "twilio_phone": client.twilio_phone,
            "crm_type": client.crm_type,
            "ten_dlc_status": client.ten_dlc_status,
            "is_active": client.is_active,
            "created_at": client.created_at.isoformat() if client.created_at else None,
        },
        "metrics": metrics.model_dump() if metrics else {},
        "recent_leads": [
            {
                "id": str(l.id),
                "first_name": l.first_name,
                "last_name": l.last_name,
                "phone_masked": l.phone[:6] + "***" if l.phone else "",
                "source": l.source,
                "state": l.state,
                "score": l.score,
                "service_type": l.service_type,
                "first_response_ms": l.first_response_ms,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in leads
        ],
    }


# === LEADS ===

@router.get("/leads")
async def admin_leads(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    state: Optional[str] = None,
    source: Optional[str] = None,
    client_id: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """All leads across all clients with filters."""
    query = select(Lead)

    if state:
        query = query.where(Lead.state == state)
    if source:
        query = query.where(Lead.source == source)
    if client_id:
        query = query.where(Lead.client_id == uuid.UUID(client_id))
    if search:
        pattern = f"%{search}%"
        query = query.where(
            Lead.first_name.ilike(pattern)
            | Lead.last_name.ilike(pattern)
            | Lead.phone.ilike(pattern)
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(desc(Lead.created_at)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    leads = result.scalars().all()

    # Get client names for display
    client_ids = list({l.client_id for l in leads})
    client_names = {}
    if client_ids:
        clients_result = await db.execute(
            select(Client.id, Client.business_name).where(Client.id.in_(client_ids))
        )
        client_names = {row[0]: row[1] for row in clients_result.all()}

    return {
        "leads": [
            {
                "id": str(l.id),
                "client_id": str(l.client_id),
                "client_name": client_names.get(l.client_id, "Unknown"),
                "first_name": l.first_name,
                "last_name": l.last_name,
                "phone_masked": l.phone[:6] + "***" if l.phone else "",
                "source": l.source,
                "state": l.state,
                "score": l.score,
                "service_type": l.service_type,
                "urgency": l.urgency,
                "first_response_ms": l.first_response_ms,
                "total_messages": l.total_messages_sent + l.total_messages_received,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in leads
        ],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


# === REVENUE ===

@router.get("/revenue")
async def admin_revenue(
    period: str = Query(default="30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """MRR breakdown by tier and top clients."""
    return await get_revenue_breakdown(db, period)


# === HEALTH ===

@router.get("/health")
async def admin_health(
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """System health — recent errors, integration status."""
    from datetime import timedelta
    since_24h = datetime.utcnow() - timedelta(hours=24)

    # Recent errors
    error_result = await db.execute(
        select(EventLog)
        .where(and_(EventLog.status == "error", EventLog.created_at >= since_24h))
        .order_by(desc(EventLog.created_at))
        .limit(50)
    )
    errors = error_result.scalars().all()

    # Clients with integration issues
    clients_result = await db.execute(
        select(Client)
        .where(and_(Client.is_active == True, Client.ten_dlc_status != "approved"))
    )
    pending_clients = clients_result.scalars().all()

    return {
        "recent_errors": [
            {
                "id": str(e.id),
                "action": e.action,
                "message": e.message,
                "lead_id": str(e.lead_id) if e.lead_id else None,
                "client_id": str(e.client_id) if e.client_id else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in errors
        ],
        "error_count_24h": len(errors),
        "pending_integrations": [
            {
                "id": str(c.id),
                "business_name": c.business_name,
                "ten_dlc_status": c.ten_dlc_status,
                "crm_type": c.crm_type,
                "onboarding_status": c.onboarding_status,
            }
            for c in pending_clients
        ],
    }


# === OUTREACH ===

@router.get("/outreach")
async def admin_outreach(
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """LeadLock's own sales pipeline."""
    query = select(Outreach)
    if status:
        query = query.where(Outreach.status == status)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(desc(Outreach.updated_at)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    prospects = result.scalars().all()

    return {
        "prospects": [
            {
                "id": str(p.id),
                "prospect_name": p.prospect_name,
                "prospect_company": p.prospect_company,
                "prospect_email": p.prospect_email,
                "prospect_phone": p.prospect_phone,
                "prospect_trade_type": p.prospect_trade_type,
                "status": p.status,
                "notes": p.notes,
                "estimated_mrr": p.estimated_mrr,
                "demo_date": p.demo_date.isoformat() if p.demo_date else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in prospects
        ],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.post("/outreach")
async def create_outreach(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """Create a new outreach prospect."""
    from datetime import date as date_type

    prospect = Outreach(
        prospect_name=payload.get("prospect_name", ""),
        prospect_company=payload.get("prospect_company"),
        prospect_email=payload.get("prospect_email"),
        prospect_phone=payload.get("prospect_phone"),
        prospect_trade_type=payload.get("prospect_trade_type"),
        status=payload.get("status", "cold"),
        notes=payload.get("notes"),
        estimated_mrr=payload.get("estimated_mrr"),
    )

    demo_date = payload.get("demo_date")
    if demo_date:
        prospect.demo_date = date_type.fromisoformat(demo_date)

    db.add(prospect)
    await db.flush()

    return {
        "id": str(prospect.id),
        "status": "created",
    }


@router.put("/outreach/{prospect_id}")
async def update_outreach(
    prospect_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin: Client = Depends(get_current_admin),
):
    """Update an outreach prospect."""
    from datetime import date as date_type

    prospect = await db.get(Outreach, uuid.UUID(prospect_id))
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    for field in ["prospect_name", "prospect_company", "prospect_email", "prospect_phone",
                  "prospect_trade_type", "status", "notes", "estimated_mrr"]:
        if field in payload:
            setattr(prospect, field, payload[field])

    if "demo_date" in payload:
        prospect.demo_date = date_type.fromisoformat(payload["demo_date"]) if payload["demo_date"] else None

    if "converted_client_id" in payload:
        prospect.converted_client_id = uuid.UUID(payload["converted_client_id"]) if payload["converted_client_id"] else None

    prospect.updated_at = datetime.utcnow()
    await db.flush()

    return {"status": "updated"}
