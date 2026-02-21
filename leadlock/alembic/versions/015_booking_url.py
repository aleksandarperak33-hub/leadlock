"""Add booking_url to sales_engine_config

Revision ID: 015
Revises: 014
Create Date: 2026-02-21
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales_engine_config",
        sa.Column("booking_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sales_engine_config", "booking_url")
