# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A read across rows is refused wherever the frame is not the whole book.

A fixed expense of 1,000,000 allocated by share of sum assured totals
1,000,000 by construction -- where the share is of the book. Written through
``polars_native()`` or raw ``pl.col``, the share is of the rows in the frame:
in a batch runner the batch, on a scenario axis every scenario. Before this,
the allocation came back as 1,000,000 from ``collect()``, 3,000,000 at
``batch_size=3``, 8,000,000 at ``batch_size=1``, and 500,000 a scenario from a
two-scenario plan at any batch size above one. Now the read is refused there,
naming the read and the two routes, and stands where the frame is the book.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated, run_to_parquet
from gaspatchio.scenarios import MultiplicativeShock, ScenarioRun, Sum, with_scenarios

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

FIXED_EXPENSE = 1_000_000.0

BOOK = pl.DataFrame(
    {
        "policy_id": [f"P{i}" for i in range(8)],
        "sa": [1e5 * (i + 1) for i in range(8)],
        "term_m": [12] * 8,
        "lapse_adj": [1.0] * 8,
    }
)


def _timeline(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value="term_m",
        frequency="monthly",
    )
    af.cf = af.alloc_exp / 12 * af.lapse_adj + af.month * 0.0
    af.exp0 = af.alloc_exp * 1.0
    return af


def allocated(af: ActuarialFrame) -> ActuarialFrame:
    """Allocate the expense by share of sum assured, through the explicit escape."""
    af.sa_share = af.sa / af.sa.polars_native().sum()
    af.alloc_exp = af.sa_share * FIXED_EXPENSE
    return _timeline(af)


def allocated_raw(af: ActuarialFrame) -> ActuarialFrame:
    """Allocate the same expense by share, written in raw Polars."""
    af.sa_share = af.sa / pl.col("sa").sum()
    af.alloc_exp = af.sa_share * FIXED_EXPENSE
    return _timeline(af)


def allocated_equally(af: ActuarialFrame) -> ActuarialFrame:
    """Split the expense equally, over the count of the rows."""
    af.alloc_exp = FIXED_EXPENSE / pl.len()
    return _timeline(af)


def _routes(message: str) -> None:
    assert "model-point column" in message, message
    assert "one batch" in message, message


@pytest.mark.parametrize("model", [allocated, allocated_raw, allocated_equally])
def test_the_book_in_one_frame_allocates_the_whole_expense(
    model: Callable[[ActuarialFrame], ActuarialFrame],
) -> None:
    assert model(ActuarialFrame(BOOK)).collect()["exp0"].sum() == pytest.approx(
        FIXED_EXPENSE
    )
    for size in (8, 16):
        result = run_aggregated(
            model, BOOK, [Sum("exp0").alias("exp0")], batch_size=size
        )
        assert result.exp0 == pytest.approx(FIXED_EXPENSE)


@pytest.mark.parametrize("model", [allocated, allocated_raw, allocated_equally])
@pytest.mark.parametrize("size", [3, 1, "auto"])
def test_a_batch_runner_cutting_the_book_refuses_the_read(
    model: Callable[[ActuarialFrame], ActuarialFrame], size: int | str
) -> None:
    with pytest.raises(ValueError, match="reads across the rows") as refused:
        run_aggregated(model, BOOK, [Sum("exp0").alias("exp0")], batch_size=size)  # type: ignore[arg-type]
    message = str(refused.value)
    assert "run_aggregated cuts the 8 policies into batches" in message
    assert "here those are the batch" in message
    _routes(message)


def test_the_refusal_names_the_read() -> None:
    with pytest.raises(ValueError, match=r'sum on col\("sa"\)'):
        run_aggregated(allocated, BOOK, [Sum("exp0").alias("exp0")], batch_size=3)
    with pytest.raises(ValueError, match="len on the frame's rows"):
        run_aggregated(
            allocated_equally, BOOK, [Sum("exp0").alias("exp0")], batch_size=3
        )


def test_run_to_parquet_refuses_the_read_when_it_cuts_the_book(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run_to_parquet cuts the 8 policies"):
        run_to_parquet(allocated, BOOK, output_dir=tmp_path / "cut", batch_size=3)
    run_to_parquet(allocated, BOOK, output_dir=tmp_path / "whole", batch_size=8)
    written = pl.read_parquet(tmp_path / "whole" / "*.parquet")
    assert written["exp0"].sum() == pytest.approx(FIXED_EXPENSE)


@pytest.mark.parametrize("size", [1, 2, 16])
def test_a_scenario_plan_refuses_the_read_at_every_batch_size(size: int) -> None:
    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "UP": [MultiplicativeShock(factor=1.1, column="lapse_adj")],
        },
        aggregations=(Sum("exp0").alias("exp0").over("scenario_id"),),
    )
    with pytest.raises(ValueError, match="reads across the rows") as refused:
        plan.run(ActuarialFrame(BOOK), allocated, batch_size=size)
    message = str(refused.value)
    assert "every scenario's copy of every policy" in message
    _routes(message)


def test_a_frame_crossed_with_scenarios_refuses_the_read_after_the_axis() -> None:
    af = with_scenarios(ActuarialFrame(BOOK), ["BASE", "UP"])
    with pytest.raises(ValueError, match="this frame carries a scenario axis"):
        allocated(af)


def test_a_read_taken_before_the_axis_is_crossed_is_the_books() -> None:
    af = ActuarialFrame(BOOK)
    af.sa_share = af.sa / af.sa.polars_native().sum()
    af = with_scenarios(af, ["BASE", "UP"])
    af.exp0 = af.sa_share * FIXED_EXPENSE
    out = af.collect()
    assert out.group_by("scenario_id").agg(pl.col("exp0").sum())[
        "exp0"
    ].to_list() == pytest.approx([FIXED_EXPENSE, FIXED_EXPENSE])


@pytest.mark.parametrize(
    "write",
    [
        lambda af: af.sa.polars_native().rank(),
        lambda af: af.sa.polars_native().rolling_mean(2),
        lambda af: af.sa.polars_native().cum_sum(),
        lambda af: af.sa.polars_native().pct_change(),
        lambda _af: pl.col("sa").mean(),
        lambda _af: pl.col("sa").sum().over(pl.lit(1)),
    ],
    ids=["rank", "rolling_mean", "cum_sum", "pct_change", "raw-mean", "over"],
)
def test_every_read_across_rows_is_refused_in_a_cut_book(
    write: Callable[[ActuarialFrame], object],
) -> None:
    def model(af: ActuarialFrame) -> ActuarialFrame:
        af.read = write(af)
        af.alloc_exp = af.sa * 0.0
        return _timeline(af)

    with pytest.raises(ValueError, match="reads across the rows"):
        run_aggregated(model, BOOK, [Sum("exp0").alias("exp0")], batch_size=4)


def test_one_policys_own_periods_are_not_a_read_across_rows() -> None:
    """A fold inside ``list.eval`` runs over one policy's own list."""

    def model(af: ActuarialFrame) -> ActuarialFrame:
        af.alloc_exp = af.sa * 0.01
        af = _timeline(af)
        af.running = af.cf.polars_native().list.eval(pl.element().cum_sum())
        af.periods = af.cf.polars_native().list.eval(pl.len())
        af.total = af.cf.list.sum()
        return af

    result = run_aggregated(model, BOOK, [Sum("exp0").alias("exp0")], batch_size=3)
    assert result.exp0 == pytest.approx(sum(BOOK["sa"]) * 0.01)


def test_a_column_named_len_is_not_the_count_of_the_rows() -> None:
    book = BOOK.with_columns(pl.col("sa").alias("Len"))

    def model(af: ActuarialFrame) -> ActuarialFrame:
        af.alloc_exp = pl.col("Len") * 0.01
        return _timeline(af)

    result = run_aggregated(model, book, [Sum("exp0").alias("exp0")], batch_size=3)
    assert result.exp0 == pytest.approx(sum(BOOK["sa"]) * 0.01)
