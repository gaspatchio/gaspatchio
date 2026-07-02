# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Interpolation and parametric extrapolation — beyond the default linear curve.

``01_curve_construction`` taught the default: linear-on-rates interpolation. Real
regulatory curves need more — a different shape between knots, or a smooth pull to
an ultimate rate beyond the last liquid point. ``Curve`` exposes the full method
set, and this script proves each one against its closed form or a published oracle:

  - ``interpolation="log_linear"`` — linear in **log-discount-factor** space
    (equivalently, piecewise-constant instantaneous forward rates). The standard
    money-market convention.
  - ``interpolation="pchip"`` — Fritsch-Carlson **monotone cubic Hermite**: a
    smooth C1 spline that is shape-preserving, so it never overshoots the way an
    unconstrained cubic spline can.
  - ``Curve.from_svensson(...)`` — the **Nelson-Siegel-Svensson** parametric form
    the Federal Reserve and ECB publish: six parameters, smooth at every horizon.
  - ``Curve.fit_smith_wilson(...)`` — the **EIOPA / Solvency II** extrapolation
    method: fit the liquid market, then pull smoothly to an Ultimate Forward Rate.

Every method recovers its input rates exactly at the knots; each is then checked
against an independent oracle (a hand-built formula or a published numeric value).
A clean ``uv run python 05_interpolation_methods.py`` (exit 0, asserts pass) is the
test.

References:
  - Svensson (1994), *Estimating and Interpreting Forward Interest Rates*; the
    Federal Reserve GSW nominal yield curve publishes NSS parameters.
  - Smith & Wilson (2001); EIOPA *Technical Documentation of the Methodology to
    Derive EIOPA's Risk-Free Interest Rate Term Structures*. Numeric oracle:
    lifelib ``economic_curves`` Smith-Wilson worked example (MIT-licensed; the
    spot values below are reproduced as factual fixtures, no code is copied).
  - Fritsch & Carlson (1980), *Monotone Piecewise Cubic Interpolation* (pchip).
  Source of truth for the conventions: ``gaspatchio_core/curves/_interpolation.py``,
  ``_svensson.py``, ``_smith_wilson.py``.
"""

from __future__ import annotations

import math

from gaspatchio_core import Curve

# An illustrative zero (spot) curve — annually-compounded rates by tenor in years.
TENORS = [1.0, 2.0, 5.0, 10.0]
ZERO_RATES = [0.020, 0.025, 0.030, 0.033]


def main() -> None:
    # === interpolation="log_linear" — linear in log-discount-factor space =====
    # log-DF(u) = -u * ln(1 + r(u)). Interpolate that linearly, convert back to a
    # spot rate. This keeps the instantaneous forward rate piecewise-constant.
    ll = Curve.from_zero_rates(tenors=TENORS, rates=ZERO_RATES, interpolation="log_linear")

    # 1) Recovers the input rates exactly at every knot.
    for tenor, rate in zip(TENORS, ZERO_RATES, strict=True):
        assert abs(ll.spot_rate(tenor) - rate) < 1e-12, (
            f"log_linear spot({tenor})={ll.spot_rate(tenor)} != knot {rate}"
        )

    # 2) Between knots, the log-DF is the straight-line blend. Build it by hand at
    #    t=3 (between the 2y and 5y knots) and require an exact match.
    def log_df(u: float, r: float) -> float:
        return -u * math.log(1.0 + r)

    t_mid = 3.0
    ld_lo = log_df(TENORS[1], ZERO_RATES[1])  # 2y
    ld_hi = log_df(TENORS[2], ZERO_RATES[2])  # 5y
    ld_t = ld_lo + (ld_hi - ld_lo) * (t_mid - TENORS[1]) / (TENORS[2] - TENORS[1])
    hand_ll = math.exp(ld_t) ** (-1.0 / t_mid) - 1.0
    assert abs(ll.spot_rate(t_mid) - hand_ll) < 1e-12, (
        f"log_linear spot({t_mid})={ll.spot_rate(t_mid)} != log-DF blend {hand_ll}"
    )

    # === interpolation="pchip" — monotone cubic Hermite (shape-preserving) =====
    pc = Curve.from_zero_rates(tenors=TENORS, rates=ZERO_RATES, interpolation="pchip")

    # 1) Passes through every knot exactly (a C1 Hermite interpolant must).
    for tenor, rate in zip(TENORS, ZERO_RATES, strict=True):
        assert abs(pc.spot_rate(tenor) - rate) < 1e-12, (
            f"pchip spot({tenor})={pc.spot_rate(tenor)} != knot {rate}"
        )

    # 2) Shape-preserving: on a strictly increasing rate grid every interpolated
    #    value stays inside its bracketing knots. An unconstrained cubic spline can
    #    overshoot below 0.025 or above 0.030 here — Fritsch-Carlson cannot.
    for t in (2.5, 3.0, 4.0, 4.9):
        assert ZERO_RATES[1] <= pc.spot_rate(t) <= ZERO_RATES[2], (
            f"pchip spot({t})={pc.spot_rate(t)} overshot [{ZERO_RATES[1]}, {ZERO_RATES[2]}]"
        )

    # === Curve.from_svensson — Nelson-Siegel-Svensson parametric form =========
    # Six parameters (level b0, slope b1, two curvature humps b2/b3 with decays
    # tau1/tau2). spot_rate is annually compounded: r_ann(t) = exp(r_cc(t)) - 1,
    # where r_cc is the continuously-compounded Svensson spot (1994, eq. 22).
    p = {"b0": 0.04, "b1": -0.01, "b2": 0.005, "b3": 0.002, "tau1": 1.5, "tau2": 10.0}
    nss = Curve.from_svensson(**p)

    def nss_cc(t: float) -> float:
        """Independent re-derivation of the continuously-compounded NSS spot rate."""
        x1, x2 = t / p["tau1"], t / p["tau2"]
        l1 = (1.0 - math.exp(-x1)) / x1
        c1 = l1 - math.exp(-x1)
        l2 = (1.0 - math.exp(-x2)) / x2
        c2 = l2 - math.exp(-x2)
        return p["b0"] + p["b1"] * l1 + p["b2"] * c1 + p["b3"] * c2

    for t in (0.5, 1.0, 5.0, 10.0, 30.0):
        expected = math.exp(nss_cc(t)) - 1.0
        assert abs(nss.spot_rate(t) - expected) < 1e-12, (
            f"NSS spot({t})={nss.spot_rate(t)} != eq.22 annual {expected}"
        )

    # Closed-form limits: short rate -> b0 + b1, long rate -> b0 (continuously
    # compounded), i.e. exp(b0+b1)-1 and exp(b0)-1 once annualised.
    assert abs(nss.spot_rate(1e-6) - (math.exp(p["b0"] + p["b1"]) - 1.0)) < 1e-4, (
        "NSS short-rate limit should approach exp(b0+b1)-1"
    )
    assert abs(nss.spot_rate(1e6) - (math.exp(p["b0"]) - 1.0)) < 1e-4, (
        "NSS long-rate limit should approach exp(b0)-1"
    )

    # === Curve.fit_smith_wilson — EIOPA / Solvency II extrapolation ===========
    # Fit the liquid knots, then pull smoothly to the Ultimate Forward Rate (UFR).
    # Oracle: lifelib economic_curves worked example (UFR=4%, alpha=0.15).
    sw_tenors = [1.0, 2.0, 4.0, 5.0, 6.0, 7.0]
    sw_rates = [0.01, 0.02, 0.03, 0.032, 0.035, 0.04]
    sw = Curve.fit_smith_wilson(tenors=sw_tenors, rates=sw_rates, ufr=0.04, alpha=0.15)

    # 1) Reproduces every liquid input knot.
    for tenor, rate in zip(sw_tenors, sw_rates, strict=True):
        assert abs(sw.spot_rate(tenor) - rate) < 1e-9, (
            f"Smith-Wilson spot({tenor})={sw.spot_rate(tenor)} != knot {rate}"
        )

    # 2) Matches the published lifelib spot rates inside the grid and extrapolated
    #    well beyond the last liquid point (7y) toward the UFR.
    assert abs(sw.spot_rate(3.0) - 0.0264236322) < 1e-9, "SW spot(3) != lifelib oracle"
    assert abs(sw.spot_rate(20.0) - 0.0506997613) < 1e-9, "SW spot(20) != lifelib oracle"

    print("Curve interpolation & extrapolation — every method matches its oracle")
    print(f"  knots (tenor, rate)       : {list(zip(TENORS, ZERO_RATES, strict=True))}")
    print(f"  linear      spot(3.0)     : {Curve.from_zero_rates(tenors=TENORS, rates=ZERO_RATES).spot_rate(3.0):.6f}")
    print(f"  log_linear  spot(3.0)     : {ll.spot_rate(3.0):.6f}")
    print(f"  pchip       spot(3.0)     : {pc.spot_rate(3.0):.6f}")
    print(f"  NSS         spot(5.0)     : {nss.spot_rate(5.0):.6f}  (from_svensson)")
    print(f"  Smith-Wilson spot(20.0)   : {sw.spot_rate(20.0):.6f}  (extrapolated to UFR)")


if __name__ == "__main__":
    main()
