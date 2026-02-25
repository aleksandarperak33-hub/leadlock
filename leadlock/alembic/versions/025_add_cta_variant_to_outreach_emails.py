"""Add cta_variant to outreach_emails for CTA A/B testing.

Revision ID: 025
Revises: 024
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outreach_emails",
        sa.Column("cta_variant", sa.String(30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outreach_emails", "cta_variant")
