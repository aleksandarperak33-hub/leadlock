"""
Follow-up task model — scheduled outbound messages.
Types: cold_nurture (max 3 per lead), day_before_reminder, review_request.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base


class FollowupTask(Base):
    __tablename__ = "followup_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )

    # Task type and scheduling
    task_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # cold_nurture, day_before_reminder, review_request, re_engage
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer, default=1
    )  # Which message in the sequence (1, 2, 3)

    # Execution
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, sent, skipped, failed, cancelled
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    skip_reason: Mapped[Optional[str]] = mapped_column(
        Text
    )  # quiet_hours, opted_out, max_reached, lead_responded

    # Message content (pre-generated or template reference)
    message_template: Mapped[Optional[str]] = mapped_column(String(100))
    message_content: Mapped[Optional[str]] = mapped_column(Text)

    # Retry tracking
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    extra_data: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="followup_tasks")

    __table_args__ = (
        Index("ix_followup_scheduled_at", "scheduled_at"),
        Index("ix_followup_status", "status"),
        Index("ix_followup_lead_id", "lead_id"),
        Index("ix_followup_client_id", "client_id"),
        Index("ix_followup_pending", "status", "scheduled_at"),
    )

    def __repr__(self) -> str:
        return f"<FollowupTask {self.task_type} #{self.sequence_number} status={self.status}>"
