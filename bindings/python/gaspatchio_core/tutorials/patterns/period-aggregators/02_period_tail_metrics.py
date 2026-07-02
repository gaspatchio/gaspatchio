# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Per-period tail metrics: ``PeriodCTE`` (TVaR) and ``PeriodQuantile`` (VaR).

Regulatory capital is set by the *tail*, not the average. A reserve held against
"the worst 5% of outcomes" is a Conditional Tail Expectation (CTE / TVaR); a VaR
is a single quantile of the loss distribution. Both are *term structures* here —
one number per projection period — so a hedging desk can see *when* the tail
bites, not just by how much.

This script computes both on a known per-period loss set (20 policies) and
asserts against an independent NumPy oracle. Two conventions are load-bearing,
and BOTH are confirmed from source — getting them wrong gives a plausible-looking
but wrong number:

  1. ``PeriodCTE(level=L, direction)``: ``level`` is the *tail probability*, not
     a confidence level. ``cte`` (``_sketch.py`` cte()) averages 10 probe
     quantiles inside the tail of width ``L``. So the regulatory **CTE(95)** —
     mean of the worst 5% of losses — is ``PeriodCTE(level=0.05,
     direction="upper")`` (large values are bad losses), NOT
     ``PeriodCTE(level=0.95)``. ``level=0.95`` would average the *upper 95%* of
     the distribution (≈ the overall mean).

  2. ``PeriodCTE`` is a *probe-quantile average*, not an exact arithmetic mean of
     the worst-k values. The oracle below reproduces the SAME 10-probe formula in
     NumPy; the residual versus that oracle is DDSketch bucket-discretisation
     error (~tens of bp on this range — see the ``_sketch`` module docstring), so
     the assert uses a relative tolerance, not exact equality.

  3. ``PeriodQuantile(levels=...)`` (without ``.over()``) returns a plain
     ``dict[level -> np.ndarray]`` — one per-period vector per level. (Note: the
     prose in the running-at-scale reference describes a tidy ``{period, level,
     value}`` frame; the *implemented* un-partitioned shape is this dict — see
     ``PeriodQuantile.extract_output`` in ``_period_sketch.py``. We assert the
     shape the code actually returns.)

A clean ``uv run python 02_period_tail_metrics.py`` (exit 0, asserts pass) is
the test.

Reference: Hardy (2003) *Investment Guarantees* §9 (CTE / TVaR) and
Klugman, Panjer & Willmot, *Loss Models* (VaR / quantiles). DDSketch-backed
per-period aggregators live in ``gaspatchio_core/scenarios/_period_sketch.py``.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl

from gaspatchio_core import ActuarialFrame, run_aggregated
from gaspatchio_core.scenarios import PeriodCTE, PeriodQuantile

VALUATION_DATE = date(2025, 1, 1)
PROJECTION_MONTHS = 3
N_POLICIES = 20
CTE_LEVEL = 0.05  # tail probability -> regulatory CTE(95) = mean of worst 5%
N_PROBES = 10  # matches SignedSketch.cte's fixed probe count
CTE_REL_TOL = 5e-3  # DDSketch bucket-discretisation slack (observed ~tens of bp)


# 20 policies with distinct premiums/claims so each period's loss set is a known
# spread of values — the 5%/95% tail is well-defined with 20 observations.
MODEL_POINTS = pl.DataFrame(
    {
        "policy_id": list(range(1, N_POLICIES + 1)),
        "premium_pp": [float(100 + 10 * i) for i in range(N_POLICIES)],
        "claim_pp": [float(1 + i) for i in range(N_POLICIES)],
    },
)


def model_fn(af: ActuarialFrame) -> ActuarialFrame:
    """Project a monthly net-cashflow term structure per policy."""
    af = af.projection.set(
        valuation_date=VALUATION_DATE,
        until="term_months",
        until_value=PROJECTION_MONTHS,
        frequency="monthly",
    )
    af.projection_date = af.projection.period_dates()
    af.month = (af.projection_date.dt.year() - VALUATION_DATE.year) * 12 + (
        af.projection_date.dt.month() - VALUATION_DATE.month
    )
    af.premium_t = af.premium_pp + af.month * 0.0
    af.claim_t = af.claim_pp * af.month
    af.net_cf = af.premium_t - af.claim_t  # list column (per period)
    return af


def numpy_loss_matrix() -> np.ndarray:
    """Independent oracle: the ``net_cf`` matrix, shape (n_policies, n_periods)."""
    months = np.arange(PROJECTION_MONTHS + 1, dtype=np.float64)
    premium = MODEL_POINTS["premium_pp"].to_numpy()[:, None]
    claim = MODEL_POINTS["claim_pp"].to_numpy()[:, None]
    return premium - claim * months[None, :]


def _interp_quantile(sorted_vals: np.ndarray, q: float) -> float:
    """Linear order-statistic interpolation, matching ``SignedSketch.quantile``.

    Mirrors ``_interp_quantile`` in ``_sketch.py``: ``rank = q*(n-1)`` then
    linearly interpolate the bracketing ascending order statistics. This is the
    oracle the sketch must reproduce up to bucket-discretisation error.
    """
    n = sorted_vals.shape[0]
    rank = q * (n - 1)
    lo = max(0, min(int(rank), n - 1))
    hi = min(lo + 1, n - 1)
    if hi == lo:
        return float(sorted_vals[lo])
    return float(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (rank - lo))


def hand_cte_upper(values: np.ndarray, level: float) -> float:
    """Mean of 10 probe quantiles in the upper tail of width ``level``.

    Reproduces ``SignedSketch.cte(level, direction='upper')``:
    ``qs = [1 - level*(i+0.5)/n_probes for i in range(n_probes)]``, averaged.
    This is the upper-tail TVaR — the mean of the worst (largest) ``level``
    fraction of outcomes.
    """
    sv = np.sort(values)
    qs = [1.0 - level * (i + 0.5) / N_PROBES for i in range(N_PROBES)]
    return float(np.mean([_interp_quantile(sv, q) for q in qs]))


def main() -> None:
    matrix = numpy_loss_matrix()  # (n_policies, n_periods)
    n_periods = matrix.shape[1]

    aggregations = [
        # CTE(95) = mean of the worst 5% (upper tail) at each period.
        PeriodCTE("net_cf", level=CTE_LEVEL, direction="upper").alias("cte95"),
        # VaR term structure at the 5% and 95% quantiles.
        PeriodQuantile("net_cf", levels=(0.05, 0.95)).alias("var"),
    ]
    res = run_aggregated(model_fn, MODEL_POINTS, aggregations)

    cte95: np.ndarray = res.cte95  # np.ndarray — per-period TVaR
    var: dict[float, np.ndarray] = res.var  # dict{level -> per-period vector}

    # --- PeriodCTE: per period == hand probe-quantile CTE on that period's set ---
    expected_cte = np.array(
        [hand_cte_upper(matrix[:, t], CTE_LEVEL) for t in range(n_periods)],
        dtype=np.float64,
    )
    assert cte95.shape == (n_periods,), f"CTE vector wrong shape: {cte95.shape}"
    assert np.allclose(cte95, expected_cte, rtol=CTE_REL_TOL), (
        f"PeriodCTE {cte95} != hand probe-quantile CTE {expected_cte} "
        f"(rtol={CTE_REL_TOL})"
    )
    # The CTE of the worst tail must sit ABOVE the period median — a sanity
    # guard that we read the UPPER tail, not the body.
    medians = np.median(matrix, axis=0)
    assert np.all(cte95 > medians), "upper-tail CTE must exceed the median"

    # --- PeriodQuantile: dict{level -> per-period vector}; check shape + a value ---
    assert isinstance(var, dict), f"PeriodQuantile output is {type(var)}, expected dict"
    assert set(var.keys()) == {0.05, 0.95}, f"quantile levels: {set(var.keys())}"
    assert var[0.05].shape == (n_periods,), f"q05 vector shape {var[0.05].shape}"
    assert var[0.95].shape == (n_periods,), f"q95 vector shape {var[0.95].shape}"

    # Known quantile value at one period (period 0): hand order-stat interp.
    sv0 = np.sort(matrix[:, 0])
    expected_q95_p0 = _interp_quantile(sv0, 0.95)
    expected_q05_p0 = _interp_quantile(sv0, 0.05)
    assert abs(var[0.95][0] - expected_q95_p0) <= CTE_REL_TOL * abs(expected_q95_p0), (
        f"q95 period 0: {var[0.95][0]} != hand {expected_q95_p0}"
    )
    assert abs(var[0.05][0] - expected_q05_p0) <= CTE_REL_TOL * abs(expected_q05_p0), (
        f"q05 period 0: {var[0.05][0]} != hand {expected_q05_p0}"
    )
    # The 95% VaR must dominate the 5% VaR at every period (ordering sanity).
    assert np.all(var[0.95] > var[0.05]), "q95 must exceed q05 at every period"

    print("Period* tail metrics — CTE(95) (TVaR) and VaR term structures")
    print(f"  CTE(95) per period (worst 5% mean): {np.round(cte95, 2)}")
    print(f"    hand probe-quantile CTE:          {np.round(expected_cte, 2)}")
    print(f"  VaR 95% per period:                 {np.round(var[0.95], 2)}")
    print(f"  VaR  5% per period:                 {np.round(var[0.05], 2)}")
    print(f"  Periods:                            {n_periods}")


if __name__ == "__main__":
    main()
