"""Add email_discovery_attempted_at to outreach for tracking finder attempts

Revision ID: 024
Revises: 023
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outreach",
        sa.Column("email_discovery_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_outreach_email_discovery_attempted_at",
        "outreach",
        ["email_discovery_attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outreach_email_discovery_attempted_at", table_name="outreach")
    op.drop_column("outreach", "email_discovery_attempted_at")
