# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A total of whole numbers is taken exactly, and refused where no i64 holds it.

``run_aggregated``'s ``Sum`` summed each batch of an ``Int64`` column in
``Int64``, so 2**62, 2**62 and 5 answered 9.2e18 one policy at a time (the
values were added as doubles) and -9.2e18 two or three at a time (the batch
wrapped); 2**62, 2**62 and -2**62, whose total 2**62 fits, answered
-1.38e19 two at a time. A scenario's ``within="sum"`` wrapped the same way.
The total is now exact at every batch size, and a total outside the signed
64-bit range is refused by its column and its exact value.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import Max, Mean, Sum, for_each_scenario, run_aggregated

_H = 2**62
_I64_MAX = 2**63 - 1


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "pid": [1, 2, 3],
            "amt": [2.0, 3.0, 4.0],
            "big": [_H, _H, 5],
            "neg": [-_H, -_H, -5],
            "edge": [_I64_MAX - 10, 4, 6],
            "back": [_H, _H, -_H],
            "g": ["a", "a", "b"],
        }
    )


def _passenger(af: ActuarialFrame) -> ActuarialFrame:
    af.r = af.amt * 2
    return af


@pytest.mark.parametrize("batch_size", [1, 2, 3])
@pytest.mark.parametrize(
    ("column", "total"),
    [("big", 2 * _H + 5), ("neg", -(2 * _H + 5))],
    ids=["past the top", "past the bottom"],
)
def test_a_total_past_i64_is_refused_at_every_batch_size(
    column: str, total: int, batch_size: int
) -> None:
    with pytest.raises(ValueError, match="its sum is refused") as caught:
        run_aggregated(
            _passenger,
            _book(),
            aggregations=[Sum(column).alias("t")],
            batch_size=batch_size,
        )

    message = str(caught.value)
    assert message.startswith(
        f"Column {column!r} totals {total}, outside the signed 64-bit range"
    )
    assert f"af.{column} * 1.0" in message


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_total_that_fits_after_passing_i64_is_the_same_at_every_batch_size(
    batch_size: int,
) -> None:
    """Hand value: 2**62 + 2**62 - 2**62 = 2**62 (was -1.38e19 at two a batch)."""
    result = run_aggregated(
        _passenger,
        _book(),
        aggregations=[Sum("back").alias("t")],
        batch_size=batch_size,
    )

    assert result.aggregations["t"] == float(_H)


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_total_at_the_top_of_i64_is_answered(batch_size: int) -> None:
    """Hand value: (2**63 - 11) + 4 + 6 = 2**63 - 1, the greatest i64."""
    result = run_aggregated(
        _passenger,
        _book(),
        aggregations=[Sum("edge").alias("t")],
        batch_size=batch_size,
    )

    assert result.aggregations["t"] == float(_I64_MAX)


def test_a_partitioned_total_past_i64_is_refused() -> None:
    with pytest.raises(ValueError, match="Column 'big' totals 9223372036854775808"):
        run_aggregated(
            _passenger,
            _book(),
            aggregations=[Sum("big").alias("t").over("g")],
            batch_size=3,
        )


def test_a_decimal_total_is_unchanged() -> None:
    result = run_aggregated(
        _passenger, _book(), aggregations=[Sum("amt").alias("t")], batch_size=2
    )

    assert result.aggregations["t"] == 9.0


def _scenario_model(af: ActuarialFrame, **_: object) -> ActuarialFrame:
    af.r = af.amt * 2
    return af


@pytest.mark.parametrize("statistic", [Sum, Mean, Max], ids=["Sum", "Mean", "Max"])
def test_a_scenario_total_past_i64_is_refused_naming_the_scenario(
    statistic: type[Sum],
) -> None:
    """2**62 + 2**62 + 5 wrapped to -9.2e18 inside each scenario."""
    frame = ActuarialFrame(_book().select("pid", "amt", "big"))

    with pytest.raises(ValueError, match="its sum is refused") as caught:
        for_each_scenario(
            frame,
            ["BASE", "UP"],
            _scenario_model,
            aggregations=(statistic("big").alias("t"),),
            batch_size=1,
        )

    assert str(caught.value).startswith(
        "Column 'big' totals 9223372036854775813 in scenario 'BASE', outside"
    )


def test_scenario_totals_that_fit_but_sum_past_i64_are_refused() -> None:
    """Each scenario totals 2**62 + 3; three of them total 3 * 2**62 + 9."""
    book = pl.DataFrame({"pid": [1, 2, 3], "amt": [1.0, 1.0, 1.0], "v": [_H, 1, 2]})

    with pytest.raises(ValueError, match="Column 'v' totals 13835058055282163721,"):
        for_each_scenario(
            ActuarialFrame(book),
            ["A", "B", "C"],
            _scenario_model,
            aggregations=(Sum("v").alias("t"),),
            batch_size=1,
        )


def test_scenario_totals_that_pass_i64_and_come_back_are_exact() -> None:
    """Each scenario totals 2**62 + 2**62 - 2**62 = 2**62; the mean is 2**62."""
    frame = ActuarialFrame(_book().select("pid", "amt", "back"))
    result = for_each_scenario(
        frame,
        ["BASE", "UP"],
        _scenario_model,
        aggregations=(Mean("back").alias("t"),),
        batch_size=1,
    )

    assert result.aggregations["t"] == float(_H)
