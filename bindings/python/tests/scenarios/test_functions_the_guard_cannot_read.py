# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A function the across-rows guard cannot read is refused where the frame is cut.

``af.res.polars_native().map_batches(lambda s: s.rank() / s.len())`` is a
percentile of the reserve: a read across rows. Polars will not hand a
Python function over to be read, so the guard saw nothing in it, and
``run_aggregated`` gave 110 over the whole book, 130 at ``batch_size=2``
and 150 at ``batch_size=1`` with nothing refused, where the same read
written as ``rank()`` was refused (audit C3a-F4). A plugin registered as
not elementwise is the same read in Rust. Both are now refused wherever
the frame is not the whole book, and stand where it is.
"""

from __future__ import annotations

import datetime
from fractions import Fraction
from typing import TYPE_CHECKING

import polars as pl
import pytest
from polars.plugins import register_plugin_function

from gaspatchio import ActuarialFrame, run_aggregated, run_to_parquet
from gaspatchio.frame.lowering._polars.plugins import _get_lib
from gaspatchio.scenarios import Sum

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

BOOK = pl.DataFrame(
    {
        "pid": [1, 2, 3, 4, 5],
        "res": [10.0, 20.0, 30.0, 40.0, 50.0],
        "term": [2] * 5,
    }
)

# The percentile loading over the whole book, by hand: reserve i carries
# rank i / 5.
HAND = float(
    sum(Fraction(r) * Fraction(i + 1, 5) for i, r in enumerate(range(10, 60, 10)))
)


def _rank_pct(s: pl.Series) -> pl.Series:
    return s.rank() / s.len()


def _timeline(af: ActuarialFrame) -> ActuarialFrame:
    return af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_years",
        until_value="term",
        frequency="annual",
    )


def through_map_batches(af: ActuarialFrame) -> ActuarialFrame:
    """Load by percentile, through ``map_batches`` on the explicit escape."""
    af = _timeline(af)
    af.pct = af.res.polars_native().map_batches(_rank_pct, return_dtype=pl.Float64)
    af.load = af.res * af.pct
    return af


def through_raw_map_batches(af: ActuarialFrame) -> ActuarialFrame:
    """Load by percentile, written as a raw Polars expression."""
    af = _timeline(af)
    af.pct = pl.col("res").map_batches(_rank_pct, return_dtype=pl.Float64)
    af.load = af.res * af.pct
    return af


def through_a_raw_operand(af: ActuarialFrame) -> ActuarialFrame:
    """Load by percentile, a raw fragment used as an operand in a formula."""
    af = _timeline(af)
    af.load = af.res * pl.col("res").map_batches(_rank_pct, return_dtype=pl.Float64)
    return af


def _a_plugin_over_the_rows(expr: pl.Expr) -> pl.Expr:
    return register_plugin_function(
        args=[expr],
        plugin_path=_get_lib(),
        function_name="fill_series",
        is_elementwise=False,
        kwargs={"start": 0, "increment": 1},
    )


def _an_elementwise_plugin(expr: pl.Expr) -> pl.Expr:
    return register_plugin_function(
        args=[expr],
        plugin_path=_get_lib(),
        function_name="fill_series",
        is_elementwise=True,
        kwargs={"start": 0, "increment": 1},
    )


def through_a_plugin_over_the_rows(af: ActuarialFrame) -> ActuarialFrame:
    """Run a plugin registered as reading the rows together."""
    af.steps = _a_plugin_over_the_rows(pl.col("term").cast(pl.Int64))
    return _timeline(af)


def through_an_elementwise_plugin(af: ActuarialFrame) -> ActuarialFrame:
    """Run a plugin registered as elementwise: each row from its own values."""
    af.steps = _an_elementwise_plugin(pl.col("term").cast(pl.Int64))
    af = _timeline(af)
    af.load = af.res * 1.0
    return af


OPAQUE = [through_map_batches, through_raw_map_batches, through_a_raw_operand]


@pytest.mark.parametrize("model", OPAQUE)
def test_the_whole_book_answers_the_hand_value(
    model: Callable[[ActuarialFrame], ActuarialFrame],
) -> None:
    assert model(ActuarialFrame(BOOK)).collect()["load"].sum() == pytest.approx(HAND)
    result = run_aggregated(model, BOOK, [Sum("load").alias("l")], batch_size=5)
    assert result.l == pytest.approx(HAND)


@pytest.mark.parametrize("model", OPAQUE)
@pytest.mark.parametrize("size", [2, 1])
def test_a_python_function_is_refused_where_the_book_is_cut(
    model: Callable[[ActuarialFrame], ActuarialFrame], size: int
) -> None:
    with pytest.raises(ValueError, match="Python function") as refused:
        run_aggregated(model, BOOK, [Sum("load").alias("l")], batch_size=size)
    message = str(refused.value)
    assert 'col("res")' in message, message
    assert "run_aggregated cuts the 5 policies into batches" in message, message
    assert "model-point column" in message, message
    assert "one batch" in message, message


def test_run_to_parquet_refuses_a_python_function_when_it_cuts_the_book(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="Python function"):
        run_to_parquet(
            through_map_batches, BOOK, output_dir=tmp_path / "c", batch_size=2
        )
    run_to_parquet(through_map_batches, BOOK, output_dir=tmp_path / "w", batch_size=5)


def test_a_plugin_reading_the_rows_together_is_refused_where_the_book_is_cut() -> None:
    with pytest.raises(ValueError, match="fill_series") as refused:
        run_aggregated(
            through_a_plugin_over_the_rows,
            BOOK,
            [Sum("res").alias("r")],
            batch_size=2,
        )
    assert "is_elementwise" in str(refused.value)


def test_an_elementwise_plugin_stands_where_the_book_is_cut() -> None:
    result = run_aggregated(
        through_an_elementwise_plugin, BOOK, [Sum("load").alias("l")], batch_size=2
    )
    assert result.l == pytest.approx(150.0)
