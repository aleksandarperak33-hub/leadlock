"""
LeadLock - AI Speed-to-Lead Platform for Home Services.
Main FastAPI application entry point.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from src.config import get_settings
from src.api.router import api_router
from src.utils.logging import (
    configure_structured_logging,
    generate_correlation_id,
    set_correlation_id,
    get_correlation_id,
)

logger = logging.getLogger("leadlock")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Injects a correlation ID into every request context and response header."""

    async def dispatch(self, request: Request, call_next) -> Response:
        cid = request.headers.get("X-Correlation-ID") or generate_correlation_id()
        set_correlation_id(cid)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    settings = get_settings()
    logger.info("LeadLock starting up (env=%s)", settings.app_env)

    # Security warnings
    if not settings.dashboard_jwt_secret:
        logger.warning(
            "DASHBOARD_JWT_SECRET not set - falling back to APP_SECRET_KEY. "
            "Set a dedicated JWT secret for production."
        )
    if not settings.encryption_key:
        logger.warning(
            "ENCRYPTION_KEY not set - CRM API keys will be stored unencrypted. "
            "Generate a Fernet key for production."
        )

    # Initialize Sentry if configured
    if settings.sentry_dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                traces_sample_rate=0.1,
                environment=settings.app_env,
            )
            logger.info("Sentry initialized")
        except Exception as e:
            logger.warning("Sentry initialization failed: %s", str(e))

    # Start background workers
    worker_tasks: list[asyncio.Task] = []

    # Health monitor always runs
    from src.workers.health_monitor import run_health_monitor
    worker_tasks.append(asyncio.create_task(run_health_monitor()))
    logger.info("Health monitor worker started")

    # Dead letter queue retry worker always runs
    from src.workers.retry_worker import run_retry_worker
    worker_tasks.append(asyncio.create_task(run_retry_worker()))
    logger.info("Retry worker started")

    # Stuck lead sweeper always runs
    from src.workers.stuck_lead_sweeper import run_stuck_lead_sweeper
    worker_tasks.append(asyncio.create_task(run_stuck_lead_sweeper()))
    logger.info("Stuck lead sweeper started")

    # CRM sync worker always runs
    from src.workers.crm_sync import run_crm_sync
    worker_tasks.append(asyncio.create_task(run_crm_sync()))
    logger.info("CRM sync worker started")

    # Follow-up scheduler always runs
    from src.workers.followup_scheduler import run_followup_scheduler
    worker_tasks.append(asyncio.create_task(run_followup_scheduler()))
    logger.info("Follow-up scheduler started")

    # Deliverability monitor always runs (reputation tracking)
    from src.workers.deliverability_monitor import run_deliverability_monitor
    worker_tasks.append(asyncio.create_task(run_deliverability_monitor()))
    logger.info("Deliverability monitor started")

    # Booking reminder worker always runs
    from src.workers.booking_reminder import run_booking_reminder
    worker_tasks.append(asyncio.create_task(run_booking_reminder()))
    logger.info("Booking reminder worker started")

    # Lead lifecycle worker always runs
    from src.workers.lead_lifecycle import run_lead_lifecycle
    worker_tasks.append(asyncio.create_task(run_lead_lifecycle()))
    logger.info("Lead lifecycle worker started")

    # Registration poller - monitors A2P / toll-free registration status
    from src.workers.registration_poller import run_registration_poller
    worker_tasks.append(asyncio.create_task(run_registration_poller()))
    logger.info("Registration poller started")

    # Sales engine workers - gated behind config flag
    if settings.sales_engine_enabled:
        if not settings.brave_api_key:
            logger.error(
                "SALES_ENGINE_ENABLED=true but BRAVE_API_KEY is not set. "
                "Scraper will not run until BRAVE_API_KEY is configured."
            )

        # Ensure SalesEngineConfig row exists (auto-seed if missing)
        try:
            from src.database import async_session_factory
            from src.models.sales_config import SalesEngineConfig
            from sqlalchemy import select

            async with async_session_factory() as db:
                result = await db.execute(select(SalesEngineConfig).limit(1))
                config = result.scalar_one_or_none()
                if not config:
                    config = SalesEngineConfig(is_active=False)
                    db.add(config)
                    await db.commit()
                    logger.info(
                        "Auto-created SalesEngineConfig (inactive). "
                        "Configure via dashboard or PUT /api/v1/sales/config"
                    )
                elif not config.is_active:
                    logger.info(
                        "SalesEngineConfig exists but is_active=False. "
                        "Activate via dashboard or PUT /api/v1/sales/config"
                    )
                else:
                    locs = len(config.target_locations or [])
                    trades = len(config.target_trade_types or [])
                    logger.info(
                        "SalesEngineConfig active: %d locations, %d trades",
                        locs, trades,
                    )
        except Exception as e:
            logger.warning("Failed to verify SalesEngineConfig: %s", str(e))

        from src.workers.scraper import run_scraper
        from src.workers.outreach_sequencer import run_outreach_sequencer
        from src.workers.outreach_cleanup import run_outreach_cleanup
        from src.workers.task_processor import run_task_processor

        worker_tasks.append(asyncio.create_task(run_scraper()))
        worker_tasks.append(asyncio.create_task(run_outreach_sequencer()))
        worker_tasks.append(asyncio.create_task(run_outreach_cleanup()))
        worker_tasks.append(asyncio.create_task(run_task_processor()))
        logger.info("Sales engine workers started (scraper, sequencer, cleanup, task_processor)")
    else:
        logger.info("Sales engine workers disabled (SALES_ENGINE_ENABLED=false)")

    yield

    # Graceful shutdown - give workers time to finish current work
    logger.info("LeadLock shutting down - stopping %d workers...", len(worker_tasks))
    for task in worker_tasks:
        task.cancel()
    if worker_tasks:
        # Wait up to 10 seconds for workers to finish
        done, pending = await asyncio.wait(worker_tasks, timeout=10.0)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    logger.info("LeadLock shutdown complete - all %d workers stopped", len(worker_tasks))


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    # Configure structured JSON logging with correlation IDs
    configure_structured_logging(settings.log_level)

    application = FastAPI(
        title="LeadLock",
        description="AI Speed-to-Lead Platform for Home Services",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS - allow dashboard origin
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            settings.app_base_url,
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization", "Content-Type", "X-Correlation-ID",
            "Accept", "Origin", "X-Requested-With",
        ],
    )

    # Correlation ID middleware (must be added AFTER CORS so it runs on every request)
    application.add_middleware(CorrelationIdMiddleware)

    # Include all routes
    application.include_router(api_router)

    return application


app = create_app()
