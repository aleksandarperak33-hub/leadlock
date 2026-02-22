"""
Agent fleet service — provides status, activity, queue, and cost data
for the Agent Army Dashboard.

Reads worker heartbeats and cost hashes from Redis, task records from
PostgreSQL, and SOUL.md identity summaries from disk (cached after first load).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, and_, case

from src.database import async_session_factory
from src.models.task_queue import TaskQueue
from src.utils.dedup import get_redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SOUL.md cache (lazy, permanent)
# ---------------------------------------------------------------------------
_SOUL_CACHE: dict[str, str] = {}

_SOUL_FILE_MAP: dict[str, str | None] = {
    "ab_test_engine": "ab_testing.md",
    "warmup_optimizer": "warmup_optimizer.md",
    "winback_agent": "winback.md",
    "referral_agent": "prospect_researcher.md",
    "reflection_agent": "reflection.md",
    "outreach_health": "outreach_health.md",
    "outreach_sequencer": None,
    "scraper": None,
    "task_processor": None,
    "outreach_cleanup": None,
    "deliverability_monitor": None,
    "health_monitor": None,
    "crm_sync": None,
    "followup_scheduler": None,
    "booking_reminder": None,
    "lead_lifecycle": None,
    "stuck_lead_sweeper": None,
    "retry_worker": None,
    "registration_poller": None,
}

_SOULS_DIR = Path(__file__).resolve().parent.parent / "agents" / "souls"


def _parse_soul_identity(path: Path) -> str:
    """Synchronous helper — reads file and extracts Identity section."""
    text = path.read_text(encoding="utf-8")
    marker = "## Identity"
    idx = text.find(marker)
    if idx == -1:
        return ""
    rest = text[idx + len(marker):]
    end = rest.find("\n## ")
    return rest[:end].strip() if end != -1 else rest.strip()


async def _load_soul_summary(agent_name: str) -> str:
    """Return the Identity section of the agent's SOUL.md, cached after first success."""
    if agent_name in _SOUL_CACHE:
        return _SOUL_CACHE[agent_name]

    filename = _SOUL_FILE_MAP.get(agent_name)
    if filename is None:
        return ""

    path = _SOULS_DIR / filename
    try:
        summary = await asyncio.to_thread(_parse_soul_identity, path)
        _SOUL_CACHE[agent_name] = summary
        return summary
    except FileNotFoundError:
        logger.warning("SOUL.md not found for %s at %s", agent_name, path)
        return ""
    except Exception:
        logger.exception("Failed to load SOUL.md for %s", agent_name)
        return ""


# ---------------------------------------------------------------------------
# Agent registry (static metadata)
# ---------------------------------------------------------------------------
AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    "ab_test_engine": {
        "display_name": "A/B Testing Engine",
        "description": "Optimizes subject lines through controlled experiments",
        "schedule": "Every 6 hours",
        "icon": "flask-conical",
        "color": "purple",
        "uses_ai": True,
        "poll_interval": 21600,
        "task_types": ["generate_ab_variants"],
    },
    "warmup_optimizer": {
        "display_name": "Warmup Optimizer",
        "description": "Adjusts email send volumes based on reputation signals",
        "schedule": "Every 6 hours",
        "icon": "thermometer",
        "color": "blue",
        "uses_ai": True,
        "poll_interval": 21600,
        "task_types": ["warmup_adjustment"],
    },
    "winback_agent": {
        "display_name": "Win-Back Agent",
        "description": "Re-engages cold prospects with fresh angles",
        "schedule": "Daily",
        "icon": "refresh-cw",
        "color": "amber",
        "uses_ai": True,
        "poll_interval": 86400,
        "task_types": ["winback_sequence"],
    },
    "referral_agent": {
        "display_name": "Referral Agent",
        "description": "Generates referral requests for active clients",
        "schedule": "Daily",
        "icon": "gift",
        "color": "pink",
        "uses_ai": True,
        "poll_interval": 86400,
        "task_types": ["send_referral"],
    },
    "reflection_agent": {
        "display_name": "Reflection Agent",
        "description": "Weekly performance audit across all agents",
        "schedule": "Weekly",
        "icon": "brain",
        "color": "indigo",
        "uses_ai": True,
        "poll_interval": 604800,
        "task_types": ["weekly_reflection"],
    },
    "outreach_health": {
        "display_name": "Outreach Health Monitor",
        "description": "Detects pipeline anomalies and alert fatigue",
        "schedule": "Every 15 min",
        "icon": "heart-pulse",
        "color": "emerald",
        "uses_ai": False,
        "poll_interval": 900,
        "task_types": ["health_check"],
    },
    "outreach_sequencer": {
        "display_name": "Outreach Sequencer",
        "description": "Executes multi-step outreach sequences for active campaigns",
        "schedule": "Every 30 min",
        "icon": "mail",
        "color": "red",
        "uses_ai": True,
        "poll_interval": 1800,
        "task_types": ["outreach_sequence"],
    },
    "scraper": {
        "display_name": "Prospect Scraper",
        "description": "Discovers and enriches new prospect records",
        "schedule": "Every 15 min",
        "icon": "search",
        "color": "cyan",
        "uses_ai": False,
        "poll_interval": 900,
        "task_types": ["scrape_prospects"],
    },
    "task_processor": {
        "display_name": "Task Processor",
        "description": "Processes queued background tasks from all agents",
        "schedule": "Every 10s",
        "icon": "cog",
        "color": "gray",
        "uses_ai": False,
        "poll_interval": 10,
        "task_types": ["process_task"],
    },
    "outreach_cleanup": {
        "display_name": "Sequence Cleanup",
        "description": "Removes expired and orphaned outreach sequences",
        "schedule": "Every 4 hrs",
        "icon": "trash-2",
        "color": "slate",
        "uses_ai": False,
        "poll_interval": 14400,
        "task_types": ["cleanup_sequences"],
    },
    "deliverability_monitor": {
        "display_name": "Deliverability Monitor",
        "description": "Tracks bounce rates, spam complaints, and sender reputation",
        "schedule": "Every 5 min",
        "icon": "shield-check",
        "color": "teal",
        "uses_ai": False,
        "poll_interval": 300,
        "task_types": ["check_deliverability"],
    },
    "health_monitor": {
        "display_name": "System Health",
        "description": "Monitors infrastructure health and service availability",
        "schedule": "Every 5 min",
        "icon": "activity",
        "color": "green",
        "uses_ai": False,
        "poll_interval": 300,
        "task_types": ["system_health_check"],
    },
    "crm_sync": {
        "display_name": "CRM Sync",
        "description": "Synchronizes lead and appointment data with external CRMs",
        "schedule": "Every 30s",
        "icon": "database",
        "color": "orange",
        "uses_ai": False,
        "poll_interval": 30,
        "task_types": ["sync_crm"],
    },
    "followup_scheduler": {
        "display_name": "Follow-Up Scheduler",
        "description": "Schedules and dispatches follow-up messages for active leads",
        "schedule": "Every 60s",
        "icon": "send",
        "color": "sky",
        "uses_ai": False,
        "poll_interval": 60,
        "task_types": ["schedule_followup"],
    },
    "booking_reminder": {
        "display_name": "Booking Reminder",
        "description": "Sends appointment reminders to booked leads",
        "schedule": "Every 30 min",
        "icon": "bell",
        "color": "yellow",
        "uses_ai": False,
        "poll_interval": 1800,
        "task_types": ["send_booking_reminder"],
    },
    "lead_lifecycle": {
        "display_name": "Lead Lifecycle",
        "description": "Advances leads through lifecycle stages based on activity",
        "schedule": "Every 30 min",
        "icon": "git-branch",
        "color": "lime",
        "uses_ai": False,
        "poll_interval": 1800,
        "task_types": ["advance_lifecycle"],
    },
    "stuck_lead_sweeper": {
        "display_name": "Stuck Lead Sweeper",
        "description": "Detects and rescues leads stuck in intermediate states",
        "schedule": "Every 5 min",
        "icon": "alert-triangle",
        "color": "rose",
        "uses_ai": False,
        "poll_interval": 300,
        "task_types": ["sweep_stuck_leads"],
    },
    "retry_worker": {
        "display_name": "Retry Queue",
        "description": "Retries failed tasks with exponential backoff",
        "schedule": "Every 60s",
        "icon": "rotate-cw",
        "color": "stone",
        "uses_ai": False,
        "poll_interval": 60,
        "task_types": ["retry_failed"],
    },
    "registration_poller": {
        "display_name": "A2P Registration",
        "description": "Polls carrier registration status for A2P compliance",
        "schedule": "Every 5 min",
        "icon": "shield",
        "color": "violet",
        "uses_ai": False,
        "poll_interval": 300,
        "task_types": ["poll_registration"],
    },
}

# Flat lookup: task_type -> agent_name
_TASK_TYPE_TO_AGENT: dict[str, str] = {
    tt: name
    for name, meta in AGENT_REGISTRY.items()
    for tt in meta["task_types"]
}

# All task types across the fleet
_ALL_TASK_TYPES: list[str] = list(_TASK_TYPE_TO_AGENT.keys())


# ---------------------------------------------------------------------------
# Agent feature flags
# ---------------------------------------------------------------------------
_AGENT_FLAG_MAP: dict[str, str] = {
    "ab_test_engine": "agent_ab_test_engine",
    "warmup_optimizer": "agent_warmup_optimizer",
    "winback_agent": "agent_winback_agent",
    "referral_agent": "agent_referral_agent",
    "reflection_agent": "agent_reflection_agent",
}


def _is_agent_enabled(agent_name: str) -> bool:
    """Check feature flag for an agent. Core agents without a flag are always enabled."""
    from src.config import get_settings

    settings = get_settings()
    flag_attr = _AGENT_FLAG_MAP.get(agent_name)
    if not flag_attr:
        return True
    return getattr(settings, flag_attr, True)


# ---------------------------------------------------------------------------
# Fleet status
# ---------------------------------------------------------------------------
_FLEET_CACHE_KEY = "leadlock:fleet_status_cache"
_FLEET_CACHE_TTL = 30  # seconds


async def get_fleet_status() -> dict:
    """Return health, status, and cost summary for every agent."""
    redis = await get_redis()

    # Check cache first
    cached = await redis.get(_FLEET_CACHE_KEY)
    if cached:
        return json.loads(cached)

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    agent_names = list(AGENT_REGISTRY.keys())

    # --- Redis: heartbeats + costs (parallel pipeline) ---
    heartbeat_keys = [f"leadlock:worker_health:{n}" for n in agent_names]
    heartbeats = await redis.mget(*heartbeat_keys)
    cost_hash = await redis.hgetall(f"leadlock:agent_costs:{today_str}") or {}

    # --- PostgreSQL: today's task counts grouped by task_type ---
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    task_counts: dict[str, int] = {}
    try:
        async with async_session_factory() as session:
            rows = await session.execute(
                select(
                    TaskQueue.task_type,
                    func.count(TaskQueue.id),
                ).where(
                    and_(
                        TaskQueue.task_type.in_(_ALL_TASK_TYPES),
                        TaskQueue.created_at >= day_start,
                    )
                ).group_by(TaskQueue.task_type)
            )
            for task_type, count in rows:
                agent = _TASK_TYPE_TO_AGENT.get(task_type)
                if agent:
                    task_counts[agent] = task_counts.get(agent, 0) + count
    except Exception:
        logger.exception("Failed to query task counts for fleet status")

    # --- Build per-agent status ---
    agents: list[dict] = []
    health_summary = {"healthy": 0, "warning": 0, "unhealthy": 0}

    for idx, name in enumerate(agent_names):
        meta = AGENT_REGISTRY[name]
        hb_raw = heartbeats[idx]
        poll = meta["poll_interval"]
        cost_today = float(cost_hash.get(name, 0))
        tasks_today = task_counts.get(name, 0)

        # Compute health
        if hb_raw:
            try:
                hb_time = datetime.fromisoformat(hb_raw)
                age_s = (now - hb_time).total_seconds()
            except (ValueError, TypeError):
                age_s = float("inf")
        else:
            age_s = float("inf")

        if age_s < poll * 1.5:
            health = "healthy"
        elif age_s < poll * 3:
            health = "warning"
        else:
            health = "unhealthy"

        # Check feature flag
        enabled = _is_agent_enabled(name)

        # Derive status
        if not enabled:
            status = "disabled"
            health = "disabled"
        elif health == "unhealthy":
            status = "error"
        elif tasks_today == 0 and health == "healthy":
            status = "idle"
        else:
            status = "running"

        if not enabled:
            health_summary["disabled"] = health_summary.get("disabled", 0) + 1
        else:
            health_summary[health] += 1

        agents.append({
            "name": name,
            **meta,
            "enabled": enabled,
            "health": health,
            "status": status,
            "last_heartbeat": hb_raw,
            "cost_today": cost_today,
            "tasks_today": tasks_today,
        })

    result = {
        "fleet_summary": {
            "total_agents": len(agent_names),
            **health_summary,
            "total_cost_today": sum(a["cost_today"] for a in agents),
            "total_tasks_today": sum(a["tasks_today"] for a in agents),
            "updated_at": now.isoformat(),
        },
        "agents": agents,
    }

    # Cache for 30 seconds
    try:
        await redis.set(_FLEET_CACHE_KEY, json.dumps(result), ex=_FLEET_CACHE_TTL)
    except Exception:
        logger.warning("Failed to cache fleet status in Redis")

    return result


# ---------------------------------------------------------------------------
# Agent activity detail
# ---------------------------------------------------------------------------
async def get_agent_activity(name: str, limit: int = 20) -> dict:
    """Return recent tasks, cost history, 7-day metrics, and SOUL summary."""
    if name not in AGENT_REGISTRY:
        raise ValueError(f"Unknown agent: {name}")

    meta = AGENT_REGISTRY[name]
    task_types = meta["task_types"]
    redis = await get_redis()
    now = datetime.now(timezone.utc)

    # --- Recent tasks from PostgreSQL ---
    recent_tasks: list[dict] = []
    metrics_7d = {"total_tasks": 0, "success_rate": 0.0, "avg_duration_s": 0.0, "total_cost": 0.0}
    seven_days_ago = now - timedelta(days=7)

    try:
        async with async_session_factory() as session:
            rows = (await session.execute(
                select(TaskQueue)
                .where(TaskQueue.task_type.in_(task_types))
                .order_by(TaskQueue.created_at.desc())
                .limit(limit)
            )).scalars().all()

            for t in rows:
                duration = None
                if t.started_at and t.completed_at:
                    duration = (t.completed_at - t.started_at).total_seconds()
                recent_tasks.append({
                    "id": str(t.id),
                    "task_type": t.task_type,
                    "status": t.status,
                    "priority": t.priority,
                    "retry_count": t.retry_count,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "started_at": t.started_at.isoformat() if t.started_at else None,
                    "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                    "duration_s": duration,
                    "error_message": t.error_message,
                })

            # 7-day metrics
            week_rows = (await session.execute(
                select(
                    func.count(TaskQueue.id),
                    func.sum(case(
                        (TaskQueue.status == "completed", 1),
                        else_=0,
                    )),
                    func.avg(
                        func.extract("epoch", TaskQueue.completed_at)
                        - func.extract("epoch", TaskQueue.started_at)
                    ).filter(
                        TaskQueue.completed_at.isnot(None),
                        TaskQueue.started_at.isnot(None),
                    ),
                ).where(
                    and_(
                        TaskQueue.task_type.in_(task_types),
                        TaskQueue.created_at >= seven_days_ago,
                    )
                )
            )).one()

            total = week_rows[0] or 0
            success = week_rows[1] or 0
            avg_dur = float(week_rows[2]) if week_rows[2] else 0.0
            metrics_7d = {
                "total_tasks": total,
                "success_rate": round(success / total, 4) if total else 0.0,
                "avg_duration_s": round(avg_dur, 2),
                "total_cost": 0.0,  # filled from Redis below
            }
    except Exception:
        logger.exception("Failed to query tasks for agent %s", name)

    # --- Cost history from Redis (last 30 days) ---
    cost_history: list[dict] = []
    cost_7d_total = 0.0
    for offset in range(30):
        day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        raw = await redis.hget(f"leadlock:agent_costs:{day}", name)
        cost = float(raw) if raw else 0.0
        cost_history.append({"date": day, "cost": cost})
        if offset < 7:
            cost_7d_total += cost

    metrics_7d["total_cost"] = round(cost_7d_total, 4)
    cost_history.reverse()  # chronological order

    soul_summary = await _load_soul_summary(name)

    return {
        "agent": {"name": name, **meta},
        "recent_tasks": recent_tasks,
        "cost_history": cost_history,
        "metrics_7d": metrics_7d,
        "soul_summary": soul_summary,
    }


# ---------------------------------------------------------------------------
# Task queue browser
# ---------------------------------------------------------------------------
async def get_task_queue(
    status: str = "all",
    task_type: str = "all",
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Return paginated task queue with optional filters."""
    try:
        async with async_session_factory() as session:
            base = select(TaskQueue).where(TaskQueue.task_type.in_(_ALL_TASK_TYPES))

            if status != "all":
                base = base.where(TaskQueue.status == status)
            if task_type != "all":
                base = base.where(TaskQueue.task_type == task_type)

            # Total count for pagination
            count_q = select(func.count()).select_from(base.subquery())
            total = (await session.execute(count_q)).scalar() or 0

            # Paginated results
            offset = (page - 1) * per_page
            rows = (await session.execute(
                base.order_by(TaskQueue.created_at.desc())
                .limit(per_page)
                .offset(offset)
            )).scalars().all()

            tasks = []
            for t in rows:
                duration = None
                if t.started_at and t.completed_at:
                    duration = (t.completed_at - t.started_at).total_seconds()
                tasks.append({
                    "id": str(t.id),
                    "task_type": t.task_type,
                    "status": t.status,
                    "priority": t.priority,
                    "retry_count": t.retry_count,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "duration_s": duration,
                    "error_message": t.error_message,
                    "agent": _TASK_TYPE_TO_AGENT.get(t.task_type),
                })

            # Status counts (unfiltered by status/type for dashboard totals)
            status_rows = await session.execute(
                select(TaskQueue.status, func.count(TaskQueue.id))
                .where(TaskQueue.task_type.in_(_ALL_TASK_TYPES))
                .group_by(TaskQueue.status)
            )
            status_counts = {s: c for s, c in status_rows}
    except Exception:
        logger.exception("Failed to query task queue")
        return {
            "tasks": [],
            "pagination": {"total": 0, "page": page, "per_page": per_page, "total_pages": 1},
            "status_counts": {},
        }

    return {
        "tasks": tasks,
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, -(-total // per_page)),
        },
        "status_counts": status_counts,
    }


# ---------------------------------------------------------------------------
# Cost breakdown
# ---------------------------------------------------------------------------
_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90}


async def get_cost_breakdown(period: str = "7d") -> dict:
    """Return daily cost breakdown per agent for the requested period."""
    days = _PERIOD_DAYS.get(period, 7)
    redis = await get_redis()
    now = datetime.now(timezone.utc)

    daily: list[dict] = []
    agent_totals: dict[str, float] = {n: 0.0 for n in AGENT_REGISTRY}
    grand_total = 0.0

    for offset in range(days):
        day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        cost_hash = await redis.hgetall(f"leadlock:agent_costs:{day}") or {}
        day_entry: dict[str, Any] = {"date": day}
        day_total = 0.0
        for name in AGENT_REGISTRY:
            cost = float(cost_hash.get(name, 0))
            day_entry[name] = cost
            agent_totals[name] += cost
            day_total += cost
        day_entry["total"] = round(day_total, 4)
        grand_total += day_total
        daily.append(day_entry)

    daily.reverse()  # chronological order
    daily_avg = round(grand_total / days, 4) if days else 0.0

    return {
        "period": period,
        "days": days,
        "daily": daily,
        "agent_totals": {k: round(v, 4) for k, v in agent_totals.items()},
        "grand_total": round(grand_total, 4),
        "daily_average": daily_avg,
        "projected_monthly": round(daily_avg * 30, 2),
    }
