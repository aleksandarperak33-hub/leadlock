"""Add trial_ends_at and update billing_status for Stripe integration

Revision ID: 012
Revises: 011
Create Date: 2026-02-17
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "trial_ends_at")
