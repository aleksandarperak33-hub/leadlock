"""
Event log model — complete audit trail for every significant action.
Used for debugging, compliance audits, and performance analysis.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id")
    )
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id")
    )

    # Event details
    action: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # lead_created, sms_sent, sms_received, ai_generated, booking_confirmed, etc.
    status: Mapped[str] = mapped_column(
        String(20), default="success"
    )  # success, failure, skipped, error
    agent_id: Mapped[Optional[str]] = mapped_column(String(30))

    # Performance
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float)

    # Details
    message: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_code: Mapped[Optional[str]] = mapped_column(String(50))

    # Context data
    data: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    lead: Mapped[Optional["Lead"]] = relationship(back_populates="events")

    __table_args__ = (
        Index("ix_events_lead_id", "lead_id"),
        Index("ix_events_client_id", "client_id"),
        Index("ix_events_action", "action"),
        Index("ix_events_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<EventLog {self.action} status={self.status}>"
