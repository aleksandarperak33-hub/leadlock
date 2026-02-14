"""
Admin API — client management endpoints.
"""
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import get_db
from src.models.client import Client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/clients")
async def list_clients(
    db: AsyncSession = Depends(get_db),
):
    """List all active clients."""
    result = await db.execute(
        select(Client).where(Client.is_active == True).order_by(Client.created_at.desc())
    )
    clients = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "business_name": c.business_name,
            "trade_type": c.trade_type,
            "tier": c.tier,
            "billing_status": c.billing_status,
            "onboarding_status": c.onboarding_status,
            "crm_type": c.crm_type,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in clients
    ]


@router.get("/clients/{client_id}")
async def get_client(
    client_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get client details."""
    client = await db.get(Client, uuid.UUID(client_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return {
        "id": str(client.id),
        "business_name": client.business_name,
        "trade_type": client.trade_type,
        "tier": client.tier,
        "monthly_fee": client.monthly_fee,
        "twilio_phone": client.twilio_phone,
        "ten_dlc_status": client.ten_dlc_status,
        "crm_type": client.crm_type,
        "billing_status": client.billing_status,
        "onboarding_status": client.onboarding_status,
        "owner_name": client.owner_name,
        "owner_email": client.owner_email,
        "config": client.config,
        "is_active": client.is_active,
        "created_at": client.created_at.isoformat() if client.created_at else None,
    }


@router.post("/clients")
async def create_client(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Create a new client."""
    client = Client(
        business_name=payload["business_name"],
        trade_type=payload["trade_type"],
        tier=payload.get("tier", "starter"),
        monthly_fee=payload.get("monthly_fee", 497.00),
        twilio_phone=payload.get("twilio_phone"),
        crm_type=payload.get("crm_type", "google_sheets"),
        config=payload.get("config", {}),
        owner_name=payload.get("owner_name"),
        owner_email=payload.get("owner_email"),
        owner_phone=payload.get("owner_phone"),
        dashboard_email=payload.get("dashboard_email"),
    )

    # Hash dashboard password if provided
    if payload.get("dashboard_password"):
        import bcrypt
        client.dashboard_password_hash = bcrypt.hashpw(
            payload["dashboard_password"].encode(), bcrypt.gensalt()
        ).decode()

    db.add(client)
    await db.commit()
    await db.refresh(client)

    return {"id": str(client.id), "business_name": client.business_name}
