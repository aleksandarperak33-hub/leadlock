"""
Tests for src/api/metrics.py -- Metrics API endpoints.
Covers deliverability, funnel, response-times, costs, and worker health.
All external dependencies (database, Redis, deliverability service) are mocked.
"""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.metrics import (
    get_deliverability_metrics,
    get_number_reputation,
    get_lead_funnel,
    get_response_times,
    get_cost_metrics,
    get_worker_health,
)
from src.models.client import Client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DELIVERABILITY_SUMMARY_PATCH = "src.services.deliverability.get_deliverability_summary"
REPUTATION_SCORE_PATCH = "src.services.deliverability.get_reputation_score"
REDIS_PATCH = "src.utils.dedup.get_redis"


def _make_admin_client(client_id=None, is_admin=True):
    """Create a mock admin Client for dependency injection."""
    client = MagicMock(spec=Client)
    client.id = client_id or uuid.uuid4()
    client.is_admin = is_admin
    client.business_name = "Test HVAC Co"
    return client


def _make_state_row(state: str, count: int):
    """Create a mock row for the funnel state query."""
    row = MagicMock()
    row.state = state
    row.count = count
    return row


def _make_bucket_row(bucket: str, count: int):
    """Create a mock row for the response-time bucket query."""
    row = MagicMock()
    row.bucket = bucket
    row.count = count
    return row


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/deliverability
# ---------------------------------------------------------------------------


class TestGetDeliverabilityMetrics:
    """Covers lines 27-28."""

    async def test_returns_summary(self):
        """Deliverability endpoint delegates to get_deliverability_summary."""
        admin = _make_admin_client()
        expected = {
            "overall_delivery_rate": 0.97,
            "numbers": [{"phone": "+15125551234", "score": 92}],
        }
        with patch(DELIVERABILITY_SUMMARY_PATCH, new_callable=AsyncMock, return_value=expected):
            result = await get_deliverability_metrics(admin=admin)

        assert result == expected
        assert result["overall_delivery_rate"] == 0.97

    async def test_propagates_service_error(self):
        """If deliverability service raises, the error propagates."""
        admin = _make_admin_client()
        with patch(
            DELIVERABILITY_SUMMARY_PATCH,
            new_callable=AsyncMock,
            side_effect=Exception("redis unavailable"),
        ):
            with pytest.raises(Exception, match="redis unavailable"):
                await get_deliverability_metrics(admin=admin)


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/deliverability/{phone}
# ---------------------------------------------------------------------------


class TestGetNumberReputation:
    """Covers lines 34-35."""

    async def test_returns_reputation(self):
        """Number reputation endpoint delegates to get_reputation_score."""
        admin = _make_admin_client()
        expected = {
            "score": 85,
            "level": "good",
            "delivery_rate": 0.95,
            "total_sent_24h": 120,
            "delivered_24h": 114,
            "failed_24h": 3,
            "filtered_24h": 3,
            "invalid_24h": 0,
            "throttle_limit": 60,
        }
        with patch(REPUTATION_SCORE_PATCH, new_callable=AsyncMock, return_value=expected):
            result = await get_number_reputation(phone="+15125551234", admin=admin)

        assert result["score"] == 85
        assert result["level"] == "good"

    async def test_propagates_service_error(self):
        """If reputation service raises, the error propagates."""
        admin = _make_admin_client()
        with patch(
            REPUTATION_SCORE_PATCH,
            new_callable=AsyncMock,
            side_effect=Exception("lookup failed"),
        ):
            with pytest.raises(Exception, match="lookup failed"):
                await get_number_reputation(phone="+15125559999", admin=admin)


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/funnel
# ---------------------------------------------------------------------------


class TestGetLeadFunnel:
    """Covers lines 49-87 (and the return dict through line 110)."""

    async def test_funnel_with_leads(self):
        """Funnel returns state counts and computed rates when leads exist."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        state_rows = [
            _make_state_row("new", 10),
            _make_state_row("intake_sent", 8),
            _make_state_row("qualifying", 6),
            _make_state_row("qualified", 4),
            _make_state_row("booking", 3),
            _make_state_row("booked", 2),
            _make_state_row("completed", 1),
            _make_state_row("cold", 3),
            _make_state_row("dead", 1),
            _make_state_row("opted_out", 2),
        ]
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(state_rows)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_lead_funnel(client_id=None, days=7, db=mock_db, admin=admin)

        assert result["period_days"] == 7
        assert result["total_leads"] == 40  # sum of all
        assert result["states"]["qualifying"] == 6
        assert result["funnel"]["booked"] == 2
        assert result["funnel"]["cold"] == 3
        assert result["funnel"]["dead"] == 1
        assert result["funnel"]["opted_out"] == 2

        # engaged = qualifying + qualified + booking + booked + completed = 6+4+3+2+1 = 16
        assert result["rates"]["engagement_rate"] == round(16 / 40, 4)
        # converted = booked + completed = 2+1 = 3
        assert result["rates"]["conversion_rate"] == round(3 / 40, 4)
        # qualification_rate = (qualified + booking + booked + completed) / total = 10/40
        assert result["rates"]["qualification_rate"] == round(10 / 40, 4)
        # opt_out_rate = 2/40
        assert result["rates"]["opt_out_rate"] == round(2 / 40, 4)
        # cold_rate = (cold + dead) / total = 4/40
        assert result["rates"]["cold_rate"] == round(4 / 40, 4)

    async def test_funnel_with_no_leads(self):
        """When no leads exist, rates should all be 0."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_lead_funnel(client_id=None, days=30, db=mock_db, admin=admin)

        assert result["total_leads"] == 0
        assert result["rates"]["engagement_rate"] == 0
        assert result["rates"]["conversion_rate"] == 0
        assert result["rates"]["qualification_rate"] == 0
        assert result["rates"]["opt_out_rate"] == 0
        assert result["rates"]["cold_rate"] == 0

    async def test_funnel_with_valid_client_id(self):
        """When a valid client_id is provided, the query is filtered."""
        admin = _make_admin_client()
        mock_db = AsyncMock()
        cid = str(uuid.uuid4())

        state_rows = [_make_state_row("booked", 5)]
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(state_rows)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_lead_funnel(client_id=cid, days=14, db=mock_db, admin=admin)

        assert result["period_days"] == 14
        assert result["total_leads"] == 5
        assert result["funnel"]["booked"] == 5

    async def test_funnel_with_invalid_client_id(self):
        """An invalid client_id raises HTTP 400."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_lead_funnel(client_id="not-a-uuid", days=7, db=mock_db, admin=admin)

        assert exc_info.value.status_code == 400
        assert "Invalid client_id" in exc_info.value.detail

    async def test_funnel_missing_states_default_to_zero(self):
        """States not present in the DB default to 0 in the funnel."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        # Only one state returned
        state_rows = [_make_state_row("qualifying", 3)]
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter(state_rows)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_lead_funnel(client_id=None, days=7, db=mock_db, admin=admin)

        assert result["funnel"]["new"] == 0
        assert result["funnel"]["intake_sent"] == 0
        assert result["funnel"]["booking"] == 0
        assert result["funnel"]["booked"] == 0
        assert result["funnel"]["completed"] == 0
        assert result["funnel"]["cold"] == 0
        assert result["funnel"]["dead"] == 0
        assert result["funnel"]["opted_out"] == 0
        assert result["funnel"]["qualifying"] == 3


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/response-times
# ---------------------------------------------------------------------------


class TestGetResponseTimes:
    """Covers lines 124-169 (and the return dict through line 180)."""

    async def test_response_times_with_data(self):
        """Response times endpoint returns aggregated stats and buckets."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        # First query: aggregate stats
        stats_row = MagicMock()
        stats_row.total = 100
        stats_row.avg_ms = 8500
        stats_row.min_ms = 2000
        stats_row.max_ms = 45000
        stats_row.p50_ms = 7000
        stats_row.p95_ms = 28000
        stats_row.p99_ms = 42000

        stats_result = MagicMock()
        stats_result.one.return_value = stats_row

        # Second query: bucket counts
        bucket_rows = [
            _make_bucket_row("under_10s", 72),
            _make_bucket_row("10s_to_30s", 20),
            _make_bucket_row("30s_to_60s", 5),
            _make_bucket_row("over_60s", 3),
        ]
        bucket_result = MagicMock()
        bucket_result.__iter__ = lambda self: iter(bucket_rows)

        mock_db.execute = AsyncMock(side_effect=[stats_result, bucket_result])

        result = await get_response_times(client_id=None, days=7, db=mock_db, admin=admin)

        assert result["period_days"] == 7
        assert result["total_leads"] == 100
        assert result["avg_ms"] == 8500
        assert result["min_ms"] == 2000
        assert result["max_ms"] == 45000
        assert result["p50_ms"] == 7000
        assert result["p95_ms"] == 28000
        assert result["p99_ms"] == 42000
        assert result["sla_met_rate"] == round(72 / 100, 4)
        assert result["buckets"]["under_10s"] == 72
        assert result["buckets"]["over_60s"] == 3

    async def test_response_times_no_data(self):
        """When there are no leads with response times, all values are 0."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        stats_row = MagicMock()
        stats_row.total = 0
        stats_row.avg_ms = None
        stats_row.min_ms = None
        stats_row.max_ms = None
        stats_row.p50_ms = None
        stats_row.p95_ms = None
        stats_row.p99_ms = None

        stats_result = MagicMock()
        stats_result.one.return_value = stats_row

        bucket_result = MagicMock()
        bucket_result.__iter__ = lambda self: iter([])

        mock_db.execute = AsyncMock(side_effect=[stats_result, bucket_result])

        result = await get_response_times(client_id=None, days=7, db=mock_db, admin=admin)

        assert result["total_leads"] == 0
        assert result["avg_ms"] == 0
        assert result["min_ms"] == 0
        assert result["max_ms"] == 0
        assert result["p50_ms"] == 0
        assert result["p95_ms"] == 0
        assert result["p99_ms"] == 0
        assert result["sla_met_rate"] == 0
        assert result["buckets"] == {}

    async def test_response_times_with_valid_client_id(self):
        """Filtering by a valid client_id executes without error."""
        admin = _make_admin_client()
        mock_db = AsyncMock()
        cid = str(uuid.uuid4())

        stats_row = MagicMock()
        stats_row.total = 10
        stats_row.avg_ms = 5000
        stats_row.min_ms = 1000
        stats_row.max_ms = 12000
        stats_row.p50_ms = 4500
        stats_row.p95_ms = 11000
        stats_row.p99_ms = 11900

        stats_result = MagicMock()
        stats_result.one.return_value = stats_row

        bucket_rows = [_make_bucket_row("under_10s", 8), _make_bucket_row("10s_to_30s", 2)]
        bucket_result = MagicMock()
        bucket_result.__iter__ = lambda self: iter(bucket_rows)

        mock_db.execute = AsyncMock(side_effect=[stats_result, bucket_result])

        result = await get_response_times(client_id=cid, days=30, db=mock_db, admin=admin)

        assert result["period_days"] == 30
        assert result["total_leads"] == 10
        assert result["sla_met_rate"] == round(8 / 10, 4)

    async def test_response_times_invalid_client_id(self):
        """An invalid client_id raises HTTP 400."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_response_times(client_id="bad-uuid", days=7, db=mock_db, admin=admin)

        assert exc_info.value.status_code == 400
        assert "Invalid client_id" in exc_info.value.detail


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/costs
# ---------------------------------------------------------------------------


class TestGetCostMetrics:
    """Covers lines 193-219 (and the return dict through line 228)."""

    async def test_costs_with_data(self):
        """Cost endpoint returns aggregated cost data."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        row = MagicMock()
        row.total_leads = 50
        row.total_sms_cost = 3.95
        row.total_ai_cost = 1.25
        row.total_messages_sent = 150
        row.total_messages_received = 80

        mock_result = MagicMock()
        mock_result.one.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_cost_metrics(client_id=None, days=7, db=mock_db, admin=admin)

        assert result["period_days"] == 7
        assert result["total_leads"] == 50
        assert result["sms_cost_usd"] == round(3.95, 4)
        assert result["ai_cost_usd"] == round(1.25, 4)
        assert result["total_cost_usd"] == round(3.95 + 1.25, 4)
        assert result["cost_per_lead_usd"] == round(5.20 / 50, 4)
        assert result["total_messages_sent"] == 150
        assert result["total_messages_received"] == 80

    async def test_costs_no_leads(self):
        """When no leads exist, costs are all zero."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        row = MagicMock()
        row.total_leads = 0
        row.total_sms_cost = None
        row.total_ai_cost = None
        row.total_messages_sent = None
        row.total_messages_received = None

        mock_result = MagicMock()
        mock_result.one.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_cost_metrics(client_id=None, days=7, db=mock_db, admin=admin)

        assert result["total_leads"] == 0
        assert result["total_cost_usd"] == 0
        assert result["sms_cost_usd"] == 0
        assert result["ai_cost_usd"] == 0
        assert result["cost_per_lead_usd"] == 0
        assert result["total_messages_sent"] == 0
        assert result["total_messages_received"] == 0

    async def test_costs_with_valid_client_id(self):
        """Filtering by a valid client_id executes without error."""
        admin = _make_admin_client()
        mock_db = AsyncMock()
        cid = str(uuid.uuid4())

        row = MagicMock()
        row.total_leads = 10
        row.total_sms_cost = 0.79
        row.total_ai_cost = 0.10
        row.total_messages_sent = 30
        row.total_messages_received = 15

        mock_result = MagicMock()
        mock_result.one.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_cost_metrics(client_id=cid, days=14, db=mock_db, admin=admin)

        assert result["period_days"] == 14
        assert result["total_leads"] == 10
        assert result["cost_per_lead_usd"] == round(0.89 / 10, 4)

    async def test_costs_invalid_client_id(self):
        """An invalid client_id raises HTTP 400."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_cost_metrics(client_id="not-valid", days=7, db=mock_db, admin=admin)

        assert exc_info.value.status_code == 400
        assert "Invalid client_id" in exc_info.value.detail

    async def test_costs_null_totals_treated_as_zero(self):
        """When DB returns None for totals (no matching rows), values are 0."""
        admin = _make_admin_client()
        mock_db = AsyncMock()

        row = MagicMock()
        row.total_leads = None
        row.total_sms_cost = None
        row.total_ai_cost = None
        row.total_messages_sent = None
        row.total_messages_received = None

        mock_result = MagicMock()
        mock_result.one.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_cost_metrics(client_id=None, days=7, db=mock_db, admin=admin)

        assert result["total_leads"] == 0
        assert result["total_cost_usd"] == 0
        assert result["cost_per_lead_usd"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/metrics/health/workers
# ---------------------------------------------------------------------------


class TestGetWorkerHealth:
    """Covers lines 234-276."""

    async def test_all_workers_healthy(self):
        """All workers with recent heartbeats report as healthy."""
        admin = _make_admin_client()
        mock_redis = AsyncMock()

        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(seconds=30)).isoformat()

        # Every worker has a recent heartbeat
        mock_redis.get = AsyncMock(return_value=recent_ts)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            result = await get_worker_health(admin=admin)

        workers = result["workers"]
        assert len(workers) == 7
        for name, info in workers.items():
            assert info["status"] == "healthy"
            assert info["last_heartbeat"] == recent_ts
            assert info["age_seconds"] < 600

    async def test_stale_worker(self):
        """A worker with an old heartbeat (>600s) reports as stale."""
        admin = _make_admin_client()
        mock_redis = AsyncMock()

        now = datetime.now(timezone.utc)
        stale_ts = (now - timedelta(seconds=900)).isoformat()

        mock_redis.get = AsyncMock(return_value=stale_ts)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            result = await get_worker_health(admin=admin)

        workers = result["workers"]
        for name, info in workers.items():
            assert info["status"] == "stale"
            assert info["age_seconds"] >= 600

    async def test_unknown_worker_no_heartbeat(self):
        """A worker with no heartbeat at all reports as unknown."""
        admin = _make_admin_client()
        mock_redis = AsyncMock()

        mock_redis.get = AsyncMock(return_value=None)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            result = await get_worker_health(admin=admin)

        workers = result["workers"]
        for name, info in workers.items():
            assert info["status"] == "unknown"
            assert info["last_heartbeat"] is None
            assert info["age_seconds"] is None

    async def test_mixed_worker_statuses(self):
        """Workers can have mixed healthy/stale/unknown statuses."""
        admin = _make_admin_client()
        mock_redis = AsyncMock()

        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(seconds=30)).isoformat()
        stale_ts = (now - timedelta(seconds=900)).isoformat()

        # Return different values per worker key
        async def mock_get(key):
            if "system_health" in key:
                return recent_ts
            if "retry_worker" in key:
                return stale_ts
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            result = await get_worker_health(admin=admin)

        workers = result["workers"]
        assert workers["system_health"]["status"] == "healthy"
        assert workers["retry_worker"]["status"] == "stale"
        assert workers["lead_state_manager"]["status"] == "unknown"

    async def test_redis_failure_returns_error(self):
        """If Redis connection fails, return empty workers with error."""
        admin = _make_admin_client()

        with patch(
            REDIS_PATCH,
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ):
            result = await get_worker_health(admin=admin)

        assert result["workers"] == {}
        assert "error" in result
        assert "Failed to check worker health" in result["error"]

    async def test_heartbeat_bytes_decoded(self):
        """Heartbeat values returned as bytes are decoded properly."""
        admin = _make_admin_client()
        mock_redis = AsyncMock()

        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(seconds=10)).isoformat()
        # Return bytes instead of str
        mock_redis.get = AsyncMock(return_value=recent_ts.encode("utf-8"))

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            result = await get_worker_health(admin=admin)

        workers = result["workers"]
        for name, info in workers.items():
            assert info["status"] == "healthy"
            assert info["last_heartbeat"] == recent_ts

    async def test_heartbeat_naive_datetime_gets_utc(self):
        """A naive datetime (no tzinfo) in heartbeat gets treated as UTC."""
        admin = _make_admin_client()
        mock_redis = AsyncMock()

        now = datetime.now(timezone.utc)
        # Naive timestamp (no timezone suffix)
        naive_ts = (now - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%S")
        mock_redis.get = AsyncMock(return_value=naive_ts)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            result = await get_worker_health(admin=admin)

        workers = result["workers"]
        for name, info in workers.items():
            assert info["status"] == "healthy"
            # Age should be approximately 60 seconds, not wildly off
            assert 50 <= info["age_seconds"] <= 120

    async def test_worker_list_completeness(self):
        """All 7 expected workers are present in the response."""
        admin = _make_admin_client()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=mock_redis):
            result = await get_worker_health(admin=admin)

        expected_workers = {
            "system_health",
            "retry_worker",
            "lead_state_manager",
            "crm_sync",
            "sms_dispatch",
            "outreach_monitor",
            "registration_poller",
        }
        assert set(result["workers"].keys()) == expected_workers
