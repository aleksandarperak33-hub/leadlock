"""
Conversation model — every SMS message sent or received.
Complete audit trail with agent attribution, delivery status, and cost tracking.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )

    # Message details
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # inbound, outbound
    content: Mapped[str] = mapped_column(Text, nullable=False)
    from_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    to_phone: Mapped[str] = mapped_column(String(20), nullable=False)

    # Agent attribution — which AI agent generated this message
    agent_id: Mapped[Optional[str]] = mapped_column(
        String(30)
    )  # intake, qualify, book, followup
    agent_model: Mapped[Optional[str]] = mapped_column(String(50))  # claude-haiku, gpt-4o-mini

    # Delivery tracking
    sms_provider: Mapped[Optional[str]] = mapped_column(
        String(20)
    )  # twilio, telnyx
    sms_sid: Mapped[Optional[str]] = mapped_column(String(50))
    delivery_status: Mapped[str] = mapped_column(
        String(20), default="queued"
    )  # queued, sent, delivered, failed, undelivered
    delivery_error_code: Mapped[Optional[str]] = mapped_column(String(20))
    delivery_error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Segment counting for cost tracking
    segment_count: Mapped[int] = mapped_column(Integer, default=1)
    sms_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    ai_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # AI generation metadata
    ai_latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    ai_input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    ai_output_tokens: Mapped[Optional[int]] = mapped_column(Integer)

    # Metadata
    extra_data: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="conversations")

    __table_args__ = (
        Index("ix_conversations_lead_id", "lead_id"),
        Index("ix_conversations_client_id", "client_id"),
        Index("ix_conversations_created_at", "created_at"),
        Index("ix_conversations_sms_sid", "sms_sid"),
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.direction} agent={self.agent_id}>"
