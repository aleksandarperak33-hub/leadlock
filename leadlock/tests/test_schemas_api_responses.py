"""
Tests for src/schemas/api_responses.py — Pydantic response schemas.
Tests instantiation, validation, defaults, and edge cases.
"""
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.schemas.api_responses import (
    LoginRequest,
    LoginResponse,
    LeadSummary,
    LeadListResponse,
    MessageSummary,
    BookingDetail,
    ConsentDetail,
    EventSummary,
    LeadDetailResponse,
    DayMetric,
    ResponseTimeBucket,
    DashboardMetrics,
    ActivityEvent,
    ComplianceSummary,
    WebhookPayloadResponse,
)


NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# LoginRequest
# ---------------------------------------------------------------------------


class TestLoginRequest:
    def test_valid_login(self):
        """Valid email and password."""
        req = LoginRequest(email="test@example.com", password="secret123")
        assert req.email == "test@example.com"
        assert req.password == "secret123"

    def test_missing_email_raises(self):
        """Missing email raises ValidationError."""
        with pytest.raises(ValidationError):
            LoginRequest(password="secret123")

    def test_missing_password_raises(self):
        """Missing password raises ValidationError."""
        with pytest.raises(ValidationError):
            LoginRequest(email="test@example.com")

    def test_empty_strings_accepted(self):
        """Empty strings are technically valid for str fields."""
        req = LoginRequest(email="", password="")
        assert req.email == ""


# ---------------------------------------------------------------------------
# LoginResponse
# ---------------------------------------------------------------------------


class TestLoginResponse:
    def test_valid_response(self):
        """Valid login response with all fields."""
        resp = LoginResponse(
            token="jwt_token_here",
            client_id="client-123",
            business_name="HVAC Pro",
        )
        assert resp.token == "jwt_token_here"
        assert resp.is_admin is False  # default

    def test_admin_flag(self):
        """Admin flag can be set to True."""
        resp = LoginResponse(
            token="token",
            client_id="admin-1",
            business_name="LeadLock Admin",
            is_admin=True,
        )
        assert resp.is_admin is True

    def test_missing_required_fields(self):
        """Missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            LoginResponse(token="token")


# ---------------------------------------------------------------------------
# LeadSummary
# ---------------------------------------------------------------------------


class TestLeadSummary:
    def test_valid_lead_summary(self):
        """Full lead summary with all fields."""
        lead = LeadSummary(
            id="lead-123",
            first_name="John",
            last_name="Smith",
            phone_masked="+15125****",
            source="webform",
            state="qualifying",
            score=75,
            service_type="AC Repair",
            urgency="high",
            first_response_ms=5000,
            total_messages=3,
            created_at=NOW,
        )
        assert lead.id == "lead-123"
        assert lead.score == 75
        assert lead.total_messages == 3

    def test_minimal_lead_summary(self):
        """Lead summary with only required fields."""
        lead = LeadSummary(
            id="lead-456",
            phone_masked="+15125****",
            source="angi",
            state="new",
            score=0,
            created_at=NOW,
        )
        assert lead.first_name is None
        assert lead.last_name is None
        assert lead.service_type is None
        assert lead.urgency is None
        assert lead.first_response_ms is None
        assert lead.total_messages == 0

    def test_missing_required_fields_raises(self):
        """Missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            LeadSummary(id="lead-1")


# ---------------------------------------------------------------------------
# LeadListResponse
# ---------------------------------------------------------------------------


class TestLeadListResponse:
    def test_valid_lead_list(self):
        """Lead list with pagination metadata."""
        lead = LeadSummary(
            id="lead-1",
            phone_masked="+1512****",
            source="web",
            state="new",
            score=50,
            created_at=NOW,
        )
        response = LeadListResponse(
            leads=[lead],
            total=100,
            page=1,
            pages=10,
        )
        assert len(response.leads) == 1
        assert response.total == 100
        assert response.pages == 10

    def test_empty_lead_list(self):
        """Empty lead list is valid."""
        response = LeadListResponse(leads=[], total=0, page=1, pages=0)
        assert len(response.leads) == 0


# ---------------------------------------------------------------------------
# MessageSummary
# ---------------------------------------------------------------------------


class TestMessageSummary:
    def test_outbound_message(self):
        """Outbound SMS message."""
        msg = MessageSummary(
            id="msg-1",
            direction="outbound",
            agent_id="intake_agent",
            content="Hi, thanks for reaching out!",
            delivery_status="delivered",
            created_at=NOW,
        )
        assert msg.direction == "outbound"
        assert msg.agent_id == "intake_agent"

    def test_inbound_message(self):
        """Inbound SMS message has no agent."""
        msg = MessageSummary(
            id="msg-2",
            direction="inbound",
            content="I need AC repair",
            created_at=NOW,
        )
        assert msg.agent_id is None
        assert msg.delivery_status == "sent"  # default

    def test_missing_required_fields(self):
        """Missing required content or direction raises error."""
        with pytest.raises(ValidationError):
            MessageSummary(id="msg-3", created_at=NOW)


# ---------------------------------------------------------------------------
# BookingDetail
# ---------------------------------------------------------------------------


class TestBookingDetail:
    def test_full_booking(self):
        """Booking with all optional fields."""
        booking = BookingDetail(
            id="book-1",
            appointment_date="2025-06-15",
            time_window_start="09:00",
            time_window_end="11:00",
            service_type="AC Repair",
            tech_name="Mike",
            status="confirmed",
            crm_sync_status="synced",
        )
        assert booking.appointment_date == "2025-06-15"
        assert booking.tech_name == "Mike"

    def test_minimal_booking(self):
        """Booking with only required fields."""
        booking = BookingDetail(
            id="book-2",
            appointment_date="2025-06-15",
            service_type="Plumbing",
            status="pending",
            crm_sync_status="pending",
        )
        assert booking.time_window_start is None
        assert booking.time_window_end is None
        assert booking.tech_name is None


# ---------------------------------------------------------------------------
# ConsentDetail
# ---------------------------------------------------------------------------


class TestConsentDetail:
    def test_active_consent(self):
        """Active consent record."""
        consent = ConsentDetail(
            id="consent-1",
            consent_type="sms",
            consent_method="webform_submission",
            is_active=True,
            opted_out=False,
            created_at=NOW,
        )
        assert consent.is_active is True
        assert consent.opted_out is False

    def test_opted_out_consent(self):
        """Opted-out consent record."""
        consent = ConsentDetail(
            id="consent-2",
            consent_type="sms",
            consent_method="reply_stop",
            is_active=False,
            opted_out=True,
            created_at=NOW,
        )
        assert consent.opted_out is True


# ---------------------------------------------------------------------------
# EventSummary
# ---------------------------------------------------------------------------


class TestEventSummary:
    def test_event_with_all_fields(self):
        """Event with optional fields."""
        event = EventSummary(
            id="event-1",
            action="sms_sent",
            status="success",
            message="Intake response sent",
            duration_ms=1500,
            created_at=NOW,
        )
        assert event.action == "sms_sent"
        assert event.duration_ms == 1500

    def test_minimal_event(self):
        """Event with only required fields."""
        event = EventSummary(
            id="event-2",
            action="lead_created",
            status="success",
            created_at=NOW,
        )
        assert event.message is None
        assert event.duration_ms is None


# ---------------------------------------------------------------------------
# LeadDetailResponse
# ---------------------------------------------------------------------------


class TestLeadDetailResponse:
    def test_full_detail_response(self):
        """Full lead detail with conversations, booking, consent, events."""
        lead = LeadSummary(
            id="lead-1", phone_masked="+1****", source="web",
            state="booked", score=90, created_at=NOW,
        )
        msg = MessageSummary(
            id="msg-1", direction="outbound", content="Hi!", created_at=NOW,
        )
        booking = BookingDetail(
            id="b-1", appointment_date="2025-06-15",
            service_type="HVAC", status="confirmed", crm_sync_status="synced",
        )
        consent = ConsentDetail(
            id="c-1", consent_type="sms", consent_method="webform",
            is_active=True, opted_out=False, created_at=NOW,
        )
        event = EventSummary(
            id="e-1", action="sms_sent", status="success", created_at=NOW,
        )

        detail = LeadDetailResponse(
            lead=lead,
            conversations=[msg],
            booking=booking,
            consent=consent,
            events=[event],
        )

        assert detail.lead.id == "lead-1"
        assert len(detail.conversations) == 1
        assert detail.booking is not None
        assert detail.consent is not None
        assert len(detail.events) == 1

    def test_detail_without_optional_fields(self):
        """Lead detail without booking or consent."""
        lead = LeadSummary(
            id="lead-2", phone_masked="+1****", source="web",
            state="new", score=0, created_at=NOW,
        )
        detail = LeadDetailResponse(
            lead=lead, conversations=[], events=[],
        )
        assert detail.booking is None
        assert detail.consent is None
        assert len(detail.conversations) == 0


# ---------------------------------------------------------------------------
# DayMetric
# ---------------------------------------------------------------------------


class TestDayMetric:
    def test_full_metric(self):
        """Day metric with booked count."""
        metric = DayMetric(date="2025-06-15", count=10, booked=3)
        assert metric.count == 10
        assert metric.booked == 3

    def test_defaults(self):
        """Day metric defaults booked to 0."""
        metric = DayMetric(date="2025-06-15", count=5)
        assert metric.booked == 0


# ---------------------------------------------------------------------------
# ResponseTimeBucket
# ---------------------------------------------------------------------------


class TestResponseTimeBucket:
    def test_valid_bucket(self):
        """Response time bucket."""
        bucket = ResponseTimeBucket(bucket="<10s", count=42)
        assert bucket.bucket == "<10s"
        assert bucket.count == 42


# ---------------------------------------------------------------------------
# DashboardMetrics
# ---------------------------------------------------------------------------


class TestDashboardMetrics:
    def test_all_defaults(self):
        """DashboardMetrics with all defaults."""
        metrics = DashboardMetrics()
        assert metrics.total_leads == 0
        assert metrics.total_booked == 0
        assert metrics.conversion_rate == 0.0
        assert metrics.avg_response_time_ms == 0
        assert metrics.leads_under_60s == 0
        assert metrics.leads_under_60s_pct == 0.0
        assert metrics.total_messages == 0
        assert metrics.total_ai_cost == 0.0
        assert metrics.total_sms_cost == 0.0
        assert metrics.leads_by_source == {}
        assert metrics.leads_by_state == {}
        assert metrics.leads_by_day == []
        assert metrics.response_time_distribution == []
        assert metrics.conversion_by_source == {}

    def test_populated_metrics(self):
        """DashboardMetrics with real data."""
        day = DayMetric(date="2025-06-15", count=10, booked=3)
        bucket = ResponseTimeBucket(bucket="<10s", count=42)

        metrics = DashboardMetrics(
            total_leads=150,
            total_booked=45,
            conversion_rate=30.0,
            avg_response_time_ms=8500,
            leads_under_60s=140,
            leads_under_60s_pct=93.3,
            total_messages=500,
            total_ai_cost=12.50,
            total_sms_cost=8.75,
            leads_by_source={"webform": 100, "angi": 50},
            leads_by_state={"new": 20, "qualifying": 30},
            leads_by_day=[day],
            response_time_distribution=[bucket],
            conversion_by_source={"webform": 35.0},
        )
        assert metrics.total_leads == 150
        assert metrics.conversion_rate == 30.0
        assert len(metrics.leads_by_day) == 1
        assert len(metrics.response_time_distribution) == 1


# ---------------------------------------------------------------------------
# ActivityEvent
# ---------------------------------------------------------------------------


class TestActivityEvent:
    def test_lead_created_event(self):
        """Lead created activity event."""
        event = ActivityEvent(
            type="lead_created",
            lead_id="lead-123",
            message="New lead from webform",
            timestamp=NOW,
        )
        assert event.type == "lead_created"
        assert event.lead_id == "lead-123"

    def test_event_without_lead_id(self):
        """Activity event without lead_id."""
        event = ActivityEvent(
            type="system_alert",
            message="Twilio balance low",
            timestamp=NOW,
        )
        assert event.lead_id is None

    def test_missing_required_fields(self):
        """Missing type or message raises error."""
        with pytest.raises(ValidationError):
            ActivityEvent(timestamp=NOW)


# ---------------------------------------------------------------------------
# ComplianceSummary
# ---------------------------------------------------------------------------


class TestComplianceSummary:
    def test_all_defaults(self):
        """ComplianceSummary with all defaults."""
        summary = ComplianceSummary()
        assert summary.total_consent_records == 0
        assert summary.opted_out_count == 0
        assert summary.messages_in_quiet_hours == 0
        assert summary.cold_outreach_violations == 0
        assert summary.pending_followups == 0
        assert summary.last_audit is None

    def test_populated_compliance(self):
        """ComplianceSummary with real data."""
        summary = ComplianceSummary(
            total_consent_records=500,
            opted_out_count=12,
            messages_in_quiet_hours=0,
            cold_outreach_violations=0,
            pending_followups=8,
            last_audit=NOW,
        )
        assert summary.total_consent_records == 500
        assert summary.opted_out_count == 12
        assert summary.last_audit is not None


# ---------------------------------------------------------------------------
# WebhookPayloadResponse
# ---------------------------------------------------------------------------


class TestWebhookPayloadResponse:
    def test_defaults(self):
        """WebhookPayloadResponse with all defaults."""
        resp = WebhookPayloadResponse()
        assert resp.status == "accepted"
        assert resp.lead_id is None
        assert resp.message == "Lead received"

    def test_custom_values(self):
        """WebhookPayloadResponse with custom values."""
        resp = WebhookPayloadResponse(
            status="accepted",
            lead_id="lead-999",
            message="Lead queued for processing",
        )
        assert resp.lead_id == "lead-999"
        assert resp.message == "Lead queued for processing"

    def test_serialization(self):
        """WebhookPayloadResponse serializes to dict correctly."""
        resp = WebhookPayloadResponse(lead_id="lead-1")
        data = resp.model_dump()
        assert data["status"] == "accepted"
        assert data["lead_id"] == "lead-1"
        assert data["message"] == "Lead received"
