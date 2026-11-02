# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A ``list_clip`` bound covers every row, or it is refused by name.

A bound reaches the kernel two ways -- as a ``List`` column carrying one
value per element, or as an ordinary column carrying one per row -- and
until this file the two disagreed about a bound whose height was not the
frame's. The per-row side broadcast a single row over all of them and read
a taller bound row by row until it ran out of values to bound; the
per-element side had no broadcast at all, so a single-row bound answered
the first row correctly and every row after it with an **empty list**,
silently. Two value rows against ``pl.lit([2.0, 2.0, 2.0])`` answered
``[[2.0, 5.0, 8.0], []]``.

The rule both sides keep now is the engine's own, read off Polars 1.42.1:
a bound of one row broadcasts over every row, and any other height is
refused, naming the bound, its height and the frame's. ``pl.Expr.clip``
against a one-row bound answers ``[2.0, 5.0]`` for ``[1.0, 5.0]``; against
a three-row bound on two rows it raises ``ShapeError: arguments for
`clip(min)` have different lengths (2 != 3)``. Empty lists for the rows a
bound does not reach is the one answer neither the engine nor this
framework gives -- *Sharp knives, no magic*: refuse rather than fill in.

These tests drive the kernel through
``gaspatchio.frame.lowering._polars.plugins.list_clip``, the eager door the
difference lives behind. The frame door cannot reach it:
an ``ActuarialFrame``'s columns are equal height by construction and a
missing bound is spelled as a one-row infinity, which broadcasts.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio.frame.lowering._polars.plugins import list_clip

# Two rows of values, and the answer a bound of 2.0 below and 8.0 above
# gives for them. Every case below clips these same numbers, so what
# changes between cases is only where the bound came from.
VALUES = [[0.0, 5.0, 10.0], [1.0, 2.0, 3.0]]
CLIPPED = [[2.0, 5.0, 8.0], [2.0, 2.0, 3.0]]


def _frame() -> pl.DataFrame:
    """The two value rows, with no bound columns of their own."""
    return pl.DataFrame({"v": VALUES}, schema={"v": pl.List(pl.Float64)})


def _one_row_list_bound(value: float) -> pl.Expr:
    """A per-element bound of a single row: ``pl.lit([v, v, v])``.

    This is the literal a reader following the ``list_clip`` docstring
    writes when the scalar bound in its worked example becomes a bound per
    element, and it is the shape the silent empty lists came from.
    """
    return pl.lit(pl.Series("b", [[value, value, value]]))


def _taller_list_bound(value: float, rows: int) -> pl.Expr:
    """A per-element bound of ``rows`` rows, against two rows of values."""
    return pl.lit(pl.Series("b", [[value, value, value]] * rows))


def _one_row_per_row_bound(value: float) -> pl.Expr:
    """A per-row bound of a single row, which has always broadcast."""
    return pl.lit(pl.Series("b", [value]))


def _taller_per_row_bound(value: float, rows: int) -> pl.Expr:
    """A per-row bound of ``rows`` rows, against two rows of values."""
    return pl.lit(pl.Series("b", [value] * rows))


class TestTheEnginesRuleIsTheKernelsRule:
    """What Polars' own ``clip`` does with a bound that is not the height."""

    def test_the_engine_broadcasts_a_one_row_bound(self) -> None:
        """A bound of one row covers every row, in the engine."""
        clipped = pl.DataFrame({"v": [1.0, 5.0]}).select(
            o=pl.col("v").clip(pl.lit(pl.Series("lo", [2.0])))
        )

        assert clipped["o"].to_list() == [2.0, 5.0]

    def test_the_engine_refuses_any_other_height_by_name(self) -> None:
        """A bound of three rows against two is a named refusal, not an answer."""
        with pytest.raises(pl.exceptions.ShapeError, match=r"different lengths \(2 != 3\)"):
            pl.DataFrame({"v": [1.0, 5.0]}).select(
                o=pl.col("v").clip(pl.lit(pl.Series("lo", [2.0, 2.0, 2.0])))
            )


class TestAOneRowBoundCoversEveryRow:
    """Broadcast, on both sides of the bound and from both sources."""

    def test_a_one_row_list_lower_bound_broadcasts(self) -> None:
        """The shape that used to answer an empty list for row 1."""
        clipped = _frame().with_columns(
            o=list_clip(pl.col("v"), _one_row_list_bound(2.0), pl.lit(8.0))
        )

        assert clipped["o"].to_list() == CLIPPED

    def test_a_one_row_list_upper_bound_broadcasts(self) -> None:
        """The same on the other side of the clip."""
        clipped = _frame().with_columns(
            o=list_clip(pl.col("v"), pl.lit(2.0), _one_row_list_bound(8.0))
        )

        assert clipped["o"].to_list() == CLIPPED

    def test_both_bounds_one_row_lists(self) -> None:
        """Both sides at once, which used to answer an empty list too."""
        clipped = _frame().with_columns(
            o=list_clip(
                pl.col("v"), _one_row_list_bound(2.0), _one_row_list_bound(8.0)
            )
        )

        assert clipped["o"].to_list() == CLIPPED

    def test_the_two_bound_sources_agree_on_the_one_row_case(self) -> None:
        """A per-element bound and a per-row bound answer the same thing.

        This is the asymmetry the fix closes: one row of a ``List`` bound
        and one row of a plain bound are the same statement about every
        row, and were answered two different ways.
        """
        per_element = _frame().with_columns(
            o=list_clip(pl.col("v"), _one_row_list_bound(2.0), pl.lit(8.0))
        )["o"]
        per_row = _frame().with_columns(
            o=list_clip(pl.col("v"), _one_row_per_row_bound(2.0), pl.lit(8.0))
        )["o"]

        assert per_element.to_list() == per_row.to_list() == CLIPPED

    def test_the_streaming_engine_already_answered_this(self) -> None:
        """Streaming broadcasts before the kernel is called; now so does eager.

        ``ActuarialFrame.collect()`` defaults to the streaming engine, which
        is why no model saw the empty lists -- and why the eager door
        disagreeing with it was a difference between two ways of running one
        formula.
        """
        streaming = (
            _frame()
            .lazy()
            .with_columns(o=list_clip(pl.col("v"), _one_row_list_bound(2.0), pl.lit(8.0)))
            .collect(engine="streaming")
        )
        eager = _frame().with_columns(
            o=list_clip(pl.col("v"), _one_row_list_bound(2.0), pl.lit(8.0))
        )

        assert streaming["o"].to_list() == eager["o"].to_list() == CLIPPED


class TestAnyOtherHeightIsRefusedByName:
    """Never an empty list, never a truncated read -- a message."""

    def test_a_taller_list_bound_is_refused(self) -> None:
        """Three rows of bound against two rows of values names both figures."""
        with pytest.raises(
            pl.exceptions.ComputeError,
            match=r"lower bound for list_clip has 3 rows, but the values have 2",
        ):
            _frame().with_columns(
                o=list_clip(pl.col("v"), _taller_list_bound(2.0, 3), pl.lit(8.0))
            )

    def test_a_taller_per_row_bound_is_refused(self) -> None:
        """The per-row side used to read the first two rows and drop the third."""
        with pytest.raises(
            pl.exceptions.ComputeError,
            match=r"lower bound for list_clip has 3 rows, but the values have 2",
        ):
            _frame().with_columns(
                o=list_clip(pl.col("v"), _taller_per_row_bound(2.0, 3), pl.lit(8.0))
            )

    def test_the_upper_bound_is_named_as_the_upper_bound(self) -> None:
        """The refusal says which of the two bounds is the wrong height."""
        with pytest.raises(
            pl.exceptions.ComputeError,
            match=r"upper bound for list_clip has 3 rows, but the values have 2",
        ):
            _frame().with_columns(
                o=list_clip(pl.col("v"), pl.lit(2.0), _taller_per_row_bound(8.0, 3))
            )

    def test_the_two_bound_sources_agree_on_the_mismatch(self) -> None:
        """Both sources refuse a three-row bound with the same words."""
        messages = []
        for bound in (_taller_list_bound(2.0, 3), _taller_per_row_bound(2.0, 3)):
            with pytest.raises(pl.exceptions.ComputeError) as caught:
                _frame().with_columns(o=list_clip(pl.col("v"), bound, pl.lit(8.0)))
            messages.append(str(caught.value).splitlines()[0])

        assert messages[0] == messages[1]
        assert "has 3 rows, but the values have 2" in messages[0]

    def test_a_shorter_bound_that_is_not_one_row_is_refused(self) -> None:
        """Two rows of bound against three rows of values, the other direction."""
        frame = pl.DataFrame(
            {"v": [*VALUES, [0.0, 0.0, 0.0]]}, schema={"v": pl.List(pl.Float64)}
        )

        with pytest.raises(
            pl.exceptions.ComputeError,
            match=r"lower bound for list_clip has 2 rows, but the values have 3",
        ):
            frame.with_columns(
                o=list_clip(pl.col("v"), _taller_list_bound(2.0, 2), pl.lit(8.0))
            )


class TestWhatTheHeightRuleDoesNotDisturb:
    """The shapes that were right already, held in place."""

    def test_a_bound_of_matching_height_is_read_row_by_row(self) -> None:
        """The ordinary case: one bound row per value row."""
        frame = pl.DataFrame(
            {"v": VALUES, "lo": [[2.0, 2.0, 2.0], [2.0, 2.0, 2.0]]},
            schema={"v": pl.List(pl.Float64), "lo": pl.List(pl.Float64)},
        )
        clipped = frame.with_columns(
            o=list_clip(pl.col("v"), pl.col("lo"), pl.lit(8.0))
        )

        assert clipped["o"].to_list() == CLIPPED

    def test_a_null_bound_row_still_answers_an_empty_list(self) -> None:
        """An empty list is what a bound that is *null* means, and only that."""
        frame = pl.DataFrame(
            {"v": VALUES, "lo": [[2.0, 2.0, 2.0], None]},
            schema={"v": pl.List(pl.Float64), "lo": pl.List(pl.Float64)},
        )
        clipped = frame.with_columns(
            o=list_clip(pl.col("v"), pl.col("lo"), pl.lit(8.0))
        )

        assert clipped["o"].to_list() == [[2.0, 5.0, 8.0], []]

    def test_a_zero_row_frame_takes_a_one_row_bound(self) -> None:
        """Nothing to bound is not a height mismatch; the engine agrees."""
        empty = pl.DataFrame({"v": []}, schema={"v": pl.List(pl.Float64)})
        clipped = empty.with_columns(
            o=list_clip(pl.col("v"), _one_row_list_bound(2.0), pl.lit(8.0))
        )

        assert clipped["o"].to_list() == []

    def test_the_inner_length_rule_is_unchanged(self) -> None:
        """Elements per row is a different question from rows per column."""
        frame = pl.DataFrame(
            {"v": VALUES, "lo": [[2.0], [2.0]]},
            schema={"v": pl.List(pl.Float64), "lo": pl.List(pl.Float64)},
        )

        with pytest.raises(
            pl.exceptions.ComputeError,
            match=(
                r"mismatched inner list lengths in one policy: "
                r"lower bound against values"
            ),
        ):
            frame.with_columns(o=list_clip(pl.col("v"), pl.col("lo"), pl.lit(8.0)))

    def test_a_null_per_row_bound_is_still_refused_by_name(self) -> None:
        """A per-row bound has no elements to carry an absence, so it refuses."""
        frame = pl.DataFrame({"v": VALUES, "lo": [2.0, None]})

        with pytest.raises(
            pl.exceptions.ComputeError,
            match=r"the lower bound of a clip is null for one policy",
        ):
            frame.with_columns(o=list_clip(pl.col("v"), pl.col("lo"), pl.lit(8.0)))


class TestAnUnpromotableInnerDtypeIsNamed:
    """A ``List(Struct)`` refusal is a message, and was once an abort.

    Before the row loop was written once, the element cast was
    ``row.f64().unwrap()``, so a dtype that cannot be promoted to Float64
    aborted the plugin and Polars reported only "the plugin panicked" with
    the dtype text suppressed. It now arrives as a named ``ComputeError``
    carrying that text. This test exists so the abort cannot come back:
    the refusal is the contract, not the panic.
    """

    def test_a_struct_inner_dtype_raises_rather_than_panics(self) -> None:
        """The dtype is named in the message, and the word "panicked" is not."""
        frame = pl.DataFrame({"v": [[{"a": 1}], [{"a": 2}]]})

        with pytest.raises(pl.exceptions.ComputeError) as caught:
            frame.with_columns(o=list_clip(pl.col("v"), pl.lit(0.0), pl.lit(5.0)))

        message = str(caught.value)
        assert "invalid series dtype" in message
        assert "struct[1]" in message
        assert "panicked" not in message
