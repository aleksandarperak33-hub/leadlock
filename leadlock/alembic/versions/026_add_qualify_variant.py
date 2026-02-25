"""Add qualify_variant to leads for qualify agent A/B testing.

Revision ID: 026
Revises: 025
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("qualify_variant", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leads", "qualify_variant")
