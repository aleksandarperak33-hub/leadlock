"""
Phone validation service — Twilio Lookup API v2 for line type intelligence.
Identifies mobile vs landline vs VoIP to optimize SMS delivery.
Cost: $0.008 per lookup.
"""
import logging
import re
from typing import Optional
logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> Optional[str]:
    """
    Normalize phone number to E.164 format (+1XXXXXXXXXX for US numbers).
    Returns None if the number is invalid.
    """
    # Strip all non-digit characters
    digits = re.sub(r"\D", "", phone)

    # Handle US numbers
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) > 11 and digits.startswith("1"):
        return f"+{digits[:11]}"

    # Already has country code
    if phone.startswith("+") and len(digits) >= 10:
        return f"+{digits}"

    return None


def is_valid_us_phone(phone: str) -> bool:
    """Check if phone number is a valid US number in E.164 format."""
    if not phone or not phone.startswith("+1"):
        return False
    digits = re.sub(r"\D", "", phone)
    return len(digits) == 11 and digits.startswith("1")


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
        result = client.lookups.v2.phone_numbers(normalized).fetch(
            fields="line_type_intelligence"
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
