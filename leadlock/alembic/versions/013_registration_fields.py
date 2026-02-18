"""Add Twilio registration fields to clients table

Revision ID: 013
Revises: 012
Create Date: 2026-02-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("twilio_messaging_service_sid", sa.String(100), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("ten_dlc_profile_sid", sa.String(100), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("ten_dlc_verification_sid", sa.String(100), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("business_website", sa.String(255), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("business_type", sa.String(50), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("business_ein", sa.String(20), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("business_address", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "business_address")
    op.drop_column("clients", "business_ein")
    op.drop_column("clients", "business_type")
    op.drop_column("clients", "business_website")
    op.drop_column("clients", "ten_dlc_verification_sid")
    op.drop_column("clients", "ten_dlc_profile_sid")
    op.drop_column("clients", "twilio_messaging_service_sid")
