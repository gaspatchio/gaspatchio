# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A condition with no truth value selects neither branch; a branch's null has no say.

Section 11.1.28: a condition a NaN left without a truth value "selects
neither branch: the answer is NaN where it is a double ... per policy and per
period alike". Per period the producer answered NaN by adding a NaN term to
the selection -- and a null plus a NaN is a null, so where the branch the
kernel picked held a null at that very period the answer was null. Which
branch the null sat in decided it: ``when(L < 1).then(a).otherwise(run)``
with the run null where ``L`` is NaN answered null, the same null in the
``then`` answered NaN, and per policy every placement answered NaN. Now the
cell is NaN wherever the answer is a double, whichever branch holds the null,
on every route a per-period selection takes; a type that holds no NaN keeps
its null.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable

NAN = float("nan")
ENGINES = ["in-memory", "streaming"]


def _same(got: object, want: object) -> bool:
    if isinstance(want, list):
        return (
            isinstance(got, list)
            and len(got) == len(want)
            and all(_same(g, w) for g, w in zip(got, want, strict=True))
        )
    if isinstance(want, float) and math.isnan(want):
        return isinstance(got, float) and math.isnan(got)
    return got == want


# Per period the condition's run is NaN at period 1; per policy x is NaN.
_BOOK = {
    "L": pl.Series("L", [[0.5, NAN, 2.0]]),
    "M": pl.Series("M", [[9.0, 9.0, 9.0]]),
    "x": pl.Series("x", [NAN]),
    "Li": pl.Series("Li", [[1, 5, 9]], dtype=pl.List(pl.Int64)),
}

# The routes a per-period double selection takes over a condition with no
# truth value at period 1 (every period, for a per-policy NaN).
_ROUTES: dict[str, Callable[[ActuarialFrame], object]] = {
    "L < 1": lambda af: af.L < 1.0,
    "L > 1": lambda af: af.L > 1.0,
    "L != 1": lambda af: af.L != 1.0,
    "L < M": lambda af: af.L < af.M,
    "1 > L": lambda af: 1.0 > af.L,  # noqa: SIM300 -- the commuted form is the case
    "(L < 1) | (M > 10)": lambda af: (af.L < 1.0) | (af.M > 10.0),
    "~(L < 1)": lambda af: ~(af.L < 1.0),
    "Li > x": lambda af: af.Li > af.x,
    "x < 1": lambda af: af.x < 1.0,
}

# A double answer's pairings: (the scalar branch, its dtype, the run's dtype,
# the run with a null at period 1).
_DOUBLES = {
    "f64|f64": (1.5, pl.Float64, pl.Float64, [7.5, None, 9.5]),
    "i64|f64": (3, pl.Int64, pl.Float64, [7.5, None, 9.5]),
    "bool|i64": (True, pl.Boolean, pl.Int64, [7, None, 9]),
    "bool|f64": (True, pl.Boolean, pl.Float64, [7.5, None, 9.5]),
}


def _frame(
    scalar: object, scalar_dtype: object, run_dtype: object, run: list
) -> ActuarialFrame:
    columns = [
        *_BOOK.values(),
        pl.Series("a", [scalar], dtype=scalar_dtype),  # type: ignore[arg-type]
        pl.Series("run", [run], dtype=pl.List(run_dtype)),  # type: ignore[arg-type]
    ]
    return ActuarialFrame(pl.DataFrame(columns))


def _unknown_at(route: str) -> list[int]:
    return [0, 1, 2] if route in {"Li > x", "x < 1"} else [1]


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("placed", ["then", "otherwise"])
@pytest.mark.parametrize("pair", list(_DOUBLES))
@pytest.mark.parametrize("route", list(_ROUTES))
def test_a_double_answer_is_nan_whichever_branch_holds_the_null(
    route: str, pair: str, placed: str, engine: str
) -> None:
    af = _frame(*_DOUBLES[pair])
    condition = _ROUTES[route](af)
    if placed == "then":
        af.answer = when(condition).then(af.run).otherwise(af.a)
    else:
        af.answer = when(condition).then(af.a).otherwise(af.run)
    (answer,) = af.collect(engine=engine).get_column("answer").to_list()
    for period in _unknown_at(route):
        assert isinstance(answer[period], float), (period, answer)
        assert math.isnan(answer[period]), (period, answer)


@pytest.mark.parametrize("engine", ENGINES)
def test_the_other_periods_keep_the_branch_they_select(engine: str) -> None:
    af = _frame(1.5, pl.Float64, pl.Float64, [None, None, 9.5])
    af.answer = when(af.L < 1.0).then(af.a).otherwise(af.run)
    af.held = when(af.L > 1.0).then(af.a).otherwise(af.run)
    out = af.collect(engine=engine)
    assert _same(out.get_column("answer").to_list(), [[1.5, NAN, 9.5]])
    # Period 0 selects the run's own null; period 1 has no truth value.
    assert _same(out.get_column("held").to_list(), [[None, NAN, 1.5]])


_NO_NAN = {
    "i64|i64": (3, pl.Int64, [7, None, 9]),
    "bool|bool": (True, pl.Boolean, [True, None, False]),
    "str|str": ("a", pl.String, ["b", None, "c"]),
    "date|date": (
        dt.date(2020, 1, 1),
        pl.Date,
        [dt.date(2021, 1, 1), None, dt.date(2022, 1, 1)],
    ),
    "datetime|datetime": (
        dt.datetime(2020, 1, 1),  # noqa: DTZ001 -- a naive instant is the case
        pl.Datetime("us"),
        [dt.datetime(2021, 1, 1), None, dt.datetime(2022, 1, 1)],  # noqa: DTZ001
    ),
}


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("pair", list(_NO_NAN))
def test_a_type_that_holds_no_nan_keeps_its_null(pair: str, engine: str) -> None:
    scalar, dtype, run = _NO_NAN[pair]
    af = _frame(scalar, dtype, dtype, run)
    af.answer = when(af.L < 1.0).then(af.a).otherwise(af.run)
    (answer,) = af.collect(engine=engine).get_column("answer").to_list()
    assert answer[1] is None
