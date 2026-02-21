"""
Phone number normalization - E.164 format using the phonenumbers library.
Handles all edge cases: parentheses, dashes, dots, spaces, missing country code.

This module provides the canonical normalize function. The legacy
phone_validation.normalize_phone still works but delegates here.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Fallback regex-based normalizer (used when phonenumbers library unavailable)
_DIGITS_ONLY = re.compile(r"\D")

try:
    import phonenumbers
    _HAS_PHONENUMBERS = True
except ImportError:
    _HAS_PHONENUMBERS = False
    logger.warning("phonenumbers library not installed - using regex fallback")


def normalize_phone_e164(phone: str, default_region: str = "US") -> Optional[str]:
    """
    Normalize a phone number to E.164 format.

    Handles:
    - (555) 123-4567 → +15551234567
    - 555.123.4567   → +15551234567
    - 5551234567     → +15551234567
    - +15551234567   → +15551234567
    - 1-555-123-4567 → +15551234567

    Returns None if the number is invalid.
    """
    if not phone or not phone.strip():
        return None

    cleaned = phone.strip()

    if _HAS_PHONENUMBERS:
        return _normalize_with_phonenumbers(cleaned, default_region)
    return _normalize_with_regex(cleaned)


def _normalize_with_phonenumbers(phone: str, region: str) -> Optional[str]:
    """Normalize using the phonenumbers library for accurate parsing."""
    try:
        parsed = phonenumbers.parse(phone, region)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        return None


def _normalize_with_regex(phone: str) -> Optional[str]:
    """Fallback regex normalization for US numbers."""
    digits = _DIGITS_ONLY.sub("", phone)

    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) > 11 and digits.startswith("1"):
        return f"+{digits[:11]}"

    if phone.startswith("+") and len(digits) >= 10:
        return f"+{digits}"

    return None


def is_valid_us_phone(phone: str) -> bool:
    """Check if a phone number is a valid US number in E.164 format."""
    if not phone or not phone.startswith("+1"):
        return False

    if _HAS_PHONENUMBERS:
        try:
            parsed = phonenumbers.parse(phone, "US")
            return phonenumbers.is_valid_number(parsed)
        except phonenumbers.NumberParseException:
            return False

    digits = _DIGITS_ONLY.sub("", phone)
    return len(digits) == 11 and digits.startswith("1")
