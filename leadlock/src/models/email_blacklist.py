"""
EmailBlacklist model — prevents sending to specific emails or domains.
Used for manual blocks, competitor domains, and known-bad addresses.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class EmailBlacklist(Base):
    __tablename__ = "email_blacklist"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    entry_type: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # "email" or "domain"

    value: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )  # email address or domain

    reason: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_email_blacklist_value", "value", unique=True),
        Index("ix_email_blacklist_type", "entry_type"),
    )

    def __repr__(self) -> str:
        return f"<EmailBlacklist {self.entry_type}={self.value}>"
