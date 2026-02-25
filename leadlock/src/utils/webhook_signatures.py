"""
Webhook signature validation - verify incoming webhooks are authentic.

Supported providers:
- Twilio: HMAC-SHA1 via X-Twilio-Signature
- Generic HMAC-SHA256: For ServiceTitan, Angi, Facebook, etc.
"""
import hashlib
import hmac
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def validate_twilio_signature(
    auth_token: str,
    signature: str,
    url: str,
    params: dict,
) -> bool:
    """
    Validate Twilio webhook signature using their RequestValidator.
    Returns True if valid, False if invalid or on error.
    """
    if not signature:
        logger.warning("Missing X-Twilio-Signature header")
        return False

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        return validator.validate(url, params, signature)
    except Exception as e:
        logger.error("Twilio signature validation error: %s", str(e))
        return False


def validate_hmac_sha256(
    secret: str,
    signature: str,
    body: bytes,
    header_prefix: str = "sha256=",
) -> bool:
    """
    Validate generic HMAC-SHA256 webhook signature.
    Handles signatures with optional prefix (e.g., "sha256=...").
    Returns True if valid, False if invalid.
    """
    if not secret or not signature:
        return False

    # Strip prefix if present
    sig = signature
    if sig.startswith(header_prefix):
        sig = sig[len(header_prefix):]

    try:
        expected = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, sig.lower())
    except Exception as e:
        logger.error("HMAC-SHA256 validation error: %s", str(e))
        return False


def compute_payload_hash(body: bytes) -> str:
    """Compute SHA-256 hash of raw payload for dedup and audit."""
    return hashlib.sha256(body).hexdigest()


async def get_webhook_url(request) -> str:
    """
    Reconstruct the public URL for Twilio signature validation.
    Behind a reverse proxy (Caddy), request.url returns the internal URL
    (e.g., http://api:8000/...) but Twilio signs against the public URL
    (e.g., https://api.leadlock.org/...). We use X-Forwarded-Proto and
    X-Forwarded-Host headers (set by Caddy) to reconstruct the correct URL.
    """
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    path = request.url.path
    query = request.url.query
    base = f"{proto}://{host}{path}"
    if query:
        return f"{base}?{query}"
    return base


async def validate_webhook_source(
    source: str,
    request,
    body: bytes,
    form_params: Optional[dict] = None,
) -> bool:
    """
    Validate webhook signature based on source type.
    Returns True if valid or if no secret is configured (soft enforcement).
    """
    from src.config import get_settings
    settings = get_settings()
    strict_prod = settings.app_env == "production" and not settings.allow_unsigned_webhooks

    def _missing_secret(source_name: str, secret_name: str) -> bool:
        if strict_prod:
            logger.error(
                "Missing %s in production for source '%s' - rejecting webhook",
                secret_name,
                source_name,
            )
            return True
        logger.warning(
            "%s not set - accepting %s webhook without signature verification. "
            "Configure the secret for production (ALLOW_UNSIGNED_WEBHOOKS defaults to false).",
            secret_name,
            source_name,
        )
        return False

    if source == "twilio":
        signature = request.headers.get("X-Twilio-Signature", "")
        if not settings.twilio_auth_token:
            if _missing_secret(source, "TWILIO_AUTH_TOKEN"):
                return False
            return True
        url = await get_webhook_url(request)
        return validate_twilio_signature(
            settings.twilio_auth_token,
            signature,
            url,
            form_params or {},
        )

    if source == "google_lsa":
        secret = settings.webhook_secret_google
        if not secret:
            if _missing_secret(source, "WEBHOOK_SECRET_GOOGLE"):
                return False
            return True
        sig = request.headers.get("X-Webhook-Signature", "")
        return validate_hmac_sha256(secret, sig, body)

    if source == "angi":
        secret = settings.webhook_secret_angi
        if not secret:
            if _missing_secret(source, "WEBHOOK_SECRET_ANGI"):
                return False
            return True
        sig = request.headers.get("X-Webhook-Signature", "")
        return validate_hmac_sha256(secret, sig, body)

    if source == "facebook":
        secret = settings.webhook_secret_facebook
        if not secret:
            if _missing_secret(source, "WEBHOOK_SECRET_FACEBOOK"):
                return False
            return True
        sig = request.headers.get("X-Hub-Signature-256", "")
        return validate_hmac_sha256(secret, sig, body)

    if source == "thumbtack":
        secret = settings.webhook_secret_thumbtack
        if not secret:
            if _missing_secret(source, "WEBHOOK_SECRET_THUMBTACK"):
                return False
            return True
        sig = request.headers.get("X-Webhook-Signature", "")
        return validate_hmac_sha256(secret, sig, body)

    # Generic: use webhook_signing_key if configured
    if settings.webhook_signing_key:
        sig = request.headers.get("X-Webhook-Signature", "")
        if sig:
            return validate_hmac_sha256(settings.webhook_signing_key, sig, body)

    if strict_prod:
        logger.error(
            "No webhook secret configured for source '%s' in production - rejecting webhook",
            source,
        )
        return False

    logger.warning(
        "No webhook secret configured for source '%s' - accepting without "
        "signature verification. Configure webhook_signing_key for production.",
        source,
    )
    return True
