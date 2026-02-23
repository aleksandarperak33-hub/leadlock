"""
Tests for merged workers:
- system_health (health_monitor + deliverability_monitor)
- lead_state_manager (stuck_lead_sweeper + lead_lifecycle)
- outreach_monitor (outreach_health + outreach_cleanup)
- sms_dispatch (followup_scheduler + booking_reminder)
"""
import pytest
from datetime import datetime, timezone, timedelta, date
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# system_health
# ---------------------------------------------------------------------------

class TestSystemHealth:
    """Tests for the merged system_health worker."""

    @pytest.mark.asyncio
    async def test_connectivity_checks_db(self):
        """Should execute SELECT 1 to verify DB connectivity."""
        from src.workers.system_health import _check_connectivity

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.database.async_session_factory", return_value=mock_session), \
             patch("src.utils.dedup.get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            await _check_connectivity()

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_connectivity_handles_db_failure(self):
        """DB failure should log error and send alert, not raise."""
        from src.workers.system_health import _check_connectivity

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.side_effect = Exception("Connection refused")

        with patch("src.database.async_session_factory", return_value=mock_session), \
             patch("src.utils.dedup.get_redis") as mock_get_redis, \
             patch("src.workers.system_health.send_alert") as mock_alert:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            await _check_connectivity()

        mock_alert.assert_called()

    @pytest.mark.asyncio
    async def test_deliverability_check_no_sends(self):
        """Should return early when no SMS sent in 24h."""
        from src.workers.system_health import _check_deliverability

        with patch("src.workers.system_health.get_deliverability_summary") as mock_summary:
            mock_summary.return_value = {"total_sent_24h": 0, "overall_delivery_rate": None}
            await _check_deliverability()

    @pytest.mark.asyncio
    async def test_heartbeat_key(self):
        """Heartbeat should use system_health key, not old keys."""
        from src.workers.system_health import _heartbeat

        mock_redis = AsyncMock()
        with patch("src.utils.dedup.get_redis", return_value=mock_redis):
            await _heartbeat()

        mock_redis.set.assert_called_once()
        key = mock_redis.set.call_args[0][0]
        assert key == "leadlock:worker_health:system_health"


# ---------------------------------------------------------------------------
# lead_state_manager
# ---------------------------------------------------------------------------

class TestLeadStateManager:
    """Tests for the merged lead_state_manager worker."""

    @pytest.mark.asyncio
    async def test_sweep_stuck_leads(self):
        """Should find and process stuck leads."""
        from src.workers.lead_state_manager import _sweep_stuck_leads

        mock_lead = MagicMock()
        mock_lead.id = "test-lead-id"
        mock_lead.client_id = "test-client-id"
        mock_lead.state = "intake_sent"
        mock_lead.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lead]

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.return_value = mock_result

        with patch("src.workers.lead_state_manager.async_session_factory", return_value=mock_session):
            found = await _sweep_stuck_leads()

        assert found >= 1

    @pytest.mark.asyncio
    async def test_archive_old_leads(self):
        """Should archive leads in terminal states older than 90 days."""
        from src.workers.lead_state_manager import _archive_old_leads

        mock_result = MagicMock()
        mock_result.rowcount = 5

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.return_value = mock_result

        with patch("src.workers.lead_state_manager.async_session_factory", return_value=mock_session):
            count = await _archive_old_leads()

        assert count == 5

    @pytest.mark.asyncio
    async def test_heartbeat_key(self):
        """Heartbeat should use lead_state_manager key."""
        from src.workers.lead_state_manager import _heartbeat

        mock_redis = AsyncMock()
        with patch("src.utils.dedup.get_redis", return_value=mock_redis):
            await _heartbeat()

        key = mock_redis.set.call_args[0][0]
        assert key == "leadlock:worker_health:lead_state_manager"


# ---------------------------------------------------------------------------
# outreach_monitor
# ---------------------------------------------------------------------------

class TestOutreachMonitor:
    """Tests for the merged outreach_monitor worker."""

    @pytest.mark.asyncio
    async def test_health_check_inactive_config(self):
        """Should skip checks when config is inactive."""
        from src.workers.outreach_monitor import _check_outreach_health

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.return_value = mock_result

        with patch("src.workers.outreach_monitor.async_session_factory", return_value=mock_session):
            await _check_outreach_health()

    @pytest.mark.asyncio
    async def test_cleanup_paused_skips(self):
        """Should skip cleanup when cleanup_paused is True."""
        from src.workers.outreach_monitor import _cleanup_exhausted_sequences

        mock_config = MagicMock()
        mock_config.is_active = True
        mock_config.cleanup_paused = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.return_value = mock_result

        with patch("src.workers.outreach_monitor.async_session_factory", return_value=mock_session):
            await _cleanup_exhausted_sequences()

        # Should not call commit if cleanup was skipped
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_heartbeat_key(self):
        """Heartbeat should use outreach_monitor key."""
        from src.workers.outreach_monitor import _heartbeat

        mock_redis = AsyncMock()
        with patch("src.utils.dedup.get_redis", return_value=mock_redis):
            await _heartbeat()

        key = mock_redis.set.call_args[0][0]
        assert key == "leadlock:worker_health:outreach_monitor"


# ---------------------------------------------------------------------------
# sms_dispatch
# ---------------------------------------------------------------------------

class TestSmsDispatch:
    """Tests for the merged sms_dispatch worker."""

    @pytest.mark.asyncio
    async def test_followup_no_tasks(self):
        """Should return immediately when no due followup tasks."""
        from src.workers.sms_dispatch import _process_due_followups

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.return_value = mock_result

        with patch("src.workers.sms_dispatch.async_session_factory", return_value=mock_session):
            await _process_due_followups()

    @pytest.mark.asyncio
    async def test_reminders_no_bookings(self):
        """Should return immediately when no bookings need reminders."""
        from src.workers.sms_dispatch import _send_due_reminders

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute.return_value = mock_result

        with patch("src.workers.sms_dispatch.async_session_factory", return_value=mock_session):
            await _send_due_reminders()

    @pytest.mark.asyncio
    async def test_heartbeat_key(self):
        """Heartbeat should use sms_dispatch key."""
        from src.workers.sms_dispatch import _heartbeat

        mock_redis = AsyncMock()
        with patch("src.utils.dedup.get_redis", return_value=mock_redis):
            await _heartbeat()

        key = mock_redis.set.call_args[0][0]
        assert key == "leadlock:worker_health:sms_dispatch"

    @pytest.mark.asyncio
    async def test_followup_skips_opted_out(self):
        """Follow-up should skip leads that have opted out."""
        from src.workers.sms_dispatch import _execute_followup_task

        mock_task = MagicMock()
        mock_task.lead_id = "lead-1"
        mock_task.client_id = "client-1"

        mock_lead = MagicMock()
        mock_lead.state = "opted_out"

        mock_client = MagicMock()

        mock_session = AsyncMock()
        mock_session.get.side_effect = lambda model, id: mock_lead if id == "lead-1" else mock_client

        await _execute_followup_task(mock_session, mock_task)

        assert mock_task.status == "skipped"
        assert "opted_out" in mock_task.skip_reason


# ---------------------------------------------------------------------------
# Reflection agent (daily)
# ---------------------------------------------------------------------------

class TestReflectionDaily:
    """Tests for the reflection agent's daily schedule."""

    @pytest.mark.asyncio
    async def test_should_run_today_no_key(self):
        """Should return True when no date key exists."""
        from src.workers.reflection_agent import _should_run_today

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch("src.utils.dedup.get_redis", return_value=mock_redis):
            result = await _should_run_today()

        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_run_today_key_exists(self):
        """Should return False when date key already exists."""
        from src.workers.reflection_agent import _should_run_today

        mock_redis = AsyncMock()
        mock_redis.get.return_value = "1"

        with patch("src.utils.dedup.get_redis", return_value=mock_redis):
            result = await _should_run_today()

        assert result is False
