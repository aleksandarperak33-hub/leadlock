"""
Competitive intelligence model - stores competitor analysis snapshots.
One-Writer: competitive_intel worker.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Float, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class CompetitiveIntel(Base):
    __tablename__ = "competitive_intel"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    competitor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    competitor_url: Mapped[str] = mapped_column(String(500), nullable=False)
    pricing_summary: Mapped[Optional[str]] = mapped_column(Text)
    features_summary: Mapped[Optional[str]] = mapped_column(Text)
    positioning_summary: Mapped[Optional[str]] = mapped_column(Text)
    battle_card: Mapped[Optional[str]] = mapped_column(Text)
    changes_from_previous: Mapped[Optional[str]] = mapped_column(Text)
    raw_analysis: Mapped[Optional[dict]] = mapped_column(JSONB)
    ai_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_competitive_intel_competitor", "competitor_name"),
        Index("ix_competitive_intel_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<CompetitiveIntel {self.competitor_name}>"
