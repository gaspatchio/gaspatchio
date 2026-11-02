# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A policy with no run compares to null, whichever side of the comparison it is on.

A null outer list is a policy with no periods, and a comparison or a
conditional on one is null (11.1.25, 11.1.26, 11.1.28). Written with the
absent run on the left -- ``gmdb > av`` -- the frame answered null; written
with it on the right -- ``av < gmdb`` -- the kernel padded it to a null in
each period and answered ``[None, None]``. The two lines mean one thing, and
a ``fill_null(0.0)`` then a total gave 0.0 for one and null for the other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable

# Policy 2 holds no guarantee run. By hand, policy 1: 100 < 95 is false and
# 90 < 95 is true, so the indicator is [0.0, 1.0]; policy 2 is null.
_BOOK = pl.DataFrame(
    [
        pl.Series("av", [[100.0, 90.0], [50.0, 40.0]], dtype=pl.List(pl.Float64)),
        pl.Series("gmdb", [[95.0, 95.0], None], dtype=pl.List(pl.Float64)),
        pl.Series("n", [[1, 2], [3, 4]], dtype=pl.List(pl.Int64)),
        pl.Series("cap", [[2, 2], None], dtype=pl.List(pl.Int64)),
    ]
)
_ENGINES = ["in-memory", "streaming"]


_LINES: dict[str, tuple[Callable[[ActuarialFrame], object], list[object]]] = {
    "av < gmdb": (lambda af: af.av < af.gmdb, [[0.0, 1.0], None]),
    "gmdb > av": (lambda af: af.gmdb > af.av, [[0.0, 1.0], None]),
    "av <= gmdb": (lambda af: af.av <= af.gmdb, [[0.0, 1.0], None]),
    "av >= gmdb": (lambda af: af.av >= af.gmdb, [[1.0, 0.0], None]),
    "av == gmdb": (lambda af: af.av == af.gmdb, [[0.0, 0.0], None]),
    "av != gmdb": (lambda af: af.av != af.gmdb, [[1.0, 1.0], None]),
    # Two whole-number runs go through the exact route: 1 < 2, 2 < 2.
    "n < cap": (lambda af: af.n < af.cap, [[1.0, 0.0], None]),
    "cap > n": (lambda af: af.cap > af.n, [[1.0, 0.0], None]),
    # A double against a whole number: 100 > 2 and 90 > 2.
    "av > cap": (lambda af: af.av > af.cap, [[1.0, 1.0], None]),
}


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("written", list(_LINES))
def test_a_null_run_on_either_side_answers_null(engine: str, written: str) -> None:
    line, expected = _LINES[written]
    af = ActuarialFrame(_BOOK)
    af.r = line(af)
    out = af.collect(engine=engine)  # type: ignore[arg-type]
    assert out["r"].dtype == pl.List(pl.Float64)
    assert out["r"].to_list() == expected


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_conditional_on_it_answers_null_and_a_total_does_not_move_with_the_order(
    engine: str,
) -> None:
    af = ActuarialFrame(_BOOK)
    af.short_r = when(af.av < af.gmdb).then(af.gmdb - af.av).otherwise(0.0)
    af.short_l = when(af.gmdb > af.av).then(af.gmdb - af.av).otherwise(0.0)
    af.total_r = af.short_r.fill_null(0.0).list.sum()
    af.total_l = af.short_l.fill_null(0.0).list.sum()
    out = af.collect(engine=engine)  # type: ignore[arg-type]
    # Policy 1 by hand: [0.0, 95 - 90] = [0.0, 5.0], totalling 5.0.
    assert out["short_r"].to_list() == [[0.0, 5.0], None]
    assert out["short_l"].to_list() == [[0.0, 5.0], None]
    assert out["total_r"].to_list() == out["total_l"].to_list()
    assert out["total_r"].to_list()[0] == 5.0
