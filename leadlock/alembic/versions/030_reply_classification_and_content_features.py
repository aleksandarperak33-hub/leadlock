"""Add reply_classification and content_features columns to outreach_emails.

reply_classification: stores AI classification of inbound replies
  (interested, rejection, auto_reply, out_of_office, unsubscribe).
content_features: JSONB storing structured email features for intelligence
  analytics (subject length, personalization depth, greeting type, etc.).

Revision ID: 030
Revises: 029
Create Date: 2026-02-26
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outreach_emails",
        sa.Column("reply_classification", sa.String(30), nullable=True),
    )
    op.add_column(
        "outreach_emails",
        sa.Column("content_features", JSONB, nullable=True),
    )
    op.create_index(
        "ix_outreach_emails_reply_classification",
        "outreach_emails",
        ["reply_classification"],
        postgresql_where="reply_classification IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outreach_emails_reply_classification",
        table_name="outreach_emails",
    )
    op.drop_column("outreach_emails", "content_features")
    op.drop_column("outreach_emails", "reply_classification")
