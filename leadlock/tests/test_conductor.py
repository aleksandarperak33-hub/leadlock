"""
Conductor tests - the central orchestrator for the entire lead pipeline.
Tests handle_new_lead, handle_inbound_reply, and _handle_opt_out flows.
All external services (SMS, AI, Redis, DB) are mocked.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from src.agents.conductor import (
    handle_new_lead,
    handle_inbound_reply,
    _handle_opt_out,
    VALID_TRANSITIONS,
)
from src.schemas.lead_envelope import LeadEnvelope, NormalizedLead, LeadMetadata


# --- Helpers ---

def _make_envelope(
    phone="+15125559876",
    first_name="John",
    source="website",
    client_id=None,
    service_type="AC Repair",
    problem_description="AC not cooling",
    inbound_message=None,
    state_code="TX",
):
    """Create a LeadEnvelope for testing."""
    return LeadEnvelope(
        source=source,
        client_id=client_id or str(uuid.uuid4()),
        lead=NormalizedLead(
            phone=phone,
            first_name=first_name,
            service_type=service_type,
            problem_description=problem_description,
            state_code=state_code,
        ),
        metadata=LeadMetadata(),
        inbound_message=inbound_message,
    )


def _make_client(client_id=None, tier="pro", config=None):
    """Create a mock Client object."""
    client = MagicMock()
    client.id = client_id or uuid.uuid4()
    client.business_name = "Austin HVAC"
    client.trade_type = "hvac"
    client.tier = tier
    client.twilio_phone = "+15125551234"
    client.twilio_messaging_service_sid = "MG_test_123"
    client.config = config or {
        "persona": {"rep_name": "Sarah", "tone": "friendly_professional"},
        "services": {"primary": ["AC Repair"], "secondary": [], "do_not_quote": []},
        "emergency_keywords": [],
        "hours": {"business": {"start": "08:00", "end": "18:00", "days": ["mon", "tue", "wed", "thu", "fri"]}},
        "scheduling": {"slot_duration_minutes": 120, "buffer_minutes": 30, "max_daily_bookings": 8},
        "team": [{"name": "Mike", "specialty": ["hvac_repair"], "active": True}],
        "service_area": {"center": {"lat": 30.2672, "lng": -97.7431}, "radius_miles": 35},
    }
    return client


def _make_lead(lead_id=None, state="qualifying", score=50):
    """Create a mock Lead object."""
    lead = MagicMock()
    lead.id = lead_id or uuid.uuid4()
    lead.phone = "+15125559876"
    lead.first_name = "John"
    lead.state = state
    lead.state_code = "TX"
    lead.is_emergency = False
    lead.emergency_type = None
    lead.urgency = "flexible"
    lead.score = score
    lead.consent_id = uuid.uuid4()
    lead.service_type = "AC Repair"
    lead.qualification_data = {}
    lead.total_messages_received = 1
    lead.total_messages_sent = 1
    lead.total_sms_cost_usd = 0.01
    lead.total_ai_cost_usd = 0.0
    lead.conversation_turn = 1
    lead.conversations = []
    lead.last_agent_response = None
    lead.previous_state = None
    lead.current_agent = "qualify"
    return lead


def _make_consent(opted_out=False):
    """Create a mock ConsentRecord."""
    consent = MagicMock()
    consent.id = uuid.uuid4()
    consent.opted_out = opted_out
    consent.consent_type = "pec"
    return consent


def _sms_result():
    """Standard successful SMS result."""
    return {
        "sid": "SM_test_123",
        "status": "sent",
        "provider": "twilio",
        "segments": 1,
        "cost_usd": 0.0079,
        "error": None,
    }


# --- handle_new_lead tests ---

class TestHandleNewLead:
    """Test the new lead entry point."""

    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_invalid_phone_returns_error(self, mock_normalize, mock_dedup):
        """Invalid phone number should return status 'invalid_phone'."""
        mock_normalize.return_value = None
        db = AsyncMock()

        envelope = _make_envelope(phone="invalid")
        result = await handle_new_lead(db, envelope)

        assert result["status"] == "invalid_phone"
        assert result["lead_id"] is None

    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_duplicate_lead_rejected(self, mock_normalize, mock_dedup):
        """Duplicate lead should return status 'duplicate_acknowledged'."""
        mock_normalize.return_value = "+15125559876"
        mock_dedup.return_value = True
        db = AsyncMock()

        envelope = _make_envelope()
        result = await handle_new_lead(db, envelope)

        assert result["status"] == "duplicate_acknowledged"
        assert result["lead_id"] is None

    @patch("src.agents.conductor.needs_ai_disclosure", return_value=False)
    @patch("src.services.compliance.check_content_compliance")
    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_intake", new_callable=AsyncMock)
    @patch("src.agents.conductor.get_monthly_lead_limit")
    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_successful_new_lead(
        self, mock_normalize, mock_dedup, mock_limit, mock_intake, mock_sms,
        mock_compliance, mock_content, mock_ai_disc,
    ):
        """Successful new lead should send SMS and return intake_sent."""
        mock_normalize.return_value = "+15125559876"
        mock_dedup.return_value = False
        mock_limit.return_value = None  # Unlimited

        # Compliance checks pass
        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_content.return_value = MagicMock(__bool__=lambda s: True)

        # Mock intake response
        intake_result = MagicMock()
        intake_result.message = "Hi John! Sarah from Austin HVAC here. Reply STOP to opt out."
        intake_result.template_id = "standard_A"
        intake_result.is_emergency = False
        mock_intake.return_value = intake_result

        mock_sms.return_value = _sms_result()

        # Mock DB - db.add is sync, so use MagicMock
        client = _make_client()
        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=client)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        # Mock the prior opt-out query
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_execute_result)

        envelope = _make_envelope(client_id=str(client.id))
        result = await handle_new_lead(db, envelope)

        assert result["status"] == "intake_sent"
        assert result["lead_id"] is not None
        mock_sms.assert_called_once()

    @patch("src.agents.conductor.get_monthly_lead_limit")
    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_client_not_found(self, mock_normalize, mock_dedup, mock_limit):
        """Missing client should return client_not_found."""
        mock_normalize.return_value = "+15125559876"
        mock_dedup.return_value = False

        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        envelope = _make_envelope()
        result = await handle_new_lead(db, envelope)

        assert result["status"] == "client_not_found"

    @patch("src.agents.conductor.get_monthly_lead_limit")
    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_monthly_lead_limit_enforced(
        self, mock_normalize, mock_dedup, mock_limit
    ):
        """Starter tier at monthly lead limit should be rejected."""
        mock_normalize.return_value = "+15125559876"
        mock_dedup.return_value = False
        mock_limit.return_value = 200  # Starter limit

        client = _make_client(tier="starter")
        db = AsyncMock()
        db.get = AsyncMock(return_value=client)

        # Return count >= limit
        mock_scalar = MagicMock()
        mock_scalar.scalar.return_value = 200
        db.execute = AsyncMock(return_value=mock_scalar)

        envelope = _make_envelope(client_id=str(client.id))
        result = await handle_new_lead(db, envelope)

        assert result["status"] == "monthly_lead_limit_reached"


# --- handle_inbound_reply tests ---

class TestHandleInboundReply:
    """Test inbound reply routing and opt-out handling."""

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.lead_lock")
    @patch("src.agents.conductor.process_qualify", new_callable=AsyncMock)
    @patch("src.config.get_settings")
    async def test_reply_routes_to_qualify(
        self, mock_settings, mock_qualify, mock_lock, mock_sms, mock_compliance
    ):
        """Reply during qualifying state should route to qualify agent."""
        # Mock settings
        mock_settings.return_value.max_conversation_turns = 10

        # Setup qualify result
        qualify_result = MagicMock()
        qualify_result.message = "Great! What type of service do you need?"
        qualify_result.qualification = None
        qualify_result.score_adjustment = 5
        qualify_result.next_action = "continue_qualifying"
        qualify_result.ai_cost_usd = 0.001
        qualify_result.ai_latency_ms = 200
        mock_qualify.return_value = qualify_result

        # Mock lock as async context manager
        mock_lock.return_value.__aenter__ = AsyncMock()
        mock_lock.return_value.__aexit__ = AsyncMock()

        # Compliance passes
        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)

        mock_sms.return_value = _sms_result()

        lead = _make_lead(state="qualifying")
        client = _make_client()
        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()

        result = await handle_inbound_reply(db, lead, client, "I need AC repair")

        assert result["lead_id"] == str(lead.id)
        mock_sms.assert_called_once()

    async def test_stop_keyword_triggers_opt_out(self):
        """STOP keyword should immediately trigger opt-out flow."""
        lead = _make_lead(state="qualifying")
        client = _make_client()
        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()
        db.execute = AsyncMock()

        result = await handle_inbound_reply(db, lead, client, "STOP")

        assert result["status"] == "opted_out"
        assert lead.state == "opted_out"

    async def test_unsubscribe_triggers_opt_out(self):
        """'unsubscribe' should trigger opt-out."""
        lead = _make_lead(state="intake_sent")
        client = _make_client()
        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()
        db.execute = AsyncMock()

        result = await handle_inbound_reply(db, lead, client, "unsubscribe")

        assert result["status"] == "opted_out"

    @patch("src.agents.conductor.lead_lock")
    async def test_lock_timeout_returns_status(self, mock_lock):
        """Lock timeout should return lock_timeout status."""
        from src.utils.locks import LockTimeoutError
        mock_lock.return_value.__aenter__ = AsyncMock(side_effect=LockTimeoutError("timeout"))

        lead = _make_lead()
        client = _make_client()
        db = AsyncMock()

        result = await handle_inbound_reply(db, lead, client, "Hello")

        assert result["status"] == "lock_timeout"


# --- _handle_opt_out tests ---

class TestHandleOptOut:
    """Test the opt-out flow."""

    async def test_opt_out_sets_state(self):
        """Opt-out should set lead state to 'opted_out'."""
        lead = _make_lead(state="qualifying")
        client = _make_client()
        consent = _make_consent()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=consent)
        db.commit = AsyncMock()
        db.execute = AsyncMock()

        from src.utils.metrics import Timer
        timer = Timer().start()

        result = await _handle_opt_out(db, lead, client, "STOP", timer)

        assert result["status"] == "opted_out"
        assert lead.state == "opted_out"
        assert lead.current_agent is None

    async def test_opt_out_updates_consent(self):
        """Opt-out should mark consent record as opted out."""
        lead = _make_lead(state="booking")
        client = _make_client()
        consent = _make_consent()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=consent)
        db.commit = AsyncMock()
        db.execute = AsyncMock()

        from src.utils.metrics import Timer
        timer = Timer().start()

        await _handle_opt_out(db, lead, client, "STOP", timer)

        assert consent.opted_out is True
        assert consent.opt_out_method == "sms_stop"
        assert consent.is_active is False

    async def test_opt_out_cancels_pending_followups(self):
        """Opt-out should cancel all pending follow-up tasks."""
        lead = _make_lead(state="cold")
        client = _make_client()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()
        db.execute = AsyncMock()

        from src.utils.metrics import Timer
        timer = Timer().start()

        await _handle_opt_out(db, lead, client, "leave me alone", timer)

        # Verify db.execute was called (for the FollowupTask update query)
        db.execute.assert_called()

    async def test_opt_out_records_previous_state(self):
        """Opt-out should save the previous state."""
        lead = _make_lead(state="qualified")
        client = _make_client()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()
        db.execute = AsyncMock()

        from src.utils.metrics import Timer
        timer = Timer().start()

        await _handle_opt_out(db, lead, client, "STOP", timer)

        assert lead.previous_state == "qualified"


# --- State machine tests ---

class TestStateTransitions:
    """Verify the state machine transition rules."""

    def test_all_states_have_opted_out_transition(self):
        """Every non-terminal state should allow transition to opted_out."""
        for state, transitions in VALID_TRANSITIONS.items():
            if state != "opted_out":
                assert "opted_out" in transitions, (
                    f"State '{state}' is missing 'opted_out' transition"
                )

    def test_opted_out_is_terminal(self):
        """opted_out should have no outgoing transitions."""
        assert VALID_TRANSITIONS["opted_out"] == []

    def test_new_transitions_to_intake_sent(self):
        assert "intake_sent" in VALID_TRANSITIONS["new"]

    def test_qualifying_can_become_qualified(self):
        assert "qualified" in VALID_TRANSITIONS["qualifying"]

    def test_cold_can_re_engage(self):
        assert "qualifying" in VALID_TRANSITIONS["cold"]
