"""Add fallback_used column to outreach_emails

Revision ID: 021
Revises: 020
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outreach_emails",
        sa.Column(
            "fallback_used",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("outreach_emails", "fallback_used")
