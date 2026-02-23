"""
A/B test engine worker - polls every 6 hours to check experiment results
and create new experiments when needed.

Lifecycle:
1. Check active experiments for winners (sufficient data + clear winner)
2. Create new experiments for steps/trades lacking active experiments
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_

from src.database import async_session_factory
from src.models.ab_test import ABTestExperiment

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 6 * 3600  # 6 hours

# Steps to run experiments on
EXPERIMENT_STEPS = [1, 2, 3]


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:ab_test_engine",
            datetime.now(timezone.utc).isoformat(),
            ex=7 * 3600,  # 7h TTL (slightly longer than poll interval)
        )
    except Exception as e:
        logger.debug("Heartbeat write failed: %s", str(e))


async def run_ab_test_engine():
    """Main loop - check/create A/B experiments every 6 hours."""
    logger.info("A/B test engine started (poll every %ds)", POLL_INTERVAL_SECONDS)

    # Wait 5 minutes on startup to let other workers initialize
    await asyncio.sleep(300)

    while True:
        await _heartbeat()
        try:
            await ab_test_cycle()
        except Exception as e:
            logger.error("A/B test engine cycle error: %s", str(e))

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def ab_test_cycle():
    """
    Run one A/B test engine cycle:
    1. Check active experiments for winners
    2. Create experiments for uncovered steps
    """
    from src.services.ab_testing import check_and_declare_winner, create_experiment

    async with async_session_factory() as db:
        # Step 1: Check active experiments for winners
        active_result = await db.execute(
            select(ABTestExperiment).where(
                ABTestExperiment.status == "active"
            )
        )
        active_experiments = active_result.scalars().all()

        for exp in active_experiments:
            try:
                winner = await check_and_declare_winner(str(exp.id))
                if winner:
                    logger.info(
                        "A/B experiment %s completed: winner=%s open_rate=%.1f%%",
                        str(exp.id)[:8],
                        winner["winner_label"],
                        winner["winner_open_rate"] * 100,
                    )
            except Exception as e:
                logger.error(
                    "Error checking A/B experiment %s: %s",
                    str(exp.id)[:8], str(e),
                )

        # Step 2: Find steps without active experiments and create new ones
        active_steps = {
            (exp.sequence_step, exp.target_trade)
            for exp in active_experiments
            if exp.status == "active"  # Re-check in case we just completed one
        }

        # Refresh active list after potential completions
        refresh_result = await db.execute(
            select(ABTestExperiment).where(
                ABTestExperiment.status == "active"
            )
        )
        still_active = refresh_result.scalars().all()
        active_step_set = {(e.sequence_step, e.target_trade) for e in still_active}

    # Create experiments for uncovered steps (general, no trade filter)
    for step in EXPERIMENT_STEPS:
        if (step, None) not in active_step_set:
            try:
                result = await create_experiment(
                    sequence_step=step,
                    target_trade=None,
                    variant_count=3,
                )
                if result:
                    logger.info(
                        "Created new A/B experiment for step %d: %s",
                        step, result["name"],
                    )
            except Exception as e:
                logger.error(
                    "Failed to create A/B experiment for step %d: %s",
                    step, str(e),
                )
