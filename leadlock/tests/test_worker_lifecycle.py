"""
Tests for src/workers/lead_lifecycle.py - long-term lead state management.
"""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lead(
    state: str = "cold",
    archived: bool = False,
    cold_outreach_count: int = 0,
    updated_at: datetime | None = None,
    lead_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
):
    """Create a mock Lead object."""
    lead = MagicMock()
    lead.id = lead_id or uuid.uuid4()
    lead.client_id = client_id or uuid.uuid4()
    lead.state = state
    lead.archived = archived
    lead.cold_outreach_count = cold_outreach_count
    lead.current_agent = "followup"
    lead.updated_at = updated_at or datetime.now(timezone.utc)
    lead.next_followup_at = None
    return lead


def _make_client(client_id: uuid.UUID | None = None, tier: str = "pro"):
    """Create a mock Client object."""
    client = MagicMock()
    client.id = client_id or uuid.uuid4()
    client.tier = tier
    return client


@asynccontextmanager
async def mock_session():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.get = AsyncMock()
    db.add = MagicMock()
    yield db


# ---------------------------------------------------------------------------
# _archive_old_leads
# ---------------------------------------------------------------------------

class TestArchiveOldLeads:
    """Tests for _archive_old_leads."""

    async def test_archives_terminal_state_leads_over_90_days(self):
        """Leads in completed/dead/opted_out older than 90 days are archived."""
        update_result = MagicMock()
        update_result.rowcount = 5

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(return_value=update_result)
            db.commit = AsyncMock()
            yield db

        with patch(
            "src.workers.lead_lifecycle.async_session_factory",
            side_effect=session_factory,
        ):
            from src.workers.lead_lifecycle import _archive_old_leads

            count = await _archive_old_leads()

            assert count == 5

    async def test_no_leads_to_archive_returns_zero(self):
        """Returns 0 when no leads match archive criteria."""
        update_result = MagicMock()
        update_result.rowcount = 0

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(return_value=update_result)
            db.commit = AsyncMock()
            yield db

        with patch(
            "src.workers.lead_lifecycle.async_session_factory",
            side_effect=session_factory,
        ):
            from src.workers.lead_lifecycle import _archive_old_leads

            count = await _archive_old_leads()

            assert count == 0

    async def test_commit_only_when_leads_archived(self):
        """db.commit() is only called when rowcount > 0."""
        update_result = MagicMock()
        update_result.rowcount = 0
        commit_mock = AsyncMock()

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(return_value=update_result)
            db.commit = commit_mock
            yield db

        with patch(
            "src.workers.lead_lifecycle.async_session_factory",
            side_effect=session_factory,
        ):
            from src.workers.lead_lifecycle import _archive_old_leads

            await _archive_old_leads()
            commit_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# _mark_dead_leads
# ---------------------------------------------------------------------------

class TestMarkDeadLeads:
    """Tests for _mark_dead_leads."""

    async def test_cold_leads_with_exhausted_outreach_marked_dead(self):
        """Cold leads with >= 3 cold outreach messages are marked dead."""
        now = datetime.now(timezone.utc)
        lead = _make_lead(
            state="cold",
            cold_outreach_count=3,
            updated_at=now - timedelta(days=5),  # Not yet past 30 days
        )

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [lead]
        select_result = MagicMock()
        select_result.scalars.return_value = scalars_mock

        update_result = MagicMock()
        update_result.rowcount = 0

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            # First call is the select, subsequent are update for followup tasks
            if call_count == 1:
                return select_result
            return update_result

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.add = MagicMock()
            yield db

        with (
            patch(
                "src.workers.lead_lifecycle.async_session_factory",
                side_effect=session_factory,
            ),
            patch("src.models.event_log.EventLog") as mock_event_cls,
        ):
            mock_event_cls.return_value = MagicMock()

            from src.workers.lead_lifecycle import _mark_dead_leads

            count = await _mark_dead_leads()

            assert count == 1
            assert lead.state == "dead"
            assert lead.current_agent is None

    async def test_cold_leads_past_30_days_marked_dead(self):
        """Cold leads with no activity for >30 days are marked dead."""
        now = datetime.now(timezone.utc)
        lead = _make_lead(
            state="cold",
            cold_outreach_count=1,
            updated_at=now - timedelta(days=35),
        )

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [lead]
        select_result = MagicMock()
        select_result.scalars.return_value = scalars_mock

        update_result = MagicMock()
        update_result.rowcount = 0

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return select_result
            return update_result

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.add = MagicMock()
            yield db

        with (
            patch(
                "src.workers.lead_lifecycle.async_session_factory",
                side_effect=session_factory,
            ),
            patch("src.models.event_log.EventLog") as mock_event_cls,
        ):
            mock_event_cls.return_value = MagicMock()

            from src.workers.lead_lifecycle import _mark_dead_leads

            count = await _mark_dead_leads()

            assert count == 1
            assert lead.state == "dead"

    async def test_no_cold_leads_returns_zero(self):
        """Returns 0 when no cold leads meet dead criteria."""
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        select_result = MagicMock()
        select_result.scalars.return_value = scalars_mock

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(return_value=select_result)
            db.commit = AsyncMock()
            db.add = MagicMock()
            yield db

        with patch(
            "src.workers.lead_lifecycle.async_session_factory",
            side_effect=session_factory,
        ):
            from src.workers.lead_lifecycle import _mark_dead_leads

            count = await _mark_dead_leads()

            assert count == 0


# ---------------------------------------------------------------------------
# _schedule_cold_recycling
# ---------------------------------------------------------------------------

class TestScheduleColdRecycling:
    """Tests for _schedule_cold_recycling."""

    async def test_schedules_reengagement_for_eligible_cold_leads(self):
        """Cold leads in the recycle window get a followup task scheduled."""
        now = datetime.now(timezone.utc)
        client_id = uuid.uuid4()
        lead = _make_lead(
            state="cold",
            cold_outreach_count=1,
            updated_at=now - timedelta(days=7, minutes=30),
            client_id=client_id,
        )
        client = _make_client(client_id=client_id, tier="pro")

        # First query: select cold leads
        scalars_leads = MagicMock()
        scalars_leads.all.return_value = [lead]
        select_leads_result = MagicMock()
        select_leads_result.scalars.return_value = scalars_leads

        # Second query: check existing followup (none found)
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return select_leads_result
            return existing_result

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.get = AsyncMock(return_value=client)
            db.add = MagicMock()
            yield db

        with (
            patch(
                "src.workers.lead_lifecycle.async_session_factory",
                side_effect=session_factory,
            ),
            patch(
                "src.workers.lead_lifecycle.is_cold_followup_enabled",
                return_value=True,
            ),
            patch("src.models.followup.FollowupTask") as mock_task_cls,
            patch("src.models.event_log.EventLog") as mock_event_cls,
        ):
            mock_task_cls.return_value = MagicMock()
            mock_event_cls.return_value = MagicMock()

            from src.workers.lead_lifecycle import _schedule_cold_recycling

            count = await _schedule_cold_recycling()

            assert count == 1

    async def test_skips_leads_when_tier_not_enabled(self):
        """Cold leads are skipped if their client tier does not allow cold follow-ups."""
        now = datetime.now(timezone.utc)
        client_id = uuid.uuid4()
        lead = _make_lead(
            state="cold",
            cold_outreach_count=0,
            updated_at=now - timedelta(days=7, minutes=30),
            client_id=client_id,
        )
        client = _make_client(client_id=client_id, tier="starter")

        scalars_leads = MagicMock()
        scalars_leads.all.return_value = [lead]
        select_leads_result = MagicMock()
        select_leads_result.scalars.return_value = scalars_leads

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(return_value=select_leads_result)
            db.commit = AsyncMock()
            db.get = AsyncMock(return_value=client)
            db.add = MagicMock()
            yield db

        with (
            patch(
                "src.workers.lead_lifecycle.async_session_factory",
                side_effect=session_factory,
            ),
            patch(
                "src.workers.lead_lifecycle.is_cold_followup_enabled",
                return_value=False,
            ),
        ):
            from src.workers.lead_lifecycle import _schedule_cold_recycling

            count = await _schedule_cold_recycling()

            assert count == 0

    async def test_skips_leads_with_existing_pending_followup(self):
        """Cold leads with an existing pending cold_nurture task are skipped."""
        now = datetime.now(timezone.utc)
        client_id = uuid.uuid4()
        lead = _make_lead(
            state="cold",
            cold_outreach_count=1,
            updated_at=now - timedelta(days=7, minutes=30),
            client_id=client_id,
        )
        client = _make_client(client_id=client_id, tier="pro")

        # First: select cold leads
        scalars_leads = MagicMock()
        scalars_leads.all.return_value = [lead]
        select_leads_result = MagicMock()
        select_leads_result.scalars.return_value = scalars_leads

        # Second: existing followup found
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = MagicMock()  # has one

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return select_leads_result
            return existing_result

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.get = AsyncMock(return_value=client)
            db.add = MagicMock()
            yield db

        with (
            patch(
                "src.workers.lead_lifecycle.async_session_factory",
                side_effect=session_factory,
            ),
            patch(
                "src.workers.lead_lifecycle.is_cold_followup_enabled",
                return_value=True,
            ),
        ):
            from src.workers.lead_lifecycle import _schedule_cold_recycling

            count = await _schedule_cold_recycling()

            assert count == 0
