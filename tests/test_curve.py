"""
test_curve.py
Author: Jun Shen

Unit tests for TreasuryCurve: CSV loading, shape classification, and
tenor-by-tenor comparison between two curves.
"""

import os
import unittest

from src.curve import TreasuryCurve

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


class TestTreasuryCurveFromCsv(unittest.TestCase):
    def test_loads_expected_number_of_tenors(self):
        curve = TreasuryCurve.from_csv(os.path.join(DATA_DIR, "treasury_curve.csv"))
        self.assertEqual(len(curve.tenors), 11)
        self.assertEqual(len(curve.maturities), len(curve.yields))

    def test_maturities_are_sorted_ascending(self):
        curve = TreasuryCurve.from_csv(os.path.join(DATA_DIR, "treasury_curve.csv"))
        for i in range(len(curve.maturities) - 1):
            self.assertLessEqual(curve.maturities[i], curve.maturities[i + 1])

    def test_get_yield_returns_correct_value(self):
        curve = TreasuryCurve.from_csv(os.path.join(DATA_DIR, "treasury_curve.csv"))
        self.assertAlmostEqual(curve.get_yield("10Y"), 0.0415, places=6)

    def test_get_yield_raises_for_missing_tenor(self):
        curve = TreasuryCurve.from_csv(os.path.join(DATA_DIR, "treasury_curve.csv"))
        with self.assertRaises(ValueError):
            curve.get_yield("50Y")


class TestCurveShapeClassification(unittest.TestCase):
    def test_normal_curve(self):
        curve = TreasuryCurve()
        curve.tenors = ["1Y", "10Y"]
        curve.maturities = [1.0, 10.0]
        curve.yields = [0.030, 0.045]
        self.assertIn("Normal", curve.classify_shape())

    def test_inverted_curve(self):
        curve = TreasuryCurve()
        curve.tenors = ["1Y", "10Y"]
        curve.maturities = [1.0, 10.0]
        curve.yields = [0.050, 0.035]
        self.assertIn("Inverted", curve.classify_shape())

    def test_flat_curve(self):
        curve = TreasuryCurve()
        curve.tenors = ["1Y", "10Y"]
        curve.maturities = [1.0, 10.0]
        curve.yields = [0.040, 0.0405]
        self.assertIn("Flat", curve.classify_shape())


class TestCurveComparison(unittest.TestCase):
    def test_compare_to_reports_correct_bp_change(self):
        curve_now = TreasuryCurve()
        curve_now.tenors = ["1Y", "10Y"]
        curve_now.maturities = [1.0, 10.0]
        curve_now.yields = [0.040, 0.045]

        curve_prev = TreasuryCurve()
        curve_prev.tenors = ["1Y", "10Y"]
        curve_prev.maturities = [1.0, 10.0]
        curve_prev.yields = [0.038, 0.046]

        comparison = curve_now.compare_to(curve_prev)
        by_tenor = {row["tenor"]: row["change_bp"] for row in comparison}

        self.assertAlmostEqual(by_tenor["1Y"], 20.0, places=4)
        self.assertAlmostEqual(by_tenor["10Y"], -10.0, places=4)


if __name__ == "__main__":
    unittest.main()
