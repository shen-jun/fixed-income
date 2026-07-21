"""
test_shock_engine.py
Author: Jun Shen

Unit tests for ShockEngine's parallel and non-parallel curve shocks, and
for the flat-yield shock evaluation helper.
"""

import unittest
from datetime import date

from src.bond import Bond
from src.pricing_engine import PricingEngine
from src.risk_measures import RiskMeasures
from src.curve import TreasuryCurve
from src.shock_engine import ShockEngine


class TestShockEngine(unittest.TestCase):
    def setUp(self):
        self.curve = TreasuryCurve(name="Test Curve")
        self.curve.tenors = ["1Y", "2Y", "5Y", "10Y", "20Y", "30Y"]
        self.curve.maturities = [1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
        self.curve.yields = [0.040, 0.041, 0.042, 0.043, 0.045, 0.044]
        self.engine = ShockEngine(self.curve)

    def test_parallel_shock_shifts_every_tenor_equally(self):
        shocked = self.engine.parallel_shock(25)
        for base_y, shocked_y in zip(self.curve.yields, shocked):
            self.assertAlmostEqual(shocked_y - base_y, 0.0025, places=8)

    def test_steepener_short_end_and_long_end_move_opposite(self):
        shocked = self.engine.steepener(short_bp=-25, long_bp=25)
        short_change = shocked[0] - self.curve.yields[0]
        long_change = shocked[-1] - self.curve.yields[-1]
        self.assertAlmostEqual(short_change, -0.0025, places=8)
        self.assertAlmostEqual(long_change, 0.0025, places=8)
        # slope should have increased (long end rose more than short end
        # relative to base -- the curve steepened)
        base_slope = self.curve.yields[-1] - self.curve.yields[0]
        shocked_slope = shocked[-1] - shocked[0]
        self.assertGreater(shocked_slope, base_slope)

    def test_twist_pivots_around_specified_tenor(self):
        shocked = self.engine.twist(pivot_tenor=5.0, short_bp=-20, long_bp=20)
        pivot_index = self.curve.maturities.index(5.0)
        # yield exactly at the pivot tenor should be unchanged
        self.assertAlmostEqual(shocked[pivot_index], self.curve.yields[pivot_index], places=8)

    def test_butterfly_moves_belly_opposite_to_wings(self):
        shocked = self.engine.butterfly(belly_tenor=5.0, wing_bp=20, belly_bp=-20)
        belly_index = self.curve.maturities.index(5.0)
        belly_change = shocked[belly_index] - self.curve.yields[belly_index]
        short_wing_change = shocked[0] - self.curve.yields[0]
        long_wing_change = shocked[-1] - self.curve.yields[-1]

        self.assertAlmostEqual(belly_change, -0.0020, places=8)
        self.assertAlmostEqual(short_wing_change, 0.0020, places=8)
        self.assertAlmostEqual(long_wing_change, 0.0020, places=8)


class TestFlatYieldShockEvaluation(unittest.TestCase):
    def setUp(self):
        self.bond = Bond(
            bond_id="TEST_SHOCK_BOND",
            face_value=100,
            coupon_rate=0.04,
            coupon_frequency=2,
            issue_date=date(2015, 1, 15),
            maturity_date=date(2035, 1, 15),
        )
        self.pricing_engine = PricingEngine(self.bond)
        self.risk_measures = RiskMeasures(self.bond, self.pricing_engine)
        self.settlement = date(2025, 1, 15)

    def test_rate_increase_produces_negative_pnl(self):
        result = ShockEngine.evaluate_flat_yield_shock(
            self.pricing_engine, self.risk_measures,
            ytm_base=0.04, ytm_shocked=0.05,
            settlement_date=self.settlement,
        )
        self.assertLess(result["pnl"], 0.0)
        self.assertLess(result["pct_change_actual"], 0.0)

    def test_rate_decrease_produces_positive_pnl(self):
        result = ShockEngine.evaluate_flat_yield_shock(
            self.pricing_engine, self.risk_measures,
            ytm_base=0.04, ytm_shocked=0.03,
            settlement_date=self.settlement,
        )
        self.assertGreater(result["pnl"], 0.0)
        self.assertGreater(result["pct_change_actual"], 0.0)

    def test_convexity_adjusted_approx_closer_than_duration_only(self):
        result = ShockEngine.evaluate_flat_yield_shock(
            self.pricing_engine, self.risk_measures,
            ytm_base=0.04, ytm_shocked=0.06,  # large 200bp move
            settlement_date=self.settlement,
        )
        actual = result["pct_change_actual"]
        duration_only_error = abs(result["pct_change_duration_approx"] - actual)
        dur_convexity_error = abs(result["pct_change_duration_convexity_approx"] - actual)

        self.assertLess(dur_convexity_error, duration_only_error)


if __name__ == "__main__":
    unittest.main()
