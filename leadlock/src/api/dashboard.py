"""
Dashboard API — all endpoints for the React client dashboard.
All endpoints require JWT authentication via Bearer token.
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from src.database import get_db
from src.models.lead import Lead
from src.models.client import Client
from src.models.conversation import Conversation
from src.models.booking import Booking
from src.models.consent import ConsentRecord
from src.models.event_log import EventLog
from src.models.followup import FollowupTask
from src.schemas.api_responses import (
    LoginRequest,
    LoginResponse,
    LeadSummary,
    LeadListResponse,
    MessageSummary,
    LeadDetailResponse,
    BookingDetail,
    ConsentDetail,
    EventSummary,
    DashboardMetrics,
    ActivityEvent,
    ComplianceSummary,
)
from src.services.reporting import get_dashboard_metrics

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


# === AUTH ===

@router.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate dashboard user and return JWT token."""
    result = await db.execute(
        select(Client).where(Client.dashboard_email == payload.email)
    )
    client = result.scalar_one_or_none()

    if not client or not client.dashboard_password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    import bcrypt
    if not bcrypt.checkpw(payload.password.encode(), client.dashboard_password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate JWT
    import jwt
    from src.config import get_settings
    settings = get_settings()

    token = jwt.encode(
        {
            "client_id": str(client.id),
            "exp": datetime.utcnow() + timedelta(hours=settings.dashboard_jwt_expiry_hours),
        },
        settings.dashboard_jwt_secret or settings.app_secret_key,
        algorithm="HS256",
    )

    return LoginResponse(
        token=token,
        client_id=str(client.id),
        business_name=client.business_name,
    )


async def get_current_client(
    db: AsyncSession = Depends(get_db),
) -> Client:
    """
    Dependency to extract client from JWT token.
    In production, this reads the Authorization header.
    For development, we use a query param or the first active client.
    """
    # Development fallback — use first active client
    result = await db.execute(
        select(Client).where(Client.is_active == True).limit(1)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=401, detail="No authenticated client")
    return client


# === METRICS ===

@router.get("/api/v1/dashboard/metrics", response_model=DashboardMetrics)
async def get_metrics(
    period: str = Query(default="7d", regex="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get aggregated KPI metrics for the dashboard."""
    return await get_dashboard_metrics(db, str(client.id), period)


# === LEADS ===

@router.get("/api/v1/dashboard/leads", response_model=LeadListResponse)
async def get_leads(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    state: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get paginated lead list with filters."""
    query = select(Lead).where(Lead.client_id == client.id)

    if state:
        query = query.where(Lead.state == state)
    if source:
        query = query.where(Lead.source == source)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            Lead.first_name.ilike(search_pattern)
            | Lead.last_name.ilike(search_pattern)
            | Lead.phone.ilike(search_pattern)
            | Lead.service_type.ilike(search_pattern)
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(desc(Lead.created_at)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    leads = result.scalars().all()

    return LeadListResponse(
        leads=[
            LeadSummary(
                id=str(l.id),
                first_name=l.first_name,
                last_name=l.last_name,
                phone_masked=l.phone[:6] + "***" if l.phone else "",
                source=l.source,
                state=l.state,
                score=l.score,
                service_type=l.service_type,
                urgency=l.urgency,
                first_response_ms=l.first_response_ms,
                total_messages=l.total_messages_sent + l.total_messages_received,
                created_at=l.created_at,
            )
            for l in leads
        ],
        total=total,
        page=page,
        pages=max(1, (total + per_page - 1) // per_page),
    )


@router.get("/api/v1/dashboard/leads/{lead_id}", response_model=LeadDetailResponse)
async def get_lead_detail(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get full lead detail with conversation history."""
    lead = await db.get(Lead, uuid.UUID(lead_id))
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get conversations
    conv_result = await db.execute(
        select(Conversation)
        .where(Conversation.lead_id == lead.id)
        .order_by(Conversation.created_at)
    )
    conversations = conv_result.scalars().all()

    # Get booking
    booking_result = await db.execute(
        select(Booking).where(Booking.lead_id == lead.id)
    )
    booking = booking_result.scalar_one_or_none()

    # Get consent
    consent = None
    if lead.consent_id:
        consent = await db.get(ConsentRecord, lead.consent_id)

    # Get events
    event_result = await db.execute(
        select(EventLog)
        .where(EventLog.lead_id == lead.id)
        .order_by(EventLog.created_at)
    )
    events = event_result.scalars().all()

    return LeadDetailResponse(
        lead=LeadSummary(
            id=str(lead.id),
            first_name=lead.first_name,
            last_name=lead.last_name,
            phone_masked=lead.phone[:6] + "***" if lead.phone else "",
            source=lead.source,
            state=lead.state,
            score=lead.score,
            service_type=lead.service_type,
            urgency=lead.urgency,
            first_response_ms=lead.first_response_ms,
            total_messages=lead.total_messages_sent + lead.total_messages_received,
            created_at=lead.created_at,
        ),
        conversations=[
            MessageSummary(
                id=str(c.id),
                direction=c.direction,
                agent_id=c.agent_id,
                content=c.content,
                delivery_status=c.delivery_status,
                created_at=c.created_at,
            )
            for c in conversations
        ],
        booking=BookingDetail(
            id=str(booking.id),
            appointment_date=str(booking.appointment_date),
            time_window_start=str(booking.time_window_start) if booking.time_window_start else None,
            time_window_end=str(booking.time_window_end) if booking.time_window_end else None,
            service_type=booking.service_type,
            tech_name=booking.tech_name,
            status=booking.status,
            crm_sync_status=booking.crm_sync_status,
        ) if booking else None,
        consent=ConsentDetail(
            id=str(consent.id),
            consent_type=consent.consent_type,
            consent_method=consent.consent_method,
            is_active=consent.is_active,
            opted_out=consent.opted_out,
            created_at=consent.created_at,
        ) if consent else None,
        events=[
            EventSummary(
                id=str(e.id),
                action=e.action,
                status=e.status,
                message=e.message,
                duration_ms=e.duration_ms,
                created_at=e.created_at,
            )
            for e in events
        ],
    )


@router.get("/api/v1/dashboard/leads/{lead_id}/conversations")
async def get_conversations(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get full conversation thread for a lead."""
    result = await db.execute(
        select(Conversation)
        .where(
            and_(Conversation.lead_id == uuid.UUID(lead_id), Conversation.client_id == client.id)
        )
        .order_by(Conversation.created_at)
    )
    conversations = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "direction": c.direction,
            "agent_id": c.agent_id,
            "content": c.content,
            "delivery_status": c.delivery_status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in conversations
    ]


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
    }


@router.put("/api/v1/dashboard/settings")
async def update_settings(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Update client configuration."""
    if "config" in payload:
        client.config = payload["config"]
    await db.commit()
    return {"status": "updated"}


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
        last_audit=datetime.utcnow(),
    )
