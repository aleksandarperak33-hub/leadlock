"""
Analytics API - dashboard endpoints for funnel, cost, A/B test, and performance data.
All queries use Redis-cached SQL aggregations.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from src.api.dashboard import get_current_admin

from src.services.analytics import (
    get_trade_funnel,
    get_cost_per_lead,
    get_email_performance_by_step,
    get_ab_test_results,
    get_pipeline_waterfall,
    get_agent_costs,
    get_cta_variant_performance,
)
from src.services.sales_tenancy import normalize_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/funnel")
async def trade_funnel(
    trade: Optional[str] = Query(None),
    admin=Depends(get_current_admin),
):
    """Per-trade conversion funnel."""
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    data = await get_trade_funnel(trade, tenant_id=tenant_id)
    return {"success": True, "data": data}


@router.get("/cost-per-lead")
async def cost_per_lead(
    trade: Optional[str] = Query(None),
    admin=Depends(get_current_admin),
):
    """Cost-per-lead breakdown by trade."""
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    data = await get_cost_per_lead(trade, tenant_id=tenant_id)
    return {"success": True, "data": data}


@router.get("/email-performance")
async def email_performance(admin=Depends(get_current_admin)):
    """Email open/reply rates by sequence step."""
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    data = await get_email_performance_by_step(tenant_id=tenant_id)
    return {"success": True, "data": data}


@router.get("/ab-tests")
async def ab_tests():
    """A/B test experiments with variant performance."""
    data = await get_ab_test_results()
    return {"success": True, "data": data}


@router.get("/pipeline")
async def pipeline_waterfall(admin=Depends(get_current_admin)):
    """Outreach pipeline waterfall chart data."""
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    data = await get_pipeline_waterfall(tenant_id=tenant_id)
    return {"success": True, "data": data}


@router.get("/agent-costs")
async def agent_costs(days: int = Query(7, ge=1, le=90)):
    """Per-agent AI cost breakdown."""
    data = await get_agent_costs(days)
    return {"success": True, "data": data}


@router.get("/email-intelligence")
async def email_intelligence(admin=Depends(get_current_admin)):
    """
    Email intelligence dashboard: CTA performance, content feature correlations,
    and active A/B test results in one response.
    """
    from src.services.email_intelligence import get_content_intelligence_summary

    tenant_id = normalize_tenant_id(getattr(admin, "id", None))

    cta_data = await get_cta_variant_performance(tenant_id=tenant_id)
    content_data = await get_content_intelligence_summary()
    ab_data = await get_ab_test_results()

    return {
        "success": True,
        "data": {
            "cta_performance": cta_data,
            "content_features": content_data,
            "ab_tests": ab_data,
        },
    }
