"""
Lead model - every inbound lead from any source.
Tracks full lifecycle: new → intake_sent → qualifying → qualified → booking → booked → completed.
Terminal states: cold → dead, opted_out.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )

    # Contact info
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_national: Mapped[Optional[str]] = mapped_column(String(20))
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    address: Mapped[Optional[str]] = mapped_column(Text)
    zip_code: Mapped[Optional[str]] = mapped_column(String(10))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state_code: Mapped[Optional[str]] = mapped_column(String(2))

    # Lead source and lifecycle
    source: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # google_lsa, angi, website, missed_call, text_in, facebook, thumbtack, referral, yelp
    source_lead_id: Mapped[Optional[str]] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(30), default="new", nullable=False)
    previous_state: Mapped[Optional[str]] = mapped_column(String(30))

    # Qualification data
    score: Mapped[int] = mapped_column(Integer, default=50)
    service_type: Mapped[Optional[str]] = mapped_column(String(100))
    urgency: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # emergency, today, this_week, flexible, just_quote
    property_type: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # residential, commercial
    budget_range: Mapped[Optional[str]] = mapped_column(String(50))
    problem_description: Mapped[Optional[str]] = mapped_column(Text)
    qualification_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # AI agent tracking
    current_agent: Mapped[Optional[str]] = mapped_column(
        String(30)
    )  # intake, qualify, book, followup
    conversation_turn: Mapped[int] = mapped_column(Integer, default=0)
    last_agent_response: Mapped[Optional[str]] = mapped_column(Text)

    # Phone intelligence
    phone_type: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # mobile, landline, voip, unknown
    carrier: Mapped[Optional[str]] = mapped_column(String(100))

    # Consent
    consent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consent_records.id")
    )

    # Emergency flag
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    emergency_type: Mapped[Optional[str]] = mapped_column(String(50))

    # Performance tracking
    first_response_ms: Mapped[Optional[int]] = mapped_column(Integer)
    total_messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_messages_received: Mapped[int] = mapped_column(Integer, default=0)
    total_ai_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_sms_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Follow-up tracking
    cold_outreach_count: Mapped[int] = mapped_column(Integer, default=0)
    last_outbound_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_inbound_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Phase 2: Lead actions
    tags: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    extra_data: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    client: Mapped["Client"] = relationship(back_populates="leads")
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="lead", lazy="select", order_by="Conversation.created_at"
    )
    booking: Mapped[Optional["Booking"]] = relationship(
        back_populates="lead", uselist=False, lazy="select"
    )
    consent: Mapped[Optional["ConsentRecord"]] = relationship(lazy="select")
    followup_tasks: Mapped[list["FollowupTask"]] = relationship(
        back_populates="lead", lazy="select"
    )
    events: Mapped[list["EventLog"]] = relationship(
        back_populates="lead", lazy="select", order_by="EventLog.created_at"
    )

    __table_args__ = (
        Index("ix_leads_client_id", "client_id"),
        Index("ix_leads_phone", "phone"),
        Index("ix_leads_state", "state"),
        Index("ix_leads_source", "source"),
        Index("ix_leads_created_at", "created_at"),
        Index("ix_leads_client_phone", "client_id", "phone"),
        Index("ix_leads_next_followup", "next_followup_at"),
    )

    def __repr__(self) -> str:
        masked = self.phone[:6] + "***" if self.phone else "unknown"
        return f"<Lead {masked} state={self.state}>"
