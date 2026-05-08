"""
Analytics endpoints.

POST /analytics/roi   – ad-hoc ROI calculation
POST /analytics/risk  – ad-hoc risk evaluation
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import ROICalculationRequest, ROICalculationResponse
from app.config.settings import load_yaml_config
from app.core.roi_engine import ROIEngine
from app.core.risk_engine import RiskEngine

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/roi", response_model=ROICalculationResponse)
async def calculate_roi(request: ROICalculationRequest) -> ROICalculationResponse:
    cfg = load_yaml_config()
    engine = ROIEngine(cfg["roi"])
    result = engine.calculate(
        base_price=request.base_price,
        area_sqm=request.area_sqm,
        market_value=request.market_value,
        property_type=request.property_type,
        renovation_level=request.renovation_level,
        is_primary_residence=request.is_primary_residence,
    )
    return ROICalculationResponse(
        purchase_price=result.purchase_price,
        market_value=result.market_value,
        renovation_cost=result.renovation_cost,
        legal_cost=result.legal_cost,
        tax_cost=result.tax_cost,
        notary_cost=result.notary_cost,
        total_acquisition_cost=result.total_acquisition_cost,
        gross_profit=result.gross_profit,
        net_profit=result.net_profit,
        roi_percentage=result.roi_percentage,
        payback_years=result.payback_years,
        is_viable=result.is_viable(cfg["roi"].get("target_min_roi_pct", 15)),
        summary=result.summary(),
        assumptions=result.assumptions,
    )


@router.post("/risk")
async def evaluate_risk(
    auction_data: dict,
    property_data: dict,
) -> dict:
    cfg = load_yaml_config()
    engine = RiskEngine(cfg["risk"])
    result = engine.evaluate(auction_data=auction_data, property_data=property_data)
    return {
        "total_score": result.total_score,
        "grade": result.grade,
        "breakdown": result.breakdown,
        "flags": [f.to_db_dict() for f in result.flags],
        "summary": result.summary(),
    }
