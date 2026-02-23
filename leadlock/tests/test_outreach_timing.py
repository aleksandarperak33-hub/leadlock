from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.services.outreach_timing import (
    MIN_FOLLOWUP_DELAY_HOURS,
    followup_readiness,
    required_followup_delay_hours,
)


def _prospect(**overrides):
    defaults = {
        "outreach_sequence_step": 1,
        "last_email_sent_at": datetime.now(timezone.utc) - timedelta(hours=50),
        "last_email_opened_at": None,
        "last_email_clicked_at": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_step_zero_is_always_due():
    p = _prospect(outreach_sequence_step=0, last_email_sent_at=None)
    due, required, remaining = followup_readiness(p, base_delay_hours=48)
    assert due is True
    assert required == 0
    assert remaining == 0


def test_no_engagement_requires_longer_delay():
    p = _prospect(outreach_sequence_step=1)
    required = required_followup_delay_hours(p, base_delay_hours=48)
    assert required >= 72


def test_clicked_engagement_allows_faster_but_respects_floor():
    p = _prospect(last_email_clicked_at=datetime.now(timezone.utc) - timedelta(hours=1))
    required = required_followup_delay_hours(p, base_delay_hours=48)
    assert required >= MIN_FOLLOWUP_DELAY_HOURS
    assert required < 48


def test_followup_not_due_returns_remaining_seconds():
    p = _prospect(last_email_sent_at=datetime.now(timezone.utc) - timedelta(hours=10))
    due, required, remaining = followup_readiness(p, base_delay_hours=48)
    assert due is False
    assert required >= 72
    assert remaining > 0


def test_followup_due_after_required_window():
    p = _prospect(
        last_email_opened_at=datetime.now(timezone.utc) - timedelta(hours=1),
        last_email_sent_at=datetime.now(timezone.utc) - timedelta(hours=49),
    )
    due, required, remaining = followup_readiness(p, base_delay_hours=48)
    assert due is True
    assert required == 48
    assert remaining == 0

