"""
run_demo.py
Author: Jun Shen

Command-line walkthrough of the whole platform, using the sample data in
data/bonds.csv and data/treasury_curve.csv. This is meant as both a
sanity check that everything wires together correctly and a readable
example of how to use each module. Run it with:

    python scripts/run_demo.py

from the project root.
"""

import csv
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.bond import Bond
from src.pricing_engine import PricingEngine
from src.yield_solver import YieldSolver
from src.curve import TreasuryCurve
from src.interpolation import (
    LinearInterpolator,
    CubicSplineInterpolator,
    NelsonSiegelModel,
    NelsonSiegelSvenssonModel,
)
from src.risk_measures import RiskMeasures, KeyRateDuration
from src.shock_engine import ShockEngine
from src.portfolio import Portfolio, PortfolioHolding

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SETTLEMENT_DATE = date(2025, 1, 15)


def load_bonds():
    bonds = []
    with open(os.path.join(DATA_DIR, "bonds.csv"), "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bond = Bond(
                bond_id=row["bond_id"],
                face_value=float(row["face_value"]),
                coupon_rate=float(row["coupon_rate"]),
                coupon_frequency=int(row["coupon_frequency"]),
                issue_date=datetime.strptime(row["issue_date"], "%Y-%m-%d").date(),
                maturity_date=datetime.strptime(row["maturity_date"], "%Y-%m-%d").date(),
                day_count=row["day_count"],
            )
            bonds.append(bond)
    return bonds


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main():
    bonds = load_bonds()
    curve = TreasuryCurve.from_csv(os.path.join(DATA_DIR, "treasury_curve.csv"),
                                    name="Current Curve", as_of_date=SETTLEMENT_DATE)
    previous_curve = TreasuryCurve.from_csv(os.path.join(DATA_DIR, "treasury_curve_previous.csv"),
                                             name="Previous Curve")

    # ------------------------------------------------------------------
    section("1. Curve summary")
    # ------------------------------------------------------------------
    print(f"Curve shape today: {curve.classify_shape()}")
    for row in curve.compare_to(previous_curve):
        print(f"  {row['tenor']:>4}  current={row['current_yield']*100:.2f}%  "
              f"previous={row['previous_yield']*100:.2f}%  change={row['change_bp']:+.1f}bp")

    # ------------------------------------------------------------------
    section("2. Bond pricing at market-implied yields")
    # ------------------------------------------------------------------
    for bond in bonds:
        engine = PricingEngine(bond)
        flat_yield = curve.yields[-1]
        result = engine.price_from_yield(flat_yield, SETTLEMENT_DATE)
        print(f"  {bond.bond_id:>8}  clean={result['clean_price']:.4f}  "
              f"dirty={result['dirty_price']:.4f}  accrued={result['accrued_interest']:.4f}")

    # ------------------------------------------------------------------
    section("3. Yield solver round trip (UST_10Y)")
    # ------------------------------------------------------------------
    ten_year = next(b for b in bonds if b.bond_id == "UST_10Y")
    engine = PricingEngine(ten_year)
    solver = YieldSolver(ten_year, engine)

    known_yield = 0.0415
    market_price = engine.price_from_yield(known_yield, SETTLEMENT_DATE)["clean_price"]
    solved_yield = solver.solve_yield(market_price, SETTLEMENT_DATE)
    print(f"  Priced at yield {known_yield:.4%} -> clean price {market_price:.4f}")
    print(f"  Solved yield from that price: {solved_yield:.6%}")

    # ------------------------------------------------------------------
    section("4. Interpolation comparison at 15Y (not directly quoted)")
    # ------------------------------------------------------------------
    linear = LinearInterpolator(curve.maturities, curve.yields)
    spline = CubicSplineInterpolator(curve.maturities, curve.yields)

    ns_model = NelsonSiegelModel()
    ns_model.calibrate(curve.maturities, curve.yields)

    nss_model = NelsonSiegelSvenssonModel()
    nss_model.calibrate(curve.maturities, curve.yields)

    query_t = 15.0
    print(f"  Linear:         {linear.interpolate(query_t):.4%}")
    print(f"  Cubic Spline:   {spline.interpolate(query_t):.4%}")
    print(f"  Nelson-Siegel:  {ns_model.yield_at(query_t):.4%}")
    print(f"  NSS:            {nss_model.yield_at(query_t):.4%}")

    # ------------------------------------------------------------------
    section("5. Risk measures for every bond")
    # ------------------------------------------------------------------
    print(f"  {'Bond':>8}  {'MacDur':>8}  {'ModDur':>8}  {'DV01':>8}  {'Convexity':>10}")
    flat_yield = curve.yields[-1]
    for bond in bonds:
        bond_engine = PricingEngine(bond)
        bond_risk = RiskMeasures(bond, bond_engine)
        mac_dur = bond_risk.macaulay_duration(flat_yield, SETTLEMENT_DATE)
        mod_dur = bond_risk.modified_duration(flat_yield, SETTLEMENT_DATE)
        dv01 = bond_risk.dv01(flat_yield, SETTLEMENT_DATE)
        convexity = bond_risk.convexity(flat_yield, SETTLEMENT_DATE)
        print(f"  {bond.bond_id:>8}  {mac_dur:8.3f}  {mod_dur:8.3f}  {dv01:8.4f}  {convexity:10.3f}")

    # ------------------------------------------------------------------
    section("6. Key rate duration for UST_10Y")
    # ------------------------------------------------------------------
    key_rate_tenors = [0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
    krd_calc = KeyRateDuration(ten_year, curve, CubicSplineInterpolator, key_rate_tenors)
    krd_result = krd_calc.compute(SETTLEMENT_DATE)
    for tenor, values in krd_result["key_rate_results"].items():
        print(f"  {tenor:>5}Y  KRD={values['KRD']:8.4f}  KR01={values['KR01']:8.5f}")

    # ------------------------------------------------------------------
    section("7. Parallel and non-parallel shock scenarios")
    # ------------------------------------------------------------------
    shock_engine = ShockEngine(curve)
    risk = RiskMeasures(ten_year, engine)

    for bp in [25, 50, 100, -25, -50]:
        shocked_yield = flat_yield + bp / 10000.0
        result = shock_engine.evaluate_flat_yield_shock(
            engine, risk, flat_yield, shocked_yield, SETTLEMENT_DATE
        )
        print(f"  Parallel {bp:+4}bp: actual={result['pct_change_actual']:+.4%}  "
              f"dur_only={result['pct_change_duration_approx']:+.4%}  "
              f"dur+convex={result['pct_change_duration_convexity_approx']:+.4%}")

    steepener_curve = shock_engine.steepener(short_bp=-25, long_bp=25)
    flattener_curve = shock_engine.flattener(short_bp=25, long_bp=-25)
    twist_curve = shock_engine.twist(pivot_tenor=5.0, short_bp=-25, long_bp=25)
    butterfly_curve = shock_engine.butterfly(belly_tenor=5.0, wing_bp=25, belly_bp=-25)

    print("\n  Non-parallel scenario curves (10Y point):")
    idx_10y = curve.maturities.index(10.0)
    print(f"  Base:       {curve.yields[idx_10y]:.4%}")
    print(f"  Steepener:  {steepener_curve[idx_10y]:.4%}")
    print(f"  Flattener:  {flattener_curve[idx_10y]:.4%}")
    print(f"  Twist:      {twist_curve[idx_10y]:.4%}")
    print(f"  Butterfly:  {butterfly_curve[idx_10y]:.4%}")

    # ------------------------------------------------------------------
    section("8. Portfolio analytics")
    # ------------------------------------------------------------------
    portfolio = Portfolio(name="Sample Treasury Portfolio")
    for bond in bonds:
        portfolio.add_holding(
            PortfolioHolding(bond, notional=5_000_000, ytm=flat_yield,
                              settlement_date=SETTLEMENT_DATE)
        )

    summary = portfolio.summary()
    print(f"  Market Value:        ${summary['market_value']:,.2f}")
    print(f"  Weighted Yield:      {summary['weighted_yield']:.4%}")
    print(f"  Weighted Duration:   {summary['weighted_duration']:.4f}")
    print(f"  Portfolio Convexity: {summary['portfolio_convexity']:.4f}")
    print(f"  Portfolio DV01:      ${summary['portfolio_dv01']:,.2f}")

    print("\n  Contribution by bond:")
    for c in portfolio.contribution_by_bond():
        print(f"  {c['bond_id']:>8}  weight={c['weight']:6.2%}  "
              f"modDur={c['modified_duration']:6.3f}  dollarDV01=${c['dollar_dv01']:,.2f}")

    print("\nDemo complete.\n")


if __name__ == "__main__":
    main()
