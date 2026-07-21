"""
curve.py
Author: Jun Shen

Loads and represents a U.S. Treasury par yield curve as a simple set of
parallel lists (tenor label, maturity in years, yield). Also provides a
basic curve-shape classifier (normal / inverted / flat) and a helper to
compare two curves tenor by tenor.

Note on methodology: this platform treats the loaded par yields as a
proxy for the discount/spot curve directly, rather than bootstrapping a
true zero-coupon curve from par yields. That is a simplification -- a
production desk would strip the par curve into zero rates first -- but
it keeps the curve-based pricing and key rate duration logic in this
project tractable while still being directionally correct. This is
called out again in the LaTeX report.
"""

import csv


class TreasuryCurve:
    """
    Represents a Treasury yield curve as three aligned lists: tenors,
    maturities (in years), and yields (decimal).
    """

    def __init__(self, name="Treasury Curve", as_of_date=None):
        self.name = name
        self.as_of_date = as_of_date
        self.tenors = []
        self.maturities = []
        self.yields = []

    @classmethod
    def from_csv(cls, filepath, name="Treasury Curve", as_of_date=None):
        curve = cls(name=name, as_of_date=as_of_date)
        with open(filepath, "r", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # sort by maturity in years just in case the CSV is not ordered
        rows.sort(key=lambda r: float(r["years"]))

        for row in rows:
            curve.tenors.append(row["tenor"])
            curve.maturities.append(float(row["years"]))
            curve.yields.append(float(row["yield"]))

        return curve

    def get_yield(self, tenor_label):
        for tenor, y in zip(self.tenors, self.yields):
            if tenor == tenor_label:
                return y
        raise ValueError(f"Tenor '{tenor_label}' not found in curve '{self.name}'")

    def classify_shape(self, flat_threshold_bp=25.0):
        """
        Very simple shape classifier based on the spread between the
        longest and shortest tenor on the curve. This is intentionally
        coarse -- real curve-shape analysis would look at the whole term
        structure, not just the two endpoints -- but it is enough to
        flag normal vs. inverted vs. roughly flat curves for reporting.
        """
        short_yield = self.yields[0]
        long_yield = self.yields[-1]
        spread_bp = (long_yield - short_yield) * 10000.0

        if spread_bp > flat_threshold_bp:
            return "Normal (upward-sloping)"
        elif spread_bp < -flat_threshold_bp:
            return "Inverted (downward-sloping)"
        else:
            return "Flat / mixed"

    def compare_to(self, other_curve):
        """
        Returns a list of dicts describing the yield change, in basis
        points, tenor by tenor, relative to another curve. Tenors that
        do not exist on both curves are skipped.
        """
        comparison = []
        for tenor, maturity, y in zip(self.tenors, self.maturities, self.yields):
            if tenor in other_curve.tenors:
                other_y = other_curve.get_yield(tenor)
                change_bp = (y - other_y) * 10000.0
                comparison.append({
                    "tenor": tenor,
                    "years": maturity,
                    "current_yield": y,
                    "previous_yield": other_y,
                    "change_bp": change_bp,
                })
        return comparison

    def __repr__(self):
        return f"TreasuryCurve(name={self.name}, tenors={self.tenors})"
