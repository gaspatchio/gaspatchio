# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Partition the fold by a dimension with ``.over()`` — totals still reconcile.

A portfolio total is rarely the whole story: you want it split by product line,
fund, or scenario. ``.over(by)`` partitions an aggregator by a low-cardinality
column. A scalar aggregator like ``Sum`` then returns a ``{*by, alias}``
DataFrame — one row per partition — instead of a single float.

Partitioning must not change the arithmetic: summing a portfolio by product
line and then summing those subtotals must give back the un-partitioned
portfolio total. There is no double-counting and nothing dropped at the
boundaries.

This script proves that reconciliation:

  - ``Sum("pv_net_cf").over("product_line")`` returns a per-partition
    DataFrame.
  - The sum of the per-partition subtotals equals the un-partitioned portfolio
    total (computed by the same aggregator without ``.over()``), which in turn
    equals a direct full-frame run.

A clean ``uv run python 04_over_partition.py`` (exit 0, asserts pass) is the
test.

Reference: batched aggregate-and-stream design (repo ``ref/41-backend-portability``,
GSP-89 / PR #111).
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import ActuarialFrame, run_aggregated
from gaspatchio_core.scenarios import Sum

VALUATION_DATE = date(2025, 1, 1)
PROJECTION_MONTHS = 6


# Plain Polars DataFrame of model points with a partition key (product_line).
MODEL_POINTS = pl.DataFrame(
    {
        "policy_id": [1, 2, 3, 4, 5, 6],
        "product_line": ["TERM", "TERM", "ANNUITY", "ANNUITY", "TERM", "ANNUITY"],
        "premium_pp": [100.0, 200.0, 50.0, 80.0, 130.0, 90.0],
        "claim_pp": [1.0, 3.0, 0.5, 0.8, 2.0, 1.2],
    },
)


def model_fn(af: ActuarialFrame) -> ActuarialFrame:
    """Project a monthly net-cashflow term structure plus its scalar PV."""
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
    af.net_cf = af.premium_t - af.claim_t
    af.pv_net_cf = af.net_cf.list.sum()
    return af


def main() -> None:
    # Partitioned fold: Sum(...).over("product_line") returns a per-partition
    # DataFrame {product_line, pv_net_cf} rather than a single float.
    res_over = run_aggregated(
        model_fn,
        MODEL_POINTS,
        [Sum("pv_net_cf").alias("pv_net_cf").over("product_line")],
    )
    by_product: pl.DataFrame = res_over.pv_net_cf  # pl.DataFrame

    # Un-partitioned portfolio total (same aggregator, no .over()).
    res_total = run_aggregated(
        model_fn,
        MODEL_POINTS,
        [Sum("pv_net_cf").alias("pv_net_cf")],
    )
    portfolio_total: float = res_total.pv_net_cf  # float

    # Closed-form baseline: direct full-frame run.
    full = model_fn(ActuarialFrame(MODEL_POINTS)).collect()
    direct_total = float(full["pv_net_cf"].sum())

    # Reconciliation: partition subtotals must sum back to the portfolio total,
    # and that must match the direct full-run total.
    sum_of_partitions = float(by_product["pv_net_cf"].sum())

    assert abs(sum_of_partitions - portfolio_total) < 1e-9, (
        f"partition subtotals {sum_of_partitions} != portfolio total "
        f"{portfolio_total}"
    )
    assert abs(portfolio_total - direct_total) < 1e-9, (
        f"portfolio total {portfolio_total} != direct full-run total {direct_total}"
    )

    print("run_aggregated — partitioned fold reconciles to the portfolio total")
    print("  Per product line:")
    for row in by_product.sort("product_line").iter_rows(named=True):
        print(f"    {row['product_line']:<10} {row['pv_net_cf']:>14,.4f}")
    print(f"  Sum of partitions:  {sum_of_partitions:>14,.4f}")
    print(f"  Portfolio total:    {portfolio_total:>14,.4f}")
    print(f"  Direct full-run:    {direct_total:>14,.4f}")


if __name__ == "__main__":
    main()
