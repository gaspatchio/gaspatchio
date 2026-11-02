# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars itself still writes the lines the error door lifts a sentence above.

Two lifts key on Polars' own wording: a strict read by position that finds no
value (``get index is out of bounds``) and text a strict parse cannot read as
a date or a date and time (``conversion from `str` to `date` failed in column
'x' for 1 out of 3 values: [...]``). The replay past its head keys on the same
two lines. If an upgrade rewords either, the lift stops and the engine's text
stands -- the safe direction, but silent. These run against Polars with no
gaspatchio in the way, so a rewording fails here by name.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio.errors.boundary import (
    _A_DATE_PARSE,
    _STRICT_CAST_LINE,
)
from gaspatchio.errors.boundary import (
    _POSITION_NOT_HELD as _REPLAY_POSITION_LINE,
)
from gaspatchio.errors.formatting_errors import _NOT_A_DATE, _POSITION_NOT_HELD

_ENGINES = ("in-memory", "streaming")


def _first_line(error: BaseException) -> str:
    return str(error).split("\n", 1)[0]


@pytest.mark.parametrize("engine", _ENGINES)
def test_polars_still_raises_the_position_line(engine: str) -> None:
    plan = (
        pl.DataFrame({"av": [[1.0, 2.0, 3.0], [1.0]]})
        .lazy()
        .select(pl.col("av").list.get(2))
    )
    with pytest.raises(pl.exceptions.ComputeError) as refused:
        plan.collect(engine=engine)  # type: ignore[call-overload]

    assert _first_line(refused.value).strip() == _POSITION_NOT_HELD
    assert _POSITION_NOT_HELD == _REPLAY_POSITION_LINE


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize(
    ("parse", "texts"),
    [
        (
            pl.col("t").str.to_date("%Y-%m-%d"),
            ["2025-01-01", "31/12/2025", "2025-03-01"],
        ),
        (
            pl.col("t").str.to_datetime("%Y-%m-%d %H:%M:%S"),
            ["2025-01-01 00:00:00", "31/12/2025 10:00", "2025-03-01 00:00:00"],
        ),
        (
            pl.col("t").str.to_datetime(
                "%Y-%m-%d %H:%M:%S", time_unit="ns", time_zone="UTC"
            ),
            ["2025-01-01 00:00:00", "31/12/2025 10:00", "2025-03-01 00:00:00"],
        ),
    ],
    ids=["date", "datetime", "datetime-ns-utc"],
)
def test_polars_still_raises_the_failed_parse_line(
    engine: str, parse: pl.Expr, texts: list[str]
) -> None:
    plan = pl.DataFrame({"t": texts}).lazy().select(x=parse)
    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        plan.collect(engine=engine)  # type: ignore[call-overload]

    first = _first_line(refused.value)
    lifted = _NOT_A_DATE.match(first)
    assert lifted is not None, first
    assert lifted.group(2) == "t"
    assert "31/12/2025" in lifted.group(3)
    replayed = _STRICT_CAST_LINE.fullmatch(first)
    assert replayed is not None, first
    assert replayed.group(2) == "t"
    assert _A_DATE_PARSE.search(replayed.group(1)) is not None, first
