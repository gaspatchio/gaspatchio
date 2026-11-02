# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period fold of whole numbers is exact, and one past i64 is refused by name.

A sum, a running sum or product and a remaining sum of a per-period ``i64``
run were taken in its own width and wrapped: ``[2**63 - 1, 1].list.sum()``
answered ``-2**63`` and its ``cum_sum`` ``[2**63 - 1, -2**63]``, on both
Polars engines, with the record saying ``i64``. The total of a run is now
taken exactly, and an answer no ``i64`` holds -- the total, or one period of
a running fold -- is refused naming the column and the fold, as a total of
the book (``run_aggregated``'s ``Sum``) already is. A total that fits is
answered even where a running total on the way passed the range.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX = 2**63 - 1
_MIN = -(2**63)
_ENGINES = ["in-memory", "streaming"]

_FOLDS: dict[str, Callable[[ActuarialFrame], object]] = {
    "sum": lambda af: af.n.list.sum(),
    "running sum": lambda af: af.n.cum_sum(),
    "running product": lambda af: af.n.cum_prod(),
    "remaining sum": lambda af: af.n.projection.remaining_sum(),
}


def _run(runs: list[list[int | None]], fold: str, engine: str) -> list[object]:
    af = ActuarialFrame(pl.DataFrame({"n": pl.Series(runs, dtype=pl.List(pl.Int64))}))
    af.r = _FOLDS[fold](af)
    return af.collect(engine=engine)["r"].to_list()  # type: ignore[arg-type]


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize(
    ("fold", "run"),
    [
        ("sum", [_MAX, 1]),
        ("sum", [_MIN, -1]),
        ("sum", [2**62, 2**62]),
        ("running sum", [_MAX, 1]),
        ("running sum", [_MAX, 1, -1]),
        ("running product", [2**32, 2**32]),
        ("running product", [_MIN, -1]),
        ("running product", [2**62, 2**62, 0]),
        ("remaining sum", [_MAX, 1]),
    ],
    ids=str,
)
def test_a_fold_past_i64_is_refused_by_name(
    engine: str, fold: str, run: list[int]
) -> None:
    with pytest.raises(
        Exception, match=rf"Column 'n' holds whole numbers whose {fold}"
    ):
        _run([[1, 2, 3], run], fold, engine)


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize(
    ("fold", "run", "expected"),
    [
        # Totals that fit, by hand, although 2**63 - 1 + 1 passes on the way.
        ("sum", [_MAX, 1, -1], _MAX),
        ("sum", [_MIN, 0], _MIN),
        ("sum", [2**53 + 1, 2], 2**53 + 3),
        ("running sum", [_MAX, -1, 1], [_MAX, _MAX - 1, _MAX]),
        ("running product", [2**31, 2**31], [2**31, 2**62]),
        ("running product", [_MAX, 1, -1], [_MAX, _MAX, -_MAX]),
        ("remaining sum", [_MAX, 1, -1], [_MAX, 0, -1]),
        # A period with no value: the total is null, never refused.
        ("sum", [_MAX, None, 1], None),
        ("running sum", [_MAX, None, 1], [_MAX, None, None]),
    ],
    ids=str,
)
def test_a_fold_that_fits_is_answered_exactly(
    engine: str, fold: str, run: list[int | None], expected: object
) -> None:
    answers = _run([[1, 2, 3], run, [], None], fold, engine)
    ordinary = {
        "sum": 6,
        "running sum": [1, 3, 6],
        "running product": [1, 2, 6],
        "remaining sum": [6, 5, 3],
    }[fold]
    empty = 0 if fold == "sum" else []
    assert answers == [ordinary, expected, empty, None]


def test_the_frame_s_type_stays_the_record_s_i64() -> None:
    af = ActuarialFrame(
        pl.DataFrame({"n": pl.Series([[_MAX, 1, -1]], dtype=pl.List(pl.Int64))})
    )
    af.total = af.n.list.sum()
    af.running = af.n.cum_prod()
    out = af.collect()
    assert out.schema["total"] == pl.Int64
    assert out.schema["running"] == pl.List(pl.Int64)


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("shape", ["per policy", "per period"])
def test_the_absolute_value_of_minus_2_63_is_refused_by_name(
    engine: str, shape: str
) -> None:
    """``abs(-2**63)`` answered ``-2**63`` in its own width, a negative magnitude."""
    values: list[object] = [-5, _MIN] if shape == "per policy" else [[-5, 1], [_MIN, 1]]
    dtype = pl.Int64 if shape == "per policy" else pl.List(pl.Int64)
    af = ActuarialFrame(pl.DataFrame({"n": pl.Series(values, dtype=dtype)}))
    af.r = af.n.abs()
    with pytest.raises(
        pl.exceptions.InvalidOperationError,
        match=r"Column 'n' holds -2\*\*63, whose absolute value 2\*\*63",
    ):
        af.collect(engine=engine)  # type: ignore[arg-type]


@pytest.mark.parametrize("engine", _ENGINES)
def test_the_absolute_value_of_every_other_whole_number_is_answered(
    engine: str,
) -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            {"n": pl.Series([[_MIN + 1, -3, None], None], dtype=pl.List(pl.Int64))}
        )
    )
    af.r = af.n.abs()
    out = af.collect(engine=engine)  # type: ignore[arg-type]
    assert out["r"].to_list() == [[_MAX, 3, None], None]


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_run_of_flags_totals_to_the_i64_the_record_names(engine: str) -> None:
    """Polars totalled a run of flags as UInt64 and ran it as List(UInt32)."""
    flags = pl.Series([[True, False, True], [False, False]], dtype=pl.List(pl.Boolean))
    af = ActuarialFrame(pl.DataFrame({"in_force": flags}))
    af.policies = af.in_force.list.sum()
    af.running = af.in_force.cum_sum()
    out = af.collect(engine=engine)  # type: ignore[arg-type]
    assert out.schema["policies"] == pl.Int64
    assert out.schema["running"] == pl.List(pl.Int64)
    assert out["policies"].to_list() == [2, 0]
    assert out["running"].to_list() == [[1, 1, 2], [0, 0]]
