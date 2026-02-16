"""add sales engine tables and extend outreach

Revision ID: 003
Revises: 002
Create Date: 2026-02-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Extend outreach table with sales engine columns ---

    # Source tracking
    op.add_column("outreach", sa.Column("source", sa.String(50), nullable=True))
    op.add_column("outreach", sa.Column("source_place_id", sa.String(255), nullable=True))
    op.add_column("outreach", sa.Column("website", sa.String(500), nullable=True))

    # Business details
    op.add_column("outreach", sa.Column("google_rating", sa.Float(), nullable=True))
    op.add_column("outreach", sa.Column("review_count", sa.Integer(), nullable=True))
    op.add_column("outreach", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("outreach", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("outreach", sa.Column("state_code", sa.String(2), nullable=True))
    op.add_column("outreach", sa.Column("zip_code", sa.String(10), nullable=True))

    # Email enrichment
    op.add_column("outreach", sa.Column("email_verified", sa.Boolean(), server_default="false"))
    op.add_column("outreach", sa.Column("email_source", sa.String(50), nullable=True))

    # Outreach sequence tracking
    op.add_column("outreach", sa.Column("outreach_sequence_step", sa.Integer(), server_default="0"))
    op.add_column("outreach", sa.Column("last_email_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outreach", sa.Column("last_email_opened_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outreach", sa.Column("last_email_clicked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outreach", sa.Column("last_email_replied_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outreach", sa.Column("total_emails_sent", sa.Integer(), server_default="0"))
    op.add_column("outreach", sa.Column("total_cost_usd", sa.Float(), server_default="0.0"))

    # CAN-SPAM compliance
    op.add_column("outreach", sa.Column("email_unsubscribed", sa.Boolean(), server_default="false"))
    op.add_column("outreach", sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True))

    # Raw enrichment data
    op.add_column("outreach", sa.Column("enrichment_data", JSONB(), nullable=True))

    # Indexes on outreach
    op.create_index(
        "ix_outreach_source_place_id", "outreach", ["source_place_id"],
        unique=True, postgresql_where=sa.text("source_place_id IS NOT NULL"),
    )
    op.create_index("ix_outreach_sequence_step", "outreach", ["outreach_sequence_step"])

    # --- Create scrape_jobs table ---
    op.create_table(
        "scrape_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("trade_type", sa.String(50), nullable=False),
        sa.Column("location_query", sa.String(255), nullable=False),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state_code", sa.String(2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("results_found", sa.Integer(), server_default="0"),
        sa.Column("new_prospects_created", sa.Integer(), server_default="0"),
        sa.Column("duplicates_skipped", sa.Integer(), server_default="0"),
        sa.Column("api_cost_usd", sa.Float(), server_default="0.0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scrape_jobs_status", "scrape_jobs", ["status"])
    op.create_index(
        "ix_scrape_jobs_platform_location", "scrape_jobs",
        ["platform", "city", "state_code", "trade_type"],
    )

    # --- Create outreach_emails table ---
    op.create_table(
        "outreach_emails",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("outreach_id", UUID(as_uuid=True),
                  sa.ForeignKey("outreach.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("from_email", sa.String(255), nullable=True),
        sa.Column("to_email", sa.String(255), nullable=True),
        sa.Column("sendgrid_message_id", sa.String(255), nullable=True),
        sa.Column("sequence_step", sa.Integer(), server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_cost_usd", sa.Float(), server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_outreach_emails_outreach_id", "outreach_emails", ["outreach_id"])
    op.create_index("ix_outreach_emails_sendgrid_id", "outreach_emails", ["sendgrid_message_id"])
    op.create_index("ix_outreach_emails_direction", "outreach_emails", ["direction"])

    # --- Create sales_engine_config table ---
    op.create_table(
        "sales_engine_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("is_active", sa.Boolean(), server_default="false"),
        sa.Column("target_trade_types", JSONB(), nullable=True),
        sa.Column("target_locations", JSONB(), nullable=True),
        sa.Column("daily_email_limit", sa.Integer(), server_default="50"),
        sa.Column("daily_scrape_limit", sa.Integer(), server_default="100"),
        sa.Column("sequence_delay_hours", sa.Integer(), server_default="48"),
        sa.Column("max_sequence_steps", sa.Integer(), server_default="3"),
        sa.Column("from_email", sa.String(255), nullable=True),
        sa.Column("from_name", sa.String(100), nullable=True),
        sa.Column("reply_to_email", sa.String(255), nullable=True),
        sa.Column("company_address", sa.String(500), nullable=True),
        sa.Column("sms_after_email_reply", sa.Boolean(), server_default="false"),
        sa.Column("sms_from_phone", sa.String(20), nullable=True),
        sa.Column("email_templates", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    # Drop new tables
    op.drop_table("sales_engine_config")

    op.drop_index("ix_outreach_emails_direction", table_name="outreach_emails")
    op.drop_index("ix_outreach_emails_sendgrid_id", table_name="outreach_emails")
    op.drop_index("ix_outreach_emails_outreach_id", table_name="outreach_emails")
    op.drop_table("outreach_emails")

    op.drop_index("ix_scrape_jobs_platform_location", table_name="scrape_jobs")
    op.drop_index("ix_scrape_jobs_status", table_name="scrape_jobs")
    op.drop_table("scrape_jobs")

    # Drop outreach indexes
    op.drop_index("ix_outreach_sequence_step", table_name="outreach")
    op.drop_index("ix_outreach_source_place_id", table_name="outreach")

    # Drop outreach columns
    op.drop_column("outreach", "enrichment_data")
    op.drop_column("outreach", "unsubscribed_at")
    op.drop_column("outreach", "email_unsubscribed")
    op.drop_column("outreach", "total_cost_usd")
    op.drop_column("outreach", "total_emails_sent")
    op.drop_column("outreach", "last_email_replied_at")
    op.drop_column("outreach", "last_email_clicked_at")
    op.drop_column("outreach", "last_email_opened_at")
    op.drop_column("outreach", "last_email_sent_at")
    op.drop_column("outreach", "outreach_sequence_step")
    op.drop_column("outreach", "email_source")
    op.drop_column("outreach", "email_verified")
    op.drop_column("outreach", "zip_code")
    op.drop_column("outreach", "state_code")
    op.drop_column("outreach", "city")
    op.drop_column("outreach", "address")
    op.drop_column("outreach", "review_count")
    op.drop_column("outreach", "google_rating")
    op.drop_column("outreach", "website")
    op.drop_column("outreach", "source_place_id")
    op.drop_column("outreach", "source")
