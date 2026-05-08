"""Unit tests for Risk engine."""
from __future__ import annotations

import pytest
from app.core.risk_engine import RiskEngine


@pytest.fixture
def engine(risk_config):
    return RiskEngine(risk_config)


def _auction(**kwargs):
    base = {"base_price": 100_000, "minimum_bid": 75_000, "court": "Tribunale di Milano", "auction_type": "asincrona_telematica"}
    base.update(kwargs)
    return base


def _prop(**kwargs):
    base = {"province": "MI", "property_type": "apartment", "encumbrances": None, "condition_notes": None}
    base.update(kwargs)
    return base


class TestRiskEngine:
    def test_clean_property_low_risk(self, engine):
        result = engine.evaluate(_auction(), _prop())
        assert result.grade == "LOW"
        assert result.total_score < 40

    def test_mortgage_raises_score(self, engine):
        result = engine.evaluate(_auction(), _prop(encumbrances="ipoteca"))
        clean = engine.evaluate(_auction(), _prop())
        assert result.total_score > clean.total_score
        flag_types = [f.flag_type for f in result.flags]
        assert "mortgage_encumbrance" in flag_types

    def test_seizure_critical_flag(self, engine):
        result = engine.evaluate(_auction(), _prop(encumbrances="pignoramento"))
        flag_types = [f.flag_type for f in result.flags]
        assert "seizure_encumbrance" in flag_types
        severe = [f for f in result.flags if f.flag_type == "seizure_encumbrance"]
        assert severe[0].severity == "critical"

    def test_province_c_tier_raises_score(self, engine):
        unknown_prov = engine.evaluate(_auction(), _prop(province="ZZ"))
        milan = engine.evaluate(_auction(), _prop(province="MI"))
        assert unknown_prov.total_score > milan.total_score

    def test_high_discount_flag(self, engine):
        # 50% discount triggers high_discount_signal
        result = engine.evaluate(
            _auction(base_price=200_000, minimum_bid=90_000),
            _prop(),
        )
        flag_types = [f.flag_type for f in result.flags]
        assert "high_discount_signal" in flag_types

    def test_multiple_encumbrances_compound(self, engine):
        # legal_complexity sub-score = min(20+30+40, 100) = 90
        # weighted total = 90*0.30 + 15*0.20 + 20*0.20 + 20*0.15 + 15*0.15 = 39.25
        # Both flags must be present and legal sub-score must dominate
        result = engine.evaluate(_auction(), _prop(encumbrances="ipoteca, pignoramento"))
        assert result.breakdown["legal_complexity"] == pytest.approx(90.0)
        flag_types = [f.flag_type for f in result.flags]
        assert "mortgage_encumbrance" in flag_types
        assert "seizure_encumbrance" in flag_types
        assert result.total_score > 30

    def test_score_max_100(self, engine):
        result = engine.evaluate(
            _auction(base_price=100_000, minimum_bid=20_000, auction_type="tradizionale"),
            _prop(province="ZZ", encumbrances="ipoteca, pignoramento, privilegio", condition_notes="fatiscente"),
        )
        assert result.total_score <= 100.0

    def test_breakdown_keys(self, engine):
        result = engine.evaluate(_auction(), _prop())
        expected = {"legal_complexity", "location_grade", "property_condition", "debt_burden", "auction_history"}
        assert expected.issubset(result.breakdown.keys())

    def test_grade_mapping(self, engine):
        # Verify grade is one of the expected values
        result = engine.evaluate(_auction(), _prop())
        assert result.grade in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_to_db_dict(self, engine):
        result = engine.evaluate(_auction(), _prop(encumbrances="ipoteca"))
        for flag in result.flags:
            d = flag.to_db_dict()
            assert "flag_type" in d
            assert "severity" in d
            assert "description" in d
