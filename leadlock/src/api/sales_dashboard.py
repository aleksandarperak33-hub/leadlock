"""
Sales Engine — Campaign management and Command Center dashboard.
All endpoints require admin authentication.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.scrape_job import ScrapeJob
from src.models.sales_config import SalesEngineConfig
from src.api.dashboard import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


# === CAMPAIGNS ===

@router.get("/campaigns")
async def list_campaigns(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """List campaigns with pagination."""
    from src.models.campaign import Campaign

    count_result = await db.execute(select(func.count()).select_from(Campaign))
    total = count_result.scalar() or 0

    # Subquery: per-campaign outbound email stats (sent, opened)
    outbound_stats = (
        select(
            Outreach.campaign_id.label("campaign_id"),
            func.count().label("sent"),
            func.count(OutreachEmail.opened_at).label("opened"),
        )
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(OutreachEmail.direction == "outbound")
        .group_by(Outreach.campaign_id)
    ).subquery("outbound_stats")

    # Subquery: per-campaign inbound reply count
    inbound_stats = (
        select(
            Outreach.campaign_id.label("campaign_id"),
            func.count().label("replied"),
        )
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(OutreachEmail.direction == "inbound")
        .group_by(Outreach.campaign_id)
    ).subquery("inbound_stats")

    # Subquery: per-campaign prospect count
    prospect_stats = (
        select(
            Outreach.campaign_id.label("campaign_id"),
            func.count().label("prospect_count"),
        )
        .select_from(Outreach)
        .where(Outreach.campaign_id.isnot(None))
        .group_by(Outreach.campaign_id)
    ).subquery("prospect_stats")

    result = await db.execute(
        select(
            Campaign,
            func.coalesce(outbound_stats.c.sent, 0).label("calc_sent"),
            func.coalesce(outbound_stats.c.opened, 0).label("calc_opened"),
            func.coalesce(inbound_stats.c.replied, 0).label("calc_replied"),
            func.coalesce(prospect_stats.c.prospect_count, 0).label("calc_prospects"),
        )
        .outerjoin(outbound_stats, Campaign.id == outbound_stats.c.campaign_id)
        .outerjoin(inbound_stats, Campaign.id == inbound_stats.c.campaign_id)
        .outerjoin(prospect_stats, Campaign.id == prospect_stats.c.campaign_id)
        .order_by(desc(Campaign.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = result.all()

    return {
        "campaigns": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "status": c.status,
                "target_trades": c.target_trades or [],
                "target_locations": c.target_locations or [],
                "sequence_steps": c.sequence_steps or [],
                "daily_limit": c.daily_limit,
                "total_sent": calc_sent,
                "total_opened": calc_opened,
                "total_replied": calc_replied,
                "prospect_count": calc_prospects,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c, calc_sent, calc_opened, calc_replied, calc_prospects in rows
        ],
        "total": total,
        "page": page,
    }


@router.post("/campaigns")
async def create_campaign(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Create a new campaign."""
    from src.models.campaign import Campaign

    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    campaign = Campaign(
        name=name,
        description=payload.get("description"),
        status="draft",
        target_trades=payload.get("target_trades", []),
        target_locations=payload.get("target_locations", []),
        target_filters=payload.get("target_filters", {}),
        sequence_steps=payload.get("sequence_steps", []),
        daily_limit=payload.get("daily_limit", 25),
    )
    db.add(campaign)
    await db.flush()
    return {"status": "created", "id": str(campaign.id)}


@router.put("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Update a campaign."""
    from src.models.campaign import Campaign

    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    campaign = await db.get(Campaign, cid)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    allowed = ["name", "description", "target_trades", "target_locations", "target_filters", "sequence_steps", "daily_limit"]
    for field in allowed:
        if field in payload:
            setattr(campaign, field, payload[field])

    campaign.updated_at = datetime.now(timezone.utc)
    return {"status": "updated"}


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Pause an active campaign."""
    from src.models.campaign import Campaign

    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    campaign = await db.get(Campaign, cid)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "paused"
    campaign.updated_at = datetime.now(timezone.utc)
    return {"status": "paused"}


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Resume a paused campaign."""
    from src.models.campaign import Campaign

    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    campaign = await db.get(Campaign, cid)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "active"
    campaign.updated_at = datetime.now(timezone.utc)
    return {"status": "active"}


# === COMMAND CENTER ===

def _compute_send_window_label(config: SalesEngineConfig) -> dict:
    """Build a human-readable send window label + next open time."""
    from zoneinfo import ZoneInfo
    from src.workers.outreach_sequencer import is_within_send_window

    tz_name = getattr(config, "send_timezone", None) or "America/Chicago"
    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, Exception):
        tz = ZoneInfo("America/Chicago")

    now_local = datetime.now(tz)
    start_str = getattr(config, "send_hours_start", None) or "08:00"
    end_str = getattr(config, "send_hours_end", None) or "18:00"
    weekdays_only = getattr(config, "send_weekdays_only", True)
    is_active = is_within_send_window(config)

    label = f"{start_str}\u2013{end_str} {tz_name.split('/')[-1]}"
    if weekdays_only:
        label += " (Weekdays)"

    # Compute next_open
    next_open = None
    if not is_active:
        try:
            start_h, start_m = map(int, start_str.split(":"))
        except (ValueError, AttributeError):
            start_h, start_m = 8, 0

        candidate = now_local.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        if candidate <= now_local:
            candidate += timedelta(days=1)
        if weekdays_only:
            while candidate.weekday() >= 5:
                candidate += timedelta(days=1)
        next_open = candidate.isoformat()

    return {
        "is_active": is_active,
        "label": label,
        "hours": f"{start_str}\u2013{end_str}",
        "weekdays_only": weekdays_only,
        "next_open": next_open,
    }


async def _build_activity_feed(db: AsyncSession, limit: int = 20) -> list:
    """Merge recent email events and scrape completions into a unified feed."""
    activities = []

    # Recent outbound emails (sent)
    sent_result = await db.execute(
        select(
            OutreachEmail.id,
            OutreachEmail.sent_at,
            OutreachEmail.subject,
            OutreachEmail.sequence_step,
            Outreach.prospect_name,
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at.isnot(None),
            )
        )
        .order_by(desc(OutreachEmail.sent_at))
        .limit(limit)
    )
    for row in sent_result.all():
        activities.append({
            "type": "email_sent",
            "timestamp": row.sent_at.isoformat() if row.sent_at else None,
            "prospect_name": row.prospect_name,
            "detail": row.subject or f"Step {row.sequence_step}",
        })

    # Recent opens
    opened_result = await db.execute(
        select(
            OutreachEmail.opened_at,
            OutreachEmail.subject,
            Outreach.prospect_name,
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(OutreachEmail.opened_at.isnot(None))
        .order_by(desc(OutreachEmail.opened_at))
        .limit(limit)
    )
    for row in opened_result.all():
        activities.append({
            "type": "email_opened",
            "timestamp": row.opened_at.isoformat() if row.opened_at else None,
            "prospect_name": row.prospect_name,
            "detail": row.subject or "",
        })

    # Recent clicks
    clicked_result = await db.execute(
        select(
            OutreachEmail.clicked_at,
            OutreachEmail.subject,
            Outreach.prospect_name,
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(OutreachEmail.clicked_at.isnot(None))
        .order_by(desc(OutreachEmail.clicked_at))
        .limit(limit)
    )
    for row in clicked_result.all():
        activities.append({
            "type": "email_clicked",
            "timestamp": row.clicked_at.isoformat() if row.clicked_at else None,
            "prospect_name": row.prospect_name,
            "detail": row.subject or "",
        })

    # Recent replies (inbound)
    replied_result = await db.execute(
        select(
            OutreachEmail.sent_at,
            OutreachEmail.subject,
            Outreach.prospect_name,
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(OutreachEmail.direction == "inbound")
        .order_by(desc(OutreachEmail.sent_at))
        .limit(limit)
    )
    for row in replied_result.all():
        activities.append({
            "type": "email_replied",
            "timestamp": row.sent_at.isoformat() if row.sent_at else None,
            "prospect_name": row.prospect_name,
            "detail": row.subject or "",
        })

    # Recent bounces
    bounced_result = await db.execute(
        select(
            OutreachEmail.bounced_at,
            OutreachEmail.subject,
            Outreach.prospect_name,
        )
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(OutreachEmail.bounced_at.isnot(None))
        .order_by(desc(OutreachEmail.bounced_at))
        .limit(limit)
    )
    for row in bounced_result.all():
        activities.append({
            "type": "email_bounced",
            "timestamp": row.bounced_at.isoformat() if row.bounced_at else None,
            "prospect_name": row.prospect_name,
            "detail": row.subject or "",
        })

    # Recent scrape completions
    scrape_result = await db.execute(
        select(ScrapeJob)
        .where(ScrapeJob.status == "completed")
        .order_by(desc(ScrapeJob.completed_at))
        .limit(limit)
    )
    for j in scrape_result.scalars().all():
        activities.append({
            "type": "scrape_completed",
            "timestamp": j.completed_at.isoformat() if j.completed_at else None,
            "prospect_name": None,
            "detail": f"{j.trade_type} in {j.city}, {j.state_code} - {j.new_prospects_created} new",
        })

    # Recent unsubscribes
    unsub_result = await db.execute(
        select(
            Outreach.unsubscribed_at,
            Outreach.prospect_name,
            Outreach.prospect_company,
        )
        .where(Outreach.unsubscribed_at.isnot(None))
        .order_by(desc(Outreach.unsubscribed_at))
        .limit(limit)
    )
    for row in unsub_result.all():
        activities.append({
            "type": "unsubscribed",
            "timestamp": row.unsubscribed_at.isoformat() if row.unsubscribed_at else None,
            "prospect_name": row.prospect_name,
            "detail": row.prospect_company or "",
        })

    # Sort by timestamp descending, take top N
    activities.sort(key=lambda a: a["timestamp"] or "", reverse=True)
    return activities[:limit]


def _compute_alerts(data: dict) -> list:
    """Generate alerts from aggregated command center data."""
    alerts = []

    # Bounce rate alerts
    today = data.get("email_pipeline", {}).get("today", {})
    sent_today = today.get("sent", 0)
    bounced_today = today.get("bounced", 0)
    if sent_today > 0:
        bounce_rate = bounced_today / sent_today * 100
        if bounce_rate > 10:
            alerts.append({
                "severity": "critical",
                "type": "bounce_rate",
                "message": f"Bounce rate is {bounce_rate:.1f}% - above 10% threshold",
                "value": round(bounce_rate, 1),
            })
        elif bounce_rate > 5:
            alerts.append({
                "severity": "warning",
                "type": "bounce_rate",
                "message": f"Bounce rate is {bounce_rate:.1f}% - approaching 10% limit",
                "value": round(bounce_rate, 1),
            })

    # Worker health alerts
    workers = data.get("system", {}).get("workers", {})
    for name, info in workers.items():
        health = info.get("health", "unknown")
        if health == "unhealthy":
            alerts.append({
                "severity": "critical",
                "type": "worker_down",
                "message": f"Worker '{name}' is unhealthy - no heartbeat",
                "value": name,
            })
        elif health == "warning":
            alerts.append({
                "severity": "warning",
                "type": "worker_stale",
                "message": f"Worker '{name}' heartbeat is stale",
                "value": name,
            })

    # Budget alerts
    budget = data.get("system", {}).get("budget", {})
    pct_used = budget.get("pct_used", 0)
    if pct_used >= 100:
        alerts.append({
            "severity": "critical",
            "type": "budget_exceeded",
            "message": f"Monthly budget exceeded ({pct_used:.0f}%)",
            "value": pct_used,
        })
    elif pct_used >= (budget.get("alert_threshold", 0.8) * 100):
        alerts.append({
            "severity": "warning",
            "type": "budget_high",
            "message": f"Budget usage at {pct_used:.0f}%",
            "value": pct_used,
        })

    # Send window alert
    send_window = data.get("system", {}).get("send_window", {})
    if not send_window.get("is_active"):
        alerts.append({
            "severity": "info",
            "type": "send_window_closed",
            "message": "Send window is closed - emails paused",
            "value": send_window.get("next_open"),
        })

    return alerts


@router.get("/command-center")
async def get_command_center(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Aggregated command center data - single endpoint for the ops dashboard.
    Returns system status, email pipeline, funnel, scraper stats,
    sequence performance, geo performance, recent emails, activity feed, and alerts.
    """
    try:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 1. Config
        config_result = await db.execute(select(SalesEngineConfig).limit(1))
        config = config_result.scalar_one_or_none()

        engine_active = config.is_active if config else False

        # 2. Workers (Redis heartbeats)
        worker_status = {}
        try:
            from src.utils.dedup import get_redis
            redis = await get_redis()
            worker_names = ["scraper", "outreach_sequencer", "outreach_monitor", "system_health", "task_processor"]
            pause_map = {
                "scraper": "scraper_paused",
                "outreach_sequencer": "sequencer_paused",
                "outreach_monitor": "cleanup_paused",
            }

            for name in worker_names:
                key = f"leadlock:worker_health:{name}"
                heartbeat = await redis.get(key)
                paused = False
                if config and name in pause_map:
                    paused = bool(getattr(config, pause_map[name], False))

                if heartbeat:
                    last_beat = datetime.fromisoformat(
                        heartbeat.decode() if isinstance(heartbeat, bytes) else heartbeat
                    )
                    age_seconds = int((now - last_beat).total_seconds())
                    health = "healthy" if age_seconds < 600 else ("warning" if age_seconds < 1800 else "unhealthy")
                    worker_status[name] = {
                        "health": health,
                        "last_heartbeat": last_beat.isoformat(),
                        "age_seconds": age_seconds,
                        "paused": paused,
                    }
                else:
                    worker_status[name] = {
                        "health": "unknown",
                        "last_heartbeat": None,
                        "age_seconds": None,
                        "paused": paused,
                    }
        except Exception as e:
            logger.warning("Redis worker status failed: %s", str(e))

        # 3. Send window
        send_window = _compute_send_window_label(config) if config else {
            "is_active": False, "label": "Not configured", "hours": "", "weekdays_only": True, "next_open": None,
        }

        # 4. Budget
        cost_result = await db.execute(
            select(func.coalesce(func.sum(Outreach.total_cost_usd), 0.0)).where(
                Outreach.updated_at >= month_start
            )
        )
        budget_used = float(cost_result.scalar() or 0.0)
        monthly_limit = float(config.monthly_budget_usd) if config and config.monthly_budget_usd else 100.0
        alert_threshold = float(config.budget_alert_threshold) if config and config.budget_alert_threshold else 0.8
        pct_used = round(budget_used / monthly_limit * 100, 1) if monthly_limit > 0 else 0

        # 5. Funnel counts
        funnel_result = await db.execute(
            select(Outreach.status, func.count()).where(
                Outreach.source.isnot(None)
            ).group_by(Outreach.status)
        )
        funnel_raw = {status: count for status, count in funnel_result.all()}
        funnel = {
            "cold": funnel_raw.get("cold", 0),
            "contacted": funnel_raw.get("contacted", 0),
            "demo_scheduled": funnel_raw.get("demo_scheduled", 0),
            "demo_completed": funnel_raw.get("demo_completed", 0),
            "proposal_sent": funnel_raw.get("proposal_sent", 0),
            "won": funnel_raw.get("won", 0),
            "lost": funnel_raw.get("lost", 0),
        }

        # 6. Email metrics - today
        today_email = await db.execute(
            select(
                func.count().label("sent"),
                func.count(OutreachEmail.opened_at).label("opened"),
                func.count(OutreachEmail.clicked_at).label("clicked"),
                func.count(OutreachEmail.bounced_at).label("bounced"),
            ).where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sent_at >= today_start,
                )
            )
        )
        today_row = today_email.one()

        today_reply_result = await db.execute(
            select(func.count()).select_from(OutreachEmail).where(
                and_(
                    OutreachEmail.direction == "inbound",
                    OutreachEmail.sent_at >= today_start,
                )
            )
        )
        today_replies = today_reply_result.scalar() or 0

        today_unsub_result = await db.execute(
            select(func.count()).select_from(Outreach).where(
                and_(
                    Outreach.unsubscribed_at.isnot(None),
                    Outreach.unsubscribed_at >= today_start,
                )
            )
        )
        today_unsubs = today_unsub_result.scalar() or 0

        daily_limit = config.daily_email_limit if config else 50

        # 7. Email metrics - 30d
        email_30d = await db.execute(
            select(
                func.count().label("sent"),
                func.count(OutreachEmail.opened_at).label("opened"),
                func.count(OutreachEmail.clicked_at).label("clicked"),
                func.count(OutreachEmail.bounced_at).label("bounced"),
            ).where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sent_at >= thirty_days_ago,
                )
            )
        )
        period_row = email_30d.one()
        period_sent = period_row.sent or 0

        reply_30d_result = await db.execute(
            select(func.count()).select_from(OutreachEmail).where(
                and_(
                    OutreachEmail.direction == "inbound",
                    OutreachEmail.sent_at >= thirty_days_ago,
                )
            )
        )
        period_replies = reply_30d_result.scalar() or 0

        # 8. Email metrics - prev 30d (for trends)
        email_prev = await db.execute(
            select(
                func.count().label("sent"),
                func.count(OutreachEmail.opened_at).label("opened"),
                func.count(OutreachEmail.clicked_at).label("clicked"),
                func.count(OutreachEmail.bounced_at).label("bounced"),
            ).where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sent_at >= sixty_days_ago,
                    OutreachEmail.sent_at < thirty_days_ago,
                )
            )
        )
        prev_row = email_prev.one()
        prev_sent = prev_row.sent or 0

        reply_prev_result = await db.execute(
            select(func.count()).select_from(OutreachEmail).where(
                and_(
                    OutreachEmail.direction == "inbound",
                    OutreachEmail.sent_at >= sixty_days_ago,
                    OutreachEmail.sent_at < thirty_days_ago,
                )
            )
        )
        prev_replies = reply_prev_result.scalar() or 0

        def _rate(num, denom):
            return round(num / denom * 100, 1) if denom else 0

        # 9. Sequence step performance (30d)
        step_result = await db.execute(
            select(
                OutreachEmail.sequence_step,
                func.count().label("sent"),
                func.count(OutreachEmail.opened_at).label("opened"),
                func.count(OutreachEmail.clicked_at).label("clicked"),
            ).where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sent_at >= thirty_days_ago,
                )
            ).group_by(OutreachEmail.sequence_step)
            .order_by(OutreachEmail.sequence_step)
        )
        # Replies per step
        step_reply_result = await db.execute(
            select(
                OutreachEmail.sequence_step,
                func.count().label("replied"),
            ).where(
                and_(
                    OutreachEmail.direction == "inbound",
                    OutreachEmail.sent_at >= thirty_days_ago,
                )
            ).group_by(OutreachEmail.sequence_step)
        )
        step_replies_map = {row.sequence_step: row.replied for row in step_reply_result.all()}

        sequence_performance = []
        for row in step_result.all():
            step_sent = row.sent or 0
            step_replied = step_replies_map.get(row.sequence_step, 0)
            sequence_performance.append({
                "step": row.sequence_step,
                "sent": step_sent,
                "opened": row.opened or 0,
                "clicked": row.clicked or 0,
                "replied": step_replied,
                "open_rate": _rate(row.opened or 0, step_sent),
                "click_rate": _rate(row.clicked or 0, step_sent),
                "reply_rate": _rate(step_replied, step_sent),
            })

        # 10. Scraper stats - today
        scraper_today = await db.execute(
            select(
                func.coalesce(func.sum(ScrapeJob.new_prospects_created), 0).label("new_today"),
                func.coalesce(func.sum(ScrapeJob.duplicates_skipped), 0).label("dupes_today"),
            ).where(ScrapeJob.created_at >= today_start)
        )
        scraper_today_row = scraper_today.one()

        total_prospects_result = await db.execute(
            select(func.count()).select_from(Outreach).where(Outreach.source.isnot(None))
        )
        total_prospects = total_prospects_result.scalar() or 0

        scraped_today_result = await db.execute(
            select(func.count()).select_from(Outreach).where(
                and_(
                    Outreach.source.isnot(None),
                    Outreach.created_at >= today_start,
                )
            )
        )
        scraped_today = scraped_today_result.scalar() or 0

        # Target locations from config
        locations = config.target_locations if config and config.target_locations else []

        # 11. Geo performance (30d, top 20)
        geo_result = await db.execute(
            select(
                Outreach.city,
                Outreach.state_code,
                func.count(Outreach.id).label("prospects"),
            ).where(
                and_(
                    Outreach.source.isnot(None),
                    Outreach.city.isnot(None),
                )
            ).group_by(Outreach.city, Outreach.state_code)
            .order_by(desc(func.count(Outreach.id)))
            .limit(20)
        )
        geo_performance = []
        for row in geo_result.all():
            # Get email stats for this city
            geo_email = await db.execute(
                select(
                    func.count(OutreachEmail.id).label("sent"),
                    func.count(OutreachEmail.opened_at).label("opened"),
                ).join(Outreach, OutreachEmail.outreach_id == Outreach.id)
                .where(
                    and_(
                        OutreachEmail.direction == "outbound",
                        OutreachEmail.sent_at >= thirty_days_ago,
                        Outreach.city == row.city,
                        Outreach.state_code == row.state_code,
                    )
                )
            )
            ge = geo_email.one()
            # Replies per geo
            geo_reply = await db.execute(
                select(func.count()).select_from(OutreachEmail)
                .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
                .where(
                    and_(
                        OutreachEmail.direction == "inbound",
                        OutreachEmail.sent_at >= thirty_days_ago,
                        Outreach.city == row.city,
                        Outreach.state_code == row.state_code,
                    )
                )
            )
            geo_replies = geo_reply.scalar() or 0
            geo_sent = ge.sent or 0

            geo_performance.append({
                "city": row.city,
                "state": row.state_code,
                "prospects": row.prospects,
                "emails_sent": geo_sent,
                "open_rate": _rate(ge.opened or 0, geo_sent),
                "reply_rate": _rate(geo_replies, geo_sent),
            })

        # 11b. Total sent all-time
        total_sent_all_result = await db.execute(
            select(func.count()).select_from(OutreachEmail).where(
                OutreachEmail.direction == "outbound"
            )
        )
        total_sent_all_time = total_sent_all_result.scalar() or 0

        # 12. Recent emails (last 10)
        recent_emails_result = await db.execute(
            select(
                OutreachEmail.id,
                OutreachEmail.subject,
                OutreachEmail.sequence_step,
                OutreachEmail.sent_at,
                OutreachEmail.opened_at,
                OutreachEmail.clicked_at,
                OutreachEmail.bounced_at,
                OutreachEmail.body_text,
                Outreach.prospect_name,
            )
            .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
            .where(OutreachEmail.direction == "outbound")
            .order_by(desc(OutreachEmail.sent_at))
            .limit(10)
        )
        recent_emails = []
        for row in recent_emails_result.all():
            body_preview = (row.body_text or "")[:120]
            recent_emails.append({
                "id": str(row.id),
                "prospect_name": row.prospect_name,
                "subject": row.subject,
                "step": row.sequence_step,
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                "opened_at": row.opened_at.isoformat() if row.opened_at else None,
                "clicked_at": row.clicked_at.isoformat() if row.clicked_at else None,
                "bounced_at": row.bounced_at.isoformat() if row.bounced_at else None,
                "body_preview": body_preview,
            })

        # 13. Activity feed
        activity = await _build_activity_feed(db, limit=20)

        # Assemble response
        data = {
            "system": {
                "engine_active": engine_active,
                "workers": worker_status,
                "send_window": send_window,
                "budget": {
                    "used_this_month": round(budget_used, 2),
                    "monthly_limit": monthly_limit,
                    "pct_used": pct_used,
                    "alert_threshold": alert_threshold,
                },
            },
            "email_pipeline": {
                "sent_today": today_row.sent or 0,
                "total_sent_all_time": total_sent_all_time,
                "today": {
                    "sent": today_row.sent or 0,
                    "daily_limit": daily_limit,
                    "opened": today_row.opened or 0,
                    "clicked": today_row.clicked or 0,
                    "replied": today_replies,
                    "bounced": today_row.bounced or 0,
                    "unsubscribed": today_unsubs,
                },
                "period_30d": {
                    "sent": period_sent,
                    "opened": period_row.opened or 0,
                    "clicked": period_row.clicked or 0,
                    "replied": period_replies,
                    "bounced": period_row.bounced or 0,
                    "open_rate": _rate(period_row.opened or 0, period_sent),
                    "click_rate": _rate(period_row.clicked or 0, period_sent),
                    "reply_rate": _rate(period_replies, period_sent),
                    "bounce_rate": _rate(period_row.bounced or 0, period_sent),
                },
                "prev_30d": {
                    "open_rate": _rate(prev_row.opened or 0, prev_sent),
                    "click_rate": _rate(prev_row.clicked or 0, prev_sent),
                    "reply_rate": _rate(prev_replies, prev_sent),
                    "bounce_rate": _rate(prev_row.bounced or 0, prev_sent),
                },
            },
            "funnel": funnel,
            "scraper": {
                "total_prospects": total_prospects,
                "scraped_today": scraped_today,
                "new_today": scraper_today_row.new_today,
                "dupes_today": scraper_today_row.dupes_today,
                "locations": locations,
            },
            "sequence_performance": sequence_performance,
            "geo_performance": geo_performance,
            "recent_emails": recent_emails,
            "activity": activity,
        }

        # 14. Alerts (computed from assembled data)
        data["alerts"] = _compute_alerts(data)

        return data

    except Exception as e:
        logger.error("Command center endpoint failed: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to load command center data")
