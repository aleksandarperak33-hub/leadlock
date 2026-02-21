"""
SalesEngineConfig model - singleton config row for the sales engine.
Admin-editable from the dashboard. Controls all automation behavior.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Boolean, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class SalesEngineConfig(Base):
    __tablename__ = "sales_engine_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Master switch
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    # Targeting
    target_trade_types: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list
    )  # ["hvac", "plumbing", "roofing"]
    target_locations: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list
    )  # [{"city": "Austin", "state": "TX"}, ...]

    # Limits
    daily_email_limit: Mapped[int] = mapped_column(Integer, default=50)
    daily_scrape_limit: Mapped[int] = mapped_column(Integer, default=100)

    # Sequence settings
    sequence_delay_hours: Mapped[int] = mapped_column(Integer, default=48)
    max_sequence_steps: Mapped[int] = mapped_column(Integer, default=3)

    # Email sender config
    from_email: Mapped[Optional[str]] = mapped_column(String(255))
    from_name: Mapped[Optional[str]] = mapped_column(String(100))
    sender_name: Mapped[Optional[str]] = mapped_column(String(50))  # Human first name for sign-off (e.g. "Alek")
    reply_to_email: Mapped[Optional[str]] = mapped_column(String(255))
    company_address: Mapped[Optional[str]] = mapped_column(String(500))

    # Booking / demo config
    booking_url: Mapped[Optional[str]] = mapped_column(String(500))  # Cal.com or Calendly link

    # SMS after email reply
    sms_after_email_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_from_phone: Mapped[Optional[str]] = mapped_column(String(20))

    # Custom email templates (overrides AI generation)
    email_templates: Mapped[Optional[dict]] = mapped_column(JSONB)

    # --- Phase 1B: Continuous scraper config ---
    scraper_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    variant_cooldown_days: Mapped[int] = mapped_column(Integer, default=7)

    # --- Phase 1C: Business hours gating ---
    send_hours_start: Mapped[str] = mapped_column(String(5), default="08:00")
    send_hours_end: Mapped[str] = mapped_column(String(5), default="18:00")
    send_timezone: Mapped[str] = mapped_column(String(50), default="America/Chicago")
    send_weekdays_only: Mapped[bool] = mapped_column(Boolean, default=True)

    # --- Phase 3: Worker controls & budget ---
    scraper_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    sequencer_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    cleanup_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_budget_usd: Mapped[Optional[float]] = mapped_column(Float)
    budget_alert_threshold: Mapped[float] = mapped_column(Float, default=0.8)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<SalesEngineConfig active={self.is_active}>"
