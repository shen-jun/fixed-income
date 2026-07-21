"""
dashboard.py
Author: Jun Shen

Streamlit dashboard that ties together every module in this project:
curve loading/visualization, interpolation method comparison, a bond
price/yield calculator, duration & convexity reporting, key rate
duration charting, parallel and non-parallel shock simulators, and a
portfolio risk summary.

Run with:
    streamlit run src/dashboard.py

This file is intentionally just a UI layer -- all of the actual math
lives in bond.py, pricing_engine.py, yield_solver.py, curve.py,
interpolation.py, risk_measures.py, shock_engine.py, and portfolio.py.
"""

import os
import sys
from datetime import date, datetime

import matplotlib.pyplot as plt
import streamlit as st

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


@st.cache_data
def load_curve():
    return TreasuryCurve.from_csv(
        os.path.join(DATA_DIR, "treasury_curve.csv"),
        name="Current Treasury Curve",
        as_of_date=SETTLEMENT_DATE,
    )


@st.cache_data
def load_previous_curve():
    return TreasuryCurve.from_csv(
        os.path.join(DATA_DIR, "treasury_curve_previous.csv"),
        name="Previous Treasury Curve",
    )


@st.cache_data
def load_bonds():
    import csv
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


def main():
    st.set_page_config(page_title="Fixed Income Analytics Platform", layout="wide")
    st.title("Fixed Income Analytics Platform")
    st.caption("Author: Jun Shen -- illustrative Treasury data, not a live market feed.")

    curve = load_curve()
    previous_curve = load_previous_curve()
    bonds = load_bonds()

    tabs = st.tabs([
        "Yield Curve",
        "Interpolation",
        "Bond Pricing",
        "Risk Measures",
        "Shock Simulator",
        "Portfolio",
    ])

    # ------------------------------------------------------------------
    # Tab 1: Yield curve
    # ------------------------------------------------------------------
    with tabs[0]:
        st.subheader("U.S. Treasury Yield Curve")
        st.write(f"Curve shape: **{curve.classify_shape()}**")

        fig, ax = plt.subplots()
        ax.plot(curve.maturities, [y * 100 for y in curve.yields], marker="o", label="Current")
        ax.plot(previous_curve.maturities, [y * 100 for y in previous_curve.yields],
                marker="o", linestyle="--", label="Previous")
        ax.set_xlabel("Maturity (years)")
        ax.set_ylabel("Yield (%)")
        ax.set_title("Treasury Par Curve")
        ax.legend()
        st.pyplot(fig)

        st.write("Tenor-by-tenor change vs. previous curve (bp):")
        comparison = curve.compare_to(previous_curve)
        st.table(comparison)

    # ------------------------------------------------------------------
    # Tab 2: Interpolation comparison
    # ------------------------------------------------------------------
    with tabs[1]:
        st.subheader("Yield Curve Interpolation Methods")

        linear = LinearInterpolator(curve.maturities, curve.yields)
        spline = CubicSplineInterpolator(curve.maturities, curve.yields)

        ns_model = NelsonSiegelModel()
        ns_model.calibrate(curve.maturities, curve.yields)

        nss_model = NelsonSiegelSvenssonModel()
        nss_model.calibrate(curve.maturities, curve.yields)

        query_points = [round(0.25 * i, 2) for i in range(1, 121)]  # 0.25y to 30y

        fig, ax = plt.subplots()
        ax.plot(curve.maturities, [y * 100 for y in curve.yields], "ko", label="Market Yields")
        ax.plot(query_points, [linear.interpolate(t) * 100 for t in query_points], label="Linear")
        ax.plot(query_points, [spline.interpolate(t) * 100 for t in query_points], label="Cubic Spline")
        ax.plot(query_points, [ns_model.yield_at(t) * 100 for t in query_points], label="Nelson-Siegel")
        ax.plot(query_points, [nss_model.yield_at(t) * 100 for t in query_points], label="NSS")
        ax.set_xlabel("Maturity (years)")
        ax.set_ylabel("Yield (%)")
        ax.legend()
        st.pyplot(fig)

        st.write("Nelson-Siegel fitted parameters:",
                  {"beta0": ns_model.beta0, "beta1": ns_model.beta1,
                   "beta2": ns_model.beta2, "tau": ns_model.tau})
        st.write("NSS fitted parameters:",
                  {"beta0": nss_model.beta0, "beta1": nss_model.beta1,
                   "beta2": nss_model.beta2, "beta3": nss_model.beta3,
                   "tau1": nss_model.tau1, "tau2": nss_model.tau2})

    # ------------------------------------------------------------------
    # Tab 3: Bond pricing calculator
    # ------------------------------------------------------------------
    with tabs[2]:
        st.subheader("Bond Price / Yield Calculator")

        bond_ids = [b.bond_id for b in bonds]
        selected_id = st.selectbox("Select bond", bond_ids)
        selected_bond = next(b for b in bonds if b.bond_id == selected_id)

        engine = PricingEngine(selected_bond)

        mode = st.radio("Input mode", ["Price from Yield", "Yield from Price"])

        if mode == "Price from Yield":
            ytm_input = st.slider("Yield to maturity (%)", 0.0, 10.0, 4.0, 0.05) / 100.0
            result = engine.price_from_yield(ytm_input, SETTLEMENT_DATE)
            st.write(f"Clean price: **{result['clean_price']:.4f}**")
            st.write(f"Dirty price: **{result['dirty_price']:.4f}**")
            st.write(f"Accrued interest: **{result['accrued_interest']:.4f}**")
        else:
            price_input = st.number_input("Target clean price", value=100.0)
            solver = YieldSolver(selected_bond, engine)
            solved_yield = solver.solve_yield(price_input, SETTLEMENT_DATE)
            st.write(f"Implied yield to maturity: **{solved_yield * 100:.4f}%**")

        st.write("Price / Yield curve for this bond:")
        yields_range = [y / 1000.0 for y in range(0, 100)]
        prices_range = [engine.price_from_yield(y, SETTLEMENT_DATE)["clean_price"] for y in yields_range]
        fig2, ax2 = plt.subplots()
        ax2.plot([y * 100 for y in yields_range], prices_range)
        ax2.set_xlabel("Yield (%)")
        ax2.set_ylabel("Clean Price")
        st.pyplot(fig2)

    # ------------------------------------------------------------------
    # Tab 4: Risk measures
    # ------------------------------------------------------------------
    with tabs[3]:
        st.subheader("Duration, Convexity, and Key Rate Duration")

        rows = []
        for bond in bonds:
            engine = PricingEngine(bond)
            risk = RiskMeasures(bond, engine)
            flat_yield = curve.yields[-1]  # placeholder flat yield assumption for the report
            mac_dur = risk.macaulay_duration(flat_yield, SETTLEMENT_DATE)
            mod_dur = risk.modified_duration(flat_yield, SETTLEMENT_DATE)
            dv01 = risk.dv01(flat_yield, SETTLEMENT_DATE)
            convexity = risk.convexity(flat_yield, SETTLEMENT_DATE)
            rows.append({
                "Bond": bond.bond_id,
                "Macaulay Duration": round(mac_dur, 3),
                "Modified Duration": round(mod_dur, 3),
                "DV01": round(dv01, 5),
                "Convexity": round(convexity, 3),
            })
        st.table(rows)

        st.write("Key Rate Duration for a selected bond:")
        krd_bond_id = st.selectbox("Bond for KRD", [b.bond_id for b in bonds], key="krd_bond")
        krd_bond = next(b for b in bonds if b.bond_id == krd_bond_id)
        key_rate_tenors = [0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
        krd_calc = KeyRateDuration(krd_bond, curve, CubicSplineInterpolator, key_rate_tenors)
        krd_result = krd_calc.compute(SETTLEMENT_DATE)

        tenors_plot = list(krd_result["key_rate_results"].keys())
        krd_values = [krd_result["key_rate_results"][t]["KRD"] for t in tenors_plot]
        fig3, ax3 = plt.subplots()
        ax3.bar([str(t) for t in tenors_plot], krd_values)
        ax3.set_xlabel("Key Rate Tenor (years)")
        ax3.set_ylabel("Key Rate Duration")
        st.pyplot(fig3)

    # ------------------------------------------------------------------
    # Tab 5: Shock simulator
    # ------------------------------------------------------------------
    with tabs[4]:
        st.subheader("Yield Curve Shock Simulator")

        shock_engine = ShockEngine(curve)
        shock_type = st.selectbox(
            "Shock type",
            ["Parallel", "Steepener", "Flattener", "Twist", "Butterfly"],
        )

        if shock_type == "Parallel":
            bp = st.slider("Parallel shock (bp)", -100, 100, 25, 5)
            shocked_yields = shock_engine.parallel_shock(bp)
        elif shock_type == "Steepener":
            short_bp = st.slider("Short end shock (bp)", -100, 100, -25, 5)
            long_bp = st.slider("Long end shock (bp)", -100, 100, 25, 5)
            shocked_yields = shock_engine.steepener(short_bp, long_bp)
        elif shock_type == "Flattener":
            short_bp = st.slider("Short end shock (bp)", -100, 100, 25, 5)
            long_bp = st.slider("Long end shock (bp)", -100, 100, -25, 5)
            shocked_yields = shock_engine.flattener(short_bp, long_bp)
        elif shock_type == "Twist":
            pivot = st.select_slider("Pivot tenor (years)", options=curve.maturities, value=5.0)
            short_bp = st.slider("Short side shock (bp)", -100, 100, -25, 5)
            long_bp = st.slider("Long side shock (bp)", -100, 100, 25, 5)
            shocked_yields = shock_engine.twist(pivot, short_bp, long_bp)
        else:
            belly = st.select_slider("Belly tenor (years)", options=curve.maturities, value=5.0)
            wing_bp = st.slider("Wing shock (bp)", -100, 100, 25, 5)
            belly_bp = st.slider("Belly shock (bp)", -100, 100, -25, 5)
            shocked_yields = shock_engine.butterfly(belly, wing_bp, belly_bp)

        fig4, ax4 = plt.subplots()
        ax4.plot(curve.maturities, [y * 100 for y in curve.yields], marker="o", label="Base")
        ax4.plot(curve.maturities, [y * 100 for y in shocked_yields], marker="o", label="Shocked")
        ax4.set_xlabel("Maturity (years)")
        ax4.set_ylabel("Yield (%)")
        ax4.legend()
        st.pyplot(fig4)

    # ------------------------------------------------------------------
    # Tab 6: Portfolio
    # ------------------------------------------------------------------
    with tabs[5]:
        st.subheader("Portfolio Risk Summary")

        portfolio = Portfolio(name="Sample Treasury Portfolio")
        flat_yield = curve.yields[-1]
        for bond in bonds:
            portfolio.add_holding(
                PortfolioHolding(bond, notional=5_000_000, ytm=flat_yield,
                                  settlement_date=SETTLEMENT_DATE)
            )

        summary = portfolio.summary()
        col1, col2, col3 = st.columns(3)
        col1.metric("Market Value", f"${summary['market_value']:,.0f}")
        col2.metric("Weighted Duration", f"{summary['weighted_duration']:.3f}")
        col3.metric("Portfolio DV01", f"${summary['portfolio_dv01']:,.2f}")

        st.write("Contribution by bond:")
        st.table(portfolio.contribution_by_bond())


if __name__ == "__main__":
    main()
