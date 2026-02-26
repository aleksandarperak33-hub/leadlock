"""
Email validation - format check + DNS MX record + SMTP mailbox verification.
Prevents sending to invalid emails (saves SendGrid credits, protects sender reputation).
"""
import asyncio
import logging
import re
import smtplib
import socket
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MX record cache — avoids repeated DNS lookups for the same domain.
# In-memory dict with TTL. Safe for single-process (Railway/Docker).
# ---------------------------------------------------------------------------
_mx_cache: dict[str, tuple[bool, float]] = {}
_mx_hosts_cache: dict[str, tuple[list[str], float]] = {}
_MX_CACHE_TTL = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Known catch-all MX providers — these accept mail for ANY address,
# so pattern-guessed emails at these domains look "valid" but often aren't.
# We downgrade confidence for domains whose MX points to these.
# ---------------------------------------------------------------------------
_CATCH_ALL_MX_PATTERNS = frozenset({
    "secureserver.net",       # GoDaddy shared hosting — catch-all by default
    "emailsrvr.com",         # Rackspace catch-all
    "registrar-servers.com", # Namecheap default mail
    "hostinger.com",         # Hostinger catch-all
    "bluehost.com",          # Bluehost catch-all
    "dreamhost.com",         # DreamHost default
    "pair.com",              # pair Networks
    "fatcow.com",            # FatCow catch-all
    "ipage.com",             # iPage catch-all
})

# RFC 5322 simplified - covers 99%+ of valid emails
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$"
)

# SMTP verification timeout (seconds) - fast enough to not block,
# slow enough to handle real servers
_SMTP_TIMEOUT = 10

# MAIL FROM address for SMTP verification (must be a real domain with MX)
_VERIFY_FROM = "verify@leadlock.org"


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


def _get_mx_hosts(domain: str) -> list[str]:
    """
    Resolve MX records for a domain, sorted by priority (lowest first).
    Falls back to the domain itself if no MX records found.

    Returns:
        List of MX hostnames, ordered by priority.
        Empty list if the domain does not exist (NXDOMAIN).
    """
    try:
        import dns.resolver

        answers = dns.resolver.resolve(domain, "MX")
        # Sort by MX priority (lower = higher priority)
        mx_records = sorted(answers, key=lambda r: r.preference)
        return [str(r.exchange).rstrip(".") for r in mx_records]
    except dns.resolver.NXDOMAIN:
        # Domain does not exist — no point trying port 25
        return []
    except dns.resolver.NoAnswer:
        # Domain exists but no MX records — try A record fallback
        return [domain]
    except Exception as e:
        logger.debug("MX resolution error for %s: %s", domain, str(e))
        # Transient DNS error — try the domain itself
        return [domain]


async def has_mx_record(domain: str) -> bool:
    """
    Check if domain has MX (mail exchange) DNS records.  Cached for 1 hour.
    Falls back to A record check if no MX found.
    Runs DNS resolution in a thread pool to avoid blocking the event loop.

    Args:
        domain: Domain to check (e.g. "example.com")

    Returns:
        True if domain can receive email
    """
    # Check cache first
    now = time.time()
    cached = _mx_cache.get(domain)
    if cached is not None:
        result, cached_at = cached
        if now - cached_at < _MX_CACHE_TTL:
            return result

    try:
        import dns.resolver

        loop = asyncio.get_running_loop()

        def _resolve_mx():
            try:
                answers = dns.resolver.resolve(domain, "MX")
                return len(answers) > 0
            except dns.resolver.NoAnswer:
                try:
                    dns.resolver.resolve(domain, "A")
                    return True
                except Exception:
                    return False
            except dns.resolver.NXDOMAIN:
                return False

        result = await loop.run_in_executor(None, _resolve_mx)
        _mx_cache[domain] = (result, now)
        return result

    except ImportError:
        logger.warning("dnspython not installed - skipping MX record check")
        return True
    except Exception as e:
        logger.warning("MX record check failed for %s: %s", domain, str(e))
        return True


async def get_mx_hosts_async(domain: str) -> list[str]:
    """
    Async wrapper for _get_mx_hosts — resolves MX records in thread pool.
    Cached for 1 hour to avoid redundant DNS lookups (called by both
    has_mx_record flow and is_likely_catch_all in the same pipeline).

    Args:
        domain: Domain to resolve

    Returns:
        List of MX hostnames, or empty list if domain has no mail setup.
    """
    now = time.time()
    cached = _mx_hosts_cache.get(domain)
    if cached is not None:
        hosts, cached_at = cached
        if now - cached_at < _MX_CACHE_TTL:
            return hosts

    loop = asyncio.get_running_loop()
    hosts = await loop.run_in_executor(None, _get_mx_hosts, domain)
    _mx_hosts_cache[domain] = (hosts, now)
    return hosts


async def is_likely_catch_all(domain: str) -> bool:
    """
    Heuristic catch-all detection via MX provider matching.
    Returns True if the domain's MX records point to a known
    catch-all shared hosting provider.

    Without SMTP port 25, we can't probe with a random address,
    so we rely on MX provider patterns.

    Args:
        domain: Domain to check

    Returns:
        True if domain is likely a catch-all (emails may not actually exist)
    """
    try:
        mx_hosts = await get_mx_hosts_async(domain)
        for mx_host in mx_hosts:
            mx_lower = mx_host.lower()
            for catch_all_pattern in _CATCH_ALL_MX_PATTERNS:
                if mx_lower.endswith(catch_all_pattern):
                    logger.debug(
                        "Domain %s likely catch-all (MX: %s)", domain, mx_host,
                    )
                    return True
        return False
    except Exception as e:
        logger.debug("Catch-all check failed for %s: %s", domain, str(e))
        return False


def _smtp_verify_sync(email: str, mx_hosts: list[str]) -> dict:
    """
    Synchronous SMTP RCPT TO verification against MX hosts.
    Tries each MX host in priority order until one responds.

    Response codes:
        250: Mailbox exists → verified
        550/551/552/553: Mailbox doesn't exist → rejected
        450/451/452: Temp failure (greylisting) → inconclusive
        Connection/timeout errors → inconclusive

    Returns:
        {"exists": bool|None, "reason": str}
        exists=True: mailbox confirmed
        exists=False: mailbox rejected by server
        exists=None: inconclusive (timeout, greylisting, connection refused)
    """
    for mx_host in mx_hosts:
        try:
            smtp = smtplib.SMTP(timeout=_SMTP_TIMEOUT)
            smtp.connect(mx_host, 25)
            smtp.ehlo("leadlock.org")

            # MAIL FROM
            code, _ = smtp.mail(_VERIFY_FROM)
            if code != 250:
                smtp.quit()
                continue

            # RCPT TO - this is the actual mailbox check
            code, message = smtp.rcpt(email)
            smtp.quit()

            if code == 250:
                return {"exists": True, "reason": "smtp_accepted"}

            if code in (550, 551, 552, 553):
                msg_str = message.decode("utf-8", errors="replace") if isinstance(message, bytes) else str(message)
                return {"exists": False, "reason": f"smtp_rejected_{code}: {msg_str[:100]}"}

            # 450/451/452 = temporary failure (greylisting, rate limiting)
            return {"exists": None, "reason": f"smtp_temp_{code}"}

        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError):
            continue
        except (socket.timeout, TimeoutError):
            continue
        except (ConnectionRefusedError, OSError):
            continue
        except Exception as e:
            logger.debug("SMTP verify error for %s via %s: %s", email, mx_host, str(e))
            continue

    return {"exists": None, "reason": "all_mx_unreachable"}


async def verify_smtp_mailbox(email: str) -> dict:
    """
    Verify that an email mailbox exists via SMTP RCPT TO check.
    Connects to the domain's MX servers and checks if the mailbox accepts mail.

    This catches the most common bounce scenario: guessed addresses like
    info@domain.com on servers that reject unknown recipients (Google Workspace,
    Microsoft 365, most business mail servers).

    Runs in a thread pool to avoid blocking the event loop.

    Args:
        email: Email address to verify

    Returns:
        {"exists": bool|None, "reason": str}
        exists=True: mailbox confirmed by server
        exists=False: server explicitly rejected the mailbox
        exists=None: inconclusive (timeout, greylisting, catch-all, connection issues)
    """
    cleaned = email.strip().lower()
    if "@" not in cleaned:
        return {"exists": None, "reason": "invalid_email_format"}
    domain = cleaned.split("@")[1]
    if not domain:
        return {"exists": None, "reason": "invalid_email_format"}

    loop = asyncio.get_running_loop()

    # Resolve MX in the thread pool
    mx_hosts = await loop.run_in_executor(None, _get_mx_hosts, domain)

    if not mx_hosts:
        return {"exists": None, "reason": "no_mx_hosts"}

    # Run SMTP verification in thread pool (blocking I/O)
    return await loop.run_in_executor(None, _smtp_verify_sync, cleaned, mx_hosts)


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


async def validate_email_full(email: str) -> dict:
    """
    Full email validation: format + MX + SMTP mailbox verification.
    Use this for pattern-guessed emails that need verification before sending.

    Args:
        email: Email address to validate

    Returns:
        {"valid": bool, "reason": str|None, "smtp_verified": bool}
    """
    basic = await validate_email(email)
    if not basic["valid"]:
        return {**basic, "smtp_verified": False}

    smtp_result = await verify_smtp_mailbox(email)

    if smtp_result["exists"] is False:
        # Server explicitly rejected the mailbox
        return {
            "valid": False,
            "reason": f"mailbox_not_found: {smtp_result['reason']}",
            "smtp_verified": False,
        }

    if smtp_result["exists"] is True:
        return {"valid": True, "reason": None, "smtp_verified": True}

    # Inconclusive — format + MX passed, SMTP was inconclusive
    # Allow sending but don't mark as verified
    return {"valid": True, "reason": None, "smtp_verified": False}
