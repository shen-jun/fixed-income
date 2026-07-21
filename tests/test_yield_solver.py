"""
test_yield_solver.py
Author: Jun Shen

Round-trip tests: price a bond at a known yield, then solve for the
yield given that price, and check we recover the original yield.
"""

import unittest
from datetime import date

from src.bond import Bond
from src.pricing_engine import PricingEngine
from src.yield_solver import YieldSolver


class TestYieldSolver(unittest.TestCase):
    def setUp(self):
        self.bond = Bond(
            bond_id="TEST_SOLVER",
            face_value=100,
            coupon_rate=0.045,
            coupon_frequency=2,
            issue_date=date(2019, 3, 15),
            maturity_date=date(2034, 3, 15),
        )
        self.engine = PricingEngine(self.bond)
        self.solver = YieldSolver(self.bond, self.engine)
        self.settlement = date(2025, 6, 1)

    def test_round_trip_par_yield(self):
        true_yield = 0.045
        price = self.engine.price_from_yield(true_yield, self.settlement)["clean_price"]
        solved = self.solver.solve_yield(price, self.settlement)
        self.assertAlmostEqual(solved, true_yield, places=6)

    def test_round_trip_premium_yield(self):
        true_yield = 0.03
        price = self.engine.price_from_yield(true_yield, self.settlement)["clean_price"]
        solved = self.solver.solve_yield(price, self.settlement)
        self.assertAlmostEqual(solved, true_yield, places=6)

    def test_round_trip_discount_yield(self):
        true_yield = 0.065
        price = self.engine.price_from_yield(true_yield, self.settlement)["clean_price"]
        solved = self.solver.solve_yield(price, self.settlement)
        self.assertAlmostEqual(solved, true_yield, places=6)

    def test_unreachable_price_raises(self):
        # a negative target price can never be bracketed since bond
        # prices are always positive
        with self.assertRaises(ValueError):
            self.solver.solve_yield(-50.0, self.settlement)


if __name__ == "__main__":
    unittest.main()
