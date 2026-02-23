"""
Unified inbox API — cross-campaign conversation view and email thread viewer.
Extracted from campaign_detail.py for file size compliance.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.campaign import Campaign
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.api.dashboard import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sales", tags=["campaign-inbox"])


@router.get("/inbox")
async def get_inbox(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    campaign_id: Optional[str] = Query(default=None),
    filter: Optional[str] = Query(default="all", pattern="^(all|replies|sent)$"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Unified inbox - prospects with email activity, ordered by most recent.

    Filters:
      - all: All prospects that have ANY email (outbound or inbound)
      - replies: Only prospects that have inbound replies
      - sent: Prospects with outbound emails but NO inbound replies

    Each item includes prospect info, campaign name, last email snippet,
    reply count, sent count, and timestamps.
    """
    # Subquery: email stats per prospect (outbound)
    outbound_stats = (
        select(
            OutreachEmail.outreach_id,
            func.max(OutreachEmail.sent_at).label("last_outbound_at"),
            func.count().label("sent_count"),
        )
        .where(OutreachEmail.direction == "outbound")
        .group_by(OutreachEmail.outreach_id)
        .subquery()
    )

    # Subquery: email stats per prospect (inbound)
    inbound_stats = (
        select(
            OutreachEmail.outreach_id,
            func.max(OutreachEmail.sent_at).label("last_inbound_at"),
            func.count().label("reply_count"),
        )
        .where(OutreachEmail.direction == "inbound")
        .group_by(OutreachEmail.outreach_id)
        .subquery()
    )

    # Build conditions based on filter
    conditions = []
    if campaign_id:
        try:
            cid = uuid.UUID(campaign_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid campaign ID")
        conditions.append(Outreach.campaign_id == cid)

    if filter == "replies":
        # Only prospects with inbound replies (original behavior)
        conditions.append(inbound_stats.c.last_inbound_at.isnot(None))
    elif filter == "sent":
        # Prospects with outbound but NO inbound
        conditions.append(outbound_stats.c.last_outbound_at.isnot(None))
        conditions.append(inbound_stats.c.last_inbound_at.is_(None))
    else:
        # "all" - any prospect that has at least one email (outbound or inbound)
        conditions.append(
            or_(
                outbound_stats.c.last_outbound_at.isnot(None),
                inbound_stats.c.last_inbound_at.isnot(None),
            )
        )

    where_clause = and_(*conditions) if conditions else True

    # Build the base query with outer joins to get both outbound and inbound stats
    base = (
        select(Outreach)
        .outerjoin(outbound_stats, Outreach.id == outbound_stats.c.outreach_id)
        .outerjoin(inbound_stats, Outreach.id == inbound_stats.c.outreach_id)
    )

    # Count total
    count_query = (
        select(func.count())
        .select_from(Outreach)
        .outerjoin(outbound_stats, Outreach.id == outbound_stats.c.outreach_id)
        .outerjoin(inbound_stats, Outreach.id == inbound_stats.c.outreach_id)
        .where(where_clause)
    )
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Also compute filter-level counts for the UI tabs
    count_all_q = (
        select(func.count())
        .select_from(Outreach)
        .outerjoin(outbound_stats, Outreach.id == outbound_stats.c.outreach_id)
        .outerjoin(inbound_stats, Outreach.id == inbound_stats.c.outreach_id)
        .where(
            or_(
                outbound_stats.c.last_outbound_at.isnot(None),
                inbound_stats.c.last_inbound_at.isnot(None),
            )
        )
    )
    count_replies_q = (
        select(func.count())
        .select_from(Outreach)
        .outerjoin(inbound_stats, Outreach.id == inbound_stats.c.outreach_id)
        .where(inbound_stats.c.last_inbound_at.isnot(None))
    )
    count_sent_q = (
        select(func.count())
        .select_from(Outreach)
        .outerjoin(outbound_stats, Outreach.id == outbound_stats.c.outreach_id)
        .outerjoin(inbound_stats, Outreach.id == inbound_stats.c.outreach_id)
        .where(
            and_(
                outbound_stats.c.last_outbound_at.isnot(None),
                inbound_stats.c.last_inbound_at.is_(None),
            )
        )
    )
    all_count_r = await db.execute(count_all_q)
    replies_count_r = await db.execute(count_replies_q)
    sent_count_r = await db.execute(count_sent_q)
    total_conversations = all_count_r.scalar() or 0
    with_replies = replies_count_r.scalar() or 0
    without_replies = sent_count_r.scalar() or 0

    # Order by most recent activity (whichever is newer: inbound or outbound)
    last_activity = func.greatest(
        func.coalesce(outbound_stats.c.last_outbound_at, datetime(2000, 1, 1, tzinfo=timezone.utc)),
        func.coalesce(inbound_stats.c.last_inbound_at, datetime(2000, 1, 1, tzinfo=timezone.utc)),
    )

    # Fetch page
    query = (
        select(
            Outreach,
            outbound_stats.c.last_outbound_at,
            outbound_stats.c.sent_count,
            inbound_stats.c.last_inbound_at,
            inbound_stats.c.reply_count,
        )
        .outerjoin(outbound_stats, Outreach.id == outbound_stats.c.outreach_id)
        .outerjoin(inbound_stats, Outreach.id == inbound_stats.c.outreach_id)
        .where(where_clause)
        .order_by(desc(last_activity))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        prospect = row[0]
        last_outbound_at = row[1]
        sent_count = row[2] or 0
        last_inbound_at = row[3]
        reply_count = row[4] or 0

        # Get last email snippet (prefer inbound reply, fall back to outbound)
        snippet = ""
        if reply_count > 0:
            last_email_result = await db.execute(
                select(OutreachEmail)
                .where(
                    and_(
                        OutreachEmail.outreach_id == prospect.id,
                        OutreachEmail.direction == "inbound",
                    )
                )
                .order_by(desc(OutreachEmail.sent_at))
                .limit(1)
            )
            last_email = last_email_result.scalar_one_or_none()
            if last_email:
                text = last_email.body_text or last_email.body_html or ""
                snippet = text[:80].strip()
        elif sent_count > 0:
            last_email_result = await db.execute(
                select(OutreachEmail)
                .where(
                    and_(
                        OutreachEmail.outreach_id == prospect.id,
                        OutreachEmail.direction == "outbound",
                    )
                )
                .order_by(desc(OutreachEmail.sent_at))
                .limit(1)
            )
            last_email = last_email_result.scalar_one_or_none()
            if last_email:
                text = last_email.body_text or last_email.body_html or ""
                snippet = text[:80].strip()

        # Get campaign name if assigned
        campaign_name = None
        if prospect.campaign_id:
            campaign_obj = await db.get(Campaign, prospect.campaign_id)
            if campaign_obj:
                campaign_name = campaign_obj.name

        # Determine most recent activity timestamp
        last_activity_at = last_inbound_at or last_outbound_at

        items.append({
            "prospect_id": str(prospect.id),
            "prospect_name": prospect.prospect_name,
            "prospect_company": prospect.prospect_company,
            "prospect_email": prospect.prospect_email,
            "campaign_id": str(prospect.campaign_id) if prospect.campaign_id else None,
            "campaign_name": campaign_name,
            "status": prospect.status,
            "last_reply_snippet": snippet,
            "reply_count": reply_count,
            "sent_count": sent_count,
            "last_outbound_at": last_outbound_at.isoformat() if last_outbound_at else None,
            "last_inbound_at": last_inbound_at.isoformat() if last_inbound_at else None,
            "last_activity_at": last_activity_at.isoformat() if last_activity_at else None,
        })

    return {
        "conversations": items,
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "total_conversations": total_conversations,
        "with_replies": with_replies,
        "without_replies": without_replies,
    }


@router.get("/inbox/{prospect_id}/thread")
async def get_inbox_thread(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Full email thread for a prospect - all outbound + inbound in chronological order.
    Includes prospect details and campaign name.
    """
    try:
        pid = uuid.UUID(prospect_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid prospect ID")
    prospect = await db.get(Outreach, pid)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    # Campaign name
    campaign_name = None
    if prospect.campaign_id:
        campaign_obj = await db.get(Campaign, prospect.campaign_id)
        if campaign_obj:
            campaign_name = campaign_obj.name

    # All emails chronological
    result = await db.execute(
        select(OutreachEmail)
        .where(OutreachEmail.outreach_id == prospect.id)
        .order_by(OutreachEmail.sent_at.asc())
    )
    emails = result.scalars().all()

    return {
        "prospect": {
            "id": str(prospect.id),
            "name": prospect.prospect_name,
            "company": prospect.prospect_company,
            "email": prospect.prospect_email,
            "phone": prospect.prospect_phone,
            "trade_type": prospect.prospect_trade_type,
            "city": prospect.city,
            "state_code": prospect.state_code,
            "status": prospect.status,
            "campaign_id": str(prospect.campaign_id) if prospect.campaign_id else None,
            "campaign_name": campaign_name,
        },
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
                "sent_at": e.sent_at.isoformat() if e.sent_at else None,
                "delivered_at": e.delivered_at.isoformat() if e.delivered_at else None,
                "opened_at": e.opened_at.isoformat() if e.opened_at else None,
                "clicked_at": e.clicked_at.isoformat() if e.clicked_at else None,
                "bounced_at": e.bounced_at.isoformat() if e.bounced_at else None,
            }
            for e in emails
        ],
        "total": len(emails),
    }
