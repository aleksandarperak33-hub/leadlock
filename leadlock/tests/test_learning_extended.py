"""
Extended tests for src/services/learning.py - covers get_best_send_time,
get_open_rate_by_dimension, and get_insights_summary using mock sessions.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


from src.services.learning import (
    get_best_send_time,
    get_open_rate_by_dimension,
    get_insights_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session_factory(mock_db):
    """Build a mock async_session_factory that yields mock_db."""

    class _FakeCtx:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *args):
            pass

    return _FakeCtx


# ---------------------------------------------------------------------------
# get_best_send_time (lines 83-112)
# ---------------------------------------------------------------------------


class TestGetBestSendTime:
    @pytest.mark.asyncio
    async def test_returns_best_time_bucket_when_data_exists(self):
        """Returns the top time_bucket when sufficient data is available."""
        mock_row = MagicMock()
        mock_row.time_bucket = "9am-12pm"
        mock_row.avg_value = 0.75
        mock_row.sample_count = 20

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_best_send_time("hvac", "TX")

        assert result == "9am-12pm"
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_data(self):
        """Returns None when no rows meet the minimum sample threshold."""
        mock_result = MagicMock()
        mock_result.first.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_best_send_time("plumbing", "FL")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_evening_bucket(self):
        """Returns 'evening' when that is the best bucket."""
        mock_row = MagicMock()
        mock_row.time_bucket = "evening"
        mock_row.avg_value = 0.92
        mock_row.sample_count = 50

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_best_send_time("roofing", "CA")

        assert result == "evening"


# ---------------------------------------------------------------------------
# get_open_rate_by_dimension (lines 126-137)
# ---------------------------------------------------------------------------


class TestGetOpenRateByDimension:
    @pytest.mark.asyncio
    async def test_returns_rate_when_data_exists(self):
        """Returns the aggregated open rate as a float."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0.65

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_open_rate_by_dimension("trade", "hvac")

        assert result == 0.65

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_data(self):
        """Returns 0.0 when no matching signals exist."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_open_rate_by_dimension("city", "Nonexistent")

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_returns_float_conversion(self):
        """Ensures the result is cast to float properly."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_open_rate_by_dimension("state", "TX")

        assert result == 1.0
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# get_insights_summary (lines 147-247)
# ---------------------------------------------------------------------------


class TestGetInsightsSummary:
    @pytest.mark.asyncio
    async def test_returns_full_summary_with_data(self):
        """Returns a complete insights dict when learning data exists."""
        # Mock rows for trade query
        trade_row = MagicMock()
        trade_row.trade = "hvac"
        trade_row.avg_rate = 0.45
        trade_row.count = 100

        # Mock rows for time bucket query
        time_row = MagicMock()
        time_row.time_bucket = "9am-12pm"
        time_row.avg_rate = 0.62
        time_row.count = 80

        # Mock rows for step query
        step_row = MagicMock()
        step_row.step = "1"
        step_row.avg_rate = 0.55
        step_row.count = 60

        # Mock rows for reply query
        reply_row = MagicMock()
        reply_row.trade = "plumbing"
        reply_row.avg_rate = 0.12
        reply_row.count = 30

        # Build mock results for each execute call
        trade_result = MagicMock()
        trade_result.all.return_value = [trade_row]

        time_result = MagicMock()
        time_result.all.return_value = [time_row]

        step_result = MagicMock()
        step_result.all.return_value = [step_row]

        reply_result = MagicMock()
        reply_result.all.return_value = [reply_row]

        total_result = MagicMock()
        total_result.scalar.return_value = 270

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[trade_result, time_result, step_result, reply_result, total_result]
        )

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_insights_summary()

        assert result["period_days"] == 30
        assert result["total_signals"] == 270
        assert len(result["open_rate_by_trade"]) == 1
        assert result["open_rate_by_trade"][0]["trade"] == "hvac"
        assert result["open_rate_by_trade"][0]["open_rate"] == 0.45
        assert result["open_rate_by_trade"][0]["count"] == 100
        assert len(result["open_rate_by_time"]) == 1
        assert result["open_rate_by_time"][0]["time_bucket"] == "9am-12pm"
        assert len(result["open_rate_by_step"]) == 1
        assert result["open_rate_by_step"][0]["step"] == "1"
        assert len(result["reply_rate_by_trade"]) == 1
        assert result["reply_rate_by_trade"][0]["trade"] == "plumbing"
        assert result["reply_rate_by_trade"][0]["reply_rate"] == 0.12

    @pytest.mark.asyncio
    async def test_returns_empty_summary_with_no_data(self):
        """Returns zeroed-out summary when no learning signals exist."""
        empty_result = MagicMock()
        empty_result.all.return_value = []

        total_result = MagicMock()
        total_result.scalar.return_value = 0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[empty_result, empty_result, empty_result, empty_result, total_result]
        )

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_insights_summary()

        assert result["period_days"] == 30
        assert result["total_signals"] == 0
        assert result["open_rate_by_trade"] == []
        assert result["open_rate_by_time"] == []
        assert result["open_rate_by_step"] == []
        assert result["reply_rate_by_trade"] == []

    @pytest.mark.asyncio
    async def test_filters_out_null_trade_rows(self):
        """Rows with trade=None are excluded from the results."""
        null_trade_row = MagicMock()
        null_trade_row.trade = None
        null_trade_row.avg_rate = 0.5
        null_trade_row.count = 10

        valid_trade_row = MagicMock()
        valid_trade_row.trade = "hvac"
        valid_trade_row.avg_rate = 0.7
        valid_trade_row.count = 20

        trade_result = MagicMock()
        trade_result.all.return_value = [null_trade_row, valid_trade_row]

        empty_result = MagicMock()
        empty_result.all.return_value = []

        total_result = MagicMock()
        total_result.scalar.return_value = 30

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[trade_result, empty_result, empty_result, empty_result, total_result]
        )

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_insights_summary()

        assert len(result["open_rate_by_trade"]) == 1
        assert result["open_rate_by_trade"][0]["trade"] == "hvac"

    @pytest.mark.asyncio
    async def test_filters_out_null_time_bucket_rows(self):
        """Rows with time_bucket=None are excluded from by_time results."""
        null_row = MagicMock()
        null_row.time_bucket = None
        null_row.avg_rate = 0.3
        null_row.count = 5

        valid_row = MagicMock()
        valid_row.time_bucket = "evening"
        valid_row.avg_rate = 0.8
        valid_row.count = 40

        time_result = MagicMock()
        time_result.all.return_value = [null_row, valid_row]

        empty_result = MagicMock()
        empty_result.all.return_value = []

        total_result = MagicMock()
        total_result.scalar.return_value = 45

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[empty_result, time_result, empty_result, empty_result, total_result]
        )

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_insights_summary()

        assert len(result["open_rate_by_time"]) == 1
        assert result["open_rate_by_time"][0]["time_bucket"] == "evening"

    @pytest.mark.asyncio
    async def test_filters_out_null_step_rows(self):
        """Rows with step=None are excluded from by_step results."""
        null_step = MagicMock()
        null_step.step = None
        null_step.avg_rate = 0.2
        null_step.count = 3

        valid_step = MagicMock()
        valid_step.step = "2"
        valid_step.avg_rate = 0.4
        valid_step.count = 15

        step_result = MagicMock()
        step_result.all.return_value = [null_step, valid_step]

        empty_result = MagicMock()
        empty_result.all.return_value = []

        total_result = MagicMock()
        total_result.scalar.return_value = 18

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[empty_result, empty_result, step_result, empty_result, total_result]
        )

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_insights_summary()

        assert len(result["open_rate_by_step"]) == 1
        assert result["open_rate_by_step"][0]["step"] == "2"

    @pytest.mark.asyncio
    async def test_filters_out_null_reply_trade_rows(self):
        """Rows with trade=None in reply results are excluded."""
        null_row = MagicMock()
        null_row.trade = None
        null_row.avg_rate = 0.1
        null_row.count = 2

        reply_result = MagicMock()
        reply_result.all.return_value = [null_row]

        empty_result = MagicMock()
        empty_result.all.return_value = []

        total_result = MagicMock()
        total_result.scalar.return_value = 2

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[empty_result, empty_result, empty_result, reply_result, total_result]
        )

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_insights_summary()

        assert result["reply_rate_by_trade"] == []

    @pytest.mark.asyncio
    async def test_total_signals_defaults_to_zero(self):
        """When total_result.scalar() returns None, total_signals defaults to 0."""
        empty_result = MagicMock()
        empty_result.all.return_value = []

        total_result = MagicMock()
        total_result.scalar.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[empty_result, empty_result, empty_result, empty_result, total_result]
        )

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_insights_summary()

        assert result["total_signals"] == 0

    @pytest.mark.asyncio
    async def test_multiple_trades_returned(self):
        """Multiple trade rows are returned in order."""
        row1 = MagicMock()
        row1.trade = "hvac"
        row1.avg_rate = 0.8
        row1.count = 50

        row2 = MagicMock()
        row2.trade = "plumbing"
        row2.avg_rate = 0.6
        row2.count = 30

        trade_result = MagicMock()
        trade_result.all.return_value = [row1, row2]

        empty_result = MagicMock()
        empty_result.all.return_value = []

        total_result = MagicMock()
        total_result.scalar.return_value = 80

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[trade_result, empty_result, empty_result, empty_result, total_result]
        )

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_insights_summary()

        assert len(result["open_rate_by_trade"]) == 2
        assert result["open_rate_by_trade"][0]["trade"] == "hvac"
        assert result["open_rate_by_trade"][0]["open_rate"] == 0.8
        assert result["open_rate_by_trade"][1]["trade"] == "plumbing"
        assert result["open_rate_by_trade"][1]["open_rate"] == 0.6

    @pytest.mark.asyncio
    async def test_open_rate_rounding(self):
        """Open rates are rounded to 3 decimal places."""
        row = MagicMock()
        row.trade = "solar"
        row.avg_rate = 0.33333333
        row.count = 15

        trade_result = MagicMock()
        trade_result.all.return_value = [row]

        empty_result = MagicMock()
        empty_result.all.return_value = []

        total_result = MagicMock()
        total_result.scalar.return_value = 15

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[trade_result, empty_result, empty_result, empty_result, total_result]
        )

        factory_cls = _make_mock_session_factory(mock_db)

        with patch("src.services.learning.async_session_factory", return_value=factory_cls()):
            result = await get_insights_summary()

        assert result["open_rate_by_trade"][0]["open_rate"] == 0.333
