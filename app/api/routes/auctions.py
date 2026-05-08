"""
Auction endpoints.

GET  /auctions                   – paginated list with filters
GET  /auctions/{id}              – full detail with property + ROI + risk flags
POST /auctions/trigger-ingestion – manually fire an ingestion run
GET  /auctions/stats             – status counts
"""
from __future__ import annotations

import uuid
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


@router.get("", response_model=list[AuctionOut])
async def list_auctions(
    status: Optional[str] = Query(default="scheduled"),
    province: Optional[str] = Query(default=None, max_length=4),
    min_roi: Optional[float] = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[AuctionOut]:
    repo = AuctionRepository(db)
    try:
        auction_status = AuctionStatus(status) if status else AuctionStatus.SCHEDULED
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    auctions = await repo.list_upcoming(
        status=auction_status,
        province=province,
        min_roi=min_roi,
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
    """
    Manually trigger an ingestion run.
    In production, use the scheduler instead.
    Accepts dry_run=true to run without hitting real endpoints.
    """
    from app.config.settings import get_settings
    import os

    if request.dry_run:
        os.environ["DRY_RUN"] = "true"

    service = IngestionService(db)
    result = await service.run(source=request.source)
    return IngestionStatusResponse(**result)
