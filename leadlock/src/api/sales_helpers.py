"""
Sales Engine helpers — send window label, activity feed, alert computation.
Extracted from sales_dashboard.py for file size compliance.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.scrape_job import ScrapeJob
from src.models.sales_config import SalesEngineConfig

logger = logging.getLogger(__name__)


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
