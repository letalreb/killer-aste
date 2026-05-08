"""
Property endpoints.

GET /properties             – paginated list
GET /properties/{id}        – detail with all auctions
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PropertyOut
from app.db.database import get_db
from app.db.repository import PropertyRepository

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("", response_model=list[PropertyOut])
async def list_properties(
    province: Optional[str] = Query(default=None, max_length=4),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[PropertyOut]:
    repo = PropertyRepository(db)
    if province:
        props = await repo.list_by_province(
            province=province,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
    else:
        from sqlalchemy import select
        from app.db.models import Property
        result = await db.execute(
            select(Property)
            .order_by(Property.updated_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        props = result.scalars().all()

    return [PropertyOut.model_validate(p) for p in props]


@router.get("/{property_id}", response_model=PropertyOut)
async def get_property(
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PropertyOut:
    repo = PropertyRepository(db)
    prop = await repo.get_by_id(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return PropertyOut.model_validate(prop)
