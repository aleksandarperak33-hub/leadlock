"""
API response schemas for the dashboard and admin endpoints.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    client_id: str
    business_name: str
    is_admin: bool = False


class LeadSummary(BaseModel):
    id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_masked: str
    source: str
    state: str
    score: int
    service_type: Optional[str] = None
    urgency: Optional[str] = None
    first_response_ms: Optional[int] = None
    total_messages: int = 0
    created_at: datetime


class LeadListResponse(BaseModel):
    leads: list[LeadSummary]
    total: int
    page: int
    pages: int


class MessageSummary(BaseModel):
    id: str
    direction: str
    agent_id: Optional[str] = None
    content: str
    delivery_status: str = "sent"
    created_at: datetime


class BookingDetail(BaseModel):
    id: str
    appointment_date: str
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None
    service_type: str
    tech_name: Optional[str] = None
    status: str
    crm_sync_status: str


class ConsentDetail(BaseModel):
    id: str
    consent_type: str
    consent_method: str
    is_active: bool
    opted_out: bool
    created_at: datetime


class EventSummary(BaseModel):
    id: str
    action: str
    status: str
    message: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: datetime


class LeadDetailResponse(BaseModel):
    lead: LeadSummary
    conversations: list[MessageSummary]
    booking: Optional[BookingDetail] = None
    consent: Optional[ConsentDetail] = None
    events: list[EventSummary]


class DayMetric(BaseModel):
    date: str
    count: int
    booked: int = 0


class ResponseTimeBucket(BaseModel):
    bucket: str
    count: int


class DashboardMetrics(BaseModel):
    total_leads: int = 0
    total_booked: int = 0
    conversion_rate: float = 0.0
    avg_response_time_ms: int = 0
    leads_under_60s: int = 0
    leads_under_60s_pct: float = 0.0
    total_messages: int = 0
    total_ai_cost: float = 0.0
    total_sms_cost: float = 0.0
    leads_by_source: dict = Field(default_factory=dict)
    leads_by_state: dict = Field(default_factory=dict)
    leads_by_day: list[DayMetric] = Field(default_factory=list)
    response_time_distribution: list[ResponseTimeBucket] = Field(default_factory=list)
    conversion_by_source: dict = Field(default_factory=dict)


class ActivityEvent(BaseModel):
    type: str  # lead_created, sms_sent, sms_received, booking_confirmed, opt_out
    lead_id: Optional[str] = None
    message: str
    timestamp: datetime


class ComplianceSummary(BaseModel):
    total_consent_records: int = 0
    opted_out_count: int = 0
    messages_in_quiet_hours: int = 0
    cold_outreach_violations: int = 0
    pending_followups: int = 0
    last_audit: Optional[datetime] = None


class WebhookPayloadResponse(BaseModel):
    """Standard webhook response."""
    status: str = "accepted"
    lead_id: Optional[str] = None
    message: str = "Lead received"
