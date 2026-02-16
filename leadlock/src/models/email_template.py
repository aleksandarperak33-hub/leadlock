"""
EmailTemplate model — reusable email templates for outreach campaigns.
Can be static templates or AI-generation guidance.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    step_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # first_contact, followup, breakup, custom

    subject_template: Mapped[Optional[str]] = mapped_column(String(500))
    body_template: Mapped[Optional[str]] = mapped_column(Text)
    ai_instructions: Mapped[Optional[str]] = mapped_column(Text)

    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<EmailTemplate {self.name} ({self.step_type})>"
