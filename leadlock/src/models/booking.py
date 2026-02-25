"""
Booking model - confirmed appointments with CRM sync tracking.
"""
import uuid
from datetime import datetime, timezone, date, time
from typing import Optional
from sqlalchemy import String, Text, Boolean, Integer, DateTime, Date, Time, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, unique=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )

    # Appointment details
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_window_start: Mapped[Optional[time]] = mapped_column(Time)
    time_window_end: Mapped[Optional[time]] = mapped_column(Time)
    service_type: Mapped[str] = mapped_column(String(100), nullable=False)
    service_description: Mapped[Optional[str]] = mapped_column(Text)

    # Address (may differ from lead address)
    service_address: Mapped[Optional[str]] = mapped_column(Text)
    service_zip: Mapped[Optional[str]] = mapped_column(String(10))

    # Technician assignment
    tech_name: Mapped[Optional[str]] = mapped_column(String(100))
    tech_id: Mapped[Optional[str]] = mapped_column(String(100))

    # CRM sync
    crm_job_id: Mapped[Optional[str]] = mapped_column(String(100))
    crm_customer_id: Mapped[Optional[str]] = mapped_column(String(100))
    crm_sync_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, synced, failed, not_applicable
    crm_sync_error: Mapped[Optional[str]] = mapped_column(Text)
    crm_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="confirmed"
    )  # confirmed, completed, cancelled, no_show, rescheduled
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Reminders
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    same_day_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Review tracking
    review_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    review_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Metadata
    extra_data: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="booking")

    __table_args__ = (
        Index("ix_bookings_client_id", "client_id"),
        Index("ix_bookings_appointment_date", "appointment_date"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_crm_sync_status", "crm_sync_status"),
    )

    def __repr__(self) -> str:
        return f"<Booking {self.appointment_date} {self.service_type} status={self.status}>"
