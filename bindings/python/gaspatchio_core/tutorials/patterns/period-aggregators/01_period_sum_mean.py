# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scalar fold answers *how much*; a ``Period*`` fold answers *how much, when*.

A scalar ``Sum`` collapses the whole portfolio to one number — the present-day
total. That is the wrong shape for a cashflow profile: it hides the *term
structure*, the period-by-period vector that an asset-liability team actually
hedges against. ``PeriodSum`` and ``PeriodMean`` keep the time axis: they fold
the portfolio at *each* projection period and return a vector, one value per
period.

This script makes the contrast concrete on a tiny known portfolio:

  - ``Sum("pv_net_cf")`` returns a single float (the grand total across every
    policy and every period). The scalar ``Sum`` aggregator needs a *scalar*
    column, so the model first collapses ``net_cf`` to its PV via
    ``net_cf.list.sum()`` — a scalar ``Sum`` cannot reduce a ``list[f64]`` column
    directly.
  - ``PeriodSum("net_cf")`` returns a length-``n_periods`` vector — the portfolio
    net-cashflow term structure. This is the aggregator that reduces the *list*
    column at each period index.
  - ``PeriodMean("net_cf")`` returns the per-period average across policies.

The asserts are independent: we build the same ``net_cf`` matrix in plain NumPy
and check that ``PeriodSum``/``PeriodMean`` reproduce ``matrix.sum(axis=0)`` and
``matrix.mean(axis=0)`` exactly. Because ``net_cf`` ramps with the month index,
the vector is non-flat — a flat term structure would make the per-period
assertion vacuous.

A clean ``uv run python 01_period_sum_mean.py`` (exit 0, asserts pass) is the
test.

Reference: per-period (vector) aggregators sharing the Aggregator Protocol
(``gaspatchio_core/scenarios/_period_aggregators.py``). The term-structure
deliverable is the portfolio cashflow profile that drives ALM / liability
hedging.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl

from gaspatchio_core import ActuarialFrame, run_aggregated
from gaspatchio_core.scenarios import PeriodMean, PeriodSum, Sum

VALUATION_DATE = date(2025, 1, 1)
PROJECTION_MONTHS = 6


# A small known portfolio — five policies, exact hand arithmetic.
# net_cf(policy, month) = premium_pp - claim_pp * month, so the term structure
# ramps DOWN with month (claims grow) and differs per policy.
MODEL_POINTS = pl.DataFrame(
    {
        "policy_id": [1, 2, 3, 4, 5],
        "premium_pp": [100.0, 200.0, 50.0, 80.0, 130.0],
        "claim_pp": [1.0, 3.0, 0.5, 0.8, 2.0],
    },
)


def model_fn(af: ActuarialFrame) -> ActuarialFrame:
    """Project a monthly net-cashflow term structure per policy.

    ``net_cf`` is a list column (one element per projection period). The claim
    ramps with the month index so the term structure is genuinely non-flat.
    """
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
    af.premium_t = af.premium_pp + af.month * 0.0  # broadcast scalar across periods
    af.claim_t = af.claim_pp * af.month  # ramps with month -> non-flat
    af.net_cf = af.premium_t - af.claim_t  # list column (per period)
    af.pv_net_cf = af.net_cf.list.sum()  # scalar — collapses the term structure
    return af


def numpy_baseline() -> np.ndarray:
    """Build the ``net_cf`` matrix in pure NumPy: shape (n_policies, n_periods).

    This is the independent oracle — no Gaspatchio involved. The month index
    runs 0 .. PROJECTION_MONTHS, matching the projection grid produced inside
    ``model_fn`` (an inclusive endpoint gives PROJECTION_MONTHS + 1 periods).
    """
    months = np.arange(PROJECTION_MONTHS + 1, dtype=np.float64)
    premium = MODEL_POINTS["premium_pp"].to_numpy()[:, None]
    claim = MODEL_POINTS["claim_pp"].to_numpy()[:, None]
    return premium - claim * months[None, :]  # (n_policies, n_periods)


def main() -> None:
    aggregations = [
        Sum("pv_net_cf").alias("net_cf_total"),  # scalar: ONE number
        PeriodSum("net_cf").alias("net_cf_period"),  # vector: per-period total
        PeriodMean("net_cf").alias("net_cf_mean"),  # vector: per-period average
    ]
    res = run_aggregated(model_fn, MODEL_POINTS, aggregations)

    total: float = res.net_cf_total  # float — the grand total
    period_sum: np.ndarray = res.net_cf_period  # np.ndarray — term structure
    period_mean: np.ndarray = res.net_cf_mean  # np.ndarray — per-period average

    # Independent NumPy oracle.
    matrix = numpy_baseline()  # (n_policies, n_periods)
    expected_sum = matrix.sum(axis=0)  # per-period total
    expected_mean = matrix.mean(axis=0)  # per-period average
    expected_total = float(matrix.sum())  # grand total (all policies, all periods)

    # The scalar fold is ONE number; the period fold is a VECTOR. The scalar
    # equals the sum of the period vector — same data, different shape.
    assert abs(total - expected_total) < 1e-9, (
        f"scalar Sum {total} != NumPy grand total {expected_total}"
    )
    assert abs(total - float(period_sum.sum())) < 1e-9, (
        f"scalar Sum {total} != sum of PeriodSum vector {period_sum.sum()}"
    )
    assert np.allclose(period_sum, expected_sum), (
        f"PeriodSum {period_sum} != NumPy per-period sum {expected_sum}"
    )
    assert np.allclose(period_mean, expected_mean), (
        f"PeriodMean {period_mean} != NumPy per-period mean {expected_mean}"
    )
    # The term structure must NOT be flat — otherwise the per-period assert is
    # vacuous (any constant would pass a sum check).
    assert period_sum.std() > 1.0, "term structure is flat — assertion would be vacuous"

    print("Period* aggregators — scalar fold vs term structure")
    print(f"  Scalar Sum (ONE number):        {total:>14,.2f}")
    print(f"  PeriodSum  (vector, per period): {np.round(period_sum, 2)}")
    print(f"  PeriodMean (vector, per period): {np.round(period_mean, 2)}")
    print(
        f"  Sum of the PeriodSum vector:    {period_sum.sum():>14,.2f}  (== scalar Sum)"
    )
    print(f"  Periods in term structure:      {res.n_periods}")


if __name__ == "__main__":
    main()
