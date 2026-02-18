"""
Consent record model — TCPA compliance requires tracking exactly how consent was obtained.
Records must be retained for 5 years (FTC TSR 2024).

Consent types:
- PEC (Prior Express Consent): Customer initiated contact → allows informational SMS
- PEWC (Prior Express Written Consent): Explicit opt-in → allows marketing SMS
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )

    # Consent type and status
    consent_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # pec, pewc
    consent_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # text_in, web_form, google_lsa, angi, facebook, missed_call, verbal, written
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Opt-out tracking
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    opted_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    opt_out_method: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # sms_stop, manual, api

    # Legal record — raw evidence of how consent was obtained
    consent_text: Mapped[Optional[str]] = mapped_column(
        Text
    )  # The actual opt-in message or form text
    consent_url: Mapped[Optional[str]] = mapped_column(
        Text
    )  # URL of the form where consent was given
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    # Raw data for legal disputes
    raw_consent_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Timestamps — 5-year retention required
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_consent_phone_client", "phone", "client_id"),
        Index("ix_consent_opted_out", "opted_out"),
    )

    def __repr__(self) -> str:
        masked = self.phone[:6] + "***" if self.phone else "unknown"
        return f"<ConsentRecord {masked} type={self.consent_type} active={self.is_active}>"
