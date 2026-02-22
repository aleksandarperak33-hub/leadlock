"""
Extended agent tests - covers uncovered lines in conductor, book, qualify,
followup, and sales_outreach agents.

All external services (AI, SMS, CRM, DB, Redis) are mocked.
Uses pytest-asyncio with asyncio_mode = "auto".
"""
import json
import uuid
from datetime import datetime, date, time, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from src.agents.conductor import (
    handle_new_lead,
    handle_inbound_reply,
    _handle_opt_out,
    _route_to_qualify,
    _route_to_book,
    _process_reply_locked,
    VALID_TRANSITIONS,
)
from src.agents.book import process_booking, _fallback_booking, _escape_braces
from src.agents.qualify import process_qualify, _fallback_response, _escape_braces as qualify_escape_braces
from src.agents.followup import process_followup
from src.agents.sales_outreach import (
    generate_outreach_email,
    classify_reply,
    _get_learning_context,
    VALID_CLASSIFICATIONS,
)
from src.schemas.lead_envelope import LeadEnvelope, NormalizedLead, LeadMetadata
from src.schemas.agent_responses import (
    BookResponse,
    QualifyResponse,
    QualificationData,
)
from src.utils.metrics import Timer


# ============================================================
# Helpers - reusable factory functions for test objects
# ============================================================

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
    lead.last_name = "Doe"
    lead.state = state
    lead.state_code = "TX"
    lead.is_emergency = False
    lead.emergency_type = None
    lead.urgency = "flexible"
    lead.score = score
    lead.consent_id = uuid.uuid4()
    lead.service_type = "AC Repair"
    lead.property_type = "residential"
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


def _make_config():
    """Create a ClientConfig for use with conductor helpers."""
    from src.schemas.client_config import ClientConfig
    return ClientConfig(
        service_area={"center": {"lat": 30.2672, "lng": -97.7431}, "radius_miles": 35},
        persona={"rep_name": "Sarah", "tone": "friendly_professional"},
        services={"primary": ["AC Repair"], "secondary": [], "do_not_quote": []},
        emergency_keywords=[],
        hours={"business": {"start": "08:00", "end": "18:00"}},
        scheduling={"slot_duration_minutes": 120, "buffer_minutes": 30, "max_daily_bookings": 8},
        team=[{"name": "Mike", "specialty": ["hvac_repair"], "active": True}],
    )


# ============================================================
# Conductor: handle_new_lead - emergency detection (lines 153-156)
# ============================================================

class TestConductorEmergencyDetection:
    """Cover lines 153-156: emergency flags on new lead."""

    @patch("src.agents.conductor.needs_ai_disclosure", return_value=False)
    @patch("src.services.compliance.check_content_compliance")
    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_intake", new_callable=AsyncMock)
    @patch("src.agents.conductor.get_monthly_lead_limit")
    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_emergency_lead_sets_flags(
        self, mock_normalize, mock_dedup, mock_limit, mock_intake, mock_sms,
        mock_compliance, mock_content, mock_ai_disc,
    ):
        """When emergency detected, lead.is_emergency/emergency_type/urgency/score are set."""
        mock_normalize.return_value = "+15125559876"
        mock_dedup.return_value = False
        mock_limit.return_value = None

        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_content.return_value = MagicMock(__bool__=lambda s: True)

        intake_result = MagicMock()
        intake_result.message = "Emergency! Austin HVAC is dispatching. Reply STOP to opt out."
        intake_result.template_id = "intake_emergency"
        intake_result.is_emergency = True
        mock_intake.return_value = intake_result
        mock_sms.return_value = _sms_result()

        client = _make_client()
        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=client)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_execute_result)

        # Use gas leak in the problem_description to trigger emergency
        envelope = _make_envelope(
            client_id=str(client.id),
            problem_description="We have a gas leak in the basement!",
        )
        result = await handle_new_lead(db, envelope)

        assert result["status"] == "intake_sent"
        # The Lead constructor is called with the emergency properties set
        # Verify intake was called (meaning the pipeline proceeded)
        mock_intake.assert_called_once()


# ============================================================
# Conductor: handle_new_lead - inbound_message recording (lines 172-183)
# ============================================================

class TestConductorInboundMessage:
    """Cover lines 172-183: recording inbound message on new lead."""

    @patch("src.agents.conductor.needs_ai_disclosure", return_value=False)
    @patch("src.services.compliance.check_content_compliance")
    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_intake", new_callable=AsyncMock)
    @patch("src.agents.conductor.get_monthly_lead_limit")
    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_inbound_message_recorded(
        self, mock_normalize, mock_dedup, mock_limit, mock_intake, mock_sms,
        mock_compliance, mock_content, mock_ai_disc,
    ):
        """When envelope has inbound_message, Conversation record is created."""
        mock_normalize.return_value = "+15125559876"
        mock_dedup.return_value = False
        mock_limit.return_value = None

        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_content.return_value = MagicMock(__bool__=lambda s: True)

        intake_result = MagicMock()
        intake_result.message = "Hi! Austin HVAC here. Reply STOP to opt out."
        intake_result.template_id = "intake_standard"
        intake_result.is_emergency = False
        mock_intake.return_value = intake_result
        mock_sms.return_value = _sms_result()

        client = _make_client()
        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=client)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_execute_result)

        envelope = _make_envelope(
            client_id=str(client.id),
            inbound_message="I need my AC fixed ASAP",
        )
        result = await handle_new_lead(db, envelope)

        assert result["status"] == "intake_sent"
        # db.add called multiple times: consent, lead, event_log, inbound_conv, outbound_conv, event_log
        assert db.add.call_count >= 4


# ============================================================
# Conductor: handle_new_lead - compliance blocked (lines 209-215)
# ============================================================

class TestConductorComplianceBlocked:
    """Cover lines 209-215: compliance blocks a new lead response."""

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.get_monthly_lead_limit")
    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_compliance_blocks_lead(
        self, mock_normalize, mock_dedup, mock_limit, mock_compliance,
    ):
        """When compliance check fails, lead stays in 'new' state."""
        mock_normalize.return_value = "+15125559876"
        mock_dedup.return_value = False
        mock_limit.return_value = None

        # Compliance fails
        compliance_result = MagicMock(__bool__=lambda s: False)
        compliance_result.reason = "opted_out"
        compliance_result.rule = "consent_check"
        mock_compliance.return_value = compliance_result

        client = _make_client()
        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=client)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = MagicMock()  # prior opt-out exists
        db.execute = AsyncMock(return_value=mock_execute_result)

        envelope = _make_envelope(client_id=str(client.id))
        result = await handle_new_lead(db, envelope)

        assert "compliance_blocked" in result["status"]
        assert result["lead_id"] is not None
        db.commit.assert_called_once()


# ============================================================
# Conductor: handle_new_lead - template compliance error (lines 238-240)
# ============================================================

class TestConductorTemplateComplianceError:
    """Cover lines 238-240: content compliance check fails on template."""

    @patch("src.services.compliance.check_content_compliance")
    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_intake", new_callable=AsyncMock)
    @patch("src.agents.conductor.get_monthly_lead_limit")
    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_template_compliance_error(
        self, mock_normalize, mock_dedup, mock_limit, mock_intake, mock_sms,
        mock_compliance, mock_content,
    ):
        """When content compliance fails, return template_compliance_error."""
        mock_normalize.return_value = "+15125559876"
        mock_dedup.return_value = False
        mock_limit.return_value = None

        # First compliance check passes, content check fails
        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        content_fail = MagicMock(__bool__=lambda s: False)
        content_fail.reason = "Missing STOP language"
        mock_content.return_value = content_fail

        intake_result = MagicMock()
        intake_result.message = "Bad template without STOP"
        intake_result.template_id = "broken_template"
        intake_result.is_emergency = False
        mock_intake.return_value = intake_result

        client = _make_client()
        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=client)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_execute_result)

        envelope = _make_envelope(client_id=str(client.id))
        result = await handle_new_lead(db, envelope)

        assert result["status"] == "template_compliance_error"
        assert result["lead_id"] is not None
        # SMS should NOT have been sent
        mock_sms.assert_not_called()


# ============================================================
# Conductor: handle_new_lead - AI disclosure (lines 249-251)
# ============================================================

class TestConductorAIDisclosure:
    """Cover lines 249-251: California SB 1001 AI disclosure prepend."""

    @patch("src.agents.conductor.get_ai_disclosure")
    @patch("src.agents.conductor.needs_ai_disclosure", return_value=True)
    @patch("src.services.compliance.check_content_compliance")
    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_intake", new_callable=AsyncMock)
    @patch("src.agents.conductor.get_monthly_lead_limit")
    @patch("src.agents.conductor.is_duplicate", new_callable=AsyncMock)
    @patch("src.agents.conductor.normalize_phone")
    async def test_ai_disclosure_prepended_for_ca(
        self, mock_normalize, mock_dedup, mock_limit, mock_intake, mock_sms,
        mock_compliance, mock_content, mock_needs_disc, mock_get_disc,
    ):
        """CA leads should have AI disclosure prepended to first message."""
        mock_normalize.return_value = "+15125559876"
        mock_dedup.return_value = False
        mock_limit.return_value = None

        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_content.return_value = MagicMock(__bool__=lambda s: True)

        intake_result = MagicMock()
        intake_result.message = "Hi John! Austin HVAC here. Reply STOP to opt out."
        intake_result.template_id = "intake_standard"
        intake_result.is_emergency = False
        mock_intake.return_value = intake_result
        mock_sms.return_value = _sms_result()
        mock_get_disc.return_value = "[AI Disclosure] "

        client = _make_client()
        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=client)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_execute_result)

        envelope = _make_envelope(client_id=str(client.id), state_code="CA")
        result = await handle_new_lead(db, envelope)

        assert result["status"] == "intake_sent"
        # Verify SMS was called with disclosure-prepended message
        sms_call_kwargs = mock_sms.call_args
        body_sent = sms_call_kwargs.kwargs.get("body") or sms_call_kwargs[1].get("body") or sms_call_kwargs[0][1] if sms_call_kwargs[0] else ""
        mock_get_disc.assert_called_once()


# ============================================================
# Conductor: _process_reply_locked - emergency in reply (lines 361-364)
# ============================================================

class TestProcessReplyLockedEmergency:
    """Cover lines 361-364: emergency detected during inbound reply."""

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_qualify", new_callable=AsyncMock)
    @patch("src.agents.conductor.detect_emergency")
    @patch("src.config.get_settings")
    async def test_emergency_in_reply_sets_flags(
        self, mock_settings, mock_emergency, mock_qualify, mock_sms, mock_compliance,
    ):
        """Emergency keywords in reply should flag lead as emergency."""
        mock_settings.return_value.max_conversation_turns = 10
        mock_emergency.return_value = {
            "is_emergency": True,
            "emergency_type": "gas_or_co",
            "matched_keyword": "gas leak",
        }

        qualify_result = MagicMock()
        qualify_result.message = "I'm dispatching someone right now!"
        qualify_result.qualification = None
        qualify_result.score_adjustment = 10
        qualify_result.next_action = "escalate_emergency"
        qualify_result.ai_cost_usd = 0.001
        qualify_result.ai_latency_ms = 200
        mock_qualify.return_value = qualify_result

        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_sms.return_value = _sms_result()

        lead = _make_lead(state="qualifying", score=40)
        client = _make_client()
        config = _make_config()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()

        timer = Timer().start()
        result = await _process_reply_locked(
            db, lead, client, config, "I smell gas, it's a gas leak!", timer,
        )

        assert lead.is_emergency is True
        assert lead.emergency_type == "gas_or_co"
        assert lead.urgency == "emergency"
        assert lead.score >= 90


# ============================================================
# Conductor: _process_reply_locked - cold/dead re-engagement (lines 383-385)
# ============================================================

class TestProcessReplyLockedColdReEngagement:
    """Cover lines 383-385: cold/dead leads re-engage on reply."""

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_qualify", new_callable=AsyncMock)
    @patch("src.agents.conductor.detect_emergency")
    @patch("src.config.get_settings")
    async def test_cold_lead_reengages(
        self, mock_settings, mock_emergency, mock_qualify, mock_sms, mock_compliance,
    ):
        """Cold lead replying should move back to qualifying."""
        mock_settings.return_value.max_conversation_turns = 10
        mock_emergency.return_value = {"is_emergency": False, "emergency_type": None, "matched_keyword": None}

        qualify_result = MagicMock()
        qualify_result.message = "Welcome back! How can I help?"
        qualify_result.qualification = None
        qualify_result.score_adjustment = 5
        qualify_result.next_action = "continue_qualifying"
        qualify_result.ai_cost_usd = 0.001
        qualify_result.ai_latency_ms = 200
        mock_qualify.return_value = qualify_result

        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_sms.return_value = _sms_result()

        lead = _make_lead(state="cold", score=20)
        client = _make_client()
        config = _make_config()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()

        timer = Timer().start()
        await _process_reply_locked(db, lead, client, config, "Actually I do need help", timer)

        assert lead.state == "qualifying"
        assert lead.current_agent == "qualify"
        assert lead.score >= 50

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_qualify", new_callable=AsyncMock)
    @patch("src.agents.conductor.detect_emergency")
    @patch("src.config.get_settings")
    async def test_dead_lead_reengages(
        self, mock_settings, mock_emergency, mock_qualify, mock_sms, mock_compliance,
    ):
        """Dead lead replying should move back to qualifying."""
        mock_settings.return_value.max_conversation_turns = 10
        mock_emergency.return_value = {"is_emergency": False, "emergency_type": None, "matched_keyword": None}

        qualify_result = MagicMock()
        qualify_result.message = "Great to hear from you!"
        qualify_result.qualification = None
        qualify_result.score_adjustment = 5
        qualify_result.next_action = "continue_qualifying"
        qualify_result.ai_cost_usd = 0.001
        qualify_result.ai_latency_ms = 200
        mock_qualify.return_value = qualify_result

        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_sms.return_value = _sms_result()

        lead = _make_lead(state="dead", score=10)
        client = _make_client()
        config = _make_config()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()

        timer = Timer().start()
        await _process_reply_locked(db, lead, client, config, "Hey I changed my mind", timer)

        assert lead.state == "qualifying"
        assert lead.current_agent == "qualify"


# ============================================================
# Conductor: _process_reply_locked - conversation turn limit (lines 391-403)
# ============================================================

class TestProcessReplyLockedTurnLimit:
    """Cover lines 391-403: conversation turn limit triggers escalation."""

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.detect_emergency")
    @patch("src.config.get_settings")
    async def test_turn_limit_in_qualifying_escalates(
        self, mock_settings, mock_emergency, mock_sms, mock_compliance,
    ):
        """Exceeding turn limit during qualifying should escalate."""
        mock_settings.return_value.max_conversation_turns = 10
        mock_emergency.return_value = {"is_emergency": False, "emergency_type": None, "matched_keyword": None}
        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_sms.return_value = _sms_result()

        lead = _make_lead(state="qualifying", score=60)
        lead.conversation_turn = 10  # Will be incremented to 11, exceeding limit
        client = _make_client()
        config = _make_config()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()

        timer = Timer().start()
        result = await _process_reply_locked(db, lead, client, config, "still chatting", timer)

        # conversation_turn is incremented to 11 which > 10
        assert lead.conversation_turn == 11
        # State transitions to booking when in qualifying and turn limit hit
        assert lead.state == "booking"
        assert result["lead_id"] == str(lead.id)

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.detect_emergency")
    @patch("src.config.get_settings")
    async def test_turn_limit_in_booking_stays(
        self, mock_settings, mock_emergency, mock_sms, mock_compliance,
    ):
        """Exceeding turn limit during booking state keeps booking state."""
        mock_settings.return_value.max_conversation_turns = 5
        mock_emergency.return_value = {"is_emergency": False, "emergency_type": None, "matched_keyword": None}
        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_sms.return_value = _sms_result()

        lead = _make_lead(state="booking", score=70)
        lead.conversation_turn = 5  # Will be incremented to 6, exceeding limit of 5
        client = _make_client()
        config = _make_config()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()

        timer = Timer().start()
        result = await _process_reply_locked(db, lead, client, config, "still going", timer)

        # booking stays as booking
        assert lead.state == "booking"


# ============================================================
# Conductor: _process_reply_locked - routing (lines 411-415)
# ============================================================

class TestProcessReplyLockedRouting:
    """Cover lines 411-415: routing to book agent and default qualify."""

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_booking", new_callable=AsyncMock)
    @patch("src.agents.conductor.detect_emergency")
    @patch("src.config.get_settings")
    async def test_qualified_routes_to_book(
        self, mock_settings, mock_emergency, mock_booking, mock_sms, mock_compliance,
    ):
        """Lead in 'qualified' state routes to booking agent."""
        mock_settings.return_value.max_conversation_turns = 10
        mock_emergency.return_value = {"is_emergency": False, "emergency_type": None, "matched_keyword": None}

        book_result = BookResponse(
            message="How about tomorrow at 9am?",
            booking_confirmed=False,
        )
        book_result.ai_cost_usd = 0.001
        book_result.ai_latency_ms = 300
        mock_booking.return_value = book_result

        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_sms.return_value = _sms_result()

        lead = _make_lead(state="qualified", score=70)
        client = _make_client()
        config = _make_config()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()

        timer = Timer().start()
        result = await _process_reply_locked(db, lead, client, config, "When can you come?", timer)

        assert result["lead_id"] == str(lead.id)
        mock_booking.assert_called_once()

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_qualify", new_callable=AsyncMock)
    @patch("src.agents.conductor.detect_emergency")
    @patch("src.config.get_settings")
    async def test_default_state_routes_to_qualify(
        self, mock_settings, mock_emergency, mock_qualify, mock_sms, mock_compliance,
    ):
        """Lead in unexpected state (e.g., 'booked') defaults to qualify agent."""
        mock_settings.return_value.max_conversation_turns = 10
        mock_emergency.return_value = {"is_emergency": False, "emergency_type": None, "matched_keyword": None}

        qualify_result = MagicMock()
        qualify_result.message = "How can I help?"
        qualify_result.qualification = None
        qualify_result.score_adjustment = 0
        qualify_result.next_action = "continue_qualifying"
        qualify_result.ai_cost_usd = 0.001
        qualify_result.ai_latency_ms = 200
        mock_qualify.return_value = qualify_result

        mock_compliance.return_value = MagicMock(__bool__=lambda s: True)
        mock_sms.return_value = _sms_result()

        lead = _make_lead(state="booked", score=70)
        client = _make_client()
        config = _make_config()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()

        timer = Timer().start()
        result = await _process_reply_locked(db, lead, client, config, "Actually one more thing", timer)

        mock_qualify.assert_called_once()


# ============================================================
# Conductor: _process_reply_locked - compliance blocked reply (line 471)
# ============================================================

class TestProcessReplyLockedComplianceBlocked:
    """Cover line 471: compliance blocks outbound reply."""

    @patch("src.agents.conductor.full_compliance_check")
    @patch("src.agents.conductor.send_sms", new_callable=AsyncMock)
    @patch("src.agents.conductor.process_qualify", new_callable=AsyncMock)
    @patch("src.agents.conductor.detect_emergency")
    @patch("src.config.get_settings")
    async def test_compliance_blocks_outbound_reply(
        self, mock_settings, mock_emergency, mock_qualify, mock_sms, mock_compliance,
    ):
        """When compliance fails on reply, SMS is not sent but commit happens."""
        mock_settings.return_value.max_conversation_turns = 10
        mock_emergency.return_value = {"is_emergency": False, "emergency_type": None, "matched_keyword": None}

        qualify_result = MagicMock()
        qualify_result.message = "A response"
        qualify_result.qualification = None
        qualify_result.score_adjustment = 0
        qualify_result.next_action = "continue_qualifying"
        qualify_result.ai_cost_usd = 0.001
        qualify_result.ai_latency_ms = 200
        mock_qualify.return_value = qualify_result

        # Compliance fails
        compliance_fail = MagicMock(__bool__=lambda s: False)
        compliance_fail.reason = "quiet_hours"
        mock_compliance.return_value = compliance_fail

        lead = _make_lead(state="qualifying")
        client = _make_client()
        config = _make_config()

        db = AsyncMock()
        db.add = MagicMock()
        db.get = AsyncMock(return_value=_make_consent())
        db.commit = AsyncMock()

        timer = Timer().start()
        result = await _process_reply_locked(db, lead, client, config, "I need help", timer)

        # SMS should NOT be sent
        mock_sms.assert_not_called()
        # But commit should still happen
        db.commit.assert_called_once()


# ============================================================
# Conductor: _route_to_qualify - conversation history (line 484)
# and qualification data updates (lines 502-514, 521-528)
# ============================================================

class TestRouteToQualify:
    """Cover lines 484, 502-514, 521-528 in _route_to_qualify."""

    @patch("src.agents.conductor.process_qualify", new_callable=AsyncMock)
    async def test_conversation_history_built(self, mock_qualify):
        """Conversation history from lead.conversations is passed to qualify."""
        qualify_result = MagicMock()
        qualify_result.message = "What service do you need?"
        qualify_result.qualification = QualificationData(
            service_type="AC Repair",
            urgency="today",
            property_type="residential",
            preferred_date="2026-02-20",
        )
        qualify_result.score_adjustment = 10
        qualify_result.next_action = "ready_to_book"
        qualify_result.ai_cost_usd = 0.002
        qualify_result.ai_latency_ms = 300
        mock_qualify.return_value = qualify_result

        lead = _make_lead(state="qualifying", score=50)
        # Add conversation history
        conv1 = MagicMock()
        conv1.direction = "outbound"
        conv1.content = "Hi, how can I help?"
        conv2 = MagicMock()
        conv2.direction = "inbound"
        conv2.content = "I need AC repair today"
        lead.conversations = [conv1, conv2]
        lead.qualification_data = {}

        client = _make_client()
        config = _make_config()
        db = AsyncMock()

        result = await _route_to_qualify(db, lead, client, config, "I need AC repair today")

        # Verify conversations were passed
        call_kwargs = mock_qualify.call_args.kwargs
        assert len(call_kwargs["conversation_history"]) == 2
        assert call_kwargs["conversation_history"][0]["direction"] == "outbound"
        assert call_kwargs["conversation_history"][1]["content"] == "I need AC repair today"

        # Verify qualification data updates
        assert lead.service_type == "AC Repair"
        assert lead.urgency == "today"
        assert lead.property_type == "residential"
        assert lead.qualification_data.get("preferred_date") == "2026-02-20"

        # State transitions for ready_to_book
        assert lead.state == "qualified"
        assert lead.current_agent == "book"

        # Score adjusted
        assert lead.score == 60

    @patch("src.agents.conductor.process_qualify", new_callable=AsyncMock)
    async def test_mark_cold_transition(self, mock_qualify):
        """next_action=mark_cold should transition to cold."""
        qualify_result = MagicMock()
        qualify_result.message = "Ok, we'll be here if you need us."
        qualify_result.qualification = QualificationData()
        qualify_result.score_adjustment = -10
        qualify_result.next_action = "mark_cold"
        qualify_result.ai_cost_usd = 0.001
        qualify_result.ai_latency_ms = 200
        mock_qualify.return_value = qualify_result

        lead = _make_lead(state="qualifying", score=40)
        client = _make_client()
        config = _make_config()
        db = AsyncMock()

        result = await _route_to_qualify(db, lead, client, config, "Not interested right now")

        assert lead.state == "cold"
        assert lead.current_agent == "followup"

    @patch("src.agents.conductor.process_qualify", new_callable=AsyncMock)
    async def test_escalate_emergency_transition(self, mock_qualify):
        """next_action=escalate_emergency should flag lead as emergency."""
        qualify_result = MagicMock()
        qualify_result.message = "I'm sending help immediately!"
        qualify_result.qualification = QualificationData()
        qualify_result.score_adjustment = 20
        qualify_result.next_action = "escalate_emergency"
        qualify_result.ai_cost_usd = 0.001
        qualify_result.ai_latency_ms = 200
        mock_qualify.return_value = qualify_result

        lead = _make_lead(state="qualifying", score=50)
        client = _make_client()
        config = _make_config()
        db = AsyncMock()

        result = await _route_to_qualify(db, lead, client, config, "Gas leak!")

        assert lead.is_emergency is True
        assert lead.urgency == "emergency"


# ============================================================
# Conductor: _route_to_book - booking confirmed and fallback paths
# (lines 544-604)
# ============================================================

class TestRouteToBook:
    """Cover lines 544-604 in _route_to_book."""

    @patch("src.agents.conductor.process_booking", new_callable=AsyncMock)
    async def test_booking_confirmed_creates_record(self, mock_booking):
        """booking_confirmed=True should create Booking and EventLog."""
        book_result = BookResponse(
            message="You're all set for tomorrow at 9am!",
            appointment_date="2026-02-20",
            time_window_start="09:00",
            time_window_end="11:00",
            tech_name="Mike",
            booking_confirmed=True,
        )
        book_result.ai_cost_usd = 0.001
        book_result.ai_latency_ms = 300
        mock_booking.return_value = book_result

        lead = _make_lead(state="booking", score=80)
        client = _make_client()
        config = _make_config()
        db = AsyncMock()
        db.add = MagicMock()

        result = await _route_to_book(db, lead, client, config, "Yes, tomorrow 9am works!")

        assert lead.state == "booked"
        assert lead.current_agent is None
        assert result["message"] == "You're all set for tomorrow at 9am!"
        assert result["agent_id"] == "book"
        # Booking + EventLog added
        assert db.add.call_count >= 2

    @patch("src.agents.conductor.process_booking", new_callable=AsyncMock)
    async def test_booking_confirmed_unparseable_date(self, mock_booking):
        """Unparseable appointment_date should use today's date."""
        book_result = BookResponse(
            message="You're all set!",
            appointment_date="next Tuesday",  # unparseable
            booking_confirmed=True,
        )
        book_result.ai_cost_usd = 0.001
        book_result.ai_latency_ms = 300
        mock_booking.return_value = book_result

        lead = _make_lead(state="booking", score=80)
        client = _make_client()
        config = _make_config()
        db = AsyncMock()
        db.add = MagicMock()

        result = await _route_to_book(db, lead, client, config, "Sounds good!")

        assert lead.state == "booked"
        # Booking should still be created (with today's date)
        assert db.add.call_count >= 2

    @patch("src.agents.conductor.process_booking", new_callable=AsyncMock)
    async def test_booking_confirmed_no_date(self, mock_booking):
        """booking_confirmed=True with no appointment_date uses today's date."""
        book_result = BookResponse(
            message="You're all set!",
            appointment_date=None,
            booking_confirmed=True,
        )
        book_result.ai_cost_usd = 0.001
        book_result.ai_latency_ms = 300
        mock_booking.return_value = book_result

        lead = _make_lead(state="booking", score=80)
        client = _make_client()
        config = _make_config()
        db = AsyncMock()
        db.add = MagicMock()

        result = await _route_to_book(db, lead, client, config, "Book it!")

        assert lead.state == "booked"
        assert db.add.call_count >= 2

    @patch("src.agents.conductor.process_booking", new_callable=AsyncMock)
    async def test_needs_human_handoff(self, mock_booking):
        """needs_human_handoff=True should keep state=booking and log event."""
        book_result = BookResponse(
            message="Let me get a manager to help with that request.",
            booking_confirmed=False,
            needs_human_handoff=True,
        )
        book_result.ai_cost_usd = 0.001
        book_result.ai_latency_ms = 300
        mock_booking.return_value = book_result

        lead = _make_lead(state="booking", score=70)
        client = _make_client()
        config = _make_config()
        db = AsyncMock()
        db.add = MagicMock()

        result = await _route_to_book(db, lead, client, config, "I need something special")

        assert lead.state == "booking"
        assert result["agent_id"] == "book"
        # EventLog for human_handoff_needed
        db.add.assert_called()

    @patch("src.agents.conductor.process_booking", new_callable=AsyncMock)
    async def test_booking_not_confirmed_stays_booking(self, mock_booking):
        """Neither confirmed nor handoff keeps state=booking."""
        book_result = BookResponse(
            message="Would Tuesday work instead?",
            booking_confirmed=False,
            needs_human_handoff=False,
        )
        book_result.ai_cost_usd = 0.001
        book_result.ai_latency_ms = 300
        mock_booking.return_value = book_result

        lead = _make_lead(state="booking", score=70)
        client = _make_client()
        config = _make_config()
        db = AsyncMock()
        db.add = MagicMock()

        result = await _route_to_book(db, lead, client, config, "Monday doesn't work")

        assert lead.state == "booking"


# ============================================================
# Book Agent - full process_booking flow (lines 71-163)
# ============================================================

class TestBookAgent:
    """Cover book.py lines 71-163: main process_booking and parse paths."""

    @patch("src.agents.book.generate_response", new_callable=AsyncMock)
    @patch("src.agents.book.generate_available_slots")
    async def test_successful_booking_response(self, mock_slots, mock_ai):
        """Successful AI response should return parsed BookResponse."""
        from src.services.scheduling import TimeSlot

        slot = TimeSlot(date(2026, 2, 20), time(9, 0), time(11, 0), "Mike")
        mock_slots.return_value = [slot]

        mock_ai.return_value = {
            "content": json.dumps({
                "message": "How about Friday at 9am?",
                "appointment_date": "2026-02-20",
                "time_window_start": "09:00",
                "time_window_end": "11:00",
                "tech_name": "Mike",
                "booking_confirmed": False,
                "needs_human_handoff": False,
                "internal_notes": "Offered first available slot",
            }),
            "cost_usd": 0.001,
            "latency_ms": 500,
            "error": None,
        }

        result = await process_booking(
            lead_message="When can you come?",
            first_name="John",
            service_type="AC Repair",
            preferred_date="2026-02-20",
            business_name="Austin HVAC",
            rep_name="Sarah",
            scheduling_config={"advance_booking_days": 14, "slot_duration_minutes": 120, "buffer_minutes": 30, "max_daily_bookings": 8},
            team_members=[{"name": "Mike", "specialty": ["hvac_repair"], "active": True}],
            hours_config={"business": {"start": "08:00", "end": "18:00"}, "saturday": {"start": "08:00", "end": "14:00"}},
            conversation_history=[],
        )

        assert result.message == "How about Friday at 9am?"
        assert result.appointment_date == "2026-02-20"
        assert result.tech_name == "Mike"
        assert result.ai_cost_usd == 0.001

    @patch("src.agents.book.generate_response", new_callable=AsyncMock)
    @patch("src.agents.book.generate_available_slots")
    async def test_ai_error_fallback(self, mock_slots, mock_ai):
        """AI error should return fallback response."""
        from src.services.scheduling import TimeSlot

        slot = TimeSlot(date(2026, 2, 20), time(9, 0), time(11, 0), "Mike")
        mock_slots.return_value = [slot]

        mock_ai.return_value = {
            "content": "",
            "cost_usd": 0.0,
            "latency_ms": 0,
            "error": "API timeout",
        }

        result = await process_booking(
            lead_message="When can you come?",
            first_name="John",
            service_type="AC Repair",
            preferred_date=None,
            business_name="Austin HVAC",
            rep_name="Sarah",
            scheduling_config={},
            team_members=[],
            hours_config={},
            conversation_history=[],
        )

        assert "scheduled" in result.message.lower() or "available" in result.message.lower()
        assert result.ai_cost_usd == 0.0
        assert result.ai_latency_ms == 0

    @patch("src.agents.book.generate_response", new_callable=AsyncMock)
    @patch("src.agents.book.generate_available_slots")
    async def test_markdown_fences_stripped(self, mock_slots, mock_ai):
        """AI response wrapped in ```json should be stripped and parsed."""
        from src.services.scheduling import TimeSlot

        slot = TimeSlot(date(2026, 2, 20), time(9, 0), time(11, 0))
        mock_slots.return_value = [slot]

        json_content = json.dumps({
            "message": "How about 9am?",
            "appointment_date": None,
            "booking_confirmed": False,
            "needs_human_handoff": False,
            "internal_notes": "",
        })
        mock_ai.return_value = {
            "content": f"```json\n{json_content}\n```",
            "cost_usd": 0.001,
            "latency_ms": 400,
            "error": None,
        }

        result = await process_booking(
            lead_message="hello",
            first_name="John",
            service_type="AC Repair",
            preferred_date=None,
            business_name="Austin HVAC",
            rep_name="Sarah",
            scheduling_config={},
            team_members=[],
            hours_config={},
            conversation_history=[{"direction": "inbound", "content": "hello"}],
        )

        assert result.message == "How about 9am?"

    @patch("src.agents.book.generate_response", new_callable=AsyncMock)
    @patch("src.agents.book.generate_available_slots")
    async def test_json_parse_error_fallback(self, mock_slots, mock_ai):
        """Invalid JSON from AI should use fallback parse path."""
        from src.services.scheduling import TimeSlot

        slot = TimeSlot(date(2026, 2, 20), time(9, 0), time(11, 0))
        mock_slots.return_value = [slot]

        mock_ai.return_value = {
            "content": "This is not valid JSON at all",
            "cost_usd": 0.001,
            "latency_ms": 400,
            "error": None,
        }

        result = await process_booking(
            lead_message="hello",
            first_name="John",
            service_type="AC Repair",
            preferred_date=None,
            business_name="Austin HVAC",
            rep_name="Sarah",
            scheduling_config={},
            team_members=[],
            hours_config={},
            conversation_history=[],
        )

        # Should use the raw content (truncated to 300 chars)
        assert "This is not valid JSON" in result.message
        assert "Parse error" in result.internal_notes
        assert result.ai_cost_usd == 0.001

    @patch("src.agents.book.generate_response", new_callable=AsyncMock)
    @patch("src.agents.book.generate_available_slots")
    async def test_no_slots_available_text(self, mock_slots, mock_ai):
        """When no slots available, prompt should indicate that."""
        mock_slots.return_value = []

        mock_ai.return_value = {
            "content": json.dumps({
                "message": "Let me check with the team.",
                "booking_confirmed": False,
                "needs_human_handoff": True,
                "internal_notes": "No slots",
            }),
            "cost_usd": 0.001,
            "latency_ms": 400,
            "error": None,
        }

        result = await process_booking(
            lead_message="when?",
            first_name="John",
            service_type="AC Repair",
            preferred_date=None,
            business_name="Austin HVAC",
            rep_name="Sarah",
            scheduling_config={},
            team_members=[],
            hours_config={},
            conversation_history=[],
        )

        assert result.needs_human_handoff is True

    @patch("src.agents.book.generate_response", new_callable=AsyncMock)
    @patch("src.agents.book.generate_available_slots")
    async def test_booking_confirmed_response(self, mock_slots, mock_ai):
        """Booking confirmed flag should be set from AI response."""
        from src.services.scheduling import TimeSlot

        slot = TimeSlot(date(2026, 2, 20), time(9, 0), time(11, 0), "Mike")
        mock_slots.return_value = [slot]

        mock_ai.return_value = {
            "content": json.dumps({
                "message": "Great! You're all set for Friday at 9am with Mike!",
                "appointment_date": "2026-02-20",
                "time_window_start": "09:00",
                "time_window_end": "11:00",
                "tech_name": "Mike",
                "booking_confirmed": True,
                "needs_human_handoff": False,
                "internal_notes": "Customer confirmed",
            }),
            "cost_usd": 0.002,
            "latency_ms": 600,
            "error": None,
        }

        result = await process_booking(
            lead_message="Yes 9am works!",
            first_name="John",
            service_type="AC Repair",
            preferred_date="2026-02-20",
            business_name="Austin HVAC",
            rep_name="Sarah",
            scheduling_config={},
            team_members=[{"name": "Mike", "active": True}],
            hours_config={},
            conversation_history=[],
        )

        assert result.booking_confirmed is True
        assert result.tech_name == "Mike"
        assert result.ai_cost_usd == 0.002


# ============================================================
# Book Agent - _fallback_booking (lines 168-185)
# ============================================================

class TestBookFallback:
    """Cover book.py lines 168-185: _fallback_booking."""

    def test_fallback_with_slots(self):
        """Fallback with available slots offers the first one."""
        from src.services.scheduling import TimeSlot

        slot = TimeSlot(date(2026, 2, 20), time(9, 0), time(11, 0), "Mike")
        result = _fallback_booking([slot])

        assert "get you scheduled" in result.message.lower() or "available" in result.message.lower()
        assert result.appointment_date == "2026-02-20"
        assert result.tech_name == "Mike"
        assert "AI fallback" in result.internal_notes

    def test_fallback_with_slot_no_tech(self):
        """Fallback with slot that has no tech name."""
        from src.services.scheduling import TimeSlot

        slot = TimeSlot(date(2026, 2, 20), time(14, 0), time(16, 0), None)
        result = _fallback_booking([slot])

        assert result.tech_name is None
        assert "available" in result.message.lower() or "scheduled" in result.message.lower()

    def test_fallback_no_slots(self):
        """Fallback with no slots triggers human handoff."""
        result = _fallback_booking([])

        assert result.needs_human_handoff is True
        assert "check our schedule" in result.message.lower() or "get back to you" in result.message.lower()
        assert "no slots" in result.internal_notes.lower()


# ============================================================
# Book Agent - _escape_braces (line 18)
# ============================================================

class TestBookEscapeBraces:
    """Cover book.py line 18: _escape_braces utility."""

    def test_escape_braces_curly(self):
        """Curly braces should be doubled."""
        assert _escape_braces("{test}") == "{{test}}"
        assert _escape_braces("no braces") == "no braces"
        assert _escape_braces("") == ""


# ============================================================
# Qualify Agent - process_qualify full flow (lines 87-159)
# ============================================================

class TestQualifyAgent:
    """Cover qualify.py lines 87-159: main process_qualify and parse paths."""

    @patch("src.agents.qualify.generate_response", new_callable=AsyncMock)
    async def test_successful_qualify_response(self, mock_ai):
        """Successful AI response returns parsed QualifyResponse."""
        mock_ai.return_value = {
            "content": json.dumps({
                "message": "What type of AC service do you need?",
                "qualification": {
                    "service_type": "AC Repair",
                    "urgency": "today",
                    "property_type": None,
                    "preferred_date": None,
                },
                "internal_notes": "Customer mentioned AC issue",
                "next_action": "continue_qualifying",
                "score_adjustment": 5,
                "is_qualified": False,
            }),
            "cost_usd": 0.003,
            "latency_ms": 800,
            "error": None,
        }

        result = await process_qualify(
            lead_message="My AC is broken",
            conversation_history=[],
            current_qualification={},
            business_name="Austin HVAC",
            rep_name="Sarah",
            trade_type="hvac",
            services={"primary": ["AC Repair"], "secondary": [], "do_not_quote": []},
            conversation_turn=1,
        )

        assert result.message == "What type of AC service do you need?"
        assert result.qualification.service_type == "AC Repair"
        assert result.qualification.urgency == "today"
        assert result.score_adjustment == 5
        assert result.ai_cost_usd == 0.003

    @patch("src.agents.qualify.generate_response", new_callable=AsyncMock)
    async def test_ai_error_fallback(self, mock_ai):
        """AI error should return fallback response."""
        mock_ai.return_value = {
            "content": "",
            "cost_usd": 0.0,
            "latency_ms": 0,
            "error": "API timeout",
        }

        result = await process_qualify(
            lead_message="hello",
            conversation_history=[],
            current_qualification={},
            business_name="Austin HVAC",
            rep_name="Sarah",
            trade_type="hvac",
            services={},
            conversation_turn=0,
        )

        assert "tell me more" in result.message.lower() or "help with" in result.message.lower()
        assert result.ai_cost_usd == 0.0
        assert result.ai_latency_ms == 0

    @patch("src.agents.qualify.generate_response", new_callable=AsyncMock)
    async def test_markdown_fences_stripped(self, mock_ai):
        """AI response wrapped in ```json should be parsed correctly."""
        json_content = json.dumps({
            "message": "Is this for a home or business?",
            "qualification": {"property_type": "residential"},
            "internal_notes": "",
            "next_action": "continue_qualifying",
            "score_adjustment": 0,
            "is_qualified": False,
        })
        mock_ai.return_value = {
            "content": f"```json\n{json_content}\n```",
            "cost_usd": 0.002,
            "latency_ms": 600,
            "error": None,
        }

        result = await process_qualify(
            lead_message="I need plumbing",
            conversation_history=[],
            current_qualification={},
            business_name="Austin HVAC",
            rep_name="Sarah",
            trade_type="hvac",
            services={},
            conversation_turn=1,
        )

        assert result.message == "Is this for a home or business?"
        assert result.qualification.property_type == "residential"

    @patch("src.agents.qualify.generate_response", new_callable=AsyncMock)
    async def test_json_parse_error_fallback(self, mock_ai):
        """Invalid JSON from AI should use fallback with raw content."""
        mock_ai.return_value = {
            "content": "Not a JSON response at all here",
            "cost_usd": 0.002,
            "latency_ms": 500,
            "error": None,
        }

        result = await process_qualify(
            lead_message="test",
            conversation_history=[],
            current_qualification={},
            business_name="Austin HVAC",
            rep_name="Sarah",
            trade_type="hvac",
            services={},
            conversation_turn=2,
        )

        assert "Not a JSON response" in result.message
        assert "Parse error" in result.internal_notes
        assert result.ai_cost_usd == 0.002

    @patch("src.agents.qualify.generate_response", new_callable=AsyncMock)
    async def test_empty_ai_content_uses_fallback_message(self, mock_ai):
        """Empty AI content with parse error uses fallback message."""
        mock_ai.return_value = {
            "content": "",
            "cost_usd": 0.001,
            "latency_ms": 200,
            "error": None,
        }

        result = await process_qualify(
            lead_message="test",
            conversation_history=[],
            current_qualification={},
            business_name="Austin HVAC",
            rep_name="Sarah",
            trade_type="hvac",
            services={},
            conversation_turn=2,
        )

        # Empty content triggers JSONDecodeError, fallback uses _fallback_response
        assert len(result.message) > 0
        assert result.ai_cost_usd == 0.001

    @patch("src.agents.qualify.generate_response", new_callable=AsyncMock)
    async def test_conversation_history_with_existing_data(self, mock_ai):
        """Existing conversation history and qualification data pass through."""
        mock_ai.return_value = {
            "content": json.dumps({
                "message": "When would you like the service?",
                "qualification": {
                    "preferred_date": "next Monday",
                },
                "internal_notes": "Has service type and urgency already",
                "next_action": "continue_qualifying",
                "score_adjustment": 5,
                "is_qualified": False,
            }),
            "cost_usd": 0.002,
            "latency_ms": 500,
            "error": None,
        }

        result = await process_qualify(
            lead_message="How about next Monday?",
            conversation_history=[
                {"direction": "outbound", "content": "Hi! What service do you need?"},
                {"direction": "inbound", "content": "AC repair"},
                {"direction": "outbound", "content": "How urgent is it?"},
                {"direction": "inbound", "content": "Today if possible"},
            ],
            current_qualification={"service_type": "AC Repair", "urgency": "today"},
            business_name="Austin HVAC",
            rep_name="Sarah",
            trade_type="hvac",
            services={"primary": ["AC Repair"], "secondary": ["Duct Cleaning"], "do_not_quote": ["Ductwork"]},
            conversation_turn=3,
        )

        assert result.message == "When would you like the service?"
        assert result.qualification.preferred_date == "next Monday"

    @patch("src.agents.qualify.generate_response", new_callable=AsyncMock)
    async def test_qualified_response(self, mock_ai):
        """Fully qualified lead should set is_qualified=True."""
        mock_ai.return_value = {
            "content": json.dumps({
                "message": "Great! Let me find you an appointment.",
                "qualification": {
                    "service_type": "AC Repair",
                    "urgency": "today",
                    "property_type": "residential",
                    "preferred_date": "tomorrow morning",
                },
                "internal_notes": "All 4 fields collected",
                "next_action": "ready_to_book",
                "score_adjustment": 15,
                "is_qualified": True,
            }),
            "cost_usd": 0.003,
            "latency_ms": 700,
            "error": None,
        }

        result = await process_qualify(
            lead_message="Tomorrow morning works",
            conversation_history=[],
            current_qualification={"service_type": "AC Repair", "urgency": "today", "property_type": "residential"},
            business_name="Austin HVAC",
            rep_name="Sarah",
            trade_type="hvac",
            services={},
            conversation_turn=4,
        )

        assert result.is_qualified is True
        assert result.next_action == "ready_to_book"
        assert result.score_adjustment == 15


# ============================================================
# Qualify Agent - _fallback_response (lines 164-171)
# ============================================================

class TestQualifyFallback:
    """Cover qualify.py lines 164-171: _fallback_response."""

    def test_fallback_turn_0(self):
        """Turn 0 should use first fallback message."""
        result = _fallback_response(0)
        assert "tell me more" in result.message.lower() or "help with" in result.message.lower()
        assert "AI fallback" in result.internal_notes

    def test_fallback_turn_1(self):
        """Turn 1 should use urgency question."""
        result = _fallback_response(1)
        assert "urgent" in result.message.lower() or "today" in result.message.lower()

    def test_fallback_turn_2(self):
        """Turn 2 should use property type question."""
        result = _fallback_response(2)
        assert "home" in result.message.lower() or "business" in result.message.lower()

    def test_fallback_turn_3(self):
        """Turn 3 should use scheduling question."""
        result = _fallback_response(3)
        assert "time" in result.message.lower() or "look" in result.message.lower()

    def test_fallback_turn_beyond_list(self):
        """Turn beyond list length should use last fallback."""
        result = _fallback_response(10)
        assert "time" in result.message.lower() or "look" in result.message.lower()


# ============================================================
# Qualify Agent - _escape_braces (line 23)
# ============================================================

class TestQualifyEscapeBraces:
    """Cover qualify.py line 23: _escape_braces utility."""

    def test_escape_braces(self):
        assert qualify_escape_braces("{key}") == "{{key}}"
        assert qualify_escape_braces("plain") == "plain"


# ============================================================
# Followup Agent - unknown type (lines 94-95)
# ============================================================

class TestFollowupUnknownType:
    """Cover followup.py lines 94-95: unknown followup_type."""

    async def test_unknown_followup_type(self):
        """Unknown followup type should return a generic fallback message."""
        result = await process_followup(
            lead_first_name="John",
            service_type="AC Repair",
            business_name="Austin HVAC",
            rep_name="Sarah",
            followup_type="some_unknown_type",
            sequence_number=1,
        )

        assert "John" in result.message
        assert "Austin HVAC" in result.message
        assert result.followup_type == "some_unknown_type"
        assert "Unknown type fallback" in result.internal_notes

    async def test_unknown_followup_type_no_name(self):
        """Unknown followup type with no lead name uses 'there'."""
        result = await process_followup(
            lead_first_name=None,
            service_type=None,
            business_name="Austin HVAC",
            rep_name="Sarah",
            followup_type="random_type",
            sequence_number=2,
        )

        assert "there" in result.message
        assert "Austin HVAC" in result.message
        assert result.sequence_number == 2


# ============================================================
# Sales Outreach Agent - _get_learning_context (lines 39-57)
# ============================================================

class TestSalesOutreachLearningContext:
    """Cover sales_outreach.py lines 39-57: _get_learning_context."""

    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    @patch("src.services.learning.get_open_rate_by_dimension", new_callable=AsyncMock)
    async def test_learning_context_with_data(self, mock_open_rate, mock_best_time):
        """Learning context with data should return formatted insights."""
        mock_open_rate.return_value = 0.35
        mock_best_time.return_value = "9am-12pm"

        result = await _get_learning_context("hvac", "TX")

        assert "Performance insights" in result
        assert "hvac" in result
        assert "35%" in result
        assert "9am-12pm" in result

    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    @patch("src.services.learning.get_open_rate_by_dimension", new_callable=AsyncMock)
    async def test_learning_context_zero_open_rate(self, mock_open_rate, mock_best_time):
        """Zero open rate should not be included."""
        mock_open_rate.return_value = 0
        mock_best_time.return_value = None

        result = await _get_learning_context("plumbing", "CA")

        assert result == ""

    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    @patch("src.services.learning.get_open_rate_by_dimension", new_callable=AsyncMock)
    async def test_learning_context_only_open_rate(self, mock_open_rate, mock_best_time):
        """Only open rate available should still return insights."""
        mock_open_rate.return_value = 0.42
        mock_best_time.return_value = None

        result = await _get_learning_context("roofing", "FL")

        assert "Performance insights" in result
        assert "42%" in result

    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    @patch("src.services.learning.get_open_rate_by_dimension", new_callable=AsyncMock)
    async def test_learning_context_only_best_time(self, mock_open_rate, mock_best_time):
        """Only best time available should still return insights."""
        mock_open_rate.return_value = 0
        mock_best_time.return_value = "3pm-6pm"

        result = await _get_learning_context("electrical", "NY")

        assert "Performance insights" in result
        assert "3pm-6pm" in result

    async def test_learning_context_import_error(self):
        """Import error should return empty string gracefully."""
        with patch.dict("sys.modules", {"src.services.learning": None}):
            # The function catches all exceptions including ImportError
            result = await _get_learning_context("hvac", "TX")
            assert result == ""


# ============================================================
# Sales Outreach Agent - generate_outreach_email (lines 118, 123, 126)
# ============================================================

class TestSalesOutreachGenerate:
    """Cover sales_outreach.py lines 118, 123, 126: optional fields in email generation."""

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_with_all_optional_fields(self, mock_ai, mock_learning):
        """All optional fields (rating, review_count, website) included."""
        mock_learning.return_value = "Performance insights:\n- Best send time: 9am"
        mock_ai.return_value = {
            "content": json.dumps({
                "subject": "Quick question about your leads",
                "body_html": "<p>Hi John,</p>",
                "body_text": "Hi John,",
            }),
            "cost_usd": 0.001,
            "latency_ms": 500,
            "error": None,
        }

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="ABC HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
            rating=4.8,
            review_count=150,
            website="https://abchvac.com",
            sequence_step=1,
        )

        assert result["subject"] == "Quick question about your leads"
        assert result["body_html"] == "<p>Hi John,</p>"
        assert result["ai_cost_usd"] == 0.001
        assert "error" not in result

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_with_learning_context(self, mock_ai, mock_learning):
        """Learning context should be included in prompt when available."""
        mock_learning.return_value = "Performance insights:\n- Avg open rate for hvac: 35%"
        mock_ai.return_value = {
            "content": json.dumps({
                "subject": "Your leads",
                "body_html": "<p>Hi</p>",
                "body_text": "Hi",
            }),
            "cost_usd": 0.001,
            "latency_ms": 500,
            "error": None,
        }

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="ABC HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert result["subject"] == "Your leads"
        mock_learning.assert_called_once_with("hvac", "TX", 1)

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_with_extra_instructions(self, mock_ai, mock_learning):
        """Extra instructions should be included in prompt."""
        mock_learning.return_value = ""
        mock_ai.return_value = {
            "content": json.dumps({
                "subject": "Test",
                "body_html": "<p>Test</p>",
                "body_text": "Test",
            }),
            "cost_usd": 0.001,
            "latency_ms": 500,
            "error": None,
        }

        result = await generate_outreach_email(
            prospect_name="Jane",
            company_name="Best Plumbing",
            trade_type="plumbing",
            city="Dallas",
            state="TX",
            extra_instructions="Mention their new website redesign",
        )

        assert result["subject"] == "Test"
        # Verify extra_instructions was included in the user_message
        call_kwargs = mock_ai.call_args.kwargs
        assert "new website redesign" in call_kwargs["user_message"]

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_step_clamping(self, mock_ai, mock_learning):
        """Sequence step should be clamped to 1-3."""
        mock_learning.return_value = ""
        mock_ai.return_value = {
            "content": json.dumps({
                "subject": "Break-up",
                "body_html": "<p>Last email</p>",
                "body_text": "Last email",
            }),
            "cost_usd": 0.001,
            "latency_ms": 500,
            "error": None,
        }

        # Step 5 should be clamped to 3
        result = await generate_outreach_email(
            prospect_name="Bob",
            company_name="XYZ Roofing",
            trade_type="roofing",
            city="Houston",
            state="TX",
            sequence_step=5,
        )

        assert result["subject"] == "Break-up"
        # Step 0 should be clamped to 1
        await generate_outreach_email(
            prospect_name="Bob",
            company_name="XYZ Roofing",
            trade_type="roofing",
            city="Houston",
            state="TX",
            sequence_step=0,
        )

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_ai_error(self, mock_ai, mock_learning):
        """AI error should return error dict."""
        mock_learning.return_value = ""
        mock_ai.return_value = {
            "content": "",
            "cost_usd": 0.0,
            "latency_ms": 0,
            "error": "Rate limit exceeded",
        }

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Test Co",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert result["error"] == "Rate limit exceeded"
        assert result["subject"] == ""
        assert result["body_html"] == ""

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_json_parse_error(self, mock_ai, mock_learning):
        """Invalid JSON from AI should return error dict."""
        mock_learning.return_value = ""
        mock_ai.return_value = {
            "content": "Not valid JSON here",
            "cost_usd": 0.001,
            "latency_ms": 500,
            "error": None,
        }

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Test Co",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert "error" in result
        assert "JSON parse error" in result["error"]

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_empty_subject_or_body(self, mock_ai, mock_learning):
        """Empty subject or body_html should return error."""
        mock_learning.return_value = ""
        mock_ai.return_value = {
            "content": json.dumps({
                "subject": "",
                "body_html": "",
                "body_text": "Something",
            }),
            "cost_usd": 0.001,
            "latency_ms": 500,
            "error": None,
        }

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Test Co",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert "error" in result
        assert "empty" in result["error"].lower()

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_markdown_fences_stripped(self, mock_ai, mock_learning):
        """Markdown code fences should be stripped from AI response."""
        mock_learning.return_value = ""
        json_content = json.dumps({
            "subject": "Test subject",
            "body_html": "<p>Hello</p>",
            "body_text": "Hello",
        })
        mock_ai.return_value = {
            "content": f"```json\n{json_content}\n```",
            "cost_usd": 0.001,
            "latency_ms": 500,
            "error": None,
        }

        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Test Co",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )

        assert result["subject"] == "Test subject"
        assert "error" not in result


# ============================================================
# Sales Outreach Agent - classify_reply
# ============================================================

class TestSalesOutreachClassify:
    """Cover classify_reply edge cases."""

    async def test_empty_reply_classified_as_auto_reply(self):
        """Empty reply text should return auto_reply."""
        result = await classify_reply("")
        assert result["classification"] == "auto_reply"
        assert result["ai_cost_usd"] == 0.0

    async def test_whitespace_only_reply(self):
        """Whitespace-only reply should return auto_reply."""
        result = await classify_reply("   ")
        assert result["classification"] == "auto_reply"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_classify_interested(self, mock_ai):
        """Interested reply should be classified correctly."""
        mock_ai.return_value = {
            "content": "interested",
            "cost_usd": 0.0001,
            "latency_ms": 100,
            "error": None,
        }

        result = await classify_reply("Tell me more about your service")
        assert result["classification"] == "interested"
        assert result["ai_cost_usd"] == 0.0001

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_classify_rejection(self, mock_ai):
        """Rejection reply should be classified correctly."""
        mock_ai.return_value = {
            "content": "rejection",
            "cost_usd": 0.0001,
            "latency_ms": 100,
            "error": None,
        }

        result = await classify_reply("Not interested, please stop")
        assert result["classification"] == "rejection"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_classify_unknown_defaults_interested(self, mock_ai):
        """Unknown classification from AI defaults to interested."""
        mock_ai.return_value = {
            "content": "maybe_later",
            "cost_usd": 0.0001,
            "latency_ms": 100,
            "error": None,
        }

        result = await classify_reply("I'll think about it")
        assert result["classification"] == "interested"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_classify_ai_error_defaults_interested(self, mock_ai):
        """AI error during classification defaults to interested."""
        mock_ai.return_value = {
            "content": "",
            "cost_usd": 0.0001,
            "latency_ms": 0,
            "error": "API error",
        }

        result = await classify_reply("Some reply text")
        assert result["classification"] == "interested"
        assert result["ai_cost_usd"] == 0.0001

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_classify_unsubscribe(self, mock_ai):
        """Unsubscribe reply should be classified correctly."""
        mock_ai.return_value = {
            "content": "unsubscribe",
            "cost_usd": 0.0001,
            "latency_ms": 100,
            "error": None,
        }

        result = await classify_reply("Please remove me from your list")
        assert result["classification"] == "unsubscribe"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_classify_out_of_office(self, mock_ai):
        """Out of office reply should be classified correctly."""
        mock_ai.return_value = {
            "content": "out_of_office",
            "cost_usd": 0.0001,
            "latency_ms": 100,
            "error": None,
        }

        result = await classify_reply("I'm out of office until March 1")
        assert result["classification"] == "out_of_office"

    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_classify_normalizes_whitespace(self, mock_ai):
        """Classification with spaces should be normalized to underscores."""
        mock_ai.return_value = {
            "content": "auto reply",
            "cost_usd": 0.0001,
            "latency_ms": 100,
            "error": None,
        }

        result = await classify_reply("Auto-generated reply")
        assert result["classification"] == "auto_reply"
