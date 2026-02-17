"""
Critical alerting system — sends alerts on important system events.

Alert channels:
1. Structured log (always) — at ERROR level
2. Webhook (configurable) — Discord/Slack URL via ALERT_WEBHOOK_URL env var

Rate limiting: Max 1 alert per type per 5 minutes to prevent alert storms.
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Rate limit: alert type → last sent timestamp
_alert_cooldowns: dict[str, float] = {}
ALERT_COOLDOWN_SECONDS = 300  # 5 minutes


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


async def send_alert(
    alert_type: str,
    message: str,
    correlation_id: Optional[str] = None,
    severity: str = "error",
    extra: Optional[dict] = None,
) -> None:
    """
    Send an alert through all configured channels.
    Rate-limited to prevent alert storms.
    """
    # Check rate limit
    if not _should_send(alert_type):
        return

    _alert_cooldowns[alert_type] = time.time()

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


def _should_send(alert_type: str) -> bool:
    """Check if alert is within rate limit cooldown."""
    last_sent = _alert_cooldowns.get(alert_type)
    if last_sent is None:
        return True
    return (time.time() - last_sent) >= ALERT_COOLDOWN_SECONDS


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
        severity_emoji = {"critical": "🚨", "error": "❌", "warning": "⚠️"}.get("error", "ℹ️")
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

        # Send to the transactional email sender (admin address)
        from src.config import get_settings
        settings = get_settings()
        alert_email = settings.from_email_transactional or "noreply@leadlock.org"

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
