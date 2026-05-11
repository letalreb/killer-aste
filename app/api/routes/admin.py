"""
Admin endpoints. All require role=admin.

GET  /admin/ingestion/runs          – recent ingestion runs (history)
GET  /admin/ingestion/runs/{run_id} – status of a specific run (poll for progress)
POST /admin/ingestion/trigger       – fire an ingestion run in the background
GET  /admin/stats                   – platform-wide statistics
GET  /admin/users                   – list all registered users
PATCH /admin/users/{user_id}/role   – change a user's role
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import UserOut, get_current_user
from app.api.schemas import IngestionTriggerRequest
from app.db.database import AsyncSessionFactory, get_db
from app.db.models import Auction, IngestionLog, IngestionStatus, LoginAudit, Property, User, UserRole

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Admin guard ──────────────────────────────────────────────────────────────

def require_admin(user: UserOut = Depends(get_current_user)) -> UserOut:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ─── Ingestion ────────────────────────────────────────────────────────────────

async def _run_ingestion_background(source: str, dry_run: bool) -> None:
    import os
    from app.ingestion.ingestion_service import IngestionService
    if dry_run:
        os.environ["DRY_RUN"] = "true"
    try:
        async with AsyncSessionFactory() as session:
            service = IngestionService(session)
            result = await service.run(source=source)
        log.info("admin.ingestion_complete", **result)
    except Exception as exc:
        log.error("admin.ingestion_error", error=str(exc))


@router.post("/ingestion/trigger", status_code=202)
async def trigger_ingestion(
    body: IngestionTriggerRequest,
    background_tasks: BackgroundTasks,
    admin: UserOut = Depends(require_admin),
) -> dict:
    background_tasks.add_task(_run_ingestion_background, body.source, body.dry_run)
    log.info("admin.ingestion_queued", source=body.source, dry_run=body.dry_run, by=admin.email)
    return {"status": "queued", "source": body.source, "dry_run": body.dry_run}


@router.get("/ingestion/runs")
async def list_ingestion_runs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: UserOut = Depends(require_admin),
) -> list[dict]:
    result = await db.execute(
        select(IngestionLog)
        .order_by(IngestionLog.started_at.desc())
        .limit(min(limit, 100))
    )
    runs = result.scalars().all()
    return [_run_to_dict(r) for r in runs]


@router.post("/ingestion/runs/{run_id}/cancel", status_code=200)
async def cancel_ingestion_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    admin: UserOut = Depends(require_admin),
) -> dict:
    result = await db.execute(
        select(IngestionLog)
        .where(IngestionLog.run_id == run_id)
        .order_by(IngestionLog.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status.value != "running":
        raise HTTPException(status_code=409, detail=f"Run is not active (status: {run.status.value})")

    from app.ingestion.cancellation import request_cancel
    request_cancel(run_id)
    log.info("admin.ingestion_cancel_requested", run_id=run_id, by=admin.email)
    return {"run_id": run_id, "status": "cancel_requested"}


@router.get("/ingestion/runs/{run_id}")
async def get_ingestion_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserOut = Depends(require_admin),
) -> dict:
    result = await db.execute(
        select(IngestionLog)
        .where(IngestionLog.run_id == run_id)
        .order_by(IngestionLog.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_dict(run)


def _run_to_dict(r: IngestionLog) -> dict:
    extra = r.extra or {}
    return {
        "id": str(r.id),
        "run_id": r.run_id,
        "source": r.source,
        "mode": r.mode,
        "status": r.status.value,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "pages_fetched": r.pages_fetched,
        "records_found": r.records_found,
        "records_inserted": r.records_inserted,
        "records_updated": r.records_updated,
        "properties_inserted": extra.get("properties_inserted", 0),
        "properties_updated": extra.get("properties_updated", 0),
        "errors_count": r.errors_count,
        "requests_made": r.requests_made,
        "error_detail": r.error_detail,
    }


# ─── Platform stats ───────────────────────────────────────────────────────────

@router.get("/stats")
async def platform_stats(
    db: AsyncSession = Depends(get_db),
    _: UserOut = Depends(require_admin),
) -> dict:
    # Auction counts by status
    auction_rows = (await db.execute(
        select(Auction.status, func.count().label("n")).group_by(Auction.status)
    )).all()
    auction_counts = {row.status.value: row.n for row in auction_rows}

    # Property total
    prop_total = (await db.execute(select(func.count()).select_from(Property))).scalar_one()

    # Users by role (active only)
    user_rows = (await db.execute(
        select(User.role, func.count().label("n"))
        .where(User.is_active == True)  # noqa: E712
        .group_by(User.role)
    )).all()
    user_counts = {row.role.value: row.n for row in user_rows}

    # Logins in last 30 days
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    logins_30d = (await db.execute(
        select(func.count())
        .select_from(LoginAudit)
        .where(LoginAudit.logged_in_at >= thirty_days_ago)
    )).scalar_one()

    # Ingestion summary
    total_runs = (await db.execute(select(func.count()).select_from(IngestionLog))).scalar_one()
    last_ok = (await db.execute(
        select(IngestionLog)
        .where(IngestionLog.status == IngestionStatus.COMPLETED)
        .order_by(IngestionLog.completed_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    # Auctions with ROI data (valuations count)
    from app.db.models import Valuation
    auctions_with_roi = (await db.execute(
        select(func.count(func.distinct(Valuation.auction_id))).select_from(Valuation)
    )).scalar_one()

    return {
        "users": {
            "total": sum(user_counts.values()),
            "by_role": user_counts,
            "logins_last_30d": logins_30d,
        },
        "auctions": {
            "total": sum(auction_counts.values()),
            "by_status": auction_counts,
            "with_roi": auctions_with_roi,
        },
        "properties": {
            "total": prop_total,
        },
        "ingestion": {
            "total_runs": total_runs,
            "last_successful_at": last_ok.completed_at.isoformat() if last_ok and last_ok.completed_at else None,
            "last_run_inserted": last_ok.records_inserted if last_ok else 0,
        },
        "sources": ["pvp.giustizia.it"],
    }


# ─── User management ─────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: UserOut = Depends(require_admin),
) -> list[dict]:
    result = await db.execute(
        select(User)
        .order_by(User.last_login_at.desc().nulls_last())
        .limit(min(limit, 500))
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "picture": u.picture,
            "role": u.role.value,
            "is_active": u.is_active,
            "max_favorites": u.max_favorites,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


class SetRoleRequest(BaseModel):
    role: str


@router.patch("/users/{user_id}/role")
async def set_user_role(
    user_id: uuid.UUID,
    body: SetRoleRequest,
    db: AsyncSession = Depends(get_db),
    admin: UserOut = Depends(require_admin),
) -> dict:
    try:
        new_role = UserRole(body.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {body.role}")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from app.db.repository import UserRepository
    repo = UserRepository(db)
    await repo.set_role(user_id, new_role)
    await db.commit()
    log.info("admin.role_changed", user_id=str(user_id), role=body.role, by=admin.email)
    return {"user_id": str(user_id), "role": body.role}
