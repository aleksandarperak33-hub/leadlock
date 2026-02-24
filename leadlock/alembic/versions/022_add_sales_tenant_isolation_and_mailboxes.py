"""Add sales tenant isolation columns and sender mailbox pool

Revision ID: 022
Revises: 021
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def _pick_default_tenant_id(bind):
    tenant_id = bind.execute(
        sa.text(
            """
            SELECT id
            FROM clients
            WHERE is_admin = TRUE
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
    ).scalar()
    if tenant_id:
        return tenant_id

    return bind.execute(
        sa.text(
            """
            SELECT id
            FROM clients
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
    ).scalar()


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "outreach",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "sales_engine_config",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "sales_engine_config",
        sa.Column(
            "sender_mailboxes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "scrape_jobs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "email_templates",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_index("ix_campaigns_tenant_id", "campaigns", ["tenant_id"], unique=False)
    op.create_index("ix_outreach_tenant_id", "outreach", ["tenant_id"], unique=False)
    op.create_index(
        "ix_sales_engine_config_tenant_id",
        "sales_engine_config",
        ["tenant_id"],
        unique=False,
    )
    op.create_index("ix_scrape_jobs_tenant_id", "scrape_jobs", ["tenant_id"], unique=False)
    op.create_index(
        "ix_email_templates_tenant_id",
        "email_templates",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "uq_sales_engine_config_tenant_id",
        "sales_engine_config",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )

    bind = op.get_bind()
    tenant_id = _pick_default_tenant_id(bind)
    if tenant_id:
        bind.execute(
            sa.text("UPDATE campaigns SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
            {"tenant_id": tenant_id},
        )
        bind.execute(
            sa.text("UPDATE outreach SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
            {"tenant_id": tenant_id},
        )
        bind.execute(
            sa.text(
                """
                WITH chosen AS (
                    SELECT id
                    FROM sales_engine_config
                    WHERE tenant_id IS NULL
                    ORDER BY created_at ASC, id ASC
                    LIMIT 1
                )
                UPDATE sales_engine_config cfg
                SET tenant_id = :tenant_id
                FROM chosen
                WHERE cfg.id = chosen.id
                """
            ),
            {"tenant_id": tenant_id},
        )
        bind.execute(
            sa.text("UPDATE scrape_jobs SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
            {"tenant_id": tenant_id},
        )
        bind.execute(
            sa.text("UPDATE email_templates SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
            {"tenant_id": tenant_id},
        )


def downgrade() -> None:
    op.drop_index("uq_sales_engine_config_tenant_id", table_name="sales_engine_config")
    op.drop_index("ix_email_templates_tenant_id", table_name="email_templates")
    op.drop_index("ix_scrape_jobs_tenant_id", table_name="scrape_jobs")
    op.drop_index("ix_sales_engine_config_tenant_id", table_name="sales_engine_config")
    op.drop_index("ix_outreach_tenant_id", table_name="outreach")
    op.drop_index("ix_campaigns_tenant_id", table_name="campaigns")

    op.drop_column("email_templates", "tenant_id")
    op.drop_column("scrape_jobs", "tenant_id")
    op.drop_column("sales_engine_config", "sender_mailboxes")
    op.drop_column("sales_engine_config", "tenant_id")
    op.drop_column("outreach", "tenant_id")
    op.drop_column("campaigns", "tenant_id")
