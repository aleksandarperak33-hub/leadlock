"""
LeadLock — AI Speed-to-Lead Platform for Home Services.
Main FastAPI application entry point.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import get_settings
from src.api.router import api_router

logger = logging.getLogger("leadlock")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    settings = get_settings()
    logger.info("LeadLock starting up (env=%s)", settings.app_env)

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

    # Sales engine workers — gated behind config flag
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

    # Cancel all background workers on shutdown
    for task in worker_tasks:
        task.cancel()
    if worker_tasks:
        await asyncio.gather(*worker_tasks, return_exceptions=True)
    logger.info("LeadLock shutting down — all workers stopped")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    application = FastAPI(
        title="LeadLock",
        description="AI Speed-to-Lead Platform for Home Services",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS — allow dashboard origin
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            settings.app_base_url,
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include all routes
    application.include_router(api_router)

    return application


app = create_app()
