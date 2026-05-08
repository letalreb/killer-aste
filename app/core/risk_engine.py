"""
Risk Scoring Engine.

Produces a 0–100 composite risk score from weighted sub-scores.
Also generates human-readable RiskFlag objects persisted to the DB.

Weights (configurable via config.yaml):
  legal_complexity  30% – encumbrances, procedure complexity
  location_grade    20% – province tier (A/B/C based on market liquidity)
  property_condition 20% – condition notes, renovation signals
  debt_burden       15% – ratio of base price to deposit (proxy for debt level)
  auction_history   15% – auction_type risk, first/repeated auction
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
#  Province tier lookup (Italian real-estate market liquidity tiers)
#  A = high liquidity (low risk), B = medium, C = low liquidity (high risk)
# ─────────────────────────────────────────────────────────────────────────────
_PROVINCE_TIER: dict[str, str] = {
    "MI": "A", "RM": "A", "TO": "A", "BO": "A", "FI": "A", "GE": "A",
    "NA": "A", "VE": "A", "PD": "A", "BG": "A", "BS": "A", "VR": "A",
    "BA": "B", "CT": "B", "PA": "B", "CL": "B", "MO": "B", "PR": "B",
    "TS": "B", "TN": "B", "RC": "B", "AQ": "B", "PE": "B", "AN": "B",
}
_TIER_SCORE: dict[str, float] = {"A": 15.0, "B": 40.0, "C": 70.0}


@dataclass
class RiskFlagResult:
    flag_type: str
    severity: str        # low / medium / high / critical
    score_contribution: float
    description: str
    metadata: dict = field(default_factory=dict)

    def to_db_dict(self) -> dict:
        return {
            "flag_type": self.flag_type,
            "severity": self.severity,
            "score_contribution": round(self.score_contribution, 2),
            "description": self.description,
            "extra": self.metadata,
        }


@dataclass
class RiskResult:
    total_score: float           # 0 = no risk, 100 = maximum risk
    grade: str                   # LOW / MEDIUM / HIGH / CRITICAL
    flags: list[RiskFlagResult] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"Risk {self.grade} ({self.total_score:.0f}/100) | "
            f"{len(self.flags)} flag(s)"
        )


def _severity_from_score(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _grade_from_total(total: float, thresholds: dict) -> str:
    if total >= thresholds.get("critical", 90):
        return "CRITICAL"
    if total >= thresholds.get("high", 80):
        return "HIGH"
    if total >= thresholds.get("medium", 60):
        return "MEDIUM"
    return "LOW"


class RiskEngine:
    def __init__(self, config: dict) -> None:
        self._weights = config["weights"]
        self._thresholds = config["thresholds"]

    def evaluate(
        self,
        auction_data: dict,
        property_data: dict,
    ) -> RiskResult:
        flags: list[RiskFlagResult] = []
        breakdown: dict[str, float] = {}

        # ── Legal complexity (30%) ─────────────────────────────────────────────
        legal_score = self._score_legal(property_data, flags)
        breakdown["legal_complexity"] = legal_score

        # ── Location grade (20%) ──────────────────────────────────────────────
        location_score = self._score_location(property_data, flags)
        breakdown["location_grade"] = location_score

        # ── Property condition (20%) ──────────────────────────────────────────
        condition_score = self._score_condition(property_data, flags)
        breakdown["property_condition"] = condition_score

        # ── Debt burden (15%) ─────────────────────────────────────────────────
        debt_score = self._score_debt(auction_data, flags)
        breakdown["debt_burden"] = debt_score

        # ── Auction history / type (15%) ──────────────────────────────────────
        auction_score = self._score_auction_type(auction_data, flags)
        breakdown["auction_history"] = auction_score

        # ── Weighted composite ────────────────────────────────────────────────
        total = (
            legal_score * self._weights["legal_complexity"]
            + location_score * self._weights["location_grade"]
            + condition_score * self._weights["property_condition"]
            + debt_score * self._weights["debt_burden"]
            + auction_score * self._weights["auction_history"]
        )
        total = min(total, 100.0)

        return RiskResult(
            total_score=total,
            grade=_grade_from_total(total, self._thresholds),
            flags=flags,
            breakdown=breakdown,
        )

    # ── Sub-scorers ───────────────────────────────────────────────────────────

    def _score_legal(self, prop: dict, flags: list) -> float:
        encumbrances = (prop.get("encumbrances") or "").lower()
        score = 20.0  # baseline

        if "ipoteca" in encumbrances:
            score += 30
            flags.append(RiskFlagResult(
                flag_type="mortgage_encumbrance",
                severity="high",
                score_contribution=30.0,
                description="Presenza di ipoteca sull'immobile.",
                metadata={"encumbrances_raw": prop.get("encumbrances")},
            ))

        if "pignoramento" in encumbrances:
            score += 40
            flags.append(RiskFlagResult(
                flag_type="seizure_encumbrance",
                severity="critical",
                score_contribution=40.0,
                description="Presenza di pignoramento sull'immobile. Alta complessità legale.",
                metadata={"encumbrances_raw": prop.get("encumbrances")},
            ))

        if "privilegio" in encumbrances or "vincolo" in encumbrances:
            score += 20
            flags.append(RiskFlagResult(
                flag_type="privilege_lien",
                severity="medium",
                score_contribution=20.0,
                description="Presenza di privilegi o vincoli sull'immobile.",
            ))

        return min(score, 100.0)

    def _score_location(self, prop: dict, flags: list) -> float:
        province = (prop.get("province") or "").upper()
        tier = _PROVINCE_TIER.get(province, "C")
        score = _TIER_SCORE[tier]

        if tier == "C":
            flags.append(RiskFlagResult(
                flag_type="low_liquidity_market",
                severity=_severity_from_score(score),
                score_contribution=score,
                description=(
                    f"Provincia '{province or 'sconosciuta'}' classificata "
                    f"mercato a bassa liquidità (Tier {tier})."
                ),
                metadata={"province": province, "tier": tier},
            ))
        elif tier == "B":
            flags.append(RiskFlagResult(
                flag_type="medium_liquidity_market",
                severity="low",
                score_contribution=score,
                description=(
                    f"Provincia '{province}' classificata mercato liquidità media (Tier B)."
                ),
                metadata={"province": province, "tier": tier},
            ))
        return score

    def _score_condition(self, prop: dict, flags: list) -> float:
        notes = (prop.get("condition_notes") or "").lower()
        description = notes  # same field used
        score = 20.0

        heavy_keywords = ["fatiscente", "rudere", "diroccato", "inabitabile", "pericolante"]
        medium_keywords = ["ristrutturazione", "riqualificazione", "da ristrutturare"]

        if any(k in description for k in heavy_keywords):
            score += 60
            flags.append(RiskFlagResult(
                flag_type="poor_condition",
                severity="high",
                score_contribution=60.0,
                description="Immobile in condizioni molto scadenti o inabitabile.",
            ))
        elif any(k in description for k in medium_keywords):
            score += 30
            flags.append(RiskFlagResult(
                flag_type="renovation_required",
                severity="medium",
                score_contribution=30.0,
                description="Immobile necessita di ristrutturazione significativa.",
            ))

        return min(score, 100.0)

    def _score_debt(self, auction: dict, flags: list) -> float:
        base_price = auction.get("base_price") or 0
        minimum_bid = auction.get("minimum_bid") or 0
        score = 20.0

        if base_price > 0 and minimum_bid > 0:
            discount = (base_price - minimum_bid) / base_price
            if discount > 0.40:
                # Large discount often signals heavy debt burden
                score += 50
                flags.append(RiskFlagResult(
                    flag_type="high_discount_signal",
                    severity="medium",
                    score_contribution=50.0,
                    description=(
                        f"Offerta minima al {(1-discount)*100:.0f}% del prezzo base "
                        f"({discount*100:.0f}% sconto). Possibile elevato onere debitorio."
                    ),
                    metadata={
                        "base_price": base_price,
                        "minimum_bid": minimum_bid,
                        "discount_pct": round(discount * 100, 1),
                    },
                ))

        return min(score, 100.0)

    def _score_auction_type(self, auction: dict, flags: list) -> float:
        auction_type = auction.get("auction_type", "")
        score = 15.0  # baseline for telematic (modern, well-regulated)

        if auction_type == "tradizionale":
            score += 30
            flags.append(RiskFlagResult(
                flag_type="traditional_auction_type",
                severity="low",
                score_contribution=30.0,
                description=(
                    "Vendita con modalità tradizionale: minore trasparenza "
                    "rispetto alle vendite telematiche."
                ),
            ))
        elif auction_type == "senza_incanto":
            score += 20
            flags.append(RiskFlagResult(
                flag_type="no_competitive_bidding",
                severity="low",
                score_contribution=20.0,
                description="Vendita senza incanto: offerta unica, minore competizione.",
            ))

        return min(score, 100.0)
