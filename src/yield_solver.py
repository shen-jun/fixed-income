"""
yield_solver.py
Author: Jun Shen

Solves for the yield-to-maturity that reproduces a given market clean
price, using bisection. Bisection was chosen over Newton-Raphson because
bond price is a well-behaved, monotonically decreasing function of yield
over any sane range, so bisection converges reliably without needing an
analytical derivative or a good initial guess.
"""


class YieldSolver:
    """
    Solves for the yield that reprices a bond to a target clean price.
    """

    def __init__(self, bond, pricing_engine):
        self.bond = bond
        self.pricing_engine = pricing_engine

    def solve_yield(self, target_clean_price, settlement_date,
                     lower_bound=-0.50, upper_bound=1.00,
                     tolerance=1e-8, max_iterations=200):
        """
        Bisection search for YTM such that
        pricing_engine.price_from_yield(ytm, settlement_date)["clean_price"]
        equals target_clean_price, within tolerance.
        """
        low = lower_bound
        high = upper_bound

        price_low = self.pricing_engine.price_from_yield(low, settlement_date)["clean_price"]
        price_high = self.pricing_engine.price_from_yield(high, settlement_date)["clean_price"]

        # price is decreasing in yield, so price_low should be > target > price_high
        if not (price_high <= target_clean_price <= price_low):
            raise ValueError(
                "Target price is not bracketed by the given yield bounds. "
                f"price(low)={price_low:.4f}, price(high)={price_high:.4f}, "
                f"target={target_clean_price:.4f}"
            )

        mid = (low + high) / 2.0
        for _ in range(max_iterations):
            mid = (low + high) / 2.0
            result = self.pricing_engine.price_from_yield(mid, settlement_date)
            price_diff = result["clean_price"] - target_clean_price

            if abs(price_diff) < tolerance:
                return mid

            if price_diff > 0:
                # price too high means yield needs to go up (price falls as yield rises)
                low = mid
            else:
                high = mid

        return mid
