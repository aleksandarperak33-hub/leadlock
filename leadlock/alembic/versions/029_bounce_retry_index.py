"""Add partial composite index for bounce-retry email finder query.

Keeps the bounce-retry query fast as the lost bucket grows.
Index covers: (status, email_verified, email_discovery_attempted_at)
WHERE status = 'lost' AND email_verified = false.

Revision ID: 029
Revises: 028
Create Date: 2026-02-26
"""
from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_outreach_bounce_retry",
        "outreach",
        ["status", "email_verified", "email_discovery_attempted_at"],
        postgresql_where="status = 'lost' AND email_verified = false",
    )


def downgrade() -> None:
    op.drop_index("ix_outreach_bounce_retry", table_name="outreach")
