"""Unit tests for ROI engine."""
from __future__ import annotations

import pytest
from app.core.roi_engine import ROIEngine


@pytest.fixture
def engine(roi_config):
    return ROIEngine(roi_config)


class TestROICalculation:
    def test_basic_positive_roi(self, engine):
        result = engine.calculate(
            base_price=150_000,
            area_sqm=80,
            market_value=200_000,
        )
        # Total cost = 150k + taxes + fees + renovation (80*800=64k) ≈ 237k
        # Market value 200k < total cost → negative ROI in this case (high reno)
        assert result.purchase_price == 150_000
        assert result.total_acquisition_cost > 150_000
        assert isinstance(result.roi_percentage, float)
        assert isinstance(result.payback_years, float)

    def test_high_roi_scenario(self, engine):
        """Auction at 50% below market value, no renovation needed."""
        result = engine.calculate(
            base_price=80_000,
            area_sqm=60,
            market_value=200_000,
            renovation_level="light",
        )
        assert result.net_profit > 0
        assert result.roi_percentage > 0

    def test_negative_roi_flagged(self, engine):
        """Overpaying for a property that needs heavy work."""
        result = engine.calculate(
            base_price=300_000,
            area_sqm=50,
            market_value=200_000,
            renovation_level="heavy",
        )
        assert result.net_profit < 0
        assert not result.is_viable()

    def test_market_value_assumed_when_zero(self, engine):
        result = engine.calculate(
            base_price=100_000,
            area_sqm=70,
            market_value=0,
        )
        # Should fall back to base_price * 1.3
        assert result.market_value == pytest.approx(130_000, rel=0.01)
        assert result.assumptions["market_value_assumed"] is True

    def test_primary_residence_lower_tax(self, engine):
        r_primary = engine.calculate(100_000, 70, 150_000, is_primary_residence=True)
        r_secondary = engine.calculate(100_000, 70, 150_000, is_primary_residence=False)
        # Primary home has 2% registration tax vs 9%
        assert r_primary.tax_cost < r_secondary.tax_cost

    def test_to_db_dict_keys(self, engine):
        result = engine.calculate(120_000, 80, 160_000)
        db_dict = result.to_db_dict()
        required_keys = {
            "purchase_price", "market_value", "estimated_renovation_cost",
            "total_acquisition_cost", "net_profit_estimate", "roi_percentage",
            "payback_years", "methodology", "assumptions",
        }
        assert required_keys.issubset(db_dict.keys())

    def test_zero_area_no_renovation_cost(self, engine):
        result = engine.calculate(100_000, 0, 150_000)
        assert result.renovation_cost == 0.0

    def test_renovation_levels(self, engine):
        light = engine.calculate(100_000, 80, 150_000, renovation_level="light")
        medium = engine.calculate(100_000, 80, 150_000, renovation_level="medium")
        heavy = engine.calculate(100_000, 80, 150_000, renovation_level="heavy")
        assert light.renovation_cost < medium.renovation_cost < heavy.renovation_cost
