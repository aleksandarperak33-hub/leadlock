"""
Client model - represents a home services business using LeadLock.
Stores business config as JSONB for flexible schema (persona, hours, services, etc.).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, Float, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # hvac, plumbing, roofing, electrical, solar, general
    tier: Mapped[str] = mapped_column(
        String(50), default="starter"
    )  # starter, pro, business
    monthly_fee: Mapped[float] = mapped_column(Float, default=497.00)

    # Twilio / 10DLC
    twilio_phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True)
    twilio_phone_sid: Mapped[Optional[str]] = mapped_column(String(50))
    twilio_messaging_service_sid: Mapped[Optional[str]] = mapped_column(String(100))
    ten_dlc_brand_id: Mapped[Optional[str]] = mapped_column(String(50))
    ten_dlc_campaign_id: Mapped[Optional[str]] = mapped_column(String(50))
    ten_dlc_status: Mapped[str] = mapped_column(String(30), default="pending")
    ten_dlc_profile_sid: Mapped[Optional[str]] = mapped_column(String(100))
    ten_dlc_verification_sid: Mapped[Optional[str]] = mapped_column(String(100))

    # Business registration (for 10DLC / toll-free verification)
    business_website: Mapped[Optional[str]] = mapped_column(String(255))
    business_type: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # sole_proprietorship, llc, corporation, partnership
    business_ein: Mapped[Optional[str]] = mapped_column(String(20))
    business_address: Mapped[Optional[dict]] = mapped_column(JSONB)

    # CRM
    crm_type: Mapped[str] = mapped_column(
        String(50), default="google_sheets"
    )  # servicetitan, housecallpro, jobber, gohighlevel, google_sheets
    crm_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    crm_tenant_id: Mapped[Optional[str]] = mapped_column(String(100))
    crm_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Full business configuration (persona, hours, services, team, etc.)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Billing
    billing_status: Mapped[str] = mapped_column(
        String(30), default="trial"
    )  # trial, pilot, active, paused, churned
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(100))
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Onboarding
    onboarding_status: Mapped[str] = mapped_column(
        String(30), default="pending"
    )  # pending, in_progress, testing, live
    owner_name: Mapped[Optional[str]] = mapped_column(String(100))
    owner_email: Mapped[Optional[str]] = mapped_column(String(255))
    owner_phone: Mapped[Optional[str]] = mapped_column(String(20))

    # Dashboard auth - hashed password for the client's dashboard login
    dashboard_email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    dashboard_password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Trial
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Admin flag - True for LeadLock operators who see the admin dashboard
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # Agency partner
    agency_partner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Timestamps
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    leads: Mapped[list["Lead"]] = relationship(back_populates="client", lazy="selectin")

    __table_args__ = (
        Index("ix_clients_trade_type", "trade_type"),
        Index("ix_clients_billing_status", "billing_status"),
        Index("ix_clients_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Client {self.business_name} ({self.trade_type})>"
