"""
Outreach model — tracks LeadLock's own sales pipeline.
Each record is a prospective client being pursued.
Extended with sales engine automation columns for scraping and email sequences.
"""
import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, Date, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
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

    # --- Sales engine automation columns ---

    # Source tracking
    source: Mapped[Optional[str]] = mapped_column(String(50))  # google_maps, yelp, manual
    source_place_id: Mapped[Optional[str]] = mapped_column(String(255))  # dedup key
    website: Mapped[Optional[str]] = mapped_column(String(500))

    # Business details from scraping
    google_rating: Mapped[Optional[float]] = mapped_column(Float)
    review_count: Mapped[Optional[int]] = mapped_column(Integer)
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state_code: Mapped[Optional[str]] = mapped_column(String(2))
    zip_code: Mapped[Optional[str]] = mapped_column(String(10))

    # Email enrichment
    email_verified: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    email_source: Mapped[Optional[str]] = mapped_column(String(50))  # hunter, website_scrape, pattern_guess

    # Outreach sequence tracking
    outreach_sequence_step: Mapped[int] = mapped_column(Integer, default=0)
    last_email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_email_opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_email_clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_email_replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    total_emails_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # CAN-SPAM compliance
    email_unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Raw enrichment data
    enrichment_data: Mapped[Optional[dict]] = mapped_column(JSONB)

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
        Index("ix_outreach_source_place_id", "source_place_id", unique=True,
              postgresql_where="source_place_id IS NOT NULL"),
        Index("ix_outreach_sequence_step", "outreach_sequence_step"),
    )

    def __repr__(self) -> str:
        return f"<Outreach {self.prospect_name} ({self.status})>"
