"""
Tests for src/services/learning.py - engagement signal recording and time bucketing.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.learning import _time_bucket, record_signal


# ---------------------------------------------------------------------------
# _time_bucket
# ---------------------------------------------------------------------------

class TestTimeBucket:
    def test_early_morning_hours(self):
        """Hours before 9am are 'early_morning'."""
        assert _time_bucket(0) == "early_morning"
        assert _time_bucket(5) == "early_morning"
        assert _time_bucket(8) == "early_morning"

    def test_morning_9am_to_noon(self):
        """Hours 9-11 are '9am-12pm'."""
        assert _time_bucket(9) == "9am-12pm"
        assert _time_bucket(10) == "9am-12pm"
        assert _time_bucket(11) == "9am-12pm"

    def test_afternoon_noon_to_3pm(self):
        """Hours 12-14 are '12pm-3pm'."""
        assert _time_bucket(12) == "12pm-3pm"
        assert _time_bucket(13) == "12pm-3pm"
        assert _time_bucket(14) == "12pm-3pm"

    def test_late_afternoon_3pm_to_6pm(self):
        """Hours 15-17 are '3pm-6pm'."""
        assert _time_bucket(15) == "3pm-6pm"
        assert _time_bucket(16) == "3pm-6pm"
        assert _time_bucket(17) == "3pm-6pm"

    def test_evening_6pm_and_later(self):
        """Hours 18+ are 'evening'."""
        assert _time_bucket(18) == "evening"
        assert _time_bucket(21) == "evening"
        assert _time_bucket(23) == "evening"

    def test_boundary_9(self):
        """Hour 9 is the start of the morning bucket."""
        assert _time_bucket(9) == "9am-12pm"

    def test_boundary_12(self):
        """Hour 12 is the start of the afternoon bucket."""
        assert _time_bucket(12) == "12pm-3pm"

    def test_boundary_15(self):
        """Hour 15 is the start of the late afternoon bucket."""
        assert _time_bucket(15) == "3pm-6pm"

    def test_boundary_18(self):
        """Hour 18 is the start of the evening bucket."""
        assert _time_bucket(18) == "evening"


# ---------------------------------------------------------------------------
# record_signal
# ---------------------------------------------------------------------------

def _mock_async_session_factory():
    """Return a mock session factory and the mock db it yields."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    class _FakeCtx:
        async def __aenter__(self):
            return mock_db
        async def __aexit__(self, *args):
            pass

    return _FakeCtx, mock_db


class TestRecordSignal:
    @pytest.mark.asyncio
    async def test_creates_learning_signal(self):
        """record_signal adds a LearningSignal to the DB session."""
        factory_cls, mock_db = _mock_async_session_factory()

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            await record_signal(
                signal_type="email_opened",
                dimensions={"trade": "hvac", "state": "TX", "time_bucket": "9am-12pm"},
                value=1.0,
            )

        mock_db.add.assert_called_once()
        signal = mock_db.add.call_args[0][0]
        assert signal.signal_type == "email_opened"
        assert signal.dimensions["trade"] == "hvac"
        assert signal.value == 1.0
        assert signal.outreach_id is None
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_valid_outreach_id(self):
        """Valid outreach_id is converted to UUID and stored."""
        factory_cls, mock_db = _mock_async_session_factory()
        outreach_uuid = str(uuid.uuid4())

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            await record_signal(
                signal_type="email_replied",
                dimensions={"trade": "plumbing"},
                value=1.0,
                outreach_id=outreach_uuid,
            )

        signal = mock_db.add.call_args[0][0]
        assert signal.outreach_id == uuid.UUID(outreach_uuid)

    @pytest.mark.asyncio
    async def test_invalid_outreach_id_stored_as_none(self):
        """Invalid outreach_id string results in None (not a crash)."""
        factory_cls, mock_db = _mock_async_session_factory()

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            await record_signal(
                signal_type="email_bounced",
                dimensions={"trade": "hvac"},
                value=0.0,
                outreach_id="not-a-uuid",
            )

        signal = mock_db.add.call_args[0][0]
        assert signal.outreach_id is None

    @pytest.mark.asyncio
    async def test_negative_signal_value(self):
        """Negative signals (value=0.0) are stored correctly."""
        factory_cls, mock_db = _mock_async_session_factory()

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            await record_signal(
                signal_type="email_bounced",
                dimensions={"trade": "roofing", "step": 2},
                value=0.0,
            )

        signal = mock_db.add.call_args[0][0]
        assert signal.value == 0.0

    @pytest.mark.asyncio
    async def test_none_outreach_id(self):
        """None outreach_id is handled gracefully."""
        factory_cls, mock_db = _mock_async_session_factory()

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            await record_signal(
                signal_type="demo_booked",
                dimensions={"trade": "solar"},
                value=1.0,
                outreach_id=None,
            )

        signal = mock_db.add.call_args[0][0]
        assert signal.outreach_id is None
