# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A refusal the plan raises names the line that raised it, whatever ran the plan.

A lazy plan refuses a row by failing a string's cast to ``Int64`` with the
framework's sentence as the value, and the error door lifts the sentence to
the top. The attribution beneath it -- ``Failing column``, ``Defined as``,
``At`` -- was found by replaying the plan over the book's head and comparing
first lines. In memory the two first lines were one; the streaming engine
numbers the failed values within its morsel (``1 out of 3 values``) where the
replay numbers them within the head (``1 out of 12``), so no line matched and
the block was dropped; and a refused row past the replay's head, in a book
of more than ten thousand policies, reproduced nothing at all. The refusal's
own sentence is the same in every batch and is written into exactly the one
calculation that checks it, so it is what names the line.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame


def _book(policies: int) -> pl.DataFrame:
    last = policies - 1
    return pl.DataFrame(
        {
            "pid": list(range(1, policies + 1)),
            "term_m": [6] * policies,
            "units": [2**60 if row == last else 100 for row in range(policies)],
        }
    )


def _model(book: pl.DataFrame) -> ActuarialFrame:
    af = ActuarialFrame(book).projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_months",
        until_value="term_m",
        frequency="monthly",
    )
    af.units_t = af.units * (af.month + 1)
    af.total_units = af.units_t.list.sum()
    return af


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
@pytest.mark.parametrize("policies", [12, 10_001])
def test_the_sum_past_i64_names_its_line(engine: str, policies: int) -> None:
    af = _model(_book(policies))

    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        af.collect(engine=engine)

    said = str(refused.value)
    assert said.startswith("Column 'units_t' holds whole numbers whose sum")
    assert "Failing column: 'total_units'" in said
    assert "Defined as:     af.units_t.list.sum()" in said
    assert "test_a_plan_refusal_names_its_line_on_every_engine.py" in said


def test_two_lines_carrying_one_refusal_name_neither() -> None:
    """The sentence names a line only where one calculation alone carries it."""
    af = _model(_book(10_001))
    af.total_again = af.units_t.list.sum()

    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        af.collect(engine="streaming")

    assert "Failing column: 'total_units'" not in str(refused.value)
    assert "Failing column: 'total_again'" not in str(refused.value)
