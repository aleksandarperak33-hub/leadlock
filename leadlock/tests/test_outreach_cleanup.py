"""
Tests for outreach cleanup worker — marks exhausted sequences as lost.
Covers _heartbeat, run_outreach_cleanup, and cleanup_cycle.
"""
import uuid
import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.outreach import Outreach
from src.models.sales_config import SalesEngineConfig
from src.models.campaign import Campaign
from src.workers.outreach_cleanup import (
    _heartbeat,
    run_outreach_cleanup,
    cleanup_cycle,
    POLL_INTERVAL_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(
    db: AsyncSession,
    *,
    is_active: bool = True,
    sequence_delay_hours: int = 48,
    max_sequence_steps: int = 3,
    cleanup_paused: bool = False,
) -> SalesEngineConfig:
    """Create and add a SalesEngineConfig to the session."""
    config = SalesEngineConfig(
        id=uuid.uuid4(),
        is_active=is_active,
        sequence_delay_hours=sequence_delay_hours,
        max_sequence_steps=max_sequence_steps,
        cleanup_paused=cleanup_paused,
    )
    db.add(config)
    return config


def _make_campaign(
    db: AsyncSession,
    *,
    status: str = "active",
    sequence_steps: list | None = None,
) -> Campaign:
    """Create and add a Campaign to the session."""
    campaign = Campaign(
        id=uuid.uuid4(),
        name=f"Campaign-{uuid.uuid4().hex[:6]}",
        status=status,
        sequence_steps=sequence_steps,
    )
    db.add(campaign)
    return campaign


def _make_outreach(
    db: AsyncSession,
    *,
    campaign_id: uuid.UUID | None = None,
    status: str = "cold",
    outreach_sequence_step: int = 3,
    last_email_sent_at: datetime | None = None,
    last_email_replied_at: datetime | None = None,
) -> Outreach:
    """Create and add an Outreach record to the session."""
    outreach = Outreach(
        id=uuid.uuid4(),
        prospect_name=f"Prospect-{uuid.uuid4().hex[:6]}",
        status=status,
        campaign_id=campaign_id,
        outreach_sequence_step=outreach_sequence_step,
        last_email_sent_at=last_email_sent_at,
        last_email_replied_at=last_email_replied_at,
    )
    db.add(outreach)
    return outreach


def _past_cutoff(hours: int = 49) -> datetime:
    """Return a datetime past the default 48-hour delay cutoff."""
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _recent() -> datetime:
    """Return a datetime within the default 48-hour delay cutoff."""
    return datetime.now(timezone.utc) - timedelta(hours=1)


@asynccontextmanager
async def _session_factory_from(db: AsyncSession):
    """Yield the test db session as if it were from async_session_factory."""
    yield db


# ---------------------------------------------------------------------------
# Test: POLL_INTERVAL_SECONDS constant
# ---------------------------------------------------------------------------


class TestConstants:
    def test_poll_interval_is_4_hours(self):
        assert POLL_INTERVAL_SECONDS == 4 * 60 * 60


# ---------------------------------------------------------------------------
# Test: _heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    async def test_heartbeat_sets_redis_key(self):
        """Heartbeat stores timestamp in Redis with 18000s expiry."""
        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=True)

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=redis_mock,
        ):
            await _heartbeat()

        redis_mock.set.assert_called_once()
        call_args = redis_mock.set.call_args
        assert call_args[0][0] == "leadlock:worker_health:outreach_cleanup"
        assert call_args[1]["ex"] == 18000

    async def test_heartbeat_swallows_redis_errors(self):
        """Heartbeat must not raise even if Redis is down."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis down"),
        ):
            await _heartbeat()  # Should not raise


# ---------------------------------------------------------------------------
# Test: cleanup_cycle
# ---------------------------------------------------------------------------


class TestCleanupCycle:
    """Tests for the cleanup_cycle function."""

    async def test_no_config_returns_early(self, db):
        """If no SalesEngineConfig exists, cleanup_cycle does nothing."""
        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        # No outreach records — just verify it didn't crash
        result = await db.execute(select(Outreach))
        assert result.scalars().all() == []

    async def test_inactive_config_returns_early(self, db):
        """If config.is_active is False, cleanup_cycle does nothing."""
        _make_config(db, is_active=False)
        o = _make_outreach(
            db,
            status="cold",
            outreach_sequence_step=5,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "cold"  # Unchanged

    async def test_unbound_prospect_marked_lost(self, db):
        """Unbound prospect past max steps + delay is marked lost."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        o = _make_outreach(
            db,
            campaign_id=None,
            status="cold",
            outreach_sequence_step=3,
            last_email_sent_at=_past_cutoff(50),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "lost"

    async def test_unbound_contacted_status_marked_lost(self, db):
        """Unbound prospect with status 'contacted' is also eligible."""
        _make_config(db, max_sequence_steps=3)
        o = _make_outreach(
            db,
            campaign_id=None,
            status="contacted",
            outreach_sequence_step=4,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "lost"

    async def test_unbound_prospect_with_reply_not_marked(self, db):
        """Prospect who replied is never marked lost."""
        _make_config(db, max_sequence_steps=3)
        o = _make_outreach(
            db,
            campaign_id=None,
            status="cold",
            outreach_sequence_step=5,
            last_email_sent_at=_past_cutoff(),
            last_email_replied_at=datetime.now(timezone.utc),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "cold"

    async def test_unbound_prospect_below_max_steps_not_marked(self, db):
        """Prospect below max steps is not marked lost."""
        _make_config(db, max_sequence_steps=3)
        o = _make_outreach(
            db,
            campaign_id=None,
            status="cold",
            outreach_sequence_step=2,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "cold"

    async def test_unbound_prospect_recent_email_not_marked(self, db):
        """Prospect whose last email is recent (within cutoff) is not marked."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        o = _make_outreach(
            db,
            campaign_id=None,
            status="cold",
            outreach_sequence_step=5,
            last_email_sent_at=_recent(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "cold"

    async def test_unbound_prospect_no_email_sent_not_marked(self, db):
        """Prospect with no email sent (last_email_sent_at is None) is not marked."""
        _make_config(db, max_sequence_steps=3)
        o = _make_outreach(
            db,
            campaign_id=None,
            status="cold",
            outreach_sequence_step=5,
            last_email_sent_at=None,
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "cold"

    async def test_unbound_prospect_wrong_status_not_marked(self, db):
        """Prospect with non-eligible status (e.g. 'won') is not marked."""
        _make_config(db, max_sequence_steps=3)
        o = _make_outreach(
            db,
            campaign_id=None,
            status="won",
            outreach_sequence_step=5,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "won"

    # --- Campaign-bound tests (Pass 1) ---

    async def test_campaign_bound_prospect_marked_lost(self, db):
        """Campaign-bound prospect past campaign step count is marked lost."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        campaign = _make_campaign(
            db,
            status="active",
            sequence_steps=[{"step": 1}, {"step": 2}],
        )
        await db.flush()

        o = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=2,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "lost"

    async def test_campaign_bound_contacted_marked_lost(self, db):
        """Campaign-bound prospect with 'contacted' status is also eligible."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        campaign = _make_campaign(
            db, status="active", sequence_steps=[{"step": 1}]
        )
        await db.flush()

        o = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="contacted",
            outreach_sequence_step=1,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "lost"

    async def test_campaign_with_empty_steps_skipped(self, db):
        """Campaign with no sequence_steps is skipped (max_steps=0)."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        campaign = _make_campaign(db, status="active", sequence_steps=[])
        await db.flush()

        o = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=5,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "cold"  # Not touched

    async def test_campaign_with_none_steps_skipped(self, db):
        """Campaign with sequence_steps=None is treated as empty."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        campaign = _make_campaign(db, status="active", sequence_steps=None)
        await db.flush()

        o = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=5,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "cold"

    async def test_campaign_bound_below_step_count_not_marked(self, db):
        """Prospect below campaign step count is not marked."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        campaign = _make_campaign(
            db,
            status="active",
            sequence_steps=[{"step": 1}, {"step": 2}, {"step": 3}],
        )
        await db.flush()

        o = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=2,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "cold"

    async def test_campaign_bound_with_reply_not_marked(self, db):
        """Campaign-bound prospect who replied is not marked lost."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        campaign = _make_campaign(
            db, status="active", sequence_steps=[{"step": 1}]
        )
        await db.flush()

        o = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=5,
            last_email_sent_at=_past_cutoff(),
            last_email_replied_at=datetime.now(timezone.utc),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        assert o.status == "cold"

    async def test_draft_campaign_not_queried(self, db):
        """Campaigns with status 'draft' are not queried."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        campaign = _make_campaign(
            db, status="draft", sequence_steps=[{"step": 1}]
        )
        await db.flush()

        o = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=5,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o)
        # Draft campaigns are not included, so this prospect is not cleaned up
        # by pass 1.  But it HAS a campaign_id, so pass 2 (unbound) won't
        # touch it either.
        assert o.status == "cold"

    async def test_paused_and_completed_campaigns_included(self, db):
        """Campaigns with 'paused' or 'completed' status are included."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)

        c_paused = _make_campaign(
            db, status="paused", sequence_steps=[{"step": 1}]
        )
        c_completed = _make_campaign(
            db, status="completed", sequence_steps=[{"step": 1}]
        )
        await db.flush()

        o1 = _make_outreach(
            db,
            campaign_id=c_paused.id,
            status="cold",
            outreach_sequence_step=1,
            last_email_sent_at=_past_cutoff(),
        )
        o2 = _make_outreach(
            db,
            campaign_id=c_completed.id,
            status="contacted",
            outreach_sequence_step=2,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o1)
        await db.refresh(o2)
        assert o1.status == "lost"
        assert o2.status == "lost"

    async def test_mixed_campaign_and_unbound(self, db):
        """Both campaign-bound and unbound prospects are cleaned up."""
        _make_config(db, max_sequence_steps=2, sequence_delay_hours=48)
        campaign = _make_campaign(
            db, status="active", sequence_steps=[{"step": 1}]
        )
        await db.flush()

        # Campaign-bound — should be marked lost (step >= 1)
        o_campaign = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=1,
            last_email_sent_at=_past_cutoff(),
        )
        # Unbound — should be marked lost (step >= 2)
        o_unbound = _make_outreach(
            db,
            campaign_id=None,
            status="cold",
            outreach_sequence_step=2,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o_campaign)
        await db.refresh(o_unbound)
        assert o_campaign.status == "lost"
        assert o_unbound.status == "lost"

    async def test_no_prospects_to_mark_no_error(self, db):
        """Active config but no eligible prospects is fine — 0 marked."""
        _make_config(db, max_sequence_steps=3)
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()
        # Just verify no exception

    async def test_campaign_with_multiple_prospects_partial_mark(self, db):
        """Only eligible prospects within a campaign are marked."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        campaign = _make_campaign(
            db, status="active", sequence_steps=[{"step": 1}, {"step": 2}]
        )
        await db.flush()

        # Eligible: step >= 2, old email, no reply
        o_eligible = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=2,
            last_email_sent_at=_past_cutoff(),
        )
        # Not eligible: step < 2
        o_low_step = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=1,
            last_email_sent_at=_past_cutoff(),
        )
        # Not eligible: has reply
        o_replied = _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=3,
            last_email_sent_at=_past_cutoff(),
            last_email_replied_at=datetime.now(timezone.utc),
        )
        await db.flush()

        with patch(
            "src.workers.outreach_cleanup.async_session_factory",
            return_value=_session_factory_from(db),
        ):
            await cleanup_cycle()

        await db.refresh(o_eligible)
        await db.refresh(o_low_step)
        await db.refresh(o_replied)
        assert o_eligible.status == "lost"
        assert o_low_step.status == "cold"
        assert o_replied.status == "cold"


# ---------------------------------------------------------------------------
# Test: run_outreach_cleanup (main loop)
# ---------------------------------------------------------------------------


class TestRunOutreachCleanup:
    """Tests for the main loop function run_outreach_cleanup."""

    async def test_loop_calls_cleanup_when_not_paused(self, db):
        """Normal run: no config → cleanup_cycle is called."""
        call_count = 0

        async def _fake_cleanup():
            nonlocal call_count
            call_count += 1

        async def _fake_sleep(seconds):
            raise _StopLoop()

        class _StopLoop(Exception):
            pass

        # No config in db means cleanup_paused check defaults to calling cleanup
        _make_config(db, cleanup_paused=False)
        await db.flush()

        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_session_factory_from(db),
            ),
            patch(
                "src.workers.outreach_cleanup.cleanup_cycle",
                side_effect=_fake_cleanup,
            ),
            patch(
                "src.workers.outreach_cleanup._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.outreach_cleanup.asyncio.sleep",
                side_effect=_fake_sleep,
            ),
        ):
            with pytest.raises(_StopLoop):
                await run_outreach_cleanup()

        assert call_count == 1

    async def test_loop_skips_cleanup_when_paused(self, db):
        """When cleanup_paused=True, cleanup_cycle is NOT called."""
        cleanup_called = False

        async def _fake_cleanup():
            nonlocal cleanup_called
            cleanup_called = True

        async def _fake_sleep(seconds):
            raise _StopLoop()

        class _StopLoop(Exception):
            pass

        _make_config(db, cleanup_paused=True)
        await db.flush()

        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_session_factory_from(db),
            ),
            patch(
                "src.workers.outreach_cleanup.cleanup_cycle",
                side_effect=_fake_cleanup,
            ),
            patch(
                "src.workers.outreach_cleanup._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.outreach_cleanup.asyncio.sleep",
                side_effect=_fake_sleep,
            ),
        ):
            with pytest.raises(_StopLoop):
                await run_outreach_cleanup()

        assert cleanup_called is False

    async def test_loop_handles_error_gracefully(self, db):
        """If the inner block raises, it logs error and continues."""

        async def _fake_sleep(seconds):
            raise _StopLoop()

        class _StopLoop(Exception):
            pass

        # Make async_session_factory raise to trigger the except branch
        async def _exploding_factory():
            raise RuntimeError("DB connection failed")

        @asynccontextmanager
        async def _exploding_cm():
            raise RuntimeError("DB connection failed")
            yield  # pragma: no cover  # noqa: E305

        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_exploding_cm(),
            ),
            patch(
                "src.workers.outreach_cleanup._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.outreach_cleanup.asyncio.sleep",
                side_effect=_fake_sleep,
            ),
        ):
            with pytest.raises(_StopLoop):
                await run_outreach_cleanup()
        # No crash — error was caught and logged

    async def test_loop_runs_without_config(self, db):
        """When no config exists, cleanup_cycle is still called (config=None branch)."""
        call_count = 0

        async def _fake_cleanup():
            nonlocal call_count
            call_count += 1

        async def _fake_sleep(seconds):
            raise _StopLoop()

        class _StopLoop(Exception):
            pass

        # Empty db — no config at all
        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_session_factory_from(db),
            ),
            patch(
                "src.workers.outreach_cleanup.cleanup_cycle",
                side_effect=_fake_cleanup,
            ),
            patch(
                "src.workers.outreach_cleanup._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.outreach_cleanup.asyncio.sleep",
                side_effect=_fake_sleep,
            ),
        ):
            with pytest.raises(_StopLoop):
                await run_outreach_cleanup()

        # config is None → cleanup_cycle is called (the `if config and ...` is False)
        assert call_count == 1

    async def test_loop_calls_heartbeat(self, db):
        """Heartbeat is called after each cycle."""

        async def _fake_sleep(seconds):
            raise _StopLoop()

        class _StopLoop(Exception):
            pass

        heartbeat_mock = AsyncMock()

        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_session_factory_from(db),
            ),
            patch(
                "src.workers.outreach_cleanup.cleanup_cycle",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.outreach_cleanup._heartbeat",
                heartbeat_mock,
            ),
            patch(
                "src.workers.outreach_cleanup.asyncio.sleep",
                side_effect=_fake_sleep,
            ),
        ):
            with pytest.raises(_StopLoop):
                await run_outreach_cleanup()

        heartbeat_mock.assert_called_once()

    async def test_loop_sleeps_correct_interval(self, db):
        """Loop sleeps for POLL_INTERVAL_SECONDS."""

        sleep_value = None

        async def _capture_sleep(seconds):
            nonlocal sleep_value
            sleep_value = seconds
            raise _StopLoop()

        class _StopLoop(Exception):
            pass

        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_session_factory_from(db),
            ),
            patch(
                "src.workers.outreach_cleanup.cleanup_cycle",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.outreach_cleanup._heartbeat",
                new_callable=AsyncMock,
            ),
            patch(
                "src.workers.outreach_cleanup.asyncio.sleep",
                side_effect=_capture_sleep,
            ),
        ):
            with pytest.raises(_StopLoop):
                await run_outreach_cleanup()

        assert sleep_value == POLL_INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# Test: logging output
# ---------------------------------------------------------------------------


class TestCleanupLogging:
    """Verify that key log messages are emitted."""

    async def test_logs_campaign_marked_count(self, db, caplog):
        """Logs how many prospects were marked in each campaign."""
        _make_config(db, max_sequence_steps=3, sequence_delay_hours=48)
        campaign = _make_campaign(
            db, status="active", sequence_steps=[{"step": 1}]
        )
        await db.flush()

        _make_outreach(
            db,
            campaign_id=campaign.id,
            status="cold",
            outreach_sequence_step=1,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_session_factory_from(db),
            ),
            caplog.at_level("INFO", logger="src.workers.outreach_cleanup"),
        ):
            await cleanup_cycle()

        assert any("marked" in r.message and "Campaign" in r.message for r in caplog.records)

    async def test_logs_unbound_marked_count(self, db, caplog):
        """Logs how many unbound prospects were marked."""
        _make_config(db, max_sequence_steps=2, sequence_delay_hours=48)
        _make_outreach(
            db,
            campaign_id=None,
            status="cold",
            outreach_sequence_step=3,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_session_factory_from(db),
            ),
            caplog.at_level("INFO", logger="src.workers.outreach_cleanup"),
        ):
            await cleanup_cycle()

        assert any("Unbound" in r.message for r in caplog.records)

    async def test_logs_total_marked(self, db, caplog):
        """Logs total count when > 0."""
        _make_config(db, max_sequence_steps=2, sequence_delay_hours=48)
        _make_outreach(
            db,
            campaign_id=None,
            status="cold",
            outreach_sequence_step=3,
            last_email_sent_at=_past_cutoff(),
        )
        await db.flush()

        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_session_factory_from(db),
            ),
            caplog.at_level("INFO", logger="src.workers.outreach_cleanup"),
        ):
            await cleanup_cycle()

        assert any("Total marked" in r.message for r in caplog.records)

    async def test_no_log_when_zero_marked(self, db, caplog):
        """No 'Total marked' log when nothing was marked."""
        _make_config(db, max_sequence_steps=3)
        await db.flush()

        with (
            patch(
                "src.workers.outreach_cleanup.async_session_factory",
                return_value=_session_factory_from(db),
            ),
            caplog.at_level("INFO", logger="src.workers.outreach_cleanup"),
        ):
            await cleanup_cycle()

        assert not any("Total marked" in r.message for r in caplog.records)
