"""
Referral models - tracking referral links and requests.
Skeleton for when first customers arrive.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ReferralLink(Base):
    __tablename__ = "referral_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    referral_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    total_clicks: Mapped[int] = mapped_column(Integer, default=0)
    total_signups: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_referral_links_client", "client_id"),
        Index("ix_referral_links_code", "referral_code", unique=True),
    )

    def __repr__(self) -> str:
        return f"<ReferralLink {self.referral_code}>"


class ReferralRequest(Base):
    __tablename__ = "referral_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    referral_link_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("referral_links.id"), nullable=True
    )
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, sent, clicked, converted
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_referral_requests_client", "client_id"),
    )

    def __repr__(self) -> str:
        return f"<ReferralRequest ({self.status})>"
