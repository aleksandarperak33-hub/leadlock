"""
WinningPattern model - stores proven email patterns from AB tests and reflection.
Core of the intelligence loop: what works feeds back into email generation.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class WinningPattern(Base):
    """Stores subject line instructions and patterns that have proven effective."""

    __tablename__ = "winning_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(30), nullable=False)  # "ab_test" or "reflection"
    source_id = Column(UUID(as_uuid=True), nullable=True)  # experiment_id or NULL
    pattern_type = Column(String(30), nullable=False, default="subject_instruction")
    instruction_text = Column(Text, nullable=False)
    trade = Column(String(50), nullable=True)  # NULL = all trades
    sequence_step = Column(Integer, nullable=True)  # NULL = all steps
    open_rate = Column(Float, nullable=False, default=0.0)
    reply_rate = Column(Float, nullable=False, default=0.0)
    sample_size = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=False, default=0.0)  # 0.0-1.0
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<WinningPattern source={self.source} trade={self.trade} "
            f"step={self.sequence_step} confidence={self.confidence:.2f}>"
        )
