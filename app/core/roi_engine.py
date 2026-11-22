"""
ROI Calculation Engine.

Formula (buy-renovate-resell, investor scenario) — methodology "standard_v2"
──────────────────────────────────────────────────────────────────────────────
Total acquisition cost = purchase_price
                       + registration_tax (9% / 2% prima casa, minimum €1,000)
                       + cadastral_tax (€50) + mortgage_tax (€50)
                       + transfer/delegate fees (base + % of value)
                       + legal_fee (% of purchase_price)
                       + renovation_cost (€/m² × area)
                       + condo arrears the buyer inherits (art. 63 disp. att.
                         c.c.: current + previous year), residential only

Holding cost   = purchase_price × holding_cost_pct_per_year × holding_months/12
Selling cost   = market_value × selling_cost_pct (agency + VAT)
Capital gains  = plusvalenza × capital_gains_tax_rate, if resold within 5 years
                 (plusvalenza = net sale price − deductible acquisition costs)

Gross profit = market_value − total_acquisition_cost
Net profit   = gross_profit − holding − selling − capital gains tax
ROI %        = net_profit / (total_acquisition_cost + holding) × 100

All rates come from config.yaml (roi section) and are estimates: they are
meant to stop the screener from overstating returns, not to replace a
professional assessment.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ROIResult:
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
    condo_arrears: float = 0.0
    holding_cost: float = 0.0
    selling_cost: float = 0.0
    capital_gains_tax: float = 0.0
    methodology: str = "standard_v2"
    assumptions: dict = field(default_factory=dict)

    def to_db_dict(self) -> dict:
        return {
            "purchase_price": round(self.purchase_price, 2),
            "market_value": round(self.market_value, 2),
            "estimated_renovation_cost": round(self.renovation_cost, 2),
            "estimated_legal_cost": round(self.legal_cost, 2),
            "estimated_tax_cost": round(self.tax_cost, 2),
            "estimated_notary_cost": round(self.notary_cost, 2),
            "total_acquisition_cost": round(self.total_acquisition_cost, 2),
            "gross_profit_estimate": round(self.gross_profit, 2),
            "net_profit_estimate": round(self.net_profit, 2),
            "roi_percentage": round(self.roi_percentage, 4),
            "payback_years": round(self.payback_years, 2),
            "methodology": self.methodology,
            "assumptions": self.assumptions,
        }

    def is_viable(self, min_roi_pct: float = 15.0) -> bool:
        return self.roi_percentage >= min_roi_pct

    def summary(self) -> str:
        viability = "VIABLE" if self.is_viable() else "BELOW THRESHOLD"
        return (
            f"ROI {self.roi_percentage:.1f}% | "
            f"Acquisto €{self.purchase_price:,.0f} → "
            f"Valore €{self.market_value:,.0f} | "
            f"Utile netto €{self.net_profit:,.0f} | {viability}"
        )


class ROIEngine:
    def __init__(self, config: dict) -> None:
        self._cfg = config

    def calculate(
        self,
        base_price: float,
        area_sqm: float,
        market_value: float,
        property_type: str = "apartment",
        renovation_level: str = "medium",
        is_primary_residence: bool = False,
        condo_annual_fees: float | None = None,
        resale_within_5_years: bool | None = None,
    ) -> ROIResult:
        """
        Calculate ROI for an auction purchase.

        If market_value is unknown (0), we assume it equals base_price * 1.3
        as a conservative proxy based on the fact that Italian court appraisals
        are typically 20-40% above starting price.
        """
        purchase_price = base_price or 0.0

        # Estimate market value if not available
        if market_value <= 0:
            market_value = purchase_price * 1.3
            assumed_mv = True
        else:
            assumed_mv = False

        # ── Renovation cost ────────────────────────────────────────────────────
        reno_cfg = self._cfg["renovation"]
        cost_per_sqm = reno_cfg.get(f"{renovation_level}_cost_per_sqm", 800)
        renovation_cost = area_sqm * cost_per_sqm if area_sqm > 0 else 0.0

        # ── Taxes ──────────────────────────────────────────────────────────────
        tax_cfg = self._cfg["taxes"]
        if is_primary_residence:
            reg_tax_rate = tax_cfg["registration_tax_primary"]
        else:
            reg_tax_rate = tax_cfg["registration_tax_secondary"]

        registration_tax = max(
            purchase_price * reg_tax_rate, float(tax_cfg.get("registration_tax_min_eur", 1000))
        )
        cadastral_tax = float(tax_cfg["cadastral_tax_fixed"])
        mortgage_tax = float(tax_cfg["mortgage_tax_fixed"])
        total_tax = registration_tax + cadastral_tax + mortgage_tax

        # ── Professional fees ─────────────────────────────────────────────────
        fee_cfg = self._cfg["professional_fees"]
        notary_base = float(fee_cfg["notary_base_eur"])
        notary_pct_fee = purchase_price * fee_cfg["notary_pct"]
        notary_cost = notary_base + notary_pct_fee

        legal_cost = purchase_price * fee_cfg["legal_pct"]

        # ── Condo arrears inherited by the buyer ──────────────────────────────
        exit_cfg = self._cfg.get("exit", {})
        condo_arrears = 0.0
        if property_type in exit_cfg.get("condo_property_types", ["apartment"]):
            if condo_annual_fees is None:
                condo_annual_fees = area_sqm * float(exit_cfg.get("condo_fee_per_sqm_year", 0))
            condo_arrears = condo_annual_fees * float(exit_cfg.get("condo_arrears_years", 2))

        # ── Totals ─────────────────────────────────────────────────────────────
        total_acquisition = (
            purchase_price
            + renovation_cost
            + total_tax
            + notary_cost
            + legal_cost
            + condo_arrears
        )

        # ── Exit: holding, selling, capital gains ─────────────────────────────
        holding_months = float(exit_cfg.get("holding_months", 0))
        holding_cost = (
            purchase_price * float(exit_cfg.get("holding_cost_pct_per_year", 0))
            * holding_months / 12
        )
        selling_cost = market_value * float(exit_cfg.get("selling_cost_pct", 0))

        if resale_within_5_years is None:
            resale_within_5_years = bool(exit_cfg.get("resale_within_5_years", True))
        capital_gains_tax = 0.0
        if resale_within_5_years and not is_primary_residence:
            deductible = purchase_price + total_tax + notary_cost + legal_cost + renovation_cost
            plusvalenza = market_value - selling_cost - deductible
            if plusvalenza > 0:
                capital_gains_tax = plusvalenza * float(exit_cfg.get("capital_gains_tax_rate", 0))

        gross_profit = market_value - total_acquisition
        net_profit = gross_profit - holding_cost - selling_cost - capital_gains_tax

        invested = total_acquisition + holding_cost
        roi_pct = (net_profit / invested * 100) if invested > 0 else 0.0

        # Payback in years: assume 5% net annual rental yield as proxy
        annual_rental_proxy = market_value * 0.05
        payback_years = (
            total_acquisition / annual_rental_proxy if annual_rental_proxy > 0 else 999.0
        )

        assumptions = {
            "renovation_level": renovation_level,
            "cost_per_sqm": cost_per_sqm,
            "is_primary_residence": is_primary_residence,
            "market_value_assumed": assumed_mv,
            "annual_rental_yield_proxy_pct": 5.0,
            "registration_tax": round(registration_tax, 2),
            "condo_arrears": round(condo_arrears, 2),
            "holding_months": holding_months,
            "holding_cost": round(holding_cost, 2),
            "selling_cost": round(selling_cost, 2),
            "resale_within_5_years": resale_within_5_years,
            "capital_gains_tax": round(capital_gains_tax, 2),
        }

        return ROIResult(
            purchase_price=purchase_price,
            market_value=market_value,
            renovation_cost=renovation_cost,
            legal_cost=legal_cost,
            tax_cost=total_tax,
            notary_cost=notary_cost,
            total_acquisition_cost=total_acquisition,
            gross_profit=gross_profit,
            net_profit=net_profit,
            roi_percentage=roi_pct,
            payback_years=payback_years,
            condo_arrears=condo_arrears,
            holding_cost=holding_cost,
            selling_cost=selling_cost,
            capital_gains_tax=capital_gains_tax,
            assumptions=assumptions,
        )
