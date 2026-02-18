"""
Tests for src/workers/stuck_lead_sweeper.py — stuck lead detection and remediation.
"""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lead(
    state: str = "intake_sent",
    updated_at: datetime | None = None,
    lead_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
):
    """Create a mock Lead object in a given state."""
    lead = MagicMock()
    lead.id = lead_id or uuid.uuid4()
    lead.client_id = client_id or uuid.uuid4()
    lead.state = state
    lead.current_agent = None
    lead.updated_at = updated_at or (datetime.now(timezone.utc) - timedelta(hours=3))
    return lead


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
# _sweep_stuck_leads — finding leads
# ---------------------------------------------------------------------------

class TestSweepStuckLeads:
    """Tests for _sweep_stuck_leads discovering stuck leads."""

    async def test_finds_stuck_leads_in_non_terminal_states(self):
        """Sweep finds leads stuck in intake_sent, qualifying, booking states."""
        now = datetime.now(timezone.utc)

        stuck_intake = _make_lead(
            state="intake_sent",
            updated_at=now - timedelta(minutes=45),
        )
        stuck_qualifying = _make_lead(
            state="qualifying",
            updated_at=now - timedelta(hours=2),
        )

        # Track which states were queried
        call_count = 0
        state_results = {
            "intake_sent": [stuck_intake],
            "qualifying": [stuck_qualifying],
            "qualified": [],
            "booking": [],
        }
        state_order = list(state_results.keys())

        async def mock_execute(query):
            nonlocal call_count
            state_key = state_order[call_count] if call_count < len(state_order) else None
            call_count += 1
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = state_results.get(state_key, [])
            result = MagicMock()
            result.scalars.return_value = scalars_mock
            return result

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.add = MagicMock()
            yield db

        with (
            patch("src.database.async_session_factory", side_effect=session_factory),
            patch(
                "src.workers.stuck_lead_sweeper._handle_stuck_lead",
                new_callable=AsyncMock,
            ) as mock_handle,
        ):
            from src.workers.stuck_lead_sweeper import _sweep_stuck_leads

            found = await _sweep_stuck_leads()

            assert found == 2
            assert mock_handle.await_count == 2


# ---------------------------------------------------------------------------
# _handle_stuck_lead — state transitions
# ---------------------------------------------------------------------------

class TestHandleStuckLead:
    """Tests for _handle_stuck_lead state-specific actions."""

    async def test_intake_sent_over_30min_transitions_to_qualifying(self):
        """intake_sent lead stuck >30min is advanced to qualifying."""
        now = datetime.now(timezone.utc)
        lead = _make_lead(
            state="intake_sent",
            updated_at=now - timedelta(minutes=45),
        )
        db = MagicMock()
        db.add = MagicMock()

        with patch("src.models.event_log.EventLog") as mock_event_cls:
            mock_event_cls.return_value = MagicMock()

            from src.workers.stuck_lead_sweeper import _handle_stuck_lead

            await _handle_stuck_lead(db, lead, "intake_sent", now)

            assert lead.state == "qualifying"
            assert lead.current_agent == "qualify"
            db.add.assert_called_once()

    async def test_qualifying_over_1hr_transitions_to_cold(self):
        """qualifying lead stuck >1hr is marked cold."""
        now = datetime.now(timezone.utc)
        lead = _make_lead(
            state="qualifying",
            updated_at=now - timedelta(hours=2),
        )
        db = MagicMock()
        db.add = MagicMock()

        with patch("src.models.event_log.EventLog") as mock_event_cls:
            mock_event_cls.return_value = MagicMock()

            from src.workers.stuck_lead_sweeper import _handle_stuck_lead

            await _handle_stuck_lead(db, lead, "qualifying", now)

            assert lead.state == "cold"
            assert lead.current_agent == "followup"
            db.add.assert_called_once()

    async def test_qualified_over_1hr_transitions_to_cold(self):
        """qualified lead stuck >1hr is also marked cold."""
        now = datetime.now(timezone.utc)
        lead = _make_lead(
            state="qualified",
            updated_at=now - timedelta(hours=2),
        )
        db = MagicMock()
        db.add = MagicMock()

        with patch("src.models.event_log.EventLog") as mock_event_cls:
            mock_event_cls.return_value = MagicMock()

            from src.workers.stuck_lead_sweeper import _handle_stuck_lead

            await _handle_stuck_lead(db, lead, "qualified", now)

            assert lead.state == "cold"
            assert lead.current_agent == "followup"

    async def test_booking_over_2hr_alerts_admin_no_state_change(self):
        """booking lead stuck >2hr logs an admin alert but does NOT change state."""
        now = datetime.now(timezone.utc)
        lead = _make_lead(
            state="booking",
            updated_at=now - timedelta(hours=3),
        )
        original_state = lead.state
        db = MagicMock()
        db.add = MagicMock()

        with patch("src.models.event_log.EventLog") as mock_event_cls:
            mock_event_cls.return_value = MagicMock()

            from src.workers.stuck_lead_sweeper import _handle_stuck_lead

            await _handle_stuck_lead(db, lead, "booking", now)

            # State should NOT change
            assert lead.state == original_state
            # An alert event should be added
            db.add.assert_called_once()
            # Verify the EventLog was created with alert action
            event_kwargs = mock_event_cls.call_args
            assert event_kwargs.kwargs.get("action") == "stuck_lead_alert" or (
                len(event_kwargs.args) == 0
                and "ALERT" in str(event_kwargs.kwargs.get("message", ""))
            )
