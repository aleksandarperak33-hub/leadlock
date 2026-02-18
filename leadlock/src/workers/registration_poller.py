"""
Registration poller worker — monitors Twilio A2P registration status.
Polls every 5 minutes for clients with non-terminal registration states.
Automatically advances through the registration pipeline when approved.

State machine:
  collecting_info -> profile_pending -> profile_approved -> brand_pending
    -> brand_approved -> campaign_pending -> active

  Toll-free shortcut:
    collecting_info -> tf_verification_pending -> active

  Error states: profile_rejected, brand_rejected, campaign_rejected, tf_rejected
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_

from src.database import async_session_factory
from src.models.client import Client
from src.services.twilio_registration import (
    TERMINAL_STATES,
    check_customer_profile_status,
    create_brand_registration,
    check_brand_status,
    create_campaign,
    check_campaign_status,
    check_tollfree_status,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 300  # 5 minutes
BATCH_LIMIT = 50


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:registration_poller",
            datetime.now(timezone.utc).isoformat(),
            ex=600,
        )
    except Exception:
        pass


async def run_registration_poller():
    """Main loop — poll for clients needing registration status checks."""
    logger.info(
        "Registration poller started (poll every %ds)", POLL_INTERVAL_SECONDS,
    )

    while True:
        try:
            await poll_registration_statuses()
        except Exception as e:
            logger.error("Registration poller error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def poll_registration_statuses():
    """Check and advance registration for all clients with pending statuses."""
    pending_statuses = [
        "profile_pending", "profile_approved",
        "brand_pending", "brand_approved",
        "campaign_pending", "tf_verification_pending",
    ]

    async with async_session_factory() as db:
        result = await db.execute(
            select(Client).where(
                and_(
                    Client.ten_dlc_status.in_(pending_statuses),
                    Client.is_active == True,
                )
            ).limit(BATCH_LIMIT)
        )
        clients = result.scalars().all()

        if not clients:
            return

        logger.info("Polling registration for %d clients", len(clients))

        for client in clients:
            try:
                await _advance_single_client(client)
            except Exception as e:
                logger.error(
                    "Registration poll failed for client %s: %s",
                    str(client.id)[:8], str(e),
                )

        await db.commit()


async def _advance_single_client(client: Client):
    """
    Check current status and advance to next step for a single client.
    Each client is processed independently so failures don't affect others.
    """
    old_status = client.ten_dlc_status

    if old_status == "profile_pending":
        await _handle_profile_pending(client)

    elif old_status == "profile_approved":
        await _handle_profile_approved(client)

    elif old_status == "brand_pending":
        await _handle_brand_pending(client)

    elif old_status == "brand_approved":
        await _handle_brand_approved(client)

    elif old_status == "campaign_pending":
        await _handle_campaign_pending(client)

    elif old_status == "tf_verification_pending":
        await _handle_tf_pending(client)

    # Log status change
    if client.ten_dlc_status != old_status:
        logger.info(
            "Client %s registration: %s -> %s",
            str(client.id)[:8], old_status, client.ten_dlc_status,
        )
        await _send_status_alert(client, old_status, client.ten_dlc_status)


async def _handle_profile_pending(client: Client):
    """Check profile status and advance if approved."""
    if not client.ten_dlc_profile_sid:
        return

    result = await check_customer_profile_status(client.ten_dlc_profile_sid)
    if result["error"]:
        return

    status = result["result"]["status"]
    if status == "twilio-approved":
        client.ten_dlc_status = "profile_approved"
    elif status == "twilio-rejected":
        client.ten_dlc_status = "profile_rejected"


async def _handle_profile_approved(client: Client):
    """Profile approved — create brand registration."""
    if not client.ten_dlc_profile_sid:
        logger.warning(
            "Client %s has no profile SID, can't create brand",
            str(client.id)[:8],
        )
        return

    result = await create_brand_registration(
        customer_profile_sid=client.ten_dlc_profile_sid,
    )

    if result["error"]:
        logger.error(
            "Brand registration failed for client %s: %s",
            str(client.id)[:8], result["error"],
        )
        return

    client.ten_dlc_brand_id = result["result"]["brand_sid"]
    client.ten_dlc_status = "brand_pending"


async def _handle_brand_pending(client: Client):
    """Check brand status and advance if approved."""
    if not client.ten_dlc_brand_id:
        return

    result = await check_brand_status(client.ten_dlc_brand_id)
    if result["error"]:
        return

    status = result["result"]["status"]
    if status == "APPROVED":
        client.ten_dlc_status = "brand_approved"
    elif status in ("FAILED", "REJECTED"):
        client.ten_dlc_status = "brand_rejected"


async def _handle_brand_approved(client: Client):
    """Brand approved — create campaign."""
    if not client.twilio_messaging_service_sid or not client.ten_dlc_brand_id:
        return

    result = await create_campaign(
        brand_sid=client.ten_dlc_brand_id,
        messaging_service_sid=client.twilio_messaging_service_sid,
        business_name=client.business_name,
    )

    if result["error"]:
        logger.error(
            "Campaign creation failed for client %s: %s",
            str(client.id)[:8], result["error"],
        )
        return

    client.ten_dlc_campaign_id = result["result"]["campaign_sid"]
    client.ten_dlc_status = "campaign_pending"


async def _handle_campaign_pending(client: Client):
    """Check campaign status and mark active if approved."""
    if not client.ten_dlc_campaign_id or not client.twilio_messaging_service_sid:
        return

    result = await check_campaign_status(
        client.ten_dlc_campaign_id,
        client.twilio_messaging_service_sid,
    )
    if result["error"]:
        return

    status = result["result"]["status"]
    if status == "VERIFIED":
        client.ten_dlc_status = "active"
    elif status in ("FAILED", "REJECTED"):
        client.ten_dlc_status = "campaign_rejected"


async def _handle_tf_pending(client: Client):
    """Check toll-free verification status."""
    if not client.ten_dlc_verification_sid:
        return

    result = await check_tollfree_status(client.ten_dlc_verification_sid)
    if result["error"]:
        return

    status = result["result"]["status"]
    if status == "TWILIO_APPROVED":
        client.ten_dlc_status = "active"
    elif status == "TWILIO_REJECTED":
        client.ten_dlc_status = "tf_rejected"


async def _send_status_alert(
    client: Client,
    old_status: str,
    new_status: str,
):
    """Send an alert on registration status change via configured webhook."""
    try:
        from src.config import get_settings
        settings = get_settings()
        if not settings.alert_webhook_url:
            return

        import httpx

        is_error = new_status.endswith("_rejected")
        prefix = "[ERROR]" if is_error else (
            "[OK]" if new_status == "active" else "[UPDATE]"
        )

        message = (
            f"{prefix} **Registration Update** - {client.business_name}\n"
            f"Status: `{old_status}` -> `{new_status}`"
        )

        async with httpx.AsyncClient(timeout=10.0) as http_client:
            await http_client.post(
                settings.alert_webhook_url,
                json={"content": message},
            )
    except Exception as e:
        logger.warning("Failed to send registration alert: %s", str(e))
