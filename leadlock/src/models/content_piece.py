"""
Content piece model - stores AI-generated marketing content.
One-Writer: content_factory worker creates, dashboard API updates status.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ContentPiece(Base):
    __tablename__ = "content_pieces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # blog_post, twitter, linkedin, reddit, lead_magnet
    title: Mapped[Optional[str]] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    target_trade: Mapped[Optional[str]] = mapped_column(String(50))
    target_keyword: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False
    )  # draft, approved, published, rejected
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    seo_meta: Mapped[Optional[str]] = mapped_column(String(320))
    ai_model: Mapped[Optional[str]] = mapped_column(String(50))
    ai_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    published_url: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_content_pieces_status", "status"),
        Index("ix_content_pieces_type", "content_type"),
        Index("ix_content_pieces_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ContentPiece {self.content_type}: {self.title} ({self.status})>"
