"""
Report generator worker - creates weekly reports and sends via email.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.database import async_session_factory
from src.services.reporting import get_dashboard_metrics
from src.models.client import Client
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def run_report_generator():
    """Generate weekly reports for all active clients. Runs once per week."""
    logger.info("Report generator started")

    while True:
        try:
            await generate_weekly_reports()
        except Exception as e:
            logger.error("Report generation error: %s", str(e))

        # Sleep until next Monday 8am
        await asyncio.sleep(3600)  # Check every hour


async def generate_weekly_reports():
    """Generate and email weekly reports for all active clients."""
    now = datetime.now(timezone.utc)
    # Only run on Mondays
    if now.weekday() != 0 or now.hour != 8:
        return

    async with async_session_factory() as db:
        result = await db.execute(
            select(Client).where(Client.is_active == True)
        )
        clients = result.scalars().all()

        for client in clients:
            try:
                metrics = await get_dashboard_metrics(db, str(client.id), "7d")
                logger.info(
                    "Weekly report for %s: %d leads, %d booked, %.1f%% conversion",
                    client.business_name,
                    metrics.total_leads,
                    metrics.total_booked,
                    metrics.conversion_rate * 100,
                )
                # Send email via SendGrid (if configured)
                if client.owner_email:
                    await _send_report_email(client, metrics)
            except Exception as e:
                logger.error("Report failed for %s: %s", client.business_name, str(e))


async def _send_report_email(client: Client, metrics) -> bool:
    """Send weekly report email via SendGrid."""
    from src.config import get_settings
    settings = get_settings()

    if not settings.sendgrid_api_key:
        logger.warning("SendGrid not configured - skipping email for %s", client.business_name)
        return False

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=(settings.sendgrid_from_email, settings.sendgrid_from_name),
            to_emails=client.owner_email,
            subject=f"LeadLock Weekly Report - {client.business_name}",
            html_content=_render_report_html(client, metrics),
        )

        sg = SendGridAPIClient(settings.sendgrid_api_key)
        # Offload synchronous SendGrid SDK call to thread pool
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: sg.send(message))
        logger.info("Weekly report emailed to %s", client.owner_email)
        return True
    except Exception as e:
        logger.error("SendGrid email failed: %s", str(e))
        return False


def _render_report_html(client, metrics) -> str:
    """Render report email HTML."""
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #f8fafc; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px;">
        <h1 style="color: #1a6df5;">LeadLock Weekly Report</h1>
        <h2 style="color: #334155;">{client.business_name}</h2>
        <hr style="border-color: #e2e8f0;">
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 8px 0; color: #64748b;">Total Leads</td><td style="text-align: right; font-weight: bold;">{metrics.total_leads}</td></tr>
            <tr><td style="padding: 8px 0; color: #64748b;">Booked</td><td style="text-align: right; font-weight: bold; color: #10b981;">{metrics.total_booked}</td></tr>
            <tr><td style="padding: 8px 0; color: #64748b;">Conversion Rate</td><td style="text-align: right; font-weight: bold;">{metrics.conversion_rate * 100:.1f}%</td></tr>
            <tr><td style="padding: 8px 0; color: #64748b;">Avg Response Time</td><td style="text-align: right; font-weight: bold;">{metrics.avg_response_time_ms / 1000:.1f}s</td></tr>
            <tr><td style="padding: 8px 0; color: #64748b;">Under 60s Rate</td><td style="text-align: right; font-weight: bold;">{metrics.leads_under_60s_pct:.0f}%</td></tr>
        </table>
        <hr style="border-color: #e2e8f0;">
        <p style="color: #94a3b8; font-size: 12px; text-align: center;">Powered by LeadLock AI</p>
    </div>
    </body>
    </html>
    """
