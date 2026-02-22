"""
Content factory worker - generates weekly batches of marketing content.

Weekly output:
- 2 SEO blog posts (Sonnet for quality)
- 5 Twitter/X posts
- 3 LinkedIn posts
- 2 Reddit engagement posts
- 1 lead magnet outline

All content created with status 'draft' for human review.
"""
import asyncio
import logging
import random
from datetime import datetime, timezone

from src.services.content_generation import (
    generate_content_piece,
    SOCIAL_TOPICS,
    REDDIT_SUBREDDITS,
    SEO_KEYWORDS,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 7 * 24 * 3600  # Weekly


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:content_factory",
            datetime.now(timezone.utc).isoformat(),
            ex=8 * 24 * 3600,  # 8-day TTL
        )
    except Exception:
        pass


async def run_content_factory():
    """Main loop - generate content batch weekly."""
    logger.info("Content factory started (poll every %ds)", POLL_INTERVAL_SECONDS)

    # Wait 15 minutes on startup
    await asyncio.sleep(900)

    while True:
        try:
            # Check if we already generated content this week
            if not await _should_run_this_week():
                logger.debug("Content factory: already ran this week, skipping")
            else:
                await content_batch_cycle()
        except Exception as e:
            logger.error("Content factory cycle error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _should_run_this_week() -> bool:
    """Check if content was already generated this week."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        week_key = datetime.now(timezone.utc).strftime("%Y-W%W")
        ran_key = f"leadlock:content_factory:ran:{week_key}"
        already_ran = await redis.get(ran_key)
        return already_ran is None
    except Exception:
        return True  # If Redis fails, run anyway


async def _mark_week_complete():
    """Mark this week as complete in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        week_key = datetime.now(timezone.utc).strftime("%Y-W%W")
        ran_key = f"leadlock:content_factory:ran:{week_key}"
        await redis.set(ran_key, "1", ex=8 * 86400)  # 8-day TTL
    except Exception:
        pass


async def content_batch_cycle():
    """Generate a full weekly content batch."""
    logger.info("Content factory: starting weekly batch")

    results = {
        "blog_posts": 0,
        "twitter": 0,
        "linkedin": 0,
        "reddit": 0,
        "lead_magnet": 0,
        "total_cost_usd": 0.0,
        "errors": 0,
    }

    # Shuffle topics for variety
    topics = list(SOCIAL_TOPICS)
    random.shuffle(topics)
    topic_index = 0

    def _next_topic() -> str:
        nonlocal topic_index
        t = topics[topic_index % len(topics)]
        topic_index += 1
        return t

    # 1. Blog posts (2x) — use different trades
    trades = list(SEO_KEYWORDS.keys())
    random.shuffle(trades)
    for i in range(2):
        trade = trades[i % len(trades)]
        result = await generate_content_piece(
            content_type="blog_post",
            target_trade=trade,
        )
        if result.get("error"):
            results["errors"] += 1
        else:
            results["blog_posts"] += 1
            results["total_cost_usd"] += result.get("ai_cost_usd", 0.0)
        await asyncio.sleep(5)  # Brief pause between generations

    # 2. Twitter posts (5x)
    for _ in range(5):
        result = await generate_content_piece(
            content_type="twitter",
            topic=_next_topic(),
        )
        if result.get("error"):
            results["errors"] += 1
        else:
            results["twitter"] += 1
            results["total_cost_usd"] += result.get("ai_cost_usd", 0.0)
        await asyncio.sleep(2)

    # 3. LinkedIn posts (3x)
    for _ in range(3):
        result = await generate_content_piece(
            content_type="linkedin",
            topic=_next_topic(),
        )
        if result.get("error"):
            results["errors"] += 1
        else:
            results["linkedin"] += 1
            results["total_cost_usd"] += result.get("ai_cost_usd", 0.0)
        await asyncio.sleep(2)

    # 4. Reddit posts (2x)
    for i, subreddit in enumerate(REDDIT_SUBREDDITS[:2]):
        result = await generate_content_piece(
            content_type="reddit",
            topic=_next_topic(),
            subreddit=subreddit,
        )
        if result.get("error"):
            results["errors"] += 1
        else:
            results["reddit"] += 1
            results["total_cost_usd"] += result.get("ai_cost_usd", 0.0)
        await asyncio.sleep(2)

    # 5. Lead magnet outline (1x)
    result = await generate_content_piece(
        content_type="lead_magnet",
        topic="ROI calculator: how much revenue contractors lose from slow lead response",
    )
    if result.get("error"):
        results["errors"] += 1
    else:
        results["lead_magnet"] += 1
        results["total_cost_usd"] += result.get("ai_cost_usd", 0.0)

    await _mark_week_complete()

    total_pieces = sum(
        results[k] for k in ["blog_posts", "twitter", "linkedin", "reddit", "lead_magnet"]
    )
    logger.info(
        "Content factory batch complete: %d pieces (blog=%d twitter=%d linkedin=%d "
        "reddit=%d magnet=%d) cost=$%.4f errors=%d",
        total_pieces,
        results["blog_posts"],
        results["twitter"],
        results["linkedin"],
        results["reddit"],
        results["lead_magnet"],
        results["total_cost_usd"],
        results["errors"],
    )
