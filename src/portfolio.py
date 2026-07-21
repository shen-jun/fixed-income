"""
portfolio.py
Author: Jun Shen

Aggregates a set of bond holdings into portfolio-level analytics: market
value, weighted average yield, weighted duration, portfolio convexity,
portfolio DV01, portfolio KR01 (by key rate tenor), and each bond's
contribution to overall market value and DV01.

Convention: Bond.face_value is quoted per 100 (standard market price
quoting convention). PortfolioHolding.notional is the actual face amount
held in dollars (e.g. 5,000,000). Market value of a holding is therefore
(price_per_100 / 100) * notional.
"""

from src.pricing_engine import PricingEngine
from src.risk_measures import RiskMeasures, KeyRateDuration


class PortfolioHolding:
    """
    One position in the portfolio: a bond, the notional face amount held,
    the yield used to mark it, and the settlement/valuation date.
    """

    def __init__(self, bond, notional, ytm, settlement_date):
        self.bond = bond
        self.notional = notional
        self.ytm = ytm
        self.settlement_date = settlement_date


class Portfolio:
    def __init__(self, name="Treasury Portfolio"):
        self.name = name
        self.holdings = []

    def add_holding(self, holding):
        self.holdings.append(holding)

    def _holding_market_value(self, holding):
        engine = PricingEngine(holding.bond)
        price = engine.price_from_yield(holding.ytm, holding.settlement_date)["dirty_price"]
        return (price / 100.0) * holding.notional

    def market_value(self):
        total = 0.0
        for holding in self.holdings:
            total += self._holding_market_value(holding)
        return total

    def weighted_yield(self):
        total_mv = self.market_value()
        if total_mv == 0:
            return 0.0

        weighted_sum = 0.0
        for holding in self.holdings:
            mv = self._holding_market_value(holding)
            weight = mv / total_mv
            weighted_sum += weight * holding.ytm

        return weighted_sum

    def weighted_duration(self):
        total_mv = self.market_value()
        if total_mv == 0:
            return 0.0

        weighted_sum = 0.0
        for holding in self.holdings:
            engine = PricingEngine(holding.bond)
            risk = RiskMeasures(holding.bond, engine)
            mv = self._holding_market_value(holding)
            weight = mv / total_mv
            mod_duration = risk.modified_duration(holding.ytm, holding.settlement_date)
            weighted_sum += weight * mod_duration

        return weighted_sum

    def portfolio_convexity(self):
        total_mv = self.market_value()
        if total_mv == 0:
            return 0.0

        weighted_sum = 0.0
        for holding in self.holdings:
            engine = PricingEngine(holding.bond)
            risk = RiskMeasures(holding.bond, engine)
            mv = self._holding_market_value(holding)
            weight = mv / total_mv
            convexity = risk.convexity(holding.ytm, holding.settlement_date)
            weighted_sum += weight * convexity

        return weighted_sum

    def portfolio_dv01(self):
        """Sum of each holding's DV01, scaled from per-100 to actual notional."""
        total_dv01 = 0.0
        for holding in self.holdings:
            engine = PricingEngine(holding.bond)
            risk = RiskMeasures(holding.bond, engine)
            dv01_per_100 = risk.dv01(holding.ytm, holding.settlement_date)
            total_dv01 += dv01_per_100 * (holding.notional / 100.0)

        return total_dv01

    def portfolio_kr01(self, curve, interpolator_class, key_rate_tenors):
        """
        Aggregates KR01 across all holdings, by key rate tenor, scaled to
        each holding's notional. Returns a dict: tenor -> total dollar
        KR01 across the portfolio.
        """
        aggregated = {tenor: 0.0 for tenor in key_rate_tenors}

        for holding in self.holdings:
            krd_calc = KeyRateDuration(holding.bond, curve, interpolator_class, key_rate_tenors)
            result = krd_calc.compute(holding.settlement_date)
            for tenor, values in result["key_rate_results"].items():
                kr01_per_100 = values["KR01"]
                aggregated[tenor] += kr01_per_100 * (holding.notional / 100.0)

        return aggregated

    def contribution_by_bond(self):
        """
        Returns a list of per-holding dicts describing market value,
        weight, and dollar DV01 contribution, useful for a risk report
        broken out bond by bond.
        """
        total_mv = self.market_value()
        contributions = []

        for holding in self.holdings:
            engine = PricingEngine(holding.bond)
            risk = RiskMeasures(holding.bond, engine)

            mv = self._holding_market_value(holding)
            weight = mv / total_mv if total_mv != 0 else 0.0
            mod_duration = risk.modified_duration(holding.ytm, holding.settlement_date)
            dv01_per_100 = risk.dv01(holding.ytm, holding.settlement_date)
            dollar_dv01 = dv01_per_100 * (holding.notional / 100.0)

            contributions.append({
                "bond_id": holding.bond.bond_id,
                "market_value": mv,
                "weight": weight,
                "ytm": holding.ytm,
                "modified_duration": mod_duration,
                "dollar_dv01": dollar_dv01,
            })

        return contributions

    def summary(self):
        return {
            "name": self.name,
            "market_value": self.market_value(),
            "weighted_yield": self.weighted_yield(),
            "weighted_duration": self.weighted_duration(),
            "portfolio_convexity": self.portfolio_convexity(),
            "portfolio_dv01": self.portfolio_dv01(),
        }
