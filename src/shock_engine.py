"""
shock_engine.py
Author: Jun Shen

Generates shocked yield curves (parallel and non-parallel) and evaluates
the resulting price impact on a bond, including a comparison of the
actual repriced impact against the duration-only and duration-plus-
convexity Taylor-series approximations.

Non-parallel shock shapes implemented:
  - steepener / flattener : ramp the shock linearly from the short end
                             to the long end of the curve
  - twist                 : rotate the curve around a pivot tenor, with
                             one sign on the short side and another on
                             the long side
  - butterfly              : shock the belly of the curve one way and
                             the wings (short + long ends) the other way,
                             tapering linearly in between
"""


class ShockEngine:
    def __init__(self, curve):
        self.curve = curve

    def parallel_shock(self, bp):
        """Shift every tenor on the curve by the same number of basis points."""
        shock = bp / 10000.0
        return [y + shock for y in self.curve.yields]

    def steepener(self, short_bp, long_bp):
        """
        Ramps the shock linearly from short_bp at the shortest tenor to
        long_bp at the longest tenor. Passing short_bp < 0 < long_bp
        produces a classic steepener; the reverse produces a flattener.
        """
        maturities = self.curve.maturities
        t_min = maturities[0]
        t_max = maturities[-1]

        new_yields = []
        for t, y in zip(maturities, self.curve.yields):
            if t_max == t_min:
                weight = 0.0
            else:
                weight = (t - t_min) / (t_max - t_min)
            shock_bp = short_bp + weight * (long_bp - short_bp)
            new_yields.append(y + shock_bp / 10000.0)

        return new_yields

    def flattener(self, short_bp, long_bp):
        """Same mechanics as steepener(); callers just pass the opposite signs."""
        return self.steepener(short_bp, long_bp)

    def twist(self, pivot_tenor, short_bp, long_bp):
        """
        Rotates the curve around pivot_tenor: tenors shorter than the
        pivot ramp from short_bp (at the shortest tenor) to 0 at the
        pivot, tenors longer than the pivot ramp from 0 at the pivot to
        long_bp at the longest tenor.
        """
        maturities = self.curve.maturities
        t_min = maturities[0]
        t_max = maturities[-1]

        new_yields = []
        for t, y in zip(maturities, self.curve.yields):
            if t <= pivot_tenor:
                if pivot_tenor == t_min:
                    weight = 0.0
                else:
                    weight = (pivot_tenor - t) / (pivot_tenor - t_min)
                shock_bp = short_bp * weight
            else:
                if t_max == pivot_tenor:
                    weight = 0.0
                else:
                    weight = (t - pivot_tenor) / (t_max - pivot_tenor)
                shock_bp = long_bp * weight
            new_yields.append(y + shock_bp / 10000.0)

        return new_yields

    def butterfly(self, belly_tenor, wing_bp, belly_bp):
        """
        Shocks the wings (short and long end) by wing_bp and the belly
        (belly_tenor) by belly_bp, tapering linearly between them. A
        classic butterfly trade has wing_bp and belly_bp of opposite
        sign.
        """
        maturities = self.curve.maturities
        t_min = maturities[0]
        t_max = maturities[-1]

        new_yields = []
        for t, y in zip(maturities, self.curve.yields):
            if t <= belly_tenor:
                if belly_tenor == t_min:
                    weight = 1.0
                else:
                    weight = (t - t_min) / (belly_tenor - t_min)
                shock_bp = wing_bp + weight * (belly_bp - wing_bp)
            else:
                if t_max == belly_tenor:
                    weight = 0.0
                else:
                    weight = (t - belly_tenor) / (t_max - belly_tenor)
                shock_bp = belly_bp + weight * (wing_bp - belly_bp)
            new_yields.append(y + shock_bp / 10000.0)

        return new_yields

    @staticmethod
    def evaluate_flat_yield_shock(pricing_engine, risk_measures, ytm_base,
                                   ytm_shocked, settlement_date):
        """
        Applies a shock directly to a bond's flat YTM (used for the
        parallel-shock-on-a-single-bond case) and compares the actual
        repriced impact to the duration-only and duration+convexity
        Taylor approximations:

            actual %change      = (P(y+dy) - P(y)) / P(y)
            duration approx     = -ModDur * dy
            dur + convexity     = -ModDur * dy + 0.5 * Convexity * dy^2
        """
        price_before = pricing_engine.price_from_yield(ytm_base, settlement_date)["dirty_price"]
        price_after = pricing_engine.price_from_yield(ytm_shocked, settlement_date)["dirty_price"]

        pnl = price_after - price_before
        pct_change_actual = pnl / price_before if price_before != 0 else 0.0

        mod_duration = risk_measures.modified_duration(ytm_base, settlement_date)
        convexity = risk_measures.convexity(ytm_base, settlement_date)
        dy = ytm_shocked - ytm_base

        pct_change_duration_only = -mod_duration * dy
        pct_change_dur_convexity = -mod_duration * dy + 0.5 * convexity * (dy ** 2)

        return {
            "price_before": price_before,
            "price_after": price_after,
            "pnl": pnl,
            "pct_change_actual": pct_change_actual,
            "pct_change_duration_approx": pct_change_duration_only,
            "pct_change_duration_convexity_approx": pct_change_dur_convexity,
        }
