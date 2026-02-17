"""
Outreach sequencer worker — sends personalized cold email sequences.
Runs every 30 minutes. Respects daily email limits, sequence delays,
and business hours gating (configurable timezone + weekdays).
Email first, SMS only after a prospect replies (TCPA compliance).
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.sales_config import SalesEngineConfig
from src.models.email_blacklist import EmailBlacklist
from src.models.campaign import Campaign
from src.models.email_template import EmailTemplate
from src.agents.sales_outreach import generate_outreach_email
from src.services.cold_email import send_cold_email
from src.utils.email_validation import validate_email
from src.config import get_settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30 * 60  # 30 minutes


def sanitize_dashes(text: str) -> str:
    """Replace em dashes, en dashes, and other unicode dashes with regular hyphens."""
    if not text:
        return text
    return (
        text
        .replace("\u2014", "-")   # em dash —
        .replace("\u2013", "-")   # en dash –
        .replace("\u2012", "-")   # figure dash ‒
        .replace("\u2015", "-")   # horizontal bar ―
        .replace("\u2010", "-")   # hyphen ‐
        .replace("\u2011", "-")   # non-breaking hyphen ‑
    )


def is_within_send_window(config: SalesEngineConfig) -> bool:
    """
    Check if the current time is within the configured send window.
    Uses config timezone for local time awareness.

    Returns:
        True if sending is allowed right now, False otherwise.
    """
    try:
        tz_name = getattr(config, "send_timezone", None) or "America/Chicago"
        tz = ZoneInfo(tz_name)
    except (KeyError, Exception):
        logger.warning("Invalid timezone '%s', falling back to America/Chicago", tz_name)
        tz = ZoneInfo("America/Chicago")

    now_local = datetime.now(tz)

    # Check weekdays only
    weekdays_only = getattr(config, "send_weekdays_only", True)
    if weekdays_only and now_local.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Parse send hours
    start_str = getattr(config, "send_hours_start", None) or "08:00"
    end_str = getattr(config, "send_hours_end", None) or "18:00"

    try:
        start_hour, start_min = map(int, start_str.split(":"))
        end_hour, end_min = map(int, end_str.split(":"))
    except (ValueError, AttributeError):
        start_hour, start_min = 8, 0
        end_hour, end_min = 18, 0

    current_minutes = now_local.hour * 60 + now_local.minute
    start_minutes = start_hour * 60 + start_min
    end_minutes = end_hour * 60 + end_min

    return start_minutes <= current_minutes < end_minutes


async def _check_smart_timing(prospect, config) -> bool:
    """
    Check if now is the optimal send time for this prospect.
    If a better time bucket exists and we have enough data, defer by creating
    a task queue entry for the optimal hour.

    Returns True if the email was deferred, False if it should be sent now.
    """
    try:
        from src.services.learning import get_best_send_time, _time_bucket

        trade = prospect.prospect_trade_type or "general"
        state = prospect.state_code or ""

        best_bucket = await get_best_send_time(trade, state)
        if not best_bucket:
            # Not enough data to make a recommendation — send now
            return False

        # Check if we're already in the best time bucket
        try:
            tz_name = getattr(config, "send_timezone", None) or "America/Chicago"
            tz = ZoneInfo(tz_name)
        except (KeyError, Exception):
            tz = ZoneInfo("America/Chicago")

        now_local = datetime.now(tz)
        current_bucket = _time_bucket(now_local.hour)

        if current_bucket == best_bucket:
            return False  # Already optimal — send now

        # Calculate delay to the start of the optimal bucket
        bucket_start_hours = {
            "early_morning": 6,
            "9am-12pm": 9,
            "12pm-3pm": 12,
            "3pm-6pm": 15,
            "evening": 18,
        }
        target_hour = bucket_start_hours.get(best_bucket, 9)

        # If target is later today, delay until then
        # If target is earlier today, delay until tomorrow at that time
        target_time = now_local.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if target_time <= now_local:
            target_time = target_time + timedelta(days=1)

        delay_seconds = int((target_time - now_local).total_seconds())

        # Don't defer for more than 24 hours
        if delay_seconds > 86400:
            return False

        # Create delayed task
        from src.services.task_dispatch import enqueue_task

        await enqueue_task(
            task_type="send_sequence_email",
            payload={
                "outreach_id": str(prospect.id),
            },
            priority=5,
            delay_seconds=delay_seconds,
        )

        logger.info(
            "Smart timing: deferred prospect %s from %s to %s (delay=%ds)",
            str(prospect.id)[:8], current_bucket, best_bucket, delay_seconds,
        )
        return True

    except Exception as e:
        logger.debug("Smart timing check failed (sending now): %s", str(e))
        return False


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set("leadlock:worker_health:outreach_sequencer", datetime.utcnow().isoformat(), ex=3600)
    except Exception:
        pass


async def run_outreach_sequencer():
    """Main loop — process outreach sequences every 30 minutes."""
    logger.info("Outreach sequencer started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        try:
            # Check if sequencer is paused
            async with async_session_factory() as db:
                result = await db.execute(select(SalesEngineConfig).limit(1))
                config = result.scalar_one_or_none()
                if config and hasattr(config, "sequencer_paused") and config.sequencer_paused:
                    logger.debug("Outreach sequencer is paused, skipping cycle")
                else:
                    await sequence_cycle()
        except Exception as e:
            logger.error("Outreach sequencer error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def sequence_cycle():
    """
    Execute one full outreach sequence cycle. Respects business hours gating.
    Two-pass: (1) active campaigns first, (2) unbound prospects with global config.
    """
    async with async_session_factory() as db:
        # Load config
        result = await db.execute(select(SalesEngineConfig).limit(1))
        config = result.scalar_one_or_none()

        if not config or not config.is_active:
            return

        # Business hours gating — only send during configured window
        if not is_within_send_window(config):
            logger.info("Outside send window, deferring outreach to next cycle")
            return

        if not config.from_email or not config.company_address:
            logger.warning("Sales engine email sender not configured")
            return

        settings = get_settings()
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # === PASS 1: Active campaigns ===
        campaigns_result = await db.execute(
            select(Campaign).where(Campaign.status == "active")
        )
        active_campaigns = campaigns_result.scalars().all()

        for campaign in active_campaigns:
            try:
                await _process_campaign_prospects(
                    db, config, settings, campaign, today_start
                )
            except Exception as e:
                logger.error(
                    "Campaign %s processing error: %s",
                    str(campaign.id)[:8], str(e),
                )

        # === PASS 2: Unbound prospects (campaign_id IS NULL) ===

        # Count today's sent emails (global)
        sent_today_result = await db.execute(
            select(func.count()).select_from(OutreachEmail).where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sent_at >= today_start,
                )
            )
        )
        sent_today = sent_today_result.scalar() or 0

        remaining = config.daily_email_limit - sent_today
        if remaining <= 0:
            logger.info("Daily email limit reached (%d sent)", sent_today)
            await db.commit()
            return

        # Find prospects ready for next step
        delay_cutoff = datetime.utcnow() - timedelta(hours=config.sequence_delay_hours)

        # Step 0: never contacted, has email, not unsubscribed, NOT campaign-bound
        step_0_query = select(Outreach).where(
            and_(
                Outreach.campaign_id.is_(None),
                Outreach.outreach_sequence_step == 0,
                Outreach.prospect_email.isnot(None),
                Outreach.prospect_email != "",
                Outreach.email_unsubscribed == False,
                Outreach.status.in_(["cold"]),
                Outreach.last_email_replied_at.is_(None),
            )
        ).order_by(Outreach.created_at).limit(remaining)

        # Steps 1-2: contacted but no reply, delay elapsed, NOT campaign-bound
        followup_query = select(Outreach).where(
            and_(
                Outreach.campaign_id.is_(None),
                Outreach.outreach_sequence_step >= 1,
                Outreach.outreach_sequence_step < config.max_sequence_steps,
                Outreach.prospect_email.isnot(None),
                Outreach.prospect_email != "",
                Outreach.email_unsubscribed == False,
                Outreach.status.in_(["cold", "contacted"]),
                Outreach.last_email_replied_at.is_(None),
                Outreach.last_email_sent_at <= delay_cutoff,
            )
        ).order_by(Outreach.last_email_sent_at).limit(remaining)

        # Execute both queries
        step_0_result = await db.execute(step_0_query)
        step_0_prospects = step_0_result.scalars().all()

        followup_result = await db.execute(followup_query)
        followup_prospects = followup_result.scalars().all()

        # Combine and limit
        all_prospects = step_0_prospects + followup_prospects
        all_prospects = all_prospects[:remaining]

        if all_prospects:
            logger.info("Processing %d unbound prospects for outreach", len(all_prospects))

        for i, prospect in enumerate(all_prospects):
            try:
                # Smart send timing: check if now is the optimal time bucket
                deferred = await _check_smart_timing(prospect, config)
                if deferred:
                    logger.debug(
                        "Prospect %s deferred to optimal send time",
                        str(prospect.id)[:8],
                    )
                    continue

                await send_sequence_email(db, config, settings, prospect)
            except Exception as e:
                logger.error(
                    "Failed to send outreach to %s: %s",
                    str(prospect.id)[:8], str(e),
                )

            # Rate limit: ~2 emails/min to avoid SendGrid burst limits
            if i < len(all_prospects) - 1:
                await asyncio.sleep(30)

        await db.commit()


async def _process_campaign_prospects(
    db: AsyncSession,
    config: SalesEngineConfig,
    settings,
    campaign: Campaign,
    today_start: datetime,
) -> None:
    """
    Process prospects bound to a specific campaign.
    Uses campaign's daily_limit and sequence_steps for timing/templates.
    """
    steps = campaign.sequence_steps or []
    if not steps:
        return

    # Count today's sends for THIS campaign
    sent_today_result = await db.execute(
        select(func.count())
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.campaign_id == campaign.id,
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= today_start,
            )
        )
    )
    sent_today = sent_today_result.scalar() or 0
    remaining = campaign.daily_limit - sent_today

    if remaining <= 0:
        logger.debug(
            "Campaign %s daily limit reached (%d sent)",
            str(campaign.id)[:8], sent_today,
        )
        return

    all_prospects = []

    # For each step, find eligible prospects
    for step_def in steps:
        step_num = step_def.get("step", 1)
        delay_hours = step_def.get("delay_hours", 0)
        template_id = step_def.get("template_id")

        if step_num == 1:
            # Step 1: cold prospects in this campaign, never contacted
            query = select(Outreach).where(
                and_(
                    Outreach.campaign_id == campaign.id,
                    Outreach.outreach_sequence_step == 0,
                    Outreach.prospect_email.isnot(None),
                    Outreach.prospect_email != "",
                    Outreach.email_unsubscribed == False,
                    Outreach.status.in_(["cold"]),
                    Outreach.last_email_replied_at.is_(None),
                )
            ).order_by(Outreach.created_at).limit(remaining)
        else:
            # Follow-up steps: at previous step, delay elapsed
            delay_cutoff = datetime.utcnow() - timedelta(hours=delay_hours)
            query = select(Outreach).where(
                and_(
                    Outreach.campaign_id == campaign.id,
                    Outreach.outreach_sequence_step == step_num - 1,
                    Outreach.prospect_email.isnot(None),
                    Outreach.prospect_email != "",
                    Outreach.email_unsubscribed == False,
                    Outreach.status.in_(["cold", "contacted"]),
                    Outreach.last_email_replied_at.is_(None),
                    Outreach.last_email_sent_at <= delay_cutoff,
                )
            ).order_by(Outreach.last_email_sent_at).limit(remaining)

        result = await db.execute(query)
        prospects = result.scalars().all()
        for p in prospects:
            all_prospects.append((p, template_id))

    # Limit to daily cap
    all_prospects = all_prospects[:remaining]

    if not all_prospects:
        return

    logger.info(
        "Campaign %s: processing %d prospects",
        str(campaign.id)[:8], len(all_prospects),
    )

    for i, (prospect, template_id) in enumerate(all_prospects):
        try:
            deferred = await _check_smart_timing(prospect, config)
            if deferred:
                continue

            await send_sequence_email(
                db, config, settings, prospect,
                template_id=template_id, campaign=campaign,
            )
        except Exception as e:
            logger.error(
                "Campaign %s: failed to send to %s: %s",
                str(campaign.id)[:8], str(prospect.id)[:8], str(e),
            )

        if i < len(all_prospects) - 1:
            await asyncio.sleep(30)


async def _generate_email_with_template(
    prospect: Outreach,
    next_step: int,
    template: Optional[EmailTemplate] = None,
) -> dict:
    """
    Generate an outreach email, optionally using a template.
    - No template or is_ai_generated=True with ai_instructions: use AI with instructions
    - is_ai_generated=False with body_template: render static template with substitutions
    - Fallback: standard AI generation
    """
    if template and not template.is_ai_generated and template.body_template:
        # Static template with variable substitution
        substitutions = {
            "{prospect_name}": prospect.prospect_name or "",
            "{company}": prospect.prospect_company or prospect.prospect_name or "",
            "{city}": prospect.city or "",
            "{trade}": prospect.prospect_trade_type or "home services",
        }

        body_text = template.body_template
        subject = template.subject_template or f"Quick question for {prospect.prospect_company or prospect.prospect_name}"

        for key, value in substitutions.items():
            body_text = body_text.replace(key, value)
            subject = subject.replace(key, value)

        # Simple text-to-html conversion
        body_html = body_text.replace("\n", "<br>")

        return {
            "subject": sanitize_dashes(subject),
            "body_html": sanitize_dashes(body_html),
            "body_text": sanitize_dashes(body_text),
            "ai_cost_usd": 0.0,
        }

    # AI-generated email (with optional extra instructions from template)
    extra_instructions = None
    if template and template.is_ai_generated and template.ai_instructions:
        extra_instructions = template.ai_instructions

    return await generate_outreach_email(
        prospect_name=prospect.prospect_name,
        company_name=prospect.prospect_company or prospect.prospect_name,
        trade_type=prospect.prospect_trade_type or "general",
        city=prospect.city or "",
        state=prospect.state_code or "",
        rating=prospect.google_rating,
        review_count=prospect.review_count,
        website=prospect.website,
        sequence_step=next_step,
        extra_instructions=extra_instructions,
    )


async def send_sequence_email(
    db: AsyncSession,
    config: SalesEngineConfig,
    settings,
    prospect: Outreach,
    template_id: Optional[str] = None,
    campaign: Optional[Campaign] = None,
):
    """Generate and send a single outreach email for a prospect."""
    # Validate email before sending
    email_check = await validate_email(prospect.prospect_email)
    if not email_check["valid"]:
        logger.info(
            "Skipping prospect %s — invalid email (%s)",
            str(prospect.id)[:8], email_check["reason"],
        )
        return

    # Check blacklist (email and domain)
    email_lower = prospect.prospect_email.lower().strip()
    domain = email_lower.split("@")[1] if "@" in email_lower else ""
    blacklist_check = await db.execute(
        select(EmailBlacklist).where(
            EmailBlacklist.value.in_([email_lower, domain])
        ).limit(1)
    )
    if blacklist_check.scalar_one_or_none():
        logger.info("Skipping blacklisted prospect %s", str(prospect.id)[:8])
        return

    next_step = prospect.outreach_sequence_step + 1

    # Load template if specified
    template = None
    if template_id:
        try:
            template = await db.get(EmailTemplate, uuid.UUID(template_id))
        except Exception:
            pass

    # Generate personalized email — template-aware
    email_result = await _generate_email_with_template(
        prospect=prospect,
        next_step=next_step,
        template=template,
    )

    if email_result.get("error"):
        logger.warning(
            "Email generation failed for prospect %s: %s",
            str(prospect.id)[:8], email_result["error"],
        )
        return

    # Sanitize dashes from AI-generated content
    email_result = {
        **email_result,
        "subject": sanitize_dashes(email_result.get("subject", "")),
        "body_html": sanitize_dashes(email_result.get("body_html", "")),
        "body_text": sanitize_dashes(email_result.get("body_text", "")),
    }

    # Build unsubscribe URL
    base_url = settings.app_base_url.rstrip("/")
    unsubscribe_url = f"{base_url}/api/v1/sales/unsubscribe/{prospect.id}"

    # Look up previous email for threading headers
    in_reply_to = None
    references = None
    if next_step > 1:
        prev_email_result = await db.execute(
            select(OutreachEmail).where(
                and_(
                    OutreachEmail.outreach_id == prospect.id,
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sendgrid_message_id.isnot(None),
                )
            ).order_by(OutreachEmail.sequence_step.desc()).limit(1)
        )
        prev_email = prev_email_result.scalar_one_or_none()
        if prev_email and prev_email.sendgrid_message_id:
            in_reply_to = prev_email.sendgrid_message_id
            references = f"<{prev_email.sendgrid_message_id}>"

    # Send email
    send_result = await send_cold_email(
        to_email=prospect.prospect_email,
        to_name=prospect.prospect_name,
        subject=email_result["subject"],
        body_html=email_result["body_html"],
        from_email=config.from_email,
        from_name=config.from_name or "LeadLock",
        reply_to=config.reply_to_email or config.from_email,
        unsubscribe_url=unsubscribe_url,
        company_address=config.company_address or "",
        custom_args={
            "outreach_id": str(prospect.id),
            "step": str(next_step),
        },
        in_reply_to=in_reply_to,
        references=references,
    )

    if send_result.get("error"):
        logger.warning(
            "Email send failed for prospect %s: %s",
            str(prospect.id)[:8], send_result["error"],
        )
        return

    now = datetime.utcnow()

    # Record email
    email_record = OutreachEmail(
        outreach_id=prospect.id,
        direction="outbound",
        subject=email_result["subject"],
        body_html=email_result["body_html"],
        body_text=email_result["body_text"],
        from_email=config.from_email,
        to_email=prospect.prospect_email,
        sendgrid_message_id=send_result.get("message_id"),
        sequence_step=next_step,
        sent_at=now,
        ai_cost_usd=email_result.get("ai_cost_usd", 0.0),
    )
    db.add(email_record)

    # Update prospect
    total_email_cost = email_result.get("ai_cost_usd", 0.0) + send_result.get("cost_usd", 0.0)
    prospect.outreach_sequence_step = next_step
    prospect.last_email_sent_at = now
    prospect.total_emails_sent = (prospect.total_emails_sent or 0) + 1
    prospect.total_cost_usd = (prospect.total_cost_usd or 0.0) + total_email_cost
    prospect.updated_at = now

    if prospect.status == "cold":
        prospect.status = "contacted"

    # Increment campaign counters
    if campaign:
        campaign.total_sent = (campaign.total_sent or 0) + 1

    logger.info(
        "Outreach email sent: prospect=%s step=%d to=%s campaign=%s",
        str(prospect.id)[:8], next_step, prospect.prospect_email[:20] + "***",
        str(campaign.id)[:8] if campaign else "none",
    )
