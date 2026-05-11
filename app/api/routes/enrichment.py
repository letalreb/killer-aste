"""
Enrichment endpoints — public opportunity intelligence layer.

GET  /enrichment/opportunities              – list discovered public opportunities
GET  /enrichment/opportunities/{id}         – single opportunity detail
GET  /enrichment/properties/{id}/signals    – enrichment signals for a property
GET  /enrichment/properties/{id}/opportunities – opportunities linked to a property

Admin-only:
POST /enrichment/admin/trigger-discovery    – run a discovery pass
POST /enrichment/admin/opportunities/{id}   – manually add a public opportunity
"""
from __future__ import annotations

import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import UserOut, get_current_user
from app.db.database import AsyncSessionFactory, get_db
from app.db.models import OpportunityStatus, OpportunityType
from app.db.repository import EnrichmentSignalRepository, PublicOpportunityRepository

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/enrichment", tags=["enrichment"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class OpportunityOut(BaseModel):
    id: str
    title: str
    opportunity_type: str
    status: str
    source: Optional[str] = None
    source_url: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    budget_amount: Optional[float] = None
    expected_completion: Optional[str] = None
    document_url: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class SignalOut(BaseModel):
    id: str
    signal_type: str
    value: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None
    extra: Optional[dict] = None
    created_at: str

    model_config = {"from_attributes": True}


class OpportunityCreateRequest(BaseModel):
    title: str
    opportunity_type: str = "altro"
    province: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = None
    budget_amount: Optional[float] = None
    expected_completion: Optional[str] = None
    document_url: Optional[str] = None


class DiscoveryTriggerRequest(BaseModel):
    provinces: Optional[list[str]] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(user: UserOut = Depends(get_current_user)) -> UserOut:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _opp_to_dict(opp) -> dict:
    return {
        "id": str(opp.id),
        "title": opp.title,
        "opportunity_type": opp.opportunity_type.value if opp.opportunity_type else "altro",
        "status": opp.status.value if opp.status else "unknown",
        "source": opp.source,
        "source_url": opp.source_url,
        "province": opp.province,
        "city": opp.city,
        "description": opp.description,
        "budget_amount": float(opp.budget_amount) if opp.budget_amount else None,
        "expected_completion": opp.expected_completion,
        "document_url": opp.document_url,
        "created_at": opp.created_at.isoformat(),
        "updated_at": opp.updated_at.isoformat(),
    }


def _signal_to_dict(sig) -> dict:
    return {
        "id": str(sig.id),
        "signal_type": sig.signal_type,
        "value": sig.value,
        "confidence": float(sig.confidence) if sig.confidence else None,
        "source": sig.source,
        "extra": sig.extra,
        "created_at": sig.created_at.isoformat(),
    }


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/opportunities")
async def list_opportunities(
    province: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: UserOut = Depends(get_current_user),
) -> list[dict]:
    repo = PublicOpportunityRepository(db)
    if province or city:
        opps = await repo.find_by_location(province=province, city=city, limit=limit)
    else:
        opps = await repo.list_recent(limit=limit)
    return [_opp_to_dict(o) for o in opps]


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity(
    opportunity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserOut = Depends(get_current_user),
) -> dict:
    repo = PublicOpportunityRepository(db)
    opp = await repo.get_by_id(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return _opp_to_dict(opp)


@router.get("/properties/{property_id}/signals")
async def get_property_signals(
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserOut = Depends(get_current_user),
) -> list[dict]:
    repo = EnrichmentSignalRepository(db)
    signals = await repo.get_for_property(property_id)
    return [_signal_to_dict(s) for s in signals]


@router.get("/properties/{property_id}/opportunities")
async def get_property_opportunities(
    property_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: UserOut = Depends(get_current_user),
) -> list[dict]:
    repo = PublicOpportunityRepository(db)
    opps = await repo.get_linked_opportunities(property_id)
    return [_opp_to_dict(o) for o in opps]


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.post("/admin/trigger-discovery")
async def trigger_discovery(
    req: DiscoveryTriggerRequest,
    background_tasks: BackgroundTasks,
    _admin: UserOut = Depends(_require_admin),
) -> dict:
    background_tasks.add_task(_run_discovery_background, req.provinces)
    return {"status": "queued", "provinces": req.provinces}


@router.post("/admin/opportunities")
async def create_opportunity(
    req: OpportunityCreateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: UserOut = Depends(_require_admin),
) -> dict:
    try:
        opp_type = OpportunityType(req.opportunity_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown opportunity_type: {req.opportunity_type}")

    data = {
        "title": req.title,
        "opportunity_type": opp_type,
        "status": OpportunityStatus.ACTIVE,
        "province": req.province.upper() if req.province else None,
        "city": req.city,
        "description": req.description,
        "source_url": req.source_url,
        "budget_amount": req.budget_amount,
        "expected_completion": req.expected_completion,
        "document_url": req.document_url,
        "source": "manual_admin",
    }
    repo = PublicOpportunityRepository(db)
    opp, _ = await repo.upsert(data)
    await db.commit()
    return _opp_to_dict(opp)


# ── Background task ───────────────────────────────────────────────────────────

async def _run_discovery_background(provinces: Optional[list[str]]) -> None:
    from app.ingestion.discovery.discovery_service import DiscoveryService
    try:
        async with AsyncSessionFactory() as session:
            svc = DiscoveryService(session)
            result = await svc.run(provinces=provinces)
        log.info("enrichment.discovery_complete", **result)
    except Exception as exc:
        log.error("enrichment.discovery_error", error=str(exc))
