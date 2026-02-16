"""
Outreach model — tracks LeadLock's own sales pipeline.
Each record is a prospective client being pursued.
"""
import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Text, Float, DateTime, Date, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class Outreach(Base):
    __tablename__ = "outreach"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Prospect info
    prospect_name: Mapped[str] = mapped_column(String(200), nullable=False)
    prospect_company: Mapped[Optional[str]] = mapped_column(String(200))
    prospect_email: Mapped[Optional[str]] = mapped_column(String(255))
    prospect_phone: Mapped[Optional[str]] = mapped_column(String(20))
    prospect_trade_type: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # hvac, plumbing, roofing, electrical, solar, general

    # Pipeline
    status: Mapped[str] = mapped_column(
        String(30), default="cold", nullable=False
    )  # cold, contacted, demo_scheduled, demo_completed, proposal_sent, won, lost

    notes: Mapped[Optional[str]] = mapped_column(Text)
    estimated_mrr: Mapped[Optional[float]] = mapped_column(Float)
    demo_date: Mapped[Optional[date]] = mapped_column(Date)
    converted_client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_outreach_status", "status"),
        Index("ix_outreach_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Outreach {self.prospect_name} ({self.status})>"
