"""
SalesEngineConfig cache — avoids repeated DB queries across 8+ workers.

Reads from Redis with a 60-second TTL. Workers call get_sales_config()
instead of querying the database directly. The dashboard PUT endpoint
invalidates the cache when config changes.
"""
import json
import logging
import inspect
import uuid
from typing import Any, Optional

from src.utils.dedup import get_redis

logger = logging.getLogger(__name__)

CACHE_KEY = "leadlock:sales_config_cache"
CACHE_TTL = 60  # seconds


def _normalize_tenant_id(tenant_id: Optional[uuid.UUID | str]) -> Optional[uuid.UUID]:
    if tenant_id in (None, "", "None"):
        return None
    if isinstance(tenant_id, uuid.UUID):
        return tenant_id
    try:
        return uuid.UUID(str(tenant_id))
    except (TypeError, ValueError):
        return None


def _cache_key_for_tenant(tenant_id: Optional[uuid.UUID | str] = None) -> str:
    tenant = _normalize_tenant_id(tenant_id)
    return f"{CACHE_KEY}:{tenant}" if tenant is not None else CACHE_KEY


async def get_sales_config(
    tenant_id: Optional[uuid.UUID | str] = None,
) -> Optional[dict[str, Any]]:
    """
    Return the SalesEngineConfig as a dict, cached in Redis for 60s.

    Returns None when no config row exists. Always includes the is_active
    field; callers are responsible for checking it.
    """
    redis = await get_redis()

    # Try cache first
    cache_key = _cache_key_for_tenant(tenant_id)
    cached = await redis.get(cache_key)
    if cached is not None:
        try:
            data = json.loads(cached)
            return data if data else None
        except (json.JSONDecodeError, TypeError):
            pass

    # Cache miss — read from DB
    config_dict = await _load_from_db(tenant_id=tenant_id)

    # Store in cache (even None, as empty string sentinel)
    try:
        value = json.dumps(config_dict) if config_dict else ""
        await redis.set(cache_key, value, ex=CACHE_TTL)
    except Exception as e:
        logger.warning("Failed to cache SalesEngineConfig in Redis")

    return config_dict


async def invalidate_sales_config(
    tenant_id: Optional[uuid.UUID | str] = None,
) -> None:
    """Delete cached config rows. Call after any config update."""
    try:
        redis = await get_redis()
        normalized = _normalize_tenant_id(tenant_id)
        if normalized is not None:
            await redis.delete(_cache_key_for_tenant(normalized), CACHE_KEY)
            logger.info("SalesEngineConfig cache invalidated for tenant=%s", str(normalized))
            return

        # Global invalidation path (backward compatibility).
        keys = [CACHE_KEY]
        try:
            scan_iter_fn = getattr(redis, "scan_iter", None)
            if scan_iter_fn and not inspect.iscoroutinefunction(scan_iter_fn):
                async for key in scan_iter_fn(match=f"{CACHE_KEY}:*"):
                    decoded = key.decode() if isinstance(key, bytes) else str(key)
                    keys.append(decoded)
        except Exception:
            # Best effort - still clear legacy global key.
            pass

        # Deduplicate and delete in one call.
        unique_keys = list(dict.fromkeys(keys))
        await redis.delete(*unique_keys)
        logger.info("SalesEngineConfig cache invalidated (%d keys)", len(unique_keys))
    except Exception as e:
        logger.warning("Failed to invalidate SalesEngineConfig cache")


async def _load_from_db(
    tenant_id: Optional[uuid.UUID | str] = None,
) -> Optional[dict[str, Any]]:
    """Load SalesEngineConfig row from the database."""
    from sqlalchemy import select

    from src.database import async_session_factory
    from src.models.sales_config import SalesEngineConfig

    try:
        async with async_session_factory() as db:
            normalized = _normalize_tenant_id(tenant_id)
            if normalized is not None:
                result = await db.execute(
                    select(SalesEngineConfig)
                    .where(SalesEngineConfig.tenant_id == normalized)
                    .limit(1)
                )
                config = result.scalar_one_or_none()
            else:
                # Backward-compatible fallback for non-tenant callers.
                result = await db.execute(
                    select(SalesEngineConfig)
                    .where(SalesEngineConfig.tenant_id.is_(None))
                    .order_by(SalesEngineConfig.updated_at.desc())
                    .limit(1)
                )
                config = result.scalar_one_or_none()
                if not config:
                    result = await db.execute(
                        select(SalesEngineConfig)
                        .where(SalesEngineConfig.is_active == True)  # noqa: E712
                        .order_by(SalesEngineConfig.updated_at.desc())
                        .limit(1)
                    )
                    config = result.scalar_one_or_none()
            if not config:
                return None

            # Serialize to dict (only the fields workers need)
            return {
                "tenant_id": str(config.tenant_id) if getattr(config, "tenant_id", None) else None,
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
                "sender_mailboxes": getattr(config, "sender_mailboxes", None),
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
    except Exception as e:
        logger.exception("Failed to load SalesEngineConfig from database")
        return None
