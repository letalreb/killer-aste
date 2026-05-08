"""
Repository layer — all DB access goes through here, never from routes.

Patterns:
- upsert_property / upsert_auction  → idempotent, safe to re-run
- get_* methods return None on miss (never raise 404 — that's the API layer's job)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Auction,
    AuctionStatus,
    IngestionLog,
    IngestionStatus,
    Property,
    RiskFlag,
    Valuation,
)

log = structlog.get_logger(__name__)


class PropertyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, data: dict) -> tuple[Property, bool]:
        """Insert or update by (external_id, source). Returns (property, created)."""
        stmt = (
            pg_insert(Property)
            .values(**data)
            .on_conflict_do_update(
                constraint="uq_property_external_source",
                set_={
                    k: v
                    for k, v in data.items()
                    if k not in ("id", "external_id", "source", "created_at")
                },
            )
            .returning(Property)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        created = row.created_at == row.updated_at
        return row, created

    async def get_by_external_id(
        self, external_id: str, source: str = "pvp"
    ) -> Optional[Property]:
        result = await self._session.execute(
            select(Property).where(
                Property.external_id == external_id, Property.source == source
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, property_id: uuid.UUID) -> Optional[Property]:
        result = await self._session.execute(
            select(Property).where(Property.id == property_id)
        )
        return result.scalar_one_or_none()

    async def list_by_province(
        self, province: str, limit: int = 50, offset: int = 0
    ) -> Sequence[Property]:
        result = await self._session.execute(
            select(Property)
            .where(Property.province == province.upper())
            .order_by(Property.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()


class AuctionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, data: dict) -> tuple[Auction, bool]:
        stmt = (
            pg_insert(Auction)
            .values(**data)
            .on_conflict_do_update(
                constraint="uq_auction_external_source",
                set_={
                    k: v
                    for k, v in data.items()
                    if k not in ("id", "external_id", "source", "created_at")
                },
            )
            .returning(Auction)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        created = row.created_at == row.updated_at
        return row, created

    async def get_by_external_id(
        self, external_id: str, source: str = "pvp"
    ) -> Optional[Auction]:
        result = await self._session.execute(
            select(Auction).where(
                Auction.external_id == external_id, Auction.source == source
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, auction_id: uuid.UUID) -> Optional[Auction]:
        result = await self._session.execute(
            select(Auction).where(Auction.id == auction_id)
        )
        return result.scalar_one_or_none()

    async def list_upcoming(
        self,
        status: AuctionStatus = AuctionStatus.SCHEDULED,
        province: Optional[str] = None,
        min_roi: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Auction]:
        q = (
            select(Auction)
            .join(Auction.property)
            .options(
                selectinload(Auction.property),
                selectinload(Auction.valuations),
                selectinload(Auction.risk_flags),
            )
            .where(Auction.status == status)
            .order_by(Auction.auction_date.asc())
        )
        if province:
            q = q.where(Property.province == province.upper())
        if min_roi is not None:
            q = (
                q.join(Valuation, Valuation.auction_id == Auction.id)
                .where(Valuation.roi_percentage >= min_roi)
            )
        return (await self._session.execute(q.limit(limit).offset(offset))).scalars().all()

    async def count_by_status(self) -> dict[str, int]:
        from sqlalchemy import func
        rows = await self._session.execute(
            select(Auction.status, func.count().label("n")).group_by(Auction.status)
        )
        return {row.status.value: row.n for row in rows}


class ValuationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict) -> Valuation:
        obj = Valuation(**data)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def get_by_auction(self, auction_id: uuid.UUID) -> Optional[Valuation]:
        result = await self._session.execute(
            select(Valuation)
            .where(Valuation.auction_id == auction_id)
            .order_by(Valuation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_for_auction(self, auction_id: uuid.UUID) -> Optional[Valuation]:
        return await self.get_by_auction(auction_id)

    async def update(self, valuation_id: uuid.UUID, data: dict) -> None:
        payload = {k: v for k, v in data.items() if k not in ("id", "auction_id", "created_at")}
        await self._session.execute(
            update(Valuation).where(Valuation.id == valuation_id).values(**payload)
        )


class RiskFlagRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_bulk(self, flags: list[dict]) -> list[RiskFlag]:
        objs = [RiskFlag(**f) for f in flags]
        self._session.add_all(objs)
        await self._session.flush()
        return objs

    async def get_for_auction(self, auction_id: uuid.UUID) -> Sequence[RiskFlag]:
        result = await self._session.execute(
            select(RiskFlag)
            .where(RiskFlag.auction_id == auction_id)
            .order_by(RiskFlag.severity.desc())
        )
        return result.scalars().all()

    async def delete_by_auction(self, auction_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(RiskFlag).where(RiskFlag.auction_id == auction_id)
        )


class IngestionLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict) -> IngestionLog:
        obj = IngestionLog(**data)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def complete(
        self,
        log_id: uuid.UUID,
        *,
        status: IngestionStatus,
        pages_fetched: int,
        records_found: int,
        records_inserted: int,
        records_updated: int,
        errors_count: int,
        requests_made: int,
        error_detail: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        await self._session.execute(
            update(IngestionLog)
            .where(IngestionLog.id == log_id)
            .values(
                status=status,
                completed_at=datetime.now(timezone.utc),
                pages_fetched=pages_fetched,
                records_found=records_found,
                records_inserted=records_inserted,
                records_updated=records_updated,
                errors_count=errors_count,
                requests_made=requests_made,
                error_detail=error_detail,
                extra=metadata,
            )
        )

    async def get_last_successful(self, source: str) -> Optional[IngestionLog]:
        result = await self._session.execute(
            select(IngestionLog)
            .where(
                IngestionLog.source == source,
                IngestionLog.status == IngestionStatus.COMPLETED,
            )
            .order_by(IngestionLog.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_cursor(self, source: str) -> int:
        """Return the page number where the last run stopped (0 = start from beginning)."""
        result = await self._session.execute(
            select(IngestionLog)
            .where(
                IngestionLog.source == source,
                IngestionLog.status.in_(
                    [IngestionStatus.COMPLETED, IngestionStatus.DRY_RUN]
                ),
            )
            .order_by(IngestionLog.completed_at.desc())
            .limit(1)
        )
        log = result.scalar_one_or_none()
        if not log or not log.extra:
            return 0
        return int(log.extra.get("next_page", 0))
