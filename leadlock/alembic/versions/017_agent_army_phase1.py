"""Agent army phase 1 - A/B testing, winback columns, outreach_emails variant FK

Revision ID: 017
Revises: 016
Create Date: 2026-02-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A/B test experiments table
    op.create_table(
        "ab_test_experiments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("sequence_step", sa.Integer(), nullable=False),
        sa.Column("target_trade", sa.String(50), nullable=True),
        sa.Column("min_sample_per_variant", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("winning_variant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ab_test_experiments_status", "ab_test_experiments", ["status"])
    op.create_index("ix_ab_test_experiments_step", "ab_test_experiments", ["sequence_step"])

    # A/B test variants table
    op.create_table(
        "ab_test_variants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("experiment_id", UUID(as_uuid=True), sa.ForeignKey("ab_test_experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_label", sa.String(10), nullable=False),
        sa.Column("subject_instruction", sa.Text(), nullable=False),
        sa.Column("total_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_opened", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_replied", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_winner", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_ab_test_variants_experiment", "ab_test_variants", ["experiment_id"])

    # Outreach winback columns
    op.add_column(
        "outreach",
        sa.Column("winback_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outreach",
        sa.Column("winback_eligible", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_outreach_winback", "outreach", ["winback_eligible", "winback_sent_at"])

    # Outreach emails A/B variant FK
    op.add_column(
        "outreach_emails",
        sa.Column("ab_variant_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_outreach_emails_ab_variant",
        "outreach_emails",
        "ab_test_variants",
        ["ab_variant_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_outreach_emails_ab_variant", "outreach_emails", type_="foreignkey")
    op.drop_column("outreach_emails", "ab_variant_id")
    op.drop_index("ix_outreach_winback", table_name="outreach")
    op.drop_column("outreach", "winback_eligible")
    op.drop_column("outreach", "winback_sent_at")
    op.drop_table("ab_test_variants")
    op.drop_index("ix_ab_test_experiments_step", table_name="ab_test_experiments")
    op.drop_index("ix_ab_test_experiments_status", table_name="ab_test_experiments")
    op.drop_table("ab_test_experiments")
