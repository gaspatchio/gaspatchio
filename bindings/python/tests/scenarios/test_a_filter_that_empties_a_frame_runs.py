# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A frame a filter empties runs to an empty result, on every door.

A model that chooses which policies it values -- ``af.filter(af.status ==
"IF")`` -- meets a batch holding none of them as soon as the book is sorted
by status and run in batches, and a whole book of lapsed policies on any
door. ``projection.set`` read a column horizon as the largest value over the
rows, which over no rows is null, and ``int(None)`` raised a bare
``TypeError``. A frame with no rows projects nothing, so its axis is zero
periods long; a frame whose rows all carry a null horizon is refused by name.

The largest horizon is read over the frame's own rows, which in a batched run
are the batch's: on a per-policy grid it only records the longest axis, so a
policy's numbers are its own whatever its batch-mates -- each batch door
agrees with ``collect()`` below, policy for policy.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import (
    MultiplicativeShock,
    ScenarioRun,
    Sum,
    run_aggregated,
    run_to_parquet,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# Three policies, the middle one lapsed: a batch of one holding it is empty.
_BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "status": ["IF", "LA", "IF"],
        "term_months": [12, 24, 6],
        "term_years": [1, 2, 1],
        "issue_age": [60, 50, 65],
        "max_age": [62, 60, 66],
        "sa": [1000.0, 2000.0, 3000.0],
    }
)
_ALL_LAPSED = _BOOK.with_columns(status=pl.lit("LA"))

# Each horizon read from the rows, with policy 1's and policy 3's value of
# sum(sa * 0.01) over their own boundaries, by hand: 12 months is 13
# boundaries (13 x 10 = 130), 6 months is 7 (7 x 30 = 210); a year is 13; to
# age 67 from 60 is 84 months (85 x 10) and from 65 is 24 (25 x 30); to their
# own maximum ages, 62 - 60 and 66 - 65 years (25 x 10, 13 x 30).
_HORIZONS: dict[str, tuple[dict[str, Any], list[float]]] = {
    "term_months column": (
        {"until": "term_months", "until_value": "term_months"},
        [130.0, 210.0],
    ),
    "term_years column": (
        {"until": "term_years", "until_value": "term_years"},
        [130.0, 390.0],
    ),
    "maximum_age whole number": (
        {"until": "maximum_age", "until_value": 67},
        [850.0, 750.0],
    ),
    "maximum_age column": (
        {"until": "maximum_age", "until_value": "max_age"},
        [250.0, 390.0],
    ),
    "maximum_age expression": (
        {"until": "maximum_age", "until_value": pl.col("max_age")},
        [250.0, 390.0],
    ),
}


def _model(horizon: dict[str, Any]) -> Callable[[ActuarialFrame], ActuarialFrame]:
    def main(af: ActuarialFrame) -> ActuarialFrame:
        af = af.filter(af.status == "IF")
        af = af.projection.set(
            valuation_date=datetime.date(2025, 1, 1), frequency="monthly", **horizon
        )
        af.cf = af.sa * 0.01 + af.month * 0.0
        af.pv = af.cf.list.sum()
        return af

    return main


def _written(directory: Path) -> pl.DataFrame:
    frames = [pl.read_parquet(path) for path in sorted(directory.glob("*.parquet"))]
    return pl.concat([frame for frame in frames if frame.height], how="vertical")


@pytest.mark.parametrize("name", sorted(_HORIZONS))
def test_a_batch_the_filter_empties_runs_as_collect_does(
    tmp_path: Path, name: str
) -> None:
    horizon, hand = _HORIZONS[name]
    main = _model(horizon)

    whole = main(ActuarialFrame(_BOOK)).collect()
    assert whole["pv"].to_list() == hand

    run_to_parquet(main, _BOOK, tmp_path / "one", batch_size=1)
    assert _written(tmp_path / "one").sort("policy_id")["pv"].to_list() == hand
    folded = run_aggregated(
        main, _BOOK, aggregations=(Sum("pv").alias("t"),), batch_size=1
    )
    assert folded.aggregations["t"] == sum(hand)


@pytest.mark.parametrize("name", sorted(_HORIZONS))
def test_a_book_the_filter_empties_runs_to_nothing(tmp_path: Path, name: str) -> None:
    main = _model(_HORIZONS[name][0])

    assert main(ActuarialFrame(_ALL_LAPSED)).collect().height == 0
    spilled = run_to_parquet(main, _ALL_LAPSED, tmp_path / "spill", batch_size=2)
    assert spilled.n_policies == 0
    folded = run_aggregated(
        main, _ALL_LAPSED, aggregations=(Sum("pv").alias("t"),), batch_size=1
    )
    # A sum that saw no value is null, not 0.0 (the aggregator's contract).
    assert folded.aggregations["t"] is None
    assert folded.n_policies == 0


@pytest.mark.parametrize("batch_size", [1, 2])
def test_a_scenario_run_over_a_book_the_filter_empties_runs_to_nothing(
    batch_size: int,
) -> None:
    main = _model(_HORIZONS["term_months column"][0])
    plan = ScenarioRun(
        shocks={"BASE": [], "AGAIN": []}, aggregations=(Sum("pv").alias("t"),)
    )

    result = plan.run(ActuarialFrame(_ALL_LAPSED), main, batch_size=batch_size)

    assert result.aggregations["t"] is None


def test_a_jagged_horizon_null_on_every_row_projects_nowhere() -> None:
    """A policy whose horizon is null carries no boundaries (section 11.1.1)."""
    book = _BOOK.with_columns(term_months=pl.lit(None, dtype=pl.Int64))
    main = _model({"until": "term_months", "until_value": "term_months"})

    answered = main(ActuarialFrame(book)).collect()

    assert answered["num_proj_months"].to_list() == [0, 0]


def test_a_shared_grid_sized_from_rows_all_null_is_refused_by_name() -> None:
    book = _BOOK.with_columns(term_months=pl.lit(None, dtype=pl.Int64))
    main = _model(
        {"until": "term_months", "until_value": "term_months", "per_policy": False}
    )

    with pytest.raises(ValueError, match=r"null in every one of the frame's 2 rows"):
        main(ActuarialFrame(book))


def test_a_lookup_with_a_literal_key_over_no_rows_answers_no_rows() -> None:
    """``Table.lookup(age=af.age, sex="M")`` after a filter that keeps nothing.

    The in-memory engine hands the kernel a zero-row column key beside a
    one-value literal; it refused the lengths. A scenario run's column shock
    reads its factors that way, so one batch of a book the filter emptied
    raised on it.
    """
    rates = Table(
        name="w5_bug24_rates",
        source=pl.DataFrame(
            {
                "age": [30, 40, 30, 40],
                "sex": ["M", "M", "F", "F"],
                "q": [0.1, 0.2, 0.3, 0.4],
            }
        ),
        dimensions={"age": "age", "sex": "sex"},
        value="q",
    )
    af = ActuarialFrame(pl.DataFrame({"age": [30, 40], "status": ["LA", "LA"]}))
    af = af.filter(af.status == "IF")
    af.q = rates.lookup(age=af.age, sex="M")

    answered = af.collect(engine="in-memory")

    assert answered.height == 0
    assert answered.schema["q"] == pl.Float64
    main = _model(_HORIZONS["term_months column"][0])
    plan = ScenarioRun(
        shocks={"BASE": [], "UP": [MultiplicativeShock(factor=1.1, column="sa")]},
        aggregations=(Sum("pv").alias("t"),),
    )
    assert (
        plan.run(ActuarialFrame(_ALL_LAPSED), main, batch_size=1).aggregations["t"]
        is None
    )
