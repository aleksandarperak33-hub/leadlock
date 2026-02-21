"""
Webhook event audit trail - every incoming webhook is recorded before processing.
Enables debugging, replay, and compliance auditing.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.database import Base


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    received_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    source = Column(String(50), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    payload_hash = Column(String(64), nullable=False, index=True)
    raw_payload = Column(JSONB, nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True, index=True)
    processing_status = Column(
        String(20), nullable=False, default="received", server_default="received"
    )
    error_message = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)
