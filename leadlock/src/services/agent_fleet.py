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
    "winback_agent": "winback.md",
    "referral_agent": "prospect_researcher.md",
    "reflection_agent": "reflection.md",
    "outreach_monitor": "outreach_health.md",
    "outreach_sequencer": None,
    "scraper": None,
    "task_processor": None,
    "system_health": None,
    "lead_state_manager": None,
    "sms_dispatch": None,
    "crm_sync": None,
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
# Agent registry (static metadata) — 14 agents in 3 tiers
# ---------------------------------------------------------------------------

# Tier constants
TIER_AI = "ai"
TIER_CORE_OPS = "core_ops"
TIER_INFRA = "infra"

AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    # --- Tier 1: AI Agents (use Claude API, generate revenue) ---
    "outreach_sequencer": {
        "display_name": "Outreach Sequencer",
        "description": "Executes multi-step outreach sequences for active campaigns",
        "schedule": "Every 30 min",
        "icon": "mail",
        "color": "red",
        "uses_ai": True,
        "poll_interval": 1800,
        "task_types": ["outreach_sequence"],
        "tier": TIER_AI,
    },
    "ab_test_engine": {
        "display_name": "A/B Testing Engine",
        "description": "Optimizes subject lines through controlled experiments",
        "schedule": "Every 6 hours",
        "icon": "flask-conical",
        "color": "purple",
        "uses_ai": True,
        "poll_interval": 21600,
        "task_types": ["generate_ab_variants"],
        "tier": TIER_AI,
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
        "tier": TIER_AI,
    },
    "reflection_agent": {
        "display_name": "Reflection Agent",
        "description": "Daily performance audit across all agents",
        "schedule": "Daily",
        "icon": "brain",
        "color": "indigo",
        "uses_ai": True,
        "poll_interval": 86400,
        "task_types": ["daily_reflection"],
        "tier": TIER_AI,
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
        "tier": TIER_AI,
    },

    # --- Tier 2: Core Ops (lead-touching, business logic) ---
    "sms_dispatch": {
        "display_name": "SMS Dispatch",
        "description": "Sends follow-up messages and booking reminders with compliance checks",
        "schedule": "Every 60s",
        "icon": "send",
        "color": "sky",
        "uses_ai": False,
        "poll_interval": 60,
        "task_types": ["schedule_followup", "send_booking_reminder"],
        "tier": TIER_CORE_OPS,
    },
    "lead_state_manager": {
        "display_name": "Lead State Manager",
        "description": "Sweeps stuck leads and manages lifecycle transitions",
        "schedule": "Every 5 min",
        "icon": "git-branch",
        "color": "lime",
        "uses_ai": False,
        "poll_interval": 300,
        "task_types": ["sweep_stuck_leads", "advance_lifecycle"],
        "tier": TIER_CORE_OPS,
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
        "tier": TIER_CORE_OPS,
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
        "tier": TIER_CORE_OPS,
    },
    "task_processor": {
        "display_name": "Task Processor",
        "description": "Processes queued background tasks from all agents",
        "schedule": "Every ~30s",
        "icon": "cog",
        "color": "gray",
        "uses_ai": False,
        "poll_interval": 30,
        "task_types": ["process_task"],
        "tier": TIER_CORE_OPS,
    },

    # --- Tier 3: Infrastructure (monitoring, maintenance) ---
    "system_health": {
        "display_name": "System Health",
        "description": "Monitors infrastructure health, SMS/email deliverability, and sender reputation",
        "schedule": "Every 5 min",
        "icon": "activity",
        "color": "green",
        "uses_ai": False,
        "poll_interval": 300,
        "task_types": ["system_health_check", "check_deliverability"],
        "tier": TIER_INFRA,
    },
    "outreach_monitor": {
        "display_name": "Outreach Monitor",
        "description": "Detects pipeline anomalies and cleans exhausted sequences",
        "schedule": "Every 15 min",
        "icon": "heart-pulse",
        "color": "emerald",
        "uses_ai": False,
        "poll_interval": 900,
        "task_types": ["health_check", "cleanup_sequences"],
        "tier": TIER_INFRA,
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
        "tier": TIER_INFRA,
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
        "tier": TIER_INFRA,
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

# Tier display metadata
TIER_METADATA: dict[str, dict[str, str]] = {
    TIER_AI: {"label": "AI Agents", "description": "Use Claude API, generate revenue"},
    TIER_CORE_OPS: {"label": "Core Operations", "description": "Lead-touching, business logic"},
    TIER_INFRA: {"label": "Infrastructure", "description": "Monitoring, maintenance"},
}


# ---------------------------------------------------------------------------
# Agent feature flags
# ---------------------------------------------------------------------------
_AGENT_FLAG_MAP: dict[str, str] = {
    "ab_test_engine": "agent_ab_test_engine",
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

    # --- PostgreSQL: today's event counts from EventLog (real activity) ---
    task_counts: dict[str, int] = {}
    try:
        from src.services.agent_activity import get_agent_event_counts
        task_counts = await get_agent_event_counts(days=1)
    except Exception:
        logger.exception("Failed to query event counts for fleet status")

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

    # --- Recent activity + 7-day metrics ---
    # task_processor uses TaskQueue; all others use EventLog for real activity.
    recent_tasks: list[dict] = []
    metrics_7d = {"total_tasks": 0, "success_rate": 0.0, "avg_duration_s": 0.0, "total_cost": 0.0}

    if name == "task_processor":
        # TaskQueue is the ground truth for task_processor
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
                        "action": t.task_type,
                        "status": t.status,
                        "duration_ms": int(duration * 1000) if duration else None,
                        "cost_usd": None,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                    })

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
                    "total_cost": 0.0,
                }
        except Exception:
            logger.exception("Failed to query tasks for agent %s", name)
    else:
        # All other agents: use EventLog for real activity
        try:
            from src.services.agent_activity import get_agent_events, get_agent_event_metrics
            recent_tasks = await get_agent_events(name, limit=limit)
            metrics_7d = await get_agent_event_metrics(name)
        except Exception:
            logger.exception("Failed to query EventLog for agent %s", name)

    # --- Cost history from Redis (last 30 days) --- pipeline batch reads ---
    cost_history: list[dict] = []
    cost_7d_total = 0.0

    # Build date keys and batch via pipeline
    date_keys = []
    for offset in range(30):
        day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
        date_keys.append((day, f"leadlock:agent_costs:{day}"))

    try:
        pipe = redis.pipeline()
        for _, redis_key in date_keys:
            pipe.hget(redis_key, name)
        results = await pipe.execute()

        for idx, (day, _) in enumerate(date_keys):
            raw = results[idx]
            cost = float(raw) if raw else 0.0
            cost_history.append({"date": day, "cost": cost})
            if idx < 7:
                cost_7d_total += cost
    except Exception:
        # Fallback to individual reads if pipeline fails
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
