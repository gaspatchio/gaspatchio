# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Build a yield curve from market rates and query it — spot, DF, forward.

A flat discount rate is the wrong shape for any regulatory valuation: EIOPA,
Solvency II and IFRS 17 all hand you a *term structure* — a different zero rate
at each tenor. ``Curve`` is the typed primitive that carries that grid of
``(tenor, zero_rate)`` knots and answers three questions at any horizon:

  - ``spot_rate(t)``       — the zero rate to discount a single cashflow at ``t``.
  - ``discount_factor(t)`` — the present value of 1 paid at ``t``.
  - ``forward_rate(t1=, t2=)`` — the implied rate for the window ``t1 → t2``.

This script proves each query against its closed form, grounded from the source
(``curves/_curve.py``), not a textbook variant:

  - ``discount_factor(t)`` is **annually compounded**: ``DF(t) = (1 + r(t))^(-t)``
    (``_curve.py:657`` docstring, ``:701`` implementation). ``DF(0) == 1.0``.
  - ``spot_rate`` interpolates **linearly on rates** between knots, with flat
    extrapolation outside the grid (``_curve.py:604`` / ``_interpolation.py``).
  - ``from_par_rates`` runs a coupon-stripping **bootstrap** (``_bootstrap.py``);
    the derived zero curve must re-price the input par bonds back to par (1.0).

A clean ``uv run python 01_curve_construction.py`` (exit 0, asserts pass) is the
test.

Reference: Hull, *Options, Futures & Other Derivatives* (zero curves, forward
rates, bootstrapping); EIOPA risk-free-rate term structure (the regulatory input
shape). Source of truth for the conventions: ``gaspatchio_core/curves/_curve.py``.
"""

from __future__ import annotations

from gaspatchio_core import Curve

# An illustrative EUR-style zero (spot) curve — NOT official EIOPA data.
# Rates are annually-compounded zero rates indexed by tenor in years.
TENORS = [1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
ZERO_RATES = [0.028, 0.030, 0.033, 0.037, 0.039, 0.040]


def main() -> None:
    curve = Curve.from_zero_rates(tenors=TENORS, rates=ZERO_RATES)

    # --- discount_factor is the annually-compounded closed form ----------
    # DF(t) = (1 + r(t))^(-t). Check it at every knot against the formula
    # built from the curve's own spot rate — no separate magic constant.
    for tenor in TENORS:
        r = curve.spot_rate(tenor)
        closed_form = (1.0 + r) ** (-tenor)
        df = curve.discount_factor(tenor)
        assert abs(df - closed_form) < 1e-12, (
            f"DF({tenor})={df} != (1+{r})^(-{tenor})={closed_form}"
        )

    # DF at t=0 is 1.0 by definition — money today is worth exactly itself.
    assert curve.discount_factor(0.0) == 1.0, "DF(0) must be exactly 1.0"

    # --- spot_rate interpolates LINEARLY on rates between knots ----------
    # t=3.5 sits between the 2y knot (0.030) and the 5y knot (0.033). The
    # implementation interpolates on rates, so the value is the straight-line
    # blend — compute it by hand and require an exact match.
    t_mid = 3.5
    r_lo, r_hi = ZERO_RATES[1], ZERO_RATES[2]  # rates at 2y and 5y
    t_lo, t_hi = TENORS[1], TENORS[2]  # 2.0 and 5.0
    hand_interp = r_lo + (r_hi - r_lo) * (t_mid - t_lo) / (t_hi - t_lo)
    assert abs(curve.spot_rate(t_mid) - hand_interp) < 1e-12, (
        f"spot({t_mid})={curve.spot_rate(t_mid)} != linear blend {hand_interp}"
    )

    # --- forward_rate is consistent with the discount factors ------------
    # DF(t1) / DF(t2) = (1 + F(t1, t2))^(t2 - t1), so F is recoverable from
    # the two discount factors. Rebuild it by hand and require a match.
    t1, t2 = 2.0, 5.0
    df1 = curve.discount_factor(t1)
    df2 = curve.discount_factor(t2)
    hand_forward = (df1 / df2) ** (1.0 / (t2 - t1)) - 1.0
    fwd = curve.forward_rate(t1=t1, t2=t2)
    assert abs(fwd - hand_forward) < 1e-12, (
        f"forward({t1},{t2})={fwd} != DF-implied {hand_forward}"
    )

    # --- from_par_rates: bootstrap must re-price the par bonds to 1.0 ----
    # A par bond at tenor T pays coupon = par_rate each year and 1.0 at T. By
    # construction its price under the bootstrapped zero curve is par (1.0).
    par_tenors = [1.0, 2.0, 3.0, 4.0, 5.0]
    par_rates = [0.028, 0.030, 0.031, 0.032, 0.033]
    par_curve = Curve.from_par_rates(tenors=par_tenors, par_rates=par_rates)

    coupon = par_rates[-1]  # the 5y par coupon
    dfs = [par_curve.discount_factor(t) for t in par_tenors]
    reprice = coupon * sum(dfs) + dfs[-1]  # PV of coupons + redemption
    assert abs(reprice - 1.0) < 1e-9, (
        f"bootstrapped curve re-prices 5y par bond to {reprice}, not 1.0"
    )

    print("Curve construction — every query matches its closed form")
    print(f"  Knots (tenor, zero rate): {list(zip(TENORS, ZERO_RATES, strict=True))}")
    print(f"  spot_rate(3.5)          : {curve.spot_rate(t_mid):.6f}  (linear blend)")
    print(f"  discount_factor(10.0)   : {curve.discount_factor(10.0):.6f}")
    print(f"  discount_factor(0.0)    : {curve.discount_factor(0.0):.6f}  (== 1.0)")
    print(f"  forward_rate(2y -> 5y)  : {fwd:.6f}")
    print(f"  par bond re-price (5y)  : {reprice:.10f}  (== 1.0)")


if __name__ == "__main__":
    main()
