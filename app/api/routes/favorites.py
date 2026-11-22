"""
Favorites (server-side).

GET    /favorites               – the user's favorites + their limit
PUT    /favorites/{auction_id}  – add (idempotent); 409 when the limit is reached
DELETE /favorites/{auction_id}  – remove (idempotent)
DELETE /favorites               – remove all

The limit comes from users.max_favorites (set by role) and is enforced here,
under a row lock on the user, so it cannot be bypassed from the client or by
concurrent requests.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.routes.auth import get_current_db_user
from app.db.database import get_db
from app.db.models import Auction, User, UserFavorite

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteItemOut(BaseModel):
    id: str
    label: str
    base_price: Optional[float] = None
    roi: Optional[float] = None


class FavoritesOut(BaseModel):
    max_favorites: int
    items: list[FavoriteItemOut]


def _item(auction: Auction) -> FavoriteItemOut:
    prop = auction.property
    city = prop.city if prop and prop.city else "—"
    label = f"{city} ({prop.province})" if prop and prop.province else city
    roi = None
    if auction.valuations:
        latest = max(auction.valuations, key=lambda v: v.created_at)
        roi = float(latest.roi_percentage) if latest.roi_percentage is not None else None
    return FavoriteItemOut(
        id=str(auction.id),
        label=label,
        base_price=float(auction.base_price) if auction.base_price is not None else None,
        roi=roi,
    )


async def _list(db: AsyncSession, user: User) -> FavoritesOut:
    result = await db.execute(
        select(UserFavorite)
        .options(
            selectinload(UserFavorite.auction).selectinload(Auction.property),
            selectinload(UserFavorite.auction).selectinload(Auction.valuations),
        )
        .where(UserFavorite.user_id == user.id)
        .order_by(UserFavorite.created_at)
    )
    favs = result.scalars().all()
    return FavoritesOut(max_favorites=user.max_favorites, items=[_item(f.auction) for f in favs])


@router.get("", response_model=FavoritesOut)
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_db_user),
) -> FavoritesOut:
    return await _list(db, user)


@router.put("/{auction_id}", response_model=FavoritesOut)
async def add_favorite(
    auction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_db_user),
) -> FavoritesOut:
    if await db.get(Auction, auction_id) is None:
        raise HTTPException(status_code=404, detail="Auction not found")

    # Serialise concurrent adds for the same user so the count check is reliable.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())

    exists = await db.scalar(
        select(UserFavorite.id).where(
            UserFavorite.user_id == user.id, UserFavorite.auction_id == auction_id
        )
    )
    if not exists:
        count = await db.scalar(
            select(func.count()).select_from(UserFavorite).where(UserFavorite.user_id == user.id)
        )
        if count >= user.max_favorites:
            raise HTTPException(
                status_code=409,
                detail=f"Favorites limit reached ({user.max_favorites})",
            )
        db.add(UserFavorite(user_id=user.id, auction_id=auction_id))
        await db.flush()
    return await _list(db, user)


@router.delete("/{auction_id}", status_code=204)
async def remove_favorite(
    auction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_db_user),
) -> Response:
    await db.execute(
        delete(UserFavorite).where(
            UserFavorite.user_id == user.id, UserFavorite.auction_id == auction_id
        )
    )
    return Response(status_code=204)


@router.delete("", status_code=204)
async def clear_favorites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_db_user),
) -> Response:
    await db.execute(delete(UserFavorite).where(UserFavorite.user_id == user.id))
    return Response(status_code=204)
