"""
Tenant scoping helpers for the sales outreach engine.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select

from src.models.sales_config import SalesEngineConfig
from src.services.sender_mailboxes import mailbox_addresses_for_config


def normalize_tenant_id(value) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


async def get_sales_config_for_tenant(
    db,
    tenant_id,
    create_if_missing: bool = False,
) -> Optional[SalesEngineConfig]:
    normalized_tenant = normalize_tenant_id(tenant_id)

    if normalized_tenant is None:
        result = await db.execute(
            select(SalesEngineConfig)
            .where(SalesEngineConfig.tenant_id.is_(None))
            .order_by(SalesEngineConfig.created_at.desc())
            .limit(1)
        )
        config = result.scalar_one_or_none()
        if config or not create_if_missing:
            return config

        config = SalesEngineConfig(tenant_id=None)
        db.add(config)
        await db.flush()
        return config

    result = await db.execute(
        select(SalesEngineConfig)
        .where(SalesEngineConfig.tenant_id == normalized_tenant)
        .order_by(SalesEngineConfig.created_at.desc())
        .limit(1)
    )
    config = result.scalar_one_or_none()
    if config or not create_if_missing:
        return config

    config = SalesEngineConfig(tenant_id=normalized_tenant)
    db.add(config)
    await db.flush()
    return config


async def get_active_sales_configs(db) -> list[SalesEngineConfig]:
    result = await db.execute(
        select(SalesEngineConfig).where(
            SalesEngineConfig.is_active == True,  # noqa: E712
            SalesEngineConfig.tenant_id.isnot(None),
        )
    )
    tenant_configs = list(result.scalars().all())
    if tenant_configs:
        return tenant_configs

    # Legacy/single-tenant fallback: if no tenant-scoped configs exist,
    # allow one or more global configs (tenant_id NULL).
    fallback_result = await db.execute(
        select(SalesEngineConfig).where(
            SalesEngineConfig.is_active == True,  # noqa: E712
            SalesEngineConfig.tenant_id.is_(None),
        )
    )
    return list(fallback_result.scalars().all())


async def resolve_tenant_ids_for_mailboxes(
    db,
    mailbox_candidates: list[str],
) -> set[uuid.UUID]:
    """
    Resolve tenant IDs by mailbox address based on configured sender identities.
    """
    normalized = {m.strip().lower() for m in mailbox_candidates if m}
    if not normalized:
        return set()

    result = await db.execute(
        select(SalesEngineConfig).where(SalesEngineConfig.tenant_id.isnot(None))
    )
    configs = result.scalars().all()

    tenant_ids: set[uuid.UUID] = set()
    for config in configs:
        mailbox_set = mailbox_addresses_for_config(config)
        if mailbox_set.intersection(normalized):
            tenant_ids.add(config.tenant_id)
    return tenant_ids
