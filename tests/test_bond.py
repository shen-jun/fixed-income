"""
test_bond.py
Author: Jun Shen

Unit tests for Bond cashflow generation and accrued interest.
"""

import unittest
from datetime import date

from src.bond import Bond


class TestBondCoupondates(unittest.TestCase):
    def test_semiannual_schedule_length(self):
        bond = Bond(
            bond_id="TEST_5Y",
            face_value=100,
            coupon_rate=0.04,
            coupon_frequency=2,
            issue_date=date(2020, 1, 15),
            maturity_date=date(2025, 1, 15),
        )
        schedule = bond.generate_coupon_dates()
        # 5 years, semiannual => 10 coupon dates
        self.assertEqual(len(schedule), 10)
        self.assertEqual(schedule[0], date(2020, 7, 15))
        self.assertEqual(schedule[-1], date(2025, 1, 15))

    def test_schedule_is_chronological(self):
        bond = Bond(
            bond_id="TEST_10Y",
            face_value=100,
            coupon_rate=0.045,
            coupon_frequency=2,
            issue_date=date(2015, 6, 1),
            maturity_date=date(2025, 6, 1),
        )
        schedule = bond.generate_coupon_dates()
        for i in range(len(schedule) - 1):
            self.assertLess(schedule[i], schedule[i + 1])


class TestBondCashflows(unittest.TestCase):
    def setUp(self):
        self.bond = Bond(
            bond_id="TEST_2Y",
            face_value=100,
            coupon_rate=0.05,
            coupon_frequency=2,
            issue_date=date(2023, 1, 15),
            maturity_date=date(2025, 1, 15),
        )

    def test_cashflow_count_after_settlement(self):
        settlement = date(2024, 1, 15)
        cashflows = self.bond.generate_cashflows(settlement)
        # remaining coupons: 2024-07-15, 2025-01-15 => 2 cashflows
        self.assertEqual(len(cashflows), 2)

    def test_final_cashflow_includes_face_value(self):
        settlement = date(2024, 1, 15)
        cashflows = self.bond.generate_cashflows(settlement)
        last_date, last_amount = cashflows[-1]
        self.assertEqual(last_date, date(2025, 1, 15))
        self.assertAlmostEqual(last_amount, 100 + 2.5, places=6)

    def test_coupon_amount_is_half_annual_rate(self):
        settlement = date(2024, 1, 15)
        cashflows = self.bond.generate_cashflows(settlement)
        first_date, first_amount = cashflows[0]
        self.assertAlmostEqual(first_amount, 2.5, places=6)


class TestAccruedInterest(unittest.TestCase):
    def setUp(self):
        self.bond = Bond(
            bond_id="TEST_ACCR",
            face_value=100,
            coupon_rate=0.04,
            coupon_frequency=2,
            issue_date=date(2023, 1, 15),
            maturity_date=date(2028, 1, 15),
        )

    def test_zero_accrued_on_coupon_date(self):
        # settlement exactly on a coupon date -> previous_coupon == settlement,
        # so days_accrued should be 0
        accrued = self.bond.accrued_interest(date(2024, 1, 15))
        self.assertAlmostEqual(accrued, 0.0, places=6)

    def test_accrued_midway_through_period(self):
        # period runs 2024-01-15 to 2024-07-15 (182 days), settlement at
        # the halfway point should give roughly half a coupon
        previous_coupon = date(2024, 1, 15)
        next_coupon = date(2024, 7, 15)
        days_in_period = (next_coupon - previous_coupon).days
        halfway = date(2024, 4, 15)
        days_accrued = (halfway - previous_coupon).days

        expected = (self.bond.coupon_payment()) * (days_accrued / days_in_period)
        actual = self.bond.accrued_interest(halfway)
        self.assertAlmostEqual(actual, expected, places=6)

    def test_accrued_is_positive_and_less_than_full_coupon(self):
        accrued = self.bond.accrued_interest(date(2024, 5, 1))
        self.assertGreater(accrued, 0.0)
        self.assertLess(accrued, self.bond.coupon_payment())


class TestZeroCouponBond(unittest.TestCase):
    def test_bill_has_no_interim_cashflow_value(self):
        bill = Bond(
            bond_id="TEST_BILL",
            face_value=100,
            coupon_rate=0.0,
            coupon_frequency=2,
            issue_date=date(2024, 7, 15),
            maturity_date=date(2025, 1, 15),
        )
        cashflows = bill.generate_cashflows(date(2024, 8, 1))
        # only one cashflow at maturity, equal to face value
        self.assertEqual(len(cashflows), 1)
        self.assertAlmostEqual(cashflows[0][1], 100.0, places=6)


if __name__ == "__main__":
    unittest.main()
