"""
Tests for src/services/task_dispatch.py — background task enqueuing.
"""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.services.task_dispatch import enqueue_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_async_session_factory():
    """Return a mock async_session_factory and the mock db session it yields."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    # The task gets an id after db.commit (simulating ORM behavior)
    fake_task_id = uuid.uuid4()

    def _side_effect_add(task):
        task.id = fake_task_id

    mock_db.add.side_effect = _side_effect_add

    class _FakeCtx:
        async def __aenter__(self):
            return mock_db
        async def __aexit__(self, *args):
            pass

    return _FakeCtx, mock_db, fake_task_id


# ---------------------------------------------------------------------------
# enqueue_task
# ---------------------------------------------------------------------------

class TestEnqueueTask:
    @pytest.mark.asyncio
    async def test_creates_task_with_correct_fields(self):
        """Task is created with correct type, payload, priority, max_retries."""
        factory_cls, mock_db, fake_id = _mock_async_session_factory()

        with patch("src.services.task_dispatch.async_session_factory", return_value=factory_cls()):
            task_id = await enqueue_task(
                task_type="enrich_email",
                payload={"outreach_id": "abc-123"},
                priority=10,
                max_retries=5,
            )

        # Verify db.add was called with a TaskQueue object
        mock_db.add.assert_called_once()
        task_obj = mock_db.add.call_args[0][0]

        assert task_obj.task_type == "enrich_email"
        assert task_obj.payload == {"outreach_id": "abc-123"}
        assert task_obj.priority == 10
        assert task_obj.max_retries == 5

        # The returned ID should be a string UUID
        assert task_id == str(fake_id)

        # db.commit was called
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_default_values(self):
        """Default priority=5, max_retries=3, payload={}."""
        factory_cls, mock_db, fake_id = _mock_async_session_factory()

        with patch("src.services.task_dispatch.async_session_factory", return_value=factory_cls()):
            await enqueue_task(task_type="classify_reply")

        task_obj = mock_db.add.call_args[0][0]
        assert task_obj.priority == 5
        assert task_obj.max_retries == 3
        assert task_obj.payload == {}

    @pytest.mark.asyncio
    async def test_returns_task_id_as_string(self):
        """The returned task_id is a string representation of the UUID."""
        factory_cls, mock_db, fake_id = _mock_async_session_factory()

        with patch("src.services.task_dispatch.async_session_factory", return_value=factory_cls()):
            task_id = await enqueue_task(task_type="send_sequence")

        assert isinstance(task_id, str)
        # Should be a valid UUID string
        uuid.UUID(task_id)

    @pytest.mark.asyncio
    async def test_delay_offsets_scheduled_at(self):
        """delay_seconds > 0 should push scheduled_at into the future."""
        factory_cls, mock_db, fake_id = _mock_async_session_factory()
        before = datetime.now(timezone.utc)

        with patch("src.services.task_dispatch.async_session_factory", return_value=factory_cls()):
            await enqueue_task(
                task_type="send_sequence",
                delay_seconds=300,
            )

        task_obj = mock_db.add.call_args[0][0]
        # scheduled_at should be at least 300 seconds from 'before'
        assert task_obj.scheduled_at >= before + timedelta(seconds=299)

    @pytest.mark.asyncio
    async def test_zero_delay_schedules_now(self):
        """delay_seconds=0 means scheduled_at is approximately now."""
        factory_cls, mock_db, fake_id = _mock_async_session_factory()
        before = datetime.now(timezone.utc)

        with patch("src.services.task_dispatch.async_session_factory", return_value=factory_cls()):
            await enqueue_task(task_type="record_signal", delay_seconds=0)

        task_obj = mock_db.add.call_args[0][0]
        after = datetime.now(timezone.utc)
        assert before <= task_obj.scheduled_at <= after + timedelta(seconds=1)

    @pytest.mark.asyncio
    async def test_payload_none_becomes_empty_dict(self):
        """When payload is None, it should default to {}."""
        factory_cls, mock_db, fake_id = _mock_async_session_factory()

        with patch("src.services.task_dispatch.async_session_factory", return_value=factory_cls()):
            await enqueue_task(task_type="scrape_location", payload=None)

        task_obj = mock_db.add.call_args[0][0]
        assert task_obj.payload == {}
