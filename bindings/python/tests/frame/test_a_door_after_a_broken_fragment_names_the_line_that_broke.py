# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A door resolving the plan after a fragment Polars cannot type names that line.

``af.band = pl.col("code") * pl.col("sa")`` over a text column is accepted where
it is written -- it is a raw Polars fragment, and Polars types it only when the
plan resolves -- and from then on the plan does not resolve. An assignment
after it is accepted and ``collect()`` names the broken line. But
``projection.set``, ``select``, ``rename`` and ``drop`` resolve the whole plan
at their own line, so each raised the earlier break there, in Polars' words,
naming no line at all; ``with_columns`` named the line but ran into the break
inside its own batch. Each now raises the break before it runs, through the
frame's error handler as ``collect()`` does, naming the column and the line
that broke, with a note that the door itself was not run. A plan that resolves
is left to the door, so the door's own errors stay its own.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "code": ["7", "8", "9"],
        "sa": [100.0, 200.0, 300.0],
        "q": [0.1, 0.2, 0.3],
    }
)


def _broken(kind: str) -> tuple[ActuarialFrame, int]:
    """Return a frame holding a fragment Polars cannot type, and its line."""
    af = ActuarialFrame(_BOOK)
    if kind == "text times a number":
        af.band = pl.col("code") * pl.col("sa")
        line = sys._getframe().f_lineno - 1  # noqa: SLF001 -- the line above
    elif kind == "a column that does not exist":
        af.band = pl.col("nope") * 2.0
        line = sys._getframe().f_lineno - 1  # noqa: SLF001 -- the line above
    else:
        af.band = pl.col("sa").list.sum()
        line = sys._getframe().f_lineno - 1  # noqa: SLF001 -- the line above
    af.healthy = af.sa * 2.0
    return af, line


_DOORS: dict[str, Callable[[ActuarialFrame], object]] = {
    "projection.set": lambda af: af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=2,
        frequency="monthly",
    ),
    "with_columns": lambda af: af.with_columns((pl.col("sa") * 2.0).alias("out")),
    "select": lambda af: af.select("policy_id", "sa"),
    "rename": lambda af: af.rename({"q": "qx"}),
    "drop": lambda af: af.drop("q"),
}
_KINDS = (
    "text times a number",
    "a column that does not exist",
    "a list method on a number",
)


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("door", list(_DOORS))
def test_the_door_names_the_line_that_broke(door: str, kind: str) -> None:
    af, line = _broken(kind)

    with pytest.raises(pl.exceptions.PolarsError) as raised:
        _DOORS[door](af)

    message = str(raised.value)
    assert "Failing column: 'band'" in message or "Operation: band" in message, message
    assert f"{Path(__file__).name}:{line}" in message, message
    notes = getattr(raised.value, "__notes__", ())
    assert any(f"{door}() was not run" in note for note in notes), notes


@pytest.mark.parametrize("door", list(_DOORS))
def test_a_door_with_no_break_before_it_runs(door: str) -> None:
    af = ActuarialFrame(_BOOK)
    af.healthy = af.sa * 2.0

    _DOORS[door](af)

    assert af.collect().height == 3


def test_a_door_whose_own_expression_fails_is_still_the_door() -> None:
    af = ActuarialFrame(_BOOK)
    af.healthy = af.sa * 2.0

    with pytest.raises(pl.exceptions.ColumnNotFoundError) as raised:
        af.drop("nope")

    notes = getattr(raised.value, "__notes__", ())
    assert not any("was not run" in note for note in notes)


def test_a_break_the_schema_cannot_see_leaves_the_door_to_run() -> None:
    """A text method on a number types; only running it fails, at collect."""
    af = ActuarialFrame(_BOOK)
    af.band = pl.col("sa").str.len_chars()

    af = af.rename({"q": "qx"})

    with pytest.raises(pl.exceptions.PolarsError):
        af.collect()
