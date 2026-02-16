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
        from src.workers.scraper import run_scraper
        from src.workers.outreach_sequencer import run_outreach_sequencer
        from src.workers.outreach_cleanup import run_outreach_cleanup

        worker_tasks.append(asyncio.create_task(run_scraper()))
        worker_tasks.append(asyncio.create_task(run_outreach_sequencer()))
        worker_tasks.append(asyncio.create_task(run_outreach_cleanup()))
        logger.info("Sales engine workers started (scraper, sequencer, cleanup)")
    else:
        logger.info("Sales engine workers disabled (sales_engine_enabled=False)")

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
