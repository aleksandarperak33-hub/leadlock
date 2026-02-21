"""
TaskQueue model - event-driven task processing queue.
Supports delayed/scheduled tasks, retries with exponential backoff,
and priority-based processing.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Float, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class TaskQueue(Base):
    __tablename__ = "task_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    task_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # enrich_email, send_sequence, classify_reply, scrape_location, record_signal

    payload: Mapped[Optional[dict]] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, processing, completed, failed

    priority: Mapped[int] = mapped_column(
        Integer, default=5
    )  # 0=low, 5=normal, 10=high

    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    # Enables delayed/scheduled tasks
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    result_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_task_queue_processing", "status", "scheduled_at", "priority"),
    )

    def __repr__(self) -> str:
        return f"<TaskQueue {self.task_type} ({self.status})>"
