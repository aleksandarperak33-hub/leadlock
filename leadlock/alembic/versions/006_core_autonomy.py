"""Core autonomy: task queue, learning signals, config fields

Revision ID: 006
Revises: 005
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Task Queue table ---
    op.create_table(
        "task_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, server_default="5"),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("max_retries", sa.Integer, server_default="3"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text),
        sa.Column("result_data", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_task_queue_processing", "task_queue",
        ["status", "scheduled_at", "priority"],
    )

    # --- Learning Signals table ---
    op.create_table(
        "learning_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("signal_type", sa.String(30), nullable=False),
        sa.Column("dimensions", postgresql.JSONB),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column(
            "outreach_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outreach.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_learning_signals_type_created", "learning_signals",
        ["signal_type", "created_at"],
    )

    # --- SalesEngineConfig new columns ---
    # Phase 1B: Continuous scraper
    op.add_column("sales_engine_config", sa.Column(
        "scraper_interval_minutes", sa.Integer, server_default="15",
    ))
    op.add_column("sales_engine_config", sa.Column(
        "variant_cooldown_days", sa.Integer, server_default="7",
    ))

    # Phase 1C: Business hours gating
    op.add_column("sales_engine_config", sa.Column(
        "send_hours_start", sa.String(5), server_default="08:00",
    ))
    op.add_column("sales_engine_config", sa.Column(
        "send_hours_end", sa.String(5), server_default="18:00",
    ))
    op.add_column("sales_engine_config", sa.Column(
        "send_timezone", sa.String(50), server_default="America/Chicago",
    ))
    op.add_column("sales_engine_config", sa.Column(
        "send_weekdays_only", sa.Boolean, server_default="true",
    ))

    # Phase 3: Worker controls & budget (added early for model consistency)
    op.add_column("sales_engine_config", sa.Column(
        "scraper_paused", sa.Boolean, server_default="false",
    ))
    op.add_column("sales_engine_config", sa.Column(
        "sequencer_paused", sa.Boolean, server_default="false",
    ))
    op.add_column("sales_engine_config", sa.Column(
        "cleanup_paused", sa.Boolean, server_default="false",
    ))
    op.add_column("sales_engine_config", sa.Column(
        "monthly_budget_usd", sa.Float, nullable=True,
    ))
    op.add_column("sales_engine_config", sa.Column(
        "budget_alert_threshold", sa.Float, server_default="0.8",
    ))


def downgrade() -> None:
    # Remove config columns
    for col in [
        "scraper_interval_minutes", "variant_cooldown_days",
        "send_hours_start", "send_hours_end", "send_timezone", "send_weekdays_only",
        "scraper_paused", "sequencer_paused", "cleanup_paused",
        "monthly_budget_usd", "budget_alert_threshold",
    ]:
        op.drop_column("sales_engine_config", col)

    # Drop tables
    op.drop_index("ix_learning_signals_type_created", table_name="learning_signals")
    op.drop_table("learning_signals")
    op.drop_index("ix_task_queue_processing", table_name="task_queue")
    op.drop_table("task_queue")
