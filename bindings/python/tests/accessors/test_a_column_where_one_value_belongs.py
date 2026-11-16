# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A period shift's fill, and a period override, are one value: a column is refused.

``previous_period(fill_value=af.initial)`` used to build without a word and
fail at collect with Polars' "named columns are not allowed in `eval`
functions", which names neither the shift nor the fill. ``with_period(0,
af.initial)`` failed with "Nested object types". Both are now refused at the
line that wrote them, naming the conditional that does what was meant -- and
that conditional is pinned here to give the answer the author wanted.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable


def _frame() -> ActuarialFrame:
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "initial": [1000.0, 500.0],
                "lapse": [[5.0, 8.0, 10.0], [1.0, 2.0, 3.0]],
            }
        )
    )
    return frame.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=2, frequency="monthly"
    )


@pytest.mark.parametrize(
    ("written", "named"),
    [
        (
            lambda af: af.lapse.projection.previous_period(fill_value=af.initial),
            "previous_period",
        ),
        (
            lambda af: af.lapse.projection.previous_period(
                fill_value=pl.col("initial")
            ),
            "previous_period",
        ),
        (
            lambda af: af.lapse.projection.next_period(fill_value=af.initial),
            "next_period",
        ),
        (
            lambda af: af.lapse.projection.at_period(-2, fill_value=af.initial),
            "at_period",
        ),
    ],
    ids=["previous column", "previous pl.col", "next column", "at_period column"],
)
def test_a_shift_refuses_a_column_fill_at_the_line(
    written: Callable[[ActuarialFrame], object], named: str
) -> None:
    """The refusal comes at the call, names it, and names the conditional."""
    af = _frame()
    with pytest.raises(TypeError) as refused:
        written(af)
    message = str(refused.value)
    assert f"{named}(fill_value=...)" in message
    assert "when(af.month == 0)" in message


def test_a_period_override_refuses_a_column_at_the_line() -> None:
    """``with_period(0, af.initial)`` is refused by name, not by Polars."""
    af = _frame()
    with pytest.raises(TypeError, match=r"with_period\(value=\.\.\.\)") as refused:
        af.lapse.projection.with_period(0, af.initial)
    assert "when(af.month == 0)" in str(refused.value)


def test_with_periods_refuses_a_column_entry() -> None:
    af = _frame()
    with pytest.raises(TypeError, match=r"updates\[0\]"):
        af.lapse.projection.with_periods({0: af.initial})


def test_one_value_fills_still_work() -> None:
    """A number and None are fills; nothing about them changes."""
    af = _frame()
    af.zero = af.lapse.projection.previous_period(fill_value=0.0)
    af.blank = af.lapse.projection.previous_period(fill_value=None)
    out = af.collect()
    assert out["zero"].to_list() == [[0.0, 5.0, 8.0], [0.0, 1.0, 2.0]]
    assert out["blank"].to_list() == [[None, 5.0, 8.0], [None, 1.0, 2.0]]


def test_the_named_conditional_opens_each_run_with_its_own_value() -> None:
    """What the message points to gives what the column fill meant."""
    af = _frame()
    af.prev = (
        when(af.month == 0)
        .then(af.initial)
        .otherwise(af.lapse.projection.previous_period())
    )
    assert af.collect()["prev"].to_list() == [
        [1000.0, 5.0, 8.0],
        [500.0, 1.0, 2.0],
    ]
    assert "prev@1" in af.graph.tiers().core
