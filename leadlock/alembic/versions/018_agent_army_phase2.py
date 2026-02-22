"""Agent army phase 2 - content pieces, channel scripts, competitive intel, referrals, regressions

Revision ID: 018
Revises: 017
Create Date: 2026-02-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Content pieces table
    op.create_table(
        "content_pieces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("target_trade", sa.String(50), nullable=True),
        sa.Column("target_keyword", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seo_meta", sa.String(320), nullable=True),
        sa.Column("ai_model", sa.String(50), nullable=True),
        sa.Column("ai_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("published_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_content_pieces_status", "content_pieces", ["status"])
    op.create_index("ix_content_pieces_type", "content_pieces", ["content_type"])
    op.create_index("ix_content_pieces_created", "content_pieces", ["created_at"])

    # Channel scripts table
    op.create_table(
        "channel_scripts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("outreach_id", UUID(as_uuid=True), sa.ForeignKey("outreach.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("script_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="generated"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_channel_scripts_outreach", "channel_scripts", ["outreach_id"])
    op.create_index("ix_channel_scripts_status", "channel_scripts", ["status"])
    op.create_index("ix_channel_scripts_channel", "channel_scripts", ["channel"])

    # Competitive intelligence table
    op.create_table(
        "competitive_intel",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("competitor_name", sa.String(100), nullable=False),
        sa.Column("competitor_url", sa.String(500), nullable=False),
        sa.Column("pricing_summary", sa.Text(), nullable=True),
        sa.Column("features_summary", sa.Text(), nullable=True),
        sa.Column("positioning_summary", sa.Text(), nullable=True),
        sa.Column("battle_card", sa.Text(), nullable=True),
        sa.Column("changes_from_previous", sa.Text(), nullable=True),
        sa.Column("raw_analysis", JSONB(), nullable=True),
        sa.Column("ai_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_competitive_intel_competitor", "competitive_intel", ["competitor_name"])
    op.create_index("ix_competitive_intel_created", "competitive_intel", ["created_at"])

    # Referral links table
    op.create_table(
        "referral_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("referral_code", sa.String(50), nullable=False, unique=True),
        sa.Column("total_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_signups", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_referral_links_client", "referral_links", ["client_id"])
    op.create_index("ix_referral_links_code", "referral_links", ["referral_code"], unique=True)

    # Referral requests table
    op.create_table(
        "referral_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("referral_link_id", UUID(as_uuid=True), sa.ForeignKey("referral_links.id"), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_referral_requests_client", "referral_requests", ["client_id"])

    # Agent regressions table
    op.create_table(
        "agent_regressions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("regression_text", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_regressions_agent", "agent_regressions", ["agent_name"])
    op.create_index("ix_agent_regressions_resolved", "agent_regressions", ["resolved"])


def downgrade() -> None:
    op.drop_index("ix_agent_regressions_resolved", table_name="agent_regressions")
    op.drop_index("ix_agent_regressions_agent", table_name="agent_regressions")
    op.drop_table("agent_regressions")
    op.drop_index("ix_referral_requests_client", table_name="referral_requests")
    op.drop_table("referral_requests")
    op.drop_index("ix_referral_links_code", table_name="referral_links")
    op.drop_index("ix_referral_links_client", table_name="referral_links")
    op.drop_table("referral_links")
    op.drop_index("ix_competitive_intel_created", table_name="competitive_intel")
    op.drop_index("ix_competitive_intel_competitor", table_name="competitive_intel")
    op.drop_table("competitive_intel")
    op.drop_index("ix_channel_scripts_channel", table_name="channel_scripts")
    op.drop_index("ix_channel_scripts_status", table_name="channel_scripts")
    op.drop_index("ix_channel_scripts_outreach", table_name="channel_scripts")
    op.drop_table("channel_scripts")
    op.drop_index("ix_content_pieces_created", table_name="content_pieces")
    op.drop_index("ix_content_pieces_type", table_name="content_pieces")
    op.drop_index("ix_content_pieces_status", table_name="content_pieces")
    op.drop_table("content_pieces")
