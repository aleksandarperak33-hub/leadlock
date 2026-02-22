"""
Content API - CRUD endpoints for the content factory dashboard.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.content_piece import ContentPiece

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/content", tags=["content"])


@router.get("/pieces")
async def list_content_pieces(
    status: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List content pieces with optional filtering."""
    query = select(ContentPiece)

    if status:
        query = query.where(ContentPiece.status == status)
    if content_type:
        query = query.where(ContentPiece.content_type == content_type)

    query = query.order_by(ContentPiece.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    pieces = result.scalars().all()

    # Count total
    count_query = select(func.count()).select_from(ContentPiece)
    if status:
        count_query = count_query.where(ContentPiece.status == status)
    if content_type:
        count_query = count_query.where(ContentPiece.content_type == content_type)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "success": True,
        "data": [
            {
                "id": str(p.id),
                "content_type": p.content_type,
                "title": p.title,
                "body": p.body,
                "target_trade": p.target_trade,
                "target_keyword": p.target_keyword,
                "status": p.status,
                "word_count": p.word_count,
                "seo_meta": p.seo_meta,
                "ai_model": p.ai_model,
                "ai_cost_usd": p.ai_cost_usd,
                "published_url": p.published_url,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in pieces
        ],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.put("/pieces/{piece_id}/status")
async def update_content_status(
    piece_id: str,
    status: str = Query(...),
    published_url: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Update content piece status (approve, reject, publish)."""
    import uuid

    valid_statuses = {"draft", "approved", "published", "rejected"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    try:
        piece = await db.get(ContentPiece, uuid.UUID(piece_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid piece ID")

    if not piece:
        raise HTTPException(status_code=404, detail="Content piece not found")

    piece.status = status
    piece.updated_at = datetime.now(timezone.utc)
    if published_url:
        piece.published_url = published_url

    return {"success": True, "data": {"id": str(piece.id), "status": piece.status}}


@router.delete("/pieces/{piece_id}")
async def delete_content_piece(
    piece_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a content piece."""
    import uuid

    try:
        piece = await db.get(ContentPiece, uuid.UUID(piece_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid piece ID")

    if not piece:
        raise HTTPException(status_code=404, detail="Content piece not found")

    await db.delete(piece)
    return {"success": True}
