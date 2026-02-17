"""
CRM sync worker — asynchronously creates records in the client's CRM.
CRITICAL: This runs AFTER the SMS response. Never in the critical path.

Retry logic:
- On failure: retry up to 5 times with exponential backoff (30s, 2min, 10min, 30min, 2hr)
- After max retries: mark as permanently failed, alert admin
- Heartbeat stored in Redis for health monitoring
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.booking import Booking
from src.models.lead import Lead
from src.models.client import Client
from src.models.event_log import EventLog
from src.integrations.crm_base import CRMBase
from src.integrations.servicetitan import ServiceTitanCRM
from src.integrations.google_sheets import GoogleSheetsCRM

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30
MAX_CRM_RETRIES = 5
CRM_RETRY_DELAYS = [30, 120, 600, 1800, 7200]  # 30s, 2m, 10m, 30m, 2h


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:crm_sync",
            datetime.now(timezone.utc).isoformat(),
            ex=300,
        )
    except Exception:
        pass


async def run_crm_sync():
    """Main loop — poll for bookings that need CRM sync."""
    logger.info("CRM sync worker started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            await sync_pending_bookings()
        except Exception as e:
            logger.error("CRM sync error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def sync_pending_bookings():
    """Find and sync all pending and retrying bookings to their CRM."""
    async with async_session_factory() as db:
        # Find pending bookings AND failed bookings that are due for retry
        result = await db.execute(
            select(Booking)
            .where(
                Booking.crm_sync_status.in_(["pending", "retrying"])
            )
            .order_by(Booking.created_at)
            .limit(20)
        )
        bookings = result.scalars().all()

        if not bookings:
            return

        logger.info("Syncing %d bookings to CRM", len(bookings))

        for booking in bookings:
            try:
                await sync_booking(db, booking)
            except Exception as e:
                retry_count = (booking.extra_data or {}).get("crm_retry_count", 0)
                logger.error(
                    "CRM sync failed for booking %s (attempt %d/%d): %s",
                    str(booking.id)[:8], retry_count + 1, MAX_CRM_RETRIES, str(e),
                )

                if retry_count < MAX_CRM_RETRIES:
                    # Schedule retry with exponential backoff
                    delay = CRM_RETRY_DELAYS[min(retry_count, len(CRM_RETRY_DELAYS) - 1)]
                    booking.crm_sync_status = "retrying"
                    booking.crm_sync_error = str(e)
                    extra = dict(booking.extra_data or {})
                    extra["crm_retry_count"] = retry_count + 1
                    extra["crm_next_retry_at"] = (
                        datetime.now(timezone.utc) + timedelta(seconds=delay)
                    ).isoformat()
                    booking.extra_data = extra
                    logger.info(
                        "CRM sync retry scheduled for booking %s in %ds",
                        str(booking.id)[:8], delay,
                    )
                else:
                    # Max retries exhausted
                    booking.crm_sync_status = "failed"
                    booking.crm_sync_error = f"Max retries ({MAX_CRM_RETRIES}) exhausted: {str(e)}"

                    from src.utils.alerting import send_alert, AlertType
                    await send_alert(
                        AlertType.LEAD_PROCESSING_FAILED,
                        f"CRM sync permanently failed for booking {str(booking.id)[:8]} after {MAX_CRM_RETRIES} retries: {str(e)}",
                        extra={"booking_id": str(booking.id)[:8]},
                    )

        await db.commit()


async def sync_booking(db: AsyncSession, booking: Booking):
    """Sync a single booking to the client's CRM."""
    lead = await db.get(Lead, booking.lead_id)
    client = await db.get(Client, booking.client_id)

    if not lead or not client:
        booking.crm_sync_status = "failed"
        booking.crm_sync_error = "Lead or client not found"
        return

    crm = get_crm_for_client(client)
    if not crm:
        booking.crm_sync_status = "not_applicable"
        return

    # Create customer
    customer_result = await crm.create_customer(
        first_name=lead.first_name or "Unknown",
        last_name=lead.last_name,
        phone=lead.phone,
        email=lead.email,
        address=lead.address,
    )

    if not customer_result.get("success"):
        booking.crm_sync_status = "failed"
        booking.crm_sync_error = f"Customer creation failed: {customer_result.get('error')}"
        return

    booking.crm_customer_id = customer_result.get("customer_id")

    # Create booking/job
    job_result = await crm.create_booking(
        customer_id=booking.crm_customer_id,
        appointment_date=booking.appointment_date,
        time_start=booking.time_window_start,
        time_end=booking.time_window_end,
        service_type=booking.service_type,
        tech_id=booking.tech_id,
        notes=f"Booked via LeadLock AI. Lead ID: {str(lead.id)[:8]}",
    )

    if job_result.get("success"):
        booking.crm_job_id = job_result.get("job_id")
        booking.crm_sync_status = "synced"
        booking.crm_synced_at = datetime.utcnow()

        db.add(EventLog(
            lead_id=lead.id,
            client_id=client.id,
            action="crm_sync_success",
            message=f"Booking synced to {client.crm_type}",
            data={"crm_job_id": booking.crm_job_id, "crm_customer_id": booking.crm_customer_id},
        ))
    else:
        booking.crm_sync_status = "failed"
        booking.crm_sync_error = job_result.get("error")


def get_crm_for_client(client: Client) -> CRMBase | None:
    """Get the appropriate CRM integration for a client."""
    crm_config = client.crm_config or {}

    if client.crm_type == "servicetitan":
        return ServiceTitanCRM(
            client_id=crm_config.get("client_id", ""),
            client_secret=crm_config.get("client_secret", ""),
            app_key=crm_config.get("app_key", ""),
            tenant_id=client.crm_tenant_id or "",
        )
    elif client.crm_type == "google_sheets":
        return GoogleSheetsCRM(
            spreadsheet_id=crm_config.get("spreadsheet_id", ""),
        )

    logger.warning("No CRM integration for type: %s", client.crm_type)
    return None
