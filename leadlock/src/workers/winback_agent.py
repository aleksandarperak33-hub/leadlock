"""
Win-back agent worker - re-engages cold prospects with alternative angles.

Runs daily. Identifies prospects who were contacted 30+ days ago, never replied,
and sends ONE win-back email with a completely different value prop.

Hard limits:
- 1 win-back per prospect ever
- Max 10 win-backs per day
- Only prospects with status='contacted' and no reply
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_, func

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.sales_config import SalesEngineConfig
from src.services.winback_generation import (
    generate_winback_email,
    select_winback_angle,
)
from src.services.cold_email import send_cold_email
from src.workers.outreach_sequencer import sanitize_dashes

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 24 * 3600  # Daily
MAX_WINBACKS_PER_DAY = 10
COLD_DAYS_THRESHOLD = 30  # Must be at least 30 days since last email


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:winback_agent",
            datetime.now(timezone.utc).isoformat(),
            ex=25 * 3600,
        )
    except Exception:
        pass


async def run_winback_agent():
    """Main loop - process win-backs daily."""
    logger.info("Win-back agent started (poll every %ds)", POLL_INTERVAL_SECONDS)

    # Wait 10 minutes on startup
    await asyncio.sleep(600)

    while True:
        try:
            await winback_cycle()
        except Exception as e:
            logger.error("Win-back agent cycle error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def winback_cycle():
    """
    Identify eligible prospects and send win-back emails.
    Eligibility: contacted, last email 30+ days ago, never replied, not unsubscribed,
    no previous win-back sent.
    """
    async with async_session_factory() as db:
        # Check if sales engine is active
        config_result = await db.execute(select(SalesEngineConfig).limit(1))
        config = config_result.scalar_one_or_none()
        if not config or not config.is_active:
            return

        if not config.from_email:
            logger.warning("Win-back: no from_email configured")
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=COLD_DAYS_THRESHOLD)

        # Find eligible prospects
        eligible_query = select(Outreach).where(
            and_(
                Outreach.status == "contacted",
                Outreach.last_email_sent_at <= cutoff,
                Outreach.last_email_replied_at.is_(None),
                Outreach.email_unsubscribed == False,
                Outreach.prospect_email.isnot(None),
                Outreach.prospect_email != "",
                Outreach.winback_sent_at.is_(None),
                Outreach.winback_eligible == True,
            )
        ).order_by(Outreach.last_email_sent_at).limit(MAX_WINBACKS_PER_DAY)

        result = await db.execute(eligible_query)
        prospects = result.scalars().all()

        if not prospects:
            logger.debug("Win-back: no eligible prospects found")
            return

        logger.info("Win-back: found %d eligible prospects", len(prospects))
        from src.config import get_settings
        settings = get_settings()

        sent_count = 0
        for i, prospect in enumerate(prospects):
            try:
                success = await _send_winback(db, config, settings, prospect, i)
                if success:
                    sent_count += 1
                await db.flush()
            except Exception as e:
                logger.error(
                    "Win-back failed for prospect %s: %s",
                    str(prospect.id)[:8], str(e),
                )

            # Rate limit with jitter
            if i < len(prospects) - 1:
                jitter = random.uniform(120, 300)
                await asyncio.sleep(jitter)

        await db.commit()
        logger.info("Win-back cycle complete: %d/%d sent", sent_count, len(prospects))


async def _send_winback(
    db,
    config: SalesEngineConfig,
    settings,
    prospect: Outreach,
    batch_index: int,
) -> bool:
    """Generate and send a single win-back email. Returns True on success."""
    angle = select_winback_angle(
        prospect.prospect_trade_type or "general",
        batch_index,
    )

    email_result = await generate_winback_email(
        prospect_name=prospect.prospect_name,
        company_name=prospect.prospect_company or prospect.prospect_name,
        trade_type=prospect.prospect_trade_type or "general",
        city=prospect.city or "",
        state=prospect.state_code or "",
        angle=angle,
        sender_name=config.sender_name or "Alek",
        enrichment_data=prospect.enrichment_data,
    )

    if email_result.get("error") or not email_result.get("subject"):
        logger.warning(
            "Win-back generation failed for %s: %s",
            str(prospect.id)[:8], email_result.get("error", "empty subject"),
        )
        return False

    # Sanitize dashes
    email_result = {
        **email_result,
        "subject": sanitize_dashes(email_result.get("subject", "")),
        "body_html": sanitize_dashes(email_result.get("body_html", "")),
        "body_text": sanitize_dashes(email_result.get("body_text", "")),
    }

    # Build unsubscribe URL
    base_url = settings.app_base_url.rstrip("/")
    unsubscribe_url = f"{base_url}/api/v1/sales/unsubscribe/{prospect.id}"

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
            "step": "winback",
        },
        body_text=email_result.get("body_text", ""),
        company_name="LeadLock",
    )

    if send_result.get("error"):
        logger.warning(
            "Win-back send failed for %s: %s",
            str(prospect.id)[:8], send_result["error"],
        )
        return False

    now = datetime.now(timezone.utc)

    # Record the email
    email_record = OutreachEmail(
        outreach_id=prospect.id,
        direction="outbound",
        subject=email_result["subject"],
        body_html=email_result["body_html"],
        body_text=email_result["body_text"],
        from_email=config.from_email,
        to_email=prospect.prospect_email,
        sendgrid_message_id=send_result.get("message_id"),
        sequence_step=99,  # Special step number for win-back
        sent_at=now,
        ai_cost_usd=email_result.get("ai_cost_usd", 0.0),
    )
    db.add(email_record)

    # Mark prospect as win-back sent
    prospect.winback_sent_at = now
    prospect.total_emails_sent = (prospect.total_emails_sent or 0) + 1
    prospect.total_cost_usd = (prospect.total_cost_usd or 0.0) + email_result.get("ai_cost_usd", 0.0)
    prospect.updated_at = now

    logger.info(
        "Win-back sent: prospect=%s angle=%s to=%s",
        str(prospect.id)[:8], angle["name"], prospect.prospect_email[:20] + "***",
    )
    return True
