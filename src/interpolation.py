"""
interpolation.py
Author: Jun Shen

Four ways of estimating a yield for a maturity that is not directly
quoted on the curve:

  1. LinearInterpolator      - straight-line interpolation between the two
                                bracketing tenors.
  2. CubicSplineInterpolator - natural cubic spline, solved with the
                                standard tridiagonal (Thomas algorithm)
                                approach from numerical analysis textbooks.
  3. NelsonSiegelModel       - 3-factor parametric term structure model,
                                calibrated to the curve by least squares.
  4. NelsonSiegelSvenssonModel - 4-factor extension of Nelson-Siegel that
                                adds a second hump/curvature term.

All interpolate()/yield_at() methods take a maturity in years and return
a yield as a decimal.

Nelson-Siegel and NSS calibration is done without any external
optimization library. Both models are linear in their beta coefficients
once tau (or tau1/tau2) is fixed, so calibration is done the way Diebold
and Li originally proposed it: grid-search over candidate tau values, and
for each candidate solve the beta coefficients by ordinary least squares
(normal equations), then keep whichever tau gives the lowest sum of
squared errors. The normal equations are solved with a small hand-rolled
Gaussian elimination routine (_solve_linear_system below) rather than a
linear algebra library call.
"""

import math


def _solve_linear_system(matrix, rhs):
    """
    Solve a small square linear system A x = b using Gaussian elimination
    with partial pivoting. matrix is a list of lists (n x n), rhs is a
    list of length n. Returns the solution vector x as a list.

    This is written out explicitly with loops (rather than delegating to
    a numerical library) since the systems here are tiny (3x3 or 4x4,
    one per grid point during Nelson-Siegel / NSS calibration).
    """
    n = len(matrix)
    augmented = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]

    for col in range(n):
        # partial pivot: swap in the row with the largest value in this column
        pivot_row = col
        largest = abs(augmented[col][col])
        for row in range(col + 1, n):
            if abs(augmented[row][col]) > largest:
                largest = abs(augmented[row][col])
                pivot_row = row
        if pivot_row != col:
            augmented[col], augmented[pivot_row] = augmented[pivot_row], augmented[col]

        pivot = augmented[col][col]
        if abs(pivot) < 1e-14:
            # nudge a near-singular pivot so we don't divide by ~zero
            augmented[col][col] += 1e-10
            pivot = augmented[col][col]

        for k in range(col, n + 1):
            augmented[col][k] /= pivot

        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            for k in range(col, n + 1):
                augmented[row][k] -= factor * augmented[col][k]

    return [augmented[i][n] for i in range(n)]


class LinearInterpolator:
    """
    Simple piecewise-linear interpolation across the curve's (maturity,
    yield) points. Flat extrapolation is used outside the curve's range.
    """

    def __init__(self, maturities, yields):
        if len(maturities) != len(yields):
            raise ValueError("maturities and yields must be the same length")
        self.maturities = list(maturities)
        self.yields = list(yields)

    def interpolate(self, t):
        maturities = self.maturities
        yields = self.yields
        n = len(maturities)

        if t <= maturities[0]:
            return yields[0]
        if t >= maturities[-1]:
            return yields[-1]

        for i in range(n - 1):
            t0 = maturities[i]
            t1 = maturities[i + 1]
            if t0 <= t <= t1:
                y0 = yields[i]
                y1 = yields[i + 1]
                if t1 == t0:
                    return y0
                weight = (t - t0) / (t1 - t0)
                return y0 + weight * (y1 - y0)

        # should not be reached given the bounds checks above
        raise RuntimeError("Failed to bracket maturity during linear interpolation")


class CubicSplineInterpolator:
    """
    Natural cubic spline (second derivative equals zero at both
    endpoints), fit using the standard tridiagonal solve described in
    Burden & Faires, Numerical Analysis. Coefficients are computed once
    in the constructor and reused for every interpolate() call.
    """

    def __init__(self, maturities, yields):
        if len(maturities) != len(yields):
            raise ValueError("maturities and yields must be the same length")
        if len(maturities) < 3:
            raise ValueError("cubic spline needs at least 3 points")

        self.x = list(maturities)
        self.y = list(yields)
        self.n = len(self.x)

        self.a, self.b, self.c, self.d = self._build_spline_coefficients()

    def _build_spline_coefficients(self):
        x = self.x
        y = self.y
        n = self.n

        h = [x[i + 1] - x[i] for i in range(n - 1)]

        # step 1: build the alpha values (right-hand side of the system)
        alpha = [0.0] * n
        for i in range(1, n - 1):
            alpha[i] = (3.0 / h[i]) * (y[i + 1] - y[i]) - (3.0 / h[i - 1]) * (y[i] - y[i - 1])

        # step 2: solve the tridiagonal system for c (second-derivative terms)
        l = [0.0] * n
        mu = [0.0] * n
        z = [0.0] * n
        l[0] = 1.0

        for i in range(1, n - 1):
            l[i] = 2.0 * (x[i + 1] - x[i - 1]) - h[i - 1] * mu[i - 1]
            mu[i] = h[i] / l[i]
            z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i]

        l[n - 1] = 1.0
        z[n - 1] = 0.0

        c = [0.0] * n
        b = [0.0] * (n - 1)
        d = [0.0] * (n - 1)
        a = y[:-1]

        # step 3: back-substitute to get b, c, d for each spline segment
        for j in range(n - 2, -1, -1):
            c[j] = z[j] - mu[j] * c[j + 1]
            b[j] = (y[j + 1] - y[j]) / h[j] - h[j] * (c[j + 1] + 2.0 * c[j]) / 3.0
            d[j] = (c[j + 1] - c[j]) / (3.0 * h[j])

        return a, b, c, d

    def interpolate(self, t):
        n = self.n
        x = self.x

        if t <= x[0]:
            segment = 0
        elif t >= x[-1]:
            segment = n - 2
        else:
            segment = n - 2
            for j in range(n - 1):
                if x[j] <= t <= x[j + 1]:
                    segment = j
                    break

        dx = t - x[segment]
        return (self.a[segment]
                + self.b[segment] * dx
                + self.c[segment] * dx ** 2
                + self.d[segment] * dx ** 3)


class NelsonSiegelModel:
    """
    Classic 3-factor Nelson-Siegel term structure model:

        y(t) = beta0 + beta1 * ((1 - exp(-t/tau)) / (t/tau))
                     + beta2 * (((1 - exp(-t/tau)) / (t/tau)) - exp(-t/tau))

    beta0 is the long-run level, beta1 the short-term slope component,
    beta2 the curvature/hump component, and tau controls where the hump
    is located along the maturity axis.
    """

    def __init__(self, beta0=0.04, beta1=-0.01, beta2=0.01, tau=1.5):
        self.beta0 = beta0
        self.beta1 = beta1
        self.beta2 = beta2
        self.tau = tau

    def _factor_loadings(self, t):
        if t <= 0:
            t = 1e-6
        term = t / self.tau
        decay = (1.0 - math.exp(-term)) / term
        curvature = decay - math.exp(-term)
        return decay, curvature

    def yield_at(self, t):
        decay, curvature = self._factor_loadings(t)
        return self.beta0 + self.beta1 * decay + self.beta2 * curvature

    def interpolate(self, t):
        # alias so this model can be used interchangeably with the
        # other interpolator classes
        return self.yield_at(t)

    def calibrate(self, maturities, yields, tau_grid=None):
        """
        Fit beta0, beta1, beta2, and tau to the observed curve.

        For a fixed tau, y(t) = beta0*1 + beta1*decay(t) + beta2*curvature(t)
        is a linear regression, so beta0/beta1/beta2 can be solved exactly
        by ordinary least squares. We therefore grid-search over tau,
        solving the OLS problem at each candidate value, and keep the tau
        (and corresponding betas) that gives the smallest sum of squared
        errors against the observed yields.
        """
        if tau_grid is None:
            tau_grid = [0.25 + 0.25 * i for i in range(0, 120)]  # 0.25 .. 30.0

        best_sse = None
        best_params = None

        for tau in tau_grid:
            design_rows = []
            for t in maturities:
                tt = t if t > 0 else 1e-6
                term = tt / tau
                decay = (1.0 - math.exp(-term)) / term
                curvature = decay - math.exp(-term)
                design_rows.append([1.0, decay, curvature])

            # build the normal equations X^T X beta = X^T y by hand
            xtx = [[0.0] * 3 for _ in range(3)]
            xty = [0.0] * 3
            for row, y_obs in zip(design_rows, yields):
                for i in range(3):
                    xty[i] += row[i] * y_obs
                    for j in range(3):
                        xtx[i][j] += row[i] * row[j]

            betas = _solve_linear_system(xtx, xty)

            sse = 0.0
            for row, y_obs in zip(design_rows, yields):
                y_model = betas[0] * row[0] + betas[1] * row[1] + betas[2] * row[2]
                sse += (y_model - y_obs) ** 2

            if best_sse is None or sse < best_sse:
                best_sse = sse
                best_params = (betas[0], betas[1], betas[2], tau)

        self.beta0, self.beta1, self.beta2, self.tau = best_params
        return {"sse": best_sse, "beta0": self.beta0, "beta1": self.beta1,
                "beta2": self.beta2, "tau": self.tau}


class NelsonSiegelSvenssonModel:
    """
    Nelson-Siegel-Svensson (NSS) extension: adds a second curvature term
    (beta3, tau2) so the model can fit curves with two humps, which is
    common for longer, more richly-populated term structures.

        y(t) = beta0
             + beta1 * ((1 - exp(-t/tau1)) / (t/tau1))
             + beta2 * (((1 - exp(-t/tau1)) / (t/tau1)) - exp(-t/tau1))
             + beta3 * (((1 - exp(-t/tau2)) / (t/tau2)) - exp(-t/tau2))
    """

    def __init__(self, beta0=0.04, beta1=-0.01, beta2=0.01, beta3=0.01,
                 tau1=1.5, tau2=5.0):
        self.beta0 = beta0
        self.beta1 = beta1
        self.beta2 = beta2
        self.beta3 = beta3
        self.tau1 = tau1
        self.tau2 = tau2

    def yield_at(self, t):
        if t <= 0:
            t = 1e-6

        term1 = t / self.tau1
        decay1 = (1.0 - math.exp(-term1)) / term1
        curvature1 = decay1 - math.exp(-term1)

        term2 = t / self.tau2
        decay2 = (1.0 - math.exp(-term2)) / term2
        curvature2 = decay2 - math.exp(-term2)

        return (self.beta0
                + self.beta1 * decay1
                + self.beta2 * curvature1
                + self.beta3 * curvature2)

    def interpolate(self, t):
        return self.yield_at(t)

    def calibrate(self, maturities, yields, tau1_grid=None, tau2_grid=None):
        """
        Same idea as NelsonSiegelModel.calibrate, extended to a 2D grid
        search over (tau1, tau2). For a fixed pair, y(t) is linear in
        beta0..beta3, so each grid point is solved by OLS (4x4 normal
        equations) and we keep the (tau1, tau2, betas) combination with
        the lowest sum of squared errors. Pairs where tau1 and tau2 are
        almost equal are skipped, since the two curvature terms become
        nearly collinear and the regression turns unstable.
        """
        if tau1_grid is None:
            tau1_grid = [0.25 + 0.25 * i for i in range(0, 40)]  # 0.25 .. 10.0
        if tau2_grid is None:
            tau2_grid = [1.0 + 1.0 * i for i in range(0, 30)]  # 1.0 .. 30.0

        best_sse = None
        best_params = None

        for tau1 in tau1_grid:
            for tau2 in tau2_grid:
                if abs(tau1 - tau2) < 0.1:
                    continue

                design_rows = []
                for t in maturities:
                    tt = t if t > 0 else 1e-6

                    term1 = tt / tau1
                    decay1 = (1.0 - math.exp(-term1)) / term1
                    curvature1 = decay1 - math.exp(-term1)

                    term2 = tt / tau2
                    decay2 = (1.0 - math.exp(-term2)) / term2
                    curvature2 = decay2 - math.exp(-term2)

                    design_rows.append([1.0, decay1, curvature1, curvature2])

                xtx = [[0.0] * 4 for _ in range(4)]
                xty = [0.0] * 4
                for row, y_obs in zip(design_rows, yields):
                    for i in range(4):
                        xty[i] += row[i] * y_obs
                        for j in range(4):
                            xtx[i][j] += row[i] * row[j]

                betas = _solve_linear_system(xtx, xty)

                sse = 0.0
                for row, y_obs in zip(design_rows, yields):
                    y_model = sum(betas[k] * row[k] for k in range(4))
                    sse += (y_model - y_obs) ** 2

                if best_sse is None or sse < best_sse:
                    best_sse = sse
                    best_params = (betas[0], betas[1], betas[2], betas[3], tau1, tau2)

        self.beta0, self.beta1, self.beta2, self.beta3, self.tau1, self.tau2 = best_params
        return {"sse": best_sse, "beta0": self.beta0, "beta1": self.beta1,
                "beta2": self.beta2, "beta3": self.beta3,
                "tau1": self.tau1, "tau2": self.tau2}
