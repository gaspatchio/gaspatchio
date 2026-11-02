# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period comparison with a null right side answers null in those periods.

A null value per policy repeats over the policy's periods (11.1.18), so each
of them compares to null; a null run per policy is a policy with no periods,
and the comparison is null for the whole policy (11.1.25, 11.1.26), as it is
with the null run on the left.

The graph-artifact specification (section 11.1.26) says of the six
comparisons: "A null operand yields a null comparison. Comparing nulls is not
null-safe equality." Per period, ``af.x == af.v`` with ``v`` null for one
policy refused the whole run -- "right at row 1 is null" -- and the same
comparison against a per-period ``v`` whose row was null answered an empty run
of periods, as if the policy had none. Selecting text branches on it nulled
the whole policy. Each now answers what Polars answers for each period on its
own: null, period by period, while the other policies answer as they did.
The text path already answered this way, and still does.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

_ENGINES = ("streaming", "in-memory")


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "x": [[1.0, 2.0], [3.0, 4.0], [5.0]],
            "v": [1.0, None, 5.0],
            "vs": [[1.0, 9.0], None, [5.0]],
            "sa": [[10.0, 20.0], [30.0, 40.0], [50.0]],
            "plan": [["A", "B"], ["A", "B"], ["A"]],
            "pv": ["A", None, "A"],
        },
        schema={
            "x": pl.List(pl.Float64),
            "v": pl.Float64,
            "vs": pl.List(pl.Float64),
            "sa": pl.List(pl.Float64),
            "plan": pl.List(pl.String),
            "pv": pl.String,
        },
    )


def _polars_own(
    book: pl.DataFrame, right: str, op: str
) -> list[list[float | None] | None]:
    """Polars' own answer, one policy at a time, period against period."""
    answers: list[list[float | None] | None] = []
    for row in book.iter_rows(named=True):
        periods = row["x"]
        value = row[right]
        if value is None and right == "vs":
            answers.append(None)
            continue
        values = value if isinstance(value, list) else [value] * len(periods)
        if value is None:
            values = [None] * len(periods)
        one = pl.DataFrame(
            {"l": periods, "r": values}, schema={"l": pl.Float64, "r": pl.Float64}
        )
        compared = (
            pl.col("l") == pl.col("r") if op == "eq" else pl.col("l") != pl.col("r")
        )
        answers.append(one.select(compared.cast(pl.Float64))["l"].to_list())
    return answers


def _compared(af: ActuarialFrame, right: str, op: str) -> object:
    return (af.x == af[right]) if op == "eq" else (af.x != af[right])


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize("op", ["eq", "ne"])
@pytest.mark.parametrize(
    "right", ["v", "vs"], ids=["a value per policy", "a list per policy"]
)
def test_a_null_right_side_answers_null_in_each_period(
    right: str, op: str, engine: str
) -> None:
    """The policy with the null answers null in each of its periods."""
    book = _book()
    af = ActuarialFrame(book)
    af.out = _compared(af, right, op)

    got = af.collect(engine=engine)["out"].to_list()

    assert got[1] == ([None, None] if right == "v" else None)
    assert got == _polars_own(book, right, op)


@pytest.mark.parametrize("engine", _ENGINES)
@pytest.mark.parametrize(
    "right", ["v", "vs"], ids=["a value per policy", "a list per policy"]
)
def test_a_null_condition_selects_neither_branch(right: str, engine: str) -> None:
    """``when`` over a null comparison is null in those periods, numbers or text."""
    af = ActuarialFrame(_book())
    af.benefit = when(af.x == af[right]).then(af.sa).otherwise(0.0)
    af.label = when(af.x == af[right]).then("hit").otherwise("miss")

    out = af.collect(engine=engine)

    missing = [None, None] if right == "v" else None
    assert out["benefit"].to_list() == [[10.0, 0.0], missing, [50.0]]
    assert out["label"].to_list() == [["hit", "miss"], missing, ["hit"]]


@pytest.mark.parametrize("engine", _ENGINES)
def test_numbers_and_text_put_their_nulls_in_the_same_periods(engine: str) -> None:
    """The text path always answered this way; the numeric path now agrees."""
    af = ActuarialFrame(_book())
    af.by_number = af.x == af.v
    af.by_text = af.plan == af.pv

    out = af.collect(engine=engine)

    assert out["by_number"].to_list() == [[1.0, 0.0], [None, None], [1.0]]
    assert out["by_text"].to_list() == [[1.0, 0.0], [None, None], [1.0]]
