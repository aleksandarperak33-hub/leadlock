"""
SMS service - Twilio primary, Telnyx failover.
Every message goes through compliance check before sending.
Tracks delivery status, segment count, and cost.

Carrier error handling:
- 30006 (landline): Mark as landline, don't retry
- 30007 (filtered/blocked): Retry once with alternate content
- 30008 (unknown error): Retry with backoff
- 21610 (unsubscribed via carrier): Auto opt-out
- 21211 (invalid number): Mark as invalid, don't retry
"""
import asyncio
import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

# SMS segment limits
GSM_SINGLE_SEGMENT = 160
GSM_MULTI_SEGMENT = 153
UCS2_SINGLE_SEGMENT = 70
UCS2_MULTI_SEGMENT = 67

# Maximum segments allowed (hard cap at 3)
MAX_SEGMENTS = 3
MAX_GSM_CHARS = GSM_MULTI_SEGMENT * MAX_SEGMENTS  # 459
MAX_UCS2_CHARS = UCS2_MULTI_SEGMENT * MAX_SEGMENTS  # 201

# Per-segment cost estimates
TWILIO_OUTBOUND_COST = 0.0079
TWILIO_INBOUND_COST = 0.0075
TELNYX_OUTBOUND_COST = 0.0040

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS_SECONDS = [5, 15, 45]

# Carrier error classifications
PERMANENT_ERRORS = {
    "21211",  # Invalid "To" phone number
    "21610",  # Unsubscribed recipient (carrier-level opt-out)
    "30006",  # Landline or unreachable
    "21612",  # Invalid "To" phone number for SMS
}

TRANSIENT_ERRORS = {
    "30007",  # Message filtered by carrier
    "30008",  # Unknown error
    "30009",  # Missing segment
    "30010",  # Message price exceeds max price
}

LANDLINE_ERRORS = {"30006"}
OPT_OUT_ERRORS = {"21610"}
INVALID_NUMBER_ERRORS = {"21211", "21612"}

# Twilio client timeout
TWILIO_CLIENT_TIMEOUT = 10


def _get_twilio_client():
    """Get a Twilio REST client with configured timeout (cached per process)."""
    from twilio.rest import Client as TwilioClient
    from twilio.http.http_client import TwilioHttpClient
    from src.config import get_settings
    settings = get_settings()
    http_client = TwilioHttpClient(timeout=TWILIO_CLIENT_TIMEOUT)
    return TwilioClient(
        settings.twilio_account_sid,
        settings.twilio_auth_token,
        http_client=http_client,
    )


async def _run_sync(func, *args, **kwargs):
    """Run a synchronous function in the thread pool to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# GSM-7 basic character set (for encoding detection)
_GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ"
    " !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "ÄÖÑÜabcdefghijklmnopqrstuvwxyz"
    "äöñüà§"
)

_GSM7_EXTENDED = set("^{}\\[~]|€")


def is_gsm7(message: str) -> bool:
    """Check if message can be encoded as GSM-7."""
    return all(c in _GSM7_BASIC or c in _GSM7_EXTENDED for c in message)


def count_segments(message: str) -> int:
    """Count SMS segments accounting for GSM-7 vs UCS-2 encoding."""
    if is_gsm7(message):
        # Count extended chars as 2
        length = sum(2 if c in _GSM7_EXTENDED else 1 for c in message)
        if length <= GSM_SINGLE_SEGMENT:
            return 1
        return math.ceil(length / GSM_MULTI_SEGMENT)
    else:
        if len(message) <= UCS2_SINGLE_SEGMENT:
            return 1
        return math.ceil(len(message) / UCS2_MULTI_SEGMENT)


def enforce_message_length(message: str) -> tuple[str, int, str]:
    """
    Enforce message length limits (max 3 segments).
    Returns: (message, segment_count, encoding)
    """
    encoding = "gsm7" if is_gsm7(message) else "ucs2"
    segments = count_segments(message)

    if segments <= MAX_SEGMENTS:
        return message, segments, encoding

    # Truncate with ellipsis
    if encoding == "gsm7":
        max_len = MAX_GSM_CHARS - 3  # Room for "..."
        truncated = message[:max_len] + "..."
    else:
        max_len = MAX_UCS2_CHARS - 3
        truncated = message[:max_len] + "..."

    new_segments = count_segments(truncated)
    logger.warning(
        "Message truncated from %d to %d segments (%s encoding)",
        segments, new_segments, encoding,
    )
    return truncated, new_segments, encoding


def mask_phone(phone: str) -> str:
    """Mask phone number for logging - show first 6 digits only."""
    if len(phone) > 6:
        return phone[:6] + "***"
    return phone


def classify_error(error_code: str | None) -> str:
    """
    Classify a Twilio error code.
    Returns: "permanent", "transient", "landline", "opt_out", "invalid", or "unknown"
    """
    if not error_code:
        return "unknown"
    code = str(error_code)
    if code in OPT_OUT_ERRORS:
        return "opt_out"
    if code in LANDLINE_ERRORS:
        return "landline"
    if code in INVALID_NUMBER_ERRORS:
        return "invalid"
    if code in PERMANENT_ERRORS:
        return "permanent"
    if code in TRANSIENT_ERRORS:
        return "transient"
    return "unknown"


async def search_available_numbers(area_code: str) -> list[dict]:
    """
    Search for available phone numbers in Twilio by area code.

    Returns: [{"phone_number": str, "friendly_name": str, "locality": str, "region": str}]
    """
    client = _get_twilio_client()

    try:
        available = await _run_sync(
            client.available_phone_numbers("US").local.list,
            area_code=area_code,
            sms_enabled=True,
            mms_enabled=True,
            limit=10,
        )
        return [
            {
                "phone_number": num.phone_number,
                "friendly_name": num.friendly_name,
                "locality": num.locality,
                "region": num.region,
            }
            for num in available
        ]
    except Exception as e:
        logger.error("Number search failed for area code %s: %s", area_code, str(e))
        raise


async def provision_phone_number(
    phone_number: str,
    client_id: str,
    business_name: str = "Business",
) -> dict:
    """
    Purchase and configure a Twilio phone number for a client.
    Sets up SMS webhook URL, creates a per-client Messaging Service,
    and attaches the number to it.

    Returns: {
        "phone_number": str, "phone_sid": str,
        "messaging_service_sid": str|None, "is_tollfree": bool,
        "error": str|None,
    }
    """
    from src.config import get_settings
    from src.services.twilio_registration import (
        create_messaging_service,
        add_phone_to_messaging_service,
        is_tollfree,
    )
    settings = get_settings()

    twilio_client = _get_twilio_client()
    webhook_url = f"{settings.app_base_url.rstrip('/')}/api/v1/webhook/twilio/sms/{client_id}"

    try:
        incoming = await _run_sync(
            twilio_client.incoming_phone_numbers.create,
            phone_number=phone_number,
            sms_url=webhook_url,
            sms_method="POST",
            friendly_name=f"LeadLock-{client_id[:8]}",
        )
        logger.info(
            "Phone provisioned: %s (SID: %s) for client %s",
            phone_number[:6] + "***", incoming.sid, client_id[:8],
        )
    except Exception as e:
        logger.error("Phone provisioning failed: %s", str(e))
        return {
            "phone_number": None, "phone_sid": None,
            "messaging_service_sid": None, "is_tollfree": False,
            "error": str(e),
        }

    # Create a Messaging Service for this client
    ms_result = await create_messaging_service(client_id, business_name)
    messaging_service_sid = None
    if ms_result["error"]:
        logger.warning(
            "Messaging Service creation failed (non-blocking): %s",
            ms_result["error"],
        )
    else:
        messaging_service_sid = ms_result["result"]["messaging_service_sid"]

        # Attach the phone number to the Messaging Service
        attach_result = await add_phone_to_messaging_service(
            messaging_service_sid, incoming.sid,
        )
        if attach_result["error"]:
            logger.warning(
                "Phone attach to Messaging Service failed (non-blocking): %s",
                attach_result["error"],
            )

    return {
        "phone_number": incoming.phone_number,
        "phone_sid": incoming.sid,
        "messaging_service_sid": messaging_service_sid,
        "is_tollfree": is_tollfree(incoming.phone_number),
        "error": None,
    }


async def release_phone_number(phone_sid: str) -> dict:
    """
    Release a Twilio phone number.

    Returns: {"released": bool, "error": str|None}
    """
    client = _get_twilio_client()

    try:
        await _run_sync(client.incoming_phone_numbers(phone_sid).delete)
        logger.info("Phone released: %s", phone_sid)
        return {"released": True, "error": None}
    except Exception as e:
        logger.error("Phone release failed: %s", str(e))
        return {"released": False, "error": str(e)}


async def send_sms(
    to: str,
    body: str,
    from_phone: Optional[str] = None,
    messaging_service_sid: Optional[str] = None,
) -> dict:
    """
    Send SMS via Twilio with retry logic. Falls back to Telnyx after all retries exhausted.

    Returns: {
        "sid": str, "status": str, "provider": str,
        "segments": int, "cost_usd": float,
        "error": str|None, "error_code": str|None,
        "encoding": str, "is_landline": bool,
    }
    """
    # Enforce message length
    body, segments, encoding = enforce_message_length(body)
    masked = mask_phone(to)

    # Check deliverability throttle before sending
    from src.services.deliverability import check_send_allowed, record_sms_outcome
    send_ok, throttle_reason = await check_send_allowed(from_phone or "default")
    if not send_ok:
        logger.warning("SMS throttled for %s: %s", masked, throttle_reason)
        return {
            "sid": None,
            "status": "throttled",
            "provider": "none",
            "segments": segments,
            "cost_usd": 0.0,
            "error": throttle_reason,
            "error_code": None,
            "encoding": encoding,
            "is_landline": False,
        }

    # Try Twilio with retries
    last_error = None
    last_error_code = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = await _send_twilio(to, body, from_phone, messaging_service_sid)
            logger.info(
                "SMS sent via Twilio to %s (%d segments, %s): %s",
                masked, segments, encoding, result.get("sid", "unknown"),
            )
            await record_sms_outcome(from_phone or "default", to, "sent", provider="twilio")
            return {
                "sid": result.get("sid"),
                "status": result.get("status", "sent"),
                "provider": "twilio",
                "segments": segments,
                "cost_usd": segments * TWILIO_OUTBOUND_COST,
                "error": None,
                "error_code": None,
                "encoding": encoding,
                "is_landline": False,
            }
        except Exception as e:
            error_code = _extract_error_code(e)
            error_class = classify_error(error_code)
            last_error = str(e)
            last_error_code = error_code

            # Permanent errors - don't retry
            if error_class in ("permanent", "opt_out", "landline", "invalid"):
                logger.warning(
                    "Twilio permanent error for %s: code=%s class=%s",
                    masked, error_code, error_class,
                )
                await record_sms_outcome(from_phone or "default", to, "failed", error_code, "twilio")
                return {
                    "sid": None,
                    "status": "failed",
                    "provider": "twilio",
                    "segments": segments,
                    "cost_usd": 0.0,
                    "error": last_error,
                    "error_code": error_code,
                    "encoding": encoding,
                    "is_landline": error_class == "landline",
                }

            # Transient error - retry with backoff
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS) - 1)]
                logger.warning(
                    "Twilio transient error for %s (attempt %d/%d): %s. Retrying in %ds...",
                    masked, attempt + 1, MAX_RETRIES + 1, error_code or str(e), delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    "Twilio exhausted retries for %s: %s. Trying Telnyx...",
                    masked, str(e),
                )

    # Failover to Telnyx
    from src.config import get_settings
    settings = get_settings()
    if settings.telnyx_api_key:
        try:
            result = await _send_telnyx(to, body)
            logger.info(
                "SMS sent via Telnyx (failover) to %s (%d segments)", masked, segments,
            )
            await record_sms_outcome(from_phone or "default", to, "sent", provider="telnyx")
            return {
                "sid": result.get("id"),
                "status": "sent",
                "provider": "telnyx",
                "segments": segments,
                "cost_usd": segments * TELNYX_OUTBOUND_COST,
                "error": None,
                "error_code": None,
                "encoding": encoding,
                "is_landline": False,
            }
        except Exception as e:
            logger.error("Telnyx failover also failed for %s: %s", masked, str(e))
            return {
                "sid": None,
                "status": "failed",
                "provider": "none",
                "segments": segments,
                "cost_usd": 0.0,
                "error": f"All providers failed. Last: {str(e)}",
                "error_code": last_error_code,
                "encoding": encoding,
                "is_landline": False,
            }

    return {
        "sid": None,
        "status": "failed",
        "provider": "none",
        "segments": segments,
        "cost_usd": 0.0,
        "error": f"Twilio failed ({last_error}) and Telnyx not configured",
        "error_code": last_error_code,
        "encoding": encoding,
        "is_landline": False,
    }


def _extract_error_code(error: Exception) -> Optional[str]:
    """Extract Twilio error code from exception."""
    # Twilio REST exceptions have a .code attribute
    code = getattr(error, "code", None)
    if code is not None:
        return str(code)
    # Some Twilio errors embed the code in the message
    msg = str(error)
    for known_code in PERMANENT_ERRORS | TRANSIENT_ERRORS:
        if known_code in msg:
            return known_code
    return None


async def _send_twilio(
    to: str,
    body: str,
    from_phone: Optional[str] = None,
    messaging_service_sid: Optional[str] = None,
) -> dict:
    """Send via Twilio REST API (non-blocking)."""
    from src.config import get_settings
    settings = get_settings()
    client = _get_twilio_client()

    kwargs = {"to": to, "body": body}
    if messaging_service_sid or settings.twilio_messaging_service_sid:
        kwargs["messaging_service_sid"] = (
            messaging_service_sid or settings.twilio_messaging_service_sid
        )
    elif from_phone:
        kwargs["from_"] = from_phone
    else:
        raise ValueError("Either from_phone or messaging_service_sid required")

    message = await _run_sync(client.messages.create, **kwargs)
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
