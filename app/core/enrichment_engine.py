"""
Enrichment Engine — correlates nearby public opportunities with PVP auction data
to produce additional intelligence signals that augment ROI and risk assessments.

Design:
  - Purely functional: takes data in, returns EnrichmentResult out
  - Non-breaking: called after standard ROI/risk engines; never replaces them
  - Additive: results are stored in enrichment_signals and in Valuation.assumptions

Uplift factors by opportunity type:
  rigenerazione_urbana        → +8% market value uplift, -10 risk points
  pnrr_progetto               → +5% uplift, -7 risk points
  valorizzazione_immobiliare  → +6% uplift, -8 risk points
  piano_recupero              → +4% uplift, -6 risk points
  investimento_infrastrutturale → +3% uplift, -5 risk points
  dismissione_pubblica        → +2% uplift, -3 risk points
  alienazione_pubblica        → +1% uplift, -2 risk points
  piano_urbanistico           → +2% uplift, -3 risk points
  altro                       → +0.5% uplift, -1 risk point

Caps (regardless of how many opportunities are found):
  max_roi_uplift_pct:   15.0   (market value cannot be boosted more than 15%)
  max_risk_reduction:   20.0   (risk score cannot be reduced more than 20 points)

Configuration lives in config.yaml under enrichment.engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Per-type uplift table ──────────────────────────────────────────────────────

_UPLIFT: dict[str, tuple[float, float]] = {
    # (roi_uplift_pct, risk_reduction_pts)
    "rigenerazione_urbana":           (8.0, 10.0),
    "pnrr_progetto":                  (5.0,  7.0),
    "valorizzazione_immobiliare":     (6.0,  8.0),
    "piano_recupero":                 (4.0,  6.0),
    "investimento_infrastrutturale":  (3.0,  5.0),
    "dismissione_pubblica":           (2.0,  3.0),
    "alienazione_pubblica":           (1.0,  2.0),
    "piano_urbanistico":              (2.0,  3.0),
    "altro":                          (0.5,  1.0),
}


@dataclass
class OpportunityInput:
    """Minimal representation of a public opportunity used by the engine."""
    id: str
    opportunity_type: str
    title: str
    city: Optional[str] = None
    province: Optional[str] = None
    budget_amount: Optional[float] = None
    relevance_score: Optional[float] = None  # 0-100 from property_opportunity_links


@dataclass
class EnrichmentResult:
    roi_market_value_uplift_pct: float   # add to existing market value estimate
    risk_score_reduction: float          # subtract from raw risk score
    opportunity_count: int
    signals: list[dict] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)

    def is_significant(self) -> bool:
        return self.roi_market_value_uplift_pct > 0.5 or self.risk_score_reduction > 1.0

    def to_assumptions_dict(self) -> dict:
        return {
            "enrichment_roi_uplift_pct": round(self.roi_market_value_uplift_pct, 2),
            "enrichment_risk_reduction": round(self.risk_score_reduction, 2),
            "enrichment_opportunity_count": self.opportunity_count,
            "enrichment_breakdown": self.breakdown,
        }

    def summary(self) -> str:
        return (
            f"Enrichment: +{self.roi_market_value_uplift_pct:.1f}% valore di mercato, "
            f"-{self.risk_score_reduction:.1f} rischio | "
            f"{self.opportunity_count} opportunità pubbliche"
        )


# ── Engine ────────────────────────────────────────────────────────────────────

class EnrichmentEngine:
    def __init__(self, config: dict) -> None:
        engine_cfg = config.get("engine", {})
        self._max_roi_uplift = float(engine_cfg.get("max_roi_uplift_pct", 15.0))
        self._max_risk_reduction = float(engine_cfg.get("max_risk_reduction", 20.0))

    def evaluate(
        self,
        opportunities: list[OpportunityInput],
        *,
        property_province: Optional[str] = None,
        property_city: Optional[str] = None,
    ) -> EnrichmentResult:
        """
        Compute enrichment adjustments for a property given a list of nearby
        public opportunities.

        Relevance weighting: an opportunity with relevance_score=100 contributes
        its full uplift; relevance_score=50 contributes half; default is 0.7 if
        no score is present (same city/province match without distance info).
        """
        if not opportunities:
            return EnrichmentResult(
                roi_market_value_uplift_pct=0.0,
                risk_score_reduction=0.0,
                opportunity_count=0,
            )

        total_roi = 0.0
        total_risk = 0.0
        breakdown: dict[str, float] = {}
        signals: list[dict] = []

        for opp in opportunities:
            opp_type = opp.opportunity_type or "altro"
            roi_factor, risk_factor = _UPLIFT.get(opp_type, (0.5, 1.0))

            relevance = (opp.relevance_score or 70.0) / 100.0
            roi_contrib = roi_factor * relevance
            risk_contrib = risk_factor * relevance

            total_roi += roi_contrib
            total_risk += risk_contrib
            breakdown[opp_type] = round(
                breakdown.get(opp_type, 0.0) + roi_contrib, 2
            )

            signals.append({
                "signal_type": f"nearby_opportunity_{opp_type}",
                "value": opp.title[:200],
                "confidence": round(relevance, 3),
                "source": f"opportunity:{opp.id}",
                "extra": {
                    "opportunity_id": opp.id,
                    "roi_contribution": round(roi_contrib, 2),
                    "risk_contribution": round(risk_contrib, 2),
                    "budget_amount": opp.budget_amount,
                },
            })

        return EnrichmentResult(
            roi_market_value_uplift_pct=min(round(total_roi, 2), self._max_roi_uplift),
            risk_score_reduction=min(round(total_risk, 2), self._max_risk_reduction),
            opportunity_count=len(opportunities),
            signals=signals,
            breakdown=breakdown,
        )

    def apply_to_market_value(
        self, base_market_value: float, enrichment: EnrichmentResult
    ) -> float:
        """Return market value adjusted upward by the enrichment uplift."""
        if enrichment.roi_market_value_uplift_pct <= 0:
            return base_market_value
        return base_market_value * (1.0 + enrichment.roi_market_value_uplift_pct / 100.0)

    def apply_to_risk_score(
        self, base_risk_score: float, enrichment: EnrichmentResult
    ) -> float:
        """Return risk score reduced by the enrichment signal."""
        return max(0.0, base_risk_score - enrichment.risk_score_reduction)
