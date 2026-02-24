"""
Helpers for multi-mailbox sender selection in the sales outreach engine.
"""
from __future__ import annotations

from typing import Any, Optional


def _normalize_email(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _to_int_or_none(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def get_default_sender_profile(config) -> Optional[dict[str, Any]]:
    """Build a sender profile from legacy single-mailbox fields."""
    from_email = _normalize_email(getattr(config, "from_email", None))
    if not from_email:
        return None
    from_name = (getattr(config, "from_name", None) or "LeadLock").strip()
    sender_name = (getattr(config, "sender_name", None) or "Alek").strip()
    reply_to = _normalize_email(getattr(config, "reply_to_email", None)) or from_email
    return {
        "from_email": from_email,
        "from_name": from_name,
        "reply_to_email": reply_to,
        "sender_name": sender_name,
        "daily_limit": None,
        "is_active": True,
    }


def get_active_sender_mailboxes(config) -> list[dict[str, Any]]:
    """
    Return normalized active mailbox profiles.
    Falls back to legacy single-mailbox config when no pool is configured.
    """
    raw = getattr(config, "sender_mailboxes", None)
    profiles: list[dict[str, Any]] = []

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            if item.get("is_active", True) is False:
                continue
            from_email = _normalize_email(item.get("from_email"))
            if not from_email:
                continue
            reply_to = _normalize_email(item.get("reply_to_email")) or from_email
            profiles.append(
                {
                    "from_email": from_email,
                    "from_name": (item.get("from_name") or getattr(config, "from_name", None) or "LeadLock").strip(),
                    "reply_to_email": reply_to,
                    "sender_name": (item.get("sender_name") or getattr(config, "sender_name", None) or "Alek").strip(),
                    "daily_limit": _to_int_or_none(item.get("daily_limit")),
                    "is_active": True,
                }
            )

    if profiles:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for profile in profiles:
            key = f"{profile['from_email']}|{profile['reply_to_email']}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(profile)
        return deduped

    default_profile = get_default_sender_profile(config)
    return [default_profile] if default_profile else []


def get_primary_sender_profile(config) -> Optional[dict[str, Any]]:
    profiles = get_active_sender_mailboxes(config)
    return profiles[0] if profiles else None


def find_sender_profile_for_address(
    config,
    mailbox_email: Optional[str],
) -> Optional[dict[str, Any]]:
    """Find mailbox profile by matching inbound recipient mailbox address."""
    target = _normalize_email(mailbox_email)
    if not target:
        return None

    for profile in get_active_sender_mailboxes(config):
        if profile["from_email"] == target or profile["reply_to_email"] == target:
            return profile
    return None


def mailbox_addresses_for_config(config) -> set[str]:
    """All mailbox addresses (from/reply-to) configured for a tenant."""
    addresses: set[str] = set()
    for profile in get_active_sender_mailboxes(config):
        if profile.get("from_email"):
            addresses.add(_normalize_email(profile["from_email"]))
        if profile.get("reply_to_email"):
            addresses.add(_normalize_email(profile["reply_to_email"]))
    return {addr for addr in addresses if addr}
