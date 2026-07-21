"""
risk_measures.py
Author: Jun Shen

Bond-level interest rate risk measures:

  - Macaulay duration  : cashflow-weighted average time to receipt
  - Modified duration  : Macaulay duration adjusted for compounding, gives
                          approximate % price change per unit yield change
  - DV01 / dollar duration : dollar price change for a 1bp yield move,
                          computed by finite difference (bump and reprice)
  - Convexity          : second-order correction to the duration
                          approximation, also computed by finite difference
  - Key rate duration / KR01 : sensitivity of price to a bump at a single
                          point on the curve, holding the rest of the curve
                          fixed (triangular shock), rather than to a flat
                          parallel move in yield

Macaulay and modified duration use the standard flat-yield formulas
(cashflow time measured in years from settlement, discounted at the flat
YTM). This is a slightly simplified version of the exact fractional-period
pricing formula used in pricing_engine.py, which is the standard textbook
treatment and is consistent with how duration is quoted in practice. DV01
and convexity are computed by finite difference directly on the pricing
engine, so they do not carry this simplification and can be used as a
cross-check against the analytical duration numbers.
"""


class RiskMeasures:
    def __init__(self, bond, pricing_engine):
        if pricing_engine.bond is not bond:
            # this catches a real footgun: if the pricing_engine belongs
            # to a different bond than the one passed in here, the
            # cashflow weighting below and the pricing done inside
            # pricing_engine will quietly disagree with each other and
            # produce a duration/DV01 number that looks plausible but is
            # wrong. Better to fail loudly at construction time.
            raise ValueError(
                "pricing_engine must be built from the same bond instance "
                "passed to RiskMeasures (got a pricing_engine for "
                f"'{pricing_engine.bond.bond_id}' but bond='{bond.bond_id}')"
            )
        self.bond = bond
        self.pricing_engine = pricing_engine

    def macaulay_duration(self, ytm, settlement_date):
        bond = self.bond
        m = bond.coupon_frequency
        coupon_payment = bond.coupon_payment()

        coupon_dates = bond.generate_coupon_dates()
        remaining_dates = [d for d in coupon_dates if d > settlement_date]

        price_result = self.pricing_engine.price_from_yield(ytm, settlement_date)
        dirty_price = price_result["dirty_price"]

        if dirty_price <= 0:
            return 0.0

        weighted_time_sum = 0.0
        for d in remaining_dates:
            cash = coupon_payment
            if d == bond.maturity_date:
                cash += bond.face_value

            t_years = (d - settlement_date).days / 365.25
            n_periods = t_years * m
            discount_factor = 1.0 / ((1.0 + ytm / m) ** n_periods)
            pv = cash * discount_factor

            weighted_time_sum += t_years * pv

        return weighted_time_sum / dirty_price

    def modified_duration(self, ytm, settlement_date):
        mac_duration = self.macaulay_duration(ytm, settlement_date)
        m = self.bond.coupon_frequency
        return mac_duration / (1.0 + ytm / m)

    def dv01(self, ytm, settlement_date, bump=0.0001):
        """
        Dollar value of a 1bp move, per 100 face value, computed by
        central finite difference on the dirty price. Reported as a
        positive number representing the price decline for a +1bp move.
        """
        price_up = self.pricing_engine.price_from_yield(ytm + bump, settlement_date)["dirty_price"]
        price_down = self.pricing_engine.price_from_yield(ytm - bump, settlement_date)["dirty_price"]
        return (price_down - price_up) / 2.0

    def convexity(self, ytm, settlement_date, bump=0.0001):
        """
        Convexity via central finite difference on the dirty price:

            Convexity = (P(y+h) + P(y-h) - 2*P(y)) / (P(y) * h^2)
        """
        base_result = self.pricing_engine.price_from_yield(ytm, settlement_date)
        price_base = base_result["dirty_price"]
        price_up = self.pricing_engine.price_from_yield(ytm + bump, settlement_date)["dirty_price"]
        price_down = self.pricing_engine.price_from_yield(ytm - bump, settlement_date)["dirty_price"]

        if price_base == 0:
            return 0.0

        return (price_up + price_down - 2.0 * price_base) / (price_base * bump ** 2)


class KeyRateDuration:
    """
    Computes key rate duration (KRD) and key rate 01 (KR01) for a bond,
    given a curve and a set of key rate tenors. Each cashflow is
    discounted using the curve yield interpolated to that cashflow's
    maturity (i.e. the curve is used directly as a spot/discount curve --
    see the note in curve.py about this simplification).

    KRD at tenor T is computed by applying a triangular bump centered at
    T (tapering linearly to zero at the neighboring key rate tenors),
    repricing the bond, and taking the finite-difference sensitivity.
    """

    def __init__(self, bond, curve, interpolator_class, key_rate_tenors):
        self.bond = bond
        self.curve = curve
        self.interpolator_class = interpolator_class
        self.key_rate_tenors = sorted(key_rate_tenors)

    def price_with_curve(self, maturities, yields, settlement_date):
        interpolator = self.interpolator_class(maturities, yields)

        bond = self.bond
        m = bond.coupon_frequency
        coupon_payment = bond.coupon_payment()

        coupon_dates = bond.generate_coupon_dates()
        remaining_dates = [d for d in coupon_dates if d > settlement_date]

        price = 0.0
        for d in remaining_dates:
            cash = coupon_payment
            if d == bond.maturity_date:
                cash += bond.face_value

            t_years = (d - settlement_date).days / 365.25
            spot_rate = interpolator.interpolate(t_years)
            n_periods = t_years * m
            discount_factor = 1.0 / ((1.0 + spot_rate / m) ** n_periods)
            price += cash * discount_factor

        return price

    def _triangular_bump(self, maturities, key_tenor, bump):
        tenors = self.key_rate_tenors
        idx = tenors.index(key_tenor)
        left = tenors[idx - 1] if idx > 0 else None
        right = tenors[idx + 1] if idx < len(tenors) - 1 else None

        shocks = []
        for t in maturities:
            if t == key_tenor:
                weight = 1.0
            elif left is not None and left < t < key_tenor:
                weight = (t - left) / (key_tenor - left)
            elif right is not None and key_tenor < t < right:
                weight = (right - t) / (right - key_tenor)
            elif left is None and t < key_tenor:
                weight = 1.0
            elif right is None and t > key_tenor:
                weight = 1.0
            else:
                weight = 0.0
            shocks.append(weight * bump)
        return shocks

    def compute(self, settlement_date, bump=0.0001):
        maturities = self.curve.maturities
        base_yields = self.curve.yields
        base_price = self.price_with_curve(maturities, base_yields, settlement_date)

        results = {}
        for key_tenor in self.key_rate_tenors:
            up_shocks = self._triangular_bump(maturities, key_tenor, bump)
            down_shocks = self._triangular_bump(maturities, key_tenor, -bump)

            yields_up = [y + s for y, s in zip(base_yields, up_shocks)]
            yields_down = [y + s for y, s in zip(base_yields, down_shocks)]

            price_up = self.price_with_curve(maturities, yields_up, settlement_date)
            price_down = self.price_with_curve(maturities, yields_down, settlement_date)

            krd = (price_down - price_up) / (2.0 * bump * base_price) if base_price != 0 else 0.0
            kr01 = (price_down - price_up) / 2.0

            results[key_tenor] = {"KRD": krd, "KR01": kr01}

        return {"base_price": base_price, "key_rate_results": results}
