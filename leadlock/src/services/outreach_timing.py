"""
Outreach timing policy.
Centralized follow-up delay rules used by sequencer and task queue handlers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Tuple

MIN_FOLLOWUP_DELAY_HOURS = 36
NO_ENGAGEMENT_EXTRA_HOURS = 24
FINAL_TOUCH_EXTRA_HOURS = 24
CLICK_ENGAGEMENT_REDUCTION_HOURS = 12


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, (int, float, str)):
            return int(value)
    except Exception:
        pass
    return default


def _as_utc(dt: Any) -> datetime | None:
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def required_followup_delay_hours(
    prospect: Any,
    base_delay_hours: int | None,
) -> int:
    """
    Compute required delay before the next follow-up email can be sent.
    Rules:
    - Hard minimum floor to prevent aggressive follow-ups.
    - If prospect never opened/clicked, wait longer between touches.
    - If prospect clicked, allow a slightly faster (but still bounded) follow-up.
    """
    base_delay = max(_safe_int(base_delay_hours, 48), MIN_FOLLOWUP_DELAY_HOURS)
    current_step = _safe_int(getattr(prospect, "outreach_sequence_step", 0), 0)

    opened_at = _as_utc(getattr(prospect, "last_email_opened_at", None))
    clicked_at = _as_utc(getattr(prospect, "last_email_clicked_at", None))
    engaged = bool(opened_at or clicked_at)

    if clicked_at:
        return max(
            MIN_FOLLOWUP_DELAY_HOURS,
            base_delay - CLICK_ENGAGEMENT_REDUCTION_HOURS,
        )

    if not engaged:
        extra = NO_ENGAGEMENT_EXTRA_HOURS
        if current_step >= 2:
            extra += FINAL_TOUCH_EXTRA_HOURS
        return base_delay + extra

    return base_delay


def followup_readiness(
    prospect: Any,
    base_delay_hours: int | None,
    now: datetime | None = None,
) -> Tuple[bool, int, int]:
    """
    Returns:
        (is_due, required_delay_hours, remaining_seconds)
    """
    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    last_sent_at = _as_utc(getattr(prospect, "last_email_sent_at", None))
    current_step = _safe_int(getattr(prospect, "outreach_sequence_step", 0), 0)

    # Step 0 (never contacted) is always due.
    if current_step <= 0 or last_sent_at is None:
        return True, 0, 0

    required = required_followup_delay_hours(prospect, base_delay_hours)
    elapsed_seconds = int((now_utc - last_sent_at).total_seconds())
    required_seconds = required * 3600
    remaining = max(0, required_seconds - elapsed_seconds)

    return remaining == 0, required, remaining

