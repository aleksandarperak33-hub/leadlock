"""
Tests for src/workers/task_processor.py - task processing, dispatch, and handlers.
Covers: _heartbeat, run_task_processor, process_cycle, _execute_task,
_dispatch_task, and all five handler functions.
"""
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.models.task_queue import TaskQueue
from src.workers.task_processor import (
    _heartbeat,
    run_task_processor,
    process_cycle,
    _execute_task,
    _dispatch_task,
    _handle_enrich_email,
    _handle_record_signal,
    _handle_classify_reply,
    _handle_send_sms_followup,
    _handle_send_sequence_email,
    POLL_INTERVAL_SECONDS,
    MAX_TASKS_PER_CYCLE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(**overrides):
    """Create a MagicMock that behaves like a TaskQueue row.

    Using MagicMock because SQLAlchemy ORM instrumented attributes
    require a proper session-bound instance; plain __new__ fails.
    MagicMock allows free attribute get/set which is exactly what
    _execute_task does.
    """
    defaults = {
        "id": uuid.uuid4(),
        "task_type": "enrich_email",
        "payload": {},
        "status": "pending",
        "priority": 5,
        "retry_count": 0,
        "max_retries": 3,
        "scheduled_at": datetime.now(timezone.utc) - timedelta(seconds=5),
        "started_at": None,
        "completed_at": None,
        "error_message": None,
        "result_data": None,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    task = MagicMock()
    for k, v in defaults.items():
        setattr(task, k, v)
    return task


def _mock_async_session_factory(tasks=None):
    """Return a mock async_session_factory context manager, mock db, and optional tasks."""
    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    # db.execute(...) returns a result proxy whose scalars().all() returns the tasks
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = tasks or []
    mock_result.scalars.return_value = mock_scalars
    # Also support scalar_one_or_none for config lookups
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.get = AsyncMock(return_value=None)

    class _FakeCtx:
        async def __aenter__(self):
            return mock_db
        async def __aexit__(self, *args):
            pass

    return _FakeCtx, mock_db


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_poll_interval(self):
        assert POLL_INTERVAL_SECONDS == 30

    def test_max_tasks_per_cycle(self):
        assert MAX_TASKS_PER_CYCLE == 10


# ---------------------------------------------------------------------------
# _heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:
    async def test_heartbeat_sets_redis_key(self):
        """Heartbeat stores a timestamp in Redis."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            await _heartbeat()

        mock_redis.set.assert_awaited_once()
        args = mock_redis.set.call_args
        assert args[0][0] == "leadlock:worker_health:task_processor"
        # TTL should be 120 seconds
        assert args[1].get("ex") == 120

    async def test_heartbeat_swallows_exceptions(self):
        """Heartbeat silently swallows any exceptions (pass in except block)."""
        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("redis down")):
            # Should not raise
            await _heartbeat()


# ---------------------------------------------------------------------------
# run_task_processor
# ---------------------------------------------------------------------------

class TestRunTaskProcessor:
    async def test_calls_process_cycle_and_heartbeat(self):
        """Main loop calls process_cycle, _heartbeat, and sleeps."""
        call_count = 0

        async def _mock_process_cycle():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt("stop loop")

        with patch("src.workers.task_processor.process_cycle", side_effect=_mock_process_cycle), \
             patch("src.workers.task_processor._heartbeat", new_callable=AsyncMock) as mock_hb, \
             patch("src.workers.task_processor.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(KeyboardInterrupt):
                await run_task_processor()

        assert call_count == 2
        # Heartbeat was called at least once before the interruption
        assert mock_hb.await_count >= 1
        mock_sleep.assert_awaited_with(POLL_INTERVAL_SECONDS)

    async def test_catches_process_cycle_exception(self):
        """Exceptions from process_cycle are caught, loop continues."""
        call_count = 0

        async def _mock_process_cycle():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("test error")
            # Second call stops the loop
            raise KeyboardInterrupt("stop")

        with patch("src.workers.task_processor.process_cycle", side_effect=_mock_process_cycle), \
             patch("src.workers.task_processor._heartbeat", new_callable=AsyncMock), \
             patch("src.workers.task_processor.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(KeyboardInterrupt):
                await run_task_processor()

        # Should have been called twice: first errored (caught), second raised KeyboardInterrupt
        assert call_count == 2


# ---------------------------------------------------------------------------
# process_cycle
# ---------------------------------------------------------------------------

class TestProcessCycle:
    async def test_no_tasks_returns_early(self):
        """When no tasks are pending, return immediately without commit."""
        factory_cls, mock_db = _mock_async_session_factory(tasks=[])

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            await process_cycle()

        mock_db.commit.assert_not_awaited()

    async def test_executes_pending_tasks_and_commits(self):
        """Processes each pending task and commits."""
        task1 = _make_task(task_type="enrich_email")
        task2 = _make_task(task_type="classify_reply")
        factory_cls, mock_db = _mock_async_session_factory(tasks=[task1, task2])

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.workers.task_processor._execute_task", new_callable=AsyncMock) as mock_exec:
            await process_cycle()

        assert mock_exec.await_count == 2
        mock_db.commit.assert_awaited_once()

    async def test_execute_task_called_with_db_and_task(self):
        """_execute_task is called with the db session and each task."""
        task = _make_task(task_type="record_signal")
        factory_cls, mock_db = _mock_async_session_factory(tasks=[task])

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.workers.task_processor._execute_task", new_callable=AsyncMock) as mock_exec:
            await process_cycle()

        mock_exec.assert_awaited_once_with(mock_db, task)


# ---------------------------------------------------------------------------
# _execute_task
# ---------------------------------------------------------------------------

class TestExecuteTask:
    async def test_success_path(self):
        """On success, task status becomes completed with result_data."""
        task = _make_task(task_type="enrich_email", payload={"website": "example.com"})
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        dispatch_result = {"email": "found@example.com"}
        with patch("src.workers.task_processor._dispatch_task", new_callable=AsyncMock, return_value=dispatch_result):
            await _execute_task(mock_db, task)

        assert task.status == "completed"
        assert task.result_data == dispatch_result
        assert task.completed_at is not None
        assert task.started_at is not None
        mock_db.flush.assert_awaited_once()

    async def test_failure_with_retries_remaining(self):
        """On failure with retries remaining, task goes back to pending with backoff."""
        task = _make_task(
            task_type="enrich_email",
            retry_count=0,
            max_retries=3,
        )
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        with patch("src.workers.task_processor._dispatch_task", new_callable=AsyncMock, side_effect=Exception("timeout")):
            await _execute_task(mock_db, task)

        assert task.status == "pending"
        assert task.retry_count == 1
        assert task.error_message == "timeout"
        # Backoff for first retry: 30 * (4^0) = 30 seconds
        assert task.scheduled_at > datetime.now(timezone.utc)
        assert task.completed_at is None

    async def test_failure_at_max_retries(self):
        """On failure at max retries, task status becomes failed."""
        task = _make_task(
            task_type="enrich_email",
            retry_count=2,
            max_retries=3,
        )
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        with patch("src.workers.task_processor._dispatch_task", new_callable=AsyncMock, side_effect=Exception("permanent error")):
            await _execute_task(mock_db, task)

        assert task.status == "failed"
        assert task.retry_count == 3
        assert task.error_message == "permanent error"
        assert task.completed_at is not None

    async def test_exponential_backoff_values(self):
        """Backoff increases exponentially: 30s, 120s, 480s."""
        expected_backoffs = [30, 120, 480]

        for retry_idx, expected_backoff in enumerate(expected_backoffs):
            task = _make_task(
                task_type="enrich_email",
                retry_count=retry_idx,
                max_retries=5,  # enough retries to test all
            )
            mock_db = AsyncMock()
            mock_db.flush = AsyncMock()
            before = datetime.now(timezone.utc)

            with patch("src.workers.task_processor._dispatch_task", new_callable=AsyncMock, side_effect=Exception("err")):
                await _execute_task(mock_db, task)

            # scheduled_at should be at least expected_backoff seconds from now
            min_scheduled = before + timedelta(seconds=expected_backoff - 1)
            assert task.scheduled_at >= min_scheduled, (
                f"retry_count={retry_idx + 1}: expected backoff ~{expected_backoff}s"
            )

    async def test_sets_processing_status_before_dispatch(self):
        """Task is set to 'processing' and flushed before dispatch."""
        task = _make_task(task_type="enrich_email")
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        statuses_at_flush = []

        async def _capture_flush():
            statuses_at_flush.append(task.status)

        mock_db.flush.side_effect = _capture_flush

        with patch("src.workers.task_processor._dispatch_task", new_callable=AsyncMock, return_value={}):
            await _execute_task(mock_db, task)

        assert statuses_at_flush == ["processing"]


# ---------------------------------------------------------------------------
# _dispatch_task
# ---------------------------------------------------------------------------

class TestDispatchTask:
    async def test_unknown_task_type_returns_skipped(self):
        """Unknown task type returns a skip result."""
        result = await _dispatch_task("unknown_type", {})
        assert result["status"] == "skipped"
        assert "unknown task type" in result["reason"]

    async def test_routes_enrich_email(self):
        """enrich_email routes to _handle_enrich_email."""
        with patch("src.workers.task_processor._handle_enrich_email", new_callable=AsyncMock, return_value={"ok": True}) as mock_h:
            result = await _dispatch_task("enrich_email", {"website": "test.com"})

        mock_h.assert_awaited_once_with({"website": "test.com"})
        assert result == {"ok": True}

    async def test_routes_record_signal(self):
        """record_signal routes to _handle_record_signal."""
        with patch("src.workers.task_processor._handle_record_signal", new_callable=AsyncMock, return_value={"status": "recorded"}) as mock_h:
            result = await _dispatch_task("record_signal", {"signal_type": "test"})

        mock_h.assert_awaited_once_with({"signal_type": "test"})
        assert result == {"status": "recorded"}

    async def test_routes_classify_reply(self):
        """classify_reply routes to _handle_classify_reply."""
        with patch("src.workers.task_processor._handle_classify_reply", new_callable=AsyncMock, return_value={"intent": "positive"}) as mock_h:
            result = await _dispatch_task("classify_reply", {"text": "hi"})

        mock_h.assert_awaited_once_with({"text": "hi"})
        assert result == {"intent": "positive"}

    async def test_routes_send_sms_followup(self):
        """send_sms_followup routes to _handle_send_sms_followup."""
        with patch("src.workers.task_processor._handle_send_sms_followup", new_callable=AsyncMock, return_value={"status": "sent"}) as mock_h:
            result = await _dispatch_task("send_sms_followup", {"outreach_id": "abc"})

        mock_h.assert_awaited_once_with({"outreach_id": "abc"})
        assert result == {"status": "sent"}

    async def test_routes_send_sequence_email(self):
        """send_sequence_email routes to _handle_send_sequence_email."""
        with patch("src.workers.task_processor._handle_send_sequence_email", new_callable=AsyncMock, return_value={"status": "sent"}) as mock_h:
            result = await _dispatch_task("send_sequence_email", {"outreach_id": "xyz"})

        mock_h.assert_awaited_once_with({"outreach_id": "xyz"})
        assert result == {"status": "sent"}


# ---------------------------------------------------------------------------
# _handle_enrich_email
# ---------------------------------------------------------------------------

class TestHandleEnrichEmail:
    async def test_calls_enrich_prospect_email(self):
        """Delegates to enrich_prospect_email with website and company_name."""
        expected = {"email": "found@test.com", "source": "website_scrape"}
        with patch("src.services.enrichment.enrich_prospect_email", new_callable=AsyncMock, return_value=expected):
            result = await _handle_enrich_email({"website": "https://example.com", "company_name": "ACME"})

        assert result == expected

    async def test_defaults_empty_strings(self):
        """Missing keys default to empty strings."""
        with patch("src.services.enrichment.enrich_prospect_email", new_callable=AsyncMock, return_value={}) as mock_fn:
            await _handle_enrich_email({})

        mock_fn.assert_awaited_once_with("", "")


# ---------------------------------------------------------------------------
# _handle_record_signal
# ---------------------------------------------------------------------------

class TestHandleRecordSignal:
    async def test_calls_record_signal(self):
        """Delegates to record_signal with correct kwargs."""
        with patch("src.services.learning.record_signal", new_callable=AsyncMock) as mock_fn:
            result = await _handle_record_signal({
                "signal_type": "email_open",
                "dimensions": {"trade": "hvac"},
                "value": 1.0,
                "outreach_id": "abc-123",
            })

        mock_fn.assert_awaited_once_with(
            signal_type="email_open",
            dimensions={"trade": "hvac"},
            value=1.0,
            outreach_id="abc-123",
        )
        assert result == {"status": "recorded"}

    async def test_defaults_for_missing_keys(self):
        """Missing keys use sensible defaults."""
        with patch("src.services.learning.record_signal", new_callable=AsyncMock) as mock_fn:
            await _handle_record_signal({})

        mock_fn.assert_awaited_once_with(
            signal_type="",
            dimensions={},
            value=0.0,
            outreach_id=None,
        )


# ---------------------------------------------------------------------------
# _handle_classify_reply
# ---------------------------------------------------------------------------

class TestHandleClassifyReply:
    async def test_calls_classify_reply(self):
        """Delegates to classify_reply with the text."""
        expected = {"intent": "interested", "confidence": 0.9}
        with patch("src.agents.sales_outreach.classify_reply", new_callable=AsyncMock, return_value=expected):
            result = await _handle_classify_reply({"text": "Sounds good, tell me more"})

        assert result == expected

    async def test_defaults_empty_text(self):
        """Missing text key defaults to empty string."""
        with patch("src.agents.sales_outreach.classify_reply", new_callable=AsyncMock, return_value={}) as mock_fn:
            await _handle_classify_reply({})

        mock_fn.assert_awaited_once_with("")


# ---------------------------------------------------------------------------
# _handle_send_sms_followup
# ---------------------------------------------------------------------------

class TestHandleSendSmsFollowup:
    """Tests for the SMS followup handler which opens its own DB session."""

    def _make_outreach_mock(self, **overrides):
        """Create a mock Outreach row."""
        defaults = {
            "id": uuid.uuid4(),
            "prospect_phone": "+15125551234",
            "email_unsubscribed": False,
            "state_code": "TX",
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    async def test_no_outreach_id_returns_skipped(self):
        """Missing outreach_id in payload returns skip."""
        result = await _handle_send_sms_followup({})
        assert result == {"status": "skipped", "reason": "no outreach_id"}

    async def test_prospect_not_found(self):
        """Prospect not in DB returns skip."""
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=None)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sms_followup({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "prospect not found"}

    async def test_no_phone_returns_skipped(self):
        """Prospect without phone returns skip."""
        prospect = self._make_outreach_mock(prospect_phone=None)
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sms_followup({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "no phone"}

    async def test_unsubscribed_returns_skipped(self):
        """Unsubscribed prospect returns skip."""
        prospect = self._make_outreach_mock(email_unsubscribed=True)
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sms_followup({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "unsubscribed"}

    async def test_quiet_hours_requeues(self):
        """During quiet hours, task is re-queued with delay."""
        prospect = self._make_outreach_mock()
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=False), \
             patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock) as mock_enqueue:
            oid = str(uuid.uuid4())
            result = await _handle_send_sms_followup({"outreach_id": oid})

        assert result == {"status": "re-queued", "reason": "still quiet hours"}
        mock_enqueue.assert_awaited_once()
        enqueue_call = mock_enqueue.call_args
        assert enqueue_call[1]["task_type"] == "send_sms_followup"
        assert enqueue_call[1]["priority"] == 7
        assert enqueue_call[1]["delay_seconds"] == 3600

    async def test_no_config_returns_skipped(self):
        """Missing SalesEngineConfig returns skip."""
        prospect = self._make_outreach_mock()
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        # db.execute for config lookup returns None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=True):
            result = await _handle_send_sms_followup({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "no config"}

    async def test_successful_sms_send(self):
        """Successful SMS send returns sent status with twilio_sid."""
        prospect = self._make_outreach_mock()
        config = MagicMock()
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=True), \
             patch("src.services.outreach_sms.generate_followup_sms_body", new_callable=AsyncMock, return_value="Follow up text"), \
             patch("src.services.outreach_sms.send_outreach_sms", new_callable=AsyncMock, return_value={"twilio_sid": "SM123", "error": None}):
            result = await _handle_send_sms_followup({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "sent", "twilio_sid": "SM123"}
        mock_db.commit.assert_awaited_once()

    async def test_sms_send_error_raises(self):
        """SMS send returning an error raises Exception."""
        prospect = self._make_outreach_mock()
        config = MagicMock()
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=True), \
             patch("src.services.outreach_sms.generate_followup_sms_body", new_callable=AsyncMock, return_value="text"), \
             patch("src.services.outreach_sms.send_outreach_sms", new_callable=AsyncMock, return_value={"error": "carrier rejected"}):
            with pytest.raises(Exception, match="carrier rejected"):
                await _handle_send_sms_followup({"outreach_id": str(uuid.uuid4())})

    async def test_empty_phone_string_treated_as_no_phone(self):
        """Empty string phone is still truthy, but None is not."""
        prospect = self._make_outreach_mock(prospect_phone="")
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        # Empty string is falsy in Python, should hit "no phone"
        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sms_followup({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "no phone"}


# ---------------------------------------------------------------------------
# _handle_send_sequence_email
# ---------------------------------------------------------------------------

class TestHandleSendSequenceEmail:
    """Tests for the sequence email handler which opens its own DB session."""

    def _make_outreach_mock(self, **overrides):
        """Create a mock Outreach row for email sequences."""
        defaults = {
            "id": uuid.uuid4(),
            "prospect_email": "test@example.com",
            "email_unsubscribed": False,
            "status": "cold",
            "last_email_replied_at": None,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    def _make_config_mock(self, **overrides):
        """Create a mock SalesEngineConfig."""
        defaults = {
            "is_active": True,
            "daily_email_limit": 50,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    async def test_no_outreach_id_returns_skipped(self):
        """Missing outreach_id in payload returns skip."""
        result = await _handle_send_sequence_email({})
        assert result == {"status": "skipped", "reason": "no outreach_id"}

    async def test_prospect_not_found(self):
        """Prospect not in DB returns skip."""
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=None)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "prospect not found"}

    async def test_unsubscribed_returns_skipped(self):
        """Unsubscribed prospect returns skip."""
        prospect = self._make_outreach_mock(email_unsubscribed=True)
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "unsubscribed"}

    async def test_no_email_returns_skipped(self):
        """Prospect without email returns skip."""
        prospect = self._make_outreach_mock(prospect_email=None)
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "no email"}

    async def test_replied_returns_skipped(self):
        """Prospect with prior reply should never get another deferred send."""
        prospect = self._make_outreach_mock(
            last_email_replied_at=datetime.now(timezone.utc),
        )
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "already replied"}

    async def test_terminal_status_returns_skipped(self):
        """Prospect in terminal lifecycle state should not be emailed."""
        prospect = self._make_outreach_mock(status="lost")
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "status lost not eligible"}

    async def test_empty_email_returns_skipped(self):
        """Prospect with empty string email returns skip."""
        prospect = self._make_outreach_mock(prospect_email="")
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "no email"}

    async def test_no_config_returns_skipped(self):
        """Missing SalesEngineConfig returns skip."""
        prospect = self._make_outreach_mock()
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "engine inactive"}

    async def test_inactive_config_returns_skipped(self):
        """Inactive SalesEngineConfig returns skip."""
        prospect = self._make_outreach_mock()
        config = self._make_config_mock(is_active=False)
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "skipped", "reason": "engine inactive"}

    async def test_outside_send_window_requeues(self):
        """Outside business hours, task is re-queued."""
        prospect = self._make_outreach_mock()
        config = self._make_config_mock()
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = config
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.workers.outreach_sequencer.is_within_send_window", return_value=False), \
             patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock) as mock_enqueue:
            oid = str(uuid.uuid4())
            result = await _handle_send_sequence_email({"outreach_id": oid})

        assert result == {"status": "re-queued", "reason": "outside send window"}
        mock_enqueue.assert_awaited_once()
        enqueue_call = mock_enqueue.call_args
        assert enqueue_call[1]["task_type"] == "send_sequence_email"
        assert enqueue_call[1]["priority"] == 5
        assert enqueue_call[1]["delay_seconds"] == 1800

    async def test_daily_limit_reached_requeues(self):
        """Daily email limit reached, task re-queued for tomorrow."""
        prospect = self._make_outreach_mock()
        config = self._make_config_mock(daily_email_limit=50)
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        # First execute call returns config; second returns count = 50 (at limit)
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = config

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 50

        mock_db.execute = AsyncMock(side_effect=[mock_config_result, mock_count_result])

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True), \
             patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock) as mock_enqueue:
            oid = str(uuid.uuid4())
            result = await _handle_send_sequence_email({"outreach_id": oid})

        assert result == {"status": "re-queued", "reason": "daily limit reached"}
        mock_enqueue.assert_awaited_once()
        enqueue_call = mock_enqueue.call_args
        assert enqueue_call[1]["task_type"] == "send_sequence_email"
        assert enqueue_call[1]["priority"] == 5
        assert enqueue_call[1]["delay_seconds"] >= 60  # minimum 60 seconds

    async def test_daily_limit_none_defaults_to_50(self):
        """daily_email_limit of None defaults to 50."""
        prospect = self._make_outreach_mock()
        config = self._make_config_mock(daily_email_limit=None)
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        # Config returns, count returns 50 (= default limit of 50)
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = config

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 50

        mock_db.execute = AsyncMock(side_effect=[mock_config_result, mock_count_result])

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True), \
             patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock) as mock_enqueue:
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "re-queued", "reason": "daily limit reached"}

    async def test_followup_not_due_requeues(self):
        """Deferred follow-up task should not send before cadence window."""
        prospect = self._make_outreach_mock(
            outreach_sequence_step=1,
            last_email_sent_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        config = self._make_config_mock(daily_email_limit=50, sequence_delay_hours=48)
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = config

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1  # Under daily limit

        mock_db.execute = AsyncMock(side_effect=[mock_config_result, mock_count_result])

        with (
            patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()),
            patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True),
            patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock) as mock_enqueue,
            patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock) as mock_send,
        ):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result == {"status": "re-queued", "reason": "followup not due"}
        mock_send.assert_not_awaited()
        mock_enqueue.assert_awaited_once()
        assert mock_enqueue.call_args.kwargs["task_type"] == "send_sequence_email"
        assert mock_enqueue.call_args.kwargs["delay_seconds"] >= 900

    async def test_successful_email_send(self):
        """Successful email send returns sent status with prospect_id."""
        prospect = self._make_outreach_mock()
        config = self._make_config_mock()
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = config

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 10  # Under limit

        mock_db.execute = AsyncMock(side_effect=[mock_config_result, mock_count_result])

        mock_settings = MagicMock()
        oid = str(uuid.uuid4())

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True), \
             patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock) as mock_send, \
             patch("src.config.get_settings", return_value=mock_settings):
            result = await _handle_send_sequence_email({"outreach_id": oid})

        assert result == {"status": "sent", "prospect_id": oid}
        mock_send.assert_awaited_once_with(mock_db, config, mock_settings, prospect)
        mock_db.commit.assert_awaited_once()

    async def test_count_result_none_treated_as_zero(self):
        """scalar() returning None for count is treated as 0."""
        prospect = self._make_outreach_mock()
        config = self._make_config_mock()
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = config

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = None  # No emails sent today

        mock_db.execute = AsyncMock(side_effect=[mock_config_result, mock_count_result])

        mock_settings = MagicMock()

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True), \
             patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock), \
             patch("src.config.get_settings", return_value=mock_settings):
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result["status"] == "sent"

    async def test_daily_limit_delay_minimum_60_seconds(self):
        """When calculated delay is very small, minimum 60 seconds is enforced."""
        prospect = self._make_outreach_mock()
        # daily_email_limit = 1 so it's easily hit
        config = self._make_config_mock(daily_email_limit=1)
        factory_cls, mock_db = _mock_async_session_factory()
        mock_db.get = AsyncMock(return_value=prospect)

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = config

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5  # Over limit

        mock_db.execute = AsyncMock(side_effect=[mock_config_result, mock_count_result])

        with patch("src.workers.task_processor.async_session_factory", return_value=factory_cls()), \
             patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True), \
             patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock) as mock_enqueue:
            result = await _handle_send_sequence_email({"outreach_id": str(uuid.uuid4())})

        assert result["status"] == "re-queued"
        enqueue_call = mock_enqueue.call_args
        assert enqueue_call[1]["delay_seconds"] >= 60


# ---------------------------------------------------------------------------
# Integration-style: _execute_task through _dispatch_task
# ---------------------------------------------------------------------------

class TestExecuteTaskIntegration:
    async def test_full_success_flow(self):
        """_execute_task -> _dispatch_task -> handler -> success."""
        task = _make_task(task_type="enrich_email", payload={"website": "example.com"})
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        with patch("src.services.enrichment.enrich_prospect_email", new_callable=AsyncMock, return_value={"email": "a@b.com"}):
            await _execute_task(mock_db, task)

        assert task.status == "completed"
        assert task.result_data == {"email": "a@b.com"}

    async def test_full_failure_retry_flow(self):
        """_execute_task -> _dispatch_task -> handler exception -> retry."""
        task = _make_task(
            task_type="classify_reply",
            payload={"text": "hello"},
            retry_count=0,
            max_retries=3,
        )
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        with patch("src.agents.sales_outreach.classify_reply", new_callable=AsyncMock, side_effect=Exception("API timeout")):
            await _execute_task(mock_db, task)

        assert task.status == "pending"
        assert task.retry_count == 1
        assert task.error_message == "API timeout"

    async def test_unknown_type_succeeds_with_skip(self):
        """Unknown task type completes successfully with skip result."""
        task = _make_task(task_type="nonexistent_handler", payload={})
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        await _execute_task(mock_db, task)

        assert task.status == "completed"
        assert task.result_data["status"] == "skipped"
        assert "unknown task type" in task.result_data["reason"]
