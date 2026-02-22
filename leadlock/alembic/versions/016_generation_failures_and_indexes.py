"""Add generation_failures column and missing indexes

Revision ID: 016
Revises: 015
Create Date: 2026-02-21
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Generation failure tracking for outreach prospects
    op.add_column(
        "outreach",
        sa.Column("generation_failures", sa.Integer(), nullable=False, server_default="0"),
    )

    # Missing indexes for frequently queried columns
    # Note: bookings.crm_sync_status and followup_tasks(status, scheduled_at) already indexed
    op.create_index("ix_leads_consent_id", "leads", ["consent_id"])
    op.create_index("ix_outreach_prospect_email", "outreach", ["prospect_email"])


def downgrade() -> None:
    op.drop_index("ix_outreach_prospect_email", table_name="outreach")
    op.drop_index("ix_leads_consent_id", table_name="leads")
    op.drop_column("outreach", "generation_failures")
