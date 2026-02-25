"""Add same_day_reminder_sent, review_score, review_requested_at to bookings.

Revision ID: 027
Revises: 026
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("same_day_reminder_sent", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "bookings",
        sa.Column("review_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("review_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "review_requested_at")
    op.drop_column("bookings", "review_score")
    op.drop_column("bookings", "same_day_reminder_sent")
