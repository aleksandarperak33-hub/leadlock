"""
Phone validation service — Twilio Lookup API v2 for line type intelligence.
Identifies mobile vs landline vs VoIP to optimize SMS delivery.
Cost: $0.008 per lookup.
"""
import asyncio
import logging
import re
from typing import Optional
logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> Optional[str]:
    """
    Normalize phone number to E.164 format (+1XXXXXXXXXX for US numbers).
    Uses phonenumbers library when available, falls back to regex.
    Returns None if the number is invalid.
    """
    from src.utils.phone import normalize_phone_e164
    return normalize_phone_e164(phone)


def is_valid_us_phone(phone: str) -> bool:
    """Check if phone number is a valid US number in E.164 format."""
    from src.utils.phone import is_valid_us_phone as _is_valid
    return _is_valid(phone)


async def lookup_phone(phone: str) -> dict:
    """
    Look up phone number using Twilio Lookup API v2.
    Returns line type intelligence (mobile, landline, voip).

    Returns:
        {
            "phone": str,
            "phone_type": str,  # mobile, landline, voip, unknown
            "carrier": str,
            "valid": bool,
            "error": str|None,
        }
    """
    normalized = normalize_phone(phone)
    if not normalized:
        return {
            "phone": phone,
            "phone_type": "unknown",
            "carrier": "",
            "valid": False,
            "error": "Invalid phone number format",
        }

    try:
        from twilio.rest import Client as TwilioClient
        from src.config import get_settings
        settings = get_settings()
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        # Offload synchronous Twilio Lookup SDK call to thread pool
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.lookups.v2.phone_numbers(normalized).fetch(
                fields="line_type_intelligence"
            ),
        )

        line_type_info = getattr(result, "line_type_intelligence", {}) or {}
        phone_type = line_type_info.get("type", "unknown")
        carrier = line_type_info.get("carrier_name", "")

        logger.info(
            "Phone lookup %s: type=%s carrier=%s",
            mask_phone_for_log(normalized), phone_type, carrier
        )

        return {
            "phone": normalized,
            "phone_type": phone_type,
            "carrier": carrier,
            "valid": True,
            "error": None,
        }
    except Exception as e:
        logger.warning("Phone lookup failed for %s: %s", mask_phone_for_log(normalized), str(e))
        return {
            "phone": normalized,
            "phone_type": "unknown",
            "carrier": "",
            "valid": True,  # Assume valid if lookup fails — don't block the lead
            "error": str(e),
        }


def mask_phone_for_log(phone: str) -> str:
    """Mask phone for logging — show first 6 digits + ***."""
    if len(phone) > 6:
        return phone[:6] + "***"
    return phone
