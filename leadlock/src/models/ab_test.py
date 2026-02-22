"""
A/B test models - experiments and variants for email subject line testing.
One-Writer: ab_test_engine worker creates experiments, outreach_sequencer reads them.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ABTestExperiment(Base):
    __tablename__ = "ab_test_experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )  # active, completed, cancelled
    sequence_step: Mapped[int] = mapped_column(Integer, nullable=False)
    target_trade: Mapped[Optional[str]] = mapped_column(String(50))  # NULL = all trades
    min_sample_per_variant: Mapped[int] = mapped_column(Integer, default=30)
    winning_variant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_ab_test_experiments_status", "status"),
        Index("ix_ab_test_experiments_step", "sequence_step"),
    )

    def __repr__(self) -> str:
        return f"<ABTestExperiment {self.name} ({self.status})>"


class ABTestVariant(Base):
    __tablename__ = "ab_test_variants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ab_test_experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_label: Mapped[str] = mapped_column(String(10), nullable=False)  # "A", "B", "C"
    subject_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_opened: Mapped[int] = mapped_column(Integer, default=0)
    total_replied: Mapped[int] = mapped_column(Integer, default=0)
    open_rate: Mapped[float] = mapped_column(Float, default=0.0)
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_ab_test_variants_experiment", "experiment_id"),
    )

    def __repr__(self) -> str:
        return f"<ABTestVariant {self.variant_label} sent={self.total_sent} open_rate={self.open_rate:.1%}>"
