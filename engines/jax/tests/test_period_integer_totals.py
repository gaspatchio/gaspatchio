# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period total of whole numbers folded here is the producer's exact total.

This engine totalled a ``list[i64]`` column's periods on the device in one
``int64``, which wrapped: 2**62, 2**62 and 5 answered 9.2e18 at every period
one policy a batch and -9.2e18 two a batch, here as on Polars, and 2**53, 1
and 1 answered 9007199254740992.0 one a batch. The device now totals each
cell's high and low 32 bits apart and the host joins them, so both engines
answer every period's exact total, and refuse one past the signed 64-bit
range by its column, its value and its period.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.scenarios import PeriodSum, run_aggregated

if TYPE_CHECKING:
    from gaspatchio import ActuarialFrame

_H = 2**62
_P = 2**53


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "amt": [2.0, 3.0, 4.0],
            "big": [_H, _H, 5],
            "neg": [-_H, -_H, -5],
            "back": [_H, _H, -_H],
            "fine": [_P, 1, 1],
            "g": ["a", "a", "a"],
        }
    )


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.b = af.big + af.month * 0
    af.n = af.neg + af.month * 0
    af.k = af.back + af.month * 0
    af.f = af.fine + af.month * 0
    af.r = af.amt + af.month * 0.0
    return af


def _answers(column: str, batch_size: int, *, over: bool = False) -> list[object]:
    aggregation = PeriodSum(column).alias("t")
    answers: list[object] = []
    for engine in (None, "jax"):
        result = run_aggregated(
            _model,
            _book(),
            aggregations=[aggregation.over("g") if over else aggregation],
            batch_size=batch_size,
            engine=engine,
        ).aggregations["t"]
        answers.append(result["t"].to_list() if over else result.tolist())
    return answers


@pytest.mark.parametrize("batch_size", [1, 2, 3])
@pytest.mark.parametrize(
    ("column", "total"),
    [("b", 2 * _H + 5), ("n", -(2 * _H + 5))],
    ids=["past the top", "past the bottom"],
)
def test_a_period_total_past_i64_is_refused_on_both_engines(
    column: str, total: int, batch_size: int
) -> None:
    for engine in (None, "jax"):
        with pytest.raises(
            ValueError, match=f"Column '{column}' totals {total} at period 0,"
        ):
            run_aggregated(
                _model,
                _book(),
                aggregations=[PeriodSum(column).alias("t")],
                batch_size=batch_size,
                engine=engine,
            )


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_period_total_that_fits_is_the_same_on_both_engines(batch_size: int) -> None:
    """Hand value: 2**62 + 2**62 - 2**62 = 2**62 (was -1.38e19 at two a batch)."""
    assert _answers("k", batch_size) == [[float(_H)] * 3] * 2


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_a_period_total_is_the_nearest_double_on_both_engines(batch_size: int) -> None:
    """Hand value: 2**53 + 1 + 1 = 9007199254740994 (was ...992 one a batch)."""
    assert _answers("f", batch_size) == [[9007199254740994.0] * 3] * 2


def test_a_partitioned_period_total_is_exact_on_both_engines() -> None:
    """Hand value: 2**53 + 1 + 1 = 9007199254740994, in the one partition."""
    assert _answers("f", 1, over=True) == [[9007199254740994.0] * 3] * 2
