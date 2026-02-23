"""
Email validation - format check + DNS MX record + SMTP mailbox verification.
Prevents sending to invalid emails (saves SendGrid credits, protects sender reputation).
"""
import asyncio
import logging
import re
import smtplib
import socket
from typing import Optional

logger = logging.getLogger(__name__)

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
    Check if domain has MX (mail exchange) DNS records.
    Falls back to A record check if no MX found.
    Runs DNS resolution in a thread pool to avoid blocking the event loop.

    Args:
        domain: Domain to check (e.g. "example.com")

    Returns:
        True if domain can receive email
    """
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

        return await loop.run_in_executor(None, _resolve_mx)

    except ImportError:
        logger.warning("dnspython not installed - skipping MX record check")
        return True
    except Exception as e:
        logger.warning("MX record check failed for %s: %s", domain, str(e))
        return True


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
