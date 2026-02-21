"""
Emergency detection - safety-critical module.
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
    "pipes are frozen",
]

# False-positive exclusion patterns for ambiguous single-word keywords.
# These patterns match non-emergency contexts where the keyword appears
# with a different meaning (e.g., "fire the contractor", "smoke outside").
_FALSE_POSITIVE_EXCLUSIONS: dict[str, list[re.Pattern]] = {
    "fire": [
        # "fire" as verb meaning "to dismiss someone"
        re.compile(r"\bfire\s+(the|our|my|your|his|her|him|them|us|me|that|this)\b"),
        # Past tense / adjective: "got fired", "you're fired"
        re.compile(r"\bfired\b"),
    ],
    "smoke": [
        # "smoke" as leisure verb: "smoke outside", "smoke cigarettes"
        re.compile(r"\bsmoke\s+(outside|cigarettes?|weed|pot|a\s+cigar|break)\b"),
        # "to smoke", "smoker" - personal habit context
        re.compile(r"\b(smoker|to\s+smoke)\b"),
    ],
    "flood": [
        # Metaphorical: "flooded with calls", "flood of requests"
        re.compile(r"\bflooded?\s+(with|of|by)\b"),
        re.compile(r"\bflood\s+of\b"),
    ],
}


def _matches_keyword(keyword: str, message_lower: str) -> bool:
    """Check if keyword matches in message.

    Multi-word phrases use substring matching (already specific enough).
    Single-word keywords use word-boundary regex matching with additional
    false-positive exclusions for ambiguous words like "fire" and "smoke".
    """
    if " " in keyword:
        return keyword in message_lower

    # Single-word: require word boundary to prevent partial matches
    if not re.search(rf"\b{re.escape(keyword)}\b", message_lower):
        return False

    # Check for known false-positive contexts
    exclusions = _FALSE_POSITIVE_EXCLUSIONS.get(keyword, [])
    return not any(pattern.search(message_lower) for pattern in exclusions)


_NOT_EMERGENCY = {
    "is_emergency": False,
    "severity": None,
    "matched_keyword": None,
    "emergency_type": None,
}


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
        return {**_NOT_EMERGENCY}

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
        if _matches_keyword(keyword, message_lower):
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
        if _matches_keyword(keyword, message_lower):
            logger.warning(
                "EMERGENCY DETECTED (urgent): '%s' in message", keyword
            )
            return {
                "is_emergency": True,
                "severity": "urgent",
                "matched_keyword": keyword,
                "emergency_type": _categorize_emergency(keyword),
            }

    return {**_NOT_EMERGENCY}


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
    if any(w in keyword_lower for w in ["frozen pipe", "frozen", "pipes are frozen", "pipes frozen"]):
        return "frozen_pipes"
    if any(w in keyword_lower for w in ["no heat", "heat not", "heater not", "furnace not"]):
        return "no_heat"
    if any(w in keyword_lower for w in ["no ac", "no air", "ac not", "no cooling"]):
        return "no_cooling"
    if any(w in keyword_lower for w in ["no hot water", "water heater"]):
        return "water_heater"

    return "general_emergency"
