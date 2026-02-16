"""add is_admin flag and outreach table

Revision ID: 002_add_admin_outreach
Revises: 001_initial_schema
Create Date: 2026-02-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_admin column to clients
    op.add_column("clients", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"))

    # Create outreach table
    op.create_table(
        "outreach",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("prospect_name", sa.String(200), nullable=False),
        sa.Column("prospect_company", sa.String(200), nullable=True),
        sa.Column("prospect_email", sa.String(255), nullable=True),
        sa.Column("prospect_phone", sa.String(20), nullable=True),
        sa.Column("prospect_trade_type", sa.String(50), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="cold"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("estimated_mrr", sa.Float(), nullable=True),
        sa.Column("demo_date", sa.Date(), nullable=True),
        sa.Column("converted_client_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_outreach_status", "outreach", ["status"])
    op.create_index("ix_outreach_created_at", "outreach", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_outreach_created_at", table_name="outreach")
    op.drop_index("ix_outreach_status", table_name="outreach")
    op.drop_table("outreach")
    op.drop_column("clients", "is_admin")
