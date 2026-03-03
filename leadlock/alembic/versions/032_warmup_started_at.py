"""Add warmup_started_at to sales_engine_config.

Persists the email warmup start date in the DB so it survives Redis
flushes and container restarts. Previously stored only in Redis, which
caused warmup day resets (day 15 → day 5) when the key was lost.

Revision ID: 032
Revises: 031
Create Date: 2026-03-03
"""
import sqlalchemy as sa
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales_engine_config",
        sa.Column("warmup_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sales_engine_config", "warmup_started_at")
