"""
Agency partner model — referral partners who bring clients to LeadLock.
Revenue share: 25% of monthly fee for referred clients.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class AgencyPartner(Base):
    __tablename__ = "agency_partners"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20))

    # Revenue share
    revenue_share_pct: Mapped[float] = mapped_column(Float, default=25.0)
    total_referred_clients: Mapped[int] = mapped_column(Integer, default=0)
    total_revenue_shared: Mapped[float] = mapped_column(Float, default=0.0)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Metadata
    extra_data: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_agency_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<AgencyPartner {self.company_name}>"
