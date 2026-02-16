"""Client dashboard: lead tags, archived, notes

Revision ID: 007
Revises: 006
Create Date: 2026-02-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("tags", postgresql.JSONB, server_default="[]"))
    op.add_column("leads", sa.Column("archived", sa.Boolean, server_default="false"))
    op.add_column("leads", sa.Column("notes", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "notes")
    op.drop_column("leads", "archived")
    op.drop_column("leads", "tags")
