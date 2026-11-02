# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An ``is_in`` member of another kind than the value is refused at the line.

``af.d.is_in([1, 2])`` over dates and ``af.x.is_in(["a"])`` over decimals ran
to ``collect()`` and failed there in Polars' words: ``'is_in' cannot check for
List(Int64) values in Date data``. Membership is equality (11.1.5), and
equality across two kinds is no comparison 11.1.26 states, so a member of
another kind is refused where the line is written, naming the move. A flag
member for a number, or a number for a flag, which Polars likewise refused,
is refused the same way.
"""

from __future__ import annotations

import datetime as dt
import re

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

_START = dt.date(2025, 1, 1)


def _frame() -> ActuarialFrame:
    """Two policies holding each kind once."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "x": [1.5, 4.0],
                "i": [1, 5],
                "s": ["a", "b"],
                "c": pl.Series(["a", "b"], dtype=pl.Categorical),
                "d": [_START, dt.date(2026, 6, 1)],
                "b": [True, None],
                "f": [1.0, float("nan")],
            }
        )
    )


def _projected() -> ActuarialFrame:
    """Return the book on a monthly axis, with a per-period decimal, text and flag."""
    af = _frame().projection.set(start_date=_START, n_periods=2, frequency="monthly")
    af.xl = af.x * af.month
    af.sl = when(af.month >= 1).then("y").otherwise("n")
    af.bl = af.xl.is_in([0, 1])
    return af


# --- is_in --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "members", "said"),
    [
        (
            "d",
            [1, 2],
            "its member -- 1 -- is a whole number, and the value it tests is a date",
        ),
        ("d", ["2025-01-01"], "is text, and the value it tests is a date"),
        (
            "x",
            ["a"],
            "its member -- 'a' -- is text, and the value it tests is a decimal",
        ),
        ("x", [True], "is a flag (True/False), and the value it tests is a decimal"),
        ("s", [1, 2], "is a whole number, and the value it tests is text"),
        ("c", [1], "is a whole number, and the value it tests is text"),
        ("b", [1], "is a whole number, and the value it tests is a flag"),
        ("b", ["a"], "is text, and the value it tests is a flag"),
    ],
)
def test_members_of_another_kind_are_refused_at_the_line(
    column: str, members: list[object], said: str
) -> None:
    """Each pair Polars refused at ``collect()`` is refused where it is written."""
    af = _frame()
    with pytest.raises(TypeError, match=re.escape(said)):
        af.r = af[column].is_in(members)


def test_a_membership_set_that_is_a_column_of_another_kind_is_refused() -> None:
    """A set read from a column is held to the value's kind too."""
    af = _frame()
    with pytest.raises(TypeError, match="the column 's' -- is text"):
        af.r = af.x.is_in(af.s)


@pytest.mark.parametrize(
    ("column", "members"),
    [("sl", [1]), ("xl", ["a"])],
)
def test_per_period_members_of_another_kind_are_refused(
    column: str, members: list[object]
) -> None:
    """Per period the same pairs are refused at the line."""
    af = _projected()
    with pytest.raises(TypeError, match=r"is_in\(\): its member"):
        af.r = af[column].is_in(members)


def test_each_move_names_a_line_that_runs() -> None:
    """Numbers tested as codes go through to_text(); dates through comparisons."""
    af = _frame()
    with pytest.raises(TypeError, match=re.escape("af.x.to_text().is_in([...])")):
        af.r = af.x.is_in(["a"])
    with pytest.raises(TypeError, match=re.escape("(af.d == date(2025, 6, 1)) |")):
        af.r = af.d.is_in([1])
    af.codes = af.x.to_text().is_in(["1.5"])
    af.dates = (af.d == _START) | (af.d == dt.date(2026, 1, 1))
    out = af.collect()
    assert out["codes"].to_list() == [True, False]
    assert out["dates"].to_list() == [True, False]


@pytest.mark.parametrize(
    ("column", "members", "want"),
    [
        ("i", [1.0, 2.5], [True, False]),
        ("x", [1, 4], [False, True]),
        ("s", ["a"], [True, False]),
        ("c", ["b"], [False, True]),
        ("b", [True], [True, None]),
    ],
)
def test_members_of_the_values_kind_answer_as_before(
    column: str, members: list[object], want: list[bool | None]
) -> None:
    """A whole number beside a decimal is one kind; a category is text."""
    af = _frame()
    af.r = af[column].is_in(members)
    assert af.collect()["r"].to_list() == want
