"""
Timezone utilities for compliance and scheduling.
Maps ZIP codes and state codes to timezones.
"""
from typing import Optional
from zoneinfo import ZoneInfo

# State to timezone mapping (simplified - uses most populous timezone per state)
STATE_TIMEZONE_MAP = {
    "AL": "America/Chicago",
    "AK": "America/Anchorage",
    "AZ": "America/Phoenix",
    "AR": "America/Chicago",
    "CA": "America/Los_Angeles",
    "CO": "America/Denver",
    "CT": "America/New_York",
    "DE": "America/New_York",
    "FL": "America/New_York",
    "GA": "America/New_York",
    "HI": "Pacific/Honolulu",
    "ID": "America/Boise",
    "IL": "America/Chicago",
    "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago",
    "KS": "America/Chicago",
    "KY": "America/New_York",
    "LA": "America/Chicago",
    "ME": "America/New_York",
    "MD": "America/New_York",
    "MA": "America/New_York",
    "MI": "America/Detroit",
    "MN": "America/Chicago",
    "MS": "America/Chicago",
    "MO": "America/Chicago",
    "MT": "America/Denver",
    "NE": "America/Chicago",
    "NV": "America/Los_Angeles",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NM": "America/Denver",
    "NY": "America/New_York",
    "NC": "America/New_York",
    "ND": "America/Chicago",
    "OH": "America/New_York",
    "OK": "America/Chicago",
    "OR": "America/Los_Angeles",
    "PA": "America/New_York",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "SD": "America/Chicago",
    "TN": "America/Chicago",
    "TX": "America/Chicago",
    "UT": "America/Denver",
    "VT": "America/New_York",
    "VA": "America/New_York",
    "WA": "America/Los_Angeles",
    "WV": "America/New_York",
    "WI": "America/Chicago",
    "WY": "America/Denver",
    "DC": "America/New_York",
}


def get_timezone_for_state(state_code: Optional[str]) -> Optional[str]:
    """Get timezone string for a US state code."""
    if not state_code:
        return None
    return STATE_TIMEZONE_MAP.get(state_code.upper())


def get_zoneinfo(state_code: Optional[str] = None, timezone_str: Optional[str] = None) -> ZoneInfo:
    """Get ZoneInfo object, defaulting to Eastern if unknown."""
    if timezone_str:
        return ZoneInfo(timezone_str)
    if state_code:
        tz_str = get_timezone_for_state(state_code)
        if tz_str:
            return ZoneInfo(tz_str)
    return ZoneInfo("America/New_York")
