"""
Cold email service - SendGrid outbound with CAN-SPAM compliance.
Every email gets a CAN-SPAM footer, List-Unsubscribe header, and custom_args for webhook tracking.
Includes retry logic with exponential backoff for transient SendGrid errors.
"""
import asyncio
import logging
import re
from typing import Optional
from src.config import get_settings

logger = logging.getLogger(__name__)

SENDGRID_COST_PER_EMAIL = 0.001  # ~$0.001/email on Pro plan

CAN_SPAM_FOOTER_HTML = """
<br/><hr style="border:none;border-top:1px solid #e0e0e0;margin:20px 0"/>
<p style="font-size:11px;color:#999;line-height:1.4">
{company_name} | {company_address}<br/>
<a href="{unsubscribe_url}" style="color:#999">Unsubscribe</a>
</p>
"""

CAN_SPAM_FOOTER_TEXT = """
---
{company_name} | {company_address}
Unsubscribe: {unsubscribe_url}
"""


async def send_cold_email(
    to_email: str,
    to_name: str,
    subject: str,
    body_html: str,
    from_email: str,
    from_name: str,
    reply_to: str,
    unsubscribe_url: str,
    company_address: str,
    custom_args: Optional[dict] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    body_text: Optional[str] = None,
    company_name: Optional[str] = None,
) -> dict:
    """
    Send a cold outreach email via SendGrid with CAN-SPAM compliance.

    Args:
        to_email: Recipient email
        to_name: Recipient name
        subject: Email subject
        body_html: HTML body (CAN-SPAM footer will be appended)
        from_email: Sender email
        from_name: Sender display name
        reply_to: Reply-to email address
        unsubscribe_url: CAN-SPAM unsubscribe link
        company_address: Physical business address for CAN-SPAM footer
        custom_args: SendGrid custom args for webhook tracking (outreach_id, step)

    Returns:
        {"message_id": str, "status": str, "cost_usd": float}
    """
    settings = get_settings()

    # Normalize recipient to avoid sending to malformed scraped addresses.
    from urllib.parse import unquote
    normalized_to_email = unquote((to_email or "").strip())
    normalized_to_email = "".join(normalized_to_email.split()).lower()
    if normalized_to_email != (to_email or ""):
        logger.info(
            "Normalized outbound recipient email: %s -> %s",
            (to_email or "")[:32],
            normalized_to_email[:32],
        )
    to_email = normalized_to_email

    if not to_email or "@" not in to_email:
        return {
            "message_id": None,
            "status": "error",
            "cost_usd": 0.0,
            "error": "invalid recipient email",
        }

    if not settings.sendgrid_api_key:
        logger.error("SendGrid API key not configured")
        return {"message_id": None, "status": "error", "cost_usd": 0.0, "error": "SendGrid not configured"}

    # CAN-SPAM §5(a)(5) requires a valid physical postal address in every commercial email.
    # Reject sends with empty company_address to prevent compliance violations.
    if not company_address or not company_address.strip():
        logger.error("CAN-SPAM violation: company_address is required but empty")
        return {"message_id": None, "status": "error", "cost_usd": 0.0, "error": "company_address required for CAN-SPAM compliance"}

    if not unsubscribe_url or not unsubscribe_url.strip():
        logger.error("CAN-SPAM violation: unsubscribe_url is required but empty")
        return {"message_id": None, "status": "error", "cost_usd": 0.0, "error": "unsubscribe_url required for CAN-SPAM compliance"}

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Mail, Email, To, Content, Header, CustomArg, ReplyTo,
        )

        # Append CAN-SPAM footer
        display_company = company_name or from_name
        footer_html = CAN_SPAM_FOOTER_HTML.format(
            company_name=display_company,
            company_address=company_address,
            unsubscribe_url=unsubscribe_url,
        )
        footer_text = CAN_SPAM_FOOTER_TEXT.format(
            company_name=display_company,
            company_address=company_address,
            unsubscribe_url=unsubscribe_url,
        )

        full_html = body_html + footer_html

        # Use AI-generated plaintext when available, fall back to HTML stripping
        if body_text and body_text.strip():
            full_text = body_text + footer_text
        else:
            plain_body = re.sub(r"<[^>]+>", "", body_html)
            plain_body = re.sub(r"\s+", " ", plain_body).strip()
            full_text = plain_body + footer_text

        # Build Mail - text/plain MUST be added before text/html per SendGrid
        message = Mail(
            from_email=Email(from_email, from_name),
            to_emails=To(to_email, to_name),
            subject=subject,
        )
        message.content = [
            Content("text/plain", full_text),
            Content("text/html", full_html),
        ]
        message.reply_to = ReplyTo(reply_to)

        # Headers (add individually - Mail.headers has no setter)
        message.header = Header("List-Unsubscribe", f"<{unsubscribe_url}>")
        message.header = Header("List-Unsubscribe-Post", "List-Unsubscribe=One-Click")
        if in_reply_to:
            message.header = Header("In-Reply-To", f"<{in_reply_to}>")
        if references:
            message.header = Header("References", references)

        # Custom args for webhook tracking
        if custom_args:
            for key, value in custom_args.items():
                message.custom_arg = CustomArg(key, str(value))

        # Open tracking: enabled for reputation monitoring (invisible pixel).
        # Click tracking: DISABLED — SendGrid rewrites every URL to a
        # u.sendgrid.net redirect, which triggers spam filters on cold outreach.
        from sendgrid.helpers.mail import (
            TrackingSettings, OpenTracking, ClickTracking,
        )
        message.tracking_settings = TrackingSettings(
            open_tracking=OpenTracking(enable=True),
            click_tracking=ClickTracking(enable=False, enable_text=False),
        )

        sg = SendGridAPIClient(api_key=settings.sendgrid_api_key)

        # Retry with exponential backoff on transient errors
        max_retries = 3
        response = None
        for attempt in range(max_retries):
            try:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(None, lambda: sg.send(message))
                break
            except Exception as send_err:
                status_code = getattr(send_err, "status_code", None)
                retryable = status_code in (429, 500, 502, 503) if status_code else True
                if not retryable or attempt == max_retries - 1:
                    raise
                wait_seconds = 2 ** (attempt + 1)  # 2s, 4s, 8s
                logger.warning(
                    "SendGrid send attempt %d failed (status=%s), retrying in %ds",
                    attempt + 1, status_code, wait_seconds,
                )
                await asyncio.sleep(wait_seconds)

        message_id = response.headers.get("X-Message-Id", "")
        logger.info(
            "Cold email sent: to=%s subject=%s message_id=%s",
            to_email[:20] + "***", subject[:30], message_id[:12],
        )

        return {
            "message_id": message_id,
            "status": "sent",
            "cost_usd": SENDGRID_COST_PER_EMAIL,
        }

    except Exception as e:
        logger.error("SendGrid send failed: to=%s error=%s", to_email[:20] + "***", str(e))
        return {
            "message_id": None,
            "status": "error",
            "cost_usd": 0.0,
            "error": str(e),
        }
