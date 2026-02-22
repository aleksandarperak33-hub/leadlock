"""
Referral agent worker - sends referral request emails to active clients.
Skeleton: gated behind having active clients (runs but skips if no clients).

7-14 days post-onboarding, generates personalized referral ask.
Creates shareable referral links with tracking.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.database import async_session_factory

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 24 * 3600  # Daily
ONBOARD_DAYS_MIN = 7
ONBOARD_DAYS_MAX = 14


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:referral_agent",
            datetime.now(timezone.utc).isoformat(),
            ex=25 * 3600,
        )
    except Exception:
        pass


async def run_referral_agent():
    """Main loop - check for referral opportunities daily."""
    logger.info("Referral agent started (poll every %ds)", POLL_INTERVAL_SECONDS)

    # Wait 30 minutes on startup
    await asyncio.sleep(1800)

    while True:
        try:
            await referral_cycle()
        except Exception as e:
            logger.error("Referral agent cycle error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def referral_cycle():
    """
    Find clients eligible for referral asks.
    Gated: only runs if there are active clients.
    """
    from sqlalchemy import select, and_

    try:
        # Try to import Client model — if it doesn't exist yet, skip gracefully
        from src.models.client import Client
    except ImportError:
        logger.debug("Referral agent: Client model not available, skipping")
        return

    async with async_session_factory() as db:
        # Find clients onboarded 7-14 days ago who haven't received a referral request
        now = datetime.now(timezone.utc)
        min_date = now - timedelta(days=ONBOARD_DAYS_MAX)
        max_date = now - timedelta(days=ONBOARD_DAYS_MIN)

        result = await db.execute(
            select(Client).where(
                and_(
                    Client.is_active == True,
                    Client.created_at >= min_date,
                    Client.created_at <= max_date,
                )
            ).limit(10)
        )
        clients = result.scalars().all()

        if not clients:
            logger.debug("Referral agent: no eligible clients (0 active in window)")
            return

        # Check which clients already have referral requests
        from src.models.referral import ReferralRequest, ReferralLink
        from src.services.referral_generation import generate_referral_email, generate_referral_code

        for client in clients:
            try:
                # Check if already sent
                existing = await db.execute(
                    select(ReferralRequest).where(
                        ReferralRequest.client_id == client.id
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    continue

                # Create referral link
                code = generate_referral_code(str(client.id))
                link = ReferralLink(
                    client_id=client.id,
                    referral_code=code,
                )
                db.add(link)
                await db.flush()

                # Generate referral email
                days_onboard = (now - client.created_at).days
                from src.config import get_settings
                settings = get_settings()
                referral_url = f"{settings.app_base_url.rstrip('/')}/ref/{code}"

                email_result = await generate_referral_email(
                    client_name=client.business_name or "there",
                    trade_type=getattr(client, "trade_type", "home services"),
                    city=getattr(client, "city", ""),
                    days_since_onboard=days_onboard,
                    referral_url=referral_url,
                )

                if email_result.get("error"):
                    logger.warning("Referral email failed for client %s", str(client.id)[:8])
                    continue

                # Record request
                request = ReferralRequest(
                    client_id=client.id,
                    referral_link_id=link.id,
                    email_sent_at=now,
                    status="sent",
                )
                db.add(request)

                logger.info(
                    "Referral request sent to client %s (code=%s)",
                    str(client.id)[:8], code,
                )

            except Exception as e:
                logger.error(
                    "Referral agent failed for client %s: %s",
                    str(client.id)[:8], str(e),
                )

        await db.commit()
