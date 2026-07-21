"""
pricing_engine.py
Author: Jun Shen

Prices a Bond given a flat yield-to-maturity, using the standard
fractional-period discounting convention (Fabozzi-style):

    Dirty Price = sum_{i=1}^{n} CF_i / (1 + y/m)^(i - 1 + w)

where w is the fraction of the current coupon period that remains between
settlement and the next coupon date, and i indexes the remaining coupons
in order (i = 1 for the next coupon).

Clean price is simply dirty price minus accrued interest.
"""


class PricingEngine:
    """
    Prices a single Bond object off of a flat yield-to-maturity.
    """

    def __init__(self, bond):
        self.bond = bond

    def price_from_yield(self, ytm, settlement_date):
        """
        Compute dirty price, clean price, and accrued interest for the
        bond at the given yield and settlement date.

        Parameters
        ----------
        ytm : float
            Annualized yield to maturity, decimal (0.045 = 4.5%), assumed
            to compound at the bond's coupon frequency.
        settlement_date : datetime.date

        Returns
        -------
        dict with keys: dirty_price, clean_price, accrued_interest
        """
        bond = self.bond
        m = bond.coupon_frequency
        coupon_payment = bond.coupon_payment()

        coupon_dates = bond.generate_coupon_dates()
        remaining_dates = [d for d in coupon_dates if d > settlement_date]

        if len(remaining_dates) == 0:
            # bond has already matured as of settlement
            return {"dirty_price": 0.0, "clean_price": 0.0, "accrued_interest": 0.0}

        # find the coupon period straddling settlement_date to get w
        previous_coupon = bond.issue_date
        for d in coupon_dates:
            if d > settlement_date:
                break
            previous_coupon = d

        next_coupon = remaining_dates[0]
        days_in_period = (next_coupon - previous_coupon).days
        days_to_next = (next_coupon - settlement_date).days

        if days_in_period <= 0:
            w = 0.0
        else:
            w = days_to_next / days_in_period

        dirty_price = 0.0
        for i, d in enumerate(remaining_dates):
            cash = coupon_payment
            if d == bond.maturity_date:
                cash += bond.face_value

            period_exponent = i + w
            discount_factor = 1.0 / ((1.0 + ytm / m) ** period_exponent)
            dirty_price += cash * discount_factor

        accrued = bond.accrued_interest(settlement_date)
        clean_price = dirty_price - accrued

        return {
            "dirty_price": dirty_price,
            "clean_price": clean_price,
            "accrued_interest": accrued,
        }
