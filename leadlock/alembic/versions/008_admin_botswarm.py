"""Admin botswarm: campaigns, email_templates, outreach.campaign_id

Revision ID: 008
Revises: 007
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Campaigns table ---
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("target_trades", postgresql.JSONB, server_default="[]"),
        sa.Column("target_locations", postgresql.JSONB, server_default="[]"),
        sa.Column("target_filters", postgresql.JSONB, server_default="{}"),
        sa.Column("sequence_steps", postgresql.JSONB, server_default="[]"),
        sa.Column("daily_limit", sa.Integer, server_default="25"),
        sa.Column("total_sent", sa.Integer, server_default="0"),
        sa.Column("total_opened", sa.Integer, server_default="0"),
        sa.Column("total_replied", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    # --- Email Templates table ---
    op.create_table(
        "email_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("step_type", sa.String(30), nullable=False),
        sa.Column("subject_template", sa.String(500), nullable=True),
        sa.Column("body_template", sa.Text, nullable=True),
        sa.Column("ai_instructions", sa.Text, nullable=True),
        sa.Column("is_ai_generated", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- Outreach: add campaign_id ---
    op.add_column(
        "outreach",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outreach", "campaign_id")
    op.drop_table("email_templates")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")
