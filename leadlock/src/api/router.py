"""
API router - aggregates all route modules.
"""
from fastapi import APIRouter
from src.api.webhooks import router as webhooks_router
from src.api.dashboard import router as dashboard_router
from src.api.admin_dashboard import router as admin_dashboard_router
from src.api.health import router as health_router
from src.api.sales_engine import router as sales_engine_router
from src.api.campaign_detail import router as campaign_detail_router
from src.api.campaign_inbox import router as campaign_inbox_router
from src.api.metrics import router as metrics_router
from src.api.billing import router as billing_router
from src.api.integrations import router as integrations_router
from src.api.analytics import router as analytics_router
from src.api.agents import router as agents_router

api_router = APIRouter()
api_router.include_router(webhooks_router)
api_router.include_router(dashboard_router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(health_router)
api_router.include_router(sales_engine_router)
api_router.include_router(campaign_detail_router)
api_router.include_router(campaign_inbox_router)
api_router.include_router(metrics_router)
api_router.include_router(billing_router)
api_router.include_router(integrations_router)
api_router.include_router(analytics_router)
api_router.include_router(agents_router)
