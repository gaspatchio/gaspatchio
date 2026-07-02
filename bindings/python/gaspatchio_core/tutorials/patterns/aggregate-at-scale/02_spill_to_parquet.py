# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Spill full per-policy output to parquet with ``run_to_parquet``.

When the deliverable is not a number but the *whole frame* — a regulatory
audit export, a downstream portfolio join, a transformation ``run_aggregated``
cannot express — you still cannot afford to hold the portfolio in memory.

``run_to_parquet`` runs ``model_fn`` in batches and writes each batch
immediately to ``output_dir/batch_NNNN.parquet``. The full portfolio is never
co-resident in memory; you read it back lazily with ``pl.scan_parquet`` and
let the query planner stream it.

This script proves spill round-trips losslessly:

  - The number of rows read back equals ``spill.n_policies``: every policy
    written, none duplicated or dropped across shards.
  - A column total over the read-back equals the same total from a direct
    full-frame run: the spilled values are the model's values, unaltered.

A clean ``uv run python 02_spill_to_parquet.py`` (exit 0, asserts pass) is the
test. Output is written under this script's own directory and cleaned up —
NOT under ``/tmp`` (on Linux ``run_to_parquet`` rejects RAM-backed
filesystems, and a full tmpfs re-OOMs the process anyway).

Reference: batched aggregate-and-stream design (repo ``ref/41-backend-portability``,
GSP-89 / PR #111).
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

import polars as pl

from gaspatchio_core import ActuarialFrame, run_to_parquet

VALUATION_DATE = date(2025, 1, 1)
PROJECTION_MONTHS = 6


# Plain Polars DataFrame of model points — NOT an ActuarialFrame.
MODEL_POINTS = pl.DataFrame(
    {
        "policy_id": [1, 2, 3, 4, 5, 6],
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
    # Spill destination: a fresh dir under THIS script's directory, never
    # /tmp. dir=... keeps tempfile off the (full) tmpfs.
    out = Path(tempfile.mkdtemp(dir=str(Path(__file__).parent), prefix="_spill_"))
    try:
        spill = run_to_parquet(model_fn, MODEL_POINTS, output_dir=out)

        # Read the spilled portfolio back lazily — no memory spike.
        scan = pl.scan_parquet(out / "*.parquet")
        readback_rows = scan.select(pl.len()).collect().item()
        readback_pv = scan.select(pl.col("pv_net_cf").sum()).collect().item()

        # Closed-form baseline: direct full-frame run.
        full = model_fn(ActuarialFrame(MODEL_POINTS)).collect()
        direct_pv = float(full["pv_net_cf"].sum())

        assert readback_rows == spill.n_policies, (
            f"read back {readback_rows} rows but spill reported "
            f"{spill.n_policies} policies"
        )
        assert abs(readback_pv - direct_pv) < 1e-9, (
            f"spilled PV total {readback_pv} != direct full-run total {direct_pv}"
        )

        print("run_to_parquet — spill round-trips losslessly")
        print(f"  Parquet shards written: {spill.n_batches}")
        print(f"  Policies written:       {spill.n_policies}")
        print(f"  Rows read back:         {readback_rows}")
        print(f"  PV net CF (read back):  {readback_pv:>14,.4f}  (direct: {direct_pv:,.4f})")
    finally:
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    main()
