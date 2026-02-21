"""
Failed lead dead letter queue - captures leads that failed at any pipeline stage.
Supports retry with exponential backoff and manual resolution.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.database import Base


class FailedLead(Base):
    __tablename__ = "failed_leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_payload = Column(JSONB, nullable=False)
    source = Column(String(50), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True, index=True)
    error_message = Column(Text, nullable=False)
    error_traceback = Column(Text, nullable=True)
    failure_stage = Column(
        String(30), nullable=False, index=True
    )  # webhook, intake, qualify, book
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=5)
    next_retry_at = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(
        String(20), nullable=False, default="pending", server_default="pending", index=True
    )  # pending, retrying, resolved, dead
    correlation_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(100), nullable=True)
