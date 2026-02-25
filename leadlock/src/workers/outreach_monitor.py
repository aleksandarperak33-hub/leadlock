"""
Outreach monitor — merged from outreach_health + outreach_cleanup.
Runs every 15 minutes.

Every cycle: Pipeline health checks (from outreach_health).
Every 16th cycle (~4h): Mark exhausted sequences as lost (from outreach_cleanup).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_, not_, update

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.services.sales_tenancy import get_active_sales_configs
from src.utils.alerting import send_alert, AlertType

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15 * 60  # 15 minutes
CLEANUP_EVERY_N_CYCLES = 16  # ~4 hours

# Alert thresholds
ZERO_SENDS_HOURS = 4
BOUNCE_RATE_THRESHOLD = 0.10
OPEN_RATE_THRESHOLD = 0.12
OPEN_RATE_MIN_SAMPLE = 30
OPEN_RATE_WINDOW_HOURS = 48
HEARTBEAT_STALE_MINUTES = 45


async def _heartbeat():
    """Store heartbeat timestamp in Redis."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(
            "leadlock:worker_health:outreach_monitor",
            datetime.now(timezone.utc).isoformat(),
            ex=1800,
        )
    except Exception as e:
        logger.debug("Heartbeat write failed: %s", str(e))


async def run_outreach_monitor():
    """Main loop — health checks every cycle, cleanup every 16th."""
    logger.info("Outreach monitor started (poll every %ds)", POLL_INTERVAL_SECONDS)

    # Wait 2 minutes on startup to let other workers initialize
    await asyncio.sleep(120)

    cycle_count = 0

    while True:
        cycle_count += 1

        try:
            # Every cycle: pipeline health checks
            await _check_outreach_health()

            # Every 16th cycle: cleanup exhausted sequences
            if cycle_count % CLEANUP_EVERY_N_CYCLES == 0:
                await _cleanup_exhausted_sequences()
        except Exception as e:
            logger.error("Outreach monitor error: %s", str(e))

        await _heartbeat()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Health checks (from outreach_health)
# ---------------------------------------------------------------------------

async def _check_outreach_health():
    """Run all outreach health checks and send alerts for failures."""
    from src.workers.outreach_sequencer import is_within_send_window

    async with async_session_factory() as db:
        configs = await get_active_sales_configs(db)
        if not configs:
            return

        now = datetime.now(timezone.utc)
        for config in configs:
            tenant_id = getattr(config, "tenant_id", None)
            in_send_window = is_within_send_window(config)
            if in_send_window:
                await _check_zero_sends(db, now, config, tenant_id)
            await _check_bounce_rate(db, now, tenant_id)
            await _check_open_rate(db, now, tenant_id)
        await _check_sequencer_heartbeat()
        await _check_reputation_paused()


async def _estimate_effective_daily_limit(config, tenant_id) -> int:
    """
    Estimate today's effective send cap after warmup and reputation throttling.
    Falls back to configured daily limit if dependencies are unavailable.
    """
    configured_limit = max(1, int(getattr(config, "daily_email_limit", 1) or 1))
    try:
        from src.services.sender_mailboxes import get_primary_sender_profile
        from src.services.deliverability import EMAIL_THROTTLE_FACTORS
        from src.workers.outreach_sequencer import _get_warmup_limit, _check_email_health

        primary_profile = get_primary_sender_profile(config) or {}
        from_email = primary_profile.get("from_email", "")
        warmup_limit = await _get_warmup_limit(
            configured_limit,
            from_email,
            tenant_id=tenant_id,
        )
        _, throttle_level = await _check_email_health()
        throttle_factor = EMAIL_THROTTLE_FACTORS.get(throttle_level, 1.0)
        return max(1, int(warmup_limit * throttle_factor))
    except Exception as e:
        logger.debug("Failed to estimate effective daily limit: %s", str(e))
        return configured_limit


async def _count_ready_candidates(db, now: datetime, config, tenant_id) -> int:
    """Count prospects currently eligible for sequencer sends."""
    followup_cutoff = now - timedelta(hours=max(1, getattr(config, "sequence_delay_hours", 48)))
    max_steps = max(1, int(getattr(config, "max_sequence_steps", 3) or 3))

    result = await db.execute(
        select(func.count()).select_from(Outreach).where(
            and_(
                Outreach.tenant_id == tenant_id,
                Outreach.prospect_email.isnot(None),
                Outreach.prospect_email != "",
                Outreach.email_unsubscribed == False,
                Outreach.status.in_(["cold", "contacted"]),
                Outreach.last_email_replied_at.is_(None),
                (
                    and_(
                        Outreach.outreach_sequence_step == 0,
                        Outreach.status == "cold",
                        Outreach.email_verified == True,  # noqa: E712
                    )
                    | and_(
                        Outreach.outreach_sequence_step >= 1,
                        Outreach.outreach_sequence_step < max_steps,
                        Outreach.last_email_sent_at.isnot(None),
                        Outreach.last_email_sent_at <= followup_cutoff,
                        not_(and_(
                            Outreach.email_source == "pattern_guess",
                            Outreach.email_verified == False,  # noqa: E712
                        )),
                    )
                ),
            )
        )
    )
    return result.scalar() or 0


async def _check_zero_sends(db, now: datetime, config, tenant_id) -> None:
    """Alert if zero outbound emails sent in the last 4 hours during send window."""
    cutoff = now - timedelta(hours=ZERO_SENDS_HOURS)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    recent_result = await db.execute(
        select(func.count())
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.tenant_id == tenant_id,
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
            )
        )
    )
    count = recent_result.scalar() or 0
    if count > 0:
        return

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

    effective_limit = await _estimate_effective_daily_limit(config, tenant_id)
    if sent_today >= effective_limit:
        logger.debug(
            "Skipping zero-sends alert for tenant=%s: daily effective cap reached (%d/%d)",
            str(tenant_id)[:8],
            sent_today,
            effective_limit,
        )
        return

    ready_candidates = await _count_ready_candidates(db, now, config, tenant_id)
    if ready_candidates == 0:
        logger.debug(
            "Skipping zero-sends alert for tenant=%s: no ready prospects",
            str(tenant_id)[:8],
        )
        return

    await send_alert(
        alert_type=AlertType.OUTREACH_ZERO_SENDS,
        message=(
            f"Zero outbound emails sent in the last {ZERO_SENDS_HOURS} hours "
            f"during the send window despite {ready_candidates} ready prospects. "
            f"The sequencer may be stuck or paused."
        ),
        severity="critical",
        extra={
            "window_hours": str(ZERO_SENDS_HOURS),
            "check_time": now.isoformat(),
            "tenant_id": str(tenant_id),
            "ready_candidates": str(ready_candidates),
            "sent_today": str(sent_today),
            "effective_limit": str(effective_limit),
        },
    )


async def _check_bounce_rate(db, now: datetime, tenant_id) -> None:
    """Alert if bounce rate exceeds 10% in the last 24 hours."""
    cutoff = now - timedelta(hours=24)

    sent_result = await db.execute(
        select(func.count())
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.tenant_id == tenant_id,
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
            )
        )
    )
    sent_count = sent_result.scalar() or 0

    if sent_count < 10:
        return

    bounced_result = await db.execute(
        select(func.count())
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.tenant_id == tenant_id,
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
                OutreachEmail.bounced_at.isnot(None),
            )
        )
    )
    bounced_count = bounced_result.scalar() or 0

    bounce_rate = bounced_count / sent_count
    if bounce_rate > BOUNCE_RATE_THRESHOLD:
        await send_alert(
            alert_type=AlertType.HIGH_BOUNCE_RATE,
            message=(
                f"Email bounce rate is {bounce_rate:.1%} in the last 24h "
                f"({bounced_count}/{sent_count} bounced). "
                f"Threshold: {BOUNCE_RATE_THRESHOLD:.0%}. Check email list quality."
            ),
            severity="critical",
            extra={
                "bounce_rate": f"{bounce_rate:.4f}",
                "bounced": str(bounced_count),
                "sent": str(sent_count),
                "tenant_id": str(tenant_id),
            },
        )


async def _check_open_rate(db, now: datetime, tenant_id) -> None:
    """Alert if open rate is below threshold over 48 hours with sufficient sample size."""
    cutoff = now - timedelta(hours=OPEN_RATE_WINDOW_HOURS)

    sent_result = await db.execute(
        select(func.count())
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.tenant_id == tenant_id,
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
            )
        )
    )
    sent_count = sent_result.scalar() or 0

    if sent_count < OPEN_RATE_MIN_SAMPLE:
        return

    opened_result = await db.execute(
        select(func.count())
        .select_from(OutreachEmail)
        .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
        .where(
            and_(
                Outreach.tenant_id == tenant_id,
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= cutoff,
                OutreachEmail.opened_at.isnot(None),
            )
        )
    )
    opened_count = opened_result.scalar() or 0

    open_rate = opened_count / sent_count
    if open_rate < OPEN_RATE_THRESHOLD:
        await send_alert(
            alert_type=AlertType.OUTREACH_LOW_OPEN_RATE,
            message=(
                f"Email open rate is {open_rate:.1%} over the last {OPEN_RATE_WINDOW_HOURS}h "
                f"({opened_count}/{sent_count} opened). "
                f"Threshold: {OPEN_RATE_THRESHOLD:.0%}. "
                f"Review subject lines and sender reputation."
            ),
            severity="warning",
            extra={
                "open_rate": f"{open_rate:.4f}",
                "opened": str(opened_count),
                "sent": str(sent_count),
                "window_hours": str(OPEN_RATE_WINDOW_HOURS),
                "tenant_id": str(tenant_id),
            },
        )


async def _check_sequencer_heartbeat() -> None:
    """Alert if the outreach sequencer hasn't heartbeated in 45 minutes."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        heartbeat_raw = await redis.get("leadlock:worker_health:outreach_sequencer")
        if heartbeat_raw is None:
            await send_alert(
                alert_type=AlertType.OUTREACH_SEQUENCER_STALE,
                message=(
                    "Outreach sequencer has no heartbeat in Redis. "
                    "The worker may not be running."
                ),
                severity="critical",
            )
            return

        heartbeat_str = heartbeat_raw.decode() if isinstance(heartbeat_raw, bytes) else str(heartbeat_raw)
        last_heartbeat = datetime.fromisoformat(heartbeat_str)
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=HEARTBEAT_STALE_MINUTES)

        if last_heartbeat < stale_cutoff:
            minutes_ago = int((datetime.now(timezone.utc) - last_heartbeat).total_seconds() / 60)
            await send_alert(
                alert_type=AlertType.OUTREACH_SEQUENCER_STALE,
                message=(
                    f"Outreach sequencer last heartbeat was {minutes_ago} minutes ago. "
                    f"Threshold: {HEARTBEAT_STALE_MINUTES} minutes. "
                    f"The worker may be stuck or crashed."
                ),
                severity="critical",
                extra={"last_heartbeat": heartbeat_str, "minutes_ago": str(minutes_ago)},
            )
    except Exception as e:
        logger.warning("Failed to check sequencer heartbeat: %s", str(e))


async def _check_reputation_paused() -> None:
    """Alert if the email reputation system has paused sending."""
    try:
        from src.utils.dedup import get_redis
        from src.services.deliverability import get_email_reputation

        redis = await get_redis()
        reputation = await get_email_reputation(redis)

        if reputation["throttle"] == "paused":
            await send_alert(
                alert_type=AlertType.OUTREACH_REPUTATION_PAUSED,
                message=(
                    f"Email reputation system has PAUSED sending. "
                    f"Score: {reputation['score']}/100. "
                    f"Bounce rate: {reputation['metrics'].get('bounce_rate', 0):.2%}, "
                    f"Complaint rate: {reputation['metrics'].get('complaint_rate', 0):.4%}. "
                    f"Sending will not resume until reputation improves."
                ),
                severity="critical",
                extra={
                    "reputation_score": str(reputation["score"]),
                    "throttle": reputation["throttle"],
                },
            )
        elif reputation["throttle"] == "critical":
            await send_alert(
                alert_type=AlertType.OUTREACH_REPUTATION_CRITICAL,
                message=(
                    f"Email reputation is CRITICAL - sending at 25% capacity. "
                    f"Score: {reputation['score']}/100. "
                    f"Investigate bounce/complaint sources immediately."
                ),
                severity="error",
                extra={
                    "reputation_score": str(reputation["score"]),
                    "throttle": reputation["throttle"],
                },
            )
    except Exception as e:
        logger.warning("Failed to check email reputation: %s", str(e))


# ---------------------------------------------------------------------------
# Cleanup (from outreach_cleanup, runs every ~4h)
# ---------------------------------------------------------------------------

async def _cleanup_exhausted_sequences():
    """Mark exhausted outreach sequences as lost."""
    async with async_session_factory() as db:
        configs = await get_active_sales_configs(db)
        if not configs:
            return

        total_marked = 0
        from src.models.campaign import Campaign

        for config in configs:
            tenant_id = getattr(config, "tenant_id", None)
            tenant_label = str(tenant_id)[:8] if tenant_id else "global"
            if getattr(config, "cleanup_paused", False):
                logger.debug("Outreach cleanup is paused for tenant=%s", tenant_label)
                continue

            delay_cutoff = datetime.now(timezone.utc) - timedelta(hours=config.sequence_delay_hours)
            tenant_outreach_filter = (
                Outreach.tenant_id == tenant_id
                if tenant_id is not None
                else Outreach.tenant_id.is_(None)
            )
            tenant_campaign_filter = (
                Campaign.tenant_id == tenant_id
                if tenant_id is not None
                else Campaign.tenant_id.is_(None)
            )

            campaigns_result = await db.execute(
                select(Campaign).where(
                    and_(
                        tenant_campaign_filter,
                        Campaign.status.in_(["active", "paused", "completed"]),
                    )
                )
            )
            all_campaigns = campaigns_result.scalars().all()

            for campaign in all_campaigns:
                steps = campaign.sequence_steps or []
                campaign_max_steps = len(steps)
                if campaign_max_steps == 0:
                    continue

                stmt = (
                    update(Outreach)
                    .where(
                        and_(
                            tenant_outreach_filter,
                            Outreach.campaign_id == campaign.id,
                            Outreach.outreach_sequence_step >= campaign_max_steps,
                            Outreach.status.in_(["cold", "contacted"]),
                            Outreach.last_email_replied_at.is_(None),
                            Outreach.last_email_sent_at.isnot(None),
                            Outreach.last_email_sent_at <= delay_cutoff,
                        )
                    )
                    .values(status="lost", updated_at=datetime.now(timezone.utc))
                )
                result = await db.execute(stmt)
                campaign_marked = result.rowcount
                if campaign_marked > 0:
                    logger.info(
                        "Campaign %s: marked %d exhausted sequences as lost (max_steps=%d)",
                        str(campaign.id)[:8], campaign_marked, campaign_max_steps,
                    )
                    total_marked += campaign_marked

            stmt = (
                update(Outreach)
                .where(
                    and_(
                        tenant_outreach_filter,
                        Outreach.campaign_id.is_(None),
                        Outreach.outreach_sequence_step >= config.max_sequence_steps,
                        Outreach.status.in_(["cold", "contacted"]),
                        Outreach.last_email_replied_at.is_(None),
                        Outreach.last_email_sent_at.isnot(None),
                        Outreach.last_email_sent_at <= delay_cutoff,
                    )
                )
                .values(status="lost", updated_at=datetime.now(timezone.utc))
            )

            result = await db.execute(stmt)
            unbound_marked = result.rowcount
            total_marked += unbound_marked

            if unbound_marked > 0:
                logger.info(
                    "Unbound tenant %s: marked %d exhausted sequences as lost (max_steps=%d)",
                    tenant_label,
                    unbound_marked,
                    config.max_sequence_steps,
                )

        if total_marked > 0:
            logger.info("Total marked %d exhausted outreach sequences as lost", total_marked)

        await db.commit()
