"""
Analytics API - dashboard endpoints for funnel, cost, A/B test, and performance data.
All queries use Redis-cached SQL aggregations.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query

from src.services.analytics import (
    get_trade_funnel,
    get_cost_per_lead,
    get_email_performance_by_step,
    get_ab_test_results,
    get_pipeline_waterfall,
    get_agent_costs,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/funnel")
async def trade_funnel(trade: Optional[str] = Query(None)):
    """Per-trade conversion funnel."""
    data = await get_trade_funnel(trade)
    return {"success": True, "data": data}


@router.get("/cost-per-lead")
async def cost_per_lead(trade: Optional[str] = Query(None)):
    """Cost-per-lead breakdown by trade."""
    data = await get_cost_per_lead(trade)
    return {"success": True, "data": data}


@router.get("/email-performance")
async def email_performance():
    """Email open/reply rates by sequence step."""
    data = await get_email_performance_by_step()
    return {"success": True, "data": data}


@router.get("/ab-tests")
async def ab_tests():
    """A/B test experiments with variant performance."""
    data = await get_ab_test_results()
    return {"success": True, "data": data}


@router.get("/pipeline")
async def pipeline_waterfall():
    """Outreach pipeline waterfall chart data."""
    data = await get_pipeline_waterfall()
    return {"success": True, "data": data}


@router.get("/agent-costs")
async def agent_costs(days: int = Query(7, ge=1, le=90)):
    """Per-agent AI cost breakdown."""
    data = await get_agent_costs(days)
    return {"success": True, "data": data}
