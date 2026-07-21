"""
test_pricing_engine.py
Author: Jun Shen

Unit tests for PricingEngine. The key sanity check for any bond pricing
engine is that a bond priced at a yield equal to its coupon rate, on a
coupon payment date, should price to exactly par (100).
"""

import unittest
from datetime import date

from src.bond import Bond
from src.pricing_engine import PricingEngine


class TestPricingEngine(unittest.TestCase):
    def setUp(self):
        self.bond = Bond(
            bond_id="TEST_PAR",
            face_value=100,
            coupon_rate=0.05,
            coupon_frequency=2,
            issue_date=date(2020, 1, 15),
            maturity_date=date(2030, 1, 15),
        )
        self.engine = PricingEngine(self.bond)

    def test_par_pricing_on_coupon_date(self):
        # settlement on a coupon date, ytm == coupon rate => price should be par
        settlement = date(2025, 1, 15)
        result = self.engine.price_from_yield(0.05, settlement)
        self.assertAlmostEqual(result["clean_price"], 100.0, places=4)
        self.assertAlmostEqual(result["accrued_interest"], 0.0, places=6)
        self.assertAlmostEqual(result["dirty_price"], 100.0, places=4)

    def test_premium_when_yield_below_coupon(self):
        settlement = date(2025, 1, 15)
        result = self.engine.price_from_yield(0.03, settlement)
        self.assertGreater(result["clean_price"], 100.0)

    def test_discount_when_yield_above_coupon(self):
        settlement = date(2025, 1, 15)
        result = self.engine.price_from_yield(0.07, settlement)
        self.assertLess(result["clean_price"], 100.0)

    def test_dirty_price_exceeds_clean_price_mid_period(self):
        settlement = date(2025, 4, 15)  # partway through a coupon period
        result = self.engine.price_from_yield(0.05, settlement)
        self.assertGreater(result["dirty_price"], result["clean_price"])
        self.assertAlmostEqual(
            result["dirty_price"] - result["clean_price"],
            result["accrued_interest"],
            places=6,
        )

    def test_zero_coupon_bond_prices_below_par(self):
        zero_bond = Bond(
            bond_id="TEST_ZERO",
            face_value=100,
            coupon_rate=0.0,
            coupon_frequency=2,
            issue_date=date(2024, 1, 15),
            maturity_date=date(2025, 1, 15),
        )
        engine = PricingEngine(zero_bond)
        result = engine.price_from_yield(0.04, date(2024, 6, 15))
        self.assertLess(result["clean_price"], 100.0)
        self.assertGreater(result["clean_price"], 0.0)

    def test_matured_bond_prices_to_zero(self):
        settlement = date(2031, 1, 15)  # past maturity
        result = self.engine.price_from_yield(0.05, settlement)
        self.assertEqual(result["dirty_price"], 0.0)
        self.assertEqual(result["clean_price"], 0.0)


if __name__ == "__main__":
    unittest.main()
