"""
LearningSignal model — tracks what-works feedback loop.
Records positive/negative signals from email engagement, replies,
and bookings to feed back into email generation.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class LearningSignal(Base):
    __tablename__ = "learning_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    signal_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # email_opened, email_clicked, email_replied, email_bounced, demo_booked

    # Dimensional data for aggregation queries
    dimensions: Mapped[Optional[dict]] = mapped_column(
        JSONB
    )  # {"trade": "hvac", "city": "Austin", "state": "TX", "step": 1, "time_bucket": "9am-12pm", "day_of_week": "tuesday"}

    value: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # 1.0 positive, 0.0 negative

    outreach_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_learning_signals_type_created", "signal_type", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<LearningSignal {self.signal_type} value={self.value}>"
