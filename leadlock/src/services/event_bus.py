"""
Lightweight event bus via Redis pub/sub — enables worker-to-worker communication.

Workers call drain_events() at the start of each cycle to pick up
pending events. Publishers call publish_event() to notify the fleet.

Key events:
- config_changed: Dashboard updates config → workers invalidate cache
- reputation_critical: system_health detects danger → outreach pauses
- ab_test_winner: A/B engine declares winner → sequencer picks it up
"""
import json
import logging
from typing import Any, Optional

from src.utils.dedup import get_redis

logger = logging.getLogger(__name__)

CHANNEL = "leadlock:worker_events"
# Events are also stored in a Redis list for workers that missed the pub/sub
EVENT_LIST_KEY = "leadlock:worker_events:pending"
EVENT_LIST_MAX = 100  # Maximum pending events to keep


async def publish_event(event_type: str, data: Optional[dict[str, Any]] = None) -> None:
    """
    Publish an event to the worker fleet.

    Uses both pub/sub (real-time) and a bounded Redis list (catch-up).
    """
    event = {
        "type": event_type,
        "data": data or {},
    }
    payload = json.dumps(event)

    try:
        redis = await get_redis()
        # Publish to channel for real-time subscribers
        await redis.publish(CHANNEL, payload)
        # Also push to list for workers to drain on their next cycle
        await redis.lpush(EVENT_LIST_KEY, payload)
        await redis.ltrim(EVENT_LIST_KEY, 0, EVENT_LIST_MAX - 1)

        logger.debug("Event published: %s", event_type)
    except Exception:
        logger.warning("Failed to publish event: %s", event_type)


async def drain_events(max_events: int = 50) -> list[dict[str, Any]]:
    """
    Drain pending events from the list. Non-blocking, returns immediately.

    Workers call this at the start of each cycle to process any events
    that were published since their last run.
    """
    events: list[dict[str, Any]] = []

    try:
        redis = await get_redis()
        for _ in range(max_events):
            raw = await redis.rpop(EVENT_LIST_KEY)
            if raw is None:
                break
            try:
                payload = raw if isinstance(raw, str) else raw.decode()
                events.append(json.loads(payload))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    except Exception:
        logger.warning("Failed to drain events from bus")

    return events


async def handle_events(events: list[dict[str, Any]]) -> None:
    """
    Process a list of events. Common handler for worker integration.

    Each worker can call this to handle standard events, then handle
    worker-specific events separately.
    """
    for event in events:
        event_type = event.get("type", "")

        if event_type == "config_changed":
            from src.services.config_cache import invalidate_sales_config
            await invalidate_sales_config()
            logger.info("Config cache invalidated via event bus")
