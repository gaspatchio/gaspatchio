# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A line written after a fragment Polars cannot type reads the types the model wrote.

``af.band = pl.col("code") * pl.col("sa")`` over a text ``code`` is a line
Polars cannot type, and it stays in the plan: from it on, the plan's schema
no longer resolves, and the frame kept the last schema that did. On a frame
of fewer than sixteen columns nothing else updated it, so every column
written afterwards was read at its old type. A ``code`` recast to a number
was still text, and the healthy ``af.out = af.code * af.sa`` was refused as
text times a number -- naming the wrong line for the break -- while a number
column overwritten with text was still a number, and arithmetic on it was
let through. A frame of sixteen columns or more typed each assignment into
its cache and read both lines right. Every frame now does once the plan
stops resolving, and a column it cannot type is unknown rather than read at
a type the plan no longer holds. The break itself still fails at
``collect()``, naming its own column.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable

# Three lines Polars cannot type, each of which stops the plan resolving.
_BREAKS: dict[str, Callable[[ActuarialFrame], None]] = {
    "text times a number": lambda af: setattr(
        af, "band", pl.col("code") * pl.col("sa")
    ),
    "a column that does not exist": lambda af: setattr(
        af, "band", pl.col("nope") * 2.0
    ),
    "a list method on a number": lambda af: setattr(
        af, "band", pl.col("sa").list.sum()
    ),
}

# What collect says about each break: the break's own error, not a later line's.
_COLLECT_FAILS = (
    pl.exceptions.InvalidOperationError,
    pl.exceptions.ColumnNotFoundError,
)


def _frame(*, wide: bool = False) -> ActuarialFrame:
    columns: dict[str, list[object]] = {
        "policy_id": [1, 2, 3],
        "code": ["7", "8", "9"],
        "sa": [100.0, 200.0, 300.0],
        "n": [1, 2, 3],
        "status": ["IF", "LA", "IF"],
    }
    if wide:
        columns.update({f"pad{i}": [0.0, 0.0, 0.0] for i in range(12)})
    return ActuarialFrame(pl.DataFrame(columns))


def _recast(af: ActuarialFrame) -> None:
    af["code"] = af.code.polars_native().cast(pl.Float64)


# Healthy lines written after the break, each over a column whose type the
# model changed after it.
_HEALTHY: dict[str, Callable[[ActuarialFrame], ActuarialFrame]] = {}


def _arithmetic(af: ActuarialFrame) -> ActuarialFrame:
    _recast(af)
    af.out = af.code * af.sa
    return af


def _retyped(af: ActuarialFrame) -> ActuarialFrame:
    af["code"] = af.n
    af.out = af.code * 2
    return af


def _a_when(af: ActuarialFrame) -> ActuarialFrame:
    _recast(af)
    af.out = when(af.code > 7.5).then(af.sa).otherwise(0.0)
    return af


def _after_a_filter(af: ActuarialFrame) -> ActuarialFrame:
    _recast(af)
    af = af.filter(pl.col("status") == "IF")
    af.out = af.code * af.sa
    return af


def _round(af: ActuarialFrame) -> ActuarialFrame:
    _recast(af)
    af.out = af.code.round(0)
    return af


_HEALTHY.update(
    {
        "recast, then arithmetic": _arithmetic,
        "overwritten with a number, then arithmetic": _retyped,
        "recast, then a when": _a_when,
        "recast, a filter, then arithmetic": _after_a_filter,
        "recast, then round": _round,
    }
)


@pytest.mark.parametrize("after", list(_HEALTHY))
@pytest.mark.parametrize("brk", list(_BREAKS))
def test_a_healthy_line_after_the_break_is_written(brk: str, after: str) -> None:
    af = _frame()
    _BREAKS[brk](af)

    af = _HEALTHY[after](af)  # refused as text on the base

    with pytest.raises(_COLLECT_FAILS):
        af.collect()


@pytest.mark.parametrize("brk", list(_BREAKS))
def test_the_cache_holds_the_type_the_line_wrote(brk: str) -> None:
    af = _frame()
    _BREAKS[brk](af)

    _recast(af)

    assert af._schema is not None  # noqa: SLF001
    assert af._schema["code"] == pl.Float64  # noqa: SLF001


@pytest.mark.parametrize("brk", list(_BREAKS))
def test_a_number_overwritten_with_text_is_still_refused_after_the_break(
    brk: str,
) -> None:
    af = _frame()
    _BREAKS[brk](af)
    af["sa"] = af.status

    with pytest.raises(TypeError, match="the column 'sa' is text"):
        af.out = af.sa * 2.0


def test_a_column_it_cannot_type_is_unknown_rather_than_its_old_type() -> None:
    af = _frame()
    _BREAKS["text times a number"](af)

    af["code"] = pl.col("nope") + 1

    assert "code" not in (af._schema or {})  # noqa: SLF001
    af.out = af.code * af.sa  # left to the engine, never refused as text


@pytest.mark.parametrize("after", list(_HEALTHY))
def test_a_narrow_frame_reads_the_line_as_a_wide_one_does(after: str) -> None:
    narrow, wide = _frame(), _frame(wide=True)
    for af in (narrow, wide):
        _BREAKS["text times a number"](af)

    narrow, wide = _HEALTHY[after](narrow), _HEALTHY[after](wide)

    assert narrow._schema["out"] == wide._schema["out"]  # type: ignore[index]  # noqa: SLF001


@pytest.mark.parametrize("after", list(_HEALTHY))
def test_without_a_break_the_line_answers_as_it_did(after: str) -> None:
    af = _HEALTHY[after](_frame())

    assert af.collect()["out"].len() in (2, 3)
