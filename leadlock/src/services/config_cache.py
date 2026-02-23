"""
SalesEngineConfig cache — avoids repeated DB queries across 8+ workers.

Reads from Redis with a 60-second TTL. Workers call get_sales_config()
instead of querying the database directly. The dashboard PUT endpoint
invalidates the cache when config changes.
"""
import json
import logging
from typing import Any, Optional

from src.utils.dedup import get_redis

logger = logging.getLogger(__name__)

CACHE_KEY = "leadlock:sales_config_cache"
CACHE_TTL = 60  # seconds


async def get_sales_config() -> Optional[dict[str, Any]]:
    """
    Return the SalesEngineConfig as a dict, cached in Redis for 60s.

    Returns None when no config row exists or is_active is False.
    """
    redis = await get_redis()

    # Try cache first
    cached = await redis.get(CACHE_KEY)
    if cached is not None:
        try:
            data = json.loads(cached)
            return data if data else None
        except (json.JSONDecodeError, TypeError):
            pass

    # Cache miss — read from DB
    config_dict = await _load_from_db()

    # Store in cache (even None, as empty string sentinel)
    try:
        value = json.dumps(config_dict) if config_dict else ""
        await redis.set(CACHE_KEY, value, ex=CACHE_TTL)
    except Exception:
        logger.warning("Failed to cache SalesEngineConfig in Redis")

    return config_dict


async def invalidate_sales_config() -> None:
    """Delete the cached config. Call after any config update."""
    try:
        redis = await get_redis()
        await redis.delete(CACHE_KEY)
        logger.info("SalesEngineConfig cache invalidated")
    except Exception:
        logger.warning("Failed to invalidate SalesEngineConfig cache")


async def _load_from_db() -> Optional[dict[str, Any]]:
    """Load SalesEngineConfig row from the database."""
    from sqlalchemy import select

    from src.database import async_session_factory
    from src.models.sales_config import SalesEngineConfig

    try:
        async with async_session_factory() as db:
            result = await db.execute(select(SalesEngineConfig).limit(1))
            config = result.scalar_one_or_none()
            if not config:
                return None

            # Serialize to dict (only the fields workers need)
            return {
                "is_active": config.is_active,
                "target_trade_types": config.target_trade_types,
                "target_locations": config.target_locations,
                "daily_email_limit": config.daily_email_limit,
                "daily_scrape_limit": config.daily_scrape_limit,
                "sequence_delay_hours": config.sequence_delay_hours,
                "max_sequence_steps": config.max_sequence_steps,
                "from_email": config.from_email,
                "from_name": config.from_name,
                "sender_name": getattr(config, "sender_name", None),
                "booking_url": getattr(config, "booking_url", None),
                "reply_to_email": getattr(config, "reply_to_email", None),
                "company_address": getattr(config, "company_address", None),
                "sms_after_email_reply": getattr(config, "sms_after_email_reply", False),
                "sms_from_phone": getattr(config, "sms_from_phone", None),
                "email_templates": getattr(config, "email_templates", None),
                "scraper_interval_minutes": getattr(config, "scraper_interval_minutes", 15),
                "variant_cooldown_days": getattr(config, "variant_cooldown_days", 7),
                "send_hours_start": getattr(config, "send_hours_start", 9),
                "send_hours_end": getattr(config, "send_hours_end", 17),
                "send_timezone": getattr(config, "send_timezone", "America/New_York"),
                "send_weekdays_only": getattr(config, "send_weekdays_only", True),
                "scraper_paused": getattr(config, "scraper_paused", False),
                "sequencer_paused": getattr(config, "sequencer_paused", False),
                "cleanup_paused": getattr(config, "cleanup_paused", False),
                "monthly_budget_usd": getattr(config, "monthly_budget_usd", None),
                "budget_alert_threshold": getattr(config, "budget_alert_threshold", 0.8),
            }
    except Exception:
        logger.exception("Failed to load SalesEngineConfig from database")
        return None
