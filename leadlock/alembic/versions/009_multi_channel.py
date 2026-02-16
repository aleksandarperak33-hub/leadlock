"""Multi-channel: outreach_sms table

Revision ID: 009
Revises: 008
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outreach_sms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "outreach_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outreach.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("from_phone", sa.String(20), nullable=False),
        sa.Column("to_phone", sa.String(20), nullable=False),
        sa.Column("twilio_sid", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), server_default="queued"),
        sa.Column("cost_usd", sa.Float, server_default="0.0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_outreach_sms_outreach_id", "outreach_sms", ["outreach_id"])
    op.create_index("ix_outreach_sms_status", "outreach_sms", ["status"])


def downgrade() -> None:
    op.drop_index("ix_outreach_sms_status", table_name="outreach_sms")
    op.drop_index("ix_outreach_sms_outreach_id", table_name="outreach_sms")
    op.drop_table("outreach_sms")
