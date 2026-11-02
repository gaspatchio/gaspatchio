# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-policy test a NaN left unknown, beside a run, is unknown in every period.

Sections 11.1.26-28 and 11.1.18: a per-policy value repeats over its
policy's periods, so ``(af.month < 2) | (af.av / af.gtee > 1.0)`` over a
zero guarantee has no truth value in any period, and a ``when`` over it
answers NaN in every period. This engine answered NaN in period 0 only and
read the unknown as false from period 1 on whenever the run beside it was
not a double -- a whole number (the projection's own ``month``), text, a
date, a stored flag, ``flag == True`` -- under ``|``, ``&``, ``<`` and
``!=`` in either order: the per-policy unknown was kept one cell wide and
widened as though it were a run one period long.
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

NAN = math.nan
D = dt.date


def _same(left: object, right: object) -> bool:
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, float) and isinstance(right, float):
        return (math.isnan(left) and math.isnan(right)) or left == right
    return left == right


_BOOK = pl.DataFrame(
    [
        pl.Series("x", [NAN, 0.5]),
        pl.Series("Lf", [[0.5, 2.0, 3.0]] * 2),
        pl.Series("Li", [[1, 5, 9]] * 2, dtype=pl.List(pl.Int64)),
        pl.Series("Lt", [["a", "m", "z"]] * 2),
        pl.Series("Ld", [[D(2020, 1, 1), D(2021, 1, 1), D(2022, 1, 1)]] * 2),
        pl.Series("d", [D(2020, 6, 1)] * 2),
        pl.Series("Lb", [[True, False, True]] * 2),
        pl.Series("q", [0.5, 0.5]),
    ]
)

_RUNS: dict[str, Callable[[ActuarialFrame], object]] = {
    "f64": lambda af: af.Lf > 1.0,
    "i64": lambda af: af.Li > 4,
    "text": lambda af: af.Lt <= "m",
    "date": lambda af: af.Ld < af.d,
    "scalar date": lambda af: af.d > af.Ld,
    "stored flag": lambda af: af.Lb,
    "flag == True": lambda af: af.Lb == True,  # noqa: E712 -- the written form is the case
}

_OPERATORS: dict[str, Callable[[object, object], object]] = {
    "|": lambda p, n: p | n,  # type: ignore[operator]
    "&": lambda p, n: p & n,  # type: ignore[operator]
    "<": lambda p, n: p < n,  # type: ignore[operator]
    "!=": lambda p, n: p != n,
    "n | p": lambda p, n: n | p,  # type: ignore[operator]
}


@pytest.mark.parametrize("operator", list(_OPERATORS))
@pytest.mark.parametrize("run", list(_RUNS))
def test_the_when_over_it_is_nan_in_every_period(run: str, operator: str) -> None:
    af = ActuarialFrame(_BOOK)
    combined = _OPERATORS[operator](_RUNS[run](af), af.x < 1.0)
    af.chosen = when(combined).then(af.q).otherwise(0.001)
    af.stored = combined * 1.0
    producer, engine = af.collect(), af.collect(engine="jax")
    for column in ("chosen", "stored"):
        assert _same(
            engine.get_column(column).to_list(), producer.get_column(column).to_list()
        ), column
    first = engine.get_column("chosen").to_list()[0]
    assert all(math.isnan(v) for v in first), first


def test_the_projection_s_own_month_beside_a_zero_guarantee() -> None:
    book = pl.DataFrame({"av": [0.0, 120.0], "gtee": [0.0, 100.0]})
    af = ActuarialFrame(book)
    af = af.projection.set(
        valuation_date=dt.date(2025, 1, 1),
        frequency="monthly",
        until="term_months",
        until_value=3,
    )
    af.itm = when((af.month < 2) | (af.av / af.gtee > 1.0)).then(1.0).otherwise(0.0)
    producer, engine = af.collect(), af.collect(engine="jax")
    assert _same(
        engine.get_column("itm").to_list(), producer.get_column("itm").to_list()
    )
    assert all(math.isnan(v) for v in engine.get_column("itm").to_list()[0])
    assert engine.get_column("itm").to_list()[1] == [1.0, 1.0, 1.0, 1.0]
