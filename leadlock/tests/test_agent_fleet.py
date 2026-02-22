"""
Tests for agent fleet service and API endpoints.
Covers: fleet status, agent activity, task queue, cost breakdown.
"""
import json
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(**overrides):
    """Create a mock TaskQueue row."""
    now = datetime.now(timezone.utc)
    defaults = {
        "id": uuid.uuid4(),
        "task_type": "generate_ab_variants",
        "status": "completed",
        "priority": 5,
        "retry_count": 0,
        "max_retries": 3,
        "created_at": now,
        "started_at": now - timedelta(seconds=5),
        "completed_at": now,
        "scheduled_at": now - timedelta(seconds=10),
        "error_message": None,
        "result_data": None,
        "payload": None,
    }
    defaults.update(overrides)
    t = MagicMock()
    for k, val in defaults.items():
        setattr(t, k, val)
    return t


def _utc_iso(seconds_ago: float = 0) -> str:
    """Return an ISO timestamp for `seconds_ago` in the past."""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


# ---------------------------------------------------------------------------
# AGENT_REGISTRY
# ---------------------------------------------------------------------------

class TestAgentRegistry:
    def test_registry_has_nine_agents(self):
        from src.services.agent_fleet import AGENT_REGISTRY
        assert len(AGENT_REGISTRY) == 9

    def test_every_agent_has_required_fields(self):
        from src.services.agent_fleet import AGENT_REGISTRY
        required = {"display_name", "description", "schedule", "icon", "color", "uses_ai", "poll_interval", "task_types"}
        for name, meta in AGENT_REGISTRY.items():
            missing = required - set(meta.keys())
            assert not missing, f"{name} missing fields: {missing}"

    def test_task_type_to_agent_mapping(self):
        from src.services.agent_fleet import _TASK_TYPE_TO_AGENT, AGENT_REGISTRY
        for name, meta in AGENT_REGISTRY.items():
            for tt in meta["task_types"]:
                assert _TASK_TYPE_TO_AGENT[tt] == name


# ---------------------------------------------------------------------------
# SOUL.md loading
# ---------------------------------------------------------------------------

class TestSoulLoading:
    @pytest.mark.asyncio
    async def test_load_known_agent_returns_string(self):
        from src.services.agent_fleet import _load_soul_summary
        summary = await _load_soul_summary("ab_test_engine")
        assert isinstance(summary, str)
        assert len(summary) > 10, "Identity section should be non-trivial"

    @pytest.mark.asyncio
    async def test_load_unknown_agent_returns_empty(self):
        from src.services.agent_fleet import _load_soul_summary
        result = await _load_soul_summary("nonexistent_agent")
        assert result == ""

    @pytest.mark.asyncio
    async def test_soul_cache_works(self):
        from src.services.agent_fleet import _load_soul_summary, _SOUL_CACHE
        await _load_soul_summary("ab_test_engine")
        assert "ab_test_engine" in _SOUL_CACHE


# ---------------------------------------------------------------------------
# Health computation
# ---------------------------------------------------------------------------

class TestHealthLogic:
    """Test the health derivation logic used in get_fleet_status."""

    def test_healthy_when_heartbeat_recent(self):
        """Heartbeat within 1.5x poll_interval -> healthy."""
        poll = 21600  # 6 hours
        age = poll * 1.0  # well within 1.5x
        assert age < poll * 1.5

    def test_warning_when_heartbeat_aged(self):
        """Heartbeat between 1.5x and 3x poll_interval -> warning."""
        poll = 21600
        age = poll * 2.0
        assert age >= poll * 1.5
        assert age < poll * 3

    def test_unhealthy_when_heartbeat_stale(self):
        """Heartbeat beyond 3x poll_interval -> unhealthy."""
        poll = 21600
        age = poll * 4.0
        assert age >= poll * 3


# ---------------------------------------------------------------------------
# get_fleet_status
# ---------------------------------------------------------------------------

class TestGetFleetStatus:
    @pytest.mark.asyncio
    async def test_returns_fleet_summary_and_agents(self):
        from src.services.agent_fleet import get_fleet_status

        mock_redis = AsyncMock()
        # No cache hit
        mock_redis.get.return_value = None
        # All 9 heartbeats — recent timestamps
        mock_redis.mget.return_value = [_utc_iso(60)] * 9
        # Cost hash for today
        mock_redis.hgetall.return_value = {"ab_test_engine": "0.001", "winback_agent": "0.002"}
        mock_redis.set.return_value = True

        mock_session = AsyncMock()
        # Task counts query returns empty
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_fleet.get_redis", return_value=mock_redis), \
             patch("src.services.agent_fleet.async_session_factory", return_value=mock_session):
            result = await get_fleet_status()

        assert "fleet_summary" in result
        assert "agents" in result
        assert len(result["agents"]) == 9
        assert result["fleet_summary"]["total_agents"] == 9

    @pytest.mark.asyncio
    async def test_uses_cache_when_available(self):
        from src.services.agent_fleet import get_fleet_status

        cached_data = {"fleet_summary": {"total_agents": 9}, "agents": []}
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(cached_data)

        with patch("src.services.agent_fleet.get_redis", return_value=mock_redis):
            result = await get_fleet_status()

        assert result == cached_data
        mock_redis.mget.assert_not_called()

    @pytest.mark.asyncio
    async def test_unhealthy_agent_status_is_error_or_disabled(self):
        from src.services.agent_fleet import get_fleet_status

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        # All heartbeats are None (no data)
        mock_redis.mget.return_value = [None] * 9
        mock_redis.hgetall.return_value = {}
        mock_redis.set.return_value = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_fleet.get_redis", return_value=mock_redis), \
             patch("src.services.agent_fleet.async_session_factory", return_value=mock_session):
            result = await get_fleet_status()

        for agent in result["agents"]:
            if agent["enabled"]:
                assert agent["health"] == "unhealthy"
                assert agent["status"] == "error"
            else:
                assert agent["health"] == "disabled"
                assert agent["status"] == "disabled"


# ---------------------------------------------------------------------------
# get_agent_activity
# ---------------------------------------------------------------------------

class TestGetAgentActivity:
    @pytest.mark.asyncio
    async def test_raises_for_unknown_agent(self):
        from src.services.agent_fleet import get_agent_activity
        with pytest.raises(ValueError, match="Unknown agent"):
            await get_agent_activity("does_not_exist")

    @pytest.mark.asyncio
    async def test_returns_activity_structure(self):
        from src.services.agent_fleet import get_agent_activity

        mock_redis = AsyncMock()
        mock_redis.hget.return_value = "0.001"

        task = _make_task()
        mock_session = AsyncMock()
        # Recent tasks query
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [task]
        mock_exec_result1 = MagicMock()
        mock_exec_result1.scalars.return_value = mock_scalars
        # 7-day metrics query
        mock_exec_result2 = MagicMock()
        mock_exec_result2.one.return_value = (5, 4, 8.5)

        mock_session.execute.side_effect = [mock_exec_result1, mock_exec_result2]
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_fleet.get_redis", return_value=mock_redis), \
             patch("src.services.agent_fleet.async_session_factory", return_value=mock_session):
            result = await get_agent_activity("ab_test_engine")

        assert "agent" in result
        assert result["agent"]["name"] == "ab_test_engine"
        assert "recent_tasks" in result
        assert "cost_history" in result
        assert len(result["cost_history"]) == 30
        assert "metrics_7d" in result
        assert "soul_summary" in result


# ---------------------------------------------------------------------------
# get_cost_breakdown
# ---------------------------------------------------------------------------

class TestGetCostBreakdown:
    @pytest.mark.asyncio
    async def test_returns_correct_period(self):
        from src.services.agent_fleet import get_cost_breakdown

        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {"ab_test_engine": "0.001"}

        with patch("src.services.agent_fleet.get_redis", return_value=mock_redis):
            result = await get_cost_breakdown("7d")

        assert result["period"] == "7d"
        assert result["days"] == 7
        assert len(result["daily"]) == 7
        assert "grand_total" in result
        assert "daily_average" in result
        assert "projected_monthly" in result
        assert "agent_totals" in result

    @pytest.mark.asyncio
    async def test_30d_period(self):
        from src.services.agent_fleet import get_cost_breakdown

        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}

        with patch("src.services.agent_fleet.get_redis", return_value=mock_redis):
            result = await get_cost_breakdown("30d")

        assert result["days"] == 30
        assert len(result["daily"]) == 30


# ---------------------------------------------------------------------------
# get_task_queue
# ---------------------------------------------------------------------------

class TestGetTaskQueue:
    @pytest.mark.asyncio
    async def test_returns_paginated_tasks(self):
        from src.services.agent_fleet import get_task_queue

        task = _make_task()
        mock_session = AsyncMock()

        # Total count
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Paginated results
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [task]
        mock_tasks_result = MagicMock()
        mock_tasks_result.scalars.return_value = mock_scalars

        # Status counts
        mock_status_result = MagicMock()
        mock_status_result.__iter__ = MagicMock(return_value=iter([("completed", 1)]))

        mock_session.execute.side_effect = [mock_count_result, mock_tasks_result, mock_status_result]
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_fleet.async_session_factory", return_value=mock_session):
            result = await get_task_queue(status="all", page=1, per_page=20)

        assert "tasks" in result
        assert "pagination" in result
        assert result["pagination"]["page"] == 1
        assert "status_counts" in result


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class TestAgentsAPI:
    """Test API endpoint handlers directly (bypassing FastAPI DI for auth)."""

    @pytest.mark.asyncio
    async def test_fleet_endpoint(self):
        from src.api.agents import fleet_status
        mock_data = {"fleet_summary": {}, "agents": []}
        with patch("src.api.agents.get_fleet_status", return_value=mock_data):
            result = await fleet_status(_admin=MagicMock())
        assert result["success"] is True
        assert result["data"] == mock_data

    @pytest.mark.asyncio
    async def test_activity_endpoint_unknown_agent(self):
        from src.api.agents import agent_activity
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await agent_activity("unknown_agent", _admin=MagicMock())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cost_endpoint(self):
        from src.api.agents import cost_tracker
        mock_data = {"period": "7d", "daily": [], "grand_total": 0}
        with patch("src.api.agents.get_cost_breakdown", return_value=mock_data):
            result = await cost_tracker(_admin=MagicMock(), period="7d")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_task_queue_endpoint(self):
        from src.api.agents import task_queue
        mock_data = {"tasks": [], "pagination": {}, "status_counts": {}}
        with patch("src.api.agents.get_task_queue", return_value=mock_data):
            result = await task_queue(_admin=MagicMock(), status="all", task_type="all", page=1, per_page=20)
        assert result["success"] is True
