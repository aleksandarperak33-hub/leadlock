"""Initial schema — all tables for LeadLock platform.

Revision ID: 001
Revises:
Create Date: 2026-02-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Agency partners
    op.create_table(
        "agency_partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(100), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False, unique=True),
        sa.Column("contact_phone", sa.String(20)),
        sa.Column("revenue_share_pct", sa.Float, default=25.0),
        sa.Column("total_referred_clients", sa.Integer, default=0),
        sa.Column("total_revenue_shared", sa.Float, default=0.0),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("metadata", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agency_is_active", "agency_partners", ["is_active"])

    # Clients
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("business_name", sa.String(255), nullable=False),
        sa.Column("trade_type", sa.String(50), nullable=False),
        sa.Column("tier", sa.String(50), default="starter"),
        sa.Column("monthly_fee", sa.Float, default=497.00),
        sa.Column("twilio_phone", sa.String(20), unique=True),
        sa.Column("twilio_phone_sid", sa.String(50)),
        sa.Column("ten_dlc_brand_id", sa.String(50)),
        sa.Column("ten_dlc_campaign_id", sa.String(50)),
        sa.Column("ten_dlc_status", sa.String(30), default="pending"),
        sa.Column("crm_type", sa.String(50), default="google_sheets"),
        sa.Column("crm_api_key_encrypted", sa.Text),
        sa.Column("crm_tenant_id", sa.String(100)),
        sa.Column("crm_config", postgresql.JSONB, default={}),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("billing_status", sa.String(30), default="trial"),
        sa.Column("stripe_customer_id", sa.String(100)),
        sa.Column("stripe_subscription_id", sa.String(100)),
        sa.Column("onboarding_status", sa.String(30), default="pending"),
        sa.Column("owner_name", sa.String(100)),
        sa.Column("owner_email", sa.String(255)),
        sa.Column("owner_phone", sa.String(20)),
        sa.Column("dashboard_email", sa.String(255), unique=True),
        sa.Column("dashboard_password_hash", sa.String(255)),
        sa.Column("agency_partner_id", postgresql.UUID(as_uuid=True)),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_clients_trade_type", "clients", ["trade_type"])
    op.create_index("ix_clients_billing_status", "clients", ["billing_status"])
    op.create_index("ix_clients_is_active", "clients", ["is_active"])

    # Consent records
    op.create_table(
        "consent_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False, index=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consent_type", sa.String(20), nullable=False),
        sa.Column("consent_method", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("opted_out", sa.Boolean, default=False),
        sa.Column("opted_out_at", sa.DateTime(timezone=True)),
        sa.Column("opt_out_method", sa.String(50)),
        sa.Column("consent_text", sa.Text),
        sa.Column("consent_url", sa.Text),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("raw_consent_data", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_consent_phone_client", "consent_records", ["phone", "client_id"])
    op.create_index("ix_consent_opted_out", "consent_records", ["opted_out"])

    # Leads
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("phone_national", sa.String(20)),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("email", sa.String(255)),
        sa.Column("address", sa.Text),
        sa.Column("zip_code", sa.String(10)),
        sa.Column("city", sa.String(100)),
        sa.Column("state_code", sa.String(2)),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_lead_id", sa.String(255)),
        sa.Column("state", sa.String(30), default="new", nullable=False),
        sa.Column("previous_state", sa.String(30)),
        sa.Column("score", sa.Integer, default=50),
        sa.Column("service_type", sa.String(100)),
        sa.Column("urgency", sa.String(20)),
        sa.Column("property_type", sa.String(50)),
        sa.Column("budget_range", sa.String(50)),
        sa.Column("problem_description", sa.Text),
        sa.Column("qualification_data", postgresql.JSONB, default={}),
        sa.Column("current_agent", sa.String(30)),
        sa.Column("conversation_turn", sa.Integer, default=0),
        sa.Column("last_agent_response", sa.Text),
        sa.Column("phone_type", sa.String(20)),
        sa.Column("carrier", sa.String(100)),
        sa.Column("consent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consent_records.id")),
        sa.Column("is_emergency", sa.Boolean, default=False),
        sa.Column("emergency_type", sa.String(50)),
        sa.Column("first_response_ms", sa.Integer),
        sa.Column("total_messages_sent", sa.Integer, default=0),
        sa.Column("total_messages_received", sa.Integer, default=0),
        sa.Column("total_ai_cost_usd", sa.Float, default=0.0),
        sa.Column("total_sms_cost_usd", sa.Float, default=0.0),
        sa.Column("cold_outreach_count", sa.Integer, default=0),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True)),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True)),
        sa.Column("next_followup_at", sa.DateTime(timezone=True)),
        sa.Column("raw_payload", postgresql.JSONB),
        sa.Column("metadata", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_leads_client_id", "leads", ["client_id"])
    op.create_index("ix_leads_phone", "leads", ["phone"])
    op.create_index("ix_leads_state", "leads", ["state"])
    op.create_index("ix_leads_source", "leads", ["source"])
    op.create_index("ix_leads_created_at", "leads", ["created_at"])
    op.create_index("ix_leads_client_phone", "leads", ["client_id", "phone"])
    op.create_index("ix_leads_next_followup", "leads", ["next_followup_at"])

    # Conversations
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("from_phone", sa.String(20), nullable=False),
        sa.Column("to_phone", sa.String(20), nullable=False),
        sa.Column("agent_id", sa.String(30)),
        sa.Column("agent_model", sa.String(50)),
        sa.Column("sms_provider", sa.String(20)),
        sa.Column("sms_sid", sa.String(50)),
        sa.Column("delivery_status", sa.String(20), default="queued"),
        sa.Column("delivery_error_code", sa.String(20)),
        sa.Column("delivery_error_message", sa.Text),
        sa.Column("segment_count", sa.Integer, default=1),
        sa.Column("sms_cost_usd", sa.Float, default=0.0),
        sa.Column("ai_cost_usd", sa.Float, default=0.0),
        sa.Column("ai_latency_ms", sa.Integer),
        sa.Column("ai_input_tokens", sa.Integer),
        sa.Column("ai_output_tokens", sa.Integer),
        sa.Column("metadata", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_conversations_lead_id", "conversations", ["lead_id"])
    op.create_index("ix_conversations_client_id", "conversations", ["client_id"])
    op.create_index("ix_conversations_created_at", "conversations", ["created_at"])
    op.create_index("ix_conversations_sms_sid", "conversations", ["sms_sid"])

    # Bookings
    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False, unique=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("appointment_date", sa.Date, nullable=False),
        sa.Column("time_window_start", sa.Time),
        sa.Column("time_window_end", sa.Time),
        sa.Column("service_type", sa.String(100), nullable=False),
        sa.Column("service_description", sa.Text),
        sa.Column("service_address", sa.Text),
        sa.Column("service_zip", sa.String(10)),
        sa.Column("tech_name", sa.String(100)),
        sa.Column("tech_id", sa.String(100)),
        sa.Column("crm_job_id", sa.String(100)),
        sa.Column("crm_customer_id", sa.String(100)),
        sa.Column("crm_sync_status", sa.String(20), default="pending"),
        sa.Column("crm_sync_error", sa.Text),
        sa.Column("crm_synced_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), default="confirmed"),
        sa.Column("cancellation_reason", sa.Text),
        sa.Column("reminder_sent", sa.Boolean, default=False),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bookings_client_id", "bookings", ["client_id"])
    op.create_index("ix_bookings_appointment_date", "bookings", ["appointment_date"])
    op.create_index("ix_bookings_status", "bookings", ["status"])
    op.create_index("ix_bookings_crm_sync_status", "bookings", ["crm_sync_status"])

    # Follow-up tasks
    op.create_table(
        "followup_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("task_type", sa.String(30), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence_number", sa.Integer, default=1),
        sa.Column("status", sa.String(20), default="pending"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("skip_reason", sa.Text),
        sa.Column("message_template", sa.String(100)),
        sa.Column("message_content", sa.Text),
        sa.Column("attempt_count", sa.Integer, default=0),
        sa.Column("max_attempts", sa.Integer, default=3),
        sa.Column("last_error", sa.Text),
        sa.Column("metadata", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_followup_scheduled_at", "followup_tasks", ["scheduled_at"])
    op.create_index("ix_followup_status", "followup_tasks", ["status"])
    op.create_index("ix_followup_lead_id", "followup_tasks", ["lead_id"])
    op.create_index("ix_followup_client_id", "followup_tasks", ["client_id"])
    op.create_index("ix_followup_pending", "followup_tasks", ["status", "scheduled_at"])

    # Event logs
    op.create_table(
        "event_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("leads.id")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), default="success"),
        sa.Column("agent_id", sa.String(30)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("cost_usd", sa.Float),
        sa.Column("message", sa.Text),
        sa.Column("error_message", sa.Text),
        sa.Column("error_code", sa.String(50)),
        sa.Column("data", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_events_lead_id", "event_logs", ["lead_id"])
    op.create_index("ix_events_client_id", "event_logs", ["client_id"])
    op.create_index("ix_events_action", "event_logs", ["action"])
    op.create_index("ix_events_created_at", "event_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("event_logs")
    op.drop_table("followup_tasks")
    op.drop_table("bookings")
    op.drop_table("conversations")
    op.drop_table("leads")
    op.drop_table("consent_records")
    op.drop_table("clients")
    op.drop_table("agency_partners")
