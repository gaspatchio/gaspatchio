# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Batch size is a memory dial, not a results dial — the fold is invariant.

``batch_size`` controls how many policies ``run_aggregated`` holds in memory at
once. Smaller batches = lower peak RSS, more passes. It is purely a
memory/throughput trade-off: the aggregated *result* must be identical
regardless of how the portfolio is sliced, because summation is associative.

This script runs the SAME aggregation at ``batch_size`` 1, 7, and ``"auto"``
and proves batch-invariance:

  - All three produce an identical scalar fold ``res.pv_net_cf``.
  - All three produce an identical per-period vector ``res.net_cf``.

If these ever diverged, the fold would be order-dependent — a correctness bug.
They do not: batched == full, at every batch size.

THE ``"auto"`` GOTCHA. ``batch_size="auto"`` sizes batches from *host* RAM via
``psutil`` — it is **cgroup-blind**. In a container or CI runner with a memory
cap well below the host's RAM, ``"auto"`` will size to far more policies than
the cgroup allows and OOM. In CI/containers, pass an explicit integer
``batch_size`` derived from your cgroup limit (measure one batch at
``batch_size=100``, read ``res.peak_rss_mb``, scale from there).

A clean ``uv run python 03_batching.py`` (exit 0, asserts pass) is the test.

Reference: batched aggregate-and-stream design (repo ``ref/41-backend-portability``,
GSP-89 / PR #111); auto-batch cgroup-blindness is a documented limitation.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl

from gaspatchio_core import ActuarialFrame, run_aggregated
from gaspatchio_core.scenarios import PeriodSum, Sum

VALUATION_DATE = date(2025, 1, 1)
PROJECTION_MONTHS = 6


# Plain Polars DataFrame of model points — NOT an ActuarialFrame.
MODEL_POINTS = pl.DataFrame(
    {
        "policy_id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "premium_pp": [100.0, 200.0, 50.0, 80.0, 130.0, 90.0, 70.0, 160.0, 40.0, 110.0],
        "claim_pp": [1.0, 3.0, 0.5, 0.8, 2.0, 1.2, 0.9, 2.4, 0.3, 1.5],
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


def _aggregate(batch_size: int | str) -> tuple[float, np.ndarray, int]:
    """Run the standard aggregation at a given batch size; return the fold."""
    res = run_aggregated(
        model_fn,
        MODEL_POINTS,
        [Sum("pv_net_cf").alias("pv_net_cf"), PeriodSum("net_cf").alias("net_cf")],
        batch_size=batch_size,
    )
    return res.pv_net_cf, np.asarray(res.net_cf), res.batch_size


def main() -> None:
    # batch_size=1 forces one policy per pass (lowest peak RSS); 7 splits the
    # 10-policy portfolio across two uneven batches; "auto" sizes from RAM.
    pv_1, period_1, bs_1 = _aggregate(1)
    pv_7, period_7, bs_7 = _aggregate(7)
    pv_auto, period_auto, bs_auto = _aggregate("auto")

    # Batch-invariance: the fold is identical no matter how the portfolio is
    # sliced. Summation is associative, so order of accumulation cannot matter.
    assert abs(pv_1 - pv_7) < 1e-9, f"batch 1 PV {pv_1} != batch 7 PV {pv_7}"
    assert abs(pv_1 - pv_auto) < 1e-9, f"batch 1 PV {pv_1} != auto PV {pv_auto}"
    assert np.allclose(period_1, period_7), "batch 1 vs 7 term structure differs"
    assert np.allclose(period_1, period_auto), "batch 1 vs auto term structure differs"

    print("run_aggregated — fold is batch-invariant (memory dial only)")
    print(f"  batch_size=1     -> resolved {bs_1:>3}, PV {pv_1:>12,.4f}")
    print(f"  batch_size=7     -> resolved {bs_7:>3}, PV {pv_7:>12,.4f}")
    print(f"  batch_size=auto  -> resolved {bs_auto:>3}, PV {pv_auto:>12,.4f}")
    print(f"  Identical term structure: {period_1}")
    print("  NOTE: 'auto' reads HOST RAM, not the cgroup limit — pass an")
    print("        explicit int in containers/CI to avoid OOM.")


if __name__ == "__main__":
    main()
