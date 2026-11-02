# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period total of whole numbers is exact, and refused where no i64 holds it.

``PeriodSum`` summed each batch's periods of a ``list[i64]`` column in
``Int64`` and carried the partials as doubles, so 2**62, 2**62 and 5 answered
9.2e18 at every period one policy at a time and -9.2e18 two or three at a
time; 2**62, 2**62 and -2**62, whose total 2**62 fits, answered -1.38e19 two
at a time; and 2**53, 1 and 1 answered 9007199254740992.0 one at a time,
where the total 9007199254740994 is a double. On the scenario axis each
scenario's per-period total wrapped the same way, for every per-period kind.
Each period's total is now exact at every batch size, and one outside the
signed 64-bit range is refused by its column, its exact value and its period,
and on the scenario axis its scenario.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.scenarios import (
    PeriodMax,
    PeriodMean,
    PeriodMedian,
    PeriodSum,
    for_each_scenario,
    run_aggregated,
)

_H = 2**62
_P = 2**53
_I64_MAX = 2**63 - 1


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "pid": [1, 2, 3],
            "amt": [2.0, 3.0, 4.0],
            "big": [_H, _H, 5],
            "neg": [-_H, -_H, -5],
            "back": [_H, _H, -_H],
            "fine": [_P, 1, 1],
            "edge": [_I64_MAX - 10, 4, 6],
            "g": ["a", "a", "b"],
            "h": ["a", "a", "a"],
        }
    )


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    for name in ("big", "neg", "back", "fine", "edge"):
        af[f"{name}_t"] = af[name] + af.month * 0
    af.amt_t = af.amt + af.month * 0.0
    return af


def _period_sum(column: str, batch_size: int) -> list[float]:
    result = run_aggregated(
        _model,
        _book(),
        aggregations=[PeriodSum(column).alias("t")],
        batch_size=batch_size,
    )
    return result.aggregations["t"].tolist()


@pytest.mark.parametrize("batch_size", [1, 2, 3])
@pytest.mark.parametrize(
    ("column", "total"),
    [("big_t", 2 * _H + 5), ("neg_t", -(2 * _H + 5))],
    ids=["past the top", "past the bottom"],
)
def test_a_period_total_past_i64_is_refused_at_every_batch_size(
    column: str, total: int, batch_size: int
) -> None:
    with pytest.raises(ValueError, match="its sum is refused") as caught:
        _period_sum(column, batch_size)

    message = str(caught.value)
    assert message.startswith(
        f"Column {column!r} totals {total} at period 0, outside the signed 64-bit"
    )
    assert f"af.{column} * 1.0" in message


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_period_total_that_fits_after_passing_i64_is_the_same_at_every_batch_size(
    batch_size: int,
) -> None:
    """Hand value: 2**62 + 2**62 - 2**62 = 2**62 (was -1.38e19 at two a batch)."""
    assert _period_sum("back_t", batch_size) == [float(_H)] * 3


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_period_total_is_the_double_nearest_the_exact_total(batch_size: int) -> None:
    """Hand value: 2**53 + 1 + 1 = 9007199254740994 (was ...992 one a batch)."""
    assert _period_sum("fine_t", batch_size) == [9007199254740994.0] * 3


@pytest.mark.parametrize("batch_size", [1, 3])
def test_a_period_total_of_exactly_the_greatest_i64_is_answered(
    batch_size: int,
) -> None:
    """Hand value: (2**63 - 11) + 4 + 6 = 2**63 - 1, whose nearest double is 2**63."""
    assert _period_sum("edge_t", batch_size) == [float(2**63)] * 3


def test_a_partitioned_period_total_past_i64_is_refused() -> None:
    with pytest.raises(ValueError, match=r"totals 9223372036854775808 at period 0,"):
        run_aggregated(
            _model,
            _book(),
            aggregations=[PeriodSum("big_t").alias("t").over("g")],
            batch_size=1,
        )


def test_a_partitioned_period_total_is_exact_in_each_partition() -> None:
    """Hand value: 2**53 + 1 + 1 = 9007199254740994 (was ...992 one a batch)."""
    result = run_aggregated(
        _model,
        _book(),
        aggregations=[PeriodSum("fine_t").alias("t").over("h")],
        batch_size=1,
    )

    assert result.aggregations["t"]["t"].to_list() == [9007199254740994.0] * 3


def test_a_period_with_no_whole_number_is_still_no_value() -> None:
    """A period whose every value is null stays masked; the others are exact.

    ``k`` is a whole-number run with a null period. Its other periods total
    2**53 + 1 and 1, which is 9007199254740994 and a double; read as doubles,
    2**53 + 1 is 2**53 and the total 9007199254740992.0.
    """

    def nulls(af: ActuarialFrame) -> ActuarialFrame:
        af = af.projection.set(
            start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
        )
        af.k = when(af.month == 1).then(None).otherwise(af.n + af.month * 0)
        af.amt_t = af.amt + af.month * 0.0
        return af

    book = pl.DataFrame({"amt": [1.0, 2.0], "n": [_P + 1, 1]})
    assert nulls(ActuarialFrame(book)).collect().schema["k"] == pl.List(pl.Int64)
    total = float(_P + 2)
    for batch_size in (1, 2):
        result = run_aggregated(
            nulls, book, aggregations=[PeriodSum("k").alias("t")], batch_size=batch_size
        )
        assert result.aggregations["t"].tolist() == [total, None, total]


def test_a_decimal_period_total_is_unchanged() -> None:
    assert _period_sum("amt_t", 1) == [9.0, 9.0, 9.0]


def _scenario_model(
    af: ActuarialFrame,
    *,
    tables: object,  # noqa: ARG001 -- the scenario runner's signature
    drivers: object,  # noqa: ARG001 -- as above
) -> ActuarialFrame:
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=1, frequency="monthly"
    )
    af.vv = af.v + af.month * 0
    af.ff = af.amt + af.month * 0.0
    return af


def _scenarios(values: list[int], names: list[str], aggregation: object) -> object:
    book = pl.DataFrame({"pid": [1, 2, 3], "amt": [1.0, 2.0, 3.0], "v": values})
    return for_each_scenario(
        ActuarialFrame(book),
        names,
        _scenario_model,
        aggregations=(aggregation,),
        batch_size=1,
    ).aggregations["t"]


@pytest.mark.parametrize(
    "aggregation",
    [
        PeriodSum("vv").alias("t"),
        PeriodMean("vv").alias("t"),
        PeriodMax("vv").alias("t"),
        PeriodMedian("vv").alias("t"),
        PeriodSum("vv").alias("t").over("scenario_id"),
    ],
    ids=["PeriodSum", "PeriodMean", "PeriodMax", "PeriodMedian", "over scenario"],
)
def test_a_scenarios_period_total_past_i64_is_refused_naming_the_scenario(
    aggregation: object,
) -> None:
    """Each scenario totals 2**62 + 2**62 + 5 at every period (was -9.2e18)."""
    with pytest.raises(ValueError, match="its sum is refused") as caught:
        _scenarios([_H, _H, 5], ["BASE", "UP"], aggregation)

    assert str(caught.value).startswith(
        "Column 'vv' totals 9223372036854775813 in scenario 'BASE' at period 0,"
    )


def test_a_period_total_across_scenarios_past_i64_is_refused() -> None:
    """Each scenario totals 2**62 + 3, which fits; three do not (was 1.38e19)."""
    with pytest.raises(ValueError, match="its sum is refused") as caught:
        _scenarios([_H, 1, 2], ["A", "B", "C"], PeriodSum("vv").alias("t"))

    assert str(caught.value).startswith(
        f"Column 'vv' totals {3 * (_H + 3)} at period 0, outside"
    )


def test_a_period_total_across_scenarios_is_exact() -> None:
    """Hand value: 3 * (2**53 + 1) = 27021597764222979, nearest double ...980.

    Added as doubles, each scenario's 2**53 + 1 was 2**53, and three of them
    27021597764222976.
    """
    answer = _scenarios([_P, 1, 0], ["A", "B", "C"], PeriodSum("vv").alias("t"))

    assert answer.tolist() == [27021597764222980.0, 27021597764222980.0]
