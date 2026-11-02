# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A period operation that runs in doubles widens a whole-number run on the record.

``accumulate`` already wrote ``to_float(...)`` around a whole-number operand,
the checked widening that refuses a whole number outside [-2**53, 2**53]
(section 11.1.20). Its siblings converted silently: a shift under the
default ``0.0`` fill, ``prospective_value`` and ``cumulative_survival``
computed an integer run in doubles, so a policy count of 2**53 + 1 came back
as 2**53, and a shift's record still named the column ``list[i64]`` while the
frame held ``list[f64]``. They now follow the one rule: the widening is on
the record, refused past 2**53, and the record's type is the frame's.
"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_PAST = 2**53 + 1


def _frame(n: int) -> ActuarialFrame:
    book = pl.DataFrame({"pid": [1, 2], "n": [3, n], "r": [0.0, 0.0]})
    af = ActuarialFrame(book).projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.k = af.n + af.month
    return af


def _node(af: ActuarialFrame, column: str) -> dict[str, Any]:
    document = json.loads(GraphExporter(af).export(profile="executable"))
    return next(n for n in document["nodes"] if n.get("column") == column)


# (what the author wrote, the line, the hand values over k = [[3, 4, 5], [10, 11, 12]]).
_WIDENED: list[tuple[str, Callable[[Any], Any], list[list[float]]]] = [
    (
        "k.previous_period()",
        lambda af: af.k.projection.previous_period(),
        [[0.0, 3.0, 4.0], [0.0, 10.0, 11.0]],
    ),
    (
        "k.next_period()",
        lambda af: af.k.projection.next_period(),
        [[4.0, 5.0, 0.0], [11.0, 12.0, 0.0]],
    ),
    (
        "k.at_period(-1)",
        lambda af: af.k.projection.at_period(-1),
        [[0.0, 3.0, 4.0], [0.0, 10.0, 11.0]],
    ),
    (
        "k.prospective_value(discount_rate=af.r)",
        lambda af: af.k.projection.prospective_value(discount_rate=af.r),
        [[12.0, 9.0, 5.0], [33.0, 23.0, 12.0]],
    ),
    (
        "(month * 0).cumulative_survival()",
        lambda af: (af.month * 0).projection.cumulative_survival(),
        [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "expected"), _WIDENED, ids=[w[0] for w in _WIDENED]
)
def test_a_whole_number_run_is_widened_on_the_record(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[list[float]],
) -> None:
    af = _frame(10)
    af.out = line(af)
    out = af.collect()

    assert out["out"].to_list() == expected
    assert out.schema["out"] == pl.List(pl.Float64)
    node = _node(af, "out")
    assert node["dtype"] == "list[f64]"
    assert node["expr"]["args"][0]["name"] == "to_float"


@pytest.mark.parametrize(
    ("written", "line"),
    [(w[0], w[1]) for w in _WIDENED if "survival" not in w[0]],
    ids=[w[0] for w in _WIDENED if "survival" not in w[0]],
)
def test_a_whole_number_no_double_names_is_refused_as_accumulate_refuses_it(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
) -> None:
    """2**53 + 1 came back as 2**53 (9007199254740992.0) without a word."""
    af = _frame(_PAST)
    af.out = line(af)

    with pytest.raises(
        Exception, match=r"holds a whole number outside \[-2\*\*53, 2\*\*53\]"
    ):
        af.collect()


def test_a_shift_under_a_whole_number_fill_keeps_the_run_whole() -> None:
    """No widening is made, so none is written: 2**53 + 1 shifts as itself."""
    af = _frame(_PAST)
    af.out = af.k.projection.previous_period(fill_value=7)
    out = af.collect()

    assert out["out"].to_list() == [[7, 3, 4], [7, _PAST, _PAST + 1]]
    assert out.schema["out"] == pl.List(pl.Int64)
    assert _node(af, "out")["dtype"] == "list[i64]"


def test_a_decimal_run_is_read_as_it_stands() -> None:
    af = _frame(10)
    af.x = af.k * 0.5
    af.out = af.x.projection.previous_period()
    af.collect()

    assert _node(af, "out")["expr"]["args"][0] == {"op": "col", "name": "x"}
