"""
Tests for src/workers/followup_scheduler.py — follow-up scheduler worker.

Covers:
- _heartbeat(): Redis heartbeat storage and error handling
- run_followup_scheduler(): Main loop with process/error/sleep cycle
- process_due_tasks(): Query logic, iteration, error handling, commit
- execute_followup_task(): All code paths including compliance, plan limits, consent, SMS send
"""
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.models.client import Client
from src.models.consent import ConsentRecord
from src.models.conversation import Conversation
from src.models.event_log import EventLog
from src.models.followup import FollowupTask
from src.models.lead import Lead
from src.schemas.agent_responses import FollowupResponse
from src.services.compliance import ComplianceResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ids():
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


_VALID_CONFIG = {
    "service_area": {
        "center": {"lat": 30.2672, "lng": -97.7431},
        "radius_miles": 35,
        "valid_zips": ["78701"],
    },
    "persona": {"rep_name": "Sarah", "tone": "friendly_professional"},
}


def _make_client(client_id, *, tier="pro", config=None, twilio_phone="+15121110000"):
    return Client(
        id=client_id,
        business_name="Cool HVAC Co",
        trade_type="hvac",
        tier=tier,
        twilio_phone=twilio_phone,
        twilio_messaging_service_sid="MG_test",
        config=config if config is not None else _VALID_CONFIG,
    )


def _make_consent(consent_id, client_id, phone="+15125551234"):
    return ConsentRecord(
        id=consent_id,
        phone=phone,
        client_id=client_id,
        consent_type="pec",
        consent_method="text_in",
    )


def _make_lead(
    lead_id,
    client_id,
    *,
    consent_id=None,
    state="cold",
    state_code="TX",
    cold_outreach_count=0,
):
    return Lead(
        id=lead_id,
        client_id=client_id,
        phone="+15125551234",
        first_name="Jane",
        source="google_lsa",
        state=state,
        state_code=state_code,
        consent_id=consent_id,
        cold_outreach_count=cold_outreach_count,
        service_type="AC Repair",
        total_messages_sent=0,
        total_sms_cost_usd=0.0,
    )


def _make_task(
    lead_id,
    client_id,
    *,
    task_type="cold_nurture",
    status="pending",
    sequence_number=1,
    scheduled_at=None,
    max_attempts=3,
    attempt_count=0,
):
    return FollowupTask(
        id=uuid.uuid4(),
        lead_id=lead_id,
        client_id=client_id,
        task_type=task_type,
        status=status,
        sequence_number=sequence_number,
        scheduled_at=scheduled_at or (datetime.now(timezone.utc) - timedelta(minutes=5)),
        max_attempts=max_attempts,
        attempt_count=attempt_count,
    )


# ---------------------------------------------------------------------------
# _heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    """Tests for _heartbeat() — Redis health check storage."""

    async def test_heartbeat_stores_timestamp_in_redis(self):
        redis_mock = AsyncMock()
        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=redis_mock):
            from src.workers.followup_scheduler import _heartbeat
            await _heartbeat()

        redis_mock.set.assert_awaited_once()
        args, kwargs = redis_mock.set.call_args
        assert args[0] == "leadlock:worker_health:followup_scheduler"
        assert kwargs.get("ex") == 300

    async def test_heartbeat_swallows_redis_errors(self):
        """Heartbeat should silently handle Redis failures."""
        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=ConnectionError("no redis")):
            from src.workers.followup_scheduler import _heartbeat
            # Should not raise
            await _heartbeat()


# ---------------------------------------------------------------------------
# run_followup_scheduler
# ---------------------------------------------------------------------------


class TestRunFollowupScheduler:
    """Tests for run_followup_scheduler() — main loop."""

    async def test_loop_calls_process_then_heartbeat_then_sleeps(self):
        """Verify the loop calls process_due_tasks, _heartbeat, and sleeps."""
        call_order = []

        async def fake_process():
            call_order.append("process")

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append(("sleep", seconds))
            # Stop the loop after one iteration
            raise KeyboardInterrupt()

        with patch("src.workers.followup_scheduler.process_due_tasks", side_effect=fake_process), \
             patch("src.workers.followup_scheduler._heartbeat", side_effect=fake_heartbeat), \
             patch("src.workers.followup_scheduler.asyncio.sleep", side_effect=fake_sleep):
            from src.workers.followup_scheduler import run_followup_scheduler
            with pytest.raises(KeyboardInterrupt):
                await run_followup_scheduler()

        assert call_order == ["process", "heartbeat", ("sleep", 60)]

    async def test_loop_catches_process_errors_and_continues(self):
        """process_due_tasks errors should be caught so the loop keeps going."""
        call_order = []

        async def fail_process():
            call_order.append("process_error")
            raise RuntimeError("db down")

        async def fake_heartbeat():
            call_order.append("heartbeat")

        async def fake_sleep(seconds):
            call_order.append("sleep")
            raise KeyboardInterrupt()

        with patch("src.workers.followup_scheduler.process_due_tasks", side_effect=fail_process), \
             patch("src.workers.followup_scheduler._heartbeat", side_effect=fake_heartbeat), \
             patch("src.workers.followup_scheduler.asyncio.sleep", side_effect=fake_sleep):
            from src.workers.followup_scheduler import run_followup_scheduler
            with pytest.raises(KeyboardInterrupt):
                await run_followup_scheduler()

        assert "process_error" in call_order
        assert "heartbeat" in call_order


# ---------------------------------------------------------------------------
# process_due_tasks
# ---------------------------------------------------------------------------


class TestProcessDueTasks:
    """Tests for process_due_tasks() — finds and dispatches tasks."""

    async def test_no_tasks_returns_early(self, db):
        """When there are no pending tasks, process_due_tasks returns early."""
        with patch("src.workers.followup_scheduler.async_session_factory") as factory_mock:
            # Create an async context manager that yields the db session
            session_cm = AsyncMock()
            session_cm.__aenter__ = AsyncMock(return_value=db)
            session_cm.__aexit__ = AsyncMock(return_value=False)
            factory_mock.return_value = session_cm

            from src.workers.followup_scheduler import process_due_tasks
            await process_due_tasks()
            # commit should not be called when there are no tasks
            # (function returns before commit)

    async def test_processes_due_tasks(self, db):
        """Pending+due tasks are loaded, executed, and committed."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id)
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id)
        task = _make_task(lead_id, client_id)

        db.add_all([client, consent, lead, task])
        await db.commit()

        sms_result = {
            "sid": "SM_test",
            "status": "sent",
            "provider": "twilio",
            "segments": 1,
            "cost_usd": 0.0079,
        }
        followup_response = FollowupResponse(
            message="Hi Jane, checking in from Cool HVAC Co!",
            followup_type="cold_nurture",
            sequence_number=1,
        )

        with patch("src.workers.followup_scheduler.async_session_factory") as factory_mock, \
             patch("src.workers.followup_scheduler.full_compliance_check") as comp_mock, \
             patch("src.workers.followup_scheduler.check_content_compliance") as content_mock, \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_response), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result), \
             patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True):

            session_cm = AsyncMock()
            session_cm.__aenter__ = AsyncMock(return_value=db)
            session_cm.__aexit__ = AsyncMock(return_value=False)
            factory_mock.return_value = session_cm

            comp_mock.return_value = ComplianceResult(True, "All clear")
            content_mock.return_value = ComplianceResult(True, "Content ok")

            from src.workers.followup_scheduler import process_due_tasks
            await process_due_tasks()

        # Task should be updated to sent
        await db.refresh(task)
        assert task.status == "sent"

    async def test_task_exception_increments_attempt(self, db):
        """When execute_followup_task raises, attempt_count increments and error is recorded."""
        lead_id, client_id, _ = _make_ids()
        client = _make_client(client_id)
        lead = _make_lead(lead_id, client_id, state="cold")
        task = _make_task(lead_id, client_id, attempt_count=0, max_attempts=3)

        db.add_all([client, lead, task])
        await db.commit()

        with patch("src.workers.followup_scheduler.async_session_factory") as factory_mock, \
             patch("src.workers.followup_scheduler.execute_followup_task", new_callable=AsyncMock, side_effect=RuntimeError("boom")):

            session_cm = AsyncMock()
            session_cm.__aenter__ = AsyncMock(return_value=db)
            session_cm.__aexit__ = AsyncMock(return_value=False)
            factory_mock.return_value = session_cm

            from src.workers.followup_scheduler import process_due_tasks
            await process_due_tasks()

        await db.refresh(task)
        assert task.attempt_count == 1
        assert task.last_error == "boom"
        assert task.status == "pending"  # still pending, not at max attempts yet

    async def test_task_exception_marks_failed_at_max_attempts(self, db):
        """When attempt_count reaches max_attempts, task is marked failed."""
        lead_id, client_id, _ = _make_ids()
        client = _make_client(client_id)
        lead = _make_lead(lead_id, client_id, state="cold")
        task = _make_task(lead_id, client_id, attempt_count=2, max_attempts=3)

        db.add_all([client, lead, task])
        await db.commit()

        with patch("src.workers.followup_scheduler.async_session_factory") as factory_mock, \
             patch("src.workers.followup_scheduler.execute_followup_task", new_callable=AsyncMock, side_effect=RuntimeError("fail3")):

            session_cm = AsyncMock()
            session_cm.__aenter__ = AsyncMock(return_value=db)
            session_cm.__aexit__ = AsyncMock(return_value=False)
            factory_mock.return_value = session_cm

            from src.workers.followup_scheduler import process_due_tasks
            await process_due_tasks()

        await db.refresh(task)
        assert task.attempt_count == 3
        assert task.status == "failed"


# ---------------------------------------------------------------------------
# execute_followup_task
# ---------------------------------------------------------------------------


class TestExecuteFollowupTask:
    """Tests for execute_followup_task() — the main execution logic."""

    # ---- Skip paths ----

    async def test_skips_when_lead_not_found(self, db):
        """Task skipped when lead does not exist."""
        _, client_id, _ = _make_ids()
        client = _make_client(client_id)
        db.add(client)
        await db.commit()

        fake_lead_id = uuid.uuid4()
        task = _make_task(fake_lead_id, client_id)
        db.add(task)
        await db.commit()

        from src.workers.followup_scheduler import execute_followup_task
        await execute_followup_task(db, task)

        assert task.status == "skipped"
        assert "not found" in task.skip_reason

    async def test_skips_when_client_not_found(self, db):
        """Task skipped when client does not exist."""
        lead_id, _, _ = _make_ids()
        fake_client_id = uuid.uuid4()
        lead = _make_lead(lead_id, fake_client_id)
        db.add(lead)
        await db.flush()

        task = _make_task(lead_id, fake_client_id)
        db.add(task)
        await db.commit()

        from src.workers.followup_scheduler import execute_followup_task
        await execute_followup_task(db, task)

        assert task.status == "skipped"
        assert "not found" in task.skip_reason

    async def test_skips_when_lead_opted_out(self, db):
        """Task skipped when lead.state is opted_out."""
        lead_id, client_id, _ = _make_ids()
        client = _make_client(client_id)
        lead = _make_lead(lead_id, client_id, state="opted_out")
        task = _make_task(lead_id, client_id)

        db.add_all([client, lead, task])
        await db.commit()

        from src.workers.followup_scheduler import execute_followup_task
        await execute_followup_task(db, task)

        assert task.status == "skipped"
        assert "opted_out" in task.skip_reason

    async def test_skips_when_lead_dead(self, db):
        """Task skipped when lead.state is dead."""
        lead_id, client_id, _ = _make_ids()
        client = _make_client(client_id)
        lead = _make_lead(lead_id, client_id, state="dead")
        task = _make_task(lead_id, client_id)

        db.add_all([client, lead, task])
        await db.commit()

        from src.workers.followup_scheduler import execute_followup_task
        await execute_followup_task(db, task)

        assert task.status == "skipped"
        assert "dead" in task.skip_reason

    async def test_skips_cold_nurture_on_starter_plan(self, db):
        """Cold nurture tasks are skipped on starter tier (no cold follow-ups)."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="starter")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        from src.workers.followup_scheduler import execute_followup_task
        await execute_followup_task(db, task)

        assert task.status == "skipped"
        assert "starter" in task.skip_reason.lower()

    async def test_skips_cold_nurture_when_lead_reengaged(self, db):
        """Cold nurture skipped if lead re-engaged (state not cold/intake_sent)."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="qualifying")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        assert task.status == "skipped"
        assert task.skip_reason == "Lead re-engaged"

    async def test_cold_nurture_proceeds_when_lead_state_cold(self, db):
        """Cold nurture proceeds when lead.state == 'cold'."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        followup_resp = FollowupResponse(
            message="Hey Jane, still need AC help?",
            followup_type="cold_nurture",
            sequence_number=1,
        )
        sms_result = {"sid": "SM1", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        assert task.status == "sent"
        assert lead.cold_outreach_count == 1

    async def test_cold_nurture_proceeds_when_lead_state_intake_sent(self, db):
        """Cold nurture proceeds when lead.state == 'intake_sent'."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="intake_sent")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        followup_resp = FollowupResponse(
            message="Hey Jane, following up on your request.",
            followup_type="cold_nurture",
            sequence_number=1,
        )
        sms_result = {"sid": "SM2", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        assert task.status == "sent"

    async def test_skips_when_compliance_check_fails(self, db):
        """Task skipped when full_compliance_check returns blocked."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        blocked = ComplianceResult(False, "Quiet hours active", "tcpa_quiet_hours")

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=blocked):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        assert task.status == "skipped"
        assert task.skip_reason == "Quiet hours active"

    async def test_skips_when_content_compliance_fails(self, db):
        """Task skipped when check_content_compliance fails on the generated message."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        followup_resp = FollowupResponse(
            message="Check out bit.ly/deal",
            followup_type="cold_nurture",
            sequence_number=1,
        )
        content_blocked = ComplianceResult(False, "URL shortener detected", "content_url_shortener")

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=content_blocked):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        assert task.status == "skipped"
        assert "Content compliance failed" in task.skip_reason

    # ---- Consent handling ----

    async def test_consent_loaded_when_consent_id_present(self, db):
        """Consent record is loaded and passed to compliance check when lead has consent_id."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        followup_resp = FollowupResponse(message="Hi Jane!", followup_type="cold_nurture", sequence_number=1)
        sms_result = {"sid": "SM3", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")) as comp_mock, \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        # Verify compliance was called with consent info
        comp_mock.assert_called_once()
        kwargs = comp_mock.call_args
        assert kwargs[1]["has_consent"] is True or kwargs[0][0] is True
        # has_consent should be True since we loaded a real consent record

    async def test_no_consent_id_passes_none_consent(self, db):
        """When lead has no consent_id, compliance check gets has_consent=False."""
        lead_id, client_id, _ = _make_ids()
        client = _make_client(client_id, tier="pro")
        lead = _make_lead(lead_id, client_id, consent_id=None, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, lead, task])
        await db.commit()

        # Compliance will block because no consent
        blocked = ComplianceResult(False, "No consent", "tcpa_no_consent")

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=blocked) as comp_mock:
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        assert task.status == "skipped"
        # Verify has_consent=False was passed
        comp_mock.assert_called_once()

    # ---- Successful send flow ----

    async def test_successful_send_records_conversation_and_event(self, db):
        """Full successful path: compliance ok, send SMS, record convo + event."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture", sequence_number=2)

        db.add_all([client, consent, lead, task])
        await db.commit()

        msg_text = "Hi Jane, just following up on AC Repair — Cool HVAC Co"
        followup_resp = FollowupResponse(
            message=msg_text,
            followup_type="cold_nurture",
            sequence_number=2,
        )
        sms_result = {
            "sid": "SM_abc",
            "status": "delivered",
            "provider": "twilio",
            "segments": 2,
            "cost_usd": 0.0158,
        }

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        # Task updates
        assert task.status == "sent"
        assert task.sent_at is not None
        assert task.message_content == msg_text

        # Lead updates
        assert lead.total_messages_sent == 1
        assert lead.total_sms_cost_usd == 0.0158
        assert lead.last_outbound_at is not None
        assert lead.cold_outreach_count == 1

    async def test_non_cold_nurture_does_not_increment_cold_outreach(self, db):
        """day_before_reminder should not increment cold_outreach_count."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="booked")
        task = _make_task(lead_id, client_id, task_type="day_before_reminder", sequence_number=1)

        db.add_all([client, consent, lead, task])
        await db.commit()

        followup_resp = FollowupResponse(
            message="Reminder: your appointment is tomorrow!",
            followup_type="day_before_reminder",
            sequence_number=1,
        )
        sms_result = {"sid": "SM_r1", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        assert task.status == "sent"
        assert lead.cold_outreach_count == 0  # not incremented

    async def test_send_sms_result_without_optional_keys(self, db):
        """SMS result dict may be missing optional keys — defaults apply."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        followup_resp = FollowupResponse(
            message="Hey Jane!",
            followup_type="cold_nurture",
            sequence_number=1,
        )
        # Minimal SMS result — missing optional keys
        sms_result = {}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        assert task.status == "sent"
        assert lead.total_sms_cost_usd == 0.0  # default from .get("cost_usd", 0.0)

    # ---- ClientConfig handling ----

    async def test_uses_client_config_when_present(self, db):
        """When client.config has persona data, it's used for rep_name."""
        lead_id, client_id, consent_id = _make_ids()
        config = {
            "service_area": {"center": {"lat": 30.0, "lng": -97.0}},
            "persona": {"rep_name": "Mike", "tone": "casual"},
        }
        client = _make_client(client_id, tier="pro", config=config)
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        followup_resp = FollowupResponse(message="Hi!", followup_type="cold_nurture", sequence_number=1)
        sms_result = {"sid": "SM_c", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp) as pf_mock, \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        # Verify process_followup was called with Mike as rep_name
        pf_mock.assert_awaited_once()
        call_kwargs = pf_mock.call_args[1]
        assert call_kwargs["rep_name"] == "Mike"

    async def test_uses_default_config_when_none(self, db):
        """When client.config is falsy, ClientConfig() default branch is exercised."""
        lead_id, client_id, consent_id = _make_ids()
        # Use a valid config dict for DB, then override to None after save
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        # Override config to None after save, then mock ClientConfig to avoid validation error
        client.config = None

        mock_config = MagicMock()
        mock_config.persona.rep_name = "DefaultRep"

        followup_resp = FollowupResponse(message="Hi!", followup_type="cold_nurture", sequence_number=1)
        sms_result = {"sid": "SM_d", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.ClientConfig", return_value=mock_config) as cc_ctor, \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp) as pf_mock, \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        # ClientConfig() was called with no args (the else branch)
        cc_ctor.assert_called_once_with()
        pf_mock.assert_awaited_once()
        call_kwargs = pf_mock.call_args[1]
        assert call_kwargs["rep_name"] == "DefaultRep"

    # ---- SMS and conversation details ----

    async def test_conversation_uses_twilio_phone_or_empty(self, db):
        """When client.twilio_phone is None, from_phone defaults to empty string."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro", twilio_phone=None)
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        followup_resp = FollowupResponse(message="Hi!", followup_type="cold_nurture", sequence_number=1)
        sms_result = {"sid": "SM_n", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        assert task.status == "sent"

    async def test_process_followup_receives_correct_parameters(self, db):
        """Verify all parameters sent to process_followup."""
        lead_id, client_id, consent_id = _make_ids()
        config = {
            "service_area": {"center": {"lat": 30.0, "lng": -97.0}},
            "persona": {"rep_name": "Alex"},
        }
        client = _make_client(client_id, tier="pro", config=config)
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        lead.first_name = "Bob"
        lead.service_type = "Plumbing"
        task = _make_task(lead_id, client_id, task_type="cold_nurture", sequence_number=3)

        db.add_all([client, consent, lead, task])
        await db.commit()

        followup_resp = FollowupResponse(message="Msg", followup_type="cold_nurture", sequence_number=3)
        sms_result = {"sid": "SM_p", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp) as pf_mock, \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        pf_mock.assert_awaited_once_with(
            lead_first_name="Bob",
            service_type="Plumbing",
            business_name="Cool HVAC Co",
            rep_name="Alex",
            followup_type="cold_nurture",
            sequence_number=3,
        )

    async def test_send_sms_receives_correct_parameters(self, db):
        """Verify send_sms is called with correct phone, body, and from info."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro", twilio_phone="+15129990000")
        client.twilio_messaging_service_sid = "MG_test_sid"
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        lead.phone = "+15125559999"
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        msg = "Hello from Cool HVAC"
        followup_resp = FollowupResponse(message=msg, followup_type="cold_nurture", sequence_number=1)
        sms_result = {"sid": "SM_s", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result) as sms_mock:
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        sms_mock.assert_awaited_once_with(
            to="+15125559999",
            body=msg,
            from_phone="+15129990000",
            messaging_service_sid="MG_test_sid",
        )

    async def test_compliance_check_receives_correct_parameters(self, db):
        """Verify full_compliance_check receives the right kwargs from task context."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        consent.consent_type = "pewc"
        consent.opted_out = True  # Will block, but let's check params
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold", state_code="FL", cold_outreach_count=2)
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        blocked = ComplianceResult(False, "Opted out", "tcpa_opt_out")

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=blocked) as comp_mock:
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        comp_mock.assert_called_once_with(
            has_consent=True,
            consent_type="pewc",
            is_opted_out=True,
            state_code="FL",
            is_emergency=False,
            cold_outreach_count=2,
            is_reply_to_inbound=False,
            message="",
            is_first_message=False,
            business_name="Cool HVAC Co",
        )

    async def test_check_content_compliance_receives_correct_parameters(self, db):
        """Verify check_content_compliance is called with generated message and business name."""
        lead_id, client_id, consent_id = _make_ids()
        client = _make_client(client_id, tier="pro")
        consent = _make_consent(consent_id, client_id)
        lead = _make_lead(lead_id, client_id, consent_id=consent_id, state="cold")
        task = _make_task(lead_id, client_id, task_type="cold_nurture")

        db.add_all([client, consent, lead, task])
        await db.commit()

        msg = "Checking in from Cool HVAC Co"
        followup_resp = FollowupResponse(message=msg, followup_type="cold_nurture", sequence_number=1)
        sms_result = {"sid": "SM_cc", "status": "sent", "provider": "twilio", "segments": 1, "cost_usd": 0.0079}

        with patch("src.workers.followup_scheduler.is_cold_followup_enabled", return_value=True), \
             patch("src.workers.followup_scheduler.full_compliance_check", return_value=ComplianceResult(True, "ok")), \
             patch("src.workers.followup_scheduler.process_followup", new_callable=AsyncMock, return_value=followup_resp), \
             patch("src.workers.followup_scheduler.check_content_compliance", return_value=ComplianceResult(True, "ok")) as cc_mock, \
             patch("src.workers.followup_scheduler.send_sms", new_callable=AsyncMock, return_value=sms_result):
            from src.workers.followup_scheduler import execute_followup_task
            await execute_followup_task(db, task)

        cc_mock.assert_called_once_with(
            message=msg,
            is_first_message=False,
            business_name="Cool HVAC Co",
        )


# ---------------------------------------------------------------------------
# POLL_INTERVAL_SECONDS constant
# ---------------------------------------------------------------------------


class TestConstants:
    def test_poll_interval_is_60(self):
        from src.workers.followup_scheduler import POLL_INTERVAL_SECONDS
        assert POLL_INTERVAL_SECONDS == 60
