"""
Agent fleet API — dashboard endpoints for agent health, activity, tasks, and costs.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dashboard import get_current_admin
from src.services.agent_fleet import (
    AGENT_REGISTRY,
    get_fleet_status,
    get_agent_activity,
    get_task_queue,
    get_cost_breakdown,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.get("/fleet")
async def fleet_status(_admin=Depends(get_current_admin)):
    """All 9 agents in one call — health, cost, task counts (30s Redis cache)."""
    data = await get_fleet_status()
    return {"success": True, "data": data}


@router.get("/tasks")
async def task_queue(
    _admin=Depends(get_current_admin),
    status: str = Query("all", pattern="^(all|pending|processing|completed|failed)$"),
    task_type: str = Query("all"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Paginated task queue with status/type filters."""
    data = await get_task_queue(
        status=status,
        task_type=task_type,
        page=page,
        per_page=per_page,
    )
    return {"success": True, "data": data}


@router.get("/costs")
async def cost_tracker(
    _admin=Depends(get_current_admin),
    period: str = Query("7d", pattern="^(7d|30d|90d)$"),
):
    """Daily cost breakdown per agent for charts."""
    data = await get_cost_breakdown(period=period)
    return {"success": True, "data": data}


@router.get("/{name}/activity")
async def agent_activity(
    name: str,
    _admin=Depends(get_current_admin),
    limit: int = Query(20, ge=1, le=100),
):
    """Detail panel data — recent tasks, cost history, SOUL summary."""
    if name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {name}")

    data = await get_agent_activity(name=name, limit=limit)
    return {"success": True, "data": data}
