# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Arithmetic between a duration and a number is refused where it is written.

``af.term = af.maturity - af.issue`` is a duration, one value per policy, and
the vocabulary has no time-delta type (section 10): the export already names
such a column and the cast that carries it as a count. Arithmetic beside it
failed only when the frame ran, in Polars' words -- ``+ not allowed on
duration[us] and i64``, ``div operation not supported for dtypes `i64` and
`duration[us]```, ``cannot add columns: dtype was not list on all nesting
levels`` -- for 177 of the 196 pairings a sweep wrote. Each is now refused at
the line, naming the duration and the count to write instead, as text and a
date beside a number already are (11.1.25).

The 19 that answered still answer, because they are Polars' own kernels and
not a failure in its words: a duration times a number on either side or over
one, one value per policy, and a run of durations times or over a number
written on its right.
"""

from __future__ import annotations

import datetime as dt
import operator
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame(
    {
        "issue": [dt.date(2020, 1, 1), dt.date(2021, 6, 1)],
        "maturity": [dt.date(2025, 1, 1), dt.date(2025, 1, 1)],
        "n": [2, 3],
        "x": [2.0, 0.5],
        "flag": [True, False],
    }
)

# By hand: 2020-01-01 to 2025-01-01 is 1827 days, 2021-06-01 to it 1310.
_TERM = [dt.timedelta(days=1827), dt.timedelta(days=1310)]

_OPS: dict[str, Callable[[object, object], object]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
}


def _per_policy() -> ActuarialFrame:
    af = ActuarialFrame(_BOOK)
    af.term = af.maturity - af.issue
    return af


def _per_period() -> ActuarialFrame:
    af = ActuarialFrame(_BOOK).projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_months",
        until_value=1,
        frequency="monthly",
    )
    af.term = (
        pl.col("maturity").repeat_by(2).list.eval(pl.element() - dt.date(2020, 1, 1))
    )
    return af


def _operand(af: ActuarialFrame, written: str) -> object:
    return {"2": 2, "2.0": 2.0, "af.n": af.n, "af.x": af.x, "af.flag": af.flag}[written]


_REFUSED_PER_POLICY = [
    (symbol, other, order)
    for symbol in _OPS
    for other in ("2", "2.0", "af.n", "af.x", "af.flag")
    for order in ("left", "right")
    if not (symbol == "*" or (symbol == "/" and order == "left"))
]


@pytest.mark.parametrize(("symbol", "other", "order"), _REFUSED_PER_POLICY)
def test_a_duration_beside_a_number_is_refused_at_the_line(
    symbol: str, other: str, order: str
) -> None:
    af = _per_policy()
    number = _operand(af, other)
    pair = (af.term, number) if order == "left" else (number, af.term)

    with pytest.raises(TypeError) as refused:
        af.r = _OPS[symbol](*pair)

    said = " ".join(str(refused.value).split())
    assert "the column 'term' is a duration, and arithmetic reads numbers" in said
    assert "section 11.1.25" in said
    assert ".polars_native().dt.total_days()" in said
    assert "no time-delta type" in said


@pytest.mark.parametrize("symbol", list(_OPS))
@pytest.mark.parametrize("other", ["2", "2.0", "af.n"])
def test_a_run_of_durations_beside_a_number_is_refused_unless_it_is_scaled(
    symbol: str, other: str
) -> None:
    af = _per_period()
    number = _operand(af, other)
    if symbol in ("*", "/") and other in ("2", "2.0"):
        af.r = _OPS[symbol](af.term, number)
        assert af.collect()["r"].dtype == pl.List(pl.Duration("us"))
        return

    with pytest.raises(TypeError, match="the column 'term' is a duration"):
        af.r = _OPS[symbol](af.term, number)
    with pytest.raises(TypeError, match="the column 'term' is a duration"):
        af.r = _OPS[symbol](number, af.term)


@pytest.mark.parametrize(
    ("line", "hand"),
    [
        (lambda af: af.term * 2, [t * 2 for t in _TERM]),
        (lambda af: 2.0 * af.term, [t * 2 for t in _TERM]),
        (lambda af: af.term * af.n, [_TERM[0] * 2, _TERM[1] * 3]),
        (lambda af: af.term / 2, [t / 2 for t in _TERM]),
        (lambda af: af.term / af.x, [_TERM[0] / 2.0, _TERM[1] / 0.5]),
        (lambda af: af.term * af.flag, [_TERM[0], dt.timedelta(0)]),
    ],
    ids=["term*2", "2.0*term", "term*n", "term/2", "term/x", "term*flag"],
)
def test_a_duration_scaled_by_a_number_still_answers(
    line: Callable[[ActuarialFrame], object], hand: list[dt.timedelta]
) -> None:
    af = _per_policy()
    af.r = line(af)

    out = af.collect()["r"]

    assert out.dtype == pl.Duration("us")
    assert out.to_list() == hand


def test_two_dates_are_still_left_to_the_engine() -> None:
    af = _per_policy()

    assert af.collect()["term"].to_list() == _TERM
