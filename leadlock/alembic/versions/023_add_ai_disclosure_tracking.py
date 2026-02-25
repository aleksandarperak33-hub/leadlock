"""Add AI disclosure tracking fields to leads

Revision ID: 023
Revises: 022
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("ai_disclosure_sent", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "leads",
        sa.Column("ai_disclosure_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "ai_disclosure_sent_at")
    op.drop_column("leads", "ai_disclosure_sent")
