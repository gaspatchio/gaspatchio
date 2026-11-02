# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A policy-axis runner takes a book handed over as a LazyFrame.

``pl.scan_parquet`` hands back a LazyFrame, and a scenario plan already ran
over one (``ScenarioRun.run(ActuarialFrame(lazy), ...)``), while
``run_aggregated`` and ``run_to_parquet`` failed inside with ``'LazyFrame'
object has no attribute 'height'``. Each now collects the book at its door,
so the three runners take the same books and answer the same totals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import ScenarioRun, Sum, run_aggregated, run_to_parquet

if TYPE_CHECKING:
    from pathlib import Path


def _book() -> pl.DataFrame:
    return pl.DataFrame({"pid": [1, 2, 3], "amt": [2.0, 3.0, 4.0]})


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af.r = af.amt * 2
    return af


@pytest.mark.parametrize("batch_size", [1, 2])
def test_run_aggregated_takes_a_lazy_book(batch_size: int) -> None:
    """Hand value: 2 * (2 + 3 + 4) = 18, as the scenario plan answers."""
    result = run_aggregated(
        _model,
        _book().lazy(),
        aggregations=[Sum("r").alias("t")],
        batch_size=batch_size,
    )
    plan = ScenarioRun(shocks={"BASE": []}, aggregations=(Sum("r").alias("t"),))

    assert result.aggregations["t"] == 18.0
    assert plan.run(ActuarialFrame(_book().lazy()), _model).aggregations["t"] == 18.0


def test_run_to_parquet_takes_a_lazy_book(tmp_path: Path) -> None:
    result = run_to_parquet(_model, _book().lazy(), tmp_path, batch_size=2)
    written = pl.read_parquet(tmp_path / "*.parquet").sort("pid")

    assert result.n_policies == 3
    assert result.n_batches == 2
    assert written["r"].to_list() == [4.0, 6.0, 8.0]


def test_a_lazy_book_s_wide_column_that_fits_is_judged_over_the_book() -> None:
    """A UInt64 column whose values fit sums as the Int64 it is: 7 + 8 + 3."""
    book = _book().with_columns(pl.Series("n", [7, 8, 3], dtype=pl.UInt64))
    result = run_aggregated(
        _model, book.lazy(), aggregations=[Sum("n").alias("t")], batch_size=1
    )

    assert result.aggregations["t"] == 18.0


@pytest.mark.parametrize(
    ("runner", "call"),
    [
        (
            "run_aggregated",
            lambda book, _: run_aggregated(
                _model, book, aggregations=[Sum("r").alias("t")]
            ),
        ),
        ("run_to_parquet", lambda book, where: run_to_parquet(_model, book, where)),
    ],
    ids=["run_aggregated", "run_to_parquet"],
)
def test_a_book_of_another_type_is_refused_by_name(
    runner: str, call: object, tmp_path: Path
) -> None:
    with pytest.raises(TypeError, match=f"{runner}\\(\\) takes the model points"):
        call({"pid": [1]}, tmp_path)  # type: ignore[operator]
