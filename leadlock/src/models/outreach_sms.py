"""
OutreachSMS model — tracks SMS messages in the outreach pipeline.
SMS only triggers after email reply expressing interest (TCPA compliance).
Cold SMS to prospects without prior consent is illegal.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, Float, DateTime, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class OutreachSMS(Base):
    __tablename__ = "outreach_sms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    outreach_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outreach.id", ondelete="CASCADE"),
        nullable=False,
    )

    direction: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # outbound, inbound

    body: Mapped[str] = mapped_column(Text, nullable=False)

    from_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    to_phone: Mapped[str] = mapped_column(String(20), nullable=False)

    # Twilio tracking
    twilio_sid: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(20), default="queued"
    )  # queued, sent, delivered, failed, received

    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Timestamps
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_outreach_sms_outreach_id", "outreach_id"),
        Index("ix_outreach_sms_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<OutreachSMS {self.direction} to={self.to_phone[:6]}*** ({self.status})>"
