"""Make source_place_id unique per tenant instead of globally unique.

Fixes UniqueViolationError when multiple tenants scrape the same business.
The old index was globally unique on source_place_id alone, but different
tenants should be able to prospect the same business independently.

Revision ID: 028
Revises: 027
Create Date: 2026-02-26
"""
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old global unique index
    op.drop_index("ix_outreach_source_place_id", table_name="outreach")
    # Create new tenant-scoped unique index
    op.create_index(
        "ix_outreach_source_place_id",
        "outreach",
        ["tenant_id", "source_place_id"],
        unique=True,
        postgresql_where="source_place_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_outreach_source_place_id", table_name="outreach")
    op.create_index(
        "ix_outreach_source_place_id",
        "outreach",
        ["source_place_id"],
        unique=True,
        postgresql_where="source_place_id IS NOT NULL",
    )
