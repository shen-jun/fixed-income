"""
test_risk_measures.py
Author: Jun Shen

Unit tests for RiskMeasures (duration, DV01, convexity) and
KeyRateDuration.
"""

import unittest
from datetime import date

from src.bond import Bond
from src.pricing_engine import PricingEngine
from src.risk_measures import RiskMeasures, KeyRateDuration
from src.curve import TreasuryCurve
from src.interpolation import LinearInterpolator


class TestDurationAndConvexity(unittest.TestCase):
    def setUp(self):
        self.bond = Bond(
            bond_id="TEST_RISK",
            face_value=100,
            coupon_rate=0.04,
            coupon_frequency=2,
            issue_date=date(2015, 1, 15),
            maturity_date=date(2035, 1, 15),
        )
        self.engine = PricingEngine(self.bond)
        self.risk = RiskMeasures(self.bond, self.engine)
        self.settlement = date(2025, 1, 15)
        self.ytm = 0.04

    def test_modified_duration_less_than_macaulay(self):
        mac_dur = self.risk.macaulay_duration(self.ytm, self.settlement)
        mod_dur = self.risk.modified_duration(self.ytm, self.settlement)
        self.assertLess(mod_dur, mac_dur)

    def test_duration_roughly_matches_finite_difference_dv01(self):
        # DV01 (per 100 face, per bp) should be approximately
        # ModDuration * Price * 0.0001
        mod_dur = self.risk.modified_duration(self.ytm, self.settlement)
        price = self.engine.price_from_yield(self.ytm, self.settlement)["dirty_price"]
        dv01 = self.risk.dv01(self.ytm, self.settlement)

        expected_dv01 = mod_dur * price * 0.0001
        # allow a modest tolerance since dv01 is a finite-difference
        # measure and duration is the analytical first-order approximation
        self.assertAlmostEqual(dv01, expected_dv01, delta=expected_dv01 * 0.02)

    def test_convexity_is_positive_for_plain_vanilla_bond(self):
        convexity = self.risk.convexity(self.ytm, self.settlement)
        self.assertGreater(convexity, 0.0)

    def test_longer_maturity_has_higher_duration(self):
        short_bond = Bond(
            bond_id="TEST_SHORT",
            face_value=100,
            coupon_rate=0.04,
            coupon_frequency=2,
            issue_date=date(2023, 1, 15),
            maturity_date=date(2028, 1, 15),
        )
        short_engine = PricingEngine(short_bond)
        short_risk = RiskMeasures(short_bond, short_engine)

        long_dur = self.risk.modified_duration(self.ytm, self.settlement)
        short_dur = short_risk.modified_duration(self.ytm, self.settlement)

        self.assertGreater(long_dur, short_dur)

    def test_price_change_approximation_via_taylor_expansion(self):
        dy = 0.0025  # 25bp shock
        price0 = self.engine.price_from_yield(self.ytm, self.settlement)["dirty_price"]
        price1 = self.engine.price_from_yield(self.ytm + dy, self.settlement)["dirty_price"]
        actual_pct_change = (price1 - price0) / price0

        mod_dur = self.risk.modified_duration(self.ytm, self.settlement)
        convexity = self.risk.convexity(self.ytm, self.settlement)
        approx_pct_change = -mod_dur * dy + 0.5 * convexity * dy ** 2

        self.assertAlmostEqual(actual_pct_change, approx_pct_change, delta=0.0005)


class TestKeyRateDuration(unittest.TestCase):
    def setUp(self):
        self.bond = Bond(
            bond_id="TEST_KRD",
            face_value=100,
            coupon_rate=0.04,
            coupon_frequency=2,
            issue_date=date(2015, 1, 15),
            maturity_date=date(2035, 1, 15),
        )
        self.curve = TreasuryCurve(name="Test Curve")
        self.curve.tenors = ["1Y", "2Y", "5Y", "10Y", "20Y", "30Y"]
        self.curve.maturities = [1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
        self.curve.yields = [0.040, 0.040, 0.040, 0.040, 0.040, 0.040]
        self.settlement = date(2025, 1, 15)

    def test_krd_sums_roughly_to_effective_duration(self):
        key_rate_tenors = [1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
        krd_calc = KeyRateDuration(self.bond, self.curve, LinearInterpolator, key_rate_tenors)
        result = krd_calc.compute(self.settlement)

        total_krd = sum(v["KRD"] for v in result["key_rate_results"].values())

        # cross-check: total KRD should roughly match effective duration
        # from a small parallel shock to the whole curve
        bump = 0.0001
        base_price = krd_calc.price_with_curve(self.curve.maturities, self.curve.yields, self.settlement)
        up_yields = [y + bump for y in self.curve.yields]
        down_yields = [y - bump for y in self.curve.yields]
        price_up = krd_calc.price_with_curve(self.curve.maturities, up_yields, self.settlement)
        price_down = krd_calc.price_with_curve(self.curve.maturities, down_yields, self.settlement)
        effective_duration = (price_down - price_up) / (2 * bump * base_price)

        self.assertAlmostEqual(total_krd, effective_duration, delta=effective_duration * 0.02)

    def test_kr01_for_longest_bond_dominated_by_long_tenor(self):
        key_rate_tenors = [1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
        krd_calc = KeyRateDuration(self.bond, self.curve, LinearInterpolator, key_rate_tenors)
        result = krd_calc.compute(self.settlement)

        kr01_20y = abs(result["key_rate_results"][20.0]["KR01"])
        kr01_1y = abs(result["key_rate_results"][1.0]["KR01"])

        # this bond matures in 10 years from settlement, so the 20Y key
        # rate bucket should have essentially no exposure, while the 1Y
        # bucket also has minimal exposure -- the bulk should sit in the
        # 10Y bucket
        kr01_10y = abs(result["key_rate_results"][10.0]["KR01"])
        self.assertGreater(kr01_10y, kr01_20y)
        self.assertGreater(kr01_10y, kr01_1y)


if __name__ == "__main__":
    unittest.main()
