"""
Reporting service - generates metrics and reports for dashboard and email.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.lead import Lead
from src.models.conversation import Conversation
from src.models.booking import Booking
from src.models.consent import ConsentRecord
from src.models.followup import FollowupTask
from src.schemas.api_responses import (
    DashboardMetrics,
    DayMetric,
    ResponseTimeBucket,
)
from src.utils.metrics import response_time_bucket

logger = logging.getLogger(__name__)


async def get_dashboard_metrics(
    db: AsyncSession,
    client_id: str,
    period: str = "7d",
) -> DashboardMetrics:
    """Calculate dashboard KPI metrics for a given period."""
    days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 7)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Total leads
    lead_count_result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.client_id == client_id, Lead.created_at >= since)
        )
    )
    total_leads = lead_count_result.scalar() or 0

    # Total booked
    booked_result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(
                Lead.client_id == client_id,
                Lead.created_at >= since,
                Lead.state.in_(["booked", "completed"]),
            )
        )
    )
    total_booked = booked_result.scalar() or 0

    # Conversion rate
    conversion_rate = total_booked / total_leads if total_leads > 0 else 0.0

    # Average response time
    response_result = await db.execute(
        select(func.avg(Lead.first_response_ms)).where(
            and_(
                Lead.client_id == client_id,
                Lead.created_at >= since,
                Lead.first_response_ms.isnot(None),
            )
        )
    )
    avg_response_ms = int(response_result.scalar() or 0)

    # Leads under 60s
    under_60s_result = await db.execute(
        select(func.count(Lead.id)).where(
            and_(
                Lead.client_id == client_id,
                Lead.created_at >= since,
                Lead.first_response_ms.isnot(None),
                Lead.first_response_ms < 60000,
            )
        )
    )
    leads_under_60s = under_60s_result.scalar() or 0
    leads_under_60s_pct = (leads_under_60s / total_leads * 100) if total_leads > 0 else 0.0

    # Total messages
    msg_result = await db.execute(
        select(func.count(Conversation.id)).where(
            and_(Conversation.client_id == client_id, Conversation.created_at >= since)
        )
    )
    total_messages = msg_result.scalar() or 0

    # Costs
    ai_cost_result = await db.execute(
        select(func.sum(Lead.total_ai_cost_usd)).where(
            and_(Lead.client_id == client_id, Lead.created_at >= since)
        )
    )
    total_ai_cost = float(ai_cost_result.scalar() or 0)

    sms_cost_result = await db.execute(
        select(func.sum(Lead.total_sms_cost_usd)).where(
            and_(Lead.client_id == client_id, Lead.created_at >= since)
        )
    )
    total_sms_cost = float(sms_cost_result.scalar() or 0)

    # Leads by source
    source_result = await db.execute(
        select(Lead.source, func.count(Lead.id))
        .where(and_(Lead.client_id == client_id, Lead.created_at >= since))
        .group_by(Lead.source)
    )
    leads_by_source = {row[0]: row[1] for row in source_result.all()}

    # Leads by state
    state_result = await db.execute(
        select(Lead.state, func.count(Lead.id))
        .where(and_(Lead.client_id == client_id, Lead.created_at >= since))
        .group_by(Lead.state)
    )
    leads_by_state = {row[0]: row[1] for row in state_result.all()}

    # Leads by day
    day_result = await db.execute(
        select(
            func.date_trunc("day", Lead.created_at).label("day"),
            func.count(Lead.id),
            func.count(case((Lead.state.in_(["booked", "completed"]), Lead.id))),
        )
        .where(and_(Lead.client_id == client_id, Lead.created_at >= since))
        .group_by("day")
        .order_by("day")
    )
    leads_by_day = [
        DayMetric(date=str(row[0].date()), count=row[1], booked=row[2])
        for row in day_result.all()
    ]

    # Response time distribution
    response_leads = await db.execute(
        select(Lead.first_response_ms).where(
            and_(
                Lead.client_id == client_id,
                Lead.created_at >= since,
                Lead.first_response_ms.isnot(None),
            )
        )
    )
    buckets = {"0-10s": 0, "10-30s": 0, "30-60s": 0, "60s+": 0}
    for (ms,) in response_leads.all():
        bucket = response_time_bucket(ms)
        buckets[bucket] = buckets.get(bucket, 0) + 1
    response_time_distribution = [
        ResponseTimeBucket(bucket=k, count=v) for k, v in buckets.items()
    ]

    return DashboardMetrics(
        total_leads=total_leads,
        total_booked=total_booked,
        conversion_rate=conversion_rate,
        avg_response_time_ms=avg_response_ms,
        leads_under_60s=leads_under_60s,
        leads_under_60s_pct=leads_under_60s_pct,
        total_messages=total_messages,
        total_ai_cost=total_ai_cost,
        total_sms_cost=total_sms_cost,
        leads_by_source=leads_by_source,
        leads_by_state=leads_by_state,
        leads_by_day=leads_by_day,
        response_time_distribution=response_time_distribution,
        conversion_by_source={},
    )
