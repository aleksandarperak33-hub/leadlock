"""Add tos_accepted_at column, change billing_status default to pending

Revision ID: 020
Revises: 019
Create Date: 2026-02-23
"""
from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("tos_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Change server default for billing_status from 'trial' to 'pending'
    op.alter_column(
        "clients",
        "billing_status",
        server_default="pending",
    )


def downgrade() -> None:
    op.alter_column(
        "clients",
        "billing_status",
        server_default="trial",
    )
    op.drop_column("clients", "tos_accepted_at")
