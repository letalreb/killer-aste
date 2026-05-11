"""Unit tests for app.core.enrichment_engine."""
from __future__ import annotations

import pytest

from app.core.enrichment_engine import EnrichmentEngine, EnrichmentResult, OpportunityInput


def _engine(max_roi=15.0, max_risk=20.0) -> EnrichmentEngine:
    return EnrichmentEngine({"engine": {"max_roi_uplift_pct": max_roi, "max_risk_reduction": max_risk}})


def _opp(opp_type: str, relevance: float = 70.0) -> OpportunityInput:
    return OpportunityInput(
        id="test-id",
        opportunity_type=opp_type,
        title=f"Test {opp_type}",
        relevance_score=relevance,
    )


class TestEnrichmentEngineNoOpportunities:
    def test_empty_list_returns_zero_adjustments(self):
        engine = _engine()
        result = engine.evaluate([])
        assert result.roi_market_value_uplift_pct == 0.0
        assert result.risk_score_reduction == 0.0
        assert result.opportunity_count == 0
        assert result.signals == []

    def test_empty_is_not_significant(self):
        assert not _engine().evaluate([]).is_significant()


class TestEnrichmentEngineUplift:
    def test_rigenerazione_urbana_high_uplift(self):
        engine = _engine()
        result = engine.evaluate([_opp("rigenerazione_urbana", relevance=100.0)])
        assert result.roi_market_value_uplift_pct == pytest.approx(8.0, abs=0.01)
        assert result.risk_score_reduction == pytest.approx(10.0, abs=0.01)

    def test_pnrr_progetto_medium_uplift(self):
        result = _engine().evaluate([_opp("pnrr_progetto", relevance=100.0)])
        assert result.roi_market_value_uplift_pct == pytest.approx(5.0, abs=0.01)
        assert result.risk_score_reduction == pytest.approx(7.0, abs=0.01)

    def test_relevance_scales_contribution(self):
        full = _engine().evaluate([_opp("rigenerazione_urbana", relevance=100.0)])
        half = _engine().evaluate([_opp("rigenerazione_urbana", relevance=50.0)])
        assert half.roi_market_value_uplift_pct == pytest.approx(
            full.roi_market_value_uplift_pct / 2, abs=0.1
        )

    def test_unknown_type_uses_altro_fallback(self):
        result = _engine().evaluate([_opp("nonexistent_type", relevance=100.0)])
        assert result.roi_market_value_uplift_pct == pytest.approx(0.5, abs=0.01)

    def test_multiple_opportunities_accumulate(self):
        opps = [
            _opp("rigenerazione_urbana", relevance=100.0),
            _opp("pnrr_progetto", relevance=100.0),
        ]
        result = _engine().evaluate(opps)
        assert result.roi_market_value_uplift_pct == pytest.approx(13.0, abs=0.01)
        assert result.opportunity_count == 2

    def test_capped_at_max_roi_uplift(self):
        opps = [_opp("rigenerazione_urbana", relevance=100.0) for _ in range(10)]
        result = _engine(max_roi=10.0).evaluate(opps)
        assert result.roi_market_value_uplift_pct == pytest.approx(10.0, abs=0.01)

    def test_capped_at_max_risk_reduction(self):
        opps = [_opp("rigenerazione_urbana", relevance=100.0) for _ in range(10)]
        result = _engine(max_risk=15.0).evaluate(opps)
        assert result.risk_score_reduction == pytest.approx(15.0, abs=0.01)


class TestEnrichmentEngineSignals:
    def test_signal_generated_for_each_opportunity(self):
        opps = [_opp("rigenerazione_urbana"), _opp("pnrr_progetto")]
        result = _engine().evaluate(opps)
        assert len(result.signals) == 2

    def test_signal_has_required_keys(self):
        result = _engine().evaluate([_opp("pnrr_progetto")])
        sig = result.signals[0]
        assert "signal_type" in sig
        assert "value" in sig
        assert "confidence" in sig
        assert "source" in sig
        assert "extra" in sig

    def test_breakdown_groups_by_type(self):
        opps = [_opp("rigenerazione_urbana"), _opp("rigenerazione_urbana")]
        result = _engine().evaluate(opps)
        assert "rigenerazione_urbana" in result.breakdown


class TestApplyToMarketValue:
    def test_applies_uplift(self):
        engine = _engine()
        result = EnrichmentResult(
            roi_market_value_uplift_pct=10.0,
            risk_score_reduction=5.0,
            opportunity_count=1,
        )
        adjusted = engine.apply_to_market_value(100_000.0, result)
        assert adjusted == pytest.approx(110_000.0, abs=1.0)

    def test_zero_uplift_unchanged(self):
        engine = _engine()
        result = EnrichmentResult(
            roi_market_value_uplift_pct=0.0,
            risk_score_reduction=0.0,
            opportunity_count=0,
        )
        assert engine.apply_to_market_value(100_000.0, result) == 100_000.0


class TestApplyToRiskScore:
    def test_reduces_score(self):
        engine = _engine()
        result = EnrichmentResult(
            roi_market_value_uplift_pct=5.0,
            risk_score_reduction=10.0,
            opportunity_count=1,
        )
        assert engine.apply_to_risk_score(60.0, result) == pytest.approx(50.0, abs=0.01)

    def test_clamps_at_zero(self):
        engine = _engine()
        result = EnrichmentResult(
            roi_market_value_uplift_pct=5.0,
            risk_score_reduction=30.0,
            opportunity_count=1,
        )
        assert engine.apply_to_risk_score(20.0, result) == 0.0


class TestToAssumptionsDict:
    def test_includes_all_enrichment_keys(self):
        result = EnrichmentResult(
            roi_market_value_uplift_pct=8.0,
            risk_score_reduction=10.0,
            opportunity_count=2,
            breakdown={"rigenerazione_urbana": 8.0},
        )
        d = result.to_assumptions_dict()
        assert d["enrichment_roi_uplift_pct"] == 8.0
        assert d["enrichment_risk_reduction"] == 10.0
        assert d["enrichment_opportunity_count"] == 2
