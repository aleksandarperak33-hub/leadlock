"""
Sales Engine API tests - comprehensive coverage for all endpoints in src/api/sales_engine.py.
Tests webhooks, unsubscribe, config, metrics, prospects, campaigns, templates,
worker status/controls, bulk operations, command center, and helper functions.
All external services (Redis, AI, SMS, scraping) are mocked.
"""
import json
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from sqlalchemy import and_, func

from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.scrape_job import ScrapeJob
from src.models.sales_config import SalesEngineConfig
from src.models.email_blacklist import EmailBlacklist
from src.models.campaign import Campaign
from src.models.email_template import EmailTemplate


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_prospect(db, **overrides):
    """Create and flush an Outreach prospect with sensible defaults."""
    now = datetime.now(timezone.utc)
    defaults = {
        "prospect_name": "Test Prospect",
        "prospect_company": "Test Co",
        "prospect_email": "test@example.com",
        "prospect_phone": "+15125551234",
        "prospect_trade_type": "hvac",
        "status": "cold",
        "source": "brave",
        "city": "Austin",
        "state_code": "TX",
        "outreach_sequence_step": 1,
        "total_emails_sent": 0,
        "total_cost_usd": 0.0,
        "email_unsubscribed": False,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    prospect = Outreach(**defaults)
    db.add(prospect)
    return prospect


def _make_email(db, outreach_id, **overrides):
    """Create and flush an OutreachEmail with sensible defaults."""
    now = datetime.now(timezone.utc)
    defaults = {
        "outreach_id": outreach_id,
        "direction": "outbound",
        "subject": "Test Subject",
        "body_text": "Test body",
        "from_email": "sales@leadlock.com",
        "to_email": "test@example.com",
        "sequence_step": 1,
        "sent_at": now,
    }
    defaults.update(overrides)
    email = OutreachEmail(**defaults)
    db.add(email)
    return email


def _make_config(db, **overrides):
    """Create a SalesEngineConfig with sensible defaults."""
    defaults = {
        "is_active": True,
        "daily_email_limit": 50,
        "daily_scrape_limit": 100,
        "sequence_delay_hours": 48,
        "max_sequence_steps": 3,
        "from_email": "sales@leadlock.com",
        "from_name": "LeadLock",
        "send_hours_start": "08:00",
        "send_hours_end": "18:00",
        "send_timezone": "America/Chicago",
        "send_weekdays_only": True,
        "scraper_paused": False,
        "sequencer_paused": False,
        "cleanup_paused": False,
        "monthly_budget_usd": 100.0,
        "budget_alert_threshold": 0.8,
    }
    defaults.update(overrides)
    config = SalesEngineConfig(**defaults)
    db.add(config)
    return config


def _make_scrape_job(db, **overrides):
    """Create a ScrapeJob with sensible defaults."""
    now = datetime.now(timezone.utc)
    defaults = {
        "platform": "brave",
        "trade_type": "hvac",
        "location_query": "hvac in Austin, TX",
        "city": "Austin",
        "state_code": "TX",
        "status": "completed",
        "results_found": 10,
        "new_prospects_created": 5,
        "duplicates_skipped": 3,
        "api_cost_usd": 0.01,
        "started_at": now - timedelta(minutes=5),
        "completed_at": now,
        "created_at": now,
    }
    defaults.update(overrides)
    job = ScrapeJob(**defaults)
    db.add(job)
    return job


def _make_campaign(db, **overrides):
    """Create a Campaign with sensible defaults."""
    now = datetime.now(timezone.utc)
    defaults = {
        "name": "Test Campaign",
        "description": "A test campaign",
        "status": "active",
        "target_trades": ["hvac"],
        "target_locations": [{"city": "Austin", "state": "TX"}],
        "sequence_steps": [],
        "daily_limit": 25,
        "total_sent": 0,
        "total_opened": 0,
        "total_replied": 0,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    campaign = Campaign(**defaults)
    db.add(campaign)
    return campaign


def _make_template(db, **overrides):
    """Create an EmailTemplate with sensible defaults."""
    now = datetime.now(timezone.utc)
    defaults = {
        "name": "Test Template",
        "step_type": "first_contact",
        "subject_template": "Hi {{name}}",
        "body_template": "<p>Hello</p>",
        "ai_instructions": "Be friendly",
        "is_ai_generated": True,
        "created_at": now,
    }
    defaults.update(overrides)
    template = EmailTemplate(**defaults)
    db.add(template)
    return template


def _mock_request(form_data=None, json_data=None, query_params=None, headers=None):
    """Build a mock FastAPI Request object."""
    req = AsyncMock()
    if form_data is not None:
        req.form = AsyncMock(return_value=form_data)
    if json_data is not None:
        req.json = AsyncMock(return_value=json_data)
    req.query_params = query_params or {}
    req.headers = headers or {}
    return req


# ── _record_email_signal ──────────────────────────────────────────────────

class TestRecordEmailSignal:
    """Tests for the _record_email_signal helper."""

    @patch("src.services.learning.record_signal", new_callable=AsyncMock)
    @patch("src.services.learning._time_bucket", return_value="morning")
    async def test_records_signal_successfully(self, mock_bucket, mock_signal):
        """Should call record_signal with correct dimensions."""
        from src.api.sales_engine import _record_email_signal

        prospect = MagicMock()
        prospect.id = uuid.uuid4()
        prospect.prospect_trade_type = "hvac"
        prospect.city = "Austin"
        prospect.state_code = "TX"

        email_record = MagicMock()
        email_record.sent_at = datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc)
        email_record.sequence_step = 1

        await _record_email_signal("email_opened", prospect, email_record, 1.0)

        mock_signal.assert_called_once()
        call_kwargs = mock_signal.call_args[1]
        assert call_kwargs["signal_type"] == "email_opened"
        assert call_kwargs["value"] == 1.0
        assert call_kwargs["dimensions"]["trade"] == "hvac"
        assert call_kwargs["dimensions"]["city"] == "Austin"

    async def test_handles_import_error_gracefully(self):
        """Should not raise even if learning module import fails."""
        from src.api.sales_engine import _record_email_signal

        prospect = MagicMock()
        prospect.id = uuid.uuid4()
        prospect.prospect_trade_type = None
        prospect.city = None
        prospect.state_code = None

        email_record = MagicMock()
        email_record.sent_at = None
        email_record.sequence_step = 1

        with patch(
            "src.services.learning.record_signal",
            side_effect=Exception("import fail"),
        ):
            # Should not raise
            await _record_email_signal("email_opened", prospect, email_record, 1.0)

    @patch("src.services.learning.record_signal", new_callable=AsyncMock)
    @patch("src.services.learning._time_bucket", return_value="unknown")
    async def test_handles_missing_sent_at(self, mock_bucket, mock_signal):
        """When sent_at is None, should use defaults for hour and day."""
        from src.api.sales_engine import _record_email_signal

        prospect = MagicMock()
        prospect.id = uuid.uuid4()
        prospect.prospect_trade_type = None
        prospect.city = None
        prospect.state_code = None

        email_record = MagicMock()
        email_record.sent_at = None
        email_record.sequence_step = 2

        await _record_email_signal("email_replied", prospect, email_record, 0.5)

        call_kwargs = mock_signal.call_args[1]
        assert call_kwargs["dimensions"]["day_of_week"] == "unknown"
        assert call_kwargs["dimensions"]["trade"] == "general"


# ── _trigger_sms_followup ────────────────────────────────────────────────

class TestTriggerSmsFollowup:
    """Tests for the _trigger_sms_followup helper."""

    async def test_returns_false_when_no_config(self, db):
        """Should return False if no SalesEngineConfig exists."""
        from src.api.sales_engine import _trigger_sms_followup

        prospect = _make_prospect(db)
        await db.flush()

        result = await _trigger_sms_followup(db, prospect)
        assert result is False

    async def test_returns_false_when_sms_disabled(self, db):
        """Should return False if sms_after_email_reply is False."""
        from src.api.sales_engine import _trigger_sms_followup

        _make_config(db, sms_after_email_reply=False)
        prospect = _make_prospect(db)
        await db.flush()

        result = await _trigger_sms_followup(db, prospect)
        assert result is False

    async def test_returns_false_when_no_phone(self, db):
        """Should return False if prospect has no phone number."""
        from src.api.sales_engine import _trigger_sms_followup

        _make_config(db, sms_after_email_reply=True)
        prospect = _make_prospect(db, prospect_phone=None)
        await db.flush()

        result = await _trigger_sms_followup(db, prospect)
        assert result is False

    @patch("src.services.outreach_sms.send_outreach_sms", new_callable=AsyncMock)
    @patch("src.services.outreach_sms.generate_followup_sms_body", new_callable=AsyncMock)
    @patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=True)
    async def test_sends_sms_when_within_hours(
        self, mock_quiet, mock_body, mock_send, db
    ):
        """Should send SMS immediately if within send window."""
        from src.api.sales_engine import _trigger_sms_followup

        _make_config(db, sms_after_email_reply=True)
        prospect = _make_prospect(db, prospect_phone="+15125551234")
        await db.flush()

        mock_body.return_value = "Hi, thanks for your reply!"
        mock_send.return_value = {"error": None}

        result = await _trigger_sms_followup(db, prospect)
        assert result is True
        mock_send.assert_called_once()

    @patch("src.services.outreach_sms.send_outreach_sms", new_callable=AsyncMock)
    @patch("src.services.outreach_sms.generate_followup_sms_body", new_callable=AsyncMock)
    @patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=True)
    async def test_returns_false_on_sms_error(
        self, mock_quiet, mock_body, mock_send, db
    ):
        """Should return False if SMS send returns an error."""
        from src.api.sales_engine import _trigger_sms_followup

        _make_config(db, sms_after_email_reply=True)
        prospect = _make_prospect(db, prospect_phone="+15125551234")
        await db.flush()

        mock_body.return_value = "Hi there!"
        mock_send.return_value = {"error": "Twilio failed"}

        result = await _trigger_sms_followup(db, prospect)
        assert result is False

    @patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock)
    @patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=False)
    async def test_defers_sms_during_quiet_hours(self, mock_quiet, mock_enqueue, db):
        """Should enqueue a deferred task if outside quiet hours."""
        from src.api.sales_engine import _trigger_sms_followup

        _make_config(db, sms_after_email_reply=True)
        prospect = _make_prospect(db, prospect_phone="+15125551234")
        await db.flush()

        result = await _trigger_sms_followup(db, prospect)
        assert result is True
        mock_enqueue.assert_called_once()
        call_kwargs = mock_enqueue.call_args[1]
        assert call_kwargs["task_type"] == "send_sms_followup"

    @patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock, side_effect=Exception("Redis down"))
    @patch("src.services.outreach_sms.is_within_sms_quiet_hours", return_value=False)
    async def test_returns_false_when_enqueue_fails(self, mock_quiet, mock_enqueue, db):
        """Should return False if enqueue raises an exception."""
        from src.api.sales_engine import _trigger_sms_followup

        _make_config(db, sms_after_email_reply=True)
        prospect = _make_prospect(db, prospect_phone="+15125551234")
        await db.flush()

        result = await _trigger_sms_followup(db, prospect)
        assert result is False


# ── _verify_sendgrid_webhook ──────────────────────────────────────────────

class TestVerifySendgridWebhook:
    """Tests for the _verify_sendgrid_webhook helper."""

    @patch("src.config.get_settings")
    async def test_rejects_in_production_when_no_key(self, mock_settings):
        """Should return False in production if no verification key set."""
        from src.api.sales_engine import _verify_sendgrid_webhook

        settings = MagicMock()
        settings.sendgrid_webhook_verification_key = ""
        settings.app_env = "production"
        mock_settings.return_value = settings

        request = _mock_request(query_params={}, headers={})
        result = await _verify_sendgrid_webhook(request)
        assert result is False

    @patch("src.config.get_settings")
    async def test_accepts_in_dev_when_no_key(self, mock_settings):
        """Should return True in non-production if no verification key set (with warning)."""
        from src.api.sales_engine import _verify_sendgrid_webhook

        settings = MagicMock()
        settings.sendgrid_webhook_verification_key = ""
        settings.environment = "development"
        mock_settings.return_value = settings

        request = _mock_request(query_params={}, headers={})
        result = await _verify_sendgrid_webhook(request)
        assert result is True

    @patch("src.config.get_settings")
    async def test_rejects_missing_token(self, mock_settings):
        """Should return False if key is configured but token is missing."""
        from src.api.sales_engine import _verify_sendgrid_webhook

        settings = MagicMock()
        settings.sendgrid_webhook_verification_key = "secret123"
        mock_settings.return_value = settings

        request = _mock_request(query_params={}, headers={})
        result = await _verify_sendgrid_webhook(request)
        assert result is False

    @patch("src.config.get_settings")
    async def test_accepts_valid_query_token(self, mock_settings):
        """Should return True when query param token matches."""
        from src.api.sales_engine import _verify_sendgrid_webhook

        settings = MagicMock()
        settings.sendgrid_webhook_verification_key = "secret123"
        mock_settings.return_value = settings

        request = _mock_request(query_params={"token": "secret123"}, headers={})
        result = await _verify_sendgrid_webhook(request)
        assert result is True

    @patch("src.config.get_settings")
    async def test_accepts_valid_header_token(self, mock_settings):
        """Should return True when X-Webhook-Token header matches."""
        from src.api.sales_engine import _verify_sendgrid_webhook

        settings = MagicMock()
        settings.sendgrid_webhook_verification_key = "secret123"
        mock_settings.return_value = settings

        request = _mock_request(
            query_params={},
            headers={"X-Webhook-Token": "secret123"},
        )
        result = await _verify_sendgrid_webhook(request)
        assert result is True

    @patch("src.config.get_settings")
    async def test_rejects_wrong_token(self, mock_settings):
        """Should return False when token does not match."""
        from src.api.sales_engine import _verify_sendgrid_webhook

        settings = MagicMock()
        settings.sendgrid_webhook_verification_key = "secret123"
        mock_settings.return_value = settings

        request = _mock_request(query_params={"token": "wrong"}, headers={})
        result = await _verify_sendgrid_webhook(request)
        assert result is False


# ── Inbound Email Webhook ────────────────────────────────────────────────

class TestInboundEmailWebhook:
    """Tests for POST /api/v1/sales/inbound-email."""

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=False)
    async def test_rejects_invalid_token(self, mock_verify, db):
        """Should raise 403 when webhook verification fails."""
        from src.api.sales_engine import inbound_email_webhook

        request = _mock_request()
        with pytest.raises(HTTPException) as exc_info:
            await inbound_email_webhook(request, db)
        assert exc_info.value.status_code == 403

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_ignores_empty_from_email(self, mock_verify, db):
        """Should return ignored status when from email is empty."""
        from src.api.sales_engine import inbound_email_webhook

        request = _mock_request(form_data={"from": "", "to": "sales@leadlock.com", "subject": "Re: Hi", "text": "Hello", "html": ""})
        result = await inbound_email_webhook(request, db)
        assert result["status"] == "ignored"
        assert result["reason"] == "no from email"

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_ignores_unknown_sender(self, mock_verify, db):
        """Should return ignored when sender is not in outreach database."""
        from src.api.sales_engine import inbound_email_webhook

        request = _mock_request(form_data={
            "from": "unknown@example.com",
            "to": "sales@leadlock.com",
            "subject": "Re: Hi",
            "text": "Hello",
            "html": "",
        })
        result = await inbound_email_webhook(request, db)
        assert result["status"] == "ignored"
        assert result["reason"] == "unknown sender"

    @patch("src.api.sales_webhooks._trigger_sms_followup", new_callable=AsyncMock, return_value=True)
    @patch("src.agents.sales_outreach.classify_reply", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_processes_interested_reply(
        self, mock_verify, mock_signal, mock_classify, mock_sms, db
    ):
        """Should process interested reply: update status, record email, trigger SMS."""
        from src.api.sales_engine import inbound_email_webhook

        prospect = _make_prospect(db, prospect_email="buyer@acme.com")
        await db.flush()

        mock_classify.return_value = {"classification": "interested"}

        request = _mock_request(form_data={
            "from": "buyer@acme.com",
            "to": "sales@leadlock.com",
            "subject": "Re: Your Services",
            "text": "I am interested",
            "html": "",
        })

        result = await inbound_email_webhook(request, db)
        assert result["status"] == "processed"
        assert result["classification"] == "interested"
        assert result["sms_sent"] is True
        assert prospect.status == "demo_scheduled"

    @patch("src.agents.sales_outreach.classify_reply", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_processes_rejection_reply(self, mock_verify, mock_signal, mock_classify, db):
        """Should mark prospect as lost on rejection reply."""
        from src.api.sales_engine import inbound_email_webhook

        prospect = _make_prospect(db, prospect_email="nope@acme.com")
        await db.flush()

        mock_classify.return_value = {"classification": "rejection"}

        request = _mock_request(form_data={
            "from": "nope@acme.com",
            "to": "sales@leadlock.com",
            "subject": "Re: Your Services",
            "text": "Not interested",
            "html": "",
        })

        result = await inbound_email_webhook(request, db)
        assert result["status"] == "processed"
        assert result["classification"] == "rejection"
        assert prospect.status == "lost"

    @patch("src.agents.sales_outreach.classify_reply", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_processes_unsubscribe_reply(self, mock_verify, mock_signal, mock_classify, db):
        """Should unsubscribe prospect when reply is classified as unsubscribe."""
        from src.api.sales_engine import inbound_email_webhook

        prospect = _make_prospect(db, prospect_email="stop@acme.com")
        await db.flush()

        mock_classify.return_value = {"classification": "unsubscribe"}

        request = _mock_request(form_data={
            "from": "stop@acme.com",
            "to": "sales@leadlock.com",
            "subject": "Re: Your Services",
            "text": "Unsubscribe me",
            "html": "",
        })

        result = await inbound_email_webhook(request, db)
        assert result["status"] == "processed"
        assert prospect.email_unsubscribed is True
        assert prospect.status == "lost"

    @patch("src.agents.sales_outreach.classify_reply", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_extracts_email_from_name_angle_bracket_format(
        self, mock_verify, mock_classify, db
    ):
        """Should extract email from 'Name <email>' format."""
        from src.api.sales_engine import inbound_email_webhook

        prospect = _make_prospect(db, prospect_email="buyer@acme.com")
        await db.flush()

        mock_classify.return_value = {"classification": "auto_reply"}

        request = _mock_request(form_data={
            "from": "Joe Buyer <buyer@acme.com>",
            "to": "sales@leadlock.com",
            "subject": "OOO",
            "text": "Out of office",
            "html": "",
        })

        result = await inbound_email_webhook(request, db)
        assert result["status"] == "processed"
        assert result["prospect_id"] == str(prospect.id)

    @patch("src.agents.sales_outreach.classify_reply", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_prefers_mailbox_aware_recent_thread_match(
        self, mock_verify, mock_classify, db
    ):
        """Reply should map to the newest outbound thread for the mailbox that received it."""
        from src.api.sales_engine import inbound_email_webhook

        old_prospect = _make_prospect(
            db,
            prospect_name="Old Prospect",
            prospect_email="shared@acme.com",
            updated_at=datetime.now(timezone.utc) - timedelta(days=3),
        )
        new_prospect = _make_prospect(
            db,
            prospect_name="New Prospect",
            prospect_email="shared@acme.com",
        )
        await db.flush()

        _make_email(
            db,
            old_prospect.id,
            to_email="shared@acme.com",
            from_email="ops1@leadlock.org",
            sent_at=datetime.now(timezone.utc) - timedelta(days=2),
        )
        _make_email(
            db,
            new_prospect.id,
            to_email="shared@acme.com",
            from_email="ops2@leadlock.org",
            sent_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        await db.flush()

        mock_classify.return_value = {"classification": "auto_reply"}

        request = _mock_request(form_data={
            "from": "Shared Contact <shared@acme.com>",
            "to": "ops2@leadlock.org",
            "subject": "Re: follow-up",
            "text": "Thanks",
            "html": "",
        })

        result = await inbound_email_webhook(request, db)
        assert result["status"] == "processed"
        assert result["prospect_id"] == str(new_prospect.id)

    @patch("src.agents.sales_outreach.classify_reply", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_does_not_mutate_campaign_counter_on_reply(
        self, mock_verify, mock_signal, mock_classify, db
    ):
        """Replies should NOT increment denormalized campaign counter (calculated metrics used instead)."""
        from src.api.sales_engine import inbound_email_webhook

        campaign = _make_campaign(db, total_replied=5)
        await db.flush()
        prospect = _make_prospect(
            db, prospect_email="camp@acme.com", campaign_id=campaign.id
        )
        await db.flush()

        mock_classify.return_value = {"classification": "interested"}

        request = _mock_request(form_data={
            "from": "camp@acme.com",
            "to": "sales@leadlock.com",
            "subject": "Re: Campaign",
            "text": "Tell me more",
            "html": "",
        })

        with patch("src.api.sales_engine._trigger_sms_followup", new_callable=AsyncMock, return_value=False):
            result = await inbound_email_webhook(request, db)

        assert result["status"] == "processed"
        assert campaign.total_replied == 5  # unchanged - calculated metrics used instead


# ── Email Events Webhook ─────────────────────────────────────────────────

class TestEmailEventsWebhook:
    """Tests for POST /api/v1/sales/email-events."""

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=False)
    async def test_rejects_invalid_token(self, mock_verify, db):
        """Should raise 403 when verification fails."""
        from src.api.sales_engine import email_events_webhook

        request = _mock_request()
        with pytest.raises(HTTPException) as exc_info:
            await email_events_webhook(request, db)
        assert exc_info.value.status_code == 403

    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_processes_delivered_event(self, mock_verify, mock_signal, db):
        """Should update delivered_at on delivery event."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db)
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_msg_123")
        await db.flush()

        events = [{"event": "delivered", "sg_message_id": "sg_msg_123.extra", "timestamp": 1700000000}]
        request = _mock_request(json_data=events, query_params={"token": "x"}, headers={})

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert email.delivered_at is not None

    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_processes_open_event(self, mock_verify, mock_signal, db):
        """Should update opened_at on open event and update prospect."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db)
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_open_1")
        await db.flush()

        events = [{
            "event": "open",
            "sg_message_id": "sg_open_1",
            "outreach_id": str(prospect.id),
            "timestamp": 1700000000,
        }]
        request = _mock_request(json_data=events, query_params={"token": "x"}, headers={})

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert email.opened_at is not None
        assert prospect.last_email_opened_at is not None

    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_processes_click_event(self, mock_verify, mock_signal, db):
        """Should update clicked_at on click event."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db)
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_click_1")
        await db.flush()

        events = [{
            "event": "click",
            "sg_message_id": "sg_click_1",
            "outreach_id": str(prospect.id),
            "timestamp": 1700000000,
        }]
        request = _mock_request(json_data=events)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert email.clicked_at is not None

    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_processes_bounce_event_marks_prospect_lost(self, mock_verify, mock_signal, db):
        """Should mark prospect as lost and email_verified as False on hard bounce."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db, prospect_email="bad@bouncy.com", email_verified=True)
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_bounce_1")
        await db.flush()

        events = [{
            "event": "bounce",
            "sg_message_id": "sg_bounce_1",
            "outreach_id": str(prospect.id),
            "type": "bounce",
            "reason": "550 User unknown",
            "timestamp": 1700000000,
        }]
        request = _mock_request(json_data=events)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert email.bounced_at is not None
        assert prospect.email_verified is False
        assert prospect.status == "lost"

    @patch("src.services.deliverability.record_email_event", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_dedupes_duplicate_sendgrid_event(self, mock_verify, mock_signal, mock_record_event, db):
        """Duplicate sg_event_id should be processed once (idempotent webhook handling)."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db, prospect_email="dup@bounce.com")
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_dupe_bounce")
        await db.flush()

        events = [
            {
                "event": "bounce",
                "sg_event_id": "evt_123",
                "sg_message_id": "sg_dupe_bounce",
                "outreach_id": str(prospect.id),
                "type": "bounce",
                "reason": "550 User unknown",
                "timestamp": 1700000000,
            },
            {
                "event": "bounce",
                "sg_event_id": "evt_123",
                "sg_message_id": "sg_dupe_bounce",
                "outreach_id": str(prospect.id),
                "type": "bounce",
                "reason": "550 User unknown",
                "timestamp": 1700000000,
            },
        ]
        request = _mock_request(json_data=events)

        redis = AsyncMock()
        redis.set = AsyncMock(side_effect=[True, None])  # seen once, then duplicate

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=redis):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert email.bounced_at is not None
        assert mock_record_event.await_count == 1

    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_bounce_auto_blacklists_email(self, mock_verify, mock_signal, db):
        """Should auto-blacklist email address on hard bounce."""
        from src.api.sales_engine import email_events_webhook
        from sqlalchemy import select

        prospect = _make_prospect(db, prospect_email="bad@faildomain.com")
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_bounce_bl")
        await db.flush()

        events = [{
            "event": "bounce",
            "sg_message_id": "sg_bounce_bl",
            "outreach_id": str(prospect.id),
            "type": "bounce",
            "reason": "Unknown user",
            "timestamp": 1700000000,
        }]
        request = _mock_request(json_data=events)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            await email_events_webhook(request, db)

        # Check blacklist
        bl_result = await db.execute(
            select(EmailBlacklist).where(EmailBlacklist.value == "bad@faildomain.com")
        )
        bl_entry = bl_result.scalar_one_or_none()
        assert bl_entry is not None
        assert bl_entry.entry_type == "email"

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_processes_deferred_event(self, mock_verify, db):
        """Should mark email as deferred without treating it as a bounce."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db)
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_defer_1")
        await db.flush()

        events = [{
            "event": "deferred",
            "sg_message_id": "sg_defer_1",
            "reason": "Temp failure",
            "timestamp": 1700000000,
        }]
        request = _mock_request(json_data=events)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert email.bounce_type == "deferred"
        assert email.bounced_at is None  # deferred does NOT set bounced_at

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_processes_spamreport_event(self, mock_verify, db):
        """Should mark prospect as unsubscribed on spam report."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db)
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_spam_1")
        await db.flush()

        events = [{
            "event": "spamreport",
            "sg_message_id": "sg_spam_1",
            "outreach_id": str(prospect.id),
            "timestamp": 1700000000,
        }]
        request = _mock_request(json_data=events)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert prospect.email_unsubscribed is True

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_skips_event_when_no_email_record_found(self, mock_verify, db):
        """Should silently skip events that don't match any email record."""
        from src.api.sales_engine import email_events_webhook

        events = [{"event": "open", "sg_message_id": "nonexistent", "timestamp": 1700000000}]
        request = _mock_request(json_data=events)

        result = await email_events_webhook(request, db)
        assert result["status"] == "processed"
        assert result["events"] == 1

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_handles_single_event_dict(self, mock_verify, db):
        """Should handle a single event dict (not wrapped in a list)."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db)
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_single")
        await db.flush()

        event = {"event": "delivered", "sg_message_id": "sg_single", "timestamp": 1700000000}
        request = _mock_request(json_data=event)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert result["events"] == 1

    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_fallback_lookup_by_outreach_id_and_step(self, mock_verify, mock_signal, db):
        """Should find email by outreach_id + step if sg_message_id lookup fails."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db)
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id=None, sequence_step=2)
        await db.flush()

        events = [{
            "event": "delivered",
            "sg_message_id": "",
            "outreach_id": str(prospect.id),
            "step": "2",
            "timestamp": 1700000000,
        }]
        request = _mock_request(json_data=events)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert email.delivered_at is not None

    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_open_event_does_not_mutate_campaign_counter(self, mock_verify, mock_signal, db):
        """Opens should NOT increment denormalized campaign counter (calculated metrics used instead)."""
        from src.api.sales_engine import email_events_webhook

        campaign = _make_campaign(db, total_opened=3)
        await db.flush()
        prospect = _make_prospect(db, campaign_id=campaign.id)
        await db.flush()
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_camp_open")
        await db.flush()

        events = [{
            "event": "open",
            "sg_message_id": "sg_camp_open",
            "outreach_id": str(prospect.id),
            "timestamp": 1700000000,
        }]
        request = _mock_request(json_data=events)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert result["status"] == "processed"
        assert campaign.total_opened == 3  # unchanged - calculated metrics used instead

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_does_not_update_already_set_delivered_at(self, mock_verify, db):
        """Should not overwrite delivered_at if already set."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db)
        await db.flush()
        original_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        email = _make_email(db, prospect.id, sendgrid_message_id="sg_dupe_del")
        email.delivered_at = original_time
        await db.flush()

        events = [{"event": "delivered", "sg_message_id": "sg_dupe_del", "timestamp": 1700000000}]
        request = _mock_request(json_data=events)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            result = await email_events_webhook(request, db)

        assert email.delivered_at == original_time

    @patch("src.api.sales_webhooks._record_email_signal", new_callable=AsyncMock)
    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_protected_domain_not_blacklisted(self, mock_verify, mock_signal, db):
        """Should NOT domain-blacklist protected providers like gmail.com."""
        from src.api.sales_engine import email_events_webhook
        from sqlalchemy import select

        # Create 4 prospects at gmail.com and bounce them all
        for i in range(4):
            p = _make_prospect(db, prospect_email=f"user{i}@gmail.com")
            await db.flush()
            e = _make_email(db, p.id, sendgrid_message_id=f"sg_gmail_bounce_{i}")
            await db.flush()

            events = [{
                "event": "bounce",
                "sg_message_id": f"sg_gmail_bounce_{i}",
                "outreach_id": str(p.id),
                "type": "bounce",
                "reason": "Unknown user",
                "timestamp": 1700000000 + i,
            }]
            request = _mock_request(json_data=events)
            with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
                await email_events_webhook(request, db)

        # Individual emails should be blacklisted
        email_bl = await db.execute(
            select(func.count()).select_from(EmailBlacklist).where(
                and_(
                    EmailBlacklist.entry_type == "email",
                    EmailBlacklist.value.like("%@gmail.com"),
                )
            )
        )
        assert email_bl.scalar() == 4

        # Domain should NOT be blacklisted (protected)
        domain_bl = await db.execute(
            select(EmailBlacklist).where(
                and_(
                    EmailBlacklist.entry_type == "domain",
                    EmailBlacklist.value == "gmail.com",
                )
            )
        )
        assert domain_bl.scalar_one_or_none() is None

    @patch("src.api.sales_webhooks._verify_sendgrid_webhook", new_callable=AsyncMock, return_value=True)
    async def test_deferred_marks_unreachable_not_unsubscribed(self, mock_verify, db):
        """After 3+ deferrals, prospect should be unreachable but NOT unsubscribed."""
        from src.api.sales_engine import email_events_webhook

        prospect = _make_prospect(db, prospect_email="slow@flaky.com")
        await db.flush()

        # Create 3 deferred emails (to reach the threshold)
        for i in range(3):
            e = _make_email(db, prospect.id, sendgrid_message_id=f"sg_defer_{i}")
            e.bounce_type = "deferred"
            await db.flush()

        # Send the 4th deferred event (triggers the check)
        fourth = _make_email(db, prospect.id, sendgrid_message_id="sg_defer_3")
        await db.flush()

        events = [{
            "event": "deferred",
            "sg_message_id": "sg_defer_3",
            "outreach_id": str(prospect.id),
            "reason": "Server busy",
            "timestamp": 1700000000,
        }]
        request = _mock_request(json_data=events)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis")):
            await email_events_webhook(request, db)

        assert prospect.status == "unreachable"
        assert prospect.email_verified is False
        # Should NOT be marked as unsubscribed (they didn't opt out)
        assert prospect.email_unsubscribed is False


# ── Unsubscribe ───────────────────────────────────────────────────────────

class TestUnsubscribe:
    """Tests for GET /api/v1/sales/unsubscribe/{prospect_id}."""

    async def test_unsubscribes_valid_prospect(self, db):
        """Should mark prospect as unsubscribed and return HTML."""
        from src.api.sales_engine import unsubscribe

        prospect = _make_prospect(db)
        await db.flush()

        result = await unsubscribe(str(prospect.id), db)
        assert result.status_code == 200
        assert "unsubscribed" in result.body.decode().lower()
        assert prospect.email_unsubscribed is True
        assert prospect.unsubscribed_at is not None

    async def test_returns_html_for_invalid_uuid(self, db):
        """Should still return the unsubscribe HTML even for invalid UUID."""
        from src.api.sales_engine import unsubscribe

        result = await unsubscribe("not-a-uuid", db)
        assert result.status_code == 200
        assert "unsubscribed" in result.body.decode().lower()

    async def test_returns_html_for_nonexistent_prospect(self, db):
        """Should return HTML even if prospect does not exist."""
        from src.api.sales_engine import unsubscribe

        fake_id = str(uuid.uuid4())
        result = await unsubscribe(fake_id, db)
        assert result.status_code == 200


# ── Sales Config ──────────────────────────────────────────────────────────

class TestGetSalesConfig:
    """Tests for GET /api/v1/sales/config."""

    async def test_returns_existing_config(self, db):
        """Should return config when one exists."""
        from src.api.sales_engine import get_sales_config

        config = _make_config(db, from_email="me@leadlock.com", daily_email_limit=75)
        await db.flush()

        result = await get_sales_config(db, admin=MagicMock())
        assert result["from_email"] == "me@leadlock.com"
        assert result["daily_email_limit"] == 75
        assert result["is_active"] is True

    async def test_creates_default_config_when_none_exists(self, db):
        """Should create and return default config when none exists."""
        from src.api.sales_engine import get_sales_config

        result = await get_sales_config(db, admin=MagicMock())
        assert "id" in result
        assert result["is_active"] is False  # default


class TestUpdateSalesConfig:
    """Tests for PUT /api/v1/sales/config."""

    async def test_updates_allowed_fields(self, db):
        """Should update only allowed fields."""
        from src.api.sales_engine import update_sales_config

        _make_config(db, daily_email_limit=50)
        await db.flush()

        result = await update_sales_config(
            {"daily_email_limit": 100, "is_active": True},
            db,
            admin=MagicMock(),
        )
        assert result["status"] == "updated"

    async def test_creates_config_if_missing(self, db):
        """Should create config if none exists and then update it."""
        from src.api.sales_engine import update_sales_config

        result = await update_sales_config(
            {"daily_email_limit": 30},
            db,
            admin=MagicMock(),
        )
        assert result["status"] == "updated"

    async def test_ignores_unknown_fields(self, db):
        """Should ignore fields not in allowed_fields list."""
        from src.api.sales_engine import update_sales_config

        _make_config(db)
        await db.flush()

        result = await update_sales_config(
            {"unknown_field": "hacker_value"},
            db,
            admin=MagicMock(),
        )
        assert result["status"] == "updated"


# ── Metrics ───────────────────────────────────────────────────────────────

class TestGetSalesMetrics:
    """Tests for GET /api/v1/sales/metrics."""

    async def test_returns_metrics_with_no_data(self, db):
        """Should return zero metrics when database is empty."""
        from src.api.sales_engine import get_sales_metrics

        result = await get_sales_metrics(period="30d", db=db, admin=MagicMock())
        assert result["period"] == "30d"
        assert result["prospects"]["total"] == 0
        assert result["emails"]["sent"] == 0
        assert result["emails"]["open_rate"] == 0

    async def test_returns_metrics_with_data(self, db):
        """Should aggregate metrics from prospect and email data."""
        from src.api.sales_engine import get_sales_metrics

        p1 = _make_prospect(db, status="cold", source="brave", total_cost_usd=0.05)
        p2 = _make_prospect(db, status="demo_scheduled", source="brave", total_cost_usd=0.10, prospect_email="p2@x.com")
        await db.flush()

        _make_email(db, p1.id, direction="outbound")
        _make_email(db, p2.id, direction="outbound", opened_at=datetime.now(timezone.utc))
        _make_email(db, p1.id, direction="inbound")
        await db.flush()

        result = await get_sales_metrics(period="30d", db=db, admin=MagicMock())
        assert result["prospects"]["total"] == 2
        assert result["emails"]["sent"] == 2
        assert result["emails"]["opened"] == 1
        assert result["emails"]["replied"] == 1
        assert result["conversions"]["demos_booked"] == 1

    async def test_parses_period_7d(self, db):
        """Should accept 7d period."""
        from src.api.sales_engine import get_sales_metrics

        result = await get_sales_metrics(period="7d", db=db, admin=MagicMock())
        assert result["period"] == "7d"

    async def test_parses_period_90d(self, db):
        """Should accept 90d period."""
        from src.api.sales_engine import get_sales_metrics

        result = await get_sales_metrics(period="90d", db=db, admin=MagicMock())
        assert result["period"] == "90d"


# ── Scrape Jobs ───────────────────────────────────────────────────────────

class TestListScrapeJobs:
    """Tests for GET /api/v1/sales/scrape-jobs."""

    async def test_returns_empty_list(self, db):
        """Should return empty list when no scrape jobs exist."""
        from src.api.sales_engine import list_scrape_jobs

        result = await list_scrape_jobs(page=1, per_page=20, db=db, admin=MagicMock())
        assert result["jobs"] == []
        assert result["total"] == 0
        assert result["page"] == 1

    async def test_returns_paginated_jobs(self, db):
        """Should return scrape jobs with pagination."""
        from src.api.sales_engine import list_scrape_jobs

        for i in range(5):
            _make_scrape_job(db, trade_type=f"trade_{i}")
        await db.flush()

        result = await list_scrape_jobs(page=1, per_page=3, db=db, admin=MagicMock())
        assert len(result["jobs"]) == 3
        assert result["total"] == 5
        assert result["pages"] == 2

    async def test_serializes_job_fields(self, db):
        """Should include all expected fields in job serialization."""
        from src.api.sales_engine import list_scrape_jobs

        _make_scrape_job(db, trade_type="hvac", city="Austin", state_code="TX")
        await db.flush()

        result = await list_scrape_jobs(page=1, per_page=20, db=db, admin=MagicMock())
        job = result["jobs"][0]
        assert "id" in job
        assert job["trade_type"] == "hvac"
        assert job["city"] == "Austin"
        assert "started_at" in job
        assert "completed_at" in job


class TestTriggerScrapeJob:
    """Tests for POST /api/v1/sales/scrape-jobs."""

    @patch("src.config.get_settings")
    async def test_rejects_when_no_brave_key(self, mock_settings):
        """Should raise 400 when Brave API key is not configured."""
        from src.api.sales_engine import trigger_scrape_job
        from fastapi import HTTPException

        settings = MagicMock()
        settings.brave_api_key = ""
        mock_settings.return_value = settings

        with pytest.raises(HTTPException) as exc_info:
            await trigger_scrape_job(
                {"city": "Austin", "state": "TX", "trade_type": "hvac"},
                admin=MagicMock(),
            )
        assert exc_info.value.status_code == 400

    @patch("src.config.get_settings")
    async def test_rejects_missing_city_state(self, mock_settings):
        """Should raise 400 when city or state is missing."""
        from src.api.sales_engine import trigger_scrape_job
        from fastapi import HTTPException

        settings = MagicMock()
        settings.brave_api_key = "test_key"
        mock_settings.return_value = settings

        with pytest.raises(HTTPException) as exc_info:
            await trigger_scrape_job(
                {"trade_type": "hvac"},
                admin=MagicMock(),
            )
        assert exc_info.value.status_code == 400

    @patch("src.api.sales_scraper._run_scrape_background", new_callable=AsyncMock)
    @patch("src.api.sales_scraper.asyncio")
    @patch("src.config.get_settings")
    async def test_queues_scrape_successfully(self, mock_settings, mock_asyncio, mock_bg):
        """Should return queued status with job_id."""
        from src.api.sales_engine import trigger_scrape_job

        settings = MagicMock()
        settings.brave_api_key = "test_key"
        mock_settings.return_value = settings

        result = await trigger_scrape_job(
            {"city": "Austin", "state": "TX", "trade_type": "hvac"},
            admin=MagicMock(),
        )
        assert result["status"] == "queued"
        assert "job_id" in result


# ── Prospects CRUD ────────────────────────────────────────────────────────

class TestListProspects:
    """Tests for GET /api/v1/sales/prospects."""

    async def test_returns_empty_list(self, db):
        """Should return empty list when no prospects exist."""
        from src.api.sales_engine import list_prospects

        result = await list_prospects(
            page=1, per_page=25, status=None, trade_type=None,
            search=None, campaign_id=None, db=db, admin=MagicMock(),
        )
        assert result["prospects"] == []
        assert result["total"] == 0

    async def test_returns_paginated_prospects(self, db):
        """Should return prospects with pagination."""
        from src.api.sales_engine import list_prospects

        for i in range(10):
            _make_prospect(db, prospect_name=f"Prospect {i}", prospect_email=f"p{i}@x.com")
        await db.flush()

        result = await list_prospects(
            page=1, per_page=5, status=None, trade_type=None,
            search=None, campaign_id=None, db=db, admin=MagicMock(),
        )
        assert len(result["prospects"]) == 5
        assert result["total"] == 10
        assert result["pages"] == 2

    async def test_filters_by_status(self, db):
        """Should filter by status when provided."""
        from src.api.sales_engine import list_prospects

        _make_prospect(db, status="cold", prospect_email="cold@x.com")
        _make_prospect(db, status="demo_scheduled", prospect_email="demo@x.com")
        await db.flush()

        result = await list_prospects(
            page=1, per_page=25, status="cold", trade_type=None,
            search=None, campaign_id=None, db=db, admin=MagicMock(),
        )
        assert result["total"] == 1
        assert result["prospects"][0]["status"] == "cold"

    async def test_filters_by_trade_type(self, db):
        """Should filter by trade_type when provided."""
        from src.api.sales_engine import list_prospects

        _make_prospect(db, prospect_trade_type="hvac", prospect_email="h@x.com")
        _make_prospect(db, prospect_trade_type="plumbing", prospect_email="p@x.com")
        await db.flush()

        result = await list_prospects(
            page=1, per_page=25, status=None, trade_type="plumbing",
            search=None, campaign_id=None, db=db, admin=MagicMock(),
        )
        assert result["total"] == 1

    async def test_filters_by_search_term(self, db):
        """Should search across name, company, email, city."""
        from src.api.sales_engine import list_prospects

        _make_prospect(db, prospect_name="Austin HVAC Pro", prospect_email="a@x.com")
        _make_prospect(db, prospect_name="Dallas Plumber", prospect_email="d@x.com")
        await db.flush()

        result = await list_prospects(
            page=1, per_page=25, status=None, trade_type=None,
            search="Austin", campaign_id=None, db=db, admin=MagicMock(),
        )
        # Match on name or city
        assert result["total"] >= 1

    async def test_filters_by_campaign_id(self, db):
        """Should filter by campaign_id when provided."""
        from src.api.sales_engine import list_prospects

        campaign = _make_campaign(db)
        await db.flush()
        _make_prospect(db, campaign_id=campaign.id, prospect_email="c@x.com")
        _make_prospect(db, prospect_email="no@x.com")
        await db.flush()

        result = await list_prospects(
            page=1, per_page=25, status=None, trade_type=None,
            search=None, campaign_id=str(campaign.id), db=db, admin=MagicMock(),
        )
        assert result["total"] == 1

    async def test_rejects_invalid_campaign_id(self, db):
        """Should raise 400 for invalid campaign_id UUID."""
        from src.api.sales_engine import list_prospects
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await list_prospects(
                page=1, per_page=25, status=None, trade_type=None,
                search=None, campaign_id="not-a-uuid", db=db, admin=MagicMock(),
            )
        assert exc_info.value.status_code == 400


class TestGetProspect:
    """Tests for GET /api/v1/sales/prospects/{prospect_id}."""

    async def test_returns_prospect(self, db):
        """Should return serialized prospect."""
        from src.api.sales_engine import get_prospect

        prospect = _make_prospect(db, prospect_name="HVAC Pros")
        await db.flush()

        result = await get_prospect(str(prospect.id), db, admin=MagicMock())
        assert result["prospect_name"] == "HVAC Pros"
        assert result["id"] == str(prospect.id)

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for non-UUID prospect_id."""
        from src.api.sales_engine import get_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_prospect("invalid", db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_prospect(self, db):
        """Should raise 404 when prospect doesn't exist."""
        from src.api.sales_engine import get_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_prospect(str(uuid.uuid4()), db, admin=MagicMock())
        assert exc_info.value.status_code == 404


class TestUpdateProspect:
    """Tests for PUT /api/v1/sales/prospects/{prospect_id}."""

    async def test_updates_allowed_fields(self, db):
        """Should update prospect fields and return serialized result."""
        from src.api.sales_engine import update_prospect

        prospect = _make_prospect(db, prospect_name="Old Name")
        await db.flush()

        result = await update_prospect(
            str(prospect.id),
            {"prospect_name": "New Name", "status": "demo_scheduled"},
            db,
            admin=MagicMock(),
        )
        assert result["prospect_name"] == "New Name"
        assert result["status"] == "demo_scheduled"

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for non-UUID."""
        from src.api.sales_engine import update_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await update_prospect("bad", {}, db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_prospect(self, db):
        """Should raise 404 when prospect not found."""
        from src.api.sales_engine import update_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await update_prospect(str(uuid.uuid4()), {}, db, admin=MagicMock())
        assert exc_info.value.status_code == 404


class TestDeleteProspect:
    """Tests for DELETE /api/v1/sales/prospects/{prospect_id}."""

    async def test_deletes_prospect(self, db):
        """Should delete the prospect successfully."""
        from src.api.sales_engine import delete_prospect

        prospect = _make_prospect(db)
        await db.flush()

        result = await delete_prospect(str(prospect.id), db, admin=MagicMock())
        assert result["status"] == "deleted"

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for invalid UUID."""
        from src.api.sales_engine import delete_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await delete_prospect("invalid", db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_prospect(self, db):
        """Should raise 404 when prospect not found."""
        from src.api.sales_engine import delete_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await delete_prospect(str(uuid.uuid4()), db, admin=MagicMock())
        assert exc_info.value.status_code == 404


class TestCreateProspect:
    """Tests for POST /api/v1/sales/prospects."""

    async def test_creates_prospect(self, db):
        """Should create and return a new prospect."""
        from src.api.sales_engine import create_prospect

        result = await create_prospect(
            {
                "prospect_name": "New HVAC",
                "prospect_company": "HVAC Inc",
                "prospect_email": "new@hvac.com",
                "prospect_trade_type": "hvac",
                "city": "Austin",
                "state_code": "TX",
            },
            db,
            admin=MagicMock(),
        )
        assert result["prospect_name"] == "New HVAC"
        assert result["source"] == "manual"
        assert result["status"] == "cold"

    async def test_raises_400_when_no_name(self, db):
        """Should raise 400 when prospect_name is empty."""
        from src.api.sales_engine import create_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await create_prospect({"prospect_name": ""}, db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_400_when_name_missing(self, db):
        """Should raise 400 when prospect_name key is absent."""
        from src.api.sales_engine import create_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await create_prospect({"prospect_email": "x@x.com"}, db, admin=MagicMock())
        assert exc_info.value.status_code == 400


# ── Blacklist Prospect ────────────────────────────────────────────────────

class TestBlacklistProspect:
    """Tests for POST /api/v1/sales/prospects/{prospect_id}/blacklist."""

    async def test_blacklists_email_and_domain(self, db):
        """Should add both email and domain to blacklist."""
        from src.api.sales_engine import blacklist_prospect

        prospect = _make_prospect(db, prospect_email="victim@baddomain.com")
        await db.flush()

        result = await blacklist_prospect(str(prospect.id), db, admin=MagicMock())
        assert result["status"] == "blacklisted"
        assert "victim@baddomain.com" in result["entries"]
        assert "baddomain.com" in result["entries"]
        assert prospect.email_unsubscribed is True
        assert prospect.status == "lost"

    async def test_handles_prospect_without_email(self, db):
        """Should return blacklisted with empty entries when no email."""
        from src.api.sales_engine import blacklist_prospect

        prospect = _make_prospect(db, prospect_email=None)
        await db.flush()

        result = await blacklist_prospect(str(prospect.id), db, admin=MagicMock())
        assert result["status"] == "blacklisted"
        assert result["entries"] == []

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for invalid UUID."""
        from src.api.sales_engine import blacklist_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await blacklist_prospect("bad", db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_prospect(self, db):
        """Should raise 404 when prospect not found."""
        from src.api.sales_engine import blacklist_prospect
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await blacklist_prospect(str(uuid.uuid4()), db, admin=MagicMock())
        assert exc_info.value.status_code == 404

    async def test_does_not_duplicate_blacklist_entries(self, db):
        """Should not add duplicate entries when already blacklisted."""
        from src.api.sales_engine import blacklist_prospect

        prospect = _make_prospect(db, prospect_email="already@blocked.com")
        await db.flush()

        # First blacklist call
        result1 = await blacklist_prospect(str(prospect.id), db, admin=MagicMock())
        assert len(result1["entries"]) == 2

        # Reset prospect for second call
        prospect.email_unsubscribed = False
        prospect.status = "cold"
        await db.flush()

        # Second blacklist call should not add duplicates
        result2 = await blacklist_prospect(str(prospect.id), db, admin=MagicMock())
        assert len(result2["entries"]) == 0


# ── Email Thread ──────────────────────────────────────────────────────────

class TestGetProspectEmails:
    """Tests for GET /api/v1/sales/prospects/{prospect_id}/emails."""

    async def test_returns_emails_for_prospect(self, db):
        """Should return all emails sorted by sent_at ascending."""
        from src.api.sales_engine import get_prospect_emails

        prospect = _make_prospect(db)
        await db.flush()

        now = datetime.now(timezone.utc)
        _make_email(db, prospect.id, direction="outbound", sent_at=now - timedelta(hours=2), subject="Intro")
        _make_email(db, prospect.id, direction="inbound", sent_at=now - timedelta(hours=1), subject="Re: Intro")
        _make_email(db, prospect.id, direction="outbound", sent_at=now, subject="Follow-up")
        await db.flush()

        result = await get_prospect_emails(str(prospect.id), db, admin=MagicMock())
        assert result["total"] == 3
        assert result["emails"][0]["subject"] == "Intro"
        assert result["emails"][1]["direction"] == "inbound"

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for invalid UUID."""
        from src.api.sales_engine import get_prospect_emails
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_prospect_emails("bad", db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_prospect(self, db):
        """Should raise 404 when prospect not found."""
        from src.api.sales_engine import get_prospect_emails
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_prospect_emails(str(uuid.uuid4()), db, admin=MagicMock())
        assert exc_info.value.status_code == 404


# ── Worker Status ─────────────────────────────────────────────────────────

class TestGetWorkerStatus:
    """Tests for GET /api/v1/sales/worker-status."""

    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    async def test_returns_worker_health(self, mock_get_redis, db):
        """Should return worker health from Redis heartbeats."""
        from src.api.sales_engine import get_worker_status

        redis_mock = AsyncMock()
        now = datetime.now(timezone.utc)
        recent = now.isoformat()
        stale = (now - timedelta(minutes=20)).isoformat()

        async def get_side_effect(key):
            if "scraper" in key:
                return recent.encode()
            elif "outreach_sequencer" in key:
                return stale.encode()
            return None

        redis_mock.get = AsyncMock(side_effect=get_side_effect)
        mock_get_redis.return_value = redis_mock

        result = await get_worker_status(db=db, admin=MagicMock())
        assert "workers" in result
        assert result["workers"]["scraper"]["health"] == "healthy"
        assert result["workers"]["outreach_sequencer"]["health"] == "warning"
        assert result["workers"]["system_health"]["health"] == "unknown"

    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("Redis down"))
    async def test_handles_redis_failure(self, mock_redis, db):
        """Should return fallback response when Redis is unavailable."""
        from src.api.sales_engine import get_worker_status

        result = await get_worker_status(db=db, admin=MagicMock())
        assert "error" in result


# ── Worker Controls ───────────────────────────────────────────────────────

class TestPauseWorker:
    """Tests for POST /api/v1/sales/workers/{worker_name}/pause."""

    async def test_pauses_valid_worker(self, db):
        """Should set scraper_paused to True."""
        from src.api.sales_engine import pause_worker

        config = _make_config(db, scraper_paused=False)
        await db.flush()

        result = await pause_worker("scraper", db=db, admin=MagicMock())
        assert result["status"] == "paused"
        assert config.scraper_paused is True

    async def test_rejects_unknown_worker(self, db):
        """Should raise 400 for unknown worker name."""
        from src.api.sales_engine import pause_worker
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await pause_worker("nonexistent", db=db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_handles_missing_config_gracefully(self, db):
        """Should not fail if no config exists."""
        from src.api.sales_engine import pause_worker

        result = await pause_worker("scraper", db=db, admin=MagicMock())
        assert result["status"] == "paused"


class TestResumeWorker:
    """Tests for POST /api/v1/sales/workers/{worker_name}/resume."""

    async def test_resumes_valid_worker(self, db):
        """Should set sequencer_paused to False."""
        from src.api.sales_engine import resume_worker

        config = _make_config(db, sequencer_paused=True)
        await db.flush()

        result = await resume_worker("sequencer", db=db, admin=MagicMock())
        assert result["status"] == "resumed"
        assert config.sequencer_paused is False

    async def test_rejects_unknown_worker(self, db):
        """Should raise 400 for unknown worker name."""
        from src.api.sales_engine import resume_worker
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await resume_worker("fake_worker", db=db, admin=MagicMock())
        assert exc_info.value.status_code == 400


# ── Campaigns ─────────────────────────────────────────────────────────────

class TestListCampaigns:
    """Tests for GET /api/v1/sales/campaigns."""

    async def test_returns_empty_list(self, db):
        """Should return empty list when no campaigns exist."""
        from src.api.sales_engine import list_campaigns

        result = await list_campaigns(page=1, per_page=20, db=db, admin=MagicMock())
        assert result["campaigns"] == []
        assert result["total"] == 0

    async def test_returns_campaigns_with_pagination(self, db):
        """Should return campaigns with proper pagination."""
        from src.api.sales_engine import list_campaigns

        for i in range(5):
            _make_campaign(db, name=f"Campaign {i}")
        await db.flush()

        result = await list_campaigns(page=1, per_page=3, db=db, admin=MagicMock())
        assert len(result["campaigns"]) == 3
        assert result["total"] == 5

    async def test_serializes_campaign_fields(self, db):
        """Should include all expected fields."""
        from src.api.sales_engine import list_campaigns

        _make_campaign(db, name="HVAC Q1", target_trades=["hvac"], daily_limit=50)
        await db.flush()

        result = await list_campaigns(page=1, per_page=20, db=db, admin=MagicMock())
        c = result["campaigns"][0]
        assert c["name"] == "HVAC Q1"
        assert c["target_trades"] == ["hvac"]
        assert c["daily_limit"] == 50


class TestCreateCampaign:
    """Tests for POST /api/v1/sales/campaigns."""

    async def test_creates_campaign(self, db):
        """Should create a campaign with draft status."""
        from src.api.sales_engine import create_campaign

        result = await create_campaign(
            {"name": "New Campaign", "target_trades": ["plumbing"], "daily_limit": 30},
            db,
            admin=MagicMock(),
        )
        assert result["status"] == "created"
        assert "id" in result

    async def test_raises_400_when_no_name(self, db):
        """Should raise 400 when name is empty."""
        from src.api.sales_engine import create_campaign
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await create_campaign({"name": ""}, db, admin=MagicMock())
        assert exc_info.value.status_code == 400


class TestUpdateCampaign:
    """Tests for PUT /api/v1/sales/campaigns/{campaign_id}."""

    async def test_updates_campaign(self, db):
        """Should update campaign fields."""
        from src.api.sales_engine import update_campaign

        campaign = _make_campaign(db, name="Old Name")
        await db.flush()

        result = await update_campaign(
            str(campaign.id),
            {"name": "New Name", "daily_limit": 50},
            db,
            admin=MagicMock(),
        )
        assert result["status"] == "updated"
        assert campaign.name == "New Name"

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for invalid UUID."""
        from src.api.sales_engine import update_campaign
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await update_campaign("bad-uuid", {}, db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_campaign(self, db):
        """Should raise 404 when campaign not found."""
        from src.api.sales_engine import update_campaign
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await update_campaign(str(uuid.uuid4()), {}, db, admin=MagicMock())
        assert exc_info.value.status_code == 404


class TestPauseCampaign:
    """Tests for POST /api/v1/sales/campaigns/{campaign_id}/pause."""

    async def test_pauses_campaign(self, db):
        """Should set campaign status to paused."""
        from src.api.sales_engine import pause_campaign

        campaign = _make_campaign(db, status="active")
        await db.flush()

        result = await pause_campaign(str(campaign.id), db, admin=MagicMock())
        assert result["status"] == "paused"
        assert campaign.status == "paused"

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for invalid UUID."""
        from src.api.sales_engine import pause_campaign
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await pause_campaign("nope", db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_campaign(self, db):
        """Should raise 404 when campaign not found."""
        from src.api.sales_engine import pause_campaign
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await pause_campaign(str(uuid.uuid4()), db, admin=MagicMock())
        assert exc_info.value.status_code == 404


class TestResumeCampaign:
    """Tests for POST /api/v1/sales/campaigns/{campaign_id}/resume."""

    async def test_resumes_campaign(self, db):
        """Should set campaign status to active."""
        from src.api.sales_engine import resume_campaign

        campaign = _make_campaign(db, status="paused")
        await db.flush()

        result = await resume_campaign(str(campaign.id), db, admin=MagicMock())
        assert result["status"] == "active"
        assert campaign.status == "active"

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for invalid UUID."""
        from src.api.sales_engine import resume_campaign
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await resume_campaign("nope", db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_campaign(self, db):
        """Should raise 404 when campaign not found."""
        from src.api.sales_engine import resume_campaign
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await resume_campaign(str(uuid.uuid4()), db, admin=MagicMock())
        assert exc_info.value.status_code == 404


# ── Templates ─────────────────────────────────────────────────────────────

class TestListTemplates:
    """Tests for GET /api/v1/sales/templates."""

    async def test_returns_empty_list(self, db):
        """Should return empty list when no templates exist."""
        from src.api.sales_engine import list_templates

        result = await list_templates(db=db, admin=MagicMock())
        assert result["templates"] == []

    async def test_returns_templates(self, db):
        """Should return all templates."""
        from src.api.sales_engine import list_templates

        _make_template(db, name="Template A")
        _make_template(db, name="Template B")
        await db.flush()

        result = await list_templates(db=db, admin=MagicMock())
        assert len(result["templates"]) == 2


class TestCreateTemplate:
    """Tests for POST /api/v1/sales/templates."""

    async def test_creates_template(self, db):
        """Should create an email template."""
        from src.api.sales_engine import create_template

        result = await create_template(
            {"name": "Welcome", "step_type": "first_contact", "subject_template": "Hi {{name}}"},
            db,
            admin=MagicMock(),
        )
        assert result["status"] == "created"
        assert "id" in result

    async def test_raises_400_when_missing_name(self, db):
        """Should raise 400 when name is empty."""
        from src.api.sales_engine import create_template
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await create_template({"name": "", "step_type": "first_contact"}, db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_400_when_missing_step_type(self, db):
        """Should raise 400 when step_type is empty."""
        from src.api.sales_engine import create_template
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await create_template({"name": "Test", "step_type": ""}, db, admin=MagicMock())
        assert exc_info.value.status_code == 400


class TestUpdateTemplate:
    """Tests for PUT /api/v1/sales/templates/{template_id}."""

    async def test_updates_template(self, db):
        """Should update template fields."""
        from src.api.sales_engine import update_template

        template = _make_template(db, name="Old")
        await db.flush()

        result = await update_template(
            str(template.id), {"name": "New"}, db, admin=MagicMock()
        )
        assert result["status"] == "updated"
        assert template.name == "New"

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for invalid UUID."""
        from src.api.sales_engine import update_template
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await update_template("bad", {}, db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_template(self, db):
        """Should raise 404 when template not found."""
        from src.api.sales_engine import update_template
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await update_template(str(uuid.uuid4()), {}, db, admin=MagicMock())
        assert exc_info.value.status_code == 404


class TestDeleteTemplate:
    """Tests for DELETE /api/v1/sales/templates/{template_id}."""

    async def test_deletes_template(self, db):
        """Should delete the template."""
        from src.api.sales_engine import delete_template

        template = _make_template(db)
        await db.flush()

        result = await delete_template(str(template.id), db, admin=MagicMock())
        assert result["status"] == "deleted"

    async def test_raises_400_for_invalid_id(self, db):
        """Should raise 400 for invalid UUID."""
        from src.api.sales_engine import delete_template
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await delete_template("bad", db, admin=MagicMock())
        assert exc_info.value.status_code == 400

    async def test_raises_404_for_missing_template(self, db):
        """Should raise 404 when template not found."""
        from src.api.sales_engine import delete_template
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await delete_template(str(uuid.uuid4()), db, admin=MagicMock())
        assert exc_info.value.status_code == 404


# ── Insights ──────────────────────────────────────────────────────────────

class TestGetInsights:
    """Tests for GET /api/v1/sales/insights."""

    @patch("src.services.learning.get_insights_summary", new_callable=AsyncMock)
    async def test_returns_insights(self, mock_insights, db):
        """Should delegate to get_insights_summary."""
        from src.api.sales_engine import get_insights

        mock_insights.return_value = {"top_trades": ["hvac"]}
        result = await get_insights(db=db, admin=MagicMock())
        assert result == {"top_trades": ["hvac"]}
        mock_insights.assert_called_once()


# ── Bulk Operations ───────────────────────────────────────────────────────

class TestBulkUpdateProspects:
    """Tests for POST /api/v1/sales/prospects/bulk."""

    async def test_bulk_status_change(self, db):
        """Should change status for multiple prospects."""
        from src.api.sales_engine import bulk_update_prospects

        p1 = _make_prospect(db, status="cold", prospect_email="b1@x.com")
        p2 = _make_prospect(db, status="cold", prospect_email="b2@x.com")
        await db.flush()

        result = await bulk_update_prospects(
            {"prospect_ids": [str(p1.id), str(p2.id)], "action": "status:contacted"},
            db,
            admin=MagicMock(),
        )
        assert result["status"] == "completed"
        assert result["updated"] == 2
        assert p1.status == "contacted"
        assert p2.status == "contacted"

    async def test_bulk_delete(self, db):
        """Should delete multiple prospects."""
        from src.api.sales_engine import bulk_update_prospects

        p1 = _make_prospect(db, prospect_email="d1@x.com")
        p2 = _make_prospect(db, prospect_email="d2@x.com")
        await db.flush()

        result = await bulk_update_prospects(
            {"prospect_ids": [str(p1.id), str(p2.id)], "action": "delete"},
            db,
            admin=MagicMock(),
        )
        assert result["updated"] == 2

    async def test_bulk_assign_campaign(self, db):
        """Should assign prospects to a campaign."""
        from src.api.sales_engine import bulk_update_prospects

        campaign = _make_campaign(db)
        await db.flush()
        p1 = _make_prospect(db, prospect_email="c1@x.com")
        await db.flush()

        result = await bulk_update_prospects(
            {
                "prospect_ids": [str(p1.id)],
                "action": f"campaign:{str(campaign.id)}",
            },
            db,
            admin=MagicMock(),
        )
        assert result["updated"] == 1
        assert p1.campaign_id == campaign.id

    async def test_raises_400_when_no_ids_or_action(self, db):
        """Should raise 400 when prospect_ids or action is missing."""
        from src.api.sales_engine import bulk_update_prospects
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await bulk_update_prospects(
                {"prospect_ids": [], "action": "delete"},
                db,
                admin=MagicMock(),
            )
        assert exc_info.value.status_code == 400

    async def test_raises_400_when_too_many_ids(self, db):
        """Should raise 400 when more than 200 prospect IDs."""
        from src.api.sales_engine import bulk_update_prospects
        from fastapi import HTTPException

        ids = [str(uuid.uuid4()) for _ in range(201)]
        with pytest.raises(HTTPException) as exc_info:
            await bulk_update_prospects(
                {"prospect_ids": ids, "action": "delete"},
                db,
                admin=MagicMock(),
            )
        assert exc_info.value.status_code == 400

    async def test_skips_nonexistent_prospects(self, db):
        """Should skip IDs that don't exist without failing."""
        from src.api.sales_engine import bulk_update_prospects

        fake_id = str(uuid.uuid4())
        result = await bulk_update_prospects(
            {"prospect_ids": [fake_id], "action": "status:contacted"},
            db,
            admin=MagicMock(),
        )
        assert result["updated"] == 0


# ── _serialize_prospect ───────────────────────────────────────────────────

class TestSerializeProspect:
    """Tests for the _serialize_prospect helper."""

    def test_serializes_all_fields(self):
        """Should serialize all expected fields."""
        from src.api.sales_engine import _serialize_prospect

        now = datetime.now(timezone.utc)
        prospect = MagicMock()
        prospect.id = uuid.uuid4()
        prospect.prospect_name = "HVAC Pro"
        prospect.prospect_company = "Pro Co"
        prospect.prospect_email = "pro@x.com"
        prospect.prospect_phone = "+15125551234"
        prospect.prospect_trade_type = "hvac"
        prospect.status = "cold"
        prospect.source = "brave"
        prospect.website = "https://hvac.com"
        prospect.google_rating = 4.5
        prospect.review_count = 100
        prospect.address = "123 Main St"
        prospect.city = "Austin"
        prospect.state_code = "TX"
        prospect.email_verified = True
        prospect.email_source = "hunter"
        prospect.outreach_sequence_step = 2
        prospect.total_emails_sent = 3
        prospect.total_cost_usd = 0.15
        prospect.email_unsubscribed = False
        prospect.campaign_id = uuid.uuid4()
        prospect.last_email_sent_at = now
        prospect.last_email_opened_at = now
        prospect.last_email_replied_at = None
        prospect.created_at = now
        prospect.updated_at = now

        result = _serialize_prospect(prospect)
        assert result["prospect_name"] == "HVAC Pro"
        assert result["campaign_id"] == str(prospect.campaign_id)
        assert result["last_email_replied_at"] is None
        assert result["google_rating"] == 4.5

    def test_handles_none_campaign_id(self):
        """Should return None for campaign_id when it is None."""
        from src.api.sales_engine import _serialize_prospect

        prospect = MagicMock()
        prospect.id = uuid.uuid4()
        prospect.campaign_id = None
        prospect.last_email_sent_at = None
        prospect.last_email_opened_at = None
        prospect.last_email_replied_at = None
        prospect.created_at = None
        prospect.updated_at = None

        result = _serialize_prospect(prospect)
        assert result["campaign_id"] is None


# ── _compute_alerts ───────────────────────────────────────────────────────

class TestComputeAlerts:
    """Tests for the _compute_alerts helper."""

    def test_critical_bounce_rate_alert(self):
        """Should generate critical alert when bounce rate > 10%."""
        from src.api.sales_engine import _compute_alerts

        data = {
            "email_pipeline": {"today": {"sent": 100, "bounced": 15}},
            "system": {"workers": {}, "budget": {"pct_used": 50, "alert_threshold": 0.8}, "send_window": {"is_active": True}},
        }
        alerts = _compute_alerts(data)
        bounce_alerts = [a for a in alerts if a["type"] == "bounce_rate"]
        assert len(bounce_alerts) == 1
        assert bounce_alerts[0]["severity"] == "critical"

    def test_warning_bounce_rate_alert(self):
        """Should generate warning when bounce rate > 5% but < 10%."""
        from src.api.sales_engine import _compute_alerts

        data = {
            "email_pipeline": {"today": {"sent": 100, "bounced": 7}},
            "system": {"workers": {}, "budget": {"pct_used": 50, "alert_threshold": 0.8}, "send_window": {"is_active": True}},
        }
        alerts = _compute_alerts(data)
        bounce_alerts = [a for a in alerts if a["type"] == "bounce_rate"]
        assert len(bounce_alerts) == 1
        assert bounce_alerts[0]["severity"] == "warning"

    def test_no_bounce_alert_when_healthy(self):
        """Should not generate bounce alert when rate is low."""
        from src.api.sales_engine import _compute_alerts

        data = {
            "email_pipeline": {"today": {"sent": 100, "bounced": 2}},
            "system": {"workers": {}, "budget": {"pct_used": 50, "alert_threshold": 0.8}, "send_window": {"is_active": True}},
        }
        alerts = _compute_alerts(data)
        bounce_alerts = [a for a in alerts if a["type"] == "bounce_rate"]
        assert len(bounce_alerts) == 0

    def test_worker_unhealthy_alert(self):
        """Should generate critical alert for unhealthy workers."""
        from src.api.sales_engine import _compute_alerts

        data = {
            "email_pipeline": {"today": {"sent": 0, "bounced": 0}},
            "system": {
                "workers": {"scraper": {"health": "unhealthy"}},
                "budget": {"pct_used": 50, "alert_threshold": 0.8},
                "send_window": {"is_active": True},
            },
        }
        alerts = _compute_alerts(data)
        worker_alerts = [a for a in alerts if a["type"] == "worker_down"]
        assert len(worker_alerts) == 1
        assert worker_alerts[0]["severity"] == "critical"

    def test_worker_warning_alert(self):
        """Should generate warning alert for stale workers."""
        from src.api.sales_engine import _compute_alerts

        data = {
            "email_pipeline": {"today": {"sent": 0, "bounced": 0}},
            "system": {
                "workers": {"sequencer": {"health": "warning"}},
                "budget": {"pct_used": 50, "alert_threshold": 0.8},
                "send_window": {"is_active": True},
            },
        }
        alerts = _compute_alerts(data)
        worker_alerts = [a for a in alerts if a["type"] == "worker_stale"]
        assert len(worker_alerts) == 1

    def test_budget_exceeded_alert(self):
        """Should generate critical alert when budget exceeded."""
        from src.api.sales_engine import _compute_alerts

        data = {
            "email_pipeline": {"today": {"sent": 0, "bounced": 0}},
            "system": {
                "workers": {},
                "budget": {"pct_used": 105, "alert_threshold": 0.8},
                "send_window": {"is_active": True},
            },
        }
        alerts = _compute_alerts(data)
        budget_alerts = [a for a in alerts if a["type"] == "budget_exceeded"]
        assert len(budget_alerts) == 1
        assert budget_alerts[0]["severity"] == "critical"

    def test_budget_warning_alert(self):
        """Should generate warning when budget is near threshold."""
        from src.api.sales_engine import _compute_alerts

        data = {
            "email_pipeline": {"today": {"sent": 0, "bounced": 0}},
            "system": {
                "workers": {},
                "budget": {"pct_used": 85, "alert_threshold": 0.8},
                "send_window": {"is_active": True},
            },
        }
        alerts = _compute_alerts(data)
        budget_alerts = [a for a in alerts if a["type"] == "budget_high"]
        assert len(budget_alerts) == 1
        assert budget_alerts[0]["severity"] == "warning"

    def test_send_window_closed_alert(self):
        """Should generate info alert when send window is closed."""
        from src.api.sales_engine import _compute_alerts

        data = {
            "email_pipeline": {"today": {"sent": 0, "bounced": 0}},
            "system": {
                "workers": {},
                "budget": {"pct_used": 50, "alert_threshold": 0.8},
                "send_window": {"is_active": False, "next_open": "2024-06-17T08:00:00"},
            },
        }
        alerts = _compute_alerts(data)
        window_alerts = [a for a in alerts if a["type"] == "send_window_closed"]
        assert len(window_alerts) == 1
        assert window_alerts[0]["severity"] == "info"

    def test_no_alerts_when_everything_healthy(self):
        """Should return empty list when everything is healthy."""
        from src.api.sales_engine import _compute_alerts

        data = {
            "email_pipeline": {"today": {"sent": 100, "bounced": 1}},
            "system": {
                "workers": {"scraper": {"health": "healthy"}},
                "budget": {"pct_used": 30, "alert_threshold": 0.8},
                "send_window": {"is_active": True},
            },
        }
        alerts = _compute_alerts(data)
        assert len(alerts) == 0


# ── _compute_send_window_label ────────────────────────────────────────────

class TestComputeSendWindowLabel:
    """Tests for the _compute_send_window_label helper."""

    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    def test_returns_active_window(self, mock_window):
        """Should return is_active=True when within send window."""
        from src.api.sales_engine import _compute_send_window_label

        config = MagicMock()
        config.send_timezone = "America/Chicago"
        config.send_hours_start = "08:00"
        config.send_hours_end = "18:00"
        config.send_weekdays_only = True

        result = _compute_send_window_label(config)
        assert result["is_active"] is True
        assert result["next_open"] is None
        assert "08:00" in result["hours"]
        assert "Weekdays" in result["label"]

    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=False)
    def test_returns_inactive_with_next_open(self, mock_window):
        """Should return is_active=False with next_open when outside send window."""
        from src.api.sales_engine import _compute_send_window_label

        config = MagicMock()
        config.send_timezone = "America/Chicago"
        config.send_hours_start = "08:00"
        config.send_hours_end = "18:00"
        config.send_weekdays_only = False

        result = _compute_send_window_label(config)
        assert result["is_active"] is False
        assert result["next_open"] is not None

    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=False)
    def test_handles_invalid_timezone(self, mock_window):
        """Should fall back to America/Chicago for invalid timezone."""
        from src.api.sales_engine import _compute_send_window_label

        config = MagicMock()
        config.send_timezone = "Invalid/TZ"
        config.send_hours_start = "08:00"
        config.send_hours_end = "18:00"
        config.send_weekdays_only = True

        # Should not raise
        result = _compute_send_window_label(config)
        assert "is_active" in result

    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    def test_handles_none_timezone(self, mock_window):
        """Should use default when timezone is None."""
        from src.api.sales_engine import _compute_send_window_label

        config = MagicMock()
        config.send_timezone = None
        config.send_hours_start = None
        config.send_hours_end = None
        config.send_weekdays_only = True

        result = _compute_send_window_label(config)
        assert result["is_active"] is True


# ── _build_activity_feed ──────────────────────────────────────────────────

class TestBuildActivityFeed:
    """Tests for the _build_activity_feed helper."""

    async def test_returns_empty_feed(self, db):
        """Should return empty list when no data exists."""
        from src.api.sales_engine import _build_activity_feed

        result = await _build_activity_feed(db, limit=20)
        assert result == []

    async def test_includes_sent_and_reply_activities(self, db):
        """Should include email_sent and email_replied activities."""
        from src.api.sales_engine import _build_activity_feed

        now = datetime.now(timezone.utc)
        prospect = _make_prospect(db)
        await db.flush()

        _make_email(db, prospect.id, direction="outbound", sent_at=now, subject="Hello")
        _make_email(db, prospect.id, direction="inbound", sent_at=now, subject="Re: Hello")
        await db.flush()

        result = await _build_activity_feed(db, limit=20)
        types = {a["type"] for a in result}
        assert "email_sent" in types
        assert "email_replied" in types

    async def test_includes_scrape_completed(self, db):
        """Should include scrape_completed activities."""
        from src.api.sales_engine import _build_activity_feed

        _make_scrape_job(db, status="completed", city="Austin", state_code="TX")
        await db.flush()

        result = await _build_activity_feed(db, limit=20)
        types = {a["type"] for a in result}
        assert "scrape_completed" in types

    async def test_includes_unsubscribed(self, db):
        """Should include unsubscribed activities."""
        from src.api.sales_engine import _build_activity_feed

        _make_prospect(db, unsubscribed_at=datetime.now(timezone.utc))
        await db.flush()

        result = await _build_activity_feed(db, limit=20)
        types = {a["type"] for a in result}
        assert "unsubscribed" in types

    async def test_respects_limit(self, db):
        """Should return at most 'limit' items."""
        from src.api.sales_engine import _build_activity_feed

        now = datetime.now(timezone.utc)
        prospect = _make_prospect(db)
        await db.flush()

        for i in range(10):
            _make_email(db, prospect.id, direction="outbound", sent_at=now - timedelta(minutes=i), subject=f"Email {i}")
        await db.flush()

        result = await _build_activity_feed(db, limit=5)
        assert len(result) <= 5

    async def test_sorts_by_timestamp_descending(self, db):
        """Should sort all activities by timestamp descending."""
        from src.api.sales_engine import _build_activity_feed

        now = datetime.now(timezone.utc)
        prospect = _make_prospect(db)
        await db.flush()

        _make_email(db, prospect.id, direction="outbound", sent_at=now - timedelta(hours=2), subject="Old")
        _make_email(db, prospect.id, direction="outbound", sent_at=now, subject="New")
        await db.flush()

        result = await _build_activity_feed(db, limit=20)
        if len(result) >= 2:
            assert result[0]["timestamp"] >= result[1]["timestamp"]


# ── Command Center ────────────────────────────────────────────────────────

class TestGetCommandCenter:
    """Tests for GET /api/v1/sales/command-center."""

    @patch("src.api.sales_dashboard._build_activity_feed", new_callable=AsyncMock, return_value=[])
    @patch("src.api.sales_dashboard._compute_send_window_label")
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis"))
    async def test_returns_full_response_structure(self, mock_redis, mock_window, mock_feed, db):
        """Should return all expected top-level keys."""
        from src.api.sales_engine import get_command_center

        mock_window.return_value = {
            "is_active": True, "label": "08:00-18:00", "hours": "08:00-18:00",
            "weekdays_only": True, "next_open": None,
        }

        _make_config(db)
        await db.flush()

        result = await get_command_center(db=db, admin=MagicMock())
        assert "system" in result
        assert "email_pipeline" in result
        assert "funnel" in result
        assert "scraper" in result
        assert "sequence_performance" in result
        assert "geo_performance" in result
        assert "recent_emails" in result
        assert "activity" in result
        assert "alerts" in result

    @patch("src.api.sales_dashboard._build_activity_feed", new_callable=AsyncMock, return_value=[])
    @patch("src.api.sales_dashboard._compute_send_window_label")
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis"))
    async def test_handles_no_config(self, mock_redis, mock_window, mock_feed, db):
        """Should handle missing config gracefully."""
        from src.api.sales_engine import get_command_center

        mock_window.return_value = {
            "is_active": False, "label": "Not configured", "hours": "",
            "weekdays_only": True, "next_open": None,
        }

        result = await get_command_center(db=db, admin=MagicMock())
        assert result["system"]["engine_active"] is False

    @patch("src.api.sales_dashboard._build_activity_feed", new_callable=AsyncMock, return_value=[])
    @patch("src.api.sales_dashboard._compute_send_window_label")
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis"))
    async def test_includes_email_pipeline_data(self, mock_redis, mock_window, mock_feed, db):
        """Should include email pipeline metrics (today and 30d)."""
        from src.api.sales_engine import get_command_center

        mock_window.return_value = {
            "is_active": True, "label": "08:00-18:00", "hours": "08:00-18:00",
            "weekdays_only": True, "next_open": None,
        }

        _make_config(db)
        prospect = _make_prospect(db)
        await db.flush()

        _make_email(db, prospect.id, direction="outbound", opened_at=datetime.now(timezone.utc))
        await db.flush()

        result = await get_command_center(db=db, admin=MagicMock())
        assert result["email_pipeline"]["today"]["sent"] >= 1

    @patch("src.api.sales_dashboard._build_activity_feed", new_callable=AsyncMock, return_value=[])
    @patch("src.api.sales_dashboard._compute_send_window_label")
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis"))
    async def test_includes_funnel_data(self, mock_redis, mock_window, mock_feed, db):
        """Should include funnel counts by status."""
        from src.api.sales_engine import get_command_center

        mock_window.return_value = {
            "is_active": True, "label": "08:00-18:00", "hours": "08:00-18:00",
            "weekdays_only": True, "next_open": None,
        }

        _make_config(db)
        _make_prospect(db, status="cold", source="brave", prospect_email="f1@x.com")
        _make_prospect(db, status="demo_scheduled", source="brave", prospect_email="f2@x.com")
        _make_prospect(db, status="won", source="brave", prospect_email="f3@x.com")
        await db.flush()

        result = await get_command_center(db=db, admin=MagicMock())
        assert result["funnel"]["cold"] == 1
        assert result["funnel"]["demo_scheduled"] == 1
        assert result["funnel"]["won"] == 1

    @patch("src.api.sales_dashboard._build_activity_feed", new_callable=AsyncMock, side_effect=Exception("feed error"))
    @patch("src.api.sales_dashboard._compute_send_window_label")
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis"))
    async def test_raises_500_on_unhandled_error(self, mock_redis, mock_window, mock_feed, db):
        """Should raise 500 when an unhandled exception occurs."""
        from src.api.sales_engine import get_command_center
        from fastapi import HTTPException

        mock_window.return_value = {
            "is_active": True, "label": "08:00-18:00", "hours": "08:00-18:00",
            "weekdays_only": True, "next_open": None,
        }

        _make_config(db)
        await db.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_command_center(db=db, admin=MagicMock())
        assert exc_info.value.status_code == 500

    @patch("src.api.sales_dashboard._build_activity_feed", new_callable=AsyncMock, return_value=[])
    @patch("src.api.sales_dashboard._compute_send_window_label")
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    async def test_includes_worker_status_from_redis(self, mock_get_redis, mock_window, mock_feed, db):
        """Should include worker health data from Redis."""
        from src.api.sales_engine import get_command_center

        mock_window.return_value = {
            "is_active": True, "label": "08:00-18:00", "hours": "08:00-18:00",
            "weekdays_only": True, "next_open": None,
        }

        redis_mock = AsyncMock()
        now = datetime.now(timezone.utc)
        redis_mock.get = AsyncMock(return_value=now.isoformat().encode())
        mock_get_redis.return_value = redis_mock

        _make_config(db, scraper_paused=True)
        await db.flush()

        result = await get_command_center(db=db, admin=MagicMock())
        workers = result["system"]["workers"]
        assert "scraper" in workers
        assert workers["scraper"]["health"] == "healthy"
        assert workers["scraper"]["paused"] is True

    @patch("src.api.sales_dashboard._build_activity_feed", new_callable=AsyncMock, return_value=[])
    @patch("src.api.sales_dashboard._compute_send_window_label")
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis"))
    async def test_includes_budget_data(self, mock_redis, mock_window, mock_feed, db):
        """Should include budget usage from config."""
        from src.api.sales_engine import get_command_center

        mock_window.return_value = {
            "is_active": True, "label": "08:00-18:00", "hours": "08:00-18:00",
            "weekdays_only": True, "next_open": None,
        }

        _make_config(db, monthly_budget_usd=200.0, budget_alert_threshold=0.8)
        await db.flush()

        result = await get_command_center(db=db, admin=MagicMock())
        budget = result["system"]["budget"]
        assert budget["monthly_limit"] == 200.0
        assert budget["alert_threshold"] == 0.8

    @patch("src.api.sales_dashboard._build_activity_feed", new_callable=AsyncMock, return_value=[])
    @patch("src.api.sales_dashboard._compute_send_window_label")
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("no redis"))
    async def test_includes_scraper_stats(self, mock_redis, mock_window, mock_feed, db):
        """Should include scraper stats (today's new and dupes)."""
        from src.api.sales_engine import get_command_center

        mock_window.return_value = {
            "is_active": True, "label": "08:00-18:00", "hours": "08:00-18:00",
            "weekdays_only": True, "next_open": None,
        }

        _make_config(db, target_locations=[{"city": "Austin", "state": "TX"}])
        _make_scrape_job(db, new_prospects_created=10, duplicates_skipped=5)
        _make_prospect(db, source="brave", prospect_email="s@x.com")
        await db.flush()

        result = await get_command_center(db=db, admin=MagicMock())
        assert result["scraper"]["total_prospects"] >= 1
        assert result["scraper"]["locations"] == [{"city": "Austin", "state": "TX"}]


# ── _run_scrape_background ────────────────────────────────────────────────

class TestRunScrapeBackground:
    """Tests for the _run_scrape_background helper."""

    @patch("src.utils.email_validation.validate_email", new_callable=AsyncMock, return_value={"valid": True})
    @patch("src.services.enrichment.enrich_prospect_email", new_callable=AsyncMock, return_value={"email": "test@biz.com", "source": "website_scrape", "verified": True})
    @patch("src.services.phone_validation.normalize_phone", return_value="+15125559999")
    @patch("src.services.scraping.parse_address_components", return_value={"city": "Austin", "state": "TX", "zip": "78701"})
    @patch("src.services.scraping.search_local_businesses", new_callable=AsyncMock)
    @patch("src.workers.scraper.get_query_variants", return_value=["hvac repair", "hvac service"])
    @patch("src.workers.scraper.get_next_variant_and_offset", new_callable=AsyncMock, return_value=(0, 0))
    @patch("src.config.get_settings")
    @patch("src.api.sales_scraper.async_session_factory")
    async def test_successful_scrape(
        self, mock_session_factory, mock_settings, mock_variant, mock_variants,
        mock_search, mock_parse, mock_phone, mock_enrich, mock_validate,
    ):
        """Should create prospects from search results."""
        from src.api.sales_engine import _run_scrape_background

        settings = MagicMock()
        settings.brave_api_key = "test_key"
        mock_settings.return_value = settings

        mock_search.return_value = {
            "cost_usd": 0.01,
            "results": [
                {
                    "place_id": "place_1",
                    "name": "Test HVAC",
                    "phone": "+15125559999",
                    "address": "123 Main St, Austin, TX 78701",
                    "website": "https://test-hvac.com",
                    "rating": 4.5,
                    "reviews": 50,
                },
            ],
        }

        # Mock async context manager for session
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        # Make execute return no existing records (not a duplicate)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_cm

        job_id = str(uuid.uuid4())
        await _run_scrape_background(job_id, "Austin", "TX", "hvac")

        mock_db.commit.assert_called_once()
        # At least the job + 1 prospect should have been added
        assert mock_db.add.call_count >= 2

    @patch("src.services.scraping.search_local_businesses", new_callable=AsyncMock, side_effect=Exception("API error"))
    @patch("src.workers.scraper.get_query_variants", return_value=["hvac repair"])
    @patch("src.workers.scraper.get_next_variant_and_offset", new_callable=AsyncMock, return_value=(0, 0))
    @patch("src.config.get_settings")
    @patch("src.api.sales_scraper.async_session_factory")
    async def test_handles_search_failure(
        self, mock_session_factory, mock_settings, mock_variant, mock_variants, mock_search,
    ):
        """Should mark job as failed when search raises an exception."""
        from src.api.sales_engine import _run_scrape_background

        settings = MagicMock()
        settings.brave_api_key = "test_key"
        mock_settings.return_value = settings

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_cm

        job_id = str(uuid.uuid4())
        await _run_scrape_background(job_id, "Austin", "TX", "hvac")

        # Should still commit (with failed status)
        mock_db.commit.assert_called_once()

    @patch("src.services.scraping.search_local_businesses", new_callable=AsyncMock)
    @patch("src.workers.scraper.get_query_variants", return_value=["hvac repair"])
    @patch("src.workers.scraper.get_next_variant_and_offset", new_callable=AsyncMock, return_value=(-1, -1))
    @patch("src.config.get_settings")
    @patch("src.api.sales_scraper.async_session_factory")
    async def test_resets_to_zero_when_variants_exhausted(
        self, mock_session_factory, mock_settings, mock_variant, mock_variants, mock_search,
    ):
        """Should fall back to variant 0, offset 0 when all variants exhausted."""
        from src.api.sales_engine import _run_scrape_background

        settings = MagicMock()
        settings.brave_api_key = "test_key"
        mock_settings.return_value = settings

        mock_search.return_value = {"cost_usd": 0.0, "results": []}

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_cm

        job_id = str(uuid.uuid4())
        await _run_scrape_background(job_id, "Austin", "TX", "hvac")

        mock_db.commit.assert_called_once()
