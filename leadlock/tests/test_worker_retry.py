"""
Tests for src/workers/retry_worker.py — dead letter queue processing.
"""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_failed_lead(
    stage: str = "webhook",
    payload: dict | None = None,
    status: str = "pending",
    retry_count: int = 0,
):
    """Create a mock FailedLead object."""
    fl = MagicMock()
    fl.id = uuid.uuid4()
    fl.failure_stage = stage
    fl.original_payload = payload
    fl.status = status
    fl.retry_count = retry_count
    fl.error_message = None
    fl.next_retry_at = datetime.now(timezone.utc)
    return fl


def _make_lead(lead_id: uuid.UUID | None = None, client_id: uuid.UUID | None = None):
    """Create a mock Lead object."""
    lead = MagicMock()
    lead.id = lead_id or uuid.uuid4()
    lead.client_id = client_id or uuid.uuid4()
    return lead


def _make_client(client_id: uuid.UUID | None = None):
    """Create a mock Client object."""
    client = MagicMock()
    client.id = client_id or uuid.uuid4()
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
# _retry_lead — webhook / intake stage
# ---------------------------------------------------------------------------

class TestRetryLeadWebhook:
    """Tests for _retry_lead with webhook and intake stages."""

    async def test_webhook_stage_calls_handle_new_lead(self):
        """Webhook stage creates a LeadEnvelope and calls handle_new_lead."""
        payload = {
            "source": "google_lsa",
            "client_id": str(uuid.uuid4()),
            "lead": {"phone": "+15125551234", "first_name": "Test"},
            "consent_type": "pec",
            "consent_method": "text_in",
        }
        failed = _make_failed_lead(stage="webhook", payload=payload)
        db = MagicMock()
        db.get = AsyncMock()

        with (
            patch(
                "src.agents.conductor.handle_new_lead",
                new_callable=AsyncMock,
                return_value={"status": "intake_sent"},
            ) as mock_handle,
            patch(
                "src.schemas.lead_envelope.LeadEnvelope",
            ) as mock_envelope_cls,
        ):
            mock_envelope = MagicMock()
            mock_envelope_cls.return_value = mock_envelope

            from src.workers.retry_worker import _retry_lead

            await _retry_lead(db, failed)
            mock_handle.assert_awaited_once_with(db, mock_envelope)

    async def test_intake_stage_calls_handle_new_lead(self):
        """Intake stage follows same path as webhook."""
        payload = {
            "source": "angi",
            "client_id": str(uuid.uuid4()),
            "lead": {"phone": "+15125559999"},
        }
        failed = _make_failed_lead(stage="intake", payload=payload)
        db = MagicMock()
        db.get = AsyncMock()

        with (
            patch(
                "src.agents.conductor.handle_new_lead",
                new_callable=AsyncMock,
                return_value={"status": "duplicate"},
            ) as mock_handle,
            patch("src.schemas.lead_envelope.LeadEnvelope"),
        ):
            from src.workers.retry_worker import _retry_lead

            await _retry_lead(db, failed)
            mock_handle.assert_awaited_once()

    async def test_webhook_stage_error_status_raises(self):
        """Webhook retry with error status raises RuntimeError."""
        payload = {
            "source": "google_lsa",
            "client_id": str(uuid.uuid4()),
            "lead": {"phone": "+15125551234"},
        }
        failed = _make_failed_lead(stage="webhook", payload=payload)
        db = MagicMock()
        db.get = AsyncMock()

        with (
            patch(
                "src.agents.conductor.handle_new_lead",
                new_callable=AsyncMock,
                return_value={"status": "error_compliance"},
            ),
            patch("src.schemas.lead_envelope.LeadEnvelope"),
        ):
            from src.workers.retry_worker import _retry_lead

            with pytest.raises(RuntimeError, match="Retry failed"):
                await _retry_lead(db, failed)


# ---------------------------------------------------------------------------
# _retry_lead — qualify / book stage
# ---------------------------------------------------------------------------

class TestRetryLeadQualify:
    """Tests for _retry_lead with qualify and book stages."""

    async def test_qualify_stage_loads_lead_and_calls_inbound_reply(self):
        """Qualify stage loads lead from DB and calls handle_inbound_reply."""
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        payload = {"lead_id": str(lead_id), "last_message": "hello"}
        failed = _make_failed_lead(stage="qualify", payload=payload)

        lead = _make_lead(lead_id=lead_id, client_id=client_id)
        client = _make_client(client_id=client_id)

        db = MagicMock()
        db.get = AsyncMock(side_effect=lambda model, pk: {
            str(lead_id): lead,
            client_id: client,
        }.get(pk))

        with patch(
            "src.agents.conductor.handle_inbound_reply",
            new_callable=AsyncMock,
            return_value={"status": "qualifying"},
        ) as mock_reply:
            from src.workers.retry_worker import _retry_lead

            await _retry_lead(db, failed)
            mock_reply.assert_awaited_once_with(db, lead, client, "hello")

    async def test_book_stage_loads_lead_and_calls_inbound_reply(self):
        """Book stage follows same path as qualify."""
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        payload = {"lead_id": str(lead_id), "last_message": "Tuesday works"}
        failed = _make_failed_lead(stage="book", payload=payload)

        lead = _make_lead(lead_id=lead_id, client_id=client_id)
        client = _make_client(client_id=client_id)

        db = MagicMock()
        db.get = AsyncMock(side_effect=lambda model, pk: {
            str(lead_id): lead,
            client_id: client,
        }.get(pk))

        with patch(
            "src.agents.conductor.handle_inbound_reply",
            new_callable=AsyncMock,
            return_value={"status": "booking"},
        ) as mock_reply:
            from src.workers.retry_worker import _retry_lead

            await _retry_lead(db, failed)
            mock_reply.assert_awaited_once()

    async def test_qualify_missing_lead_id_raises(self):
        """Qualify stage with no lead_id in payload raises ValueError."""
        payload = {"last_message": "hello"}  # no lead_id
        failed = _make_failed_lead(stage="qualify", payload=payload)
        db = MagicMock()
        db.get = AsyncMock()

        from src.workers.retry_worker import _retry_lead

        with pytest.raises(ValueError, match="No lead_id"):
            await _retry_lead(db, failed)

    async def test_qualify_lead_not_found_raises(self):
        """Qualify stage with non-existent lead raises ValueError."""
        lead_id = uuid.uuid4()
        payload = {"lead_id": str(lead_id)}
        failed = _make_failed_lead(stage="qualify", payload=payload)

        db = MagicMock()
        db.get = AsyncMock(return_value=None)

        from src.workers.retry_worker import _retry_lead

        with pytest.raises(ValueError, match="not found"):
            await _retry_lead(db, failed)

    async def test_qualify_lock_timeout_raises(self):
        """Lock timeout from handle_inbound_reply raises RuntimeError."""
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        payload = {"lead_id": str(lead_id), "last_message": "hi"}
        failed = _make_failed_lead(stage="qualify", payload=payload)

        lead = _make_lead(lead_id=lead_id, client_id=client_id)
        client = _make_client(client_id=client_id)

        db = MagicMock()
        db.get = AsyncMock(side_effect=lambda model, pk: {
            str(lead_id): lead,
            client_id: client,
        }.get(pk))

        with patch(
            "src.agents.conductor.handle_inbound_reply",
            new_callable=AsyncMock,
            return_value={"status": "lock_timeout"},
        ):
            from src.workers.retry_worker import _retry_lead

            with pytest.raises(RuntimeError, match="Lead locked"):
                await _retry_lead(db, failed)


# ---------------------------------------------------------------------------
# _retry_lead — error cases
# ---------------------------------------------------------------------------

class TestRetryLeadErrors:
    """Tests for _retry_lead error handling."""

    async def test_no_payload_raises(self):
        """Missing original_payload raises ValueError."""
        failed = _make_failed_lead(stage="webhook", payload=None)
        db = MagicMock()

        from src.workers.retry_worker import _retry_lead

        with pytest.raises(ValueError, match="No original payload"):
            await _retry_lead(db, failed)

    async def test_unknown_stage_raises(self):
        """Unknown failure_stage raises ValueError."""
        failed = _make_failed_lead(
            stage="unknown_stage",
            payload={"some": "data"},
        )
        db = MagicMock()

        from src.workers.retry_worker import _retry_lead

        with pytest.raises(ValueError, match="Unknown failure stage"):
            await _retry_lead(db, failed)


# ---------------------------------------------------------------------------
# _process_pending_retries
# ---------------------------------------------------------------------------

class TestProcessPendingRetries:
    """Tests for _process_pending_retries."""

    async def test_finds_and_processes_pending_leads(self):
        """Finds pending leads and processes them successfully."""
        lead_id = uuid.uuid4()
        payload = {
            "source": "google_lsa",
            "client_id": str(uuid.uuid4()),
            "lead": {"phone": "+15125551234"},
        }
        failed = _make_failed_lead(stage="webhook", payload=payload)

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [failed]

        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        @asynccontextmanager
        async def session_with_results():
            db = MagicMock()
            db.execute = AsyncMock(return_value=result_mock)
            db.commit = AsyncMock()
            db.flush = AsyncMock()
            yield db

        with (
            patch(
                "src.database.async_session_factory",
                side_effect=session_with_results,
            ),
            patch(
                "src.workers.retry_worker._retry_lead",
                new_callable=AsyncMock,
            ) as mock_retry,
            patch(
                "src.utils.dead_letter.resolve_failed_lead",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch(
                "src.utils.dead_letter.mark_retry_attempted",
                new_callable=AsyncMock,
            ),
        ):
            from src.workers.retry_worker import _process_pending_retries

            processed = await _process_pending_retries()

            assert processed == 1
            mock_retry.assert_awaited_once()
            mock_resolve.assert_awaited_once()

    async def test_retry_failure_calls_mark_retry_attempted(self):
        """When _retry_lead raises, mark_retry_attempted is called."""
        failed = _make_failed_lead(stage="webhook", payload={"bad": "data"})

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [failed]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        @asynccontextmanager
        async def session_with_results():
            db = MagicMock()
            db.execute = AsyncMock(return_value=result_mock)
            db.commit = AsyncMock()
            db.flush = AsyncMock()
            yield db

        with (
            patch(
                "src.database.async_session_factory",
                side_effect=session_with_results,
            ),
            patch(
                "src.workers.retry_worker._retry_lead",
                new_callable=AsyncMock,
                side_effect=RuntimeError("retry boom"),
            ),
            patch(
                "src.utils.dead_letter.resolve_failed_lead",
                new_callable=AsyncMock,
            ) as mock_resolve,
            patch(
                "src.utils.dead_letter.mark_retry_attempted",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            from src.workers.retry_worker import _process_pending_retries

            processed = await _process_pending_retries()

            assert processed == 0
            mock_resolve.assert_not_awaited()
            mock_mark.assert_awaited_once()
