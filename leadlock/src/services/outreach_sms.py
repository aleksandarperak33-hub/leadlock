"""
Outreach SMS service - sends follow-up SMS to warm prospects via Twilio.
TCPA compliance: SMS ONLY triggers after prospect replies to an email
expressing interest. Cold SMS without consent is illegal.

Compliance checks:
1. Prospect must have replied to a prior email (consent via engagement)
2. Prospect must not be unsubscribed
3. Must be within quiet hours (8am-9pm local time)
4. Must include opt-out language
5. Must identify business
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.outreach import Outreach
from src.models.outreach_sms import OutreachSMS
from src.models.sales_config import SalesEngineConfig
from src.config import get_settings
from src.services.ai import generate_response
from src.prompts.humanizer import SMS_HUMANIZER

logger = logging.getLogger(__name__)

# US state timezone mapping for quiet hours enforcement
STATE_TIMEZONES: dict[str, str] = {
    "HI": "Pacific/Honolulu", "AK": "America/Anchorage",
    "WA": "America/Los_Angeles", "OR": "America/Los_Angeles",
    "CA": "America/Los_Angeles", "NV": "America/Los_Angeles",
    "ID": "America/Boise", "MT": "America/Denver",
    "WY": "America/Denver", "UT": "America/Denver",
    "CO": "America/Denver", "AZ": "America/Phoenix",
    "NM": "America/Denver", "ND": "America/Chicago",
    "SD": "America/Chicago", "NE": "America/Chicago",
    "KS": "America/Chicago", "OK": "America/Chicago",
    "TX": "America/Chicago", "MN": "America/Chicago",
    "IA": "America/Chicago", "MO": "America/Chicago",
    "AR": "America/Chicago", "LA": "America/Chicago",
    "WI": "America/Chicago", "IL": "America/Chicago",
    "MS": "America/Chicago", "AL": "America/Chicago",
    "TN": "America/Chicago", "MI": "America/Detroit",
    "IN": "America/Indiana/Indianapolis", "OH": "America/New_York",
    "KY": "America/New_York", "WV": "America/New_York",
    "VA": "America/New_York", "NC": "America/New_York",
    "SC": "America/New_York", "GA": "America/New_York",
    "FL": "America/New_York", "PA": "America/New_York",
    "NY": "America/New_York", "NJ": "America/New_York",
    "DE": "America/New_York", "MD": "America/New_York",
    "DC": "America/New_York", "CT": "America/New_York",
    "RI": "America/New_York", "MA": "America/New_York",
    "VT": "America/New_York", "NH": "America/New_York",
    "ME": "America/New_York",
}


def _get_prospect_timezone(state_code: Optional[str]) -> ZoneInfo:
    """Get timezone for a prospect based on their state code."""
    if state_code and state_code.upper() in STATE_TIMEZONES:
        return ZoneInfo(STATE_TIMEZONES[state_code.upper()])
    return ZoneInfo("America/Chicago")  # Default to Central


def is_within_sms_quiet_hours(state_code: Optional[str]) -> bool:
    """
    Check if current time is within TCPA quiet hours for the prospect's state.
    SMS must only be sent 8am-9pm local time.

    Returns:
        True if sending is allowed (NOT quiet hours), False if quiet hours.
    """
    tz = _get_prospect_timezone(state_code)
    now_local = datetime.now(tz)

    # TCPA general: 8am-9pm local time
    if now_local.hour < 8 or now_local.hour >= 21:
        return False

    # Florida FTSA: 8am-8pm
    if state_code and state_code.upper() == "FL" and now_local.hour >= 20:
        return False

    # Texas SB 140: Sunday only noon-9pm
    if state_code and state_code.upper() == "TX" and now_local.weekday() == 6:
        if now_local.hour < 12:
            return False

    return True


async def send_outreach_sms(
    db: AsyncSession,
    prospect: Outreach,
    config: SalesEngineConfig,
    message_body: str,
) -> dict:
    """
    Send a follow-up SMS to a warm prospect.

    Pre-conditions (caller must verify):
    - Prospect has replied to a prior email (consent via engagement)
    - config.sms_after_email_reply is True
    - Prospect has a phone number

    Args:
        db: Database session
        prospect: Outreach record with phone number
        config: Sales engine configuration
        message_body: The SMS body text

    Returns:
        Dict with status, twilio_sid, cost_usd, or error
    """
    # Validate prerequisites
    if not prospect.prospect_phone:
        return {"error": "Prospect has no phone number"}

    if prospect.email_unsubscribed:
        return {"error": "Prospect is unsubscribed"}

    if not prospect.last_email_replied_at:
        return {"error": "TCPA: Cannot SMS prospect without prior email reply (no consent)"}

    from_phone = getattr(config, "sms_from_phone", None)
    if not from_phone:
        return {"error": "SMS from phone not configured"}

    # Quiet hours check
    if not is_within_sms_quiet_hours(prospect.state_code):
        return {"error": "TCPA quiet hours - SMS deferred"}

    # Append opt-out language (TCPA required)
    full_body = f"{message_body}\n\nReply STOP to opt out. - LeadLock"

    # Send via Twilio
    settings = get_settings()
    try:
        from twilio.rest import Client as TwilioClient

        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        # Offload synchronous Twilio SDK call to thread pool
        loop = asyncio.get_running_loop()
        message = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                body=full_body,
                from_=from_phone,
                to=prospect.prospect_phone,
            ),
        )

        twilio_sid = message.sid
        cost_usd = 0.0079  # Approximate per-segment cost

        # Record SMS
        sms_record = OutreachSMS(
            outreach_id=prospect.id,
            direction="outbound",
            body=full_body,
            from_phone=from_phone,
            to_phone=prospect.prospect_phone,
            twilio_sid=twilio_sid,
            status="sent",
            cost_usd=cost_usd,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(sms_record)

        # Update prospect cost
        prospect.total_cost_usd = (prospect.total_cost_usd or 0.0) + cost_usd
        prospect.updated_at = datetime.now(timezone.utc)

        logger.info(
            "Outreach SMS sent: prospect=%s to=%s sid=%s",
            str(prospect.id)[:8],
            prospect.prospect_phone[:6] + "***",
            twilio_sid,
        )

        return {
            "status": "sent",
            "twilio_sid": twilio_sid,
            "cost_usd": cost_usd,
        }

    except Exception as e:
        logger.error(
            "Failed to send outreach SMS to %s: %s",
            prospect.prospect_phone[:6] + "***",
            str(e),
        )

        # Record failed attempt
        sms_record = OutreachSMS(
            outreach_id=prospect.id,
            direction="outbound",
            body=full_body,
            from_phone=from_phone,
            to_phone=prospect.prospect_phone,
            status="failed",
            cost_usd=0.0,
        )
        db.add(sms_record)

        return {"error": f"Twilio send failed: {str(e)}"}


async def generate_followup_sms_body(
    prospect: Outreach,
) -> str:
    """
    Generate a brief follow-up SMS body for a warm prospect.
    Uses AI for personalization based on prospect details.

    Returns:
        SMS body text (without opt-out footer - caller appends it)
    """
    try:
        prompt = (
            f"Write a brief, friendly follow-up SMS (under 160 chars) for a "
            f"{prospect.prospect_trade_type or 'home services'} company called "
            f"'{prospect.prospect_company or prospect.prospect_name}' "
            f"in {prospect.city or 'their area'}, {prospect.state_code or ''}. "
            f"They replied to our email about our lead management platform. "
            f"Keep it conversational and suggest a quick call. "
            f"Do NOT include any greeting like 'Hi' - get straight to the point."
        )

        result = await generate_response(
            system_prompt=(
                "You write concise, compliant outreach SMS messages. "
                "Keep responses under 160 characters.\n\n"
                + SMS_HUMANIZER
            ),
            user_message=prompt,
            model_tier="fast",
            max_tokens=100,
        )

        if result.get("content"):
            return result["content"].strip()
        raise RuntimeError(result.get("error") or "AI returned empty content")

    except Exception as e:
        logger.warning("AI SMS generation failed, using template: %s", str(e))
        company = prospect.prospect_company or prospect.prospect_name
        return (
            f"Thanks for your interest! Would you have 15 min this week "
            f"for a quick call about how LeadLock can help {company} "
            f"capture more leads?"
        )
