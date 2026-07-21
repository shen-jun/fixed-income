"""
test_interpolation.py
Author: Jun Shen

Unit tests for LinearInterpolator, CubicSplineInterpolator,
NelsonSiegelModel, and NelsonSiegelSvenssonModel.
"""

import unittest

from src.interpolation import (
    LinearInterpolator,
    CubicSplineInterpolator,
    NelsonSiegelModel,
    NelsonSiegelSvenssonModel,
)


class TestLinearInterpolator(unittest.TestCase):
    def setUp(self):
        self.maturities = [1, 2, 5, 10]
        self.yields = [0.03, 0.035, 0.04, 0.045]
        self.interp = LinearInterpolator(self.maturities, self.yields)

    def test_passes_through_known_points(self):
        for t, y in zip(self.maturities, self.yields):
            self.assertAlmostEqual(self.interp.interpolate(t), y, places=8)

    def test_midpoint_interpolation(self):
        # halfway between (1, 0.03) and (2, 0.035) should be 0.0325
        self.assertAlmostEqual(self.interp.interpolate(1.5), 0.0325, places=8)

    def test_flat_extrapolation_below_range(self):
        self.assertAlmostEqual(self.interp.interpolate(0.1), 0.03, places=8)

    def test_flat_extrapolation_above_range(self):
        self.assertAlmostEqual(self.interp.interpolate(20), 0.045, places=8)


class TestCubicSplineInterpolator(unittest.TestCase):
    def setUp(self):
        self.maturities = [1, 2, 3, 5, 7, 10, 20, 30]
        self.yields = [0.038, 0.037, 0.0365, 0.0368, 0.0375, 0.0385, 0.0410, 0.0405]
        self.spline = CubicSplineInterpolator(self.maturities, self.yields)

    def test_passes_through_known_points(self):
        for t, y in zip(self.maturities, self.yields):
            self.assertAlmostEqual(self.spline.interpolate(t), y, places=6)

    def test_interpolated_value_is_reasonable(self):
        # value between two known points should not shoot off wildly
        # far from the neighboring yields
        mid_value = self.spline.interpolate(4.0)
        self.assertGreater(mid_value, 0.030)
        self.assertLess(mid_value, 0.045)

    def test_requires_minimum_points(self):
        with self.assertRaises(ValueError):
            CubicSplineInterpolator([1, 2], [0.03, 0.04])


class TestNelsonSiegelModel(unittest.TestCase):
    def test_calibration_reduces_fit_error(self):
        maturities = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
        yields = [0.0430, 0.0425, 0.0415, 0.0400, 0.0395, 0.0398,
                  0.0405, 0.0415, 0.0445, 0.0440]

        model = NelsonSiegelModel()

        def sse(m):
            return sum((m.yield_at(t) - y) ** 2 for t, y in zip(maturities, yields))

        error_before = sse(model)
        model.calibrate(maturities, yields)
        error_after = sse(model)

        self.assertLess(error_after, error_before)
        # a well-calibrated NS fit to a fairly smooth curve should be quite tight
        self.assertLess(error_after, 1e-4)

    def test_yield_at_is_finite_near_zero_maturity(self):
        model = NelsonSiegelModel(beta0=0.04, beta1=-0.01, beta2=0.01, tau=1.5)
        value = model.yield_at(0.0)
        self.assertTrue(value == value)  # not NaN


class TestNelsonSiegelSvenssonModel(unittest.TestCase):
    def test_calibration_reduces_fit_error(self):
        maturities = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
        yields = [0.0430, 0.0425, 0.0415, 0.0400, 0.0395, 0.0398,
                  0.0405, 0.0415, 0.0445, 0.0440]

        model = NelsonSiegelSvenssonModel()

        def sse(m):
            return sum((m.yield_at(t) - y) ** 2 for t, y in zip(maturities, yields))

        error_before = sse(model)
        model.calibrate(maturities, yields)
        error_after = sse(model)

        self.assertLess(error_after, error_before)
        self.assertLess(error_after, 1e-4)


if __name__ == "__main__":
    unittest.main()
