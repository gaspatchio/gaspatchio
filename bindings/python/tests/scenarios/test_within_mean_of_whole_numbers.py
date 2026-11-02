# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario's ``within="mean"`` of whole numbers is the double nearest its exact mean.

On the scenario axis each scenario's policies are first reduced by the
aggregator's ``within``. ``within="mean"`` over an integer column was Polars'
``mean``, which turns each value into a double before adding them: 2**63 - 1,
-2**63 and 5 averaged to 5/3, where the exact mean is 4/3, and 2**53 + 1,
2**53 + 1 and 2**53 + 2 to 9007199254740992.0, where the double nearest the
exact 2**53 + 4/3 is 9007199254740994.0. Every statistic across scenarios
then read that wrong figure, and an ``ArgMax`` named the wrong scenario.

The mean is now read once from the scenario's exact total and count, as every
other mean of whole numbers is. The other ``within`` kinds were already
exact: ``sum`` is taken in ``Int128`` and refused past ``i64``, and ``max``,
``min``, ``first``, ``last`` and ``count`` read values the column holds.
"""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import ArgMax, Max, Mean, Min, Sum, for_each_scenario

_MAX = 2**63 - 1
_MIN = -(2**63)
_P = 2**53

# Hand values.
# [2**63 - 1, -2**63, 5]: total 4 over 3 policies.
_MIXED = 4 / 3
# [2**53 + 1, 2**53 + 1, 2**53 + 2]: 2**53 + 4/3, between the doubles 2**53
# and 2**53 + 2, and nearer the second.
_FINE = 9007199254740994.0


def _book(columns: dict[str, list[int | None]]) -> pl.DataFrame:
    rows = len(next(iter(columns.values())))
    return pl.DataFrame(
        {
            "pid": list(range(rows)),
            "g": ["a"] * rows,
            **{
                name: pl.Series(values, dtype=pl.Int64)
                for name, values in columns.items()
            },
        }
    )


def _as_is(af: ActuarialFrame, *, tables: object, drivers: object) -> ActuarialFrame:  # noqa: ARG001 -- the scenario runner's signature
    return af


def _picked(af: ActuarialFrame, *, tables: object, drivers: dict[str, str]) -> Any:  # noqa: ANN401, ARG001 -- the scenario runner's signature
    return af.with_columns(pl.col(drivers["column"]).alias("v"))


def _run(
    values: list[int],
    aggregation: Any,  # noqa: ANN401 -- any aggregator, named "t"
    scenarios: tuple[str, ...] = ("A",),
    batch_size: int = 1,
) -> Any:  # noqa: ANN401 -- an aggregator's answer
    """Run every scenario over the same policies, ``v`` holding ``values``."""
    return for_each_scenario(
        ActuarialFrame(_book({"v": values})),
        list(scenarios),
        _as_is,
        aggregations=[aggregation],
        batch_size=batch_size,
    ).aggregations["t"]


def _run_each(
    columns: dict[str, list[int | None]],
    scenarios: dict[str, str],
    aggregation: Any,  # noqa: ANN401 -- any aggregator, named "t"
) -> Any:  # noqa: ANN401 -- an aggregator's answer
    """Run each scenario over its own column of the book, read as ``v``."""
    return for_each_scenario(
        ActuarialFrame(_book(columns)),
        {name: {"column": column} for name, column in scenarios.items()},
        _picked,
        aggregations=[aggregation],
        batch_size=1,
    ).aggregations["t"]


@pytest.mark.parametrize("batch_size", [1, 2])
@pytest.mark.parametrize(
    ("values", "mean"),
    [([_MAX, _MIN, 5], _MIXED), ([_P + 1, _P + 1, _P + 2], _FINE)],
    ids=["both ends and 5", "just past 2**53"],
)
def test_a_scenario_mean_of_whole_numbers_is_the_nearest_double(
    values: list[int], mean: float, batch_size: int
) -> None:
    """Was 5/3 and 9007199254740992.0."""
    answer = _run(values, Mean("v", within="mean").alias("t"), ("A", "B"), batch_size)

    assert answer == mean


@pytest.mark.parametrize("batch_size", [1, 2])
def test_every_statistic_across_scenarios_reads_the_exact_mean(
    batch_size: int,
) -> None:
    """Was 10/3 for the sum and 5/3 for the least and greatest."""
    values = [_MAX, _MIN, 5]
    scenarios = ("A", "B")

    def run(aggregation: Any) -> Any:  # noqa: ANN401 -- as above
        return _run(values, aggregation.alias("t"), scenarios, batch_size)

    assert run(Sum("v", within="mean")) == _MIXED + _MIXED
    assert run(Min("v", within="mean")) == _MIXED
    assert run(Max("v", within="mean")) == _MIXED


def test_the_scenario_with_the_greatest_mean_is_found_by_its_exact_mean() -> None:
    """A's exact mean is 4/3 and B's 3/2, so B. Was A, whose mean read as 5/3."""
    columns: dict[str, list[int | None]] = {"x": [_MAX, _MIN, 5], "y": [1, 2, None]}

    answer = _run_each(
        columns, {"A": "x", "B": "y"}, ArgMax("v", within="mean").alias("t")
    )

    assert answer == "B"


def test_a_partitioned_scenario_mean_is_exact() -> None:
    answer = _run([_MAX, _MIN, 5], Mean("v", within="mean").alias("t").over("g"))

    assert answer.to_dicts() == [{"g": "a", "t": _MIXED}]


def test_a_scenario_with_no_value_has_no_mean() -> None:
    """A scenario whose every value is missing is skipped, as before."""
    columns: dict[str, list[int | None]] = {
        "x": [_MAX, _MIN, 5],
        "y": [None, None, None],
    }
    mean = Mean("v", within="mean").alias("t")

    assert _run_each(columns, {"A": "x", "B": "y"}, mean) == _MIXED
    assert _run_each(columns, {"B": "y"}, mean) is None


def test_a_decimal_scenario_mean_is_unchanged() -> None:
    book = pl.DataFrame({"pid": [1, 2, 3], "v": [0.1, 0.2, 0.4]})

    answer = for_each_scenario(
        ActuarialFrame(book),
        ["A"],
        _as_is,
        aggregations=[Mean("v", within="mean").alias("t")],
    ).aggregations["t"]

    assert answer == pl.Series([0.1, 0.2, 0.4]).mean()
