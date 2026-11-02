# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario's column has one type in every batch file, whatever its batch-mates.

A ``column=`` shock that makes a whole-number column a decimal (``n * 1.5``)
is composed per batch, and the shocked column takes the type of every branch:
BASE's ``n`` was Int64 in a batch of its own and Float64 in a batch beside the
shocked scenario. So one scenario's type followed the batch size, and a
``return_full_grid`` directory held both types for one column and could not be
read as one dataset (``pl.scan_parquet`` raised a SchemaError). The type is
now the run's: a whole-number column any scenario of the plan shocks to a
double is a double in every batch file, its whole numbers exact.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, ScenarioRun
from gaspatchio.scenarios import AdditiveShock, MultiplicativeShock, Sum

if TYPE_CHECKING:
    from pathlib import Path

_BOOK = pl.DataFrame({"policy_id": [1, 2], "n": [3, 5], "x": [1.5, 2.5]})


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=2,
        frequency="monthly",
    )
    af.cf = af.n * 1.5 + af.x + af.month * 0.0
    af.pv = af.cf.list.sum()
    return af


def _run(
    shocks: dict[str, list[object]], batch_size: int, sink: Path
) -> dict[str, float]:
    plan = ScenarioRun(
        shocks=shocks,  # type: ignore[arg-type]
        aggregations=(Sum("pv").alias("t").over("scenario_id"),),
    )
    result = plan.run(
        ActuarialFrame(_BOOK),
        _model,
        batch_size=batch_size,
        return_full_grid=True,
        sink_dir=sink,
    )
    folded = result.aggregations["t"]
    assert isinstance(folded, pl.DataFrame)
    return dict(zip(folded["scenario_id"], folded["t"], strict=True))


_WIDENING: dict[str, list[object]] = {
    "BASE": [],
    "A": [],
    "UP": [MultiplicativeShock(factor=1.5, column="n")],
    "B": [],
}


@pytest.mark.parametrize("batch_size", [1, 2, 4])
def test_every_batch_file_carries_the_run_s_type(
    tmp_path: Path, batch_size: int
) -> None:
    totals = _run(_WIDENING, batch_size, tmp_path)

    files = sorted(tmp_path.glob("batch_*.parquet"))
    assert {str(pl.read_parquet_schema(f)["n"]) for f in files} == {"Float64"}
    whole = pl.scan_parquet(tmp_path / "batch_*.parquet").collect()
    base = whole.filter(pl.col("scenario_id") == "BASE").sort("policy_id")
    assert base["n"].to_list() == [3.0, 5.0]
    # By hand over three boundaries: (3 x 1.5 + 1.5) x 3 + (5 x 1.5 + 2.5) x 3
    # is 48; UP reads n x 1.5 first, (6.75 + 1.5) x 3 + (11.25 + 2.5) x 3.
    assert totals == {"BASE": 48.0, "A": 48.0, "UP": 66.0, "B": 48.0}


def test_a_shock_that_keeps_a_whole_number_keeps_its_type(tmp_path: Path) -> None:
    shocks: dict[str, list[object]] = {
        "BASE": [],
        "UP": [AdditiveShock(delta=1, column="n")],
    }

    _run(shocks, 1, tmp_path)

    files = sorted(tmp_path.glob("batch_*.parquet"))
    assert {str(pl.read_parquet_schema(f)["n"]) for f in files} == {"Int64"}
