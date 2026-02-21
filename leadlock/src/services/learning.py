"""
Learning service - records and queries engagement signals to feed back
into email generation. Tracks what works by trade, location, time, and step.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.learning_signal import LearningSignal

logger = logging.getLogger(__name__)


def _time_bucket(hour: int) -> str:
    """Convert hour to time bucket string."""
    if hour < 9:
        return "early_morning"
    elif hour < 12:
        return "9am-12pm"
    elif hour < 15:
        return "12pm-3pm"
    elif hour < 18:
        return "3pm-6pm"
    else:
        return "evening"


async def record_signal(
    signal_type: str,
    dimensions: dict,
    value: float,
    outreach_id: Optional[str] = None,
) -> None:
    """
    Record a learning signal for the feedback loop.

    Args:
        signal_type: email_opened, email_clicked, email_replied, email_bounced, demo_booked
        dimensions: Contextual data (trade, city, state, step, time_bucket, day_of_week)
        value: 1.0 for positive signal, 0.0 for negative
        outreach_id: Related outreach record ID
    """
    outreach_uuid = None
    if outreach_id:
        try:
            outreach_uuid = uuid.UUID(outreach_id)
        except (ValueError, TypeError):
            pass

    signal = LearningSignal(
        signal_type=signal_type,
        dimensions=dimensions,
        value=value,
        outreach_id=outreach_uuid,
    )

    async with async_session_factory() as db:
        db.add(signal)
        await db.commit()

    logger.debug(
        "Learning signal recorded: type=%s value=%.1f dims=%s",
        signal_type, value, dimensions,
    )


async def get_best_send_time(trade: str, state: str) -> Optional[str]:
    """
    Query the best time bucket for email sends based on open rate signals.

    Args:
        trade: Trade type (hvac, plumbing, etc)
        state: State code (TX, FL, etc)

    Returns:
        Best time bucket string (e.g., "9am-12pm") or None if insufficient data
    """
    async with async_session_factory() as db:
        # Query open signals grouped by time bucket
        result = await db.execute(
            select(
                func.jsonb_extract_path_text(LearningSignal.dimensions, "time_bucket").label("time_bucket"),
                func.avg(LearningSignal.value).label("avg_value"),
                func.count().label("sample_count"),
            )
            .where(
                and_(
                    LearningSignal.signal_type == "email_opened",
                    func.jsonb_extract_path_text(LearningSignal.dimensions, "trade") == trade,
                    func.jsonb_extract_path_text(LearningSignal.dimensions, "state") == state,
                )
            )
            .group_by(text("time_bucket"))
            .having(func.count() >= 5)  # Minimum sample size
            .order_by(text("avg_value DESC"))
            .limit(1)
        )

        row = result.first()
        if row:
            logger.info(
                "Best send time for %s in %s: %s (avg=%.2f, n=%d)",
                trade, state, row.time_bucket, row.avg_value, row.sample_count,
            )
            return row.time_bucket

    return None


async def get_open_rate_by_dimension(dimension: str, value: str) -> float:
    """
    Get aggregated open rate for a specific dimension value.

    Args:
        dimension: Dimension key (trade, city, state, step)
        value: Dimension value to filter by

    Returns:
        Open rate as a float (0.0-1.0)
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(func.avg(LearningSignal.value))
            .where(
                and_(
                    LearningSignal.signal_type == "email_opened",
                    func.jsonb_extract_path_text(LearningSignal.dimensions, dimension) == value,
                )
            )
        )
        rate = result.scalar()
        return float(rate) if rate is not None else 0.0


async def get_insights_summary() -> dict:
    """
    Get dashboard-ready aggregated learning insights.

    Returns:
        Dict with open rates by trade, by step, by day, top time buckets, etc.
    """
    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=30)

        # Open rate by trade
        trade_result = await db.execute(
            select(
                func.jsonb_extract_path_text(LearningSignal.dimensions, "trade").label("trade"),
                func.avg(LearningSignal.value).label("avg_rate"),
                func.count().label("count"),
            )
            .where(
                and_(
                    LearningSignal.signal_type == "email_opened",
                    LearningSignal.created_at >= since,
                )
            )
            .group_by(text("trade"))
            .order_by(text("avg_rate DESC"))
        )
        by_trade = [
            {"trade": row.trade, "open_rate": round(float(row.avg_rate), 3), "count": row.count}
            for row in trade_result.all()
            if row.trade
        ]

        # Open rate by time bucket
        time_result = await db.execute(
            select(
                func.jsonb_extract_path_text(LearningSignal.dimensions, "time_bucket").label("time_bucket"),
                func.avg(LearningSignal.value).label("avg_rate"),
                func.count().label("count"),
            )
            .where(
                and_(
                    LearningSignal.signal_type == "email_opened",
                    LearningSignal.created_at >= since,
                )
            )
            .group_by(text("time_bucket"))
            .order_by(text("avg_rate DESC"))
        )
        by_time = [
            {"time_bucket": row.time_bucket, "open_rate": round(float(row.avg_rate), 3), "count": row.count}
            for row in time_result.all()
            if row.time_bucket
        ]

        # Open rate by sequence step
        step_result = await db.execute(
            select(
                func.jsonb_extract_path_text(LearningSignal.dimensions, "step").label("step"),
                func.avg(LearningSignal.value).label("avg_rate"),
                func.count().label("count"),
            )
            .where(
                and_(
                    LearningSignal.signal_type == "email_opened",
                    LearningSignal.created_at >= since,
                )
            )
            .group_by(text("step"))
            .order_by(text("step"))
        )
        by_step = [
            {"step": row.step, "open_rate": round(float(row.avg_rate), 3), "count": row.count}
            for row in step_result.all()
            if row.step
        ]

        # Reply rate by trade
        reply_result = await db.execute(
            select(
                func.jsonb_extract_path_text(LearningSignal.dimensions, "trade").label("trade"),
                func.avg(LearningSignal.value).label("avg_rate"),
                func.count().label("count"),
            )
            .where(
                and_(
                    LearningSignal.signal_type == "email_replied",
                    LearningSignal.created_at >= since,
                )
            )
            .group_by(text("trade"))
            .order_by(text("avg_rate DESC"))
        )
        reply_by_trade = [
            {"trade": row.trade, "reply_rate": round(float(row.avg_rate), 3), "count": row.count}
            for row in reply_result.all()
            if row.trade
        ]

        # Total signals
        total_result = await db.execute(
            select(func.count()).select_from(LearningSignal).where(
                LearningSignal.created_at >= since
            )
        )
        total_signals = total_result.scalar() or 0

        return {
            "period_days": 30,
            "total_signals": total_signals,
            "open_rate_by_trade": by_trade,
            "open_rate_by_time": by_time,
            "open_rate_by_step": by_step,
            "reply_rate_by_trade": reply_by_trade,
        }
