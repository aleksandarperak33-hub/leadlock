"""
Campaign detail API - enriched campaign views, prospect assignment,
and per-campaign metrics.
Inbox endpoints live in campaign_inbox.py.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.campaign import Campaign
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.api.dashboard import get_current_admin

# Re-exports for backward compatibility
from src.api.campaign_inbox import get_inbox, get_inbox_thread  # noqa: F401

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sales", tags=["campaign-detail"])


# === CAMPAIGN DETAIL ===


@router.get("/campaigns/{campaign_id}/detail")
async def get_campaign_detail(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Enriched campaign detail with prospect counts and email metrics."""
    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    campaign = await db.get(Campaign, cid)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Prospect counts by status
    status_result = await db.execute(
        select(Outreach.status, func.count()).where(
            Outreach.campaign_id == campaign.id
        ).group_by(Outreach.status)
    )
    prospect_counts = {status: count for status, count in status_result.all()}
    total_prospects = sum(prospect_counts.values())

    # Email metrics for this campaign's prospects
    email_stats = await db.execute(
        select(
            func.count().label("sent"),
            func.count(OutreachEmail.opened_at).label("opened"),
            func.count(OutreachEmail.clicked_at).label("clicked"),
            func.count(OutreachEmail.bounced_at).label("bounced"),
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.campaign_id == campaign.id,
                OutreachEmail.direction == "outbound",
            )
        )
    )
    e = email_stats.one()
    total_sent = e.sent or 0

    # Reply count
    reply_result = await db.execute(
        select(func.count())
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.campaign_id == campaign.id,
                OutreachEmail.direction == "inbound",
            )
        )
    )
    total_replies = reply_result.scalar() or 0

    # Step performance
    step_result = await db.execute(
        select(
            OutreachEmail.sequence_step,
            func.count().label("sent"),
            func.count(OutreachEmail.opened_at).label("opened"),
            func.count(OutreachEmail.clicked_at).label("clicked"),
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.campaign_id == campaign.id,
                OutreachEmail.direction == "outbound",
            )
        )
        .group_by(OutreachEmail.sequence_step)
        .order_by(OutreachEmail.sequence_step)
    )

    step_reply_result = await db.execute(
        select(
            OutreachEmail.sequence_step,
            func.count().label("replied"),
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.campaign_id == campaign.id,
                OutreachEmail.direction == "inbound",
            )
        )
        .group_by(OutreachEmail.sequence_step)
    )
    step_replies_map = {
        row.sequence_step: row.replied for row in step_reply_result.all()
    }

    def _rate(num: int, denom: int) -> float:
        return round(num / denom * 100, 1) if denom else 0

    step_performance = []
    for row in step_result.all():
        step_sent = row.sent or 0
        step_replied = step_replies_map.get(row.sequence_step, 0)
        step_performance.append({
            "step": row.sequence_step,
            "sent": step_sent,
            "opened": row.opened or 0,
            "clicked": row.clicked or 0,
            "replied": step_replied,
            "open_rate": _rate(row.opened or 0, step_sent),
            "reply_rate": _rate(step_replied, step_sent),
        })

    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "description": campaign.description,
        "status": campaign.status,
        "target_trades": campaign.target_trades or [],
        "target_locations": campaign.target_locations or [],
        "sequence_steps": campaign.sequence_steps or [],
        "daily_limit": campaign.daily_limit,
        "total_sent": total_sent,
        "total_opened": e.opened or 0,
        "total_replied": total_replies,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
        "prospects": {
            "total": total_prospects,
            "by_status": prospect_counts,
        },
        "emails": {
            "sent": total_sent,
            "opened": e.opened or 0,
            "clicked": e.clicked or 0,
            "bounced": e.bounced or 0,
            "replied": total_replies,
            "open_rate": _rate(e.opened or 0, total_sent),
            "reply_rate": _rate(total_replies, total_sent),
            "bounce_rate": _rate(e.bounced or 0, total_sent),
        },
        "step_performance": step_performance,
    }


@router.get("/campaigns/{campaign_id}/prospects")
async def get_campaign_prospects(
    campaign_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Paginated prospects for a campaign."""
    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    campaign = await db.get(Campaign, cid)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    conditions = [Outreach.campaign_id == campaign.id]
    if status:
        conditions.append(Outreach.status == status)
    if search:
        search_term = f"%{search}%"
        conditions.append(
            or_(
                Outreach.prospect_name.ilike(search_term),
                Outreach.prospect_company.ilike(search_term),
                Outreach.prospect_email.ilike(search_term),
            )
        )

    where_clause = and_(*conditions)

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

    from src.api.sales_engine import _serialize_prospect

    return {
        "prospects": [_serialize_prospect(p) for p in prospects],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.post("/campaigns/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Activate a draft campaign.
    Validates at least 1 sequence step exists, then auto-assigns
    matching unbound cold prospects by target_trades + target_locations.
    """
    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    campaign = await db.get(Campaign, cid)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in ("draft", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot activate campaign in '{campaign.status}' status",
        )

    steps = campaign.sequence_steps or []
    if not steps:
        raise HTTPException(
            status_code=400,
            detail="Campaign must have at least 1 sequence step",
        )

    campaign.status = "active"
    campaign.updated_at = datetime.now(timezone.utc)

    # Auto-assign matching unbound cold prospects
    assigned = await _auto_assign_prospects(db, campaign)

    return {
        "status": "activated",
        "prospects_assigned": assigned,
    }


async def _auto_assign_prospects(
    db: AsyncSession,
    campaign: Campaign,
) -> int:
    """Assign unbound cold prospects matching campaign targeting."""
    conditions = [
        Outreach.campaign_id.is_(None),
        Outreach.status == "cold",
        Outreach.prospect_email.isnot(None),
        Outreach.prospect_email != "",
        Outreach.email_unsubscribed == False,
    ]

    # Filter by target trades
    target_trades = campaign.target_trades or []
    if target_trades:
        conditions.append(Outreach.prospect_trade_type.in_(target_trades))

    # Filter by target locations
    target_locations = campaign.target_locations or []
    if target_locations:
        location_conditions = []
        for loc in target_locations:
            loc_parts = []
            if isinstance(loc, dict):
                if loc.get("city"):
                    loc_parts.append(Outreach.city == loc["city"])
                if loc.get("state"):
                    loc_parts.append(Outreach.state_code == loc["state"])
            elif isinstance(loc, str) and "," in loc:
                parts = [p.strip() for p in loc.split(",")]
                if len(parts) == 2:
                    loc_parts.append(Outreach.city == parts[0])
                    loc_parts.append(Outreach.state_code == parts[1])
            if loc_parts:
                location_conditions.append(and_(*loc_parts))
        if location_conditions:
            conditions.append(or_(*location_conditions))

    result = await db.execute(
        select(Outreach).where(and_(*conditions))
    )
    prospects = result.scalars().all()

    for prospect in prospects:
        prospect.campaign_id = campaign.id
        prospect.updated_at = datetime.now(timezone.utc)

    return len(prospects)


@router.post("/campaigns/{campaign_id}/assign-prospects")
async def assign_prospects(
    campaign_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Bulk assign prospects to a campaign.
    Accepts either { filters: { trade_type, city, state, status } }
    or { prospect_ids: [...] }.
    Only assigns prospects where campaign_id IS NULL.
    """
    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    campaign = await db.get(Campaign, cid)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    prospect_ids = payload.get("prospect_ids", [])
    filters = payload.get("filters", {})

    if not prospect_ids and not filters:
        raise HTTPException(
            status_code=400,
            detail="Either prospect_ids or filters required",
        )

    assigned = 0

    if prospect_ids:
        for pid in prospect_ids:
            try:
                prospect = await db.get(Outreach, uuid.UUID(pid))
                if prospect and prospect.campaign_id is None:
                    prospect.campaign_id = campaign.id
                    prospect.updated_at = datetime.now(timezone.utc)
                    assigned += 1
            except Exception as e:
                logger.warning("Assign failed for %s: %s", str(pid)[:8], str(e))
    else:
        conditions = [
            Outreach.campaign_id.is_(None),
            Outreach.prospect_email.isnot(None),
            Outreach.prospect_email != "",
            Outreach.email_unsubscribed == False,
        ]

        if filters.get("trade_type"):
            conditions.append(
                Outreach.prospect_trade_type == filters["trade_type"]
            )
        if filters.get("city"):
            conditions.append(Outreach.city == filters["city"])
        if filters.get("state"):
            conditions.append(Outreach.state_code == filters["state"])
        if filters.get("status"):
            conditions.append(Outreach.status == filters["status"])

        result = await db.execute(
            select(Outreach).where(and_(*conditions))
        )
        prospects = result.scalars().all()
        for prospect in prospects:
            prospect.campaign_id = campaign.id
            prospect.updated_at = datetime.now(timezone.utc)
            assigned += 1

    return {"status": "assigned", "count": assigned}


@router.get("/campaigns/{campaign_id}/metrics")
async def get_campaign_metrics(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Per-campaign analytics: step performance, daily send volume (14 days),
    and conversion funnel.
    """
    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    campaign = await db.get(Campaign, cid)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    def _rate(num: int, denom: int) -> float:
        return round(num / denom * 100, 1) if denom else 0

    # Per-step performance
    step_result = await db.execute(
        select(
            OutreachEmail.sequence_step,
            func.count().label("sent"),
            func.count(OutreachEmail.opened_at).label("opened"),
            func.count(OutreachEmail.clicked_at).label("clicked"),
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.campaign_id == campaign.id,
                OutreachEmail.direction == "outbound",
            )
        )
        .group_by(OutreachEmail.sequence_step)
        .order_by(OutreachEmail.sequence_step)
    )

    step_reply_result = await db.execute(
        select(
            OutreachEmail.sequence_step,
            func.count().label("replied"),
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.campaign_id == campaign.id,
                OutreachEmail.direction == "inbound",
            )
        )
        .group_by(OutreachEmail.sequence_step)
    )
    reply_map = {
        row.sequence_step: row.replied for row in step_reply_result.all()
    }

    steps = []
    for row in step_result.all():
        step_sent = row.sent or 0
        step_replied = reply_map.get(row.sequence_step, 0)
        steps.append({
            "step": row.sequence_step,
            "sent": step_sent,
            "opened": row.opened or 0,
            "clicked": row.clicked or 0,
            "replied": step_replied,
            "open_rate": _rate(row.opened or 0, step_sent),
            "click_rate": _rate(row.clicked or 0, step_sent),
            "reply_rate": _rate(step_replied, step_sent),
        })

    # Daily send volume (last 14 days)
    fourteen_days_ago = datetime.now(timezone.utc) - timedelta(days=14)
    daily_result = await db.execute(
        select(
            func.date_trunc("day", OutreachEmail.sent_at).label("day"),
            func.count().label("sent"),
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.campaign_id == campaign.id,
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= fourteen_days_ago,
            )
        )
        .group_by(func.date_trunc("day", OutreachEmail.sent_at))
        .order_by(func.date_trunc("day", OutreachEmail.sent_at))
    )
    daily_sends = [
        {
            "date": row.day.isoformat() if row.day else None,
            "sent": row.sent,
        }
        for row in daily_result.all()
    ]

    # Funnel for this campaign
    funnel_result = await db.execute(
        select(Outreach.status, func.count()).where(
            Outreach.campaign_id == campaign.id
        ).group_by(Outreach.status)
    )
    funnel = {status: count for status, count in funnel_result.all()}

    return {
        "step_performance": steps,
        "daily_sends": daily_sends,
        "funnel": {
            "cold": funnel.get("cold", 0),
            "contacted": funnel.get("contacted", 0),
            "demo_scheduled": funnel.get("demo_scheduled", 0),
            "won": funnel.get("won", 0),
            "lost": funnel.get("lost", 0),
        },
    }
