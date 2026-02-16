"""
Sales Engine API — endpoints for scraping, outreach, email webhooks, and config.
Public endpoints: inbound email webhook, email event webhook, unsubscribe.
Admin endpoints: config, metrics, scrape jobs, prospects, email threads, blacklist.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc

from src.database import get_db, async_session_factory
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.scrape_job import ScrapeJob
from src.models.sales_config import SalesEngineConfig
from src.models.email_blacklist import EmailBlacklist
from src.api.dashboard import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sales", tags=["sales-engine"])


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

    # Check quiet hours — if outside, queue for later via task queue
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


# === PUBLIC ENDPOINTS (webhooks, unsubscribe) ===

@router.post("/inbound-email")
async def inbound_email_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    SendGrid Inbound Parse webhook — handles email replies from prospects.
    When a prospect replies, update their outreach record and record the email.
    """
    try:
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

        now = datetime.utcnow()

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
        # auto_reply / out_of_office → no status change

        # Record learning signal for reply
        if classification in ("interested", "rejection"):
            signal_value = 1.0 if classification == "interested" else 0.0
            await _record_email_signal(
                "email_replied", prospect, email_record, signal_value,
            )

        # SMS follow-up for interested prospects (Phase 4)
        sms_sent = False
        if classification == "interested":
            try:
                sms_sent = await _trigger_sms_followup(db, prospect)
            except Exception as sms_err:
                logger.warning(
                    "SMS follow-up trigger failed for %s: %s",
                    str(prospect.id)[:8], str(sms_err),
                )

        logger.info(
            "Inbound reply from prospect %s (%s) classified=%s sms=%s",
            str(prospect.id)[:8], from_email[:20] + "***",
            classification, sms_sent,
        )

        return {
            "status": "processed",
            "prospect_id": str(prospect.id),
            "classification": classification,
            "sms_sent": sms_sent,
        }

    except Exception as e:
        logger.error("Inbound email processing error: %s", str(e))
        return {"status": "error", "detail": str(e)}


@router.post("/email-events")
async def email_events_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    SendGrid Event Webhook — tracks opens, clicks, bounces, etc.
    Events are matched by sendgrid_message_id or custom args.
    """
    try:
        events = await request.json()
        if not isinstance(events, list):
            events = [events]

        for event in events:
            event_type = event.get("event", "")
            sg_message_id = event.get("sg_message_id", "").split(".")[0]
            outreach_id = event.get("outreach_id")
            timestamp = datetime.utcfromtimestamp(event.get("timestamp", 0))

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

            # Update email record based on event type
            if event_type == "delivered" and not email_record.delivered_at:
                email_record.delivered_at = timestamp
            elif event_type == "open" and not email_record.opened_at:
                email_record.opened_at = timestamp
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
                if outreach_id:
                    prospect = await db.get(Outreach, uuid.UUID(outreach_id))
                    if prospect:
                        prospect.last_email_clicked_at = timestamp
                        await _record_email_signal(
                            "email_clicked", prospect, email_record, 1.0,
                        )
            elif event_type in ("bounce", "blocked", "deferred"):
                email_record.bounced_at = timestamp
                email_record.bounce_type = event.get("type", event_type)
                email_record.bounce_reason = event.get("reason", "")
                # Hard bounce → mark prospect as lost, flag email invalid
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
            elif event_type == "spamreport":
                # Treat spam report as unsubscribe
                if outreach_id:
                    prospect = await db.get(Outreach, uuid.UUID(outreach_id))
                    if prospect:
                        prospect.email_unsubscribed = True
                        prospect.unsubscribed_at = timestamp

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
        prospect = await db.get(Outreach, uuid.UUID(prospect_id))
        if prospect:
            prospect.email_unsubscribed = True
            prospect.unsubscribed_at = datetime.utcnow()
            prospect.updated_at = datetime.utcnow()
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


# === ADMIN ENDPOINTS ===

@router.get("/config")
async def get_sales_config(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get sales engine configuration."""
    result = await db.execute(select(SalesEngineConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        # Create default config
        config = SalesEngineConfig()
        db.add(config)
        await db.flush()

    return {
        "id": str(config.id),
        "is_active": config.is_active,
        "target_trade_types": config.target_trade_types or [],
        "target_locations": config.target_locations or [],
        "daily_email_limit": config.daily_email_limit,
        "daily_scrape_limit": config.daily_scrape_limit,
        "sequence_delay_hours": config.sequence_delay_hours,
        "max_sequence_steps": config.max_sequence_steps,
        "from_email": config.from_email,
        "from_name": config.from_name,
        "reply_to_email": config.reply_to_email,
        "company_address": config.company_address,
        "sms_after_email_reply": config.sms_after_email_reply,
        "sms_from_phone": config.sms_from_phone,
        "email_templates": config.email_templates,
        "scraper_interval_minutes": config.scraper_interval_minutes,
        "variant_cooldown_days": config.variant_cooldown_days,
        "send_hours_start": config.send_hours_start,
        "send_hours_end": config.send_hours_end,
        "send_timezone": config.send_timezone,
        "send_weekdays_only": config.send_weekdays_only,
        "scraper_paused": config.scraper_paused,
        "sequencer_paused": config.sequencer_paused,
        "cleanup_paused": config.cleanup_paused,
        "monthly_budget_usd": config.monthly_budget_usd,
        "budget_alert_threshold": config.budget_alert_threshold,
    }


@router.put("/config")
async def update_sales_config(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Update sales engine configuration."""
    result = await db.execute(select(SalesEngineConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        config = SalesEngineConfig()
        db.add(config)
        await db.flush()

    allowed_fields = [
        "is_active", "target_trade_types", "target_locations",
        "daily_email_limit", "daily_scrape_limit", "sequence_delay_hours",
        "max_sequence_steps", "from_email", "from_name", "reply_to_email",
        "company_address", "sms_after_email_reply", "sms_from_phone",
        "email_templates",
        "scraper_interval_minutes", "variant_cooldown_days",
        "send_hours_start", "send_hours_end", "send_timezone", "send_weekdays_only",
        "scraper_paused", "sequencer_paused", "cleanup_paused",
        "monthly_budget_usd", "budget_alert_threshold",
    ]

    for field in allowed_fields:
        if field in payload:
            setattr(config, field, payload[field])

    config.updated_at = datetime.utcnow()
    await db.flush()

    return {"status": "updated"}


@router.get("/metrics")
async def get_sales_metrics(
    period: str = Query(default="30d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Sales engine performance metrics."""
    days = int(period.replace("d", ""))
    since = datetime.utcnow() - timedelta(days=days)

    # Prospect counts by status
    status_counts = {}
    status_result = await db.execute(
        select(Outreach.status, func.count()).where(
            Outreach.source.isnot(None)  # Only engine-sourced prospects
        ).group_by(Outreach.status)
    )
    for status, count in status_result.all():
        status_counts[status] = count

    # Email metrics
    email_stats = await db.execute(
        select(
            func.count().label("total_sent"),
            func.count(OutreachEmail.opened_at).label("opened"),
            func.count(OutreachEmail.clicked_at).label("clicked"),
            func.count(OutreachEmail.bounced_at).label("bounced"),
        ).where(
            and_(
                OutreachEmail.direction == "outbound",
                OutreachEmail.sent_at >= since,
            )
        )
    )
    email_row = email_stats.one()
    total_sent = email_row.total_sent or 0
    opened = email_row.opened or 0
    clicked = email_row.clicked or 0

    # Reply count
    reply_result = await db.execute(
        select(func.count()).select_from(OutreachEmail).where(
            and_(
                OutreachEmail.direction == "inbound",
                OutreachEmail.sent_at >= since,
            )
        )
    )
    replies = reply_result.scalar() or 0

    # Total cost
    cost_result = await db.execute(
        select(func.coalesce(func.sum(Outreach.total_cost_usd), 0.0)).where(
            Outreach.source.isnot(None)
        )
    )
    total_cost = cost_result.scalar() or 0.0

    # Scrape job stats
    scrape_result = await db.execute(
        select(
            func.count().label("total_jobs"),
            func.coalesce(func.sum(ScrapeJob.new_prospects_created), 0).label("total_scraped"),
            func.coalesce(func.sum(ScrapeJob.api_cost_usd), 0.0).label("scrape_cost"),
        ).where(ScrapeJob.created_at >= since)
    )
    scrape_row = scrape_result.one()

    return {
        "period": period,
        "prospects": {
            "total": sum(status_counts.values()),
            "by_status": status_counts,
        },
        "emails": {
            "sent": total_sent,
            "opened": opened,
            "clicked": clicked,
            "bounced": email_row.bounced or 0,
            "replied": replies,
            "open_rate": round(opened / total_sent * 100, 1) if total_sent else 0,
            "reply_rate": round(replies / total_sent * 100, 1) if total_sent else 0,
        },
        "scraping": {
            "jobs_run": scrape_row.total_jobs,
            "prospects_found": scrape_row.total_scraped,
            "scrape_cost": round(float(scrape_row.scrape_cost), 2),
        },
        "cost": {
            "total": round(float(total_cost), 2),
        },
        "conversions": {
            "demos_booked": status_counts.get("demo_scheduled", 0),
            "won": status_counts.get("won", 0),
        },
    }


@router.get("/scrape-jobs")
async def list_scrape_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """List recent scrape jobs."""
    count_result = await db.execute(
        select(func.count()).select_from(ScrapeJob)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(ScrapeJob)
        .order_by(desc(ScrapeJob.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    jobs = result.scalars().all()

    return {
        "jobs": [
            {
                "id": str(j.id),
                "platform": j.platform,
                "trade_type": j.trade_type,
                "location_query": j.location_query,
                "city": j.city,
                "state_code": j.state_code,
                "status": j.status,
                "results_found": j.results_found,
                "new_prospects_created": j.new_prospects_created,
                "duplicates_skipped": j.duplicates_skipped,
                "api_cost_usd": j.api_cost_usd,
                "error_message": j.error_message,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.post("/scrape-jobs")
async def trigger_scrape_job(
    payload: dict,
    admin=Depends(get_current_admin),
):
    """Manually trigger a scrape job. Returns immediately, runs in background.
    Automatically picks the next query variant + offset to avoid repeat results.
    """
    from src.config import get_settings

    settings = get_settings()
    if not settings.brave_api_key:
        raise HTTPException(status_code=400, detail="Brave API key not configured")

    city = payload.get("city", "")
    state = payload.get("state", "")
    trade = payload.get("trade_type", "general")

    if not city or not state:
        raise HTTPException(status_code=400, detail="city and state are required")

    # Generate job ID upfront — background task creates the DB record
    # in its own session to avoid race condition with handler's uncommitted tx
    job_id = str(uuid.uuid4())

    asyncio.create_task(_run_scrape_background(job_id, city, state, trade))

    return {
        "status": "queued",
        "job_id": job_id,
    }


async def _run_scrape_background(
    job_id: str,
    city: str,
    state: str,
    trade: str,
) -> None:
    """Background task to run a manual scrape job with auto query rotation."""
    from src.config import get_settings
    from src.services.scraping import search_local_businesses, parse_address_components
    from src.services.enrichment import enrich_prospect_email, extract_domain
    from src.services.phone_validation import normalize_phone
    from src.utils.email_validation import validate_email
    from src.workers.scraper import get_next_variant_and_offset, get_query_variants

    settings = get_settings()
    location_str = f"{city}, {state}"
    total_cost = 0.0
    new_count = 0
    dupe_count = 0

    async with async_session_factory() as db:
        # Pick next unused query variant + offset for this location+trade
        variant_idx, offset = await get_next_variant_and_offset(db, city, state, trade)

        if variant_idx == -1:
            # All slots exhausted — fall back to variant 0, offset 0
            variant_idx, offset = 0, 0
            logger.info("All query variants exhausted for %s in %s, restarting from beginning", trade, location_str)

        variants = get_query_variants(trade)
        query = variants[variant_idx]

        # Create job record in this session (avoids race with handler's tx)
        job = ScrapeJob(
            id=uuid.UUID(job_id),
            platform="brave",
            trade_type=trade,
            location_query=f"{query} in {location_str}",
            city=city,
            state_code=state,
            query_variant=variant_idx,
            search_offset=offset,
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(job)
        await db.flush()

        try:
            search_results = await search_local_businesses(
                query, location_str, settings.brave_api_key,
            )
            total_cost += search_results.get("cost_usd", 0)
            all_results = search_results.get("results", [])

            for biz in all_results:
                place_id = biz.get("place_id", "")
                raw_phone = biz.get("phone", "")
                phone = normalize_phone(raw_phone) if raw_phone else ""

                if not place_id and not phone:
                    continue

                if place_id:
                    existing = await db.execute(
                        select(Outreach).where(Outreach.source_place_id == place_id).limit(1)
                    )
                    if existing.scalar_one_or_none():
                        dupe_count += 1
                        continue

                if phone:
                    existing = await db.execute(
                        select(Outreach).where(Outreach.prospect_phone == phone).limit(1)
                    )
                    if existing.scalar_one_or_none():
                        dupe_count += 1
                        continue

                addr_parts = parse_address_components(biz.get("address", ""))

                email = None
                email_source = None
                email_verified = False
                website = biz.get("website", "")

                if website:
                    enrichment = await enrich_prospect_email(website, biz.get("name", ""))
                    if enrichment.get("email"):
                        email = enrichment["email"]
                        email_source = enrichment["source"]
                        email_verified = enrichment.get("verified", False)

                if email:
                    email_check = await validate_email(email)
                    if not email_check["valid"]:
                        email = None
                        email_source = None
                        email_verified = False

                prospect = Outreach(
                    prospect_name=biz.get("name", "Unknown"),
                    prospect_company=biz.get("name"),
                    prospect_email=email,
                    prospect_phone=phone,
                    prospect_trade_type=trade,
                    status="cold",
                    source="brave",
                    source_place_id=place_id if place_id else None,
                    website=website,
                    google_rating=biz.get("rating"),
                    review_count=biz.get("reviews"),
                    address=biz.get("address"),
                    city=addr_parts.get("city") or city,
                    state_code=addr_parts.get("state") or state,
                    zip_code=addr_parts.get("zip"),
                    email_verified=email_verified,
                    email_source=email_source,
                    outreach_sequence_step=0,
                )
                db.add(prospect)
                new_count += 1

            job.status = "completed"
            job.results_found = len(all_results)
            job.new_prospects_created = new_count
            job.duplicates_skipped = dupe_count
            job.api_cost_usd = total_cost
            job.completed_at = datetime.utcnow()

            logger.info(
                "Manual scrape completed: %s in %s (variant=%d query='%s') — "
                "found=%d new=%d dupes=%d",
                trade, location_str, variant_idx, query,
                len(all_results), new_count, dupe_count,
            )

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            job.api_cost_usd = total_cost
            logger.error("Background scrape failed for %s: %s", location_str, str(e))

        await db.commit()


# === PROSPECT ENDPOINTS ===

def _serialize_prospect(p: Outreach) -> dict:
    """Serialize an Outreach record to a JSON-friendly dict."""
    return {
        "id": str(p.id),
        "prospect_name": p.prospect_name,
        "prospect_company": p.prospect_company,
        "prospect_email": p.prospect_email,
        "prospect_phone": p.prospect_phone,
        "prospect_trade_type": p.prospect_trade_type,
        "status": p.status,
        "source": p.source,
        "website": p.website,
        "google_rating": p.google_rating,
        "review_count": p.review_count,
        "address": p.address,
        "city": p.city,
        "state_code": p.state_code,
        "email_verified": p.email_verified,
        "email_source": p.email_source,
        "outreach_sequence_step": p.outreach_sequence_step,
        "total_emails_sent": p.total_emails_sent,
        "total_cost_usd": p.total_cost_usd,
        "email_unsubscribed": p.email_unsubscribed,
        "last_email_sent_at": p.last_email_sent_at.isoformat() if p.last_email_sent_at else None,
        "last_email_opened_at": p.last_email_opened_at.isoformat() if p.last_email_opened_at else None,
        "last_email_replied_at": p.last_email_replied_at.isoformat() if p.last_email_replied_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/prospects")
async def list_prospects(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    trade_type: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """List prospects with pagination and filters."""
    conditions = []
    if status:
        conditions.append(Outreach.status == status)
    if trade_type:
        conditions.append(Outreach.prospect_trade_type == trade_type)
    if search:
        search_term = f"%{search}%"
        conditions.append(
            or_(
                Outreach.prospect_name.ilike(search_term),
                Outreach.prospect_company.ilike(search_term),
                Outreach.prospect_email.ilike(search_term),
                Outreach.city.ilike(search_term),
            )
        )

    where_clause = and_(*conditions) if conditions else True

    count_result = await db.execute(
        select(func.count()).select_from(Outreach).where(where_clause)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Outreach)
        .where(where_clause)
        .order_by(desc(Outreach.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    prospects = result.scalars().all()

    return {
        "prospects": [_serialize_prospect(p) for p in prospects],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/prospects/{prospect_id}")
async def get_prospect(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get single prospect detail."""
    prospect = await db.get(Outreach, uuid.UUID(prospect_id))
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return _serialize_prospect(prospect)


@router.put("/prospects/{prospect_id}")
async def update_prospect(
    prospect_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Edit a prospect."""
    prospect = await db.get(Outreach, uuid.UUID(prospect_id))
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    allowed_fields = [
        "prospect_name", "prospect_company", "prospect_email",
        "prospect_phone", "prospect_trade_type", "status", "notes",
        "estimated_mrr", "website", "city", "state_code",
    ]
    for field in allowed_fields:
        if field in payload:
            setattr(prospect, field, payload[field])

    prospect.updated_at = datetime.utcnow()
    await db.flush()
    return _serialize_prospect(prospect)


@router.delete("/prospects/{prospect_id}")
async def delete_prospect(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Delete a prospect and all related emails."""
    prospect = await db.get(Outreach, uuid.UUID(prospect_id))
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    await db.delete(prospect)
    return {"status": "deleted"}


@router.post("/prospects")
async def create_prospect(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Manually add a prospect."""
    name = payload.get("prospect_name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="prospect_name is required")

    prospect = Outreach(
        prospect_name=name,
        prospect_company=payload.get("prospect_company"),
        prospect_email=payload.get("prospect_email"),
        prospect_phone=payload.get("prospect_phone"),
        prospect_trade_type=payload.get("prospect_trade_type", "general"),
        status="cold",
        source="manual",
        website=payload.get("website"),
        city=payload.get("city"),
        state_code=payload.get("state_code"),
        outreach_sequence_step=0,
    )
    db.add(prospect)
    await db.flush()
    return _serialize_prospect(prospect)


@router.post("/prospects/{prospect_id}/blacklist")
async def blacklist_prospect(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Blacklist a prospect's email and domain."""
    prospect = await db.get(Outreach, uuid.UUID(prospect_id))
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    entries_added = []

    if prospect.prospect_email:
        email = prospect.prospect_email.lower().strip()
        # Blacklist email
        existing = await db.execute(
            select(EmailBlacklist).where(EmailBlacklist.value == email).limit(1)
        )
        if not existing.scalar_one_or_none():
            db.add(EmailBlacklist(
                entry_type="email",
                value=email,
                reason=f"Blacklisted from prospect {prospect_id[:8]}",
            ))
            entries_added.append(email)

        # Blacklist domain
        domain = email.split("@")[1] if "@" in email else None
        if domain:
            existing = await db.execute(
                select(EmailBlacklist).where(EmailBlacklist.value == domain).limit(1)
            )
            if not existing.scalar_one_or_none():
                db.add(EmailBlacklist(
                    entry_type="domain",
                    value=domain,
                    reason=f"Blacklisted from prospect {prospect_id[:8]}",
                ))
                entries_added.append(domain)

    # Mark prospect as unsubscribed and lost
    prospect.email_unsubscribed = True
    prospect.unsubscribed_at = datetime.utcnow()
    prospect.status = "lost"
    prospect.updated_at = datetime.utcnow()

    return {"status": "blacklisted", "entries": entries_added}


# === EMAIL THREAD ENDPOINTS ===

@router.get("/prospects/{prospect_id}/emails")
async def get_prospect_emails(
    prospect_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get all emails (outbound + inbound) for a prospect."""
    prospect = await db.get(Outreach, uuid.UUID(prospect_id))
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    result = await db.execute(
        select(OutreachEmail)
        .where(OutreachEmail.outreach_id == prospect.id)
        .order_by(OutreachEmail.sent_at.asc())
    )
    emails = result.scalars().all()

    return {
        "emails": [
            {
                "id": str(e.id),
                "direction": e.direction,
                "subject": e.subject,
                "body_html": e.body_html,
                "body_text": e.body_text,
                "from_email": e.from_email,
                "to_email": e.to_email,
                "sequence_step": e.sequence_step,
                "sendgrid_message_id": e.sendgrid_message_id,
                "sent_at": e.sent_at.isoformat() if e.sent_at else None,
                "delivered_at": e.delivered_at.isoformat() if e.delivered_at else None,
                "opened_at": e.opened_at.isoformat() if e.opened_at else None,
                "clicked_at": e.clicked_at.isoformat() if e.clicked_at else None,
                "bounced_at": e.bounced_at.isoformat() if e.bounced_at else None,
                "bounce_type": e.bounce_type,
                "bounce_reason": e.bounce_reason,
            }
            for e in emails
        ],
        "total": len(emails),
    }


# === WORKER STATUS ENDPOINT (Phase 4) ===

@router.get("/worker-status")
async def get_worker_status(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get worker health status from Redis heartbeats."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()

        workers = ["scraper", "outreach_sequencer", "outreach_cleanup", "health_monitor", "task_processor"]
        status = {}

        for name in workers:
            key = f"leadlock:worker_health:{name}"
            heartbeat = await redis.get(key)
            if heartbeat:
                last_beat = datetime.fromisoformat(heartbeat.decode() if isinstance(heartbeat, bytes) else heartbeat)
                age_seconds = (datetime.utcnow() - last_beat).total_seconds()
                health = "healthy" if age_seconds < 600 else ("warning" if age_seconds < 1800 else "unhealthy")
                status[name] = {
                    "last_heartbeat": last_beat.isoformat(),
                    "age_seconds": int(age_seconds),
                    "health": health,
                }
            else:
                status[name] = {
                    "last_heartbeat": None,
                    "age_seconds": None,
                    "health": "unknown",
                }

        # Bounce rate check
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_result = await db.execute(
            select(func.count()).select_from(OutreachEmail).where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sent_at >= today_start,
                )
            )
        )
        sent_today = sent_result.scalar() or 0

        bounced_result = await db.execute(
            select(func.count()).select_from(OutreachEmail).where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.bounced_at.isnot(None),
                    OutreachEmail.sent_at >= today_start,
                )
            )
        )
        bounced_today = bounced_result.scalar() or 0

        bounce_rate = round(bounced_today / sent_today * 100, 1) if sent_today else 0.0

        return {
            "workers": status,
            "alerts": {
                "bounce_rate": bounce_rate,
                "bounce_rate_alert": bounce_rate > 10,
            },
        }
    except Exception as e:
        logger.error("Worker status check failed: %s", str(e))
        return {"workers": {}, "alerts": {}, "error": str(e)}


# === WORKER CONTROLS (Phase 3) ===

@router.post("/workers/{worker_name}/pause")
async def pause_worker(
    worker_name: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Pause a worker by name."""
    valid_workers = {"scraper": "scraper_paused", "sequencer": "sequencer_paused", "cleanup": "cleanup_paused"}
    field = valid_workers.get(worker_name)
    if not field:
        raise HTTPException(status_code=400, detail=f"Unknown worker: {worker_name}")

    result = await db.execute(select(SalesEngineConfig).limit(1))
    config = result.scalar_one_or_none()
    if config and hasattr(config, field):
        setattr(config, field, True)
        config.updated_at = datetime.utcnow()
    return {"status": "paused", "worker": worker_name}


@router.post("/workers/{worker_name}/resume")
async def resume_worker(
    worker_name: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Resume a paused worker."""
    valid_workers = {"scraper": "scraper_paused", "sequencer": "sequencer_paused", "cleanup": "cleanup_paused"}
    field = valid_workers.get(worker_name)
    if not field:
        raise HTTPException(status_code=400, detail=f"Unknown worker: {worker_name}")

    result = await db.execute(select(SalesEngineConfig).limit(1))
    config = result.scalar_one_or_none()
    if config and hasattr(config, field):
        setattr(config, field, False)
        config.updated_at = datetime.utcnow()
    return {"status": "resumed", "worker": worker_name}


# === CAMPAIGNS (Phase 3) ===

@router.get("/campaigns")
async def list_campaigns(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """List campaigns with pagination."""
    from src.models.campaign import Campaign

    count_result = await db.execute(select(func.count()).select_from(Campaign))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Campaign)
        .order_by(desc(Campaign.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    campaigns = result.scalars().all()

    return {
        "campaigns": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "status": c.status,
                "target_trades": c.target_trades or [],
                "target_locations": c.target_locations or [],
                "sequence_steps": c.sequence_steps or [],
                "daily_limit": c.daily_limit,
                "total_sent": c.total_sent,
                "total_opened": c.total_opened,
                "total_replied": c.total_replied,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in campaigns
        ],
        "total": total,
        "page": page,
    }


@router.post("/campaigns")
async def create_campaign(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Create a new campaign."""
    from src.models.campaign import Campaign

    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    campaign = Campaign(
        name=name,
        description=payload.get("description"),
        status="draft",
        target_trades=payload.get("target_trades", []),
        target_locations=payload.get("target_locations", []),
        target_filters=payload.get("target_filters", {}),
        sequence_steps=payload.get("sequence_steps", []),
        daily_limit=payload.get("daily_limit", 25),
    )
    db.add(campaign)
    await db.flush()
    return {"status": "created", "id": str(campaign.id)}


@router.put("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Update a campaign."""
    from src.models.campaign import Campaign

    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    allowed = ["name", "description", "target_trades", "target_locations", "target_filters", "sequence_steps", "daily_limit"]
    for field in allowed:
        if field in payload:
            setattr(campaign, field, payload[field])

    campaign.updated_at = datetime.utcnow()
    return {"status": "updated"}


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Pause an active campaign."""
    from src.models.campaign import Campaign

    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "paused"
    campaign.updated_at = datetime.utcnow()
    return {"status": "paused"}


@router.post("/campaigns/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Resume a paused campaign."""
    from src.models.campaign import Campaign

    campaign = await db.get(Campaign, uuid.UUID(campaign_id))
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "active"
    campaign.updated_at = datetime.utcnow()
    return {"status": "active"}


# === TEMPLATES (Phase 3) ===

@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """List all email templates."""
    from src.models.email_template import EmailTemplate

    result = await db.execute(
        select(EmailTemplate).order_by(EmailTemplate.created_at)
    )
    templates = result.scalars().all()

    return {
        "templates": [
            {
                "id": str(t.id),
                "name": t.name,
                "step_type": t.step_type,
                "subject_template": t.subject_template,
                "body_template": t.body_template,
                "ai_instructions": t.ai_instructions,
                "is_ai_generated": t.is_ai_generated,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in templates
        ],
    }


@router.post("/templates")
async def create_template(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Create an email template."""
    from src.models.email_template import EmailTemplate

    name = payload.get("name", "").strip()
    step_type = payload.get("step_type", "").strip()
    if not name or not step_type:
        raise HTTPException(status_code=400, detail="name and step_type are required")

    template = EmailTemplate(
        name=name,
        step_type=step_type,
        subject_template=payload.get("subject_template"),
        body_template=payload.get("body_template"),
        ai_instructions=payload.get("ai_instructions"),
        is_ai_generated=payload.get("is_ai_generated", True),
    )
    db.add(template)
    await db.flush()
    return {"status": "created", "id": str(template.id)}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Update an email template."""
    from src.models.email_template import EmailTemplate

    template = await db.get(EmailTemplate, uuid.UUID(template_id))
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    allowed = ["name", "step_type", "subject_template", "body_template", "ai_instructions", "is_ai_generated"]
    for field in allowed:
        if field in payload:
            setattr(template, field, payload[field])

    return {"status": "updated"}


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Delete an email template."""
    from src.models.email_template import EmailTemplate

    template = await db.get(EmailTemplate, uuid.UUID(template_id))
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(template)
    return {"status": "deleted"}


# === INSIGHTS (Phase 3) ===

@router.get("/insights")
async def get_insights(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Get learning insights summary for the dashboard."""
    from src.services.learning import get_insights_summary
    return await get_insights_summary()


# === BULK OPERATIONS (Phase 3) ===

@router.post("/prospects/bulk")
async def bulk_update_prospects(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Bulk operations on prospects: status change, delete, assign to campaign."""
    prospect_ids = payload.get("prospect_ids", [])
    action = payload.get("action", "")

    if not prospect_ids or not action:
        raise HTTPException(status_code=400, detail="prospect_ids and action are required")

    if len(prospect_ids) > 200:
        raise HTTPException(status_code=400, detail="Maximum 200 prospects per bulk operation")

    updated = 0
    for pid in prospect_ids:
        try:
            prospect = await db.get(Outreach, uuid.UUID(pid))
            if not prospect:
                continue

            if action == "delete":
                await db.delete(prospect)
            elif action.startswith("status:"):
                new_status = action.split(":")[1]
                prospect.status = new_status
                prospect.updated_at = datetime.utcnow()
            elif action.startswith("campaign:"):
                campaign_id = action.split(":")[1]
                prospect.campaign_id = uuid.UUID(campaign_id)
                prospect.updated_at = datetime.utcnow()

            updated += 1
        except Exception as e:
            logger.warning("Bulk op failed for %s: %s", pid[:8], str(e))

    return {"status": "completed", "updated": updated, "total": len(prospect_ids)}
