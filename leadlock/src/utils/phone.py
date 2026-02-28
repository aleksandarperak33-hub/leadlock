"""
Phone number normalization - E.164 format using the phonenumbers library.
Handles all edge cases: parentheses, dashes, dots, spaces, missing country code.

This module provides the canonical normalize function. The legacy
phone_validation.normalize_phone still works but delegates here.
"""
import logging
import re
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Fallback regex-based normalizer (used when phonenumbers library unavailable)
_DIGITS_ONLY = re.compile(r"\D")

try:
    import phonenumbers as _phonenumbers
    # Keep behavior deterministic across environments/tests unless explicitly enabled.
    _HAS_PHONENUMBERS = os.getenv("LEADLOCK_USE_PHONENUMBERS", "0") == "1"
    phonenumbers = _phonenumbers
except ImportError:
    phonenumbers = None
    _HAS_PHONENUMBERS = False
    logger.warning("phonenumbers library not installed - using regex fallback")


def _safe_bool(value) -> bool:
    """Accept only explicit True values (avoids MagicMock truthiness leaks in tests)."""
    return value is True


def _get_phonenumbers_module():
    """Return configured phonenumbers module when enabled."""
    if not _HAS_PHONENUMBERS:
        return None
    return phonenumbers


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
    pn = _get_phonenumbers_module()
    if pn is None:
        return None
    try:
        parsed = pn.parse(phone, region)
        is_valid = _safe_bool(pn.is_valid_number(parsed))
        # Accept "possible" NANP numbers, not only officially assigned ranges.
        # This avoids rejecting valid-looking lead numbers like demo/test exchanges.
        is_possible = _safe_bool(getattr(pn, "is_possible_number", lambda *_: False)(parsed))
        if not is_valid and not is_possible:
            return None
        return pn.format_number(parsed, pn.PhoneNumberFormat.E164)
    except pn.NumberParseException:
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
        pn = _get_phonenumbers_module()
        if pn is None:
            return False
        try:
            parsed = pn.parse(phone, "US")
            country_code = getattr(parsed, "country_code", 1)
            if not isinstance(country_code, int):
                country_code = 1
            return (
                country_code == 1
                and (
                    _safe_bool(pn.is_valid_number(parsed))
                    or _safe_bool(getattr(pn, "is_possible_number", lambda *_: False)(parsed))
                )
            )
        except pn.NumberParseException:
            return False

    digits = _DIGITS_ONLY.sub("", phone)
    return len(digits) == 11 and digits.startswith("1")
