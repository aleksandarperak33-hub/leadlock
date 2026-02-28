"""
Outreach sequencer worker - orchestrates cold email sequences.
Runs every 30 minutes. Respects daily email limits, sequence delays,
and business hours gating (configurable timezone + weekdays).

Email sending logic lives in outreach_sending.py.
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from sqlalchemy import select, and_, not_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.sales_config import SalesEngineConfig
from src.models.campaign import Campaign
from src.config import get_settings
from src.services.sales_tenancy import get_active_sales_configs
from src.services.sender_mailboxes import get_primary_sender_profile
from src.services.outreach_timing import (
    MIN_FOLLOWUP_DELAY_HOURS,
    followup_readiness,
)

# Re-exports for backward compatibility
from src.workers.outreach_sending import (  # noqa: F401
    sanitize_dashes,
    _verify_or_find_working_email,
    _generate_email_with_template,
    send_sequence_email,
)

logger = logging.getLogger(__name__)

# Generic email prefixes — deprioritized in outreach ordering
# (personal emails like first.last@ are sent first for higher reply rates)
_GENERIC_EMAIL_PREFIXES = frozenset({
    "info", "contact", "admin", "support", "sales", "hello", "help",
    "team", "office", "service", "general", "mail", "email",
})

POLL_INTERVAL_SECONDS = 30 * 60  # 30 minutes

# Email warmup schedule - conservative ramp for sender reputation stability.
# Format: (day_range_start, day_range_end, max_daily_emails)
# day_range_end of None means "and beyond"; max_daily of None means "use configured limit"
EMAIL_WARMUP_SCHEDULE = [
    (0, 3, 10),        # Days 0-3: 10 emails/day
    (4, 7, 20),        # Days 4-7: 20 emails/day
    (8, 14, 40),       # Days 8-14: 40 emails/day
    (15, 21, 75),      # Days 15-21: 75 emails/day
    (22, 28, 120),     # Days 22-28: 120 emails/day
    (29, None, None),  # Day 29+: use configured limit
]


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

        # Avoid duplicate deferred tasks for the same prospect/time window.
        dedupe_key = f"leadlock:smart_timing:queued:{prospect.id}"
        redis = None
        try:
            from src.utils.dedup import get_redis
            redis = await get_redis()
            if await redis.exists(dedupe_key):
                return True
        except Exception:
            redis = None

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
        if redis:
            try:
                await redis.set(dedupe_key, "1", ex=max(1800, delay_seconds + 900))
            except Exception:
                pass

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


async def _get_warmup_limit(
    configured_limit: int,
    from_email: str = "",
    tenant_id=None,
) -> int:
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
        tenant_part = str(tenant_id) if tenant_id else "global"
        warmup_key = f"leadlock:email_warmup:{tenant_part}:{domain}"
        started_at_raw = await redis.get(warmup_key)

        if started_at_raw is None:
            # Redis key missing — recover from DB to avoid resetting warmup
            started_at = await _recover_warmup_start_from_db(tenant_id=tenant_id)
            if started_at is not None:
                await redis.set(warmup_key, started_at.isoformat())
                logger.info("Recovered warmup start from DB: %s", started_at.isoformat())
            else:
                # Truly first email ever — start warmup now
                started_at = datetime.now(timezone.utc)
                await redis.set(warmup_key, started_at.isoformat())
                logger.info("Email warmup started - day 0, limit=10")
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


async def _recover_warmup_start_from_db(tenant_id=None) -> Optional[datetime]:
    """
    Recover the warmup start date from the earliest outbound email in the DB.
    This prevents warmup resets when Redis data is lost on container restarts.
    """
    try:
        async with async_session_factory() as db:
            query = (
                select(func.min(OutreachEmail.sent_at))
                .select_from(OutreachEmail)
                .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
                .where(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sent_at.isnot(None),
                )
            )
            if tenant_id:
                query = query.where(Outreach.tenant_id == tenant_id)
            result = await db.execute(query)
            earliest = result.scalar()
            return earliest
    except Exception as e:
        logger.warning("Failed to recover warmup start from DB: %s", str(e))
        return None


async def _get_multi_mailbox_warmup_limit(
    config: SalesEngineConfig,
    tenant_id,
    primary_from_email: str,
) -> int:
    """
    Calculate combined warmup limit across ALL active sender mailboxes.

    Each domain warms up independently, so adding a second sending domain
    doubles throughput during the warmup period. Mailboxes on the same
    domain share that domain's warmup limit.

    Returns:
        Combined warmup limit (capped at config.daily_email_limit).
    """
    from src.services.sender_mailboxes import get_active_sender_mailboxes

    mailboxes = get_active_sender_mailboxes(config)
    if not mailboxes:
        return await _get_warmup_limit(
            config.daily_email_limit, primary_from_email, tenant_id=tenant_id,
        )

    # Group mailboxes by domain — mailboxes on the same domain share warmup
    domain_mailboxes: dict[str, list[dict]] = {}
    for mb in mailboxes:
        email = mb.get("from_email", "")
        domain = email.split("@")[1].lower() if "@" in email else "default"
        domain_mailboxes.setdefault(domain, []).append(mb)

    total_warmup = 0

    for domain, mbs in domain_mailboxes.items():
        # Get warmup limit for this domain
        representative_email = mbs[0]["from_email"]
        domain_warmup = await _get_warmup_limit(
            config.daily_email_limit, representative_email, tenant_id=tenant_id,
        )

        # Apply warmup optimizer if available
        try:
            from src.services.warmup_optimizer import get_optimized_warmup_limit
            from src.utils.dedup import get_redis as _get_redis_for_warmup

            _redis = await _get_redis_for_warmup()
            _warmup_key = f"leadlock:email_warmup:{tenant_id}:{domain}"
            _started_raw = await _redis.get(_warmup_key)
            if _started_raw:
                _started_str = (
                    _started_raw.decode()
                    if isinstance(_started_raw, bytes)
                    else str(_started_raw)
                )
                _started = datetime.fromisoformat(_started_str)
                _days = (datetime.now(timezone.utc) - _started).days
                domain_warmup = await get_optimized_warmup_limit(domain_warmup, _days)
        except Exception:
            pass

        # Sum per-mailbox daily limits for this domain (if set)
        mailbox_sum = 0
        for mb in mbs:
            mb_limit = mb.get("daily_limit")
            if mb_limit and int(mb_limit) > 0:
                mailbox_sum += int(mb_limit)
            else:
                # No per-mailbox limit: this mailbox uses the full domain warmup
                mailbox_sum = domain_warmup
                break

        # The domain's contribution is capped by its warmup stage
        domain_contribution = min(domain_warmup, mailbox_sum)
        total_warmup += domain_contribution

        logger.debug(
            "Domain %s: warmup=%d mailbox_sum=%d contribution=%d",
            domain, domain_warmup, mailbox_sum, domain_contribution,
        )

    # Cap at configured tenant limit
    combined = min(total_warmup, config.daily_email_limit)

    if len(domain_mailboxes) > 1:
        logger.info(
            "Multi-domain warmup: %d domains, combined_limit=%d (tenant cap=%d)",
            len(domain_mailboxes), combined, config.daily_email_limit,
        )

    return combined


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

        throttle = reputation["throttle"]
        metrics = reputation.get("metrics", {})
        sent = metrics.get("sent", 0)
        open_rate = metrics.get("open_rate", 0.0)

        # If opens are weak at meaningful volume, pace down proactively.
        if sent >= 100 and open_rate < 0.05 and throttle in ("normal", "reduced"):
            throttle = "critical"
            logger.warning(
                "Email open rate CRITICAL (%.2f%% over %d sends) - pacing at 25%% capacity",
                open_rate * 100, sent,
            )
        elif sent >= 50 and open_rate < 0.08 and throttle == "normal":
            throttle = "reduced"
            logger.warning(
                "Email open rate LOW (%.2f%% over %d sends) - pacing at 50%% capacity",
                open_rate * 100, sent,
            )

        if throttle == "critical":
            logger.warning(
                "Email reputation POOR (%.1f) - sending at 25%% capacity",
                reputation["score"],
            )
        elif throttle == "reduced":
            logger.warning(
                "Email reputation WARNING (%.1f) - sending at 50%% capacity",
                reputation["score"],
            )

        return True, throttle

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


async def _all_active_configs_paused() -> bool:
    """
    Lightweight pre-check so the main loop can skip a cycle when every active
    config is paused.
    """
    try:
        async with async_session_factory() as db:
            configs = await get_active_sales_configs(db)
            if not configs:
                return False
            return all(bool(getattr(cfg, "sequencer_paused", False)) for cfg in configs)
    except Exception as e:
        logger.debug("Sequencer pause pre-check failed: %s", str(e))
        return False


async def run_outreach_sequencer():
    """Main loop - process outreach sequences every 30 minutes."""
    logger.info("Outreach sequencer started (poll every %ds)", POLL_INTERVAL_SECONDS)

    while True:
        await _heartbeat()
        try:
            if await _all_active_configs_paused():
                logger.info("All active sequencer configs are paused — skipping cycle")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            # Persistent circuit breaker — skip cycle if AI provider is down
            if await _is_ai_circuit_open():
                logger.info("AI circuit breaker is open — skipping outreach cycle")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            await sequence_cycle()
        except Exception as e:
            logger.error("Outreach sequencer error: %s", str(e))

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _recover_generation_failed(db: AsyncSession, tenant_id) -> int:
    """
    Reset prospects stuck in 'generation_failed' back to 'cold' so they
    can be retried now that the AI circuit breaker has cleared.
    Returns count of recovered prospects.
    """
    try:
        result = await db.execute(
            select(Outreach).where(
                and_(
                    Outreach.status == "generation_failed",
                    Outreach.tenant_id == tenant_id,
                )
            )
        )
        prospects = list(result.scalars().all())
        if not prospects:
            return 0
        for p in prospects:
            p.status = "cold"
            p.generation_failures = 0
        await db.flush()
        logger.info(
            "Recovered %d generation_failed prospects back to cold (tenant=%s)",
            len(prospects),
            str(tenant_id)[:8],
        )
        return len(prospects)
    except Exception as e:
        logger.debug("Recovery check failed: %s", str(e))
        return 0


async def sequence_cycle():
    """
    Execute one full outreach sequence cycle. Respects business hours gating.
    Two-pass per tenant: (1) active campaigns, (2) unbound prospects.
    """
    async with async_session_factory() as db:
        configs = await get_active_sales_configs(db)
        if not configs:
            return

        # Email reputation circuit breaker - pause if reputation is critical
        email_healthy, throttle_level = await _check_email_health()
        if not email_healthy:
            logger.warning("Email sending paused due to poor reputation - skipping cycle")
            return

        settings = get_settings()
        for config in configs:
            tenant_id = getattr(config, "tenant_id", None)
            if not tenant_id:
                continue
            if getattr(config, "sequencer_paused", False):
                logger.debug("Outreach sequencer paused for tenant=%s", str(tenant_id)[:8])
                continue
            if not is_within_send_window(config):
                logger.info(
                    "Outside send window, deferring outreach (tenant=%s)",
                    str(tenant_id)[:8],
                )
                continue
            if not config.company_address:
                logger.warning(
                    "Company address not configured for tenant=%s",
                    str(tenant_id)[:8],
                )
                continue
            primary_sender = get_primary_sender_profile(config)
            if not primary_sender:
                logger.warning(
                    "No active sender mailbox configured for tenant=%s",
                    str(tenant_id)[:8],
                )
                continue

            try:
                await _sequence_cycle_for_tenant(
                    db,
                    config,
                    settings,
                    throttle_level,
                    primary_sender["from_email"],
                )
                await db.commit()
            except Exception as tenant_err:
                await db.rollback()
                logger.error(
                    "Tenant outreach cycle failed tenant=%s: %s",
                    str(tenant_id)[:8],
                    str(tenant_err),
                )


async def _sequence_cycle_for_tenant(
    db: AsyncSession,
    config: SalesEngineConfig,
    settings,
    throttle_level: str,
    primary_from_email: str,
) -> None:
    """Run one sequencer cycle for a single tenant config."""
    tenant_id = config.tenant_id
    if not tenant_id:
        return

    # Recover prospects damaged by previous AI outage
    await _recover_generation_failed(db, tenant_id)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # === PASS 1: Active campaigns ===
    campaigns_result = await db.execute(
        select(Campaign).where(
            and_(
                Campaign.tenant_id == tenant_id,
                Campaign.status == "active",
            )
        )
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
    sent_today_result = await db.execute(
        select(func.count())
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.tenant_id == tenant_id,
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= today_start,
            )
        )
    )
    sent_today = sent_today_result.scalar() or 0

    # Calculate combined warmup limit across all active mailboxes/domains.
    # Each domain warms up independently, so multiple domains multiply throughput.
    warmup_limit = await _get_multi_mailbox_warmup_limit(
        config, tenant_id, primary_from_email,
    )

    from src.services.deliverability import EMAIL_THROTTLE_FACTORS

    throttle_factor = EMAIL_THROTTLE_FACTORS.get(throttle_level, 1.0)
    effective_limit = max(1, int(warmup_limit * throttle_factor))

    remaining = effective_limit - sent_today
    if remaining <= 0:
        logger.info(
            "Daily email limit reached (tenant=%s sent=%d effective_limit=%d warmup=%d throttle=%s)",
            str(tenant_id)[:8],
            sent_today,
            effective_limit,
            warmup_limit,
            throttle_level,
        )
        return

    cycle_cap = _calculate_cycle_cap(
        effective_limit, sent_today, config,
    )
    remaining = min(remaining, cycle_cap)

    logger.info(
        "Tenant %s unbound prospects: sent_today=%d effective_limit=%d (warmup=%d throttle=%s) cycle_cap=%d",
        str(tenant_id)[:8],
        sent_today,
        effective_limit,
        warmup_limit,
        throttle_level,
        cycle_cap,
    )

    delay_cutoff = datetime.now(timezone.utc) - timedelta(hours=MIN_FOLLOWUP_DELAY_HOURS)

    verification_freshness_cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    step_0_query = select(Outreach).where(
        and_(
            Outreach.tenant_id == tenant_id,
            Outreach.campaign_id.is_(None),
            Outreach.outreach_sequence_step == 0,
            Outreach.prospect_email.isnot(None),
            Outreach.prospect_email != "",
            Outreach.email_verified == True,  # noqa: E712
            Outreach.email_unsubscribed == False,
            Outreach.status.in_(["cold"]),
            Outreach.last_email_replied_at.is_(None),
            # Verification freshness: require verified within 7 days
            Outreach.verified_at >= verification_freshness_cutoff,
            # Source quality: block pattern_guess from first-touch
            Outreach.email_source != "pattern_guess",
        )
    ).order_by(
        # Quality-based priority: personal emails first (not info@, service@, etc.)
        # PostgreSQL-specific: deprioritize generic prefixes (info@, service@, etc.)
        func.split_part(Outreach.prospect_email, "@", 1).in_(
            sorted(_GENERIC_EMAIL_PREFIXES)
        ).asc(),
        # Then enriched first, then by rating and reviews
        Outreach.enrichment_data.is_(None).asc(),
        Outreach.google_rating.desc().nulls_last(),
        Outreach.review_count.desc().nulls_last(),
        Outreach.created_at,
    ).limit(remaining).with_for_update(skip_locked=True)

    followup_query = select(Outreach).where(
        and_(
            Outreach.tenant_id == tenant_id,
            Outreach.campaign_id.is_(None),
            Outreach.outreach_sequence_step >= 1,
            Outreach.outreach_sequence_step < config.max_sequence_steps,
            Outreach.prospect_email.isnot(None),
            Outreach.prospect_email != "",
            Outreach.email_unsubscribed == False,
            Outreach.status.in_(["cold", "contacted"]),
            Outreach.last_email_replied_at.is_(None),
            Outreach.last_email_sent_at <= delay_cutoff,
            not_(and_(
                Outreach.email_source == "pattern_guess",
                Outreach.email_verified == False,  # noqa: E712
            )),
        )
    ).order_by(Outreach.last_email_sent_at).limit(remaining).with_for_update(skip_locked=True)

    step_0_result = await db.execute(step_0_query)
    step_0_prospects = step_0_result.scalars().all()

    followup_result = await db.execute(followup_query)
    followup_prospects_raw = followup_result.scalars().all()
    followup_prospects = []
    for p in followup_prospects_raw:
        is_due, required_delay, remaining_seconds = followup_readiness(
            p, base_delay_hours=config.sequence_delay_hours
        )
        if is_due:
            followup_prospects.append(p)
        else:
            logger.debug(
                "Prospect %s follow-up not due yet (required=%dh remaining=%ds)",
                str(p.id)[:8], required_delay, remaining_seconds,
            )

    all_prospects = (followup_prospects + step_0_prospects)[:remaining]

    if all_prospects:
        logger.info(
            "Processing %d unbound prospects for outreach (tenant=%s)",
            len(all_prospects),
            str(tenant_id)[:8],
        )

    consecutive_failures = 0
    for i, prospect in enumerate(all_prospects):
        try:
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
            # Commit each send immediately so webhooks can resolve records
            # without waiting for end-of-tenant batch commit.
            await db.commit()

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
                    "Circuit breaker: %d consecutive exceptions. Stopping batch.",
                    consecutive_failures,
                )
                break

        if i < len(all_prospects) - 1:
            jitter = random.uniform(60, 120)
            await asyncio.sleep(jitter)


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
                Outreach.tenant_id == campaign.tenant_id,
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

        # Hard cap: skip campaign steps beyond max_sequence_steps
        if step_num > config.max_sequence_steps:
            logger.debug(
                "Campaign %s step %d exceeds max_sequence_steps %d, skipping",
                str(campaign.id)[:8], step_num, config.max_sequence_steps,
            )
            continue

        if step_num == 1:
            # Step 1: cold prospects in this campaign, never contacted
            campaign_freshness_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            query = select(Outreach).where(
                and_(
                    Outreach.tenant_id == campaign.tenant_id,
                    Outreach.campaign_id == campaign.id,
                    Outreach.outreach_sequence_step == 0,
                    Outreach.prospect_email.isnot(None),
                    Outreach.prospect_email != "",
                    Outreach.email_verified == True,  # noqa: E712
                    Outreach.email_unsubscribed == False,
                    Outreach.status.in_(["cold"]),
                    Outreach.last_email_replied_at.is_(None),
                    # Verification freshness: require verified within 7 days
                    Outreach.verified_at >= campaign_freshness_cutoff,
                    # Source quality: block pattern_guess from first-touch
                    Outreach.email_source != "pattern_guess",
                )
            ).order_by(
                # Personal emails first (not info@, service@, etc.)
                func.split_part(Outreach.prospect_email, "@", 1).in_(
                    list(_GENERIC_EMAIL_PREFIXES)
                ).asc(),
                Outreach.created_at,
            ).limit(remaining).with_for_update(skip_locked=True)
        else:
            # Follow-up steps: at previous step, delay elapsed
            delay_cutoff = datetime.now(timezone.utc) - timedelta(hours=MIN_FOLLOWUP_DELAY_HOURS)
            query = select(Outreach).where(
                and_(
                    Outreach.tenant_id == campaign.tenant_id,
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
            if step_num > 1:
                is_due, required_delay, remaining_seconds = followup_readiness(
                    p, base_delay_hours=delay_hours
                )
                if not is_due:
                    logger.debug(
                        "Campaign %s prospect %s step %d not due (required=%dh remaining=%ds)",
                        str(campaign.id)[:8], str(p.id)[:8], step_num, required_delay, remaining_seconds,
                    )
                    continue
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
            # Commit each send immediately so event webhooks can correlate
            # sendgrid_message_id records in near real-time.
            await db.commit()

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
