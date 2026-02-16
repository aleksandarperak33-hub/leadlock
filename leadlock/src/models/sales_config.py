"""
SalesEngineConfig model — singleton config row for the sales engine.
Admin-editable from the dashboard. Controls all automation behavior.
"""
import uuid
from datetime import datetime
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
    reply_to_email: Mapped[Optional[str]] = mapped_column(String(255))
    company_address: Mapped[Optional[str]] = mapped_column(String(500))

    # SMS after email reply
    sms_after_email_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_from_phone: Mapped[Optional[str]] = mapped_column(String(20))

    # Custom email templates (overrides AI generation)
    email_templates: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<SalesEngineConfig active={self.is_active}>"
