"""
Sales Engine — Scrape job management endpoints.
All endpoints require admin authentication.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db, async_session_factory
from src.models.outreach import Outreach
from src.models.scrape_job import ScrapeJob
from src.api.dashboard import get_current_admin
from src.services.sales_tenancy import normalize_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scrape-jobs")
async def list_scrape_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """List recent scrape jobs."""
    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    count_result = await db.execute(
        select(func.count()).select_from(ScrapeJob).where(ScrapeJob.tenant_id == tenant_id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(ScrapeJob)
        .where(ScrapeJob.tenant_id == tenant_id)
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

    # Generate job ID upfront - background task creates the DB record
    # in its own session to avoid race condition with handler's uncommitted tx
    job_id = str(uuid.uuid4())

    tenant_id = normalize_tenant_id(getattr(admin, "id", None))
    asyncio.create_task(_run_scrape_background(job_id, city, state, trade, tenant_id))

    return {
        "status": "queued",
        "job_id": job_id,
    }


async def _run_scrape_background(
    job_id: str,
    city: str,
    state: str,
    trade: str,
    tenant_id=None,
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
        variant_idx, offset = await get_next_variant_and_offset(
            db,
            tenant_id,
            city,
            state,
            trade,
        )

        if variant_idx == -1:
            # All slots exhausted - fall back to variant 0, offset 0
            variant_idx, offset = 0, 0
            logger.info("All query variants exhausted for %s in %s, restarting from beginning", trade, location_str)

        variants = get_query_variants(trade)
        query = variants[variant_idx]

        # Create job record in this session (avoids race with handler's tx)
        job = ScrapeJob(
            id=uuid.UUID(job_id),
            tenant_id=tenant_id,
            platform="brave",
            trade_type=trade,
            location_query=f"{query} in {location_str}",
            city=city,
            state_code=state,
            query_variant=variant_idx,
            search_offset=offset,
            status="running",
            started_at=datetime.now(timezone.utc),
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
                        select(Outreach).where(
                            and_(
                                Outreach.tenant_id == tenant_id,
                                Outreach.source_place_id == place_id,
                            )
                        ).limit(1)
                    )
                    if existing.scalar_one_or_none():
                        dupe_count += 1
                        continue

                if phone:
                    existing = await db.execute(
                        select(Outreach).where(
                            and_(
                                Outreach.tenant_id == tenant_id,
                                Outreach.prospect_phone == phone,
                            )
                        ).limit(1)
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
                    tenant_id=tenant_id,
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
            job.completed_at = datetime.now(timezone.utc)

            logger.info(
                "Manual scrape completed: %s in %s (variant=%d query='%s') - "
                "found=%d new=%d dupes=%d",
                trade, location_str, variant_idx, query,
                len(all_results), new_count, dupe_count,
            )

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            job.api_cost_usd = total_cost
            logger.error("Background scrape failed for %s: %s", location_str, str(e))

        await db.commit()
