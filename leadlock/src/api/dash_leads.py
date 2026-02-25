"""
Dashboard lead endpoints — CRUD, export, conversations, lead actions (status/archive/tags/notes).
"""
import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from src.database import get_db
from src.api.dash_auth import get_current_client
from src.models.lead import Lead
from src.models.client import Client
from src.models.conversation import Conversation
from src.models.booking import Booking
from src.models.consent import ConsentRecord
from src.models.event_log import EventLog
from src.schemas.api_responses import (
    LeadSummary,
    LeadListResponse,
    MessageSummary,
    LeadDetailResponse,
    BookingDetail,
    ConsentDetail,
    EventSummary,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


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
        # Escape SQL LIKE wildcards in user input
        escaped = search.replace("%", r"\%").replace("_", r"\_")
        search_pattern = f"%{escaped}%"
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


@router.get("/api/v1/dashboard/leads/export")
async def export_leads_csv(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Export leads as CSV (capped at 10,000 rows for safety)."""
    MAX_EXPORT_ROWS = 10000
    result = await db.execute(
        select(Lead)
        .where(Lead.client_id == client.id)
        .order_by(desc(Lead.created_at))
        .limit(MAX_EXPORT_ROWS)
    )
    leads = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "first_name", "last_name", "phone", "source", "state",
        "score", "service_type", "urgency", "first_response_ms",
        "total_messages", "created_at",
    ])

    for lead in leads:
        writer.writerow([
            str(lead.id),
            lead.first_name,
            lead.last_name,
            lead.phone[:6] + "***" if lead.phone else "",
            lead.source,
            lead.state,
            lead.score,
            lead.service_type,
            lead.urgency,
            lead.first_response_ms,
            (lead.total_messages_sent or 0) + (lead.total_messages_received or 0),
            lead.created_at.isoformat() if lead.created_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


@router.get("/api/v1/dashboard/leads/{lead_id}", response_model=LeadDetailResponse)
async def get_lead_detail(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get full lead detail with conversation history."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
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
    try:
        lid = uuid.UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lead ID")
    result = await db.execute(
        select(Conversation)
        .where(
            and_(Conversation.lead_id == lid, Conversation.client_id == client.id)
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


# === LEAD ACTIONS ===

@router.put("/api/v1/dashboard/leads/{lead_id}/status")
async def update_lead_status(
    lead_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Change lead status (close, re-engage, etc)."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    new_status = payload.get("status", "").strip()
    # opted_out excluded - must go through SMS pipeline for compliance
    valid_statuses = {"new", "qualifying", "qualified", "booking", "booked", "completed", "cold", "dead"}
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    lead.state = new_status
    lead.updated_at = datetime.now(timezone.utc)
    return {"status": "updated", "new_state": new_status}


@router.put("/api/v1/dashboard/leads/{lead_id}/archive")
async def archive_lead(
    lead_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Archive or unarchive a lead."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    archived = payload.get("archived", True)
    if hasattr(lead, "archived"):
        lead.archived = archived
    lead.updated_at = datetime.now(timezone.utc)
    return {"status": "updated", "archived": archived}


@router.put("/api/v1/dashboard/leads/{lead_id}/tags")
async def update_lead_tags(
    lead_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Add or remove tags from a lead."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    tags = payload.get("tags", [])
    if not isinstance(tags, list):
        raise HTTPException(status_code=400, detail="tags must be a list")

    if hasattr(lead, "tags"):
        lead.tags = tags
    lead.updated_at = datetime.now(timezone.utc)
    return {"status": "updated", "tags": tags}


@router.put("/api/v1/dashboard/leads/{lead_id}/notes")
async def update_lead_notes(
    lead_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Add internal notes to a lead."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    notes = payload.get("notes", "")
    if hasattr(lead, "notes"):
        lead.notes = notes
    lead.updated_at = datetime.now(timezone.utc)
    return {"status": "updated"}


# === REPLY ===

@router.post("/api/v1/dashboard/leads/{lead_id}/reply")
async def reply_to_lead(
    lead_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Send a manual SMS reply to a lead from the dashboard."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    if len(message) > 1600:
        raise HTTPException(status_code=400, detail="Message too long (max 1600 chars)")

    if not lead.phone:
        raise HTTPException(status_code=400, detail="Lead has no phone number")

    # Compliance check before sending
    from src.services.compliance import full_compliance_check
    compliance = full_compliance_check(
        has_consent=True,
        consent_type="express",
        is_opted_out=lead.state == "opted_out",
        state_code=lead.state_code,
        is_emergency=False,
        message=message,
        is_first_message=False,
        business_name=client.business_name,
    )
    if not compliance:
        raise HTTPException(
            status_code=403,
            detail=f"Compliance blocked: {compliance.reason}",
        )

    # Send SMS
    from src.services.sms import send_sms
    sms_result = await send_sms(
        to=lead.phone,
        body=message,
        from_phone=client.twilio_phone,
        messaging_service_sid=client.twilio_messaging_service_sid,
    )

    if sms_result.get("error") and not sms_result.get("sid"):
        raise HTTPException(
            status_code=502,
            detail=f"SMS send failed: {sms_result['error']}",
        )

    # Record conversation
    conv = Conversation(
        lead_id=lead.id,
        client_id=client.id,
        direction="outbound",
        agent_id="human",
        content=message,
        from_phone=client.twilio_phone or "",
        to_phone=lead.phone,
        delivery_status=sms_result.get("status", "sent"),
        twilio_sid=sms_result.get("sid"),
    )
    db.add(conv)

    # Update lead counters
    lead.total_messages_sent = (lead.total_messages_sent or 0) + 1
    lead.updated_at = datetime.now(timezone.utc)

    # Log event
    db.add(EventLog(
        lead_id=lead.id,
        client_id=client.id,
        action="manual_sms_sent",
        message=f"Manual reply sent from dashboard ({len(message)} chars)",
    ))

    await db.commit()

    return {
        "status": "sent",
        "sid": sms_result.get("sid"),
        "segments": sms_result.get("segments", 1),
    }
