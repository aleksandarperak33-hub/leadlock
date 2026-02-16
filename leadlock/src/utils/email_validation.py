"""
Email validation — format check + DNS MX record verification.
Prevents sending to invalid emails (saves SendGrid credits, protects sender reputation).
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# RFC 5322 simplified — covers 99%+ of valid emails
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$"
)


def is_valid_email_format(email: str) -> bool:
    """
    Check if email matches a valid format (RFC 5322 simplified).

    Args:
        email: Email address to validate

    Returns:
        True if format is valid
    """
    if not email or len(email) > 254:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


async def has_mx_record(domain: str) -> bool:
    """
    Check if domain has MX (mail exchange) DNS records.
    Falls back to A record check if no MX found.

    Args:
        domain: Domain to check (e.g. "example.com")

    Returns:
        True if domain can receive email
    """
    try:
        import dns.resolver

        try:
            answers = dns.resolver.resolve(domain, "MX")
            return len(answers) > 0
        except dns.resolver.NoAnswer:
            # No MX record — check for A record as fallback
            try:
                dns.resolver.resolve(domain, "A")
                return True
            except Exception:
                return False
        except dns.resolver.NXDOMAIN:
            return False

    except ImportError:
        # dnspython not installed — skip MX check, just validate format
        logger.warning("dnspython not installed — skipping MX record check")
        return True
    except Exception as e:
        logger.warning("MX record check failed for %s: %s", domain, str(e))
        # On error, assume valid — don't block sends on DNS hiccups
        return True


async def validate_email(email: str) -> dict:
    """
    Validate email format and domain MX records.

    Args:
        email: Email address to validate

    Returns:
        {"valid": bool, "reason": str|None}
    """
    if not email:
        return {"valid": False, "reason": "empty"}

    cleaned = email.strip().lower()

    if not is_valid_email_format(cleaned):
        return {"valid": False, "reason": "invalid_format"}

    domain = cleaned.split("@")[1]

    if not await has_mx_record(domain):
        return {"valid": False, "reason": "no_mx_record"}

    return {"valid": True, "reason": None}
