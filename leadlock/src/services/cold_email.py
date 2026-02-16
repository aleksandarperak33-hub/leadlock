"""
Cold email service — SendGrid outbound with CAN-SPAM compliance.
Every email gets a CAN-SPAM footer, List-Unsubscribe header, and custom_args for webhook tracking.
"""
import logging
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
    if not settings.sendgrid_api_key:
        logger.error("SendGrid API key not configured")
        return {"message_id": None, "status": "error", "cost_usd": 0.0, "error": "SendGrid not configured"}

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Mail, Email, To, Content, Header, CustomArg, ReplyTo,
        )

        # Append CAN-SPAM footer
        footer_html = CAN_SPAM_FOOTER_HTML.format(
            company_name=from_name,
            company_address=company_address,
            unsubscribe_url=unsubscribe_url,
        )
        footer_text = CAN_SPAM_FOOTER_TEXT.format(
            company_name=from_name,
            company_address=company_address,
            unsubscribe_url=unsubscribe_url,
        )

        full_html = body_html + footer_html

        message = Mail(
            from_email=Email(from_email, from_name),
            to_emails=To(to_email, to_name),
            subject=subject,
            html_content=Content("text/html", full_html),
        )
        message.reply_to = ReplyTo(reply_to)

        # List-Unsubscribe header for email clients
        message.header = Header("List-Unsubscribe", f"<{unsubscribe_url}>")
        message.header = Header("List-Unsubscribe-Post", "List-Unsubscribe=One-Click")

        # Custom args for webhook tracking
        if custom_args:
            for key, value in custom_args.items():
                message.custom_arg = CustomArg(key, str(value))

        # Enable open and click tracking
        message.tracking_settings = {
            "open_tracking": {"enable": True},
            "click_tracking": {"enable": True},
        }

        sg = SendGridAPIClient(api_key=settings.sendgrid_api_key)
        response = sg.send(message)

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
