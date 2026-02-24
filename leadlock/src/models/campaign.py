"""
Campaign model - defines outreach campaigns with targeting and sequence configuration.
Campaigns group prospects by trade/location and define multi-step outreach sequences.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False
    )  # draft, active, paused, completed

    # Targeting
    target_trades: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list
    )  # ["hvac", "plumbing"]
    target_locations: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list
    )  # [{"city": "Austin", "state": "TX"}]
    target_filters: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=dict
    )  # {"min_rating": 4.0, "has_website": true}

    # Sequence definition
    sequence_steps: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list
    )  # [{"step": 1, "channel": "email", "delay_hours": 0, "template_id": "..."}, ...]

    # Limits & metrics
    daily_limit: Mapped[int] = mapped_column(Integer, default=25)
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_opened: Mapped[int] = mapped_column(Integer, default=0)
    total_replied: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_campaigns_tenant_id", "tenant_id"),
        Index("ix_campaigns_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Campaign {self.name} ({self.status})>"
