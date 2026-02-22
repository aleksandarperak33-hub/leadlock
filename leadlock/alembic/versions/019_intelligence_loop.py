"""Intelligence loop - winning patterns table, drop dead agent tables

Revision ID: 019
Revises: 018
Create Date: 2026-02-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Winning patterns table - core of the intelligence loop
    op.create_table(
        "winning_patterns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=True),
        sa.Column("pattern_type", sa.String(30), nullable=False, server_default="subject_instruction"),
        sa.Column("instruction_text", sa.Text(), nullable=False),
        sa.Column("trade", sa.String(50), nullable=True),
        sa.Column("sequence_step", sa.Integer(), nullable=True),
        sa.Column("open_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("reply_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_winning_patterns_trade_step_active",
        "winning_patterns",
        ["trade", "sequence_step", "is_active"],
    )
    op.create_index(
        "ix_winning_patterns_active_confidence",
        "winning_patterns",
        ["is_active", sa.text("confidence DESC")],
    )

    # Drop dead agent tables
    op.drop_index("ix_content_pieces_created", table_name="content_pieces")
    op.drop_index("ix_content_pieces_type", table_name="content_pieces")
    op.drop_index("ix_content_pieces_status", table_name="content_pieces")
    op.drop_table("content_pieces")

    op.drop_index("ix_channel_scripts_channel", table_name="channel_scripts")
    op.drop_index("ix_channel_scripts_status", table_name="channel_scripts")
    op.drop_index("ix_channel_scripts_outreach", table_name="channel_scripts")
    op.drop_table("channel_scripts")

    op.drop_index("ix_competitive_intel_created", table_name="competitive_intel")
    op.drop_index("ix_competitive_intel_competitor", table_name="competitive_intel")
    op.drop_table("competitive_intel")


def downgrade() -> None:
    # Recreate competitive_intel
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
        sa.Column("raw_analysis", sa.JSON(), nullable=True),
        sa.Column("ai_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_competitive_intel_competitor", "competitive_intel", ["competitor_name"])
    op.create_index("ix_competitive_intel_created", "competitive_intel", ["created_at"])

    # Recreate channel_scripts
    op.create_table(
        "channel_scripts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("outreach_id", UUID(as_uuid=True), nullable=False),
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

    # Recreate content_pieces
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

    # Drop winning_patterns
    op.drop_index("ix_winning_patterns_active_confidence", table_name="winning_patterns")
    op.drop_index("ix_winning_patterns_trade_step_active", table_name="winning_patterns")
    op.drop_table("winning_patterns")
