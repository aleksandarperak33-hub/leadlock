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

    # Start background workers (15 total after consolidation)
    worker_tasks: list[asyncio.Task] = []

    # --- Always-on core workers ---

    # System health (merged: health_monitor + deliverability_monitor)
    from src.workers.system_health import run_system_health
    worker_tasks.append(asyncio.create_task(run_system_health()))
    logger.info("System health worker started")

    # Retry worker
    from src.workers.retry_worker import run_retry_worker
    worker_tasks.append(asyncio.create_task(run_retry_worker()))
    logger.info("Retry worker started")

    # Lead state manager (merged: stuck_lead_sweeper + lead_lifecycle)
    from src.workers.lead_state_manager import run_lead_state_manager
    worker_tasks.append(asyncio.create_task(run_lead_state_manager()))
    logger.info("Lead state manager started")

    # CRM sync worker
    from src.workers.crm_sync import run_crm_sync
    worker_tasks.append(asyncio.create_task(run_crm_sync()))
    logger.info("CRM sync worker started")

    # SMS dispatch (merged: followup_scheduler + booking_reminder)
    from src.workers.sms_dispatch import run_sms_dispatch
    worker_tasks.append(asyncio.create_task(run_sms_dispatch()))
    logger.info("SMS dispatch worker started")

    # Registration poller
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

        # Core sales engine workers
        from src.workers.scraper import run_scraper
        from src.workers.outreach_sequencer import run_outreach_sequencer
        from src.workers.outreach_monitor import run_outreach_monitor
        from src.workers.task_processor import run_task_processor

        from src.workers.email_finder import run_email_finder

        worker_tasks.append(asyncio.create_task(run_scraper()))
        worker_tasks.append(asyncio.create_task(run_outreach_sequencer()))
        worker_tasks.append(asyncio.create_task(run_outreach_monitor()))
        worker_tasks.append(asyncio.create_task(run_task_processor()))
        worker_tasks.append(asyncio.create_task(run_email_finder()))
        logger.info("Sales engine core workers started (scraper, sequencer, outreach_monitor, task_processor, email_finder)")

        # Feature-flagged agents — toggle via env vars without code deploys
        _FLAGGED_AGENTS = {
            "ab_test_engine":    (settings.agent_ab_test_engine,    "src.workers.ab_test_engine",    "run_ab_test_engine"),
            "winback_agent":     (settings.agent_winback_agent,     "src.workers.winback_agent",     "run_winback_agent"),
            "referral_agent":    (settings.agent_referral_agent,    "src.workers.referral_agent",    "run_referral_agent"),
            "reflection_agent":  (settings.agent_reflection_agent,  "src.workers.reflection_agent",  "run_reflection_agent"),
        }

        enabled_agents = []
        disabled_agents = []
        for agent_name, (flag, module_path, func_name) in _FLAGGED_AGENTS.items():
            if flag:
                import importlib
                mod = importlib.import_module(module_path)
                run_fn = getattr(mod, func_name)
                worker_tasks.append(asyncio.create_task(run_fn()))
                enabled_agents.append(agent_name)
            else:
                disabled_agents.append(agent_name)

        if enabled_agents:
            logger.info("Enabled agents: %s", ", ".join(enabled_agents))
        if disabled_agents:
            logger.info("Disabled agents (toggle via env): %s", ", ".join(disabled_agents))
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
