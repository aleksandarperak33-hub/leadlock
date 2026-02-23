"""
Outreach sequencer worker - sends personalized cold email sequences.
Runs every 30 minutes. Respects daily email limits, sequence delays,
and business hours gating (configurable timezone + weekdays).
Email first, SMS only after a prospect replies (TCPA compliance).
"""
import asyncio
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_, or_, not_, func
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

# Email warmup schedule - ramps daily send volume over 21 days.
# Aggressive but safe: domain already has SPF/DKIM/DMARC and send history.
# Format: (day_range_start, day_range_end, max_daily_emails)
# day_range_end of None means "and beyond"; max_daily of None means "use configured limit"
EMAIL_WARMUP_SCHEDULE = [
    (0, 3, 10),       # Days 0-3: 10 emails/day (conservative start)
    (4, 7, 20),       # Days 4-7: 20 emails/day
    (8, 14, 40),      # Week 2: 40 emails/day
    (15, 21, 75),     # Week 3: 75 emails/day
    (22, 28, 120),    # Week 4: 120 emails/day
    (29, None, None), # After 4 weeks: use configured limit
]


def sanitize_dashes(text: str) -> str:
    """Replace em dashes, en dashes, and other unicode dashes with regular hyphens."""
    if not text:
        return text
    return (
        text
        .replace("\u2014", "-")   # em dash -
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
            # Not enough data to make a recommendation - send now
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
            return False  # Already optimal - send now

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
        await redis.set("leadlock:worker_health:outreach_sequencer", datetime.now(timezone.utc).isoformat(), ex=2700)
    except Exception as e:
        logger.debug("Heartbeat write failed: %s", str(e))


async def _get_warmup_limit(configured_limit: int, from_email: str = "") -> int:
    """
    Calculate the effective daily email limit based on domain warmup schedule.

    Uses Redis to cache the warmup start date, but falls back to the DB
    (first outbound email sent_at) if the Redis key is missing. This prevents
    warmup resets when containers restart and Redis data is lost.

    Args:
        configured_limit: The user-configured daily email limit.
        from_email: The sender email address used to key warmup by domain.

    Returns:
        The minimum of the warmup limit and configured limit.
    """
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        domain = from_email.split("@")[1].lower() if "@" in from_email else "default"
        warmup_key = f"leadlock:email_warmup:{domain}"
        started_at_raw = await redis.get(warmup_key)

        if started_at_raw is None:
            # Redis key missing — recover from DB to avoid resetting warmup
            started_at = await _recover_warmup_start_from_db()
            if started_at is not None:
                await redis.set(warmup_key, started_at.isoformat())
                logger.info("Recovered warmup start from DB: %s", started_at.isoformat())
            else:
                # Truly first email ever — start warmup now
                started_at = datetime.now(timezone.utc)
                await redis.set(warmup_key, started_at.isoformat())
                logger.info("Email warmup started - day 0, limit=5")
        else:
            started_at_str = started_at_raw.decode() if isinstance(started_at_raw, bytes) else str(started_at_raw)
            started_at = datetime.fromisoformat(started_at_str)

        days_since_start = (datetime.now(timezone.utc) - started_at).days

        for day_start, day_end, max_daily in EMAIL_WARMUP_SCHEDULE:
            if day_end is None:
                return configured_limit
            if day_start <= days_since_start <= day_end:
                warmup_limit = max_daily if max_daily is not None else configured_limit
                logger.info("Warmup day %d: limit=%d (configured=%d)", days_since_start, warmup_limit, configured_limit)
                return min(warmup_limit, configured_limit)

        return configured_limit

    except Exception as e:
        logger.warning("Warmup limit check failed: %s - using configured limit", str(e))
        return configured_limit


async def _recover_warmup_start_from_db() -> Optional[datetime]:
    """
    Recover the warmup start date from the earliest outbound email in the DB.
    This prevents warmup resets when Redis data is lost on container restarts.
    """
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(func.min(OutreachEmail.sent_at)).where(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sent_at.isnot(None),
                )
            )
            earliest = result.scalar()
            return earliest
    except Exception as e:
        logger.warning("Failed to recover warmup start from DB: %s", str(e))
        return None


async def _check_email_health() -> tuple[bool, str]:
    """
    Check email reputation before sending. Returns (allowed, throttle_level).

    If reputation is critical, returns (False, "paused") to halt sending.
    Otherwise returns (True, throttle_level) where throttle_level is
    one of "normal", "reduced", or "critical".
    """
    try:
        from src.utils.dedup import get_redis
        from src.services.deliverability import get_email_reputation

        redis = await get_redis()
        reputation = await get_email_reputation(redis)

        if reputation["throttle"] == "paused":
            logger.warning(
                "EMAIL SENDING PAUSED - reputation score %.1f (critical). "
                "Bounce rate: %.2f%%, Complaint rate: %.4f%%",
                reputation["score"],
                reputation["metrics"].get("bounce_rate", 0) * 100,
                reputation["metrics"].get("complaint_rate", 0) * 100,
            )
            return False, "paused"

        if reputation["throttle"] == "critical":
            logger.warning(
                "Email reputation POOR (%.1f) - sending at 25%% capacity",
                reputation["score"],
            )
        elif reputation["throttle"] == "reduced":
            logger.warning(
                "Email reputation WARNING (%.1f) - sending at 50%% capacity",
                reputation["score"],
            )

        return True, reputation["throttle"]

    except Exception as e:
        logger.warning("Email health check failed: %s - continuing with caution", str(e))
        return True, "reduced"  # Redis outage: apply 50% throttle as conservative fallback


def _calculate_cycle_cap(
    daily_limit: int,
    sent_today: int,
    config: SalesEngineConfig,
) -> int:
    """
    Calculate max emails to send in this 30-min cycle for distributed sending.
    Spreads remaining daily quota across remaining send-window cycles to avoid
    blasting all emails in a single burst.

    Returns:
        Max number of emails to send this cycle (minimum 1 if any remain).
    """
    remaining = max(0, daily_limit - sent_today)
    if remaining == 0:
        return 0

    # Estimate remaining cycles in the send window
    try:
        tz_name = getattr(config, "send_timezone", None) or "America/Chicago"
        tz = ZoneInfo(tz_name)
    except (KeyError, Exception):
        tz = ZoneInfo("America/Chicago")

    now_local = datetime.now(tz)
    end_str = getattr(config, "send_hours_end", None) or "18:00"
    try:
        end_hour, end_min = map(int, end_str.split(":"))
    except (ValueError, AttributeError):
        end_hour, end_min = 18, 0

    end_minutes = end_hour * 60 + end_min
    current_minutes = now_local.hour * 60 + now_local.minute
    remaining_minutes = max(0, end_minutes - current_minutes)
    remaining_cycles = max(1, remaining_minutes // 30)

    # Distribute remaining sends across remaining cycles
    return max(1, remaining // remaining_cycles)


_CIRCUIT_BREAKER_KEY = "leadlock:circuit:ai_generation"
_CIRCUIT_BREAKER_TTL = 7200  # 2 hours


async def _is_ai_circuit_open() -> bool:
    """Check if the AI generation circuit breaker is open (tripped)."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        return await redis.exists(_CIRCUIT_BREAKER_KEY) > 0
    except Exception as e:
        return False


async def _trip_ai_circuit_breaker() -> None:
    """Open the circuit breaker — skip AI generation for 2 hours."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(_CIRCUIT_BREAKER_KEY, "1", ex=_CIRCUIT_BREAKER_TTL)
        logger.warning(
            "AI circuit breaker TRIPPED — skipping outreach for %d minutes. "
            "Top up API credits to resume.",
            _CIRCUIT_BREAKER_TTL // 60,
        )
    except Exception as e:
        logger.debug("Circuit breaker write failed: %s", str(e))


async def run_outreach_sequencer():
    """Main loop - process outreach sequences every 30 minutes."""
    logger.info("Outreach sequencer started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        await _heartbeat()
        try:
            # Persistent circuit breaker — skip cycle if AI provider is down
            if await _is_ai_circuit_open():
                logger.info("AI circuit breaker is open — skipping outreach cycle")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

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

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _recover_generation_failed() -> int:
    """
    Reset prospects stuck in 'generation_failed' back to 'cold' so they
    can be retried now that the AI circuit breaker has cleared.
    Returns count of recovered prospects.
    """
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Outreach).where(Outreach.status == "generation_failed")
            )
            prospects = list(result.scalars().all())
            if not prospects:
                return 0
            for p in prospects:
                p.status = "cold"
                p.generation_failures = 0
            await db.commit()
            logger.info("Recovered %d generation_failed prospects back to cold", len(prospects))
            return len(prospects)
    except Exception as e:
        logger.debug("Recovery check failed: %s", str(e))
        return 0


async def sequence_cycle():
    """
    Execute one full outreach sequence cycle. Respects business hours gating.
    Two-pass: (1) active campaigns first, (2) unbound prospects with global config.
    """
    # Recover prospects damaged by previous AI outage
    await _recover_generation_failed()

    async with async_session_factory() as db:
        # Load config
        result = await db.execute(select(SalesEngineConfig).limit(1))
        config = result.scalar_one_or_none()

        if not config or not config.is_active:
            return

        # Business hours gating - only send during configured window
        if not is_within_send_window(config):
            logger.info("Outside send window, deferring outreach to next cycle")
            return

        if not config.from_email or not config.company_address:
            logger.warning("Sales engine email sender not configured")
            return

        # Email reputation circuit breaker - pause if reputation is critical
        email_healthy, throttle_level = await _check_email_health()
        if not email_healthy:
            logger.warning("Email sending paused due to poor reputation - skipping cycle")
            return

        settings = get_settings()
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

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

        # Apply warmup limit - dynamic pacing via warmup optimizer
        warmup_limit = await _get_warmup_limit(config.daily_email_limit, config.from_email or "")

        # Apply smart warmup optimizer on top of standard limit
        try:
            from src.services.warmup_optimizer import get_optimized_warmup_limit
            from src.utils.dedup import get_redis as _get_redis_for_warmup
            _redis = await _get_redis_for_warmup()
            domain = (config.from_email or "").split("@")[1].lower() if "@" in (config.from_email or "") else "default"
            _warmup_key = f"leadlock:email_warmup:{domain}"
            _started_raw = await _redis.get(_warmup_key)
            if _started_raw:
                _started_str = _started_raw.decode() if isinstance(_started_raw, bytes) else str(_started_raw)
                _started = datetime.fromisoformat(_started_str)
                _days = (datetime.now(timezone.utc) - _started).days
                warmup_limit = await get_optimized_warmup_limit(warmup_limit, _days)
        except Exception as opt_err:
            logger.debug("Warmup optimizer unavailable: %s", str(opt_err))

        # Apply reputation throttle factor
        from src.services.deliverability import EMAIL_THROTTLE_FACTORS
        throttle_factor = EMAIL_THROTTLE_FACTORS.get(throttle_level, 1.0)
        effective_limit = max(1, int(warmup_limit * throttle_factor))

        remaining = effective_limit - sent_today
        if remaining <= 0:
            logger.info(
                "Daily email limit reached (%d sent, effective_limit=%d, warmup=%d, throttle=%s)",
                sent_today, effective_limit, warmup_limit, throttle_level,
            )
            await db.commit()
            return

        # Calculate per-cycle cap for distributed sending
        cycle_cap = _calculate_cycle_cap(
            effective_limit, sent_today, config,
        )
        remaining = min(remaining, cycle_cap)

        logger.info(
            "Unbound prospects: sent_today=%d effective_limit=%d (warmup=%d throttle=%s) cycle_cap=%d",
            sent_today, effective_limit, warmup_limit, throttle_level, cycle_cap,
        )

        # Find prospects ready for next step
        delay_cutoff = datetime.now(timezone.utc) - timedelta(hours=config.sequence_delay_hours)

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
                # Skip unverified pattern guesses — wait for email_finder
                not_(and_(
                    Outreach.email_source == "pattern_guess",
                    Outreach.email_verified == False,  # noqa: E712
                )),
            )
        ).order_by(Outreach.created_at).limit(remaining).with_for_update(skip_locked=True)

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
                # Skip unverified pattern guesses — wait for email_finder
                not_(and_(
                    Outreach.email_source == "pattern_guess",
                    Outreach.email_verified == False,  # noqa: E712
                )),
            )
        ).order_by(Outreach.last_email_sent_at).limit(remaining).with_for_update(skip_locked=True)

        # Execute both queries
        step_0_result = await db.execute(step_0_query)
        step_0_prospects = step_0_result.scalars().all()

        followup_result = await db.execute(followup_query)
        followup_prospects = followup_result.scalars().all()

        # Combine: follow-ups FIRST (they've already been waiting 48h+),
        # then new contacts fill remaining slots
        all_prospects = followup_prospects + step_0_prospects
        all_prospects = all_prospects[:remaining]

        if all_prospects:
            logger.info("Processing %d unbound prospects for outreach", len(all_prospects))

        consecutive_failures = 0
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

                prev_failures = prospect.generation_failures or 0
                await send_sequence_email(db, config, settings, prospect)
                await db.flush()

                # Circuit breaker: if generation failed, track consecutive failures
                new_failures = prospect.generation_failures or 0
                if new_failures > prev_failures:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

                if consecutive_failures >= 3:
                    await _trip_ai_circuit_breaker()
                    break
            except Exception as e:
                logger.error(
                    "Failed to send outreach to %s: %s",
                    str(prospect.id)[:8], str(e),
                )
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    logger.warning(
                        "Circuit breaker: %d consecutive exceptions. "
                        "Stopping batch.",
                        consecutive_failures,
                    )
                    break

            # Rate limit with jitter: spread sends across the cycle window
            if i < len(all_prospects) - 1:
                jitter = random.uniform(60, 120)
                await asyncio.sleep(jitter)

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

    # Calculate per-cycle cap for distributed sending
    cycle_cap = _calculate_cycle_cap(campaign.daily_limit, sent_today, config)
    remaining = min(remaining, cycle_cap)

    logger.debug(
        "Campaign %s: sent_today=%d daily_limit=%d cycle_cap=%d",
        str(campaign.id)[:8], sent_today, campaign.daily_limit, cycle_cap,
    )

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
                    # Skip unverified pattern guesses — wait for email_finder
                    not_(and_(
                        Outreach.email_source == "pattern_guess",
                        Outreach.email_verified == False,  # noqa: E712
                    )),
                )
            ).order_by(Outreach.created_at).limit(remaining).with_for_update(skip_locked=True)
        else:
            # Follow-up steps: at previous step, delay elapsed
            delay_cutoff = datetime.now(timezone.utc) - timedelta(hours=delay_hours)
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
                    # Skip unverified pattern guesses — wait for email_finder
                    not_(and_(
                        Outreach.email_source == "pattern_guess",
                        Outreach.email_verified == False,  # noqa: E712
                    )),
                )
            ).order_by(Outreach.last_email_sent_at).limit(remaining).with_for_update(skip_locked=True)

        result = await db.execute(query)
        prospects = result.scalars().all()
        for p in prospects:
            all_prospects.append((p, template_id))

    # Deduplicate by prospect ID (a prospect may appear in multiple step queries)
    seen_ids = set()
    deduped = []
    for p, tmpl in all_prospects:
        if p.id not in seen_ids:
            seen_ids.add(p.id)
            deduped.append((p, tmpl))
    all_prospects = deduped

    # Limit to daily cap
    all_prospects = all_prospects[:remaining]

    if not all_prospects:
        return

    logger.info(
        "Campaign %s: processing %d prospects",
        str(campaign.id)[:8], len(all_prospects),
    )

    consecutive_failures = 0
    for i, (prospect, template_id) in enumerate(all_prospects):
        try:
            deferred = await _check_smart_timing(prospect, config)
            if deferred:
                continue

            prev_failures = prospect.generation_failures or 0
            await send_sequence_email(
                db, config, settings, prospect,
                template_id=template_id, campaign=campaign,
            )
            await db.flush()

            new_failures = prospect.generation_failures or 0
            if new_failures > prev_failures:
                consecutive_failures += 1
            else:
                consecutive_failures = 0

            if consecutive_failures >= 3:
                await _trip_ai_circuit_breaker()
                break
        except Exception as e:
            logger.error(
                "Campaign %s: failed to send to %s: %s",
                str(campaign.id)[:8], str(prospect.id)[:8], str(e),
            )
            consecutive_failures += 1
            if consecutive_failures >= 3:
                await _trip_ai_circuit_breaker()
                break

        if i < len(all_prospects) - 1:
            jitter = random.uniform(60, 120)
            await asyncio.sleep(jitter)


async def _generate_email_with_template(
    prospect: Outreach,
    next_step: int,
    template: Optional[EmailTemplate] = None,
    sender_name: str = "Alek",
    enrichment_data: Optional[dict] = None,
) -> dict:
    """
    Generate an outreach email, optionally using a template.
    Checks for active A/B experiments and injects variant instructions.
    - No template or is_ai_generated=True with ai_instructions: use AI with instructions
    - is_ai_generated=False with body_template: render static template with substitutions
    - Fallback: standard AI generation
    """
    from src.agents.sales_outreach import _extract_first_name
    first_name = _extract_first_name(prospect.prospect_name or "")

    if template and not template.is_ai_generated and template.body_template:
        # Static template with variable substitution (no A/B testing for static templates)
        substitutions = {
            "{prospect_name}": prospect.prospect_name or "",
            "{first_name}": first_name or "there",
            "{company}": prospect.prospect_company or prospect.prospect_name or "",
            "{city}": prospect.city or "",
            "{trade}": prospect.prospect_trade_type or "home services",
            "{sender_name}": sender_name,
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

    # Check for active A/B experiment for this step
    ab_variant = None
    ab_extra_instruction = None
    try:
        from src.services.ab_testing import get_active_experiment, assign_variant

        experiment = await get_active_experiment(
            sequence_step=next_step,
            trade_type=prospect.prospect_trade_type,
        )
        if experiment and experiment.get("variants"):
            ab_variant = assign_variant(experiment["variants"])
            if ab_variant and ab_variant.get("instruction"):
                ab_extra_instruction = (
                    f"SUBJECT LINE INSTRUCTION (A/B test): {ab_variant['instruction']}"
                )
    except Exception as e:
        logger.debug("A/B experiment lookup failed (proceeding without): %s", str(e))

    # AI-generated email (with optional extra instructions from template + A/B variant)
    extra_instructions = None
    if template and template.is_ai_generated and template.ai_instructions:
        extra_instructions = template.ai_instructions

    # Combine template instructions with A/B variant instruction
    if ab_extra_instruction:
        extra_instructions = (
            f"{extra_instructions}\n\n{ab_extra_instruction}"
            if extra_instructions
            else ab_extra_instruction
        )

    # If no AB experiment and no template instructions, inject winning patterns
    if not ab_extra_instruction and not extra_instructions:
        try:
            from src.services.winning_patterns import format_patterns_for_prompt

            patterns = await format_patterns_for_prompt(
                trade=prospect.prospect_trade_type,
                step=next_step,
            )
            if patterns:
                extra_instructions = patterns
        except Exception as e:
            logger.debug("Winning patterns lookup failed: %s", str(e))

    result = await generate_outreach_email(
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
        sender_name=sender_name,
        enrichment_data=enrichment_data,
    )

    # Attach A/B variant info for tracking
    if ab_variant:
        result["ab_variant_id"] = ab_variant.get("id")

    return result


async def _verify_or_find_working_email(prospect: Outreach) -> Optional[str]:
    """
    Discover a real email for a pattern-guessed prospect using deep web
    scraping and Brave Search (replaces broken SMTP verification —
    port 25 blocked on VPS).

    Returns:
        Discovered email address, or None if no real email found.
    """
    from src.services.email_discovery import discover_email

    try:
        discovery = await discover_email(
            website=prospect.website or "",
            company_name=prospect.prospect_company or prospect.prospect_name,
            enrichment_data=prospect.enrichment_data,
        )
    except Exception as e:
        logger.warning(
            "Email discovery failed for prospect %s: %s",
            str(prospect.id)[:8], str(e),
        )
        return None

    email = discovery.get("email")
    source = discovery.get("source")
    confidence = discovery.get("confidence")

    if not email:
        logger.info(
            "No email found for prospect %s via discovery",
            str(prospect.id)[:8],
        )
        return None

    # Only accept non-pattern-guess results
    if source == "pattern_guess":
        logger.info(
            "Only pattern guess available for prospect %s, skipping",
            str(prospect.id)[:8],
        )
        return None

    # Update source metadata on the prospect
    prospect.email_source = source
    prospect.email_verified = confidence == "high"
    cost = discovery.get("cost_usd", 0.0)
    if cost > 0:
        prospect.total_cost_usd = (prospect.total_cost_usd or 0) + cost

    return email


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
            "Skipping prospect %s - invalid email (%s)",
            str(prospect.id)[:8], email_check["reason"],
        )
        return

    # Gate: SMTP-verify unverified pattern-guessed emails before sending
    if prospect.email_source == "pattern_guess" and not prospect.email_verified:
        verified_email = await _verify_or_find_working_email(prospect)
        if verified_email is None:
            logger.info(
                "Skipping prospect %s - no verified email found",
                str(prospect.id)[:8],
            )
            prospect.status = "no_verified_email"
            return
        # Update prospect with the (possibly different) verified email
        if verified_email != prospect.prospect_email:
            logger.info(
                "Prospect %s: swapped email from %s*** to %s***",
                str(prospect.id)[:8],
                prospect.prospect_email[:12],
                verified_email[:12],
            )
        prospect.prospect_email = verified_email
        prospect.email_verified = True

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

    # Check for email dedup across prospects - skip if another record with same email was already contacted
    if prospect.prospect_email:
        dupe_check = await db.execute(
            select(Outreach).where(
                and_(
                    Outreach.prospect_email == email_lower,
                    Outreach.id != prospect.id,
                    Outreach.total_emails_sent > 0,
                )
            ).limit(1)
        )
        if dupe_check.scalar_one_or_none():
            logger.info(
                "Skipping prospect %s - email already contacted via another record",
                str(prospect.id)[:8],
            )
            prospect.status = "duplicate_email"
            return

    next_step = prospect.outreach_sequence_step + 1

    # Load template if specified
    template = None
    if template_id:
        try:
            template = await db.get(EmailTemplate, uuid.UUID(template_id))
        except Exception as e:
            logger.warning(
                "Template %s not found for prospect %s",
                template_id, str(prospect.id)[:8],
            )

    # Generate personalized email - template-aware, enrichment-enhanced
    email_result = await _generate_email_with_template(
        prospect=prospect,
        next_step=next_step,
        template=template,
        sender_name=config.sender_name or "Alek",
        enrichment_data=prospect.enrichment_data,
    )

    if email_result.get("error"):
        logger.warning(
            "Email generation failed for prospect %s: %s",
            str(prospect.id)[:8], email_result["error"],
        )
        # Track generation failures - after 3 failures, mark as generation_failed
        prospect.generation_failures = (prospect.generation_failures or 0) + 1
        if prospect.generation_failures >= 3:
            prospect.status = "generation_failed"
            logger.warning(
                "Prospect %s marked generation_failed after %d failures",
                str(prospect.id)[:8], prospect.generation_failures,
            )
        return

    # Sanitize dashes from AI-generated content
    email_result = {
        **email_result,
        "subject": sanitize_dashes(email_result.get("subject", "")),
        "body_html": sanitize_dashes(email_result.get("body_html", "")),
        "body_text": sanitize_dashes(email_result.get("body_text", "")),
    }

    # Quality gate - lightweight pre-send validation
    try:
        from src.services.email_quality_gate import check_email_quality

        quality = check_email_quality(
            subject=email_result["subject"],
            body_text=email_result["body_text"],
            prospect_name=prospect.prospect_name,
            company_name=prospect.prospect_company,
        )
        if not quality["passed"]:
            logger.info(
                "Quality gate failed for %s (step %d): %s - regenerating",
                str(prospect.id)[:8], next_step, "; ".join(quality["issues"]),
            )
            # Regenerate once
            retry_result = await _generate_email_with_template(
                prospect=prospect,
                next_step=next_step,
                template=template,
                sender_name=config.sender_name or "Alek",
                enrichment_data=prospect.enrichment_data,
            )
            if not retry_result.get("error"):
                retry_result = {
                    **retry_result,
                    "subject": sanitize_dashes(retry_result.get("subject", "")),
                    "body_html": sanitize_dashes(retry_result.get("body_html", "")),
                    "body_text": sanitize_dashes(retry_result.get("body_text", "")),
                }
                retry_quality = check_email_quality(
                    subject=retry_result["subject"],
                    body_text=retry_result["body_text"],
                    prospect_name=prospect.prospect_name,
                    company_name=prospect.prospect_company,
                )
                if retry_quality["passed"]:
                    email_result = retry_result
                else:
                    logger.warning(
                        "Quality gate still failing for %s after retry: %s - sending anyway",
                        str(prospect.id)[:8], "; ".join(retry_quality["issues"]),
                    )
    except Exception as qg_err:
        logger.debug("Quality gate check failed: %s", str(qg_err))

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

    # For follow-ups (steps 2-3), reuse step 1 subject with "Re:" for Gmail threading
    send_subject = email_result["subject"]
    if next_step > 1 and in_reply_to:
        # Look up the step 1 subject to thread the conversation
        step1_result = await db.execute(
            select(OutreachEmail.subject).where(
                and_(
                    OutreachEmail.outreach_id == prospect.id,
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sequence_step == 1,
                )
            ).limit(1)
        )
        step1_subject = step1_result.scalar()
        if step1_subject:
            send_subject = f"Re: {step1_subject}"

    # Send email
    send_result = await send_cold_email(
        to_email=prospect.prospect_email,
        to_name=prospect.prospect_name,
        subject=send_subject,
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
        body_text=email_result.get("body_text", ""),
        company_name="LeadLock",
    )

    if send_result.get("error"):
        logger.warning(
            "Email send failed for prospect %s: %s",
            str(prospect.id)[:8], send_result["error"],
        )
        return

    # Record send event for email reputation tracking
    try:
        from src.utils.dedup import get_redis
        from src.services.deliverability import record_email_event
        redis = await get_redis()
        await record_email_event(redis, "sent")
    except Exception as rep_err:
        logger.debug("Failed to record email send event: %s", str(rep_err))

    now = datetime.now(timezone.utc)

    # Record email (with A/B variant if assigned)
    ab_variant_id_str = email_result.get("ab_variant_id")
    ab_variant_uuid = None
    if ab_variant_id_str:
        try:
            ab_variant_uuid = uuid.UUID(ab_variant_id_str)
        except (ValueError, TypeError):
            pass

    email_record = OutreachEmail(
        outreach_id=prospect.id,
        direction="outbound",
        subject=send_subject,
        body_html=email_result["body_html"],
        body_text=email_result["body_text"],
        from_email=config.from_email,
        to_email=prospect.prospect_email,
        sendgrid_message_id=send_result.get("message_id"),
        sequence_step=next_step,
        sent_at=now,
        ai_cost_usd=email_result.get("ai_cost_usd", 0.0),
        ab_variant_id=ab_variant_uuid,
    )
    db.add(email_record)

    # Track A/B variant send event
    if ab_variant_id_str:
        try:
            from src.services.ab_testing import record_event
            await record_event(ab_variant_id_str, "sent")
        except Exception as ab_err:
            logger.debug("A/B send tracking failed: %s", str(ab_err))

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
        "Outreach email sent: prospect=%s step=%d to=%s campaign=%s",
        str(prospect.id)[:8], next_step, prospect.prospect_email[:20] + "***",
        str(campaign.id)[:8] if campaign else "none",
    )
