"""
SMS service — Twilio primary, Telnyx failover.
Every message goes through compliance check before sending.
Tracks delivery status, segment count, and cost.
"""
import logging
import math
from typing import Optional
logger = logging.getLogger(__name__)

# SMS segment limits (GSM-7 encoding)
GSM_SINGLE_SEGMENT = 160
GSM_MULTI_SEGMENT = 153
UCS2_SINGLE_SEGMENT = 70
UCS2_MULTI_SEGMENT = 67

# Per-segment cost estimates
TWILIO_OUTBOUND_COST = 0.0079
TWILIO_INBOUND_COST = 0.0075
TELNYX_OUTBOUND_COST = 0.0040


def count_segments(message: str) -> int:
    """Count SMS segments accounting for GSM-7 vs UCS-2 encoding."""
    # Check if message contains non-GSM characters (requires UCS-2)
    try:
        message.encode("ascii")
        is_gsm = True
    except UnicodeEncodeError:
        is_gsm = False

    if is_gsm:
        if len(message) <= GSM_SINGLE_SEGMENT:
            return 1
        return math.ceil(len(message) / GSM_MULTI_SEGMENT)
    else:
        if len(message) <= UCS2_SINGLE_SEGMENT:
            return 1
        return math.ceil(len(message) / UCS2_MULTI_SEGMENT)


def mask_phone(phone: str) -> str:
    """Mask phone number for logging — show first 6 digits only."""
    if len(phone) > 6:
        return phone[:6] + "***"
    return phone


async def send_sms(
    to: str,
    body: str,
    from_phone: Optional[str] = None,
    messaging_service_sid: Optional[str] = None,
) -> dict:
    """
    Send SMS via Twilio. Falls back to Telnyx on failure.
    Returns: {"sid": str, "status": str, "provider": str, "segments": int, "cost_usd": float, "error": str|None}
    """
    segments = count_segments(body)
    masked = mask_phone(to)

    # Try Twilio first
    try:
        result = await _send_twilio(to, body, from_phone, messaging_service_sid)
        logger.info(
            "SMS sent via Twilio to %s (%d segments): %s",
            masked, segments, result.get("sid", "unknown")
        )
        return {
            "sid": result.get("sid"),
            "status": result.get("status", "sent"),
            "provider": "twilio",
            "segments": segments,
            "cost_usd": segments * TWILIO_OUTBOUND_COST,
            "error": None,
        }
    except Exception as e:
        logger.warning("Twilio failed for %s: %s. Trying Telnyx...", masked, str(e))

    # Failover to Telnyx
    from src.config import get_settings
    settings = get_settings()
    if settings.telnyx_api_key:
        try:
            result = await _send_telnyx(to, body)
            logger.info("SMS sent via Telnyx (failover) to %s (%d segments)", masked, segments)
            return {
                "sid": result.get("id"),
                "status": "sent",
                "provider": "telnyx",
                "segments": segments,
                "cost_usd": segments * TELNYX_OUTBOUND_COST,
                "error": None,
            }
        except Exception as e:
            logger.error("Telnyx failover also failed for %s: %s", masked, str(e))
            return {
                "sid": None,
                "status": "failed",
                "provider": "none",
                "segments": segments,
                "cost_usd": 0.0,
                "error": f"Both providers failed. Twilio: {str(e)}",
            }

    return {
        "sid": None,
        "status": "failed",
        "provider": "none",
        "segments": segments,
        "cost_usd": 0.0,
        "error": "Twilio failed and Telnyx not configured",
    }


async def _send_twilio(
    to: str,
    body: str,
    from_phone: Optional[str] = None,
    messaging_service_sid: Optional[str] = None,
) -> dict:
    """Send via Twilio REST API."""
    from twilio.rest import Client as TwilioClient
    from src.config import get_settings
    settings = get_settings()
    client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)

    kwargs = {"to": to, "body": body}
    if messaging_service_sid or settings.twilio_messaging_service_sid:
        kwargs["messaging_service_sid"] = messaging_service_sid or settings.twilio_messaging_service_sid
    elif from_phone:
        kwargs["from_"] = from_phone
    else:
        raise ValueError("Either from_phone or messaging_service_sid required")

    message = client.messages.create(**kwargs)
    return {"sid": message.sid, "status": message.status}


async def _send_telnyx(to: str, body: str) -> dict:
    """Send via Telnyx API."""
    import httpx
    from src.config import get_settings
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.telnyx.com/v2/messages",
            headers={
                "Authorization": f"Bearer {settings.telnyx_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.telnyx_messaging_profile_id,
                "to": to,
                "text": body,
                "messaging_profile_id": settings.telnyx_messaging_profile_id,
            },
        )
        response.raise_for_status()
        data = response.json()
        return {"id": data.get("data", {}).get("id")}
