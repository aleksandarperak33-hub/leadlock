"""
Sales Engine API — endpoints for scraping, outreach, email webhooks, and config.
Public endpoints: inbound email webhook, email event webhook, unsubscribe.
Admin endpoints: config, metrics, scrape jobs.
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from src.database import get_db
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.scrape_job import ScrapeJob
from src.models.sales_config import SalesEngineConfig
from src.api.dashboard import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sales", tags=["sales-engine"])


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

        # Update prospect
        prospect.last_email_replied_at = now
        prospect.status = "demo_scheduled"  # Escalate — a reply means interest
        prospect.updated_at = now

        logger.info(
            "Inbound reply from prospect %s (%s)",
            str(prospect.id)[:8], from_email[:20] + "***",
        )

        return {"status": "processed", "prospect_id": str(prospect.id)}

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
            elif event_type == "click" and not email_record.clicked_at:
                email_record.clicked_at = timestamp
                if outreach_id:
                    prospect = await db.get(Outreach, uuid.UUID(outreach_id))
                    if prospect:
                        prospect.last_email_clicked_at = timestamp
            elif event_type == "bounce":
                email_record.bounced_at = timestamp
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
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Manually trigger a scrape job for a specific location and trade."""
    from src.config import get_settings
    from src.services.scraping import search_local_businesses, parse_address_components
    from src.services.enrichment import find_email_hunter, guess_email_patterns, extract_domain

    settings = get_settings()
    if not settings.brave_api_key:
        raise HTTPException(status_code=400, detail="Brave API key not configured")

    city = payload.get("city", "")
    state = payload.get("state", "")
    trade = payload.get("trade_type", "general")

    if not city or not state:
        raise HTTPException(status_code=400, detail="city and state are required")

    trade_queries = {
        "hvac": "HVAC contractors",
        "plumbing": "plumbing contractors",
        "roofing": "roofing contractors",
        "electrical": "electrical contractors",
        "solar": "solar installation companies",
        "general": "home services contractors",
    }
    query = trade_queries.get(trade, f"{trade} contractors")
    location_str = f"{city}, {state}"

    # Create job record
    job = ScrapeJob(
        platform="brave",
        trade_type=trade,
        location_query=f"{query} in {location_str}",
        city=city,
        state_code=state,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(job)
    await db.flush()

    total_cost = 0.0
    new_count = 0
    dupe_count = 0

    try:
        # Search via Brave
        search_results = await search_local_businesses(query, location_str, settings.brave_api_key)
        total_cost += search_results.get("cost_usd", 0)

        all_results = search_results.get("results", [])

        for biz in all_results:
            place_id = biz.get("place_id", "")
            phone = biz.get("phone", "")

            if not place_id and not phone:
                continue

            # Dedup check
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
            domain = extract_domain(website) if website else None

            if domain and settings.hunter_api_key:
                hunter = await find_email_hunter(domain, biz["name"], settings.hunter_api_key)
                total_cost += hunter.get("cost_usd", 0)
                if hunter.get("email"):
                    email = hunter["email"]
                    email_source = "hunter"
                    email_verified = hunter.get("confidence", 0) >= 80

            if not email and domain:
                patterns = guess_email_patterns(domain)
                if patterns:
                    email = patterns[0]
                    email_source = "pattern_guess"

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

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        job.api_cost_usd = total_cost
        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")

    return {
        "status": "completed",
        "job_id": str(job.id),
        "results_found": job.results_found,
        "new_prospects": new_count,
        "duplicates": dupe_count,
        "cost_usd": round(total_cost, 3),
    }
