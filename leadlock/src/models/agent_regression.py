"""
Agent regression model - tracks regressions identified by the reflection agent.
Injected into SOUL.md Regressions section for agent learning.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class AgentRegression(Base):
    __tablename__ = "agent_regressions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    regression_text: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), default="info", nullable=False
    )  # info, warning, critical
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_agent_regressions_agent", "agent_name"),
        Index("ix_agent_regressions_resolved", "resolved"),
    )

    def __repr__(self) -> str:
        return f"<AgentRegression {self.agent_name} ({self.severity})>"
