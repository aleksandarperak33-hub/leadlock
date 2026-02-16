"""
Admin reporting service — generates system-wide metrics for the admin dashboard.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func, and_, case, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.client import Client
from src.models.lead import Lead
from src.models.conversation import Conversation

logger = logging.getLogger(__name__)


async def get_system_overview(db: AsyncSession) -> dict:
    """Aggregate metrics across all clients for the admin overview."""
    # Active clients (exclude admin accounts)
    active_clients = (await db.execute(
        select(func.count(Client.id)).where(
            and_(Client.is_active == True, Client.is_admin == False)
        )
    )).scalar() or 0

    # MRR (exclude admin accounts)
    mrr_result = (await db.execute(
        select(func.sum(Client.monthly_fee)).where(
            and_(Client.is_active == True, Client.is_admin == False,
                 Client.billing_status.in_(["active", "pilot", "trial"]))
        )
    )).scalar() or 0.0

    # Total leads (last 30d)
    since_30d = datetime.utcnow() - timedelta(days=30)
    total_leads_30d = (await db.execute(
        select(func.count(Lead.id)).where(Lead.created_at >= since_30d)
    )).scalar() or 0

    # Total leads (last 7d)
    since_7d = datetime.utcnow() - timedelta(days=7)
    total_leads_7d = (await db.execute(
        select(func.count(Lead.id)).where(Lead.created_at >= since_7d)
    )).scalar() or 0

    # Avg response time (last 30d)
    avg_response = (await db.execute(
        select(func.avg(Lead.first_response_ms)).where(
            and_(Lead.created_at >= since_30d, Lead.first_response_ms.isnot(None))
        )
    )).scalar() or 0

    # Total booked (last 30d)
    total_booked_30d = (await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.created_at >= since_30d, Lead.state.in_(["booked", "completed"]))
        )
    )).scalar() or 0

    # Conversion rate
    conversion_rate = total_booked_30d / total_leads_30d if total_leads_30d > 0 else 0.0

    # Clients by tier (exclude admin accounts)
    tier_result = await db.execute(
        select(Client.tier, func.count(Client.id))
        .where(and_(Client.is_active == True, Client.is_admin == False))
        .group_by(Client.tier)
    )
    clients_by_tier = {row[0]: row[1] for row in tier_result.all()}

    # Clients by billing status (exclude admin accounts)
    billing_result = await db.execute(
        select(Client.billing_status, func.count(Client.id))
        .where(Client.is_admin == False)
        .group_by(Client.billing_status)
    )
    clients_by_billing = {row[0]: row[1] for row in billing_result.all()}

    return {
        "active_clients": active_clients,
        "mrr": float(mrr_result),
        "total_leads_30d": total_leads_30d,
        "total_leads_7d": total_leads_7d,
        "avg_response_time_ms": int(avg_response),
        "total_booked_30d": total_booked_30d,
        "conversion_rate": conversion_rate,
        "clients_by_tier": clients_by_tier,
        "clients_by_billing": clients_by_billing,
    }


async def get_client_list_with_metrics(
    db: AsyncSession,
    search: Optional[str] = None,
    tier: Optional[str] = None,
    billing_status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Get all clients with per-client lead/revenue metrics."""
    since_30d = datetime.utcnow() - timedelta(days=30)

    # Base query
    query = select(Client).where(Client.is_admin == False)

    if search:
        pattern = f"%{search}%"
        query = query.where(
            Client.business_name.ilike(pattern)
            | Client.owner_email.ilike(pattern)
            | Client.owner_name.ilike(pattern)
        )
    if tier:
        query = query.where(Client.tier == tier)
    if billing_status:
        query = query.where(Client.billing_status == billing_status)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    query = query.order_by(desc(Client.created_at)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    clients = result.scalars().all()

    # Get per-client metrics
    client_data = []
    for c in clients:
        leads_30d = (await db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.client_id == c.id, Lead.created_at >= since_30d)
            )
        )).scalar() or 0

        booked_30d = (await db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.client_id == c.id, Lead.created_at >= since_30d,
                     Lead.state.in_(["booked", "completed"]))
            )
        )).scalar() or 0

        client_data.append({
            "id": str(c.id),
            "business_name": c.business_name,
            "trade_type": c.trade_type,
            "tier": c.tier,
            "monthly_fee": c.monthly_fee,
            "billing_status": c.billing_status,
            "onboarding_status": c.onboarding_status,
            "owner_name": c.owner_name,
            "owner_email": c.owner_email,
            "twilio_phone": c.twilio_phone,
            "crm_type": c.crm_type,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "leads_30d": leads_30d,
            "booked_30d": booked_30d,
            "conversion_rate": booked_30d / leads_30d if leads_30d > 0 else 0.0,
        })

    return {
        "clients": client_data,
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


async def get_revenue_breakdown(
    db: AsyncSession,
    period: str = "30d",
) -> dict:
    """Get MRR breakdown by tier and top clients by revenue."""
    # MRR by tier (exclude admin accounts)
    tier_revenue = await db.execute(
        select(Client.tier, func.sum(Client.monthly_fee), func.count(Client.id))
        .where(and_(
            Client.is_active == True, Client.is_admin == False,
            Client.billing_status.in_(["active", "pilot", "trial"]),
        ))
        .group_by(Client.tier)
    )
    # Return as {tier: mrr} dict (what the frontend expects)
    mrr_by_tier = {
        row[0]: float(row[1] or 0)
        for row in tier_revenue.all()
    }

    # Top clients by MRR (exclude admin accounts)
    top_result = await db.execute(
        select(Client.id, Client.business_name, Client.monthly_fee, Client.tier, Client.trade_type)
        .where(and_(
            Client.is_active == True, Client.is_admin == False,
            Client.billing_status.in_(["active", "pilot", "trial"]),
        ))
        .order_by(desc(Client.monthly_fee))
        .limit(10)
    )
    top_clients = [
        {
            "id": str(row[0]),
            "business_name": row[1],
            "mrr": float(row[2] or 0),
            "tier": row[3],
            "trade_type": row[4],
        }
        for row in top_result.all()
    ]

    # Total MRR
    total_mrr = sum(mrr_by_tier.values())

    # Total paying clients (exclude admin)
    total_paying = (await db.execute(
        select(func.count(Client.id)).where(and_(
            Client.is_active == True, Client.is_admin == False,
            Client.billing_status.in_(["active", "pilot", "trial"]),
        ))
    )).scalar() or 0

    return {
        "total_mrr": total_mrr,
        "mrr_by_tier": mrr_by_tier,
        "top_clients": top_clients,
        "total_paying_clients": total_paying,
    }
