"""
Emergency detection — safety-critical module.
Detects life-threatening situations in lead messages.
Emergency messages bypass quiet hours (life safety exception).

Severity levels:
- critical: Immediate danger to life (gas leak, fire, carbon monoxide)
- urgent: Significant but not immediately life-threatening (no heat in winter, burst pipe)
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Default emergency keywords organized by severity
CRITICAL_KEYWORDS = [
    "gas leak",
    "gas smell",
    "smell gas",
    "smelling gas",
    "carbon monoxide",
    "co detector",
    "co alarm",
    "fire",
    "electrical fire",
    "sparking",
    "smoke",
    "exposed wires",
    "electrical shock",
    "electrocuted",
    "sewage",
    "sewer backup",
    "sewage backup",
]

URGENT_KEYWORDS = [
    "no heat",
    "no heating",
    "heat not working",
    "heater not working",
    "furnace not working",
    "no ac",
    "no air conditioning",
    "ac not working",
    "no cooling",
    "no hot water",
    "water heater leaking",
    "hot water heater leaking",
    "flooding",
    "flood",
    "burst pipe",
    "broken pipe",
    "pipe burst",
    "frozen pipes",
    "frozen pipe",
    "pipes frozen",
]


def detect_emergency(
    message: str,
    custom_keywords: Optional[list[str]] = None,
) -> dict:
    """
    Detect emergency situations in a message.

    Args:
        message: The lead's message text
        custom_keywords: Client-specific emergency keywords (treated as critical)

    Returns:
        {
            "is_emergency": bool,
            "severity": str|None,  # "critical" or "urgent"
            "matched_keyword": str|None,
            "emergency_type": str|None,
        }
    """
    if not message:
        return {
            "is_emergency": False,
            "severity": None,
            "matched_keyword": None,
            "emergency_type": None,
        }

    message_lower = message.lower().strip()

    # Check custom keywords first (client-specific, treated as critical)
    if custom_keywords:
        for keyword in custom_keywords:
            if keyword.lower() in message_lower:
                logger.warning(
                    "EMERGENCY DETECTED (custom, critical): '%s' in message",
                    keyword,
                )
                return {
                    "is_emergency": True,
                    "severity": "critical",
                    "matched_keyword": keyword,
                    "emergency_type": _categorize_emergency(keyword),
                }

    # Check critical keywords
    for keyword in CRITICAL_KEYWORDS:
        if keyword in message_lower:
            logger.warning(
                "EMERGENCY DETECTED (critical): '%s' in message", keyword
            )
            return {
                "is_emergency": True,
                "severity": "critical",
                "matched_keyword": keyword,
                "emergency_type": _categorize_emergency(keyword),
            }

    # Check urgent keywords
    for keyword in URGENT_KEYWORDS:
        if keyword in message_lower:
            logger.warning(
                "EMERGENCY DETECTED (urgent): '%s' in message", keyword
            )
            return {
                "is_emergency": True,
                "severity": "urgent",
                "matched_keyword": keyword,
                "emergency_type": _categorize_emergency(keyword),
            }

    return {
        "is_emergency": False,
        "severity": None,
        "matched_keyword": None,
        "emergency_type": None,
    }


def _categorize_emergency(keyword: str) -> str:
    """Categorize the emergency type based on the matched keyword."""
    keyword_lower = keyword.lower()

    if any(w in keyword_lower for w in ["gas", "carbon monoxide", "co detector", "co alarm"]):
        return "gas_or_co"
    if any(w in keyword_lower for w in ["fire", "spark", "smoke"]):
        return "fire_electrical"
    if any(w in keyword_lower for w in ["exposed wire", "electrical shock", "electrocuted"]):
        return "electrical_hazard"
    if any(w in keyword_lower for w in ["sewage", "sewer"]):
        return "sewage"
    if any(w in keyword_lower for w in ["flood", "burst pipe", "broken pipe", "pipe burst"]):
        return "flooding"
    if any(w in keyword_lower for w in ["frozen pipe"]):
        return "frozen_pipes"
    if any(w in keyword_lower for w in ["no heat", "heat not", "heater not", "furnace not"]):
        return "no_heat"
    if any(w in keyword_lower for w in ["no ac", "no air", "ac not", "no cooling"]):
        return "no_cooling"
    if any(w in keyword_lower for w in ["no hot water", "water heater"]):
        return "water_heater"

    return "general_emergency"
