"""
Sales Engine — Prospect CRUD endpoints.
All endpoints require admin authentication.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.email_blacklist import EmailBlacklist
from src.api.dashboard import get_current_admin
from src.services.sales_tenancy import normalize_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize_prospect(p: Outreach) -> dict:
    """Serialize an Outreach record to a JSON-friendly dict."""
    return {
        "id": str(p.id),
        "prospect_name": p.prospect_name,
        "prospect_company": p.prospect_company,
        "prospect_email": p.prospect_email,
        "prospect_phone": p.prospect_phone,
        "prospect_trade_type": p.prospect_trade_type,
        "status": p.status,
        "source": p.source,
        "website": p.website,
        "google_rating": p.google_rating,
        "review_count": p.review_count,
        "address": p.address,
        "city": p.city,
        "state_code": p.state_code,
        "email_verified": p.email_verified,
        "email_source": p.email_source,
        "outreach_sequence_step": p.outreach_sequence_step,
        "total_emails_sent": p.total_emails_sent,
        "total_cost_usd": p.total_cost_usd,
        "email_unsubscribed": p.email_unsubscribed,
        "campaign_id": str(p.campaign_id) if p.campaign_id else None,
        "last_email_sent_at": p.last_email_sent_at.isoformat() if p.last_email_sent_at else None,
        "last_email_opened_at": p.last_email_opened_at.isoformat() if p.last_email_opened_at else None,
        "last_email_replied_at": p.last_email_replied_at.isoformat() if p.last_email_replied_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def _get_tenant_prospect(db: AsyncSession, prospect_id: uuid.UUID, tenant_id):
    result = await db.execute(
        select(Outreach).where(
            and_(
                Outreach.id == prospect_id,
                Outreach.tenant_id == tenant_id,
            )
        ).limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/prospects")
async def list_prospects(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    trade_type: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    campaign_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """List prospects with pagination and filters."""
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    conditions = [Outreach.tenant_id == tenant_id]
    if status:
        conditions.append(Outreach.status == status)
    if trade_type:
        conditions.append(Outreach.prospect_trade_type == trade_type)
    if campaign_id:
        try:
            cid = uuid.UUID(campaign_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid campaign_id")
        conditions.append(Outreach.campaign_id == cid)
    if search:
        safe_search = search.replace("%", "\\%").replace("_", "\\_")
        search_term = f"%{safe_search}%"
        conditions.append(
            or_(
                Outreach.prospect_name.ilike(search_term),
                Outreach.prospect_company.ilike(search_term),
                Outreach.prospect_email.ilike(search_term),
                Outreach.city.ilike(search_term),
            )
        )

    where_clause = and_(*conditions) if conditions else True

    count_result = await db.execute(
        select(func.count()).select_from(Outreach).where(where_clause)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Outreach)
        .where(where_clause)
        .order_by(desc(Outreach.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    prospects = result.scalars().all()

    return {
        "prospects": [_serialize_prospect(p) for p in prospects],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/prospects/{prospect_id}")
async def get_prospect(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get single prospect detail."""
    try:
        pid = uuid.UUID(prospect_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid prospect ID")
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    prospect = await _get_tenant_prospect(db, pid, tenant_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return _serialize_prospect(prospect)


@router.put("/prospects/{prospect_id}")
async def update_prospect(
    prospect_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Edit a prospect."""
    try:
        pid = uuid.UUID(prospect_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid prospect ID")
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    prospect = await _get_tenant_prospect(db, pid, tenant_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    allowed_fields = [
        "prospect_name", "prospect_company", "prospect_email",
        "prospect_phone", "prospect_trade_type", "status", "notes",
        "estimated_mrr", "website", "city", "state_code",
    ]
    for field in allowed_fields:
        if field in payload:
            setattr(prospect, field, payload[field])

    prospect.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return _serialize_prospect(prospect)


@router.delete("/prospects/{prospect_id}")
async def delete_prospect(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Delete a prospect and all related emails."""
    try:
        pid = uuid.UUID(prospect_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid prospect ID")
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    prospect = await _get_tenant_prospect(db, pid, tenant_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    await db.delete(prospect)
    return {"status": "deleted"}


@router.post("/prospects")
async def create_prospect(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Manually add a prospect."""
    name = payload.get("prospect_name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="prospect_name is required")
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))

    prospect = Outreach(
        tenant_id=tenant_id,
        prospect_name=name,
        prospect_company=payload.get("prospect_company"),
        prospect_email=payload.get("prospect_email"),
        prospect_phone=payload.get("prospect_phone"),
        prospect_trade_type=payload.get("prospect_trade_type", "general"),
        status="cold",
        source="manual",
        website=payload.get("website"),
        city=payload.get("city"),
        state_code=payload.get("state_code"),
        outreach_sequence_step=0,
    )
    db.add(prospect)
    await db.flush()
    return _serialize_prospect(prospect)


@router.post("/prospects/{prospect_id}/blacklist")
async def blacklist_prospect(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Blacklist a prospect's email and domain."""
    try:
        pid = uuid.UUID(prospect_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid prospect ID")
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    prospect = await _get_tenant_prospect(db, pid, tenant_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    entries_added = []

    if prospect.prospect_email:
        email = prospect.prospect_email.lower().strip()
        # Blacklist email
        existing = await db.execute(
            select(EmailBlacklist).where(EmailBlacklist.value == email).limit(1)
        )
        if not existing.scalar_one_or_none():
            db.add(EmailBlacklist(
                entry_type="email",
                value=email,
                reason=f"Blacklisted from prospect {prospect_id[:8]}",
            ))
            entries_added.append(email)

        # Blacklist domain
        domain = email.split("@")[1] if "@" in email else None
        if domain:
            existing = await db.execute(
                select(EmailBlacklist).where(EmailBlacklist.value == domain).limit(1)
            )
            if not existing.scalar_one_or_none():
                db.add(EmailBlacklist(
                    entry_type="domain",
                    value=domain,
                    reason=f"Blacklisted from prospect {prospect_id[:8]}",
                ))
                entries_added.append(domain)

    # Mark prospect as unsubscribed and lost
    prospect.email_unsubscribed = True
    prospect.unsubscribed_at = datetime.now(timezone.utc)
    prospect.status = "lost"
    prospect.updated_at = datetime.now(timezone.utc)

    return {"status": "blacklisted", "entries": entries_added}


# === EMAIL THREAD ENDPOINTS ===

@router.get("/prospects/{prospect_id}/emails")
async def get_prospect_emails(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get all emails (outbound + inbound) for a prospect."""
    try:
        pid = uuid.UUID(prospect_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid prospect ID")
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    prospect = await _get_tenant_prospect(db, pid, tenant_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    result = await db.execute(
        select(OutreachEmail)
        .where(OutreachEmail.outreach_id == prospect.id)
        .order_by(OutreachEmail.sent_at.asc())
    )
    emails = result.scalars().all()

    return {
        "emails": [
            {
                "id": str(e.id),
                "direction": e.direction,
                "subject": e.subject,
                "body_html": e.body_html,
                "body_text": e.body_text,
                "from_email": e.from_email,
                "to_email": e.to_email,
                "sequence_step": e.sequence_step,
                "sendgrid_message_id": e.sendgrid_message_id,
                "sent_at": e.sent_at.isoformat() if e.sent_at else None,
                "delivered_at": e.delivered_at.isoformat() if e.delivered_at else None,
                "opened_at": e.opened_at.isoformat() if e.opened_at else None,
                "clicked_at": e.clicked_at.isoformat() if e.clicked_at else None,
                "bounced_at": e.bounced_at.isoformat() if e.bounced_at else None,
                "bounce_type": e.bounce_type,
                "bounce_reason": e.bounce_reason,
            }
            for e in emails
        ],
        "total": len(emails),
    }


# === BULK OPERATIONS ===

@router.post("/prospects/bulk")
async def bulk_update_prospects(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Bulk operations on prospects: status change, delete, assign to campaign."""
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    prospect_ids = payload.get("prospect_ids", [])
    action = payload.get("action", "")

    if not prospect_ids or not action:
        raise HTTPException(status_code=400, detail="prospect_ids and action are required")

    if len(prospect_ids) > 200:
        raise HTTPException(status_code=400, detail="Maximum 200 prospects per bulk operation")

    updated = 0
    campaign_id = None
    if action.startswith("campaign:"):
        from src.models.campaign import Campaign

        campaign_id_str = action.split(":")[1]
        try:
            campaign_id = uuid.UUID(campaign_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid campaign ID")

        campaign_result = await db.execute(
            select(Campaign).where(
                and_(
                    Campaign.id == campaign_id,
                    Campaign.tenant_id == tenant_id,
                )
            ).limit(1)
        )
        if not campaign_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Campaign not found")

    for pid in prospect_ids:
        try:
            prospect = await _get_tenant_prospect(db, uuid.UUID(pid), tenant_id)
            if not prospect:
                continue

            if action == "delete":
                await db.delete(prospect)
            elif action.startswith("status:"):
                new_status = action.split(":")[1]
                prospect.status = new_status
                prospect.updated_at = datetime.now(timezone.utc)
            elif action.startswith("campaign:"):
                prospect.campaign_id = campaign_id
                prospect.updated_at = datetime.now(timezone.utc)

            updated += 1
        except Exception as e:
            logger.warning("Bulk op failed for %s: %s", pid[:8], str(e))

    return {"status": "completed", "updated": updated, "total": len(prospect_ids)}
