"""
ScrapeJob model — tracks what areas have been scraped and when.
Prevents re-scraping the same location too frequently.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Float, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    platform: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # google_maps, yelp

    trade_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location_query: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state_code: Mapped[Optional[str]] = mapped_column(String(2))

    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, running, completed, failed

    # Query rotation tracking — enables "never repeat" scraping
    query_variant: Mapped[int] = mapped_column(Integer, default=0)
    search_offset: Mapped[int] = mapped_column(Integer, default=0)

    results_found: Mapped[int] = mapped_column(Integer, default=0)
    new_prospects_created: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0)
    api_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_scrape_jobs_status", "status"),
        Index("ix_scrape_jobs_platform_location", "platform", "city", "state_code", "trade_type"),
    )

    def __repr__(self) -> str:
        return f"<ScrapeJob {self.platform} {self.location_query} ({self.status})>"
