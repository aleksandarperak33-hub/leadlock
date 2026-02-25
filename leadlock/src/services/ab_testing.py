"""
A/B testing service - creates experiments, assigns variants, computes winners.
One-Writer for ab_test_experiments/variants tables.

Experiment lifecycle:
1. create_experiment() generates 2-3 subject line variants via AI
2. assign_variant() deterministically assigns a variant to each email send
3. record_event() increments open/reply counters
4. check_winner() declares a winner when one variant beats others by >20% with n>=30
"""
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.ab_test import ABTestExperiment, ABTestVariant
from src.services.ai import generate_response, parse_json_content
from src.utils.agent_cost import track_agent_cost

logger = logging.getLogger(__name__)

# Subject line angle templates for variant generation
VARIANT_GENERATION_PROMPT = """You generate A/B test variants for cold email subject lines.

Given a sequence step and optional trade type, generate {count} distinct subject line INSTRUCTIONS.
Each instruction tells the email writer what angle/approach to take for the subject line.

Rules:
- Each variant must use a DIFFERENT angle (e.g., pain-point, curiosity, social proof, question, stat-based)
- Instructions should be 1-2 sentences describing the approach, NOT the actual subject line
- Be specific about the psychological trigger each variant uses
- Reference the trade type if provided

Output valid JSON only:
[
  {{"label": "A", "instruction": "..."}},
  {{"label": "B", "instruction": "..."}},
  ...
]"""


async def create_experiment(
    sequence_step: int,
    target_trade: Optional[str] = None,
    variant_count: int = 3,
    min_sample: int = 30,
) -> Optional[dict]:
    """
    Create a new A/B test experiment with AI-generated variants.

    Args:
        sequence_step: Which email step to test (1, 2, or 3)
        target_trade: Optional trade filter (NULL = all trades)
        variant_count: Number of variants to generate (2-3)
        min_sample: Minimum sends per variant before declaring winner

    Returns:
        {"experiment_id": str, "variants": list, "ai_cost_usd": float} or None on error
    """
    variant_count = max(2, min(variant_count, 3))

    trade_context = f" for {target_trade} contractors" if target_trade else " for home services contractors"
    user_message = (
        f"Generate {variant_count} subject line instruction variants "
        f"for email sequence step {sequence_step}{trade_context}."
    )

    # Fetch previous winning patterns to bias new variants toward proven approaches
    try:
        from src.services.winning_patterns import format_patterns_for_prompt

        patterns_context = await format_patterns_for_prompt(
            trade=target_trade, step=sequence_step,
        )
        if patterns_context:
            user_message += (
                f"\n\nPrevious winners (use as inspiration, but vary the angles):\n"
                f"{patterns_context}"
            )
    except Exception as wp_err:
        logger.debug("Could not fetch winning patterns for experiment: %s", str(wp_err))

    result = await generate_response(
        system_prompt=VARIANT_GENERATION_PROMPT.format(count=variant_count),
        user_message=user_message,
        model_tier="fast",
        max_tokens=300,
        temperature=0.7,
    )

    if result.get("error"):
        logger.error("Failed to generate A/B variants: %s", result["error"])
        return None

    variant_data, parse_error = parse_json_content(result.get("content", ""))
    if parse_error:
        logger.error("Failed to parse A/B variant response: %s", parse_error)
        return None

    if not isinstance(variant_data, list) or len(variant_data) < 2:
        logger.error("Invalid variant data: expected list of 2+, got %s", type(variant_data).__name__)
        return None

    # Track cost
    ai_cost = result.get("cost_usd", 0.0)
    await track_agent_cost("ab_testing", ai_cost)

    # Create experiment and variants in DB
    trade_label = target_trade or "all"
    experiment_name = f"Step {sequence_step} - {trade_label} - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

    async with async_session_factory() as db:
        experiment = ABTestExperiment(
            name=experiment_name,
            sequence_step=sequence_step,
            target_trade=target_trade,
            min_sample_per_variant=min_sample,
        )
        db.add(experiment)
        await db.flush()

        variants = []
        for item in variant_data[:variant_count]:
            variant = ABTestVariant(
                experiment_id=experiment.id,
                variant_label=item.get("label", chr(65 + len(variants))),
                subject_instruction=item.get("instruction", ""),
            )
            db.add(variant)
            variants.append({
                "label": variant.variant_label,
                "instruction": variant.subject_instruction,
            })

        await db.commit()

        logger.info(
            "Created A/B experiment: %s with %d variants (step=%d, trade=%s)",
            str(experiment.id)[:8], len(variants), sequence_step, trade_label,
        )

        return {
            "experiment_id": str(experiment.id),
            "name": experiment_name,
            "variants": variants,
            "ai_cost_usd": ai_cost,
        }


async def get_active_experiment(
    sequence_step: int,
    trade_type: Optional[str] = None,
) -> Optional[dict]:
    """
    Find an active experiment for a given step and trade.
    Returns experiment with variants or None if no active experiment.
    """
    async with async_session_factory() as db:
        # Look for trade-specific experiment first, then general
        for trade_filter in [trade_type, None]:
            query = select(ABTestExperiment).where(
                and_(
                    ABTestExperiment.status == "active",
                    ABTestExperiment.sequence_step == sequence_step,
                    ABTestExperiment.target_trade == trade_filter
                    if trade_filter
                    else ABTestExperiment.target_trade.is_(None),
                )
            ).limit(1)

            result = await db.execute(query)
            experiment = result.scalar_one_or_none()

            if experiment:
                variants_result = await db.execute(
                    select(ABTestVariant).where(
                        ABTestVariant.experiment_id == experiment.id
                    )
                )
                variants = variants_result.scalars().all()

                return {
                    "experiment_id": str(experiment.id),
                    "variants": [
                        {
                            "id": str(v.id),
                            "label": v.variant_label,
                            "instruction": v.subject_instruction,
                            "total_sent": v.total_sent,
                        }
                        for v in variants
                    ],
                }

    return None


def assign_variant(variants: list[dict]) -> dict:
    """
    Randomly assign a variant from the experiment.
    Uses uniform random distribution for fair assignment.

    Args:
        variants: List of variant dicts with "id", "label", "instruction"

    Returns:
        Selected variant dict
    """
    if not variants:
        return {}
    return random.choice(variants)


async def record_event(
    variant_id: str,
    event_type: str,
) -> None:
    """
    Record an open or reply event for a variant.

    Args:
        variant_id: UUID of the variant
        event_type: "sent", "opened", or "replied"
    """
    async with async_session_factory() as db:
        variant = await db.get(ABTestVariant, uuid.UUID(variant_id))
        if not variant:
            logger.warning("A/B variant not found: %s", variant_id[:8])
            return

        if event_type == "sent":
            variant.total_sent = variant.total_sent + 1
        elif event_type == "opened":
            variant.total_opened = variant.total_opened + 1
        elif event_type == "replied":
            variant.total_replied = variant.total_replied + 1

        # Recalculate open rate
        if variant.total_sent > 0:
            variant.open_rate = variant.total_opened / variant.total_sent

        await db.commit()


async def check_and_declare_winner(experiment_id: str) -> Optional[dict]:
    """
    Check if an experiment has a winner. A variant wins when:
    1. All variants have >= min_sample sends
    2. The best variant's open rate beats all others by >= 20% relative

    Returns:
        {"winner_label": str, "winner_open_rate": float} or None
    """
    async with async_session_factory() as db:
        experiment = await db.get(ABTestExperiment, uuid.UUID(experiment_id))
        if not experiment or experiment.status != "active":
            return None

        variants_result = await db.execute(
            select(ABTestVariant).where(
                ABTestVariant.experiment_id == experiment.id
            )
        )
        variants = variants_result.scalars().all()

        if len(variants) < 2:
            return None

        # Check minimum sample size
        min_sample = experiment.min_sample_per_variant
        if any(v.total_sent < min_sample for v in variants):
            return None

        # Find best variant by open rate
        sorted_variants = sorted(variants, key=lambda v: v.open_rate, reverse=True)
        best = sorted_variants[0]
        second_best = sorted_variants[1]

        # Winner must beat second-best by 20% relative
        if second_best.open_rate > 0:
            improvement = (best.open_rate - second_best.open_rate) / second_best.open_rate
        else:
            # If second best has 0 open rate, any opens = winner
            improvement = 1.0 if best.open_rate > 0 else 0.0

        if improvement < 0.20:
            return None  # No clear winner yet

        # Declare winner
        now = datetime.now(timezone.utc)
        best.is_winner = True
        experiment.winning_variant_id = best.id
        experiment.status = "completed"
        experiment.completed_at = now

        await db.commit()

        logger.info(
            "A/B test winner: experiment=%s variant=%s open_rate=%.1f%% (beat next by %.0f%%)",
            str(experiment.id)[:8], best.variant_label,
            best.open_rate * 100, improvement * 100,
        )

        # Store winning pattern for intelligence loop
        try:
            from src.services.winning_patterns import store_winning_pattern

            await store_winning_pattern(
                source="ab_test",
                instruction_text=best.subject_instruction,
                trade=experiment.target_trade,
                step=experiment.sequence_step,
                open_rate=best.open_rate,
                reply_rate=(best.total_replied / best.total_sent) if best.total_sent > 0 else 0.0,
                sample_size=best.total_sent,
                source_id=str(experiment.id),
            )
        except Exception as wp_err:
            logger.warning("Failed to store winning pattern: %s", str(wp_err))

        return {
            "winner_label": best.variant_label,
            "winner_instruction": best.subject_instruction,
            "winner_open_rate": best.open_rate,
            "improvement_pct": improvement,
        }
