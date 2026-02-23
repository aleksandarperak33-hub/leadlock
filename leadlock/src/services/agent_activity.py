"""
Agent activity service — real activity data from EventLog.

Most agents write to event_logs (not task_queue), so this service
provides the ground truth for dashboard activity feeds, system map
counts, and per-agent event tallies.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select, and_, case, literal_column

from src.database import async_session_factory
from src.models.event_log import EventLog
from src.models.lead import Lead
from src.services.agent_fleet import AGENT_REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent → EventLog action prefix mapping
# ---------------------------------------------------------------------------
# Each agent writes events with specific action prefixes.
# This maps agent names to the action patterns found in event_logs.agent_id
# or event_logs.action fields.

AGENT_ACTION_PREFIXES: dict[str, list[str]] = {
    "sms_dispatch": ["followup_", "booking_reminder_", "sms_"],
    "lead_state_manager": ["lead_state_", "lead_archived", "lead_recycled", "lead_sweep"],
    "crm_sync": ["crm_sync_", "booking_confirmed", "crm_"],
    "outreach_sequencer": ["outreach_email_sent", "sequence_", "outreach_step_"],
    "ab_test_engine": ["ab_test_", "experiment_"],
    "winback_agent": ["winback_"],
    "reflection_agent": ["reflection_", "daily_reflection"],
    "system_health": ["health_check_", "deliverability_"],
    "scraper": ["scrape_", "prospect_"],
    "outreach_monitor": ["outreach_health_", "cleanup_sequence", "pipeline_anomaly"],
    "retry_worker": ["retry_", "task_retried"],
    "registration_poller": ["registration_poll", "a2p_"],
    "referral_agent": ["referral_"],
    "task_processor": ["task_processed", "task_failed"],
}

# Reverse lookup: action prefix → agent name (for mapping EventLog rows)
_PREFIX_TO_AGENT: list[tuple[str, str]] = [
    (prefix, agent_name)
    for agent_name, prefixes in AGENT_ACTION_PREFIXES.items()
    for prefix in prefixes
]


def _resolve_agent_name(action: str, agent_id: Optional[str]) -> Optional[str]:
    """Map an EventLog action/agent_id to a known agent name."""
    # First try agent_id directly
    if agent_id and agent_id in AGENT_REGISTRY:
        return agent_id

    # Then match by action prefix
    if action:
        for prefix, agent_name in _PREFIX_TO_AGENT:
            if action.startswith(prefix):
                return agent_name

    return None


def _build_action_filter(agent_name: str):
    """Build SQLAlchemy OR conditions for an agent's known action prefixes."""
    from sqlalchemy import or_

    prefixes = AGENT_ACTION_PREFIXES.get(agent_name, [])
    conditions = []

    # Match by agent_id field
    conditions.append(EventLog.agent_id == agent_name)

    # Match by action prefix
    for prefix in prefixes:
        conditions.append(EventLog.action.startswith(prefix))

    return or_(*conditions) if conditions else None


# ---------------------------------------------------------------------------
# get_activity_feed — global or per-agent feed from EventLog
# ---------------------------------------------------------------------------
async def get_activity_feed(
    limit: int = 50,
    agent_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Query event_logs for real agent activity.

    Args:
        limit: Max number of events to return.
        agent_name: If provided, filter to a specific agent's actions.

    Returns:
        List of event dicts with agent metadata attached.
    """
    try:
        async with async_session_factory() as session:
            query = select(EventLog).order_by(EventLog.created_at.desc()).limit(limit)

            if agent_name:
                action_filter = _build_action_filter(agent_name)
                if action_filter is not None:
                    query = query.where(action_filter)

            rows = (await session.execute(query)).scalars().all()

            events = []
            for row in rows:
                resolved_agent = _resolve_agent_name(row.action, row.agent_id)
                agent_meta = AGENT_REGISTRY.get(resolved_agent or "", {})

                events.append({
                    "id": str(row.id),
                    "action": row.action,
                    "agent_name": resolved_agent,
                    "agent_display_name": agent_meta.get("display_name", resolved_agent or "System"),
                    "agent_color": agent_meta.get("color", "gray"),
                    "agent_icon": agent_meta.get("icon", "activity"),
                    "status": row.status or "success",
                    "message": row.message,
                    "cost_usd": row.cost_usd,
                    "duration_ms": row.duration_ms,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })

            return events
    except Exception:
        logger.exception("Failed to fetch activity feed")
        return []


# ---------------------------------------------------------------------------
# get_agent_event_counts — event counts per agent for fleet status
# ---------------------------------------------------------------------------
async def get_agent_event_counts(days: int = 1) -> dict[str, int]:
    """
    Count events per agent in the last N days from event_logs.

    Returns:
        Dict mapping agent_name → event count.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    counts: dict[str, int] = {name: 0 for name in AGENT_REGISTRY}

    try:
        async with async_session_factory() as session:
            rows = (await session.execute(
                select(
                    EventLog.action,
                    EventLog.agent_id,
                    func.count(EventLog.id).label("cnt"),
                )
                .where(EventLog.created_at >= cutoff)
                .group_by(EventLog.action, EventLog.agent_id)
            )).all()

            for action, agent_id, cnt in rows:
                resolved = _resolve_agent_name(action, agent_id)
                if resolved and resolved in counts:
                    counts[resolved] += cnt

    except Exception:
        logger.exception("Failed to count agent events")

    return counts


# ---------------------------------------------------------------------------
# get_system_map_data — aggregate counts for the system flowchart
# ---------------------------------------------------------------------------

# Lead states by stage (from CLAUDE.md lifecycle)
_INBOUND_STATES = ("new",)
_PROCESSING_STATES = ("intake_sent", "qualifying", "qualified", "booking")
_OUTCOME_STATES = ("booked", "completed", "cold", "dead", "opted_out")

async def get_system_map_data() -> dict[str, Any]:
    """
    Aggregate counts for the system flowchart.

    Returns dict with:
        - lead_counts: dict of state → count for active leads
        - sms_sent_today: int
        - bookings_today: int
        - emails_sent_today: int
        - active_prospects: int
    """
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    result: dict[str, Any] = {
        "lead_counts": {},
        "sms_sent_today": 0,
        "bookings_today": 0,
        "emails_sent_today": 0,
        "active_prospects": 0,
    }

    try:
        async with async_session_factory() as session:
            # Lead counts by state
            lead_rows = (await session.execute(
                select(Lead.state, func.count(Lead.id))
                .group_by(Lead.state)
            )).all()

            for state_val, cnt in lead_rows:
                result["lead_counts"][state_val] = cnt

            # Today's event counts using conditional aggregation
            event_agg = (await session.execute(
                select(
                    func.sum(case(
                        (EventLog.action.startswith("sms_"), 1),
                        (EventLog.action.startswith("followup_"), 1),
                        (EventLog.action.startswith("booking_reminder_"), 1),
                        else_=0,
                    )).label("sms_count"),
                    func.sum(case(
                        (EventLog.action.in_(["booking_confirmed", "booking_created"]), 1),
                        else_=0,
                    )).label("booking_count"),
                    func.sum(case(
                        (EventLog.action.startswith("outreach_email_"), 1),
                        else_=0,
                    )).label("email_count"),
                ).where(EventLog.created_at >= day_start)
            )).one()

            result["sms_sent_today"] = int(event_agg.sms_count or 0)
            result["bookings_today"] = int(event_agg.booking_count or 0)
            result["emails_sent_today"] = int(event_agg.email_count or 0)

            # Active prospects (leads in processing states)
            result["active_prospects"] = sum(
                result["lead_counts"].get(s, 0)
                for s in _PROCESSING_STATES
            )

    except Exception:
        logger.exception("Failed to build system map data")

    return result


# ---------------------------------------------------------------------------
# get_agent_events — recent EventLog entries for a specific agent
# ---------------------------------------------------------------------------
async def get_agent_events(
    agent_name: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Get recent EventLog entries for a specific agent.
    Used by AgentDetailPanel for non-task_processor agents.
    """
    try:
        async with async_session_factory() as session:
            action_filter = _build_action_filter(agent_name)
            if action_filter is None:
                return []

            rows = (await session.execute(
                select(EventLog)
                .where(action_filter)
                .order_by(EventLog.created_at.desc())
                .limit(limit)
            )).scalars().all()

            return [
                {
                    "id": str(row.id),
                    "action": row.action,
                    "status": row.status or "success",
                    "message": row.message,
                    "cost_usd": row.cost_usd,
                    "duration_ms": row.duration_ms,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]
    except Exception:
        logger.exception("Failed to fetch events for agent %s", agent_name)
        return []


# ---------------------------------------------------------------------------
# get_agent_event_metrics — 7-day metrics from EventLog for an agent
# ---------------------------------------------------------------------------
async def get_agent_event_metrics(agent_name: str) -> dict[str, Any]:
    """
    Compute 7-day metrics from EventLog for a specific agent.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    metrics = {
        "total_tasks": 0,
        "success_rate": 0.0,
        "avg_duration_s": 0.0,
        "total_cost": 0.0,
    }

    try:
        async with async_session_factory() as session:
            action_filter = _build_action_filter(agent_name)
            if action_filter is None:
                return metrics

            row = (await session.execute(
                select(
                    func.count(EventLog.id).label("total"),
                    func.sum(case(
                        (EventLog.status == "success", 1),
                        else_=0,
                    )).label("success_count"),
                    func.avg(EventLog.duration_ms).filter(
                        EventLog.duration_ms.isnot(None),
                    ).label("avg_ms"),
                    func.coalesce(func.sum(EventLog.cost_usd), 0).label("total_cost"),
                )
                .where(and_(action_filter, EventLog.created_at >= cutoff))
            )).one()

            total = row.total or 0
            success = row.success_count or 0
            avg_ms = float(row.avg_ms) if row.avg_ms else 0.0

            metrics = {
                "total_tasks": total,
                "success_rate": round(success / total, 4) if total else 0.0,
                "avg_duration_s": round(avg_ms / 1000, 2),
                "total_cost": round(float(row.total_cost or 0), 4),
            }
    except Exception:
        logger.exception("Failed to compute event metrics for agent %s", agent_name)

    return metrics
