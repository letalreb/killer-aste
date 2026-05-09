"""
Auction endpoints.

GET  /auctions                   – paginated list with server-side filters
GET  /auctions/{id}              – full detail with property + ROI + risk flags
POST /auctions/trigger-ingestion – manually fire an ingestion run (deprecated: use admin route)
GET  /auctions/stats             – status counts
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AuctionOut,
    IngestionStatusResponse,
    IngestionTriggerRequest,
)
from app.db.database import get_db
from app.db.models import AuctionStatus
from app.db.repository import AuctionRepository
from app.ingestion.ingestion_service import IngestionService

router = APIRouter(prefix="/auctions", tags=["auctions"])

_SORT_VALUES = {"date", "roi", "price", "score"}
_RISK_VALUES = {"all", "low", "medium", "high"}


@router.get("", response_model=list[AuctionOut])
async def list_auctions(
    status: Optional[str] = Query(default="scheduled"),
    province: Optional[str] = Query(default=None, max_length=4),
    city: Optional[str] = Query(default=None, max_length=128),
    min_roi: Optional[float] = Query(default=None, ge=0),
    min_price: Optional[float] = Query(default=None, ge=0),
    max_price: Optional[float] = Query(default=None, ge=0),
    max_risk_grade: Optional[str] = Query(default=None),
    sort_by: str = Query(default="date"),
    days_ahead: Optional[int] = Query(default=30, ge=1, le=3650),
    show_past: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[AuctionOut]:
    if sort_by not in _SORT_VALUES:
        raise HTTPException(status_code=400, detail=f"Invalid sort_by: {sort_by}")
    if max_risk_grade and max_risk_grade not in _RISK_VALUES:
        raise HTTPException(status_code=400, detail=f"Invalid max_risk_grade: {max_risk_grade}")

    repo = AuctionRepository(db)
    try:
        auction_status = AuctionStatus(status) if status else AuctionStatus.SCHEDULED
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    now = datetime.now(timezone.utc)
    auction_date_from = None if show_past else now
    auction_date_to = (now + timedelta(days=days_ahead)) if (not show_past and days_ahead) else None

    auctions = await repo.list_upcoming(
        status=auction_status,
        province=province,
        city=city,
        min_roi=min_roi,
        min_price=min_price,
        max_price=max_price,
        max_risk_grade=max_risk_grade,
        sort_by=sort_by,
        auction_date_from=auction_date_from,
        auction_date_to=auction_date_to,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return [AuctionOut.model_validate(a) for a in auctions]


@router.get("/stats")
async def auction_stats(db: AsyncSession = Depends(get_db)) -> dict:
    repo = AuctionRepository(db)
    return await repo.count_by_status()


@router.get("/{auction_id}", response_model=AuctionOut)
async def get_auction(
    auction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AuctionOut:
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.db.models import Auction

    result = await db.execute(
        select(Auction)
        .options(
            selectinload(Auction.property),
            selectinload(Auction.valuations),
            selectinload(Auction.risk_flags),
        )
        .where(Auction.id == auction_id)
    )
    auction = result.scalar_one_or_none()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    return AuctionOut.model_validate(auction)


@router.post(
    "/trigger-ingestion",
    response_model=IngestionStatusResponse,
    status_code=202,
)
async def trigger_ingestion(
    request: IngestionTriggerRequest,
    db: AsyncSession = Depends(get_db),
) -> IngestionStatusResponse:
    import os
    if request.dry_run:
        os.environ["DRY_RUN"] = "true"
    service = IngestionService(db)
    result = await service.run(source=request.source)
    return IngestionStatusResponse(**result)
