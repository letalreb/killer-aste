"""
Pydantic v2 API schemas (request / response models).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
#  Shared
# ─────────────────────────────────────────────────────────────────────────────

class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Property
# ─────────────────────────────────────────────────────────────────────────────

class PropertyOut(OrmModel):
    id: uuid.UUID
    external_id: str
    source: str
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    property_type: str
    area_sqm: Optional[Decimal] = None
    floor: Optional[int] = None
    rooms: Optional[int] = None
    market_value_estimate: Optional[Decimal] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
#  Valuation
# ─────────────────────────────────────────────────────────────────────────────

class ValuationOut(OrmModel):
    id: uuid.UUID
    auction_id: uuid.UUID
    market_value: Optional[Decimal] = None
    purchase_price: Optional[Decimal] = None
    total_acquisition_cost: Optional[Decimal] = None
    net_profit_estimate: Optional[Decimal] = None
    roi_percentage: Optional[Decimal] = None
    payback_years: Optional[Decimal] = None
    assumptions: Optional[dict] = None
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
#  Risk Flag
# ─────────────────────────────────────────────────────────────────────────────

class RiskFlagOut(OrmModel):
    id: uuid.UUID
    flag_type: str
    severity: str
    score_contribution: Optional[Decimal] = None
    description: str
    extra: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────────
#  Auction
# ─────────────────────────────────────────────────────────────────────────────

class AuctionOut(OrmModel):
    id: uuid.UUID
    external_id: str
    source: str
    court: Optional[str] = None
    procedure_number: Optional[str] = None
    auction_type: str
    status: str
    base_price: Optional[Decimal] = None
    minimum_bid: Optional[Decimal] = None
    bid_increment: Optional[Decimal] = None
    deposit_required: Optional[Decimal] = None
    auction_date: Optional[datetime] = None
    auction_deadline: Optional[datetime] = None
    source_url: Optional[str] = None
    property: Optional[PropertyOut] = None
    valuations: list[ValuationOut] = []
    risk_flags: list[RiskFlagOut] = []
    created_at: datetime
    updated_at: datetime


class AuctionListOut(OrmModel):
    id: uuid.UUID
    external_id: str
    court: Optional[str] = None
    auction_type: str
    status: str
    base_price: Optional[Decimal] = None
    minimum_bid: Optional[Decimal] = None
    auction_date: Optional[datetime] = None
    city: Optional[str] = None
    province: Optional[str] = None
    roi_percentage: Optional[Decimal] = None   # from latest valuation


# ─────────────────────────────────────────────────────────────────────────────
#  Analytics
# ─────────────────────────────────────────────────────────────────────────────

class ROICalculationRequest(BaseModel):
    base_price: float = Field(..., gt=0)
    area_sqm: float = Field(..., gt=0)
    market_value: float = Field(default=0.0, ge=0)
    property_type: str = "apartment"
    renovation_level: str = Field(default="medium", pattern="^(light|medium|heavy)$")
    is_primary_residence: bool = False


class ROICalculationResponse(BaseModel):
    purchase_price: float
    market_value: float
    renovation_cost: float
    legal_cost: float
    tax_cost: float
    notary_cost: float
    total_acquisition_cost: float
    gross_profit: float
    net_profit: float
    roi_percentage: float
    payback_years: float
    is_viable: bool
    summary: str
    assumptions: dict


# ─────────────────────────────────────────────────────────────────────────────
#  Ingestion
# ─────────────────────────────────────────────────────────────────────────────

class IngestionTriggerRequest(BaseModel):
    source: str = Field(default="pvp", pattern="^[a-z_]+$")
    dry_run: bool = False


class IngestionStatusResponse(BaseModel):
    run_id: str
    status: str
    pages_fetched: int
    records_found: int
    records_inserted: int
    records_updated: int
    errors_count: int
    requests_made: int


# ─────────────────────────────────────────────────────────────────────────────
#  Pagination wrapper
# ─────────────────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    has_next: bool
