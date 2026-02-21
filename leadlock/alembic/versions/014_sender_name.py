"""Add sender_name to sales_engine_config

Revision ID: 014
Revises: 013
Create Date: 2026-02-21
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales_engine_config",
        sa.Column("sender_name", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sales_engine_config", "sender_name")
