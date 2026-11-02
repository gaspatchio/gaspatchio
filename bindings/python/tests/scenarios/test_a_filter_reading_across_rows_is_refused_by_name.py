# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A filter reading across rows is refused where the rows are not the book.

``af.filter(pl.col("sa") > pl.col("sa").mean())`` keeps the policies above the
mean sum assured of the rows in the frame. Over the whole book that is the
book's mean: 450 here, policies 3 and 4, a total of 2 x (600 + 900) = 3000.
In a batch it is the batch's mean, so the total was None at a batch of one,
2200 at two and 3000 only over the book; on a scenario axis it is the mean of
every scenario's rows. Section 13.2 and the ruling on reads across rows refuse
such a read by name at a batch door, as an assignment's already is; the filter
is held to the same rule. A read partitioned by the scenario stands on a
scenario axis whose policies are whole.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, ScenarioRun
from gaspatchio.scenarios import Sum, run_aggregated, run_to_parquet

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_BOOK = pl.DataFrame({"policy_id": [1, 2, 3, 4], "sa": [100.0, 200.0, 600.0, 900.0]})


def _model(
    condition: Callable[[ActuarialFrame], object],
) -> Callable[[ActuarialFrame], ActuarialFrame]:
    def main(af: ActuarialFrame) -> ActuarialFrame:
        af = af.filter(condition(af))  # type: ignore[arg-type]
        af = af.projection.set(
            valuation_date=datetime.date(2025, 1, 1),
            until="term_months",
            until_value=1,
            frequency="monthly",
        )
        af.pv = (af.sa + af.month * 0.0).list.sum()
        return af

    return main


_CONDITIONS: dict[str, Callable[[ActuarialFrame], object]] = {
    "a Polars mean": lambda _af: pl.col("sa") > pl.col("sa").mean(),
    "a mean beside the frame's column": lambda af: af.sa > pl.col("sa").mean(),
    "a share of the sum": lambda _af: pl.col("sa") / pl.col("sa").sum() > 0.2,
    "a rank": lambda _af: pl.col("sa").rank() > 2,
    "the count of the rows": lambda _af: pl.len() > 3,
}


@pytest.mark.parametrize("name", sorted(_CONDITIONS))
def test_a_batch_door_refuses_the_condition_by_name(tmp_path: Path, name: str) -> None:
    main = _model(_CONDITIONS[name])

    with pytest.raises(ValueError, match="The filter's condition reads across"):
        run_aggregated(main, _BOOK, aggregations=(Sum("pv").alias("t"),), batch_size=2)
    with pytest.raises(ValueError, match="The filter's condition reads across"):
        run_to_parquet(main, _BOOK, tmp_path, batch_size=1)


def test_the_book_in_one_batch_keeps_the_book_s_answer() -> None:
    main = _model(_CONDITIONS["a Polars mean"])

    assert main(ActuarialFrame(_BOOK)).collect()["pv"].sum() == 3000.0
    whole = run_aggregated(
        main, _BOOK, aggregations=(Sum("pv").alias("t"),), batch_size=4
    )
    assert whole.aggregations["t"] == 3000.0


def test_a_scenario_axis_refuses_it_and_keeps_a_read_partitioned_by_scenario() -> None:
    plan = ScenarioRun(
        shocks={"BASE": [], "AGAIN": []},
        aggregations=(Sum("pv").alias("t").over("scenario_id"),),
    )

    with pytest.raises(ValueError, match="partition the read by the scenario"):
        plan.run(ActuarialFrame(_BOOK), _model(_CONDITIONS["a Polars mean"]))

    per_scenario = _model(
        lambda _af: pl.col("sa") > pl.col("sa").mean().over("scenario_id")
    )
    result = plan.run(ActuarialFrame(_BOOK), per_scenario, batch_size=2)
    folded = result.aggregations["t"]
    assert isinstance(folded, pl.DataFrame)
    assert folded["t"].to_list() == [3000.0, 3000.0]
