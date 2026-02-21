"""
Tests for src/services/reporting.py - dashboard metrics generation.

Uses AsyncMock for the DB session to avoid SQLite/PostgreSQL date_trunc
incompatibility while achieving full coverage of all code paths.
"""
import uuid
from datetime import datetime, date, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.schemas.api_responses import DashboardMetrics, DayMetric, ResponseTimeBucket
from src.services.reporting import get_dashboard_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scalar(value):
    """Wrap a value in a mock result that returns it via .scalar()."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _all_rows(rows):
    """Wrap a list of tuples in a mock result that returns them via .all()."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _make_mock_db(
    total_leads=0,
    total_booked=0,
    avg_response_ms=None,
    leads_under_60s=0,
    total_messages=0,
    total_ai_cost=None,
    total_sms_cost=None,
    source_rows=None,
    state_rows=None,
    day_rows=None,
    response_ms_rows=None,
):
    """Build a mock AsyncSession with configurable return values.

    The query order in get_dashboard_metrics is:
    1. total_leads (count)
    2. total_booked (count)
    3. avg_response_ms (avg)
    4. leads_under_60s (count)
    5. total_messages (count)
    6. total_ai_cost (sum)
    7. total_sms_cost (sum)
    8. leads_by_source (group by)
    9. leads_by_state (group by)
    10. leads_by_day (group by)
    11. response_ms (individual values)
    """
    db = AsyncMock()

    # Build sequential return values for db.execute()
    returns = [
        _scalar(total_leads),
        _scalar(total_booked),
        _scalar(avg_response_ms),
        _scalar(leads_under_60s),
        _scalar(total_messages),
        _scalar(total_ai_cost),
        _scalar(total_sms_cost),
        _all_rows(source_rows or []),
        _all_rows(state_rows or []),
        _all_rows(day_rows or []),
        _all_rows(response_ms_rows or []),
    ]

    db.execute = AsyncMock(side_effect=returns)
    return db


# ---------------------------------------------------------------------------
# Tests: get_dashboard_metrics - empty dataset
# ---------------------------------------------------------------------------

class TestDashboardMetricsEmpty:
    async def test_returns_zeros_for_no_data(self):
        """Dashboard metrics with no leads returns all zeros."""
        db = _make_mock_db()
        result = await get_dashboard_metrics(db, "some-client-id", period="7d")

        assert isinstance(result, DashboardMetrics)
        assert result.total_leads == 0
        assert result.total_booked == 0
        assert result.conversion_rate == 0.0
        assert result.avg_response_time_ms == 0
        assert result.leads_under_60s == 0
        assert result.leads_under_60s_pct == 0.0
        assert result.total_messages == 0
        assert result.total_ai_cost == 0.0
        assert result.total_sms_cost == 0.0
        assert result.leads_by_source == {}
        assert result.leads_by_state == {}
        assert result.leads_by_day == []
        assert result.response_time_distribution == [
            ResponseTimeBucket(bucket="0-10s", count=0),
            ResponseTimeBucket(bucket="10-30s", count=0),
            ResponseTimeBucket(bucket="30-60s", count=0),
            ResponseTimeBucket(bucket="60s+", count=0),
        ]
        assert result.conversion_by_source == {}


# ---------------------------------------------------------------------------
# Tests: get_dashboard_metrics - with data
# ---------------------------------------------------------------------------

class TestDashboardMetricsWithData:
    async def test_counts_leads_correctly(self):
        """Counts total leads within the period."""
        db = _make_mock_db(total_leads=5)
        result = await get_dashboard_metrics(db, "client-1", period="7d")
        assert result.total_leads == 5

    async def test_counts_booked_leads(self):
        """Counts leads in booked/completed states."""
        db = _make_mock_db(total_leads=10, total_booked=4)
        result = await get_dashboard_metrics(db, "client-1", period="7d")
        assert result.total_booked == 4
        assert result.total_leads == 10

    async def test_conversion_rate(self):
        """Conversion rate is booked/total."""
        db = _make_mock_db(total_leads=10, total_booked=3)
        result = await get_dashboard_metrics(db, "client-1")
        assert result.conversion_rate == pytest.approx(0.3)

    async def test_conversion_rate_zero_leads(self):
        """Conversion rate is 0.0 when no leads."""
        db = _make_mock_db(total_leads=0, total_booked=0)
        result = await get_dashboard_metrics(db, "client-1")
        assert result.conversion_rate == 0.0

    async def test_average_response_time(self):
        """Calculates average first_response_ms."""
        db = _make_mock_db(total_leads=3, avg_response_ms=8500)
        result = await get_dashboard_metrics(db, "client-1")
        assert result.avg_response_time_ms == 8500

    async def test_average_response_time_none(self):
        """avg_response_ms defaults to 0 when None."""
        db = _make_mock_db(total_leads=3, avg_response_ms=None)
        result = await get_dashboard_metrics(db, "client-1")
        assert result.avg_response_time_ms == 0

    async def test_leads_under_60s(self):
        """Counts leads with response under 60s and percentage."""
        db = _make_mock_db(total_leads=4, leads_under_60s=3)
        result = await get_dashboard_metrics(db, "client-1")
        assert result.leads_under_60s == 3
        assert result.leads_under_60s_pct == pytest.approx(75.0)

    async def test_leads_under_60s_zero_leads(self):
        """Percentage is 0 when no leads."""
        db = _make_mock_db(total_leads=0, leads_under_60s=0)
        result = await get_dashboard_metrics(db, "client-1")
        assert result.leads_under_60s_pct == 0.0

    async def test_total_messages(self):
        """Counts total conversations (messages)."""
        db = _make_mock_db(total_leads=2, total_messages=15)
        result = await get_dashboard_metrics(db, "client-1")
        assert result.total_messages == 15

    async def test_cost_tracking(self):
        """Sums AI and SMS costs."""
        db = _make_mock_db(
            total_leads=2,
            total_ai_cost=0.15,
            total_sms_cost=0.05,
        )
        result = await get_dashboard_metrics(db, "client-1")
        assert result.total_ai_cost == pytest.approx(0.15)
        assert result.total_sms_cost == pytest.approx(0.05)

    async def test_cost_tracking_none(self):
        """Cost defaults to 0 when None."""
        db = _make_mock_db(total_leads=0, total_ai_cost=None, total_sms_cost=None)
        result = await get_dashboard_metrics(db, "client-1")
        assert result.total_ai_cost == 0.0
        assert result.total_sms_cost == 0.0

    async def test_leads_by_source(self):
        """Groups leads by source."""
        db = _make_mock_db(
            total_leads=3,
            source_rows=[("google_lsa", 2), ("website", 1)],
        )
        result = await get_dashboard_metrics(db, "client-1")
        assert result.leads_by_source == {"google_lsa": 2, "website": 1}

    async def test_leads_by_state(self):
        """Groups leads by state."""
        db = _make_mock_db(
            total_leads=3,
            state_rows=[("new", 1), ("booked", 2)],
        )
        result = await get_dashboard_metrics(db, "client-1")
        assert result.leads_by_state == {"new": 1, "booked": 2}

    async def test_leads_by_day(self):
        """Groups leads by day with booked counts."""
        day1 = datetime(2026, 2, 15, 0, 0, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 2, 16, 0, 0, 0, tzinfo=timezone.utc)

        db = _make_mock_db(
            total_leads=5,
            total_booked=2,
            day_rows=[(day1, 3, 1), (day2, 2, 1)],
        )
        result = await get_dashboard_metrics(db, "client-1")
        assert len(result.leads_by_day) == 2
        assert result.leads_by_day[0] == DayMetric(date="2026-02-15", count=3, booked=1)
        assert result.leads_by_day[1] == DayMetric(date="2026-02-16", count=2, booked=1)

    async def test_response_time_distribution(self):
        """Buckets response times into 0-10s, 10-30s, 30-60s, 60s+."""
        db = _make_mock_db(
            total_leads=4,
            response_ms_rows=[(5000,), (20000,), (45000,), (90000,)],
        )
        result = await get_dashboard_metrics(db, "client-1")
        dist = {b.bucket: b.count for b in result.response_time_distribution}
        assert dist["0-10s"] == 1
        assert dist["10-30s"] == 1
        assert dist["30-60s"] == 1
        assert dist["60s+"] == 1

    async def test_response_time_distribution_multiple_in_bucket(self):
        """Multiple responses in the same bucket are counted."""
        db = _make_mock_db(
            total_leads=3,
            response_ms_rows=[(3000,), (7000,), (9000,)],
        )
        result = await get_dashboard_metrics(db, "client-1")
        dist = {b.bucket: b.count for b in result.response_time_distribution}
        assert dist["0-10s"] == 3
        assert dist["10-30s"] == 0


# ---------------------------------------------------------------------------
# Tests: period parameter
# ---------------------------------------------------------------------------

class TestDashboardMetricsPeriods:
    async def test_7d_period(self):
        """7d period uses 7-day window."""
        db = _make_mock_db(total_leads=2)
        result = await get_dashboard_metrics(db, "client-1", period="7d")
        assert result.total_leads == 2

    async def test_30d_period(self):
        """30d period passes without error."""
        db = _make_mock_db(total_leads=5)
        result = await get_dashboard_metrics(db, "client-1", period="30d")
        assert result.total_leads == 5

    async def test_90d_period(self):
        """90d period passes without error."""
        db = _make_mock_db(total_leads=10)
        result = await get_dashboard_metrics(db, "client-1", period="90d")
        assert result.total_leads == 10

    async def test_unknown_period_defaults_to_7d(self):
        """Unknown period string defaults to 7 days."""
        db = _make_mock_db(total_leads=1)
        result = await get_dashboard_metrics(db, "client-1", period="invalid")
        assert result.total_leads == 1

    async def test_default_period_is_7d(self):
        """Default period (no argument) is 7d."""
        db = _make_mock_db(total_leads=3)
        result = await get_dashboard_metrics(db, "client-1")
        assert result.total_leads == 3


# ---------------------------------------------------------------------------
# Tests: full DashboardMetrics response structure
# ---------------------------------------------------------------------------

class TestDashboardMetricsStructure:
    async def test_full_response_structure(self):
        """Full response includes all expected fields with correct types."""
        day1 = datetime(2026, 2, 17, 0, 0, 0, tzinfo=timezone.utc)

        db = _make_mock_db(
            total_leads=10,
            total_booked=4,
            avg_response_ms=7500,
            leads_under_60s=8,
            total_messages=25,
            total_ai_cost=1.50,
            total_sms_cost=0.40,
            source_rows=[("google_lsa", 6), ("website", 4)],
            state_rows=[("new", 2), ("qualifying", 4), ("booked", 3), ("completed", 1)],
            day_rows=[(day1, 10, 4)],
            response_ms_rows=[(5000,), (15000,), (35000,), (70000,)],
        )
        result = await get_dashboard_metrics(db, "client-1", period="7d")

        # Verify types
        assert isinstance(result.total_leads, int)
        assert isinstance(result.total_booked, int)
        assert isinstance(result.conversion_rate, float)
        assert isinstance(result.avg_response_time_ms, int)
        assert isinstance(result.leads_under_60s, int)
        assert isinstance(result.leads_under_60s_pct, float)
        assert isinstance(result.total_messages, int)
        assert isinstance(result.total_ai_cost, float)
        assert isinstance(result.total_sms_cost, float)
        assert isinstance(result.leads_by_source, dict)
        assert isinstance(result.leads_by_state, dict)
        assert isinstance(result.leads_by_day, list)
        assert isinstance(result.response_time_distribution, list)
        assert isinstance(result.conversion_by_source, dict)

        # Verify values
        assert result.total_leads == 10
        assert result.total_booked == 4
        assert result.conversion_rate == pytest.approx(0.4)
        assert result.avg_response_time_ms == 7500
        assert result.leads_under_60s == 8
        assert result.leads_under_60s_pct == pytest.approx(80.0)
        assert result.total_messages == 25
        assert result.total_ai_cost == pytest.approx(1.50)
        assert result.total_sms_cost == pytest.approx(0.40)
        assert result.conversion_by_source == {}

    async def test_all_response_time_buckets_present(self):
        """All 4 response time buckets are always present, even if zero."""
        db = _make_mock_db(total_leads=0)
        result = await get_dashboard_metrics(db, "client-1")

        bucket_names = [b.bucket for b in result.response_time_distribution]
        assert "0-10s" in bucket_names
        assert "10-30s" in bucket_names
        assert "30-60s" in bucket_names
        assert "60s+" in bucket_names
