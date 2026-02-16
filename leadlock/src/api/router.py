"""
API router — aggregates all route modules.
"""
from fastapi import APIRouter
from src.api.webhooks import router as webhooks_router
from src.api.dashboard import router as dashboard_router
from src.api.admin_dashboard import router as admin_dashboard_router
from src.api.health import router as health_router

api_router = APIRouter()
api_router.include_router(webhooks_router)
api_router.include_router(dashboard_router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(health_router)
