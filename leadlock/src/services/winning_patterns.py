"""
Winning patterns service - store, query, and format proven email patterns.
Core of the intelligence loop: AB test winners and reflection insights
flow back into email generation as prompt context.
"""
import logging
import math
import uuid
from typing import Optional

from sqlalchemy import select, and_, or_

from src.database import async_session_factory
from src.models.winning_pattern import WinningPattern

logger = logging.getLogger(__name__)

# Minimum confidence to include in prompt context
MIN_CONFIDENCE_FOR_PROMPT = 0.3


def _calculate_confidence(sample_size: int, open_rate: float) -> float:
    """
    Calculate a confidence score (0.0-1.0) based on sample size and effect magnitude.
    Uses a simple logistic curve on sample size, scaled by open rate strength.

    Args:
        sample_size: Number of emails in the experiment
        open_rate: Open rate achieved (0.0-1.0)

    Returns:
        Confidence score from 0.0 to 1.0
    """
    if sample_size <= 0:
        return 0.0

    # Logistic curve: ramps from ~0.1 at n=10 to ~0.9 at n=100
    size_factor = 1.0 / (1.0 + math.exp(-0.05 * (sample_size - 50)))

    # Open rate bonus: higher open rates = higher confidence
    rate_factor = min(1.0, open_rate * 2.5) if open_rate > 0 else 0.5

    return round(min(1.0, size_factor * rate_factor), 3)


async def store_winning_pattern(
    source: str,
    instruction_text: str,
    trade: Optional[str] = None,
    step: Optional[int] = None,
    open_rate: float = 0.0,
    reply_rate: float = 0.0,
    sample_size: int = 0,
    source_id: Optional[str] = None,
) -> Optional[str]:
    """
    Store a proven winning pattern in the database.

    Args:
        source: "ab_test" or "reflection"
        instruction_text: The subject line instruction or pattern text
        trade: Trade type filter (None = all trades)
        step: Sequence step (None = all steps)
        open_rate: Observed open rate (0.0-1.0)
        reply_rate: Observed reply rate (0.0-1.0)
        sample_size: Number of emails in the sample
        source_id: UUID of the source experiment (optional)

    Returns:
        Pattern ID string, or None on error
    """
    if not instruction_text or not instruction_text.strip():
        logger.warning("Attempted to store empty winning pattern")
        return None

    confidence = _calculate_confidence(sample_size, open_rate)

    source_uuid = None
    if source_id:
        try:
            source_uuid = uuid.UUID(source_id)
        except (ValueError, TypeError):
            pass

    pattern = WinningPattern(
        source=source,
        source_id=source_uuid,
        instruction_text=instruction_text.strip(),
        trade=trade,
        sequence_step=step,
        open_rate=open_rate,
        reply_rate=reply_rate,
        sample_size=sample_size,
        confidence=confidence,
    )

    async with async_session_factory() as db:
        db.add(pattern)
        await db.commit()
        await db.refresh(pattern)

        logger.info(
            "Stored winning pattern: source=%s trade=%s step=%s "
            "open_rate=%.1f%% confidence=%.2f",
            source, trade or "all", step or "all",
            open_rate * 100, confidence,
        )
        return str(pattern.id)


async def get_winning_patterns(
    trade: Optional[str] = None,
    step: Optional[int] = None,
    limit: int = 3,
) -> list[dict]:
    """
    Query top winning patterns. Trade-specific first, falls back to general.

    Args:
        trade: Trade type to filter by (optional)
        step: Sequence step to filter by (optional)
        limit: Max patterns to return

    Returns:
        List of pattern dicts sorted by confidence descending
    """
    async with async_session_factory() as db:
        # Build filter: trade-specific OR general (trade IS NULL)
        trade_filter = or_(
            WinningPattern.trade == trade,
            WinningPattern.trade.is_(None),
        ) if trade else WinningPattern.trade.is_(None)

        # Build filter: step-specific OR general (step IS NULL)
        step_filter = or_(
            WinningPattern.sequence_step == step,
            WinningPattern.sequence_step.is_(None),
        ) if step else WinningPattern.sequence_step.is_(None)

        result = await db.execute(
            select(WinningPattern)
            .where(
                and_(
                    WinningPattern.is_active == True,
                    WinningPattern.confidence >= MIN_CONFIDENCE_FOR_PROMPT,
                    trade_filter,
                    step_filter,
                )
            )
            .order_by(WinningPattern.confidence.desc())
            .limit(limit)
        )
        patterns = result.scalars().all()

        return [
            {
                "id": str(p.id),
                "instruction": p.instruction_text,
                "trade": p.trade,
                "step": p.sequence_step,
                "open_rate": p.open_rate,
                "reply_rate": p.reply_rate,
                "confidence": p.confidence,
                "source": p.source,
            }
            for p in patterns
        ]


async def format_patterns_for_prompt(
    trade: Optional[str] = None,
    step: Optional[int] = None,
) -> str:
    """
    Format winning patterns as a string suitable for AI prompt injection.

    Args:
        trade: Trade type filter
        step: Sequence step filter

    Returns:
        Formatted string with winning patterns, or empty string if none found
    """
    patterns = await get_winning_patterns(trade=trade, step=step, limit=3)
    if not patterns:
        return ""

    lines = ["Proven winning approaches (bias toward these):"]
    for i, p in enumerate(patterns, 1):
        rate_info = f"open rate: {p['open_rate']:.0%}"
        if p["reply_rate"] > 0:
            rate_info += f", reply rate: {p['reply_rate']:.0%}"
        lines.append(f"{i}. {p['instruction']} ({rate_info})")

    return "\n".join(lines)
