"""
Transactional email service - SendGrid-based emails for auth flows and billing notifications.

Separate from cold_email.py: uses a different sender identity (noreply@) and
does NOT include CAN-SPAM footer or tracking (transactional emails are exempt).
"""
import asyncio
import logging
from typing import Optional

from src.config import get_settings

logger = logging.getLogger(__name__)


async def _send_transactional(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str,
) -> dict:
    """
    Send a transactional email via SendGrid.

    Returns: {"message_id": str|None, "status": str, "error": str|None}
    """
    settings = get_settings()
    api_key = settings.sendgrid_transactional_key or settings.sendgrid_api_key
    from_email = settings.from_email_transactional or "noreply@leadlock.org"

    if not api_key:
        logger.error("No SendGrid API key configured for transactional email")
        return {"message_id": None, "status": "error", "error": "SendGrid not configured"}

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To, Content

        message = Mail(
            from_email=Email(from_email, "LeadLock"),
            to_emails=To(to_email),
            subject=subject,
        )
        message.content = [
            Content("text/plain", text_content),
            Content("text/html", html_content),
        ]

        sg = SendGridAPIClient(api_key=api_key)
        # Offload synchronous SendGrid SDK call to thread pool
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: sg.send(message))
        message_id = response.headers.get("X-Message-Id", "")

        logger.info(
            "Transactional email sent: to=%s subject=%s",
            to_email[:20] + "***", subject[:40],
        )
        return {"message_id": message_id, "status": "sent", "error": None}

    except Exception as e:
        logger.error(
            "Transactional email failed: to=%s error=%s",
            to_email[:20] + "***", str(e),
        )
        return {"message_id": None, "status": "error", "error": str(e)}


async def send_password_reset(email: str, reset_token: str, reset_url: str) -> dict:
    """Send password reset email with a reset link."""
    full_url = f"{reset_url}?token={reset_token}"

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
      <div style="text-align: center; margin-bottom: 32px;">
        <div style="display: inline-block; background: #f97316; width: 40px; height: 40px; border-radius: 10px; line-height: 40px; text-align: center;">
          <span style="color: white; font-weight: bold; font-size: 18px;">L</span>
        </div>
        <h2 style="margin: 12px 0 0; color: #111; font-size: 20px;">Reset Your Password</h2>
      </div>
      <p style="color: #555; font-size: 15px; line-height: 1.6;">
        We received a request to reset your password. Click the button below to create a new password.
      </p>
      <div style="text-align: center; margin: 32px 0;">
        <a href="{full_url}" style="background: #f97316; color: white; padding: 12px 32px; border-radius: 10px; text-decoration: none; font-weight: 600; font-size: 15px; display: inline-block;">
          Reset Password
        </a>
      </div>
      <p style="color: #999; font-size: 13px; line-height: 1.5;">
        This link expires in 1 hour. If you didn't request a password reset, you can safely ignore this email.
      </p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
      <p style="color: #bbb; font-size: 11px; text-align: center;">LeadLock &mdash; AI Speed-to-Lead Platform</p>
    </div>
    """

    text = (
        "Reset Your Password\n\n"
        "We received a request to reset your password. "
        f"Click the link below to create a new password:\n\n{full_url}\n\n"
        "This link expires in 1 hour. If you didn't request a password reset, "
        "you can safely ignore this email.\n\n"
        "-- LeadLock"
    )

    return await _send_transactional(email, "Reset your LeadLock password", html, text)


async def send_email_verification(email: str, verify_token: str, verify_url: str) -> dict:
    """Send email verification link after signup."""
    full_url = f"{verify_url}?token={verify_token}"

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
      <div style="text-align: center; margin-bottom: 32px;">
        <div style="display: inline-block; background: #f97316; width: 40px; height: 40px; border-radius: 10px; line-height: 40px; text-align: center;">
          <span style="color: white; font-weight: bold; font-size: 18px;">L</span>
        </div>
        <h2 style="margin: 12px 0 0; color: #111; font-size: 20px;">Verify Your Email</h2>
      </div>
      <p style="color: #555; font-size: 15px; line-height: 1.6;">
        Welcome to LeadLock! Please verify your email address to get started.
      </p>
      <div style="text-align: center; margin: 32px 0;">
        <a href="{full_url}" style="background: #f97316; color: white; padding: 12px 32px; border-radius: 10px; text-decoration: none; font-weight: 600; font-size: 15px; display: inline-block;">
          Verify Email
        </a>
      </div>
      <p style="color: #999; font-size: 13px; line-height: 1.5;">
        This link expires in 24 hours. If you didn't create a LeadLock account, you can safely ignore this email.
      </p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
      <p style="color: #bbb; font-size: 11px; text-align: center;">LeadLock &mdash; AI Speed-to-Lead Platform</p>
    </div>
    """

    text = (
        "Verify Your Email\n\n"
        "Welcome to LeadLock! Please verify your email address by clicking the link below:\n\n"
        f"{full_url}\n\n"
        "This link expires in 24 hours. If you didn't create a LeadLock account, "
        "you can safely ignore this email.\n\n"
        "-- LeadLock"
    )

    return await _send_transactional(email, "Verify your LeadLock email", html, text)


async def send_welcome_email(email: str, business_name: str) -> dict:
    """Send welcome email after successful verification."""
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
      <div style="text-align: center; margin-bottom: 32px;">
        <div style="display: inline-block; background: #f97316; width: 40px; height: 40px; border-radius: 10px; line-height: 40px; text-align: center;">
          <span style="color: white; font-weight: bold; font-size: 18px;">L</span>
        </div>
        <h2 style="margin: 12px 0 0; color: #111; font-size: 20px;">Welcome to LeadLock!</h2>
      </div>
      <p style="color: #555; font-size: 15px; line-height: 1.6;">
        Hey {business_name} team! Your email is verified and your account is ready.
      </p>
      <p style="color: #555; font-size: 15px; line-height: 1.6;">Here's what to do next:</p>
      <ol style="color: #555; font-size: 15px; line-height: 1.8; padding-left: 20px;">
        <li>Complete onboarding &mdash; set up your AI persona and business hours</li>
        <li>Connect your CRM &mdash; ServiceTitan, Housecall Pro, Jobber, or GoHighLevel</li>
        <li>Provision a phone number &mdash; get your dedicated SMS line</li>
      </ol>
      <div style="text-align: center; margin: 32px 0;">
        <a href="https://leadlock.org/dashboard" style="background: #f97316; color: white; padding: 12px 32px; border-radius: 10px; text-decoration: none; font-weight: 600; font-size: 15px; display: inline-block;">
          Go to Dashboard
        </a>
      </div>
      <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
      <p style="color: #bbb; font-size: 11px; text-align: center;">LeadLock &mdash; AI Speed-to-Lead Platform</p>
    </div>
    """

    text = (
        f"Welcome to LeadLock, {business_name}!\n\n"
        "Your email is verified and your account is ready.\n\n"
        "Next steps:\n"
        "1. Complete onboarding - set up your AI persona and business hours\n"
        "2. Connect your CRM - ServiceTitan, Housecall Pro, Jobber, or GoHighLevel\n"
        "3. Provision a phone number - get your dedicated SMS line\n\n"
        "Go to your dashboard: https://leadlock.org/dashboard\n\n"
        "-- LeadLock"
    )

    return await _send_transactional(email, f"Welcome to LeadLock, {business_name}!", html, text)


async def send_subscription_confirmation(
    email: str,
    plan_name: str,
    amount: str,
) -> dict:
    """Send subscription confirmation after successful payment."""
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
      <div style="text-align: center; margin-bottom: 32px;">
        <div style="display: inline-block; background: #f97316; width: 40px; height: 40px; border-radius: 10px; line-height: 40px; text-align: center;">
          <span style="color: white; font-weight: bold; font-size: 18px;">L</span>
        </div>
        <h2 style="margin: 12px 0 0; color: #111; font-size: 20px;">Subscription Confirmed</h2>
      </div>
      <p style="color: #555; font-size: 15px; line-height: 1.6;">
        Your <strong>{plan_name}</strong> plan is now active at <strong>{amount}/month</strong>.
      </p>
      <p style="color: #555; font-size: 15px; line-height: 1.6;">
        You now have full access to all {plan_name} features. Manage your subscription anytime from your dashboard.
      </p>
      <div style="text-align: center; margin: 32px 0;">
        <a href="https://leadlock.org/billing" style="background: #f97316; color: white; padding: 12px 32px; border-radius: 10px; text-decoration: none; font-weight: 600; font-size: 15px; display: inline-block;">
          Manage Billing
        </a>
      </div>
      <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
      <p style="color: #bbb; font-size: 11px; text-align: center;">LeadLock &mdash; AI Speed-to-Lead Platform</p>
    </div>
    """

    text = (
        "Subscription Confirmed\n\n"
        f"Your {plan_name} plan is now active at {amount}/month.\n\n"
        f"You now have full access to all {plan_name} features. "
        "Manage your subscription anytime from your dashboard.\n\n"
        "Manage billing: https://leadlock.org/billing\n\n"
        "-- LeadLock"
    )

    return await _send_transactional(email, f"LeadLock {plan_name} Plan Confirmed", html, text)


async def send_payment_failed(email: str, business_name: str) -> dict:
    """Send payment failure notification."""
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
      <div style="text-align: center; margin-bottom: 32px;">
        <div style="display: inline-block; background: #ef4444; width: 40px; height: 40px; border-radius: 10px; line-height: 40px; text-align: center;">
          <span style="color: white; font-weight: bold; font-size: 18px;">!</span>
        </div>
        <h2 style="margin: 12px 0 0; color: #111; font-size: 20px;">Payment Failed</h2>
      </div>
      <p style="color: #555; font-size: 15px; line-height: 1.6;">
        Hi {business_name}, we were unable to process your latest payment. Please update your payment method to avoid service interruption.
      </p>
      <div style="text-align: center; margin: 32px 0;">
        <a href="https://leadlock.org/billing" style="background: #ef4444; color: white; padding: 12px 32px; border-radius: 10px; text-decoration: none; font-weight: 600; font-size: 15px; display: inline-block;">
          Update Payment Method
        </a>
      </div>
      <p style="color: #999; font-size: 13px; line-height: 1.5;">
        If your payment is not updated within 7 days, your account will be paused and lead response will stop.
      </p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 32px 0;" />
      <p style="color: #bbb; font-size: 11px; text-align: center;">LeadLock &mdash; AI Speed-to-Lead Platform</p>
    </div>
    """

    text = (
        "Payment Failed\n\n"
        f"Hi {business_name}, we were unable to process your latest payment. "
        "Please update your payment method to avoid service interruption.\n\n"
        "Update payment: https://leadlock.org/billing\n\n"
        "If your payment is not updated within 7 days, your account will be "
        "paused and lead response will stop.\n\n"
        "-- LeadLock"
    )

    return await _send_transactional(email, "LeadLock: Payment Failed - Action Required", html, text)
