"""
Critical alerting system - sends alerts on important system events.

Alert channels:
1. Structured log (always) - at ERROR level
2. Webhook (configurable) - Discord/Slack URL via ALERT_WEBHOOK_URL env var

Rate limiting: Per-type cooldowns to prevent alert storms.
Cooldowns stored in Redis (survives restarts, prevents post-deploy alert spam).
Default cooldown is 5 minutes; high-frequency alerts use longer cooldowns.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

ALERT_COOLDOWN_SECONDS = 300  # 5 minutes (default)

# Per-type cooldown overrides (seconds). Alerts that fire on periodic metrics
# checks use longer cooldowns to avoid spamming on persistent conditions.
ALERT_COOLDOWN_OVERRIDES: dict[str, int] = {
    "sms_delivery_failed": 3600,        # 1 hour — persistent metric, not transient
    "high_bounce_rate": 3600,           # 1 hour
    "outreach_reputation_paused": 3600, # 1 hour
    "outreach_reputation_critical": 3600,  # 1 hour
    "outreach_zero_sends": 3600,        # 1 hour
    "outreach_low_open_rate": 3600,     # 1 hour
}

# In-memory fallback when Redis is down (cleared on restart, but prevents alert storms)
_local_cooldowns: dict[str, float] = {}  # alert_type → expiry timestamp


def _get_cooldown_seconds(alert_type: str) -> int:
    """Get cooldown duration for an alert type (per-type override or default)."""
    return ALERT_COOLDOWN_OVERRIDES.get(alert_type, ALERT_COOLDOWN_SECONDS)


class AlertType:
    """Alert type constants."""
    LEAD_PROCESSING_FAILED = "lead_processing_failed"
    SMS_DELIVERY_FAILED = "sms_delivery_failed"
    STUCK_LEADS_FOUND = "stuck_leads_found"
    HEALTH_CHECK_FAILED = "health_check_failed"
    OPT_OUT_RECEIVED = "opt_out_received"
    DEAD_LETTER_EXHAUSTED = "dead_letter_exhausted"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    WEBHOOK_SIGNATURE_INVALID = "webhook_signature_invalid"
    PAYMENT_FAILED = "payment_failed"
    CRM_SYNC_ERROR = "crm_sync_error"
    HIGH_BOUNCE_RATE = "high_bounce_rate"
    OUTREACH_ZERO_SENDS = "outreach_zero_sends"
    OUTREACH_LOW_OPEN_RATE = "outreach_low_open_rate"
    OUTREACH_SEQUENCER_STALE = "outreach_sequencer_stale"
    OUTREACH_REPUTATION_PAUSED = "outreach_reputation_paused"
    OUTREACH_REPUTATION_CRITICAL = "outreach_reputation_critical"


async def send_alert(
    alert_type: str,
    message: str,
    correlation_id: Optional[str] = None,
    severity: str = "error",
    extra: Optional[dict] = None,
) -> None:
    """
    Send an alert through all configured channels.
    Rate-limited per alert type to prevent alert storms.
    """
    # Atomic rate limit check + record (SET NX EX in Redis, in-memory fallback)
    if not await _acquire_cooldown(alert_type):
        return

    # Build alert payload
    from src.utils.logging import get_correlation_id
    cid = correlation_id or get_correlation_id()

    alert_data = {
        "alert_type": alert_type,
        "message": message,
        "severity": severity,
        "correlation_id": cid,
    }
    if extra:
        alert_data["extra"] = extra

    # Channel 1: Always log
    log_message = f"ALERT [{alert_type}]: {message}"
    if cid:
        log_message += f" (correlation_id={cid})"

    if severity == "critical":
        logger.critical(log_message)
    else:
        logger.error(log_message)

    # Channel 2: Webhook (Discord/Slack)
    await _send_webhook_alert(alert_type, message, cid, extra)

    # Channel 3: Email alert (for critical/error severity)
    if severity in ("critical", "error"):
        await _send_email_alert(alert_type, message, cid, extra)


async def _acquire_cooldown(alert_type: str) -> bool:
    """
    Atomically check-and-set alert cooldown. Returns True if alert should be sent.

    Uses Redis SET NX EX (atomic) to eliminate the race between check and record.
    Falls back to in-memory dict when Redis is unavailable.

    Cooldown duration is per-type: see ALERT_COOLDOWN_OVERRIDES.
    """
    import time

    cooldown = _get_cooldown_seconds(alert_type)

    # Try Redis first (atomic SET NX EX)
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        cooldown_key = f"leadlock:alert_cooldown:{alert_type}"
        # SET NX EX: only sets if key doesn't exist, with TTL — atomic check+record
        acquired = await redis.set(cooldown_key, "1", nx=True, ex=cooldown)
        return bool(acquired)
    except Exception as e:
        # Redis down — use in-memory fallback to prevent alert storms
        logger.debug("Alert cooldown Redis check failed, using in-memory fallback: %s", str(e))
        now = time.monotonic()
        expiry = _local_cooldowns.get(alert_type, 0)
        if now < expiry:
            return False
        _local_cooldowns[alert_type] = now + cooldown
        return True


async def _send_webhook_alert(
    alert_type: str,
    message: str,
    correlation_id: Optional[str],
    extra: Optional[dict],
) -> None:
    """Send alert to configured webhook (Discord/Slack)."""
    try:
        from src.config import get_settings
        settings = get_settings()

        webhook_url = getattr(settings, "alert_webhook_url", "")
        if not webhook_url:
            return

        import httpx

        # Format for Discord/Slack compatibility
        severity_emoji = {"critical": "\U0001f6a8", "error": "\u274c", "warning": "\u26a0\ufe0f"}.get("error", "\u2139\ufe0f")
        content = f"{severity_emoji} **{alert_type}**\n{message}"
        if correlation_id:
            content += f"\n`correlation_id: {correlation_id}`"
        if extra:
            for key, val in extra.items():
                content += f"\n`{key}: {val}`"

        payload = {"content": content}

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(webhook_url, json=payload)
    except Exception as e:
        # Alert sending failure should never crash the system
        logger.warning("Failed to send webhook alert: %s", str(e))


async def _send_email_alert(
    alert_type: str,
    message: str,
    correlation_id: Optional[str],
    extra: Optional[dict],
) -> None:
    """Send alert via transactional email to the configured alert recipient."""
    try:
        from src.services.transactional_email import _send_transactional

        from src.config import get_settings
        settings = get_settings()
        alert_email = (
            settings.alert_recipient_email
            or settings.from_email_transactional
            or ""
        )
        if not alert_email:
            logger.debug("Skipping email alert: no alert_recipient_email configured")
            return

        subject = f"LeadLock Alert: {alert_type}"
        details = ""
        if correlation_id:
            details += f"<p><strong>Correlation ID:</strong> {correlation_id}</p>"
        if extra:
            for key, val in extra.items():
                details += f"<p><strong>{key}:</strong> {val}</p>"

        html = f"""
        <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 20px;">
          <h2 style="color: #ef4444; font-size: 18px;">Alert: {alert_type}</h2>
          <p style="color: #555; font-size: 14px;">{message}</p>
          {details}
          <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;" />
          <p style="color: #999; font-size: 11px;">LeadLock Monitoring System</p>
        </div>
        """
        text = f"Alert: {alert_type}\n\n{message}\n\nCorrelation ID: {correlation_id or 'N/A'}"

        await _send_transactional(alert_email, subject, html, text)
    except Exception as e:
        logger.warning("Failed to send email alert: %s", str(e))
