"""
Channel scripts API - list, copy, and mark-sent endpoints for dashboard.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.channel_script import ChannelScript

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/channel-scripts", tags=["channel_scripts"])


@router.get("/")
async def list_channel_scripts(
    channel: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    outreach_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List channel scripts with optional filtering."""
    query = select(ChannelScript)

    if channel:
        query = query.where(ChannelScript.channel == channel)
    if status:
        query = query.where(ChannelScript.status == status)
    if outreach_id:
        try:
            query = query.where(ChannelScript.outreach_id == uuid.UUID(outreach_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid outreach_id")

    query = query.order_by(ChannelScript.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    scripts = result.scalars().all()

    count_query = select(func.count()).select_from(ChannelScript)
    if channel:
        count_query = count_query.where(ChannelScript.channel == channel)
    if status:
        count_query = count_query.where(ChannelScript.status == status)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "success": True,
        "data": [
            {
                "id": str(s.id),
                "outreach_id": str(s.outreach_id),
                "channel": s.channel,
                "script_text": s.script_text,
                "status": s.status,
                "sent_at": s.sent_at.isoformat() if s.sent_at else None,
                "ai_cost_usd": s.ai_cost_usd,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in scripts
        ],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.put("/{script_id}/sent")
async def mark_script_sent(
    script_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Mark a channel script as sent."""
    try:
        script = await db.get(ChannelScript, uuid.UUID(script_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid script ID")

    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    script.status = "sent"
    script.sent_at = datetime.now(timezone.utc)

    return {"success": True, "data": {"id": str(script.id), "status": "sent"}}


@router.put("/{script_id}/skip")
async def skip_script(
    script_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Mark a channel script as skipped."""
    try:
        script = await db.get(ChannelScript, uuid.UUID(script_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid script ID")

    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    script.status = "skipped"

    return {"success": True, "data": {"id": str(script.id), "status": "skipped"}}
