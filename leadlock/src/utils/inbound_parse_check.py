"""
Startup check — verify that the reply-to domain has MX records pointing
to SendGrid's Inbound Parse (mx.sendgrid.net).

Without this, prospect replies are delivered to whatever mail provider
handles the domain (e.g. Google Workspace) and never reach the
/api/v1/sales/inbound-email webhook.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SENDGRID_INBOUND_MX = "mx.sendgrid.net"


async def check_reply_to_mx(reply_to_email: Optional[str] = None) -> None:
    """
    Check if the reply-to domain's MX records include SendGrid Inbound Parse.

    Logs a CRITICAL warning if the MX does not point to mx.sendgrid.net,
    meaning replies will never reach the inbound webhook.

    Args:
        reply_to_email: The reply-to email address configured for outreach.
                        If None, attempts to read from the active sales config.
    """
    if not reply_to_email:
        try:
            from src.database import async_session_factory
            from src.services.sales_tenancy import get_active_sales_configs
            from src.services.sender_mailboxes import get_primary_sender_profile

            async with async_session_factory() as db:
                configs = await get_active_sales_configs(db)
                for config in configs:
                    profile = get_primary_sender_profile(config)
                    if profile and profile.get("reply_to_email"):
                        reply_to_email = profile["reply_to_email"]
                        break
        except Exception as e:
            logger.debug("Could not load reply-to email from config: %s", str(e))
            return

    if not reply_to_email or "@" not in reply_to_email:
        return

    domain = reply_to_email.split("@")[1].lower()

    try:
        from src.utils.email_validation import get_mx_hosts_async

        mx_hosts = await get_mx_hosts_async(domain)
        mx_lower = [h.lower() for h in mx_hosts]

        has_sendgrid_mx = any(SENDGRID_INBOUND_MX in h for h in mx_lower)

        if has_sendgrid_mx:
            logger.info(
                "Reply-to domain %s has SendGrid Inbound Parse MX — replies will reach webhook",
                domain,
            )
        else:
            logger.critical(
                "REPLY DETECTION BROKEN: Domain '%s' MX records (%s) do NOT include %s. "
                "Prospect replies go to your mail provider, NOT to the /inbound-email webhook. "
                "Either: (1) add an MX record for %s pointing to %s, or "
                "(2) set up email forwarding from your inbox to the inbound webhook.",
                domain,
                ", ".join(mx_hosts) or "none",
                SENDGRID_INBOUND_MX,
                domain,
                SENDGRID_INBOUND_MX,
            )
    except Exception as e:
        logger.warning("Reply-to MX check failed for %s: %s", domain, str(e))
