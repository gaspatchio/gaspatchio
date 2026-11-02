# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every move a table-read refusal names works where the line was written.

Two refusals named a move that the next refusal then refused. A read keyed by
literals, ``af.q2 = mort.lookup(age=40).fill_nan(0.0)``, was told to "continue
with a declared operation ... a NaN fill is fill_nan(0.0)" -- the line it had
written, because on a read bound to no frame column the method is Polars' own.
And ``mort.lookup(age=af.age).sum()`` was told to write
``.polars_native().sum``, which the frame then refused for hiding the read in
a Polars expression. Each refusal now names the move that works there, and
each test below runs that move.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

_REFUSED = "inside a Polars expression the framework cannot see into"


def _table(name: str = "moves_that_work") -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": [40, 41, 42], "qx": [0.001, float("nan"), 0.003]}),
        dimensions={"age": "age"},
        value="qx",
        on_missing="nan",
    )


def _frame() -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame({"age": [40, 41, 42]}))


@pytest.mark.parametrize(
    "written",
    [
        lambda: _table().lookup(age=40).fill_nan(0.0),
        # A table of its own: keyed by pl.col, the read lowers to the plan a
        # read keyed by af.age lowers to, and that one is answered as bound.
        lambda: _table("moves_raw_key").lookup(age=pl.col("age")).fill_nan(0.0),
    ],
    ids=["literal-key", "raw-polars-key"],
)
def test_a_read_bound_to_no_frame_column_is_told_to_store_it_first(
    written: object,
) -> None:
    af = _frame()
    with pytest.raises(ValueError, match=_REFUSED) as refused:
        af.q2 = written()  # type: ignore[operator]

    message = str(refused.value)
    # The move it named was the line written, and it is not named again.
    assert "Either continue with a declared operation" not in message
    assert "a NaN fill is fill_nan(0.0)" not in message
    assert "Store the read as its own column first, af.q2_read = <the read>" in message
    assert "af.q2 = af.q2_read.fill_nan(0.0)" in message
    assert "af.q2 = af.q2_read.polars_native().<method>(...)" in message


def test_the_store_first_move_runs_and_keeps_both_lines_core() -> None:
    af = _frame()
    af.q2_read = _table().lookup(age=40)
    af.q2 = af.q2_read.fill_nan(0.0)

    assert af.collect()["q2"].to_list() == [0.001, 0.001, 0.001]
    assert af.graph.tiers().engine_native == ()


def test_a_read_bound_to_the_frame_keeps_both_moves() -> None:
    """Keyed by a frame column, a declared operation on the read is a move."""
    af = _frame()
    with pytest.raises(ValueError, match=_REFUSED) as refused:
        af.q = _table().lookup(age=af.age).polars_native().arctan()

    message = str(refused.value)
    assert "Either continue with a declared operation" in message
    assert "a NaN fill is fill_nan(0.0)" in message

    af.q = _table().lookup(age=af.age).fill_nan(0.0)
    assert af.collect()["q"].to_list() == [0.001, 0.0, 0.003]


def test_a_row_reading_name_on_a_read_names_store_first_and_not_the_escape() -> None:
    af = _frame()
    with pytest.raises(AttributeError) as refused:
        af.q = _table().lookup(age=af.age).sum()

    message = str(refused.value)
    assert "For a Polars method or namespace, write .polars_native().sum." not in (
        message
    )
    assert "assumption table 'moves_that_work'" in message
    assert "Store the read as its own column first" in message
    assert "af.<column>_read.polars_native().sum on that column" in message


def test_the_move_the_row_reading_refusal_names_runs() -> None:
    af = _frame()
    af.q_read = _table().lookup(age=af.age).fill_nan(0.0)
    af.q_total = af.q_read.polars_native().sum()

    assert af.collect()["q_total"].to_list() == pytest.approx([0.004] * 3)


def test_the_escape_on_the_read_itself_is_what_the_frame_refuses() -> None:
    """The move the refusal used to name, so it is shown never to work."""
    af = _frame()
    with pytest.raises(ValueError, match=_REFUSED):
        af.q = _table().lookup(age=af.age).polars_native().sum()


def test_a_row_reading_name_on_a_per_period_read_keeps_its_period_form() -> None:
    af = ActuarialFrame(pl.DataFrame({"age": [40, 41]})).projection.set(
        start_date=dt.date(2025, 1, 31), n_periods=1, frequency="annual"
    )
    af.attained = af.age + af.month // 12
    with pytest.raises(AttributeError) as refused:
        af.q = _table().lookup(age=af.attained).sum()

    message = str(refused.value)
    assert "Store the read as its own column first" in message
    assert "write .list.sum()" in message


def test_a_row_reading_name_on_an_ordinary_column_is_unchanged() -> None:
    af = ActuarialFrame(pl.DataFrame({"x": [1.0, 2.0]}))
    with pytest.raises(AttributeError) as refused:
        af.y = af.x.sum()

    assert str(refused.value).startswith(
        "No 'sum' column accessor registered or declared operation found. "
        "For a Polars method or namespace, write .polars_native().sum."
    )
