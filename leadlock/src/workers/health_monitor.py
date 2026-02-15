"""
Health monitor worker — tracks system health metrics.
"""
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def run_health_monitor():
    """Monitor system health. Runs every 5 minutes."""
    logger.info("Health monitor started")

    while True:
        try:
            await check_health()
        except Exception as e:
            logger.error("Health monitor error: %s", str(e))
        await asyncio.sleep(300)


async def check_health():
    """Check system health metrics."""
    # Check database connectivity
    try:
        from src.database import async_session_factory
        from sqlalchemy import text
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error("Database health check failed: %s", str(e))

    # Check Redis connectivity
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.ping()
    except Exception as e:
        logger.warning("Redis health check failed: %s", str(e))
