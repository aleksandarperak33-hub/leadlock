"""sales engine fixes: bounce fields, blacklist table, timezone config

Revision ID: 004
Revises: 003
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Add bounce fields to outreach_emails ---
    op.add_column("outreach_emails", sa.Column("bounce_type", sa.String(30), nullable=True))
    op.add_column("outreach_emails", sa.Column("bounce_reason", sa.Text(), nullable=True))

    # --- Add timezone to sales_engine_config ---
    op.add_column("sales_engine_config", sa.Column("timezone", sa.String(50), nullable=True))

    # --- Create email_blacklist table ---
    op.create_table(
        "email_blacklist",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_type", sa.String(10), nullable=False),
        sa.Column("value", sa.String(255), nullable=False, unique=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_email_blacklist_value", "email_blacklist", ["value"], unique=True)
    op.create_index("ix_email_blacklist_type", "email_blacklist", ["entry_type"])


def downgrade() -> None:
    op.drop_index("ix_email_blacklist_type", table_name="email_blacklist")
    op.drop_index("ix_email_blacklist_value", table_name="email_blacklist")
    op.drop_table("email_blacklist")

    op.drop_column("sales_engine_config", "timezone")

    op.drop_column("outreach_emails", "bounce_reason")
    op.drop_column("outreach_emails", "bounce_type")
