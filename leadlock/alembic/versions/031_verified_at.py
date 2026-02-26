"""Add verified_at timestamp to outreach for email verification freshness.

Tracks when email_verified was last set to True. Prospects with stale
verification (older than 14 days) are re-verified by email_finder before
first-touch outreach, preventing bounces from stale email addresses.

Revision ID: 031
Revises: 030
Create Date: 2026-02-26
"""
import sqlalchemy as sa
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outreach",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outreach", "verified_at")
