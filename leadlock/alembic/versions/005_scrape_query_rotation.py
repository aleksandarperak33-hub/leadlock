"""Add query rotation tracking to scrape_jobs

Revision ID: 005
Revises: 004
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scrape_jobs",
        sa.Column("query_variant", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "scrape_jobs",
        sa.Column("search_offset", sa.Integer(), nullable=False, server_default="0"),
    )
    # Index for fast lookup of used variant+offset combos per location+trade
    op.create_index(
        "ix_scrape_jobs_rotation",
        "scrape_jobs",
        ["city", "state_code", "trade_type", "query_variant", "search_offset"],
    )


def downgrade() -> None:
    op.drop_index("ix_scrape_jobs_rotation", table_name="scrape_jobs")
    op.drop_column("scrape_jobs", "search_offset")
    op.drop_column("scrape_jobs", "query_variant")
