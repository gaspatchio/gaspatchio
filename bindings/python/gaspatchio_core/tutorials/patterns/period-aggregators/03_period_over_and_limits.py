# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Split a term structure by group with ``.over()`` — and the one guardrail.

A portfolio-level term structure is rarely the deliverable: capital and hedging
are reported *by segment* (product line, fund, rating band). ``.over(by)``
partitions a ``Period*`` aggregator by a low-cardinality column and returns a
tidy ``{*by, period, alias}`` DataFrame — one per-period vector per group.

This script proves the partitioned output is internally consistent and shows the
one documented limit:

  - ``PeriodMedian("net_cf").over("g")`` returns ``{g, period, net_cf_med}``.
    Each group's per-period vector must equal that group's hand-computed median,
    reconciled group by group against an independent NumPy oracle.
  - ``PeriodCTE(level=0.05).over("g")`` returns ``{g, period, net_cf_cte}`` and
    its tail must sit above the group median (upper-tail sanity).
  - **Guardrail:** ``PeriodQuantile(...).over("g")`` raises
    ``NotImplementedError`` — its multi-level ``dict`` output has no tidy
    single-column form, so the driver rejects it *early* (before any compute)
    rather than crashing mid-run. We catch it and assert it raised; the script
    does not crash.

A clean ``uv run python 03_period_over_and_limits.py`` (exit 0, asserts pass) is
the test.

Reference: ``.over()`` partitioning and the ``PeriodQuantile.over()`` rejection
live in ``gaspatchio_core/scenarios/_aggregated.py`` (``_reject_multi_level_over``).
CTE / quantile risk measures: Hardy (2003) *Investment Guarantees* §9 and
Klugman, Panjer & Willmot, *Loss Models*.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl

from gaspatchio_core import ActuarialFrame, run_aggregated
from gaspatchio_core.scenarios import PeriodCTE, PeriodMedian, PeriodQuantile

VALUATION_DATE = date(2025, 1, 1)
PROJECTION_MONTHS = 3
CTE_REL_TOL = 5e-3  # DDSketch bucket-discretisation slack
GROUP_SIZE = 9  # odd -> the median is an exact order statistic (no interpolation)


# Two groups of 9 policies each. An odd group size makes each group's median a
# genuine member of the set, so the hand oracle is exact (no interpolation).
def _make_points() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    pid = 1
    for group, base in (("A", 100.0), ("B", 500.0)):
        for i in range(GROUP_SIZE):
            rows.append(
                {
                    "policy_id": pid,
                    "g": group,
                    "premium_pp": base + 10.0 * i,
                    "claim_pp": float(1 + i),
                },
            )
            pid += 1
    return pl.DataFrame(rows)


MODEL_POINTS = _make_points()


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


def group_loss_matrix(group: str) -> np.ndarray:
    """Independent oracle: the ``net_cf`` matrix for one group, (n_pol, n_periods)."""
    sub = MODEL_POINTS.filter(pl.col("g") == group)
    months = np.arange(PROJECTION_MONTHS + 1, dtype=np.float64)
    premium = sub["premium_pp"].to_numpy()[:, None]
    claim = sub["claim_pp"].to_numpy()[:, None]
    return premium - claim * months[None, :]


def main() -> None:
    n_periods = PROJECTION_MONTHS + 1

    # --- Partitioned PeriodMedian + PeriodCTE: tidy {g, period, alias} ---
    res = run_aggregated(
        model_fn,
        MODEL_POINTS,
        [
            PeriodMedian("net_cf").alias("net_cf_med").over("g"),
            PeriodCTE("net_cf", level=0.05, direction="upper")
            .alias("net_cf_cte")
            .over("g"),
        ],
    )
    med: pl.DataFrame = res.net_cf_med  # pl.DataFrame {g, period, net_cf_med}
    cte: pl.DataFrame = res.net_cf_cte  # pl.DataFrame {g, period, net_cf_cte}

    assert set(med.columns) == {"g", "period", "net_cf_med"}, (
        f"unexpected median columns: {med.columns}"
    )
    assert set(cte.columns) == {"g", "period", "net_cf_cte"}, (
        f"unexpected CTE columns: {cte.columns}"
    )

    # Reconcile each group's median vector against the NumPy oracle.
    for group in ("A", "B"):
        matrix = group_loss_matrix(group)  # (group_size, n_periods)
        expected_med = np.median(matrix, axis=0)  # exact (odd group size)
        got_med = (
            med.filter(pl.col("g") == group).sort("period")["net_cf_med"].to_numpy()
        )
        assert got_med.shape == (n_periods,), (
            f"group {group} median shape {got_med.shape}"
        )
        assert np.allclose(got_med, expected_med, rtol=CTE_REL_TOL), (
            f"group {group} median {got_med} != NumPy median {expected_med}"
        )
        # The upper-tail CTE of the group must exceed the group median.
        got_cte = (
            cte.filter(pl.col("g") == group).sort("period")["net_cf_cte"].to_numpy()
        )
        assert np.all(got_cte > expected_med), (
            f"group {group}: upper-tail CTE {got_cte} must exceed median {expected_med}"
        )

    # --- Guardrail: PeriodQuantile.over() raises NotImplementedError early ---
    raised = False
    try:
        run_aggregated(
            model_fn,
            MODEL_POINTS,
            [PeriodQuantile("net_cf", levels=(0.05, 0.95)).alias("var").over("g")],
        )
    except NotImplementedError as exc:
        raised = True
        message = str(exc)
    assert raised, "PeriodQuantile.over() should raise NotImplementedError but did not"
    assert "PeriodQuantile.over()" in message, f"unexpected message: {message}"

    print("Period* .over() — partitioned term structures reconcile per group")
    print("  PeriodMedian.over('g')  -> {g, period, net_cf_med}")
    print(med.sort(["g", "period"]))
    print("  PeriodCTE.over('g')     -> {g, period, net_cf_cte}")
    print(cte.sort(["g", "period"]))
    print(f"  Guardrail: PeriodQuantile.over() raised NotImplementedError: {raised}")


if __name__ == "__main__":
    main()
