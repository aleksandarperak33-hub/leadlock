"""
Tests for agent activity service — EventLog-based activity feeds, counts, and system map.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event_log(**overrides):
    """Create a mock EventLog row."""
    now = datetime.now(timezone.utc)
    defaults = {
        "id": uuid.uuid4(),
        "action": "ab_test_completed",
        "agent_id": "ab_test_engine",
        "status": "success",
        "message": "A/B test completed for campaign XYZ",
        "cost_usd": 0.0012,
        "duration_ms": 450,
        "created_at": now,
        "data": None,
    }
    defaults.update(overrides)
    row = MagicMock()
    for k, val in defaults.items():
        setattr(row, k, val)
    return row


def _make_lead_row(state, count):
    """Create a tuple mimicking (state, count) from the lead query."""
    return (state, count)


# ---------------------------------------------------------------------------
# Agent name resolution
# ---------------------------------------------------------------------------

class TestAgentNameResolution:
    def test_resolve_by_agent_id(self):
        from src.services.agent_activity import _resolve_agent_name
        assert _resolve_agent_name("anything", "ab_test_engine") == "ab_test_engine"

    def test_resolve_by_action_prefix(self):
        from src.services.agent_activity import _resolve_agent_name
        assert _resolve_agent_name("ab_test_completed", None) == "ab_test_engine"
        assert _resolve_agent_name("followup_sent", None) == "sms_dispatch"
        assert _resolve_agent_name("crm_sync_started", None) == "crm_sync"
        assert _resolve_agent_name("outreach_email_sent", None) == "outreach_sequencer"
        assert _resolve_agent_name("winback_initiated", None) == "winback_agent"
        assert _resolve_agent_name("reflection_daily", None) == "reflection_agent"
        assert _resolve_agent_name("health_check_done", None) == "system_health"
        assert _resolve_agent_name("scrape_new_prospects", None) == "scraper"
        assert _resolve_agent_name("lead_state_advanced", None) == "lead_state_manager"
        assert _resolve_agent_name("retry_task_xyz", None) == "retry_worker"
        assert _resolve_agent_name("registration_poll_done", None) == "registration_poller"
        assert _resolve_agent_name("referral_sent", None) == "referral_agent"

    def test_resolve_unknown_action(self):
        from src.services.agent_activity import _resolve_agent_name
        assert _resolve_agent_name("unknown_action_xyz", None) is None

    def test_agent_id_takes_priority(self):
        from src.services.agent_activity import _resolve_agent_name
        # Even if action matches sms_dispatch, agent_id should win
        assert _resolve_agent_name("followup_sent", "crm_sync") == "crm_sync"


# ---------------------------------------------------------------------------
# Action filter builder
# ---------------------------------------------------------------------------

class TestBuildActionFilter:
    def test_builds_filter_for_known_agent(self):
        from src.services.agent_activity import _build_action_filter
        result = _build_action_filter("ab_test_engine")
        assert result is not None

    def test_builds_filter_for_unknown_agent(self):
        from src.services.agent_activity import _build_action_filter
        result = _build_action_filter("nonexistent_agent")
        # Should still return something (just agent_id match)
        assert result is not None


# ---------------------------------------------------------------------------
# get_activity_feed
# ---------------------------------------------------------------------------

class TestGetActivityFeed:
    @pytest.mark.asyncio
    async def test_returns_list_of_events(self):
        from src.services.agent_activity import get_activity_feed

        events = [
            _make_event_log(action="ab_test_completed", agent_id="ab_test_engine"),
            _make_event_log(action="followup_sent", agent_id="sms_dispatch"),
        ]

        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = events
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_exec_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_activity_feed(limit=10)

        assert len(result) == 2
        assert result[0]["agent_name"] == "ab_test_engine"
        assert result[0]["agent_display_name"] == "A/B Testing Engine"
        assert result[0]["agent_color"] == "purple"
        assert result[1]["agent_name"] == "sms_dispatch"

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_error(self):
        from src.services.agent_activity import get_activity_feed

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_activity_feed(limit=10)

        assert result == []

    @pytest.mark.asyncio
    async def test_filter_by_agent_name(self):
        from src.services.agent_activity import get_activity_feed

        events = [_make_event_log(action="ab_test_completed", agent_id="ab_test_engine")]

        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = events
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_exec_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_activity_feed(limit=10, agent_name="ab_test_engine")

        assert len(result) == 1
        # Verify the session.execute was called (the WHERE clause would filter)
        mock_session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# get_agent_event_counts
# ---------------------------------------------------------------------------

class TestGetAgentEventCounts:
    @pytest.mark.asyncio
    async def test_returns_counts_per_agent(self):
        from src.services.agent_activity import get_agent_event_counts

        mock_rows = [
            ("ab_test_completed", "ab_test_engine", 5),
            ("followup_sent", "sms_dispatch", 12),
            ("crm_sync_started", None, 8),
        ]

        mock_session = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.all.return_value = mock_rows
        mock_session.execute.return_value = mock_exec_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_agent_event_counts(days=1)

        assert result["ab_test_engine"] == 5
        assert result["sms_dispatch"] == 12
        assert result["crm_sync"] == 8

    @pytest.mark.asyncio
    async def test_returns_zero_counts_on_error(self):
        from src.services.agent_activity import get_agent_event_counts

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_agent_event_counts(days=1)

        # All agents should have 0 counts
        assert all(v == 0 for v in result.values())
        assert len(result) == 15


# ---------------------------------------------------------------------------
# get_system_map_data
# ---------------------------------------------------------------------------

class TestGetSystemMapData:
    @pytest.mark.asyncio
    async def test_returns_sales_pipeline_structure(self):
        from src.services.agent_activity import get_system_map_data

        prospect_rows = [
            ("cold", 100),
            ("contacted", 45),
            ("demo_scheduled", 8),
            ("demo_completed", 5),
            ("proposal_sent", 3),
            ("won", 12),
            ("lost", 20),
        ]

        campaign_rows = [
            ("draft", 2),
            ("active", 3),
            ("paused", 1),
            ("completed", 5),
        ]

        mock_session = AsyncMock()

        # Prospect counts query
        mock_prospect_result = MagicMock()
        mock_prospect_result.all.return_value = prospect_rows

        # Campaign counts query
        mock_campaign_result = MagicMock()
        mock_campaign_result.all.return_value = campaign_rows

        # Email aggregation query
        mock_email_agg = MagicMock()
        mock_email_agg.sent_count = 42
        mock_email_agg.opened_count = 18
        mock_email_agg.replied_count = 5
        mock_email_result = MagicMock()
        mock_email_result.one.return_value = mock_email_agg

        # A/B test count query
        mock_ab_result = MagicMock()
        mock_ab_result.scalar.return_value = 3

        mock_session.execute.side_effect = [
            mock_prospect_result,
            mock_campaign_result,
            mock_email_result,
            mock_ab_result,
        ]
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_system_map_data()

        assert result["prospect_counts"]["cold"] == 100
        assert result["prospect_counts"]["contacted"] == 45
        assert result["prospect_counts"]["won"] == 12
        assert result["campaign_counts"]["active"] == 3
        assert result["total_prospects"] == 193
        assert result["active_sequences"] == 45
        assert result["emails_sent_today"] == 42
        assert result["emails_opened_today"] == 18
        assert result["emails_replied_today"] == 5
        assert result["ab_tests_today"] == 3

    @pytest.mark.asyncio
    async def test_returns_defaults_on_error(self):
        from src.services.agent_activity import get_system_map_data

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_system_map_data()

        assert result["prospect_counts"] == {}
        assert result["emails_sent_today"] == 0
        assert result["total_prospects"] == 0


# ---------------------------------------------------------------------------
# get_agent_events
# ---------------------------------------------------------------------------

class TestGetAgentEvents:
    @pytest.mark.asyncio
    async def test_returns_recent_events(self):
        from src.services.agent_activity import get_agent_events

        events = [
            _make_event_log(action="ab_test_completed", status="success", duration_ms=300),
            _make_event_log(action="experiment_started", status="success", duration_ms=50),
        ]

        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = events
        mock_exec_result = MagicMock()
        mock_exec_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_exec_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_agent_events("ab_test_engine", limit=10)

        assert len(result) == 2
        assert result[0]["action"] == "ab_test_completed"
        assert result[0]["duration_ms"] == 300

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        from src.services.agent_activity import get_agent_events

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_agent_events("ab_test_engine", limit=10)

        assert result == []


# ---------------------------------------------------------------------------
# get_agent_event_metrics
# ---------------------------------------------------------------------------

class TestGetAgentEventMetrics:
    @pytest.mark.asyncio
    async def test_returns_7d_metrics(self):
        from src.services.agent_activity import get_agent_event_metrics

        mock_row = MagicMock()
        mock_row.total = 50
        mock_row.success_count = 48
        mock_row.avg_ms = 350.5
        mock_row.total_cost = 0.125

        mock_session = AsyncMock()
        mock_exec_result = MagicMock()
        mock_exec_result.one.return_value = mock_row
        mock_session.execute.return_value = mock_exec_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_agent_event_metrics("ab_test_engine")

        assert result["total_tasks"] == 50
        assert result["success_rate"] == 0.96
        assert result["avg_duration_s"] == 0.35
        assert result["total_cost"] == 0.125

    @pytest.mark.asyncio
    async def test_returns_zero_metrics_on_error(self):
        from src.services.agent_activity import get_agent_event_metrics

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("DB error"))
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.agent_activity.async_session_factory", return_value=mock_session):
            result = await get_agent_event_metrics("ab_test_engine")

        assert result["total_tasks"] == 0
        assert result["success_rate"] == 0.0


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class TestActivityAPIEndpoints:
    @pytest.mark.asyncio
    async def test_activity_feed_endpoint(self):
        from src.api.agents import activity_feed
        mock_events = [{"id": "1", "action": "test", "agent_name": "ab_test_engine"}]

        with patch("src.api.agents.get_activity_feed", return_value=mock_events):
            result = await activity_feed(_admin=MagicMock(), limit=50, agent=None)

        assert result["success"] is True
        assert result["data"]["events"] == mock_events

    @pytest.mark.asyncio
    async def test_activity_feed_with_agent_filter(self):
        from src.api.agents import activity_feed
        mock_events = [{"id": "1", "action": "test"}]

        with patch("src.api.agents.get_activity_feed", return_value=mock_events) as mock_fn:
            result = await activity_feed(_admin=MagicMock(), limit=20, agent="ab_test_engine")

        mock_fn.assert_called_once_with(limit=20, agent_name="ab_test_engine")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_activity_feed_ignores_unknown_agent(self):
        from src.api.agents import activity_feed

        with patch("src.api.agents.get_activity_feed", return_value=[]) as mock_fn:
            await activity_feed(_admin=MagicMock(), limit=50, agent="nonexistent")

        # Should pass None for unknown agent
        mock_fn.assert_called_once_with(limit=50, agent_name=None)

    @pytest.mark.asyncio
    async def test_system_map_endpoint(self):
        from src.api.agents import system_map
        mock_data = {"lead_counts": {"new": 5}, "sms_sent_today": 10}

        with patch("src.api.agents.get_system_map_data", return_value=mock_data):
            result = await system_map(_admin=MagicMock())

        assert result["success"] is True
        assert result["data"]["lead_counts"]["new"] == 5


# ---------------------------------------------------------------------------
# AGENT_ACTION_PREFIXES coverage
# ---------------------------------------------------------------------------

class TestAgentActionPrefixes:
    def test_all_registry_agents_have_prefix_mappings(self):
        from src.services.agent_activity import AGENT_ACTION_PREFIXES
        from src.services.agent_fleet import AGENT_REGISTRY

        for agent_name in AGENT_REGISTRY:
            assert agent_name in AGENT_ACTION_PREFIXES, (
                f"Agent '{agent_name}' missing from AGENT_ACTION_PREFIXES"
            )

    def test_no_empty_prefix_lists(self):
        from src.services.agent_activity import AGENT_ACTION_PREFIXES

        for agent_name, prefixes in AGENT_ACTION_PREFIXES.items():
            assert len(prefixes) > 0, f"Agent '{agent_name}' has empty prefix list"
