# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Fold a portfolio to aggregates with ``run_aggregated`` — never hold it whole.

At portfolio scale, materialising every policy's cashflows OOMs. When the
deliverable is a *number* (a BEL, a portfolio PV) or a *vector* (a term
structure), you do not need the per-policy frame — you need the fold.

``run_aggregated`` slices ``model_points`` into batches, runs ``model_fn`` on
each batch, and immediately folds the result into per-period accumulators.
Peak memory is approximately one batch's working set, not the portfolio.

This script proves the fold is **exact**, not approximate:

  - ``Sum("pv_net_cf")`` folds the scalar PV across the portfolio. It must
    equal the same total computed by running ``model_fn`` on the full frame
    directly and summing the ``pv_net_cf`` column.
  - ``PeriodSum("net_cf")`` folds the per-period vector. It must equal the
    direct per-period column sum, element for element.

A clean ``uv run python 01_run_aggregated.py`` (exit 0, asserts pass) is the
test. The batched aggregate equals the full-frame aggregate to floating point.

Reference: batched aggregate-and-stream design (repo ``ref/41-backend-portability``,
GSP-89 / PR #111).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl

from gaspatchio_core import ActuarialFrame, run_aggregated
from gaspatchio_core.scenarios import PeriodSum, Sum

VALUATION_DATE = date(2025, 1, 1)
PROJECTION_MONTHS = 6


# A plain Polars DataFrame of model points — NOT an ActuarialFrame.
# ``run_aggregated`` hands each batch to ``model_fn`` as an ActuarialFrame
# internally; passing an ActuarialFrame here would be a type error.
MODEL_POINTS = pl.DataFrame(
    {
        "policy_id": [1, 2, 3, 4, 5],
        "premium_pp": [100.0, 200.0, 50.0, 80.0, 130.0],
        "claim_pp": [1.0, 3.0, 0.5, 0.8, 2.0],
    },
)


def model_fn(af: ActuarialFrame) -> ActuarialFrame:
    """Project a tiny monthly net-cashflow term structure per policy.

    ``net_cf`` is a list column (one element per projection period) and
    ``pv_net_cf`` is its scalar sum. The claim ramps with the month index so
    the term structure is non-trivial — a flat vector would make the
    per-period assertion vacuous.
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

    # Broadcast the scalar premium across periods; ramp the claim with month.
    af.premium_t = af.premium_pp + af.month * 0.0
    af.claim_t = af.claim_pp * af.month
    af.net_cf = af.premium_t - af.claim_t  # list column (per period)
    af.pv_net_cf = af.net_cf.list.sum()  # scalar (PV of the cashflow)
    return af


def main() -> None:
    # Every aggregator MUST carry .alias(name) — the alias becomes the
    # attribute you read off the result. A missing alias raises ValueError.
    aggregations = [
        Sum("pv_net_cf").alias("pv_net_cf"),  # scalar fold
        PeriodSum("net_cf").alias("net_cf"),  # per-period vector fold
    ]
    res = run_aggregated(model_fn, MODEL_POINTS, aggregations)

    # AggregatedResult is a frozen dataclass, NOT a DataFrame. Read by
    # attribute; never call .collect() on it.
    agg_pv: float = res.pv_net_cf  # float
    agg_period: np.ndarray = res.net_cf  # np.ndarray (one value per period)

    # Closed-form baseline: run model_fn on the full frame in one pass and
    # aggregate directly. The batched fold must reproduce this exactly.
    full = model_fn(ActuarialFrame(MODEL_POINTS)).collect()
    direct_pv = float(full["pv_net_cf"].sum())
    direct_period = np.asarray(full["net_cf"].to_list()).sum(axis=0)

    assert abs(agg_pv - direct_pv) < 1e-9, (
        f"scalar fold {agg_pv} != direct full-run total {direct_pv}"
    )
    assert np.allclose(np.asarray(agg_period), direct_period), (
        f"period fold {agg_period} != direct per-period sum {direct_period}"
    )

    print("run_aggregated — batched fold == full-frame aggregate (exact)")
    print(f"  Policies folded:     {res.n_policies}")
    print(f"  Projection periods:  {res.n_periods}")
    print(f"  Resolved batch size: {res.batch_size}")
    print(f"  Portfolio PV net CF: {agg_pv:>14,.4f}  (direct: {direct_pv:,.4f})")
    print(f"  Net CF term structure (per period): {np.asarray(agg_period)}")


if __name__ == "__main__":
    main()
