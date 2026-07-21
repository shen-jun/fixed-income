# Fixed Income Analytics Platform

A fixed income analytics toolkit covering Treasury bond pricing, yield curve
construction and interpolation, duration/convexity/key-rate risk measures, curve shock
scenarios, and portfolio-level aggregation, wrapped in a Streamlit dashboard. Everything is
plain Python + `for` loops where the math actually happens -- there's no hidden vectorized
magic to reverse-engineer, which makes it easier to trust the numbers and easier to extend.

**A note on the data**: `data/bonds.csv` and `data/treasury_curve.csv` are illustrative,
hand-built sample data meant to look like a plausible Treasury curve and a small ladder of
Treasury securities. They are not pulled from a live market feed. Swap in real data and
everything downstream keeps working.

---

## 1. What this project actually does

At a high level, the platform answers five questions:

1. Given a bond's coupon, maturity, and a yield, what is it worth today (clean price, dirty
   price, accrued interest)? And working backwards -- given a market price, what yield does
   that imply?
2. Given a handful of market-quoted Treasury yields (3M, 2Y, 10Y, 30Y, etc.), what's a
   reasonable yield for a maturity that isn't directly quoted, like 15 years?
3. How sensitive is a bond's price to a change in yield -- both a small, linear sensitivity
   (duration) and the second-order correction to that (convexity)? And how sensitive is it to
   a move at just *one* point on the curve, rather than the whole curve moving together (key
   rate duration)?
4. If the curve moves in some specific way -- up 25bp everywhere, or the front end rallies
   while the back end sells off (a steepener), or the belly of the curve outperforms the wings
   (a butterfly) -- what happens to a bond's price, and how does the actual repricing compare
   to the duration/convexity approximation?
5. Roll all of that up across a basket of bonds into portfolio-level numbers: market value,
   weighted yield, weighted duration, portfolio DV01, and how much each bond is contributing
   to the total.

Everything in `src/` maps directly onto one of these five questions.

---

## 2. Project layout

```
fixed-income/
├── README.md                  <- this file
├── requirements.txt
├── src/
│   ├── bond.py                <- Bond class: coupon schedule, cashflows, accrued interest
│   ├── pricing_engine.py      <- prices a Bond off a flat yield
│   ├── yield_solver.py        <- inverts pricing_engine (price -> yield) via bisection
│   ├── curve.py                <- TreasuryCurve: loads yields, classifies curve shape
│   ├── interpolation.py       <- Linear, Cubic Spline, Nelson-Siegel, NSS interpolators
│   ├── risk_measures.py       <- duration, convexity, DV01, key rate duration / KR01
│   ├── shock_engine.py        <- parallel + non-parallel curve shocks, P&L attribution
│   ├── portfolio.py           <- aggregates holdings into portfolio-level analytics
│   └── dashboard.py           <- Streamlit UI tying all of the above together
├── data/
│   ├── bonds.csv               <- 7 sample Treasury securities (bills, notes, bonds)
│   ├── treasury_curve.csv      <- sample current Treasury par curve
│   └── treasury_curve_previous.csv  <- sample curve from an earlier date, for comparison
├── scripts/
│   └── run_demo.py             <- end-to-end command-line walkthrough of every module
├── tests/
│   └── test_*.py               <- unit tests, one file per src/ module (57 tests total)
└── report/
    └── fixed_income_analytics_report.tex  <- full mathematical derivations + worked examples
```

None of the modules import each other in a tangled way -- the dependency graph is basically a
straight line:

```
bond.py -> pricing_engine.py -> yield_solver.py
                               -> risk_measures.py
curve.py -> interpolation.py -> risk_measures.py (KeyRateDuration)
                               -> shock_engine.py
risk_measures.py + pricing_engine.py -> portfolio.py
everything -> dashboard.py / scripts/run_demo.py
```

---

## 3. File-by-file walkthrough

### `src/bond.py` -- `Bond`

Represents one Treasury security: face value (quoted per 100, standard convention), annual
coupon rate, coupon frequency (2 for semiannual), issue date, and maturity date.

- `generate_coupon_dates()` builds the full coupon schedule by walking backward from the
  maturity date in fixed month steps until it reaches the issue date. This is done with plain
  month/year arithmetic (with day-clamping for short months), not a date-library shortcut.
- `generate_cashflows(settlement_date)` returns every coupon (plus principal at the final
  payment) that falls after the settlement date.
- `accrued_interest(settlement_date)` computes accrued interest using the
  fraction-of-period method: `coupon_payment * (days since last coupon / days in the current
  coupon period)`.

Treasury bills are represented as the same `Bond` class with `coupon_rate=0.0` -- the coupon
schedule still gets built, but every "coupon" pays zero, so the bond behaves exactly like a
zero-coupon instrument with only the final principal cashflow.

Only Actual/Actual is implemented as a day count convention (this is what Treasury notes and
bonds actually use). 30/360 is not implemented; adding it would mean writing an alternate
period-length calculation in `accrued_interest` and is a reasonable next feature if this
platform were extended to corporate or municipal bonds.

### `src/pricing_engine.py` -- `PricingEngine`

Takes a `Bond` and prices it given a flat yield-to-maturity, using the standard fractional-
period discounting formula (the same one you'd find in Fabozzi's *Bond Markets, Analysis, and
Strategies*):

```
Dirty Price = sum_i  CF_i / (1 + y/m)^(i - 1 + w)
```

where `w` is the fraction of the current coupon period remaining between settlement and the
next coupon, and `i` indexes the remaining coupons starting at 1. Clean price is dirty price
minus accrued interest. See section 3 of the LaTeX report for the full derivation and a
worked numeric example.

### `src/yield_solver.py` -- `YieldSolver`

Given a target clean price, solves for the yield that reproduces it, using bisection. Bond
price is a smooth, monotonically decreasing function of yield, so bisection is a safe choice
-- it doesn't need a derivative or a good starting guess, and it can't diverge the way
Newton-Raphson occasionally can on a bad initial point.

### `src/curve.py` -- `TreasuryCurve`

Loads a set of (tenor, maturity-in-years, yield) triples from CSV and offers:

- `classify_shape()` -- flags the curve as normal, inverted, or flat/mixed, based on the
  spread between the longest and shortest quoted tenor.
- `compare_to(other_curve)` -- tenor-by-tenor change in basis points against another curve
  (used to compare today's curve against a prior date).

One important simplification, documented again in the LaTeX report: this platform treats the
loaded par yields as a stand-in for the discount/spot curve directly, rather than bootstrapping
a true zero-coupon curve from par yields first. A production desk would strip the curve. Here,
using par yields as spot rates keeps the curve-pricing and key-rate-duration logic tractable
while still being directionally correct for a project of this scope.

### `src/interpolation.py` -- four interpolators

All four expose an `interpolate(t)` (or `yield_at(t)`) method that takes a maturity in years
and returns a yield:

- `LinearInterpolator` -- straight-line interpolation between the two bracketing curve points,
  flat extrapolation outside the curve's range.
- `CubicSplineInterpolator` -- a natural cubic spline (second derivative pinned to zero at
  both ends), solved with the standard tridiagonal system from numerical analysis textbooks
  (the same algorithm you'd find in Burden & Faires).
- `NelsonSiegelModel` -- the classic 3-factor parametric curve model (level, slope,
  curvature).
- `NelsonSiegelSvenssonModel` -- 4-factor extension with a second curvature term, useful when
  the curve has more than one hump.

Both Nelson-Siegel models are calibrated **without any external optimizer**. The trick (this
is the same approach Diebold and Li used): for a *fixed* tau, the model is linear in its beta
coefficients, so betas can be solved exactly by ordinary least squares. Calibration therefore
grid-searches over candidate tau values (and, for NSS, tau1/tau2 pairs), solves the OLS normal
equations at each grid point using a small hand-written Gaussian elimination routine
(`_solve_linear_system`), and keeps whichever tau gives the lowest sum of squared errors. This
avoids a scipy/numpy optimizer dependency entirely and is arguably more transparent about what
calibration is actually doing.

### `src/risk_measures.py` -- `RiskMeasures` and `KeyRateDuration`

`RiskMeasures` computes, for a single bond at a given flat yield:

- `macaulay_duration` -- cashflow-weighted average time to receipt of cashflows.
- `modified_duration` -- Macaulay duration adjusted for compounding frequency; the standard
  first-order approximation of % price change per unit change in yield.
- `dv01` -- dollar price change for a 1bp move, computed by *bumping the yield up and down and
  repricing* (central finite difference), not from a closed-form duration formula. This makes
  it a useful cross-check against the analytical duration number.
- `convexity` -- also computed by finite difference, and used as the second-order correction
  term in the Taylor expansion of price around a yield change.

`KeyRateDuration` computes sensitivity to a bump at *one specific point* on the curve rather
than a uniform move in a flat yield. Each bond cashflow is discounted using the curve yield
interpolated to that cashflow's own maturity, and a **triangular bump** is applied at each key
rate tenor -- full-size at that tenor, tapering linearly to zero at the neighboring key rate
tenors (this is the standard methodology used across the industry for KRD/KR01 reporting).
`RiskMeasures` validates at construction time that the `pricing_engine` you hand it was built
from the same `Bond` instance -- mixing up a bond and a pricing engine for a *different* bond
is an easy mistake to make and silently produces numbers that look plausible but are wrong, so
this is checked eagerly rather than left as a footgun.

### `src/shock_engine.py` -- `ShockEngine`

Generates shocked yield curves:

- `parallel_shock(bp)` -- shifts every tenor by the same number of basis points.
- `steepener(short_bp, long_bp)` / `flattener(...)` -- ramps the shock linearly from the short
  end to the long end (same mechanics, opposite sign convention depending on which you call
  it).
- `twist(pivot_tenor, short_bp, long_bp)` -- rotates the curve around a pivot point.
- `butterfly(belly_tenor, wing_bp, belly_bp)` -- shocks the belly one way and the wings
  (short + long ends) the other way, tapering in between.

`evaluate_flat_yield_shock(...)` is a static helper that applies a shock to a single bond's
flat yield and reports the actual repriced P&L alongside the duration-only and
duration-plus-convexity Taylor-series approximations, so you can see how much of the actual
move convexity captures that duration alone misses (this gap gets much more visible for larger
shocks -- see `report/fixed_income_analytics_report.tex` section 9 for a worked example).

### `src/portfolio.py` -- `Portfolio` and `PortfolioHolding`

`PortfolioHolding` pairs a `Bond` with a notional face amount (actual dollars, e.g.
5,000,000) and a mark-to-market yield. `Portfolio` aggregates a list of holdings into:

- market value, weighted average yield, weighted (modified) duration, portfolio convexity
- portfolio DV01 (sum of each holding's DV01, scaled to notional)
- portfolio KR01 by key rate tenor
- `contribution_by_bond()` -- a per-holding breakdown of market value weight and dollar DV01
  contribution, which is the kind of table a risk report would actually show.

### `src/dashboard.py`

A Streamlit app with six tabs: yield curve view, interpolation method comparison, a bond
price/yield calculator, a duration/convexity/KRD report, a curve shock simulator, and a
portfolio risk summary. This file is UI plumbing only -- it doesn't do any math itself, it just
calls into the modules above and renders the results.

### `scripts/run_demo.py`

A plain command-line script that exercises every module against the sample data in `data/`
and prints results to the console. Good for a first sanity check without needing Streamlit
running, and useful as a readable reference for how the modules are meant to be wired together.

### `tests/`

One test file per `src/` module (`test_bond.py`, `test_curve.py`, `test_interpolation.py`,
`test_pricing_engine.py`, `test_yield_solver.py`, `test_risk_measures.py`,
`test_shock_engine.py`, `test_portfolio.py`), 57 tests in total. They check both specific
known values (e.g. a bond priced at a yield equal to its coupon, on a coupon date, must price
to exactly par) and general sanity properties (e.g. modified duration is always less than
Macaulay duration; convexity is always positive for a plain vanilla bond; portfolio weights
sum to 1).

### `report/fixed_income_analytics_report.tex`

The full mathematical writeup: bond pricing derivation, accrued interest, YTM solving, all
four interpolation methods (including the cubic spline's tridiagonal system derivation and the
Nelson-Siegel/NSS OLS calibration), duration and convexity derivations from the price/yield
relationship, key rate duration methodology, curve shock mechanics, and portfolio aggregation
formulas -- each section paired with a small numeric example that matches what the code
actually computes, not just the abstract formula.

---

## 4. How to run it

### Setup

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

(Note: none of the `src/` modules require numpy, scipy, or pandas -- `requirements.txt` only
lists what's actually needed: `matplotlib` for charts, `streamlit` for the dashboard, and
`pytest` for the test suite. The standard library covers everything else.)

### Run the unit tests

```bash
pytest tests/ -v
```

or, without pytest installed, the standard library test runner works too:

```bash
python3 -m unittest discover -s tests -v
```

### Run the command-line demo

```bash
python3 scripts/run_demo.py
```

This walks through curve loading, bond pricing, the yield solver, all four interpolation
methods, risk measures for every sample bond, key rate duration, parallel/non-parallel shock
scenarios, and portfolio analytics, printing results to the console.

### Launch the dashboard

```bash
streamlit run src/dashboard.py
```

Opens a browser tab with six tabs: Yield Curve, Interpolation, Bond Pricing, Risk Measures,
Shock Simulator, and Portfolio.

### Build the LaTeX report

```bash
cd report
pdflatex fixed_income_analytics_report.tex
pdflatex fixed_income_analytics_report.tex   # run twice for the table of contents / refs
```

---

## 5. Known simplifications

Worth being upfront about these, since they affect how far you can push the numbers:

- **Par yields used as spot rates.** No bootstrapping step converts the par curve into a true
  zero-coupon discount curve. For a curve that isn't too steep this doesn't move the numbers
  much, but it's not what a production curve-building pipeline would do.
- **Day count is Actual/Actual only.** Fine for Treasuries, not correct for instruments that
  use 30/360 or Actual/360.
- **Macaulay/modified duration use a flat-yield, whole-years-from-settlement formula**, which
  is the standard textbook treatment but is a slightly different (simpler) convention than the
  exact fractional-period pricing formula used in `pricing_engine.py`. DV01 and convexity are
  computed by direct bump-and-reprice finite difference, so they don't carry this
  simplification and can be used to cross-check the analytical duration numbers.
- **Key rate duration triangular bumps** are the standard industry approach, but the specific
  choice of key rate tenors (0.5Y, 1Y, 2Y, 5Y, 10Y, 20Y, 30Y in the sample data) is somewhat
  arbitrary and could be adjusted to match whatever risk system you're comparing against.
