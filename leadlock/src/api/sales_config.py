"""
Sales Engine — Configuration, metrics, worker controls, templates, and insights.
All endpoints require admin authentication.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.scrape_job import ScrapeJob
from src.models.sales_config import SalesEngineConfig
from src.api.dashboard import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/config")
async def get_sales_config(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get sales engine configuration."""
    result = await db.execute(select(SalesEngineConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        # Create default config
        config = SalesEngineConfig()
        db.add(config)
        await db.flush()

    return {
        "id": str(config.id),
        "is_active": config.is_active,
        "target_trade_types": config.target_trade_types or [],
        "target_locations": config.target_locations or [],
        "daily_email_limit": config.daily_email_limit,
        "daily_scrape_limit": config.daily_scrape_limit,
        "sequence_delay_hours": config.sequence_delay_hours,
        "max_sequence_steps": config.max_sequence_steps,
        "from_email": config.from_email,
        "from_name": config.from_name,
        "sender_name": config.sender_name,
        "booking_url": config.booking_url,
        "reply_to_email": config.reply_to_email,
        "company_address": config.company_address,
        "sms_after_email_reply": config.sms_after_email_reply,
        "sms_from_phone": config.sms_from_phone,
        "email_templates": config.email_templates,
        "scraper_interval_minutes": config.scraper_interval_minutes,
        "variant_cooldown_days": config.variant_cooldown_days,
        "send_hours_start": config.send_hours_start,
        "send_hours_end": config.send_hours_end,
        "send_timezone": config.send_timezone,
        "send_weekdays_only": config.send_weekdays_only,
        "scraper_paused": config.scraper_paused,
        "sequencer_paused": config.sequencer_paused,
        "cleanup_paused": config.cleanup_paused,
        "monthly_budget_usd": config.monthly_budget_usd,
        "budget_alert_threshold": config.budget_alert_threshold,
    }


@router.put("/config")
async def update_sales_config(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Update sales engine configuration."""
    result = await db.execute(select(SalesEngineConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        config = SalesEngineConfig()
        db.add(config)
        await db.flush()

    allowed_fields = [
        "is_active", "target_trade_types", "target_locations",
        "daily_email_limit", "daily_scrape_limit", "sequence_delay_hours",
        "max_sequence_steps", "from_email", "from_name", "sender_name", "booking_url", "reply_to_email",
        "company_address", "sms_after_email_reply", "sms_from_phone",
        "email_templates",
        "scraper_interval_minutes", "variant_cooldown_days",
        "send_hours_start", "send_hours_end", "send_timezone", "send_weekdays_only",
        "scraper_paused", "sequencer_paused", "cleanup_paused",
        "monthly_budget_usd", "budget_alert_threshold",
    ]

    for field in allowed_fields:
        if field in payload:
            setattr(config, field, payload[field])

    config.updated_at = datetime.now(timezone.utc)

    # Commit first, THEN invalidate cache -- prevents TOCTOU where workers
    # read stale data from uncommitted transaction and re-cache it
    await db.commit()

    # Invalidate cached config so workers pick up changes immediately
    from src.services.config_cache import invalidate_sales_config
    await invalidate_sales_config()

    # Notify workers via event bus
    from src.services.event_bus import publish_event
    await publish_event("config_changed")

    return {"status": "updated"}


@router.get("/metrics")
async def get_sales_metrics(
    period: str = Query(default="30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Sales engine performance metrics."""
    days = int(period.replace("d", ""))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Prospect counts by status
    status_counts = {}
    status_result = await db.execute(
        select(Outreach.status, func.count()).where(
            Outreach.source.isnot(None)  # Only engine-sourced prospects
        ).group_by(Outreach.status)
    )
    for status, count in status_result.all():
        status_counts[status] = count

    # Email metrics
    email_stats = await db.execute(
        select(
            func.count().label("total_sent"),
            func.count(OutreachEmail.opened_at).label("opened"),
            func.count(OutreachEmail.clicked_at).label("clicked"),
            func.count(OutreachEmail.bounced_at).label("bounced"),
        ).where(
            and_(
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= since,
            )
        )
    )
    email_row = email_stats.one()
    total_sent = email_row.total_sent or 0
    opened = email_row.opened or 0
    clicked = email_row.clicked or 0

    # Reply count
    reply_result = await db.execute(
        select(func.count()).select_from(OutreachEmail).where(
            and_(
                OutreachEmail.direction == "inbound",
                OutreachEmail.sent_at >= since,
            )
        )
    )
    replies = reply_result.scalar() or 0

    # Total cost
    cost_result = await db.execute(
        select(func.coalesce(func.sum(Outreach.total_cost_usd), 0.0)).where(
            Outreach.source.isnot(None)
        )
    )
    total_cost = cost_result.scalar() or 0.0

    # Scrape job stats
    scrape_result = await db.execute(
        select(
            func.count().label("total_jobs"),
            func.coalesce(func.sum(ScrapeJob.new_prospects_created), 0).label("total_scraped"),
            func.coalesce(func.sum(ScrapeJob.api_cost_usd), 0.0).label("scrape_cost"),
        ).where(ScrapeJob.created_at >= since)
    )
    scrape_row = scrape_result.one()

    return {
        "period": period,
        "prospects": {
            "total": sum(status_counts.values()),
            "by_status": status_counts,
        },
        "emails": {
            "sent": total_sent,
            "opened": opened,
            "clicked": clicked,
            "bounced": email_row.bounced or 0,
            "replied": replies,
            "open_rate": round(opened / total_sent * 100, 1) if total_sent else 0,
            "click_rate": round(clicked / total_sent * 100, 1) if total_sent else 0,
            "reply_rate": round(replies / total_sent * 100, 1) if total_sent else 0,
            "bounce_rate": round((email_row.bounced or 0) / total_sent * 100, 1) if total_sent else 0,
        },
        "scraping": {
            "jobs_run": scrape_row.total_jobs,
            "prospects_found": scrape_row.total_scraped,
            "scrape_cost": round(float(scrape_row.scrape_cost), 2),
        },
        "cost": {
            "total": round(float(total_cost), 2),
        },
        "conversions": {
            "demos_booked": status_counts.get("demo_scheduled", 0),
            "won": status_counts.get("won", 0),
        },
    }


# === WORKER STATUS & CONTROLS ===

@router.get("/worker-status")
async def get_worker_status(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get worker health status from Redis heartbeats."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        workers = ["scraper", "outreach_sequencer", "outreach_monitor", "system_health", "task_processor"]
        status = {}

        for name in workers:
            key = f"leadlock:worker_health:{name}"
            heartbeat = await redis.get(key)
            if heartbeat:
                last_beat = datetime.fromisoformat(heartbeat.decode() if isinstance(heartbeat, bytes) else heartbeat)
                age_seconds = (datetime.now(timezone.utc) - last_beat).total_seconds()
                health = "healthy" if age_seconds < 600 else ("warning" if age_seconds < 1800 else "unhealthy")
                status[name] = {
                    "last_heartbeat": last_beat.isoformat(),
                    "age_seconds": int(age_seconds),
                    "health": health,
                }
            else:
                status[name] = {
                    "last_heartbeat": None,
                    "age_seconds": None,
                    "health": "unknown",
                }

        # Bounce rate check
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        sent_result = await db.execute(
            select(func.count()).select_from(OutreachEmail).where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sent_at >= today_start,
                )
            )
        )
        sent_today = sent_result.scalar() or 0

        bounced_result = await db.execute(
            select(func.count()).select_from(OutreachEmail).where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.bounced_at.isnot(None),
                    OutreachEmail.sent_at >= today_start,
                )
            )
        )
        bounced_today = bounced_result.scalar() or 0

        bounce_rate = round(bounced_today / sent_today * 100, 1) if sent_today else 0.0

        return {
            "workers": status,
            "alerts": {
                "bounce_rate": bounce_rate,
                "bounce_rate_alert": bounce_rate > 10,
            },
        }
    except Exception as e:
        logger.error("Worker status check failed: %s", str(e))
        return {"workers": {}, "alerts": {}, "error": "Failed to check worker status"}


@router.post("/workers/{worker_name}/pause")
async def pause_worker(
    worker_name: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Pause a worker by name."""
    valid_workers = {"scraper": "scraper_paused", "sequencer": "sequencer_paused", "cleanup": "cleanup_paused"}
    field = valid_workers.get(worker_name)
    if not field:
        raise HTTPException(status_code=400, detail=f"Unknown worker: {worker_name}")

    result = await db.execute(select(SalesEngineConfig).limit(1))
    config = result.scalar_one_or_none()
    if config and hasattr(config, field):
        setattr(config, field, True)
        config.updated_at = datetime.now(timezone.utc)
    return {"status": "paused", "worker": worker_name}


@router.post("/workers/{worker_name}/resume")
async def resume_worker(
    worker_name: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Resume a paused worker."""
    valid_workers = {"scraper": "scraper_paused", "sequencer": "sequencer_paused", "cleanup": "cleanup_paused"}
    field = valid_workers.get(worker_name)
    if not field:
        raise HTTPException(status_code=400, detail=f"Unknown worker: {worker_name}")

    result = await db.execute(select(SalesEngineConfig).limit(1))
    config = result.scalar_one_or_none()
    if config and hasattr(config, field):
        setattr(config, field, False)
        config.updated_at = datetime.now(timezone.utc)
    return {"status": "resumed", "worker": worker_name}


# === TEMPLATES ===

@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """List all email templates."""
    from src.models.email_template import EmailTemplate

    result = await db.execute(
        select(EmailTemplate).order_by(EmailTemplate.created_at)
    )
    templates = result.scalars().all()

    return {
        "templates": [
            {
                "id": str(t.id),
                "name": t.name,
                "step_type": t.step_type,
                "subject_template": t.subject_template,
                "body_template": t.body_template,
                "ai_instructions": t.ai_instructions,
                "is_ai_generated": t.is_ai_generated,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in templates
        ],
    }


@router.post("/templates")
async def create_template(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Create an email template."""
    from src.models.email_template import EmailTemplate

    name = payload.get("name", "").strip()
    step_type = payload.get("step_type", "").strip()
    if not name or not step_type:
        raise HTTPException(status_code=400, detail="name and step_type are required")

    template = EmailTemplate(
        name=name,
        step_type=step_type,
        subject_template=payload.get("subject_template"),
        body_template=payload.get("body_template"),
        ai_instructions=payload.get("ai_instructions"),
        is_ai_generated=payload.get("is_ai_generated", True),
    )
    db.add(template)
    await db.flush()
    return {"status": "created", "id": str(template.id)}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Update an email template."""
    from src.models.email_template import EmailTemplate

    try:
        tid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")
    template = await db.get(EmailTemplate, tid)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    allowed = ["name", "step_type", "subject_template", "body_template", "ai_instructions", "is_ai_generated"]
    for field in allowed:
        if field in payload:
            setattr(template, field, payload[field])

    return {"status": "updated"}


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Delete an email template."""
    from src.models.email_template import EmailTemplate

    try:
        tid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")
    template = await db.get(EmailTemplate, tid)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(template)
    return {"status": "deleted"}


# === INSIGHTS ===

@router.get("/insights")
async def get_insights(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get learning insights summary for the dashboard."""
    from src.services.learning import get_insights_summary
    return await get_insights_summary()
