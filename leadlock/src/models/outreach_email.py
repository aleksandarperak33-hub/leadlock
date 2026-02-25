"""
OutreachEmail model - tracks individual emails in outreach sequences.
Records both outbound (sent by sales engine) and inbound (replies from prospects).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class OutreachEmail(Base):
    __tablename__ = "outreach_emails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    outreach_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach.id", ondelete="CASCADE"), nullable=False
    )

    direction: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # outbound, inbound

    subject: Mapped[Optional[str]] = mapped_column(String(500))
    body_html: Mapped[Optional[str]] = mapped_column(Text)
    body_text: Mapped[Optional[str]] = mapped_column(Text)
    from_email: Mapped[Optional[str]] = mapped_column(String(255))
    to_email: Mapped[Optional[str]] = mapped_column(String(255))

    sendgrid_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    sequence_step: Mapped[int] = mapped_column(Integer, default=0)

    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    bounced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    bounce_type: Mapped[Optional[str]] = mapped_column(String(30))  # bounce, blocked, deferred
    bounce_reason: Mapped[Optional[str]] = mapped_column(Text)

    ai_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Whether the deterministic fallback template was used instead of AI
    fallback_used: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    # A/B test variant assignment
    ab_variant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ab_test_variants.id", ondelete="SET NULL"),
        nullable=True,
    )

    # CTA variant for lightweight A/B tests (e.g. "calendar" vs "question")
    cta_variant: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_outreach_emails_outreach_id", "outreach_id"),
        Index("ix_outreach_emails_sendgrid_id", "sendgrid_message_id"),
        Index("ix_outreach_emails_direction", "direction"),
    )

    def __repr__(self) -> str:
        return f"<OutreachEmail {self.direction} step={self.sequence_step}>"
