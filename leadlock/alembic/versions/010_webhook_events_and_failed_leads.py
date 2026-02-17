"""Add webhook_events and failed_leads tables for audit trail and dead letter queue

Revision ID: 010
Revises: 009
Create Date: 2026-02-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Webhook audit trail — records every incoming webhook before processing
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_webhook_events_source", "webhook_events", ["source"])
    op.create_index("ix_webhook_events_payload_hash", "webhook_events", ["payload_hash"])
    op.create_index("ix_webhook_events_client_id", "webhook_events", ["client_id"])
    op.create_index("ix_webhook_events_correlation_id", "webhook_events", ["correlation_id"])
    op.create_index("ix_webhook_events_received_at", "webhook_events", ["received_at"])

    # Dead letter queue — captures failed leads for retry
    op.create_table(
        "failed_leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("original_payload", postgresql.JSONB, nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("error_message", sa.Text, nullable=False),
        sa.Column("error_traceback", sa.Text, nullable=True),
        sa.Column("failure_stage", sa.String(30), nullable=False),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="5"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(100), nullable=True),
    )
    op.create_index("ix_failed_leads_source", "failed_leads", ["source"])
    op.create_index("ix_failed_leads_client_id", "failed_leads", ["client_id"])
    op.create_index("ix_failed_leads_failure_stage", "failed_leads", ["failure_stage"])
    op.create_index("ix_failed_leads_status", "failed_leads", ["status"])
    op.create_index("ix_failed_leads_next_retry_at", "failed_leads", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_failed_leads_next_retry_at", table_name="failed_leads")
    op.drop_index("ix_failed_leads_status", table_name="failed_leads")
    op.drop_index("ix_failed_leads_failure_stage", table_name="failed_leads")
    op.drop_index("ix_failed_leads_client_id", table_name="failed_leads")
    op.drop_index("ix_failed_leads_source", table_name="failed_leads")
    op.drop_table("failed_leads")

    op.drop_index("ix_webhook_events_received_at", table_name="webhook_events")
    op.drop_index("ix_webhook_events_correlation_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_client_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_payload_hash", table_name="webhook_events")
    op.drop_index("ix_webhook_events_source", table_name="webhook_events")
    op.drop_table("webhook_events")
