"""
test_portfolio.py
Author: Jun Shen

Unit tests for Portfolio aggregation logic: market value, weighted
yield/duration/convexity, DV01, and per-bond contribution.
"""

import unittest
from datetime import date

from src.bond import Bond
from src.pricing_engine import PricingEngine
from src.portfolio import Portfolio, PortfolioHolding


class TestPortfolio(unittest.TestCase):
    def setUp(self):
        self.settlement = date(2025, 1, 15)

        self.short_bond = Bond(
            bond_id="SHORT",
            face_value=100,
            coupon_rate=0.04,
            coupon_frequency=2,
            issue_date=date(2023, 1, 15),
            maturity_date=date(2028, 1, 15),
        )
        self.long_bond = Bond(
            bond_id="LONG",
            face_value=100,
            coupon_rate=0.045,
            coupon_frequency=2,
            issue_date=date(2015, 1, 15),
            maturity_date=date(2035, 1, 15),
        )

        self.portfolio = Portfolio(name="Test Portfolio")
        self.portfolio.add_holding(
            PortfolioHolding(self.short_bond, notional=1_000_000, ytm=0.04,
                              settlement_date=self.settlement)
        )
        self.portfolio.add_holding(
            PortfolioHolding(self.long_bond, notional=2_000_000, ytm=0.045,
                              settlement_date=self.settlement)
        )

    def test_market_value_matches_manual_sum(self):
        engine_short = PricingEngine(self.short_bond)
        engine_long = PricingEngine(self.long_bond)

        price_short = engine_short.price_from_yield(0.04, self.settlement)["dirty_price"]
        price_long = engine_long.price_from_yield(0.045, self.settlement)["dirty_price"]

        expected_mv = (price_short / 100.0) * 1_000_000 + (price_long / 100.0) * 2_000_000
        self.assertAlmostEqual(self.portfolio.market_value(), expected_mv, places=2)

    def test_weighted_yield_between_component_yields(self):
        weighted = self.portfolio.weighted_yield()
        self.assertGreater(weighted, 0.04)
        self.assertLess(weighted, 0.045)

    def test_weighted_duration_between_component_durations(self):
        from src.risk_measures import RiskMeasures
        risk_short = RiskMeasures(self.short_bond, PricingEngine(self.short_bond))
        risk_long = RiskMeasures(self.long_bond, PricingEngine(self.long_bond))

        dur_short = risk_short.modified_duration(0.04, self.settlement)
        dur_long = risk_long.modified_duration(0.045, self.settlement)

        weighted_dur = self.portfolio.weighted_duration()
        self.assertGreater(weighted_dur, min(dur_short, dur_long))
        self.assertLess(weighted_dur, max(dur_short, dur_long))

    def test_contribution_weights_sum_to_one(self):
        contributions = self.portfolio.contribution_by_bond()
        total_weight = sum(c["weight"] for c in contributions)
        self.assertAlmostEqual(total_weight, 1.0, places=6)

    def test_portfolio_dv01_positive(self):
        self.assertGreater(self.portfolio.portfolio_dv01(), 0.0)

    def test_empty_portfolio_has_zero_market_value(self):
        empty_portfolio = Portfolio(name="Empty")
        self.assertEqual(empty_portfolio.market_value(), 0.0)
        self.assertEqual(empty_portfolio.weighted_yield(), 0.0)


if __name__ == "__main__":
    unittest.main()
