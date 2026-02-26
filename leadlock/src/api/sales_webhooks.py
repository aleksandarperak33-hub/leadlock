"""
Sales Engine — Webhook endpoints (inbound email, email events, unsubscribe).
Public endpoints that don't require admin auth.
"""
import hmac
import hashlib
import logging
import re
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
from src.services.sales_tenancy import (
    get_sales_config_for_tenant,
    resolve_tenant_ids_for_mailboxes,
)
from src.services.sender_mailboxes import (
    find_sender_profile_for_address,
    get_primary_sender_profile,
)

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

_EMAIL_REGEX = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)


def _normalize_email(raw: str) -> str:
    """Normalize a raw email-ish string to lowercase without surrounding spaces."""
    return str(raw or "").strip().lower()


def _extract_email_candidates(raw_value: str) -> list[str]:
    """
    Extract one or more email addresses from a header-like string.
    Handles values like:
      - "Name <user@example.com>"
      - "one@example.com, two@example.com"
    """
    raw = str(raw_value or "").strip()
    if not raw:
        return []
    matches = _EMAIL_REGEX.findall(raw)
    if not matches:
        normalized = _normalize_email(raw)
        return [normalized] if "@" in normalized else []
    deduped: list[str] = []
    for email in matches:
        normalized = _normalize_email(email)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _safe_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    """Parse UUID safely for webhook payloads that may contain bad IDs."""
    if not value:
        return None
    try:
        return uuid.UUID(str(value).strip())
    except Exception:
        return None


def _safe_event_timestamp(raw_ts) -> datetime:
    """Parse event timestamp safely, falling back to current UTC time."""
    try:
        if raw_ts is None:
            raise ValueError("missing")
        return datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


async def _is_duplicate_email_event(redis_client, event: dict) -> bool:
    """
    Best-effort dedupe for SendGrid events.
    Uses sg_event_id/event_id when present; falls back to a stable fingerprint.
    """
    try:
        raw_id = event.get("sg_event_id") or event.get("event_id")
        if raw_id:
            event_id = str(raw_id).strip()
        else:
            # Fallback fingerprint when provider event ID is missing.
            parts = [
                str(event.get("event", "")).strip().lower(),
                str(event.get("sg_message_id", "")).strip(),
                str(event.get("outreach_id", "")).strip(),
                str(event.get("step", "")).strip(),
                str(event.get("timestamp", "")).strip(),
            ]
            event_id = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

        dedupe_key = f"leadlock:email_event_seen:{event_id}"
        was_set = await redis_client.set(dedupe_key, "1", ex=172800, nx=True)
        # NX set returns falsy when key already exists.
        return not bool(was_set)
    except Exception as e:
        logger.debug("Email event dedupe unavailable: %s", str(e))
        return False


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
    reply_mailbox: Optional[str] = None,
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

    sender_profile = (
        find_sender_profile_for_address(config, reply_mailbox)
        if reply_mailbox
        else None
    ) or get_primary_sender_profile(config)
    if not sender_profile:
        return False

    from src.agents.sales_outreach import generate_booking_reply
    from src.services.cold_email import send_cold_email

    # Generate the reply with context from their message and enrichment data
    reply = await generate_booking_reply(
        prospect_name=prospect.prospect_name or "",
        trade_type=prospect.prospect_trade_type or "",
        city=prospect.city or "",
        booking_url=config.booking_url,
        sender_name=sender_profile["sender_name"],
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
        from_email=sender_profile["from_email"],
        from_name=sender_profile["from_name"] or "Alek from LeadLock",
        reply_to=sender_profile["reply_to_email"] or sender_profile["from_email"],
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
        from_email=sender_profile["from_email"],
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
    tenant_id = getattr(prospect, "tenant_id", None)
    config = await get_sales_config_for_tenant(db, tenant_id)

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
        from_email_raw = str(form.get("from", "") or "")
        to_email_raw = str(form.get("to", "") or "")
        subject = form.get("subject", "")
        text_body = form.get("text", "")
        html_body = form.get("html", "")

        from_candidates = _extract_email_candidates(from_email_raw)
        from_email = from_candidates[0] if from_candidates else _normalize_email(from_email_raw)
        inbound_to_candidates = _extract_email_candidates(to_email_raw)
        inbound_to_email = (
            inbound_to_candidates[0]
            if inbound_to_candidates
            else _normalize_email(to_email_raw)
        )
        to_email = inbound_to_email or to_email_raw.strip()

        if not from_email:
            return {"status": "ignored", "reason": "no from email"}

        prospect = None
        tenant_ids = await resolve_tenant_ids_for_mailboxes(db, inbound_to_candidates)

        # First, try mailbox-aware thread matching:
        # reply sender + mailbox they replied to must match the most recent outbound.
        # This avoids wrong matches when the same prospect email exists multiple times.
        if inbound_to_candidates:
            thread_result = await db.execute(
                select(Outreach)
                .join(OutreachEmail, OutreachEmail.outreach_id == Outreach.id)
                .where(
                    and_(
                        OutreachEmail.direction == "outbound",
                        func.lower(OutreachEmail.to_email) == from_email,
                        func.lower(OutreachEmail.from_email).in_(inbound_to_candidates),
                    )
                )
                .order_by(OutreachEmail.sent_at.desc())
                .limit(25)
            )
            thread_candidates = list(thread_result.scalars().all())
            if tenant_ids:
                thread_candidates = [
                    p for p in thread_candidates if p.tenant_id in tenant_ids
                ]
            prospect = thread_candidates[0] if thread_candidates else None

        # Fallback: match by sender email only (legacy behavior), preferring
        # recently touched prospects to keep selection deterministic.
        if not prospect:
            result = await db.execute(
                select(Outreach)
                .where(func.lower(Outreach.prospect_email) == from_email)
                .order_by(
                    Outreach.last_email_sent_at.desc().nullslast(),
                    Outreach.updated_at.desc(),
                    Outreach.created_at.desc(),
                )
                .limit(25)
            )
            fallback_candidates = list(result.scalars().all())
            if tenant_ids:
                fallback_candidates = [
                    p for p in fallback_candidates if p.tenant_id in tenant_ids
                ]
            prospect = fallback_candidates[0] if fallback_candidates else None

        if not prospect:
            logger.info(
                "Inbound email from unknown sender: %s to %s",
                from_email[:20] + "***",
                (inbound_to_email or "unknown")[:20] + "***",
            )
            return {"status": "ignored", "reason": "unknown sender"}

        # Load config for auto-reply settings
        config = (
            await get_sales_config_for_tenant(db, prospect.tenant_id)
            if prospect.tenant_id
            else None
        )

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
                        reply_mailbox=inbound_to_email,
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Inbound email processing error: %s", str(e), exc_info=True)
        # Return non-2xx so upstream providers retry transient failures.
        raise HTTPException(status_code=500, detail="Inbound webhook processing error")


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
                outreach_uuid = _safe_uuid(outreach_id)
                timestamp = _safe_event_timestamp(event.get("timestamp"))

                # Find email record
                email_record = None
                if sg_message_id:
                    result = await db.execute(
                        select(OutreachEmail).where(
                            OutreachEmail.sendgrid_message_id == sg_message_id
                        ).limit(1)
                    )
                    email_record = result.scalar_one_or_none()

                if not email_record and outreach_uuid:
                    # Fallback: find by outreach_id + step
                    step = event.get("step")
                    try:
                        step_int = int(step) if step is not None else None
                    except (TypeError, ValueError):
                        step_int = None
                    if step_int is not None:
                        result = await db.execute(
                            select(OutreachEmail).where(
                                and_(
                                    OutreachEmail.outreach_id == outreach_uuid,
                                    OutreachEmail.sequence_step == step_int,
                                )
                            ).limit(1)
                        )
                        email_record = result.scalar_one_or_none()

                if not email_record:
                    continue
                prospect_id = email_record.outreach_id or outreach_uuid

                # Get Redis for reputation tracking
                try:
                    from src.utils.dedup import get_redis
                    from src.services.deliverability import record_email_event
                    redis = await get_redis()
                except Exception as redis_err:
                    logger.debug("Redis unavailable for email reputation: %s", str(redis_err))
                    redis = None

                if redis and await _is_duplicate_email_event(redis, event):
                    logger.debug(
                        "Skipping duplicate email event: type=%s sg_message_id=%s",
                        event_type, sg_message_id,
                    )
                    continue

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
                    if prospect_id:
                        prospect = await db.get(Outreach, prospect_id)
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
                    if prospect_id:
                        prospect = await db.get(Outreach, prospect_id)
                        if prospect:
                            prospect.last_email_clicked_at = timestamp
                            await _record_email_signal(
                                "email_clicked", prospect, email_record, 1.0,
                            )
                elif event_type in ("bounce", "blocked"):
                    if email_record.bounced_at:
                        logger.debug(
                            "Skipping duplicate bounce/blocked for email %s",
                            str(email_record.id)[:8],
                        )
                        continue

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
                        if prospect_id:
                            prospect = await db.get(Outreach, prospect_id)
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
                                        from src.workers.outreach_sending import normalize_email
                                        email_addr = normalize_email(prospect.prospect_email)
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

                                            # Temporary domain cooldown after repeated recent bounces.
                                            if redis and domain not in _PROTECTED_DOMAINS:
                                                recent_bounces_result = await db.execute(
                                                    select(func.count()).select_from(OutreachEmail).where(
                                                        and_(
                                                            OutreachEmail.to_email.ilike(f"%@{domain}"),
                                                            OutreachEmail.bounced_at.isnot(None),
                                                            OutreachEmail.bounced_at >= datetime.now(timezone.utc) - timedelta(hours=24),
                                                        )
                                                    )
                                                )
                                                recent_bounces = recent_bounces_result.scalar() or 0
                                                if recent_bounces >= 2:
                                                    cooldown_key = f"leadlock:email_domain_cooldown:{domain}"
                                                    await redis.set(cooldown_key, "1", ex=86400)
                                                    logger.warning(
                                                        "Domain cooldown enabled for %s after %d bounces in 24h",
                                                        domain, recent_bounces,
                                                    )

                                            # Record per-domain bounce for 30-day risk tracking
                                            # Skip protected providers — they can't be domain-blocked
                                            if domain not in _PROTECTED_DOMAINS:
                                                try:
                                                    from src.services.deliverability import record_domain_bounce
                                                    await record_domain_bounce(domain)
                                                except Exception as db_err:
                                                    logger.debug("Domain bounce recording failed: %s", str(db_err))
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
                    if prospect_id:
                        prospect = await db.get(Outreach, prospect_id)
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
                    if prospect_id:
                        prospect = await db.get(Outreach, prospect_id)
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Email event processing error: %s", str(e))
        # Return non-2xx so upstream providers retry transient failures.
        raise HTTPException(status_code=500, detail="Email event processing error")


@router.get("/unsubscribe/{prospect_id}", response_class=HTMLResponse)
async def unsubscribe(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
):
    """CAN-SPAM one-click unsubscribe. Public endpoint."""
    try:
        pid = _safe_uuid(prospect_id)
        if not pid:
            logger.info("Unsubscribe called with invalid prospect id: %s", prospect_id[:16])
        else:
            prospect = await db.get(Outreach, pid)
            if prospect:
                prospect.email_unsubscribed = True
                prospect.unsubscribed_at = datetime.now(timezone.utc)
                prospect.updated_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info("Prospect %s unsubscribed", str(pid)[:8])
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
