"""
Channel expander worker - generates multi-channel outreach scripts daily.

For prospects who haven't replied to email after step 2, generates:
- LinkedIn connection request + DM script
- Cold call script with talk track
- Facebook group engagement post (batched by city/trade)

All scripts stored for manual use. Bridge to auto-posting when API accounts exist.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.channel_script import ChannelScript
from src.services.channel_script_generation import (
    generate_linkedin_script,
    generate_cold_call_script,
    generate_facebook_post,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 24 * 3600  # Daily
MAX_PROSPECTS_PER_DAY = 20


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:channel_expander",
            datetime.now(timezone.utc).isoformat(),
            ex=25 * 3600,
        )
    except Exception:
        pass


async def run_channel_expander():
    """Main loop - generate channel scripts daily."""
    logger.info("Channel expander started (poll every %ds)", POLL_INTERVAL_SECONDS)

    # Wait 20 minutes on startup
    await asyncio.sleep(1200)

    while True:
        try:
            await channel_expander_cycle()
        except Exception as e:
            logger.error("Channel expander cycle error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def channel_expander_cycle():
    """Find non-responding prospects and generate scripts."""
    from src.models.sales_config import SalesEngineConfig

    async with async_session_factory() as db:
        config_result = await db.execute(select(SalesEngineConfig).limit(1))
        config = config_result.scalar_one_or_none()
        if not config or not config.is_active:
            return

        # Find prospects who've been sent 2+ emails but never replied
        # and don't already have channel scripts
        eligible_query = select(Outreach).where(
            and_(
                Outreach.status.in_(["cold", "contacted"]),
                Outreach.outreach_sequence_step >= 2,
                Outreach.last_email_replied_at.is_(None),
                Outreach.email_unsubscribed == False,
                Outreach.prospect_email.isnot(None),
            )
        ).order_by(Outreach.last_email_sent_at).limit(MAX_PROSPECTS_PER_DAY * 2)

        result = await db.execute(eligible_query)
        prospects = result.scalars().all()

        if not prospects:
            logger.debug("Channel expander: no eligible prospects")
            return

        # Filter out prospects that already have scripts
        prospect_ids = [p.id for p in prospects]
        existing_result = await db.execute(
            select(ChannelScript.outreach_id).where(
                ChannelScript.outreach_id.in_(prospect_ids)
            ).distinct()
        )
        already_have_scripts = {row[0] for row in existing_result.fetchall()}

        eligible = [p for p in prospects if p.id not in already_have_scripts]
        eligible = eligible[:MAX_PROSPECTS_PER_DAY]

        if not eligible:
            logger.debug("Channel expander: all eligible prospects already have scripts")
            return

        logger.info("Channel expander: generating scripts for %d prospects", len(eligible))

        # Track unique city/trade combos for Facebook posts
        city_trade_combos = set()
        generated_count = 0

        for prospect in eligible:
            try:
                await _generate_scripts_for_prospect(db, prospect)
                generated_count += 1

                city_trade = (prospect.city or "", prospect.prospect_trade_type or "general")
                city_trade_combos.add(city_trade)
            except Exception as e:
                logger.error(
                    "Channel expander failed for %s: %s",
                    str(prospect.id)[:8], str(e),
                )

            await asyncio.sleep(3)  # Rate limit

        # Generate Facebook posts for unique city/trade combos
        for city, trade in list(city_trade_combos)[:5]:
            if not city:
                continue
            try:
                fb_result = await generate_facebook_post(trade, city)
                if fb_result.get("script_text"):
                    # Store as a general script (not tied to specific prospect)
                    # Use the first eligible prospect from that city as anchor
                    anchor = next(
                        (p for p in eligible if p.city == city),
                        eligible[0],
                    )
                    script = ChannelScript(
                        outreach_id=anchor.id,
                        channel="facebook_group",
                        script_text=fb_result["script_text"],
                        ai_cost_usd=fb_result.get("ai_cost_usd", 0.0),
                    )
                    db.add(script)
            except Exception as e:
                logger.error("Facebook post generation failed for %s/%s: %s", city, trade, str(e))

        await db.commit()
        logger.info(
            "Channel expander complete: %d prospects, %d city/trade FB posts",
            generated_count, len(city_trade_combos),
        )


async def _generate_scripts_for_prospect(db, prospect: Outreach) -> None:
    """Generate LinkedIn DM and cold call scripts for a prospect."""
    enrichment = prospect.enrichment_data or {}

    # LinkedIn DM script
    linkedin_result = await generate_linkedin_script(
        prospect_name=prospect.prospect_name,
        company_name=prospect.prospect_company or prospect.prospect_name,
        trade_type=prospect.prospect_trade_type or "general",
        city=prospect.city or "",
        state=prospect.state_code or "",
        enrichment_data=enrichment,
    )

    if linkedin_result.get("script_text"):
        db.add(ChannelScript(
            outreach_id=prospect.id,
            channel="linkedin_dm",
            script_text=linkedin_result["script_text"],
            ai_cost_usd=linkedin_result.get("ai_cost_usd", 0.0),
        ))

    # Cold call script
    call_result = await generate_cold_call_script(
        prospect_name=prospect.prospect_name,
        company_name=prospect.prospect_company or prospect.prospect_name,
        trade_type=prospect.prospect_trade_type or "general",
        city=prospect.city or "",
        state=prospect.state_code or "",
        enrichment_data=enrichment,
    )

    if call_result.get("script_text"):
        db.add(ChannelScript(
            outreach_id=prospect.id,
            channel="cold_call",
            script_text=call_result["script_text"],
            ai_cost_usd=call_result.get("ai_cost_usd", 0.0),
        ))
