"""
Channel script model - stores generated outreach scripts for non-email channels.
One-Writer: channel_expander worker creates, dashboard API updates status.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ChannelScript(Base):
    __tablename__ = "channel_scripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    outreach_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outreach.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # linkedin_dm, cold_call, facebook_group
    script_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="generated", nullable=False
    )  # generated, sent, skipped
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ai_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_channel_scripts_outreach", "outreach_id"),
        Index("ix_channel_scripts_status", "status"),
        Index("ix_channel_scripts_channel", "channel"),
    )

    def __repr__(self) -> str:
        return f"<ChannelScript {self.channel} ({self.status})>"
