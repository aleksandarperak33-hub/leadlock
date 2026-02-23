"""
Sales Engine — Webhook endpoints (inbound email, email events, unsubscribe).
Public endpoints that don't require admin auth.
"""
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.sales_config import SalesEngineConfig
from src.models.email_blacklist import EmailBlacklist

logger = logging.getLogger(__name__)

router = APIRouter()

# Common email provider domains that should NEVER be domain-blacklisted.
# Individual emails at these domains CAN still be blacklisted.
_PROTECTED_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com",
    "live.com", "msn.com", "yahoo.com", "aol.com", "icloud.com",
    "me.com", "mac.com", "mail.com", "protonmail.com", "zoho.com",
    "yandex.com", "comcast.net", "att.net", "sbcglobal.net",
    "verizon.net", "cox.net", "charter.net", "earthlink.net",
})


async def _record_email_signal(
    signal_type: str,
    prospect: Outreach,
    email_record,
    value: float,
) -> None:
    """Record a learning signal from an email event."""
    try:
        from src.services.learning import record_signal, _time_bucket

        sent_hour = email_record.sent_at.hour if email_record.sent_at else 12
        sent_day = email_record.sent_at.strftime("%A").lower() if email_record.sent_at else "unknown"

        dimensions = {
            "trade": prospect.prospect_trade_type or "general",
            "city": prospect.city or "",
            "state": prospect.state_code or "",
            "step": str(email_record.sequence_step),
            "time_bucket": _time_bucket(sent_hour),
            "day_of_week": sent_day,
        }

        await record_signal(
            signal_type=signal_type,
            dimensions=dimensions,
            value=value,
            outreach_id=str(prospect.id),
        )
    except Exception as e:
        logger.warning("Failed to record learning signal: %s", str(e))


async def _send_booking_reply(
    db: AsyncSession,
    prospect: Outreach,
    config: Optional[SalesEngineConfig],
    original_subject: str = "",
    reply_text: str = "",
) -> bool:
    """
    Send auto-reply email with booking link to an interested prospect.
    Returns True if sent successfully, False otherwise.
    """
    if not config or not config.booking_url:
        logger.info(
            "No booking URL configured, skipping auto-reply for %s",
            str(prospect.id)[:8],
        )
        return False

    if not config.from_email:
        return False

    from src.agents.sales_outreach import generate_booking_reply
    from src.services.cold_email import send_cold_email

    # Generate the reply with context from their message and enrichment data
    reply = await generate_booking_reply(
        prospect_name=prospect.prospect_name or "",
        trade_type=prospect.prospect_trade_type or "",
        city=prospect.city or "",
        booking_url=config.booking_url,
        sender_name=config.sender_name or "Alek",
        original_subject=original_subject,
        reply_text=reply_text,
        enrichment_data=prospect.enrichment_data,
    )

    if reply.get("error") or not reply.get("body_html"):
        logger.warning("Auto-reply generation failed for %s", str(prospect.id)[:8])
        return False

    # Build unsubscribe URL
    from src.config import get_settings
    settings = get_settings()
    base_url = getattr(settings, "app_base_url", "") or "https://api.leadlock.org"
    unsubscribe_url = f"{base_url}/api/v1/sales/unsubscribe/{prospect.id}"

    # Send via SendGrid
    send_result = await send_cold_email(
        to_email=prospect.prospect_email,
        to_name=prospect.prospect_name or "",
        subject=reply["subject"],
        body_html=reply["body_html"],
        from_email=config.from_email,
        from_name=config.from_name or "Alek from LeadLock",
        reply_to=config.reply_to_email or config.from_email,
        unsubscribe_url=unsubscribe_url,
        company_address=config.company_address or "",
        body_text=reply.get("body_text", ""),
        company_name="LeadLock",
    )

    if send_result.get("error"):
        logger.warning(
            "Auto-reply send failed for %s: %s",
            str(prospect.id)[:8], send_result["error"],
        )
        return False

    # Record the outbound reply
    now = datetime.now(timezone.utc)
    reply_record = OutreachEmail(
        outreach_id=prospect.id,
        direction="outbound",
        subject=reply["subject"],
        body_html=reply["body_html"],
        body_text=reply.get("body_text", ""),
        from_email=config.from_email,
        to_email=prospect.prospect_email,
        sequence_step=prospect.outreach_sequence_step,
        sent_at=now,
        ai_cost_usd=reply.get("ai_cost_usd", 0.0),
        sendgrid_message_id=send_result.get("message_id"),
    )
    db.add(reply_record)
    await db.commit()

    logger.info(
        "Auto-reply sent to %s with booking link",
        str(prospect.id)[:8],
    )
    return True


async def _trigger_sms_followup(
    db: AsyncSession,
    prospect: Outreach,
) -> bool:
    """
    Trigger SMS follow-up for an interested prospect.
    Only sends if config.sms_after_email_reply is enabled and prospect has phone.
    Uses task queue for deferred delivery during quiet hours.

    Returns True if SMS was sent or queued, False otherwise.
    """
    result = await db.execute(select(SalesEngineConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        return False

    if not getattr(config, "sms_after_email_reply", False):
        return False

    if not prospect.prospect_phone:
        logger.debug("No phone for prospect %s, skipping SMS", str(prospect.id)[:8])
        return False

    from src.services.outreach_sms import (
        is_within_sms_quiet_hours,
        send_outreach_sms,
        generate_followup_sms_body,
    )

    # Check quiet hours - if outside, queue for later via task queue
    if not is_within_sms_quiet_hours(prospect.state_code):
        try:
            from src.services.task_dispatch import enqueue_task

            await enqueue_task(
                task_type="send_sms_followup",
                payload={
                    "outreach_id": str(prospect.id),
                },
                priority=7,
                delay_seconds=3600,  # Retry in 1 hour
            )
            logger.info(
                "SMS deferred (quiet hours) for prospect %s, queued for later",
                str(prospect.id)[:8],
            )
            return True
        except Exception as e:
            logger.warning("Failed to queue deferred SMS: %s", str(e))
            return False

    # Generate and send SMS immediately
    body = await generate_followup_sms_body(prospect)
    sms_result = await send_outreach_sms(db, prospect, config, body)

    if sms_result.get("error"):
        logger.warning(
            "SMS follow-up failed for %s: %s",
            str(prospect.id)[:8], sms_result["error"],
        )
        return False

    return True


# === WEBHOOK VERIFICATION ===

async def _verify_sendgrid_webhook(request: Request) -> bool:
    """
    Verify SendGrid webhook authenticity using a shared secret token.

    The webhook URL should include ?token=<secret> when configured in SendGrid.
    This is secure over HTTPS and simpler than implementing SendGrid's ECDSA
    signature verification (which requires the cryptography library).

    Returns True if valid or if no verification key is configured (with warning).
    """
    from src.config import get_settings
    settings = get_settings()
    verification_key = settings.sendgrid_webhook_verification_key

    if not verification_key:
        if settings.app_env == "production":
            logger.error(
                "SENDGRID_WEBHOOK_VERIFICATION_KEY not set in production - "
                "rejecting unauthenticated webhook traffic."
            )
            return False
        logger.warning(
            "SENDGRID_WEBHOOK_VERIFICATION_KEY not set - accepting webhook without "
            "verification. Set this key and add ?token=<key> to your SendGrid webhook URLs."
        )
        return True

    # Check token from query parameter or custom header
    token = request.query_params.get("token", "")
    if not token:
        token = request.headers.get("X-Webhook-Token", "")

    if not token:
        logger.warning("SendGrid webhook missing verification token")
        return False

    return hmac.compare_digest(token, verification_key)


# === PUBLIC ENDPOINTS (webhooks, unsubscribe) ===

@router.post("/inbound-email")
async def inbound_email_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    SendGrid Inbound Parse webhook - handles email replies from prospects.
    When a prospect replies, update their outreach record and record the email.
    """
    try:
        # Verify webhook authenticity
        if not await _verify_sendgrid_webhook(request):
            logger.warning("Rejected inbound email webhook: invalid token")
            raise HTTPException(status_code=403, detail="Invalid webhook token")

        form = await request.form()
        from_email = form.get("from", "")
        to_email = form.get("to", "")
        subject = form.get("subject", "")
        text_body = form.get("text", "")
        html_body = form.get("html", "")

        # Extract email address from "Name <email>" format
        if "<" in from_email and ">" in from_email:
            from_email = from_email.split("<")[1].split(">")[0]

        if not from_email:
            return {"status": "ignored", "reason": "no from email"}

        # Find matching prospect
        result = await db.execute(
            select(Outreach).where(
                Outreach.prospect_email == from_email.lower().strip()
            ).limit(1)
        )
        prospect = result.scalar_one_or_none()

        if not prospect:
            logger.info("Inbound email from unknown sender: %s", from_email[:20] + "***")
            return {"status": "ignored", "reason": "unknown sender"}

        # Load config for auto-reply settings
        config_result = await db.execute(select(SalesEngineConfig).limit(1))
        config = config_result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        # Record inbound email
        email_record = OutreachEmail(
            outreach_id=prospect.id,
            direction="inbound",
            subject=subject,
            body_html=html_body,
            body_text=text_body,
            from_email=from_email,
            to_email=to_email,
            sequence_step=prospect.outreach_sequence_step,
            sent_at=now,
        )
        db.add(email_record)

        # Classify reply with AI
        from src.agents.sales_outreach import classify_reply
        classification_result = await classify_reply(text_body or html_body)
        classification = classification_result["classification"]

        # Update prospect based on classification
        prospect.last_email_replied_at = now
        prospect.updated_at = now

        if classification == "interested":
            prospect.status = "demo_scheduled"
        elif classification == "rejection":
            prospect.status = "lost"
        elif classification == "unsubscribe":
            prospect.email_unsubscribed = True
            prospect.unsubscribed_at = now
            prospect.status = "lost"
        # auto_reply / out_of_office -> no status change

        # Record learning signal for reply
        if classification in ("interested", "rejection"):
            signal_value = 1.0 if classification == "interested" else 0.0
            await _record_email_signal(
                "email_replied", prospect, email_record, signal_value,
            )

        # Persist reply classification and prospect updates before attempting SMS
        await db.commit()

        # Auto-reply + SMS follow-up for interested prospects
        auto_reply_sent = False
        sms_sent = False
        if classification == "interested":
            # Check if we already auto-replied recently (prevent spamming on multiple replies)
            recent_reply = await db.execute(
                select(OutreachEmail).where(
                    and_(
                        OutreachEmail.outreach_id == prospect.id,
                        OutreachEmail.direction == "outbound",
                        OutreachEmail.sent_at >= datetime.now(timezone.utc) - timedelta(hours=24),
                        OutreachEmail.sequence_step == prospect.outreach_sequence_step,
                    )
                ).limit(1)
            )
            if recent_reply.scalar_one_or_none():
                logger.info(
                    "Skipping auto-reply for %s - already replied within 24h",
                    str(prospect.id)[:8],
                )
            else:
                # Send auto-reply email with booking link
                try:
                    auto_reply_sent = await _send_booking_reply(
                        db, prospect, config, subject,
                        reply_text=text_body or "",
                    )
                except Exception as reply_err:
                    logger.warning(
                        "Auto-reply failed for %s: %s",
                        str(prospect.id)[:8], str(reply_err),
                    )

            # SMS follow-up (optional, if configured)
            try:
                sms_sent = await _trigger_sms_followup(db, prospect)
            except Exception as sms_err:
                logger.warning(
                    "SMS follow-up trigger failed for %s: %s",
                    str(prospect.id)[:8], str(sms_err),
                )

        logger.info(
            "Inbound reply from prospect %s (%s) classified=%s auto_reply=%s sms=%s",
            str(prospect.id)[:8], from_email[:20] + "***",
            classification, auto_reply_sent, sms_sent,
        )

        return {
            "status": "processed",
            "prospect_id": str(prospect.id),
            "classification": classification,
            "auto_reply_sent": auto_reply_sent,
            "sms_sent": sms_sent,
        }

    except Exception as e:
        logger.error("Inbound email processing error: %s", str(e), exc_info=True)
        return {"status": "error"}


@router.post("/email-events")
async def email_events_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    SendGrid Event Webhook - tracks opens, clicks, bounces, etc.
    Events are matched by sendgrid_message_id or custom args.
    """
    try:
        # Verify webhook authenticity
        if not await _verify_sendgrid_webhook(request):
            logger.warning("Rejected email events webhook: invalid token")
            raise HTTPException(status_code=403, detail="Invalid webhook token")

        events = await request.json()
        if not isinstance(events, list):
            events = [events]

        for event in events:
            try:
                event_type = event.get("event", "")
                sg_message_id = event.get("sg_message_id", "").split(".")[0]
                outreach_id = event.get("outreach_id")
                timestamp = datetime.fromtimestamp(event.get("timestamp", 0), tz=timezone.utc)

                # Find email record
                email_record = None
                if sg_message_id:
                    result = await db.execute(
                        select(OutreachEmail).where(
                            OutreachEmail.sendgrid_message_id == sg_message_id
                        ).limit(1)
                    )
                    email_record = result.scalar_one_or_none()

                if not email_record and outreach_id:
                    # Fallback: find by outreach_id + step
                    step = event.get("step")
                    if step:
                        result = await db.execute(
                            select(OutreachEmail).where(
                                and_(
                                    OutreachEmail.outreach_id == uuid.UUID(outreach_id),
                                    OutreachEmail.sequence_step == int(step),
                                )
                            ).limit(1)
                        )
                        email_record = result.scalar_one_or_none()

                if not email_record:
                    continue

                # Get Redis for reputation tracking
                try:
                    from src.utils.dedup import get_redis
                    from src.services.deliverability import record_email_event
                    redis = await get_redis()
                except Exception as redis_err:
                    logger.debug("Redis unavailable for email reputation: %s", str(redis_err))
                    redis = None

                # Update email record based on event type
                if event_type == "delivered" and not email_record.delivered_at:
                    email_record.delivered_at = timestamp
                    # Record reputation event
                    if redis:
                        try:
                            await record_email_event(redis, "delivered")
                        except Exception as e:
                            logger.debug("Redis event recording failed: %s", str(e))
                elif event_type == "open" and not email_record.opened_at:
                    email_record.opened_at = timestamp
                    # Record reputation event
                    if redis:
                        try:
                            await record_email_event(redis, "opened")
                        except Exception as e:
                            logger.debug("Redis event recording failed: %s", str(e))
                    # Also update prospect
                    if outreach_id:
                        prospect = await db.get(Outreach, uuid.UUID(outreach_id))
                        if prospect:
                            prospect.last_email_opened_at = timestamp
                            # Record learning signal
                            await _record_email_signal(
                                "email_opened", prospect, email_record, 1.0,
                            )
                elif event_type == "click" and not email_record.clicked_at:
                    email_record.clicked_at = timestamp
                    # Record reputation event
                    if redis:
                        try:
                            await record_email_event(redis, "clicked")
                        except Exception as e:
                            logger.debug("Redis event recording failed: %s", str(e))
                    if outreach_id:
                        prospect = await db.get(Outreach, uuid.UUID(outreach_id))
                        if prospect:
                            prospect.last_email_clicked_at = timestamp
                            await _record_email_signal(
                                "email_clicked", prospect, email_record, 1.0,
                            )
                elif event_type in ("bounce", "blocked"):
                    # Hard bounce or block - count as real bounce
                    email_record.bounced_at = timestamp
                    email_record.bounce_type = event.get("type", event_type)
                    email_record.bounce_reason = event.get("reason", "")
                    # Record reputation event
                    if redis:
                        try:
                            await record_email_event(redis, "bounced")
                        except Exception as e:
                            logger.debug("Redis event recording failed: %s", str(e))
                    # Hard bounce -> mark prospect as lost, flag email invalid
                    if event.get("type") == "bounce" or event_type == "bounce":
                        if outreach_id:
                            prospect = await db.get(Outreach, uuid.UUID(outreach_id))
                            if prospect:
                                prospect.email_verified = False
                                prospect.status = "lost"
                                prospect.updated_at = timestamp
                                await _record_email_signal(
                                    "email_bounced", prospect, email_record, 0.0,
                                )
                                # Auto-blacklist email address on hard bounce;
                                # blacklist domain only after 3+ distinct email bounces
                                try:
                                    if prospect.prospect_email and "@" in prospect.prospect_email:
                                        email_addr = prospect.prospect_email.lower().strip()
                                        domain = email_addr.split("@")[1]
                                        if domain:
                                            # Blacklist the individual email address first
                                            existing_email = await db.execute(
                                                select(EmailBlacklist).where(
                                                    and_(
                                                        EmailBlacklist.entry_type == "email",
                                                        EmailBlacklist.value == email_addr,
                                                    )
                                                ).limit(1)
                                            )
                                            if not existing_email.scalar_one_or_none():
                                                email_blacklist_entry = EmailBlacklist(
                                                    entry_type="email",
                                                    value=email_addr,
                                                    reason="Hard bounce",
                                                )
                                                db.add(email_blacklist_entry)
                                                logger.info(
                                                    "Auto-blacklisted email %s after hard bounce",
                                                    email_addr[:20] + "***",
                                                )

                                            # Blacklist domain only after 3+ distinct bounced emails
                                            # Never blacklist common email providers (gmail, outlook, etc.)
                                            if domain in _PROTECTED_DOMAINS:
                                                logger.debug(
                                                    "Skipping domain blacklist for protected provider %s",
                                                    domain,
                                                )
                                            else:
                                                existing_domain = await db.execute(
                                                    select(EmailBlacklist).where(
                                                        and_(
                                                            EmailBlacklist.entry_type == "domain",
                                                            EmailBlacklist.value == domain,
                                                        )
                                                    ).limit(1)
                                                )
                                                if not existing_domain.scalar_one_or_none():
                                                    bounce_count_result = await db.execute(
                                                        select(func.count()).select_from(EmailBlacklist).where(
                                                            and_(
                                                                EmailBlacklist.entry_type == "email",
                                                                EmailBlacklist.value.like(f"%@{domain}"),
                                                            )
                                                        )
                                                    )
                                                    bounce_count = bounce_count_result.scalar() or 0
                                                    if bounce_count >= 3:
                                                        domain_blacklist_entry = EmailBlacklist(
                                                            entry_type="domain",
                                                            value=domain,
                                                            reason="3+ hard bounces at domain",
                                                        )
                                                        db.add(domain_blacklist_entry)
                                                        logger.info(
                                                            "Auto-blacklisted domain %s after %d bounces",
                                                            domain, bounce_count,
                                                        )
                                except Exception as bl_err:
                                    logger.warning(
                                        "Failed to auto-blacklist email/domain: %s", str(bl_err)
                                    )
                elif event_type == "deferred":
                    # Deferred is temporary - do NOT count as bounce
                    email_record.bounce_type = "deferred"
                    email_record.bounce_reason = event.get("reason", "")
                    logger.info(
                        "Email %s deferred: %s",
                        str(email_record.id)[:8],
                        event.get("reason", "unknown"),
                    )
                    # Track soft bounces - mark unreachable after 3+ deferrals
                    if outreach_id:
                        prospect = await db.get(Outreach, uuid.UUID(outreach_id))
                        if prospect and prospect.prospect_email:
                            deferral_count_result = await db.execute(
                                select(func.count()).select_from(OutreachEmail).where(
                                    and_(
                                        OutreachEmail.outreach_id == prospect.id,
                                        OutreachEmail.bounce_type == "deferred",
                                    )
                                )
                            )
                            deferral_count = deferral_count_result.scalar() or 0
                            if deferral_count >= 3:
                                prospect.status = "unreachable"
                                prospect.email_verified = False
                                prospect.updated_at = timestamp
                                logger.warning(
                                    "Prospect %s marked unreachable after %d soft bounces",
                                    str(prospect.id)[:8], deferral_count,
                                )
                elif event_type == "spamreport":
                    # Record reputation event - spam complaints are CRITICAL
                    if redis:
                        try:
                            await record_email_event(redis, "complained")
                        except Exception as e:
                            logger.debug("Redis event recording failed: %s", str(e))
                    # Treat spam report as unsubscribe
                    if outreach_id:
                        prospect = await db.get(Outreach, uuid.UUID(outreach_id))
                        if prospect:
                            prospect.email_unsubscribed = True
                            prospect.unsubscribed_at = timestamp

                await db.commit()

            except Exception as event_err:
                logger.error(
                    "Error processing email event %s: %s",
                    event.get("event", "unknown"), str(event_err),
                )
                await db.rollback()

        return {"status": "processed", "events": len(events)}

    except Exception as e:
        logger.error("Email event processing error: %s", str(e))
        return {"status": "error"}


@router.get("/unsubscribe/{prospect_id}", response_class=HTMLResponse)
async def unsubscribe(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
):
    """CAN-SPAM one-click unsubscribe. Public endpoint."""
    try:
        pid = uuid.UUID(prospect_id)
        prospect = await db.get(Outreach, pid)
        if prospect:
            prospect.email_unsubscribed = True
            prospect.unsubscribed_at = datetime.now(timezone.utc)
            prospect.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Prospect %s unsubscribed", prospect_id[:8])
    except Exception as e:
        logger.error("Unsubscribe error: %s", str(e))

    return HTMLResponse(
        content="""<!DOCTYPE html>
<html><head><title>Unsubscribed</title>
<style>body{font-family:sans-serif;text-align:center;padding:60px 20px;color:#333}
h1{font-size:24px}p{color:#666;font-size:16px}</style></head>
<body><h1>You've been unsubscribed</h1>
<p>You will no longer receive emails from us.</p></body></html>""",
        status_code=200,
    )
