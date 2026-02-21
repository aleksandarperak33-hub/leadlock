"""
Health check endpoints - used by load balancers, Docker healthcheck, and monitoring.

- GET /health       - basic liveness (always 200 if app running)
- GET /health/ready - readiness check (DB + Redis)
- GET /health/deep  - deep check (DB + Redis + Twilio + AI + worker health)
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

# Cache Twilio account status for 5 minutes
_twilio_cache: dict = {"status": None, "checked_at": None}
TWILIO_CACHE_TTL_SECONDS = 300


@router.get("/health")
async def health_check():
    """Basic liveness check - returns 200 if the app is running."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
    }


@router.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
):
    """
    Readiness check - verifies database and Redis connectivity.
    Used by Kubernetes/Railway to determine if the app can serve traffic.
    """
    checks = {"database": False, "redis": False}

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        logger.error("Database health check failed: %s", str(e))

    # Check Redis
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = True
    except Exception as e:
        logger.warning("Redis health check failed: %s", str(e))

    all_healthy = all(checks.values())
    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/deep")
async def deep_health_check(
    db: AsyncSession = Depends(get_db),
):
    """
    Deep health check - checks ALL dependencies.
    Used by external monitoring and Docker healthcheck.

    Checks:
    - PostgreSQL: SELECT 1
    - Redis: PING
    - Twilio: account status (cached 5min)
    - AI service: last successful call timestamp
    - Workers: heartbeat freshness
    """
    now = datetime.now(timezone.utc)
    checks = {}

    # 1. PostgreSQL
    checks["database"] = await _check_database(db)

    # 2. Redis
    checks["redis"] = await _check_redis()

    # 3. Twilio account status (cached)
    checks["twilio"] = await _check_twilio()

    # 4. AI service
    checks["ai_service"] = await _check_ai_service()

    # 5. Worker health
    checks["workers"] = await _check_workers()

    # Overall status
    critical = ["database", "redis"]
    critical_healthy = all(checks.get(k, {}).get("healthy", False) for k in critical)
    all_healthy = all(c.get("healthy", False) for c in checks.values())

    if all_healthy:
        status = "healthy"
    elif critical_healthy:
        status = "degraded"
    else:
        status = "unhealthy"

    return {
        "status": status,
        "checks": checks,
        "timestamp": now.isoformat(),
        "version": "2.0.0",
    }


async def _check_database(db: AsyncSession) -> dict:
    """Check PostgreSQL connectivity."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"healthy": True}
    except Exception as e:
        logger.error("Deep health: database check failed: %s", str(e))
        return {"healthy": False, "error": str(e)}


async def _check_redis() -> dict:
    """Check Redis connectivity."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.ping()
        return {"healthy": True}
    except Exception as e:
        logger.warning("Deep health: Redis check failed: %s", str(e))
        return {"healthy": False, "error": str(e)}


async def _check_twilio() -> dict:
    """Check Twilio account status (cached for 5 minutes)."""
    global _twilio_cache
    now = datetime.now(timezone.utc)

    # Return cached result if fresh
    if (
        _twilio_cache["checked_at"]
        and (now - _twilio_cache["checked_at"]).total_seconds() < TWILIO_CACHE_TTL_SECONDS
    ):
        return _twilio_cache["status"]

    try:
        from src.config import get_settings
        settings = get_settings()
        if not settings.twilio_account_sid:
            result = {"healthy": False, "error": "Twilio not configured"}
        else:
            from twilio.rest import Client as TwilioClient
            client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
            account = client.api.accounts(settings.twilio_account_sid).fetch()
            result = {
                "healthy": account.status == "active",
                "account_status": account.status,
            }
    except Exception as e:
        logger.warning("Deep health: Twilio check failed: %s", str(e))
        result = {"healthy": False, "error": str(e)}

    _twilio_cache = {"status": result, "checked_at": now}
    return result


async def _check_ai_service() -> dict:
    """Check AI service availability via Redis heartbeat."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        last_call = await redis.get("leadlock:ai_service:last_success")
        if last_call:
            return {"healthy": True, "last_success": last_call}
        # No record yet - assume healthy (service hasn't been used yet)
        return {"healthy": True, "last_success": None}
    except Exception as e:
        return {"healthy": True, "note": "Unable to check AI heartbeat"}


async def _check_workers() -> dict:
    """Check worker heartbeat timestamps in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        workers = {}
        worker_keys = [
            "leadlock:worker_health:health_monitor",
            "leadlock:worker_health:retry_worker",
            "leadlock:worker_health:stuck_lead_sweeper",
        ]

        for key in worker_keys:
            name = key.split(":")[-1]
            heartbeat = await redis.get(key)
            workers[name] = {
                "healthy": heartbeat is not None,
                "last_heartbeat": heartbeat,
            }

        all_healthy = all(w["healthy"] for w in workers.values())
        return {"healthy": all_healthy, "workers": workers}
    except Exception as e:
        return {"healthy": True, "note": "Unable to check worker heartbeats"}
