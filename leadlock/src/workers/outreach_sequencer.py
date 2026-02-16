"""
Outreach sequencer worker — sends personalized cold email sequences.
Runs every 30 minutes. Respects daily email limits and sequence delays.
Email first, SMS only after a prospect replies (TCPA compliance).
"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.sales_config import SalesEngineConfig
from src.models.email_blacklist import EmailBlacklist
from src.agents.sales_outreach import generate_outreach_email
from src.services.cold_email import send_cold_email
from src.utils.email_validation import validate_email
from src.config import get_settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30 * 60  # 30 minutes


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
            await sequence_cycle()
        except Exception as e:
            logger.error("Outreach sequencer error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def sequence_cycle():
    """Execute one full outreach sequence cycle."""
    async with async_session_factory() as db:
        # Load config
        result = await db.execute(select(SalesEngineConfig).limit(1))
        config = result.scalar_one_or_none()

        if not config or not config.is_active:
            return

        if not config.from_email or not config.company_address:
            logger.warning("Sales engine email sender not configured")
            return

        settings = get_settings()

        # Count today's sent emails
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
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
            return

        # Find prospects ready for next step
        delay_cutoff = datetime.utcnow() - timedelta(hours=config.sequence_delay_hours)

        # Step 0: never contacted, has email, not unsubscribed
        step_0_query = select(Outreach).where(
            and_(
                Outreach.outreach_sequence_step == 0,
                Outreach.prospect_email.isnot(None),
                Outreach.prospect_email != "",
                Outreach.email_unsubscribed == False,
                Outreach.status.in_(["cold"]),
                Outreach.last_email_replied_at.is_(None),
            )
        ).order_by(Outreach.created_at).limit(remaining)

        # Steps 1-2: contacted but no reply, delay elapsed
        followup_query = select(Outreach).where(
            and_(
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

        if not all_prospects:
            return

        logger.info("Processing %d prospects for outreach", len(all_prospects))

        for i, prospect in enumerate(all_prospects):
            try:
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


async def send_sequence_email(
    db: AsyncSession,
    config: SalesEngineConfig,
    settings,
    prospect: Outreach,
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

    # Generate personalized email
    email_result = await generate_outreach_email(
        prospect_name=prospect.prospect_name,
        company_name=prospect.prospect_company or prospect.prospect_name,
        trade_type=prospect.prospect_trade_type or "general",
        city=prospect.city or "",
        state=prospect.state_code or "",
        rating=prospect.google_rating,
        review_count=prospect.review_count,
        website=prospect.website,
        sequence_step=next_step,
    )

    if email_result.get("error"):
        logger.warning(
            "Email generation failed for prospect %s: %s",
            str(prospect.id)[:8], email_result["error"],
        )
        return

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

    logger.info(
        "Outreach email sent: prospect=%s step=%d to=%s",
        str(prospect.id)[:8], next_step, prospect.prospect_email[:20] + "***",
    )
