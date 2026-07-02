# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Build deterministic eval fixtures (tiny synthetic parquets).

Run::

    uv run python evals/fixtures/_build.py
"""

from pathlib import Path

import polars as pl

OUT = Path(__file__).resolve().parent


def build() -> None:
    """Write the model-points fixture used by the execute/numeric oracles."""
    (OUT / "building").mkdir(exist_ok=True)
    pts = pl.DataFrame({
        "Policy number": ["P1", "P2", "P3", "P4"],
        "sum_assured": [100000.0, 250000.0, 50000.0, 175000.0],
        "mortality_rate": [0.001, 0.004, 0.02, 0.008],
        "annual_premium": [400.0, 1500.0, 900.0, 1100.0],
    })
    pts.write_parquet(OUT / "building" / "model_points.parquet")

    (OUT / "reconciliation").mkdir(exist_ok=True)
    pts.write_parquet(OUT / "reconciliation" / "model_points.parquet")
    pts.select(
        (pl.col("sum_assured") * pl.col("mortality_rate")).alias("expected_claims")
    ).write_parquet(OUT / "reconciliation" / "reference.parquet")


if __name__ == "__main__":
    build()
    print("fixtures built")  # noqa: T201
