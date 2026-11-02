# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The attribution block's ``Defined as`` line quotes the model's own text.

A recorded calculation carries two renderings of itself: the expression the
author typed (``record.source.rhs``) and the engine's lowering of it
(``record.expr``). The terse block used to print the second under a label
that reads as the first, so a reader was shown
``[(col("product_code")) * (col("sum_assured"))]`` for a line they wrote as
``af.product_code * af.sum_assured``.

These tests pin both halves of the contract: the line quotes the author's
text wherever capture resolved one, and where it did not, the lowered form
still prints but the label says which of the two it is.

The bare label is reserved for a statement that is the failing column's own
definition. Where the statement mints the column without being its formula
-- a ``with_columns`` batch, a tuple assignment, the projection timeline --
the block prints the lowered form under the caveated label, which is the
rule ``graph_builder._as_written`` already applies to the exported
``formula`` and the rule this line now reads from.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio._semantic.ir import Col
from gaspatchio.errors.formatting_errors import _attribution_block, _defined_as_line
from gaspatchio.frame.calculations import CalculationRecord

# The label the block falls back to, written out here rather than imported:
# these tests are the record of what a user reads, and a label that drifted
# into dishonesty would still equal an imported constant.
LOWERED_LABEL = "Defined as (lowered; as-written formula not recorded):"


def _frame() -> ActuarialFrame:
    """A frame whose string and float columns cannot be multiplied together.

    The frame's own arithmetic between them is refused where it is written,
    so each failure below is the same product written as an engine fragment
    -- ``pl.col("product_code") * pl.col("sum_assured")`` -- which Polars
    alone runs, and refuses when the frame is collected.
    """
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "product_code": ["TERM", "WL"],
                "sum_assured": [100.0, 200.0],
            }
        )
    )


def _defined_as(message: str) -> str:
    """Return the block's one ``Defined as`` line, whichever label it carries."""
    lines = [line for line in message.splitlines() if "Defined as" in line]
    assert len(lines) == 1, f"expected exactly one Defined-as line in:\n{message}"
    return lines[0].removeprefix("  ")


def _batch_expression(index: int) -> pl.Expr:
    """Return one expression of a batch, the middle one of which cannot resolve."""
    if index == 1:
        return (pl.col("product_code") * pl.col("sum_assured")).alias("reserve_factor")
    return (pl.col("sum_assured") + float(index)).alias(f"filler_{index}")


def _failure_message(af: ActuarialFrame) -> str:
    """Collect ``af``, expecting the dtype refusal, and return its message."""
    with pytest.raises(Exception, match="reserve_factor") as excinfo:
        af.collect()
    return str(excinfo.value)


def test_the_block_quotes_a_plain_assignment_as_the_author_wrote_it() -> None:
    """The line as written, not the engine's `[(col("a")) * (col("b"))]`."""
    af = _frame()
    af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")

    line = _defined_as(_failure_message(af))

    assert line == 'Defined as:     pl.col("product_code") * pl.col("sum_assured")'


def test_the_block_quotes_a_setattr_built_column_as_the_author_wrote_it() -> None:
    """The builtin a run-time column name is written through quotes the same."""
    af = _frame()
    name = "reserve_factor"
    setattr(af, name, pl.col("product_code") * pl.col("sum_assured"))

    line = _defined_as(_failure_message(af))

    assert line == 'Defined as:     pl.col("product_code") * pl.col("sum_assured")'


def test_a_multi_line_formula_keeps_the_block_s_column() -> None:
    """A wrapped conditional chain is quoted whole, padded to the label column."""
    af = _frame()
    af.reserve_factor = (
        when(af.policy_id == 1)
        .then(pl.col("product_code") * pl.col("sum_assured"))
        .otherwise(af.sum_assured)
    )

    lines = _failure_message(af).splitlines()
    start = next(i for i, line in enumerate(lines) if "Defined as" in line)

    assert lines[start] == "  Defined as:     when(af.policy_id == 1)"
    assert (
        lines[start + 1]
        == " " * 18 + '        .then(pl.col("product_code") * pl.col("sum_assured"))'
    )
    assert lines[start + 2] == " " * 18 + "        .otherwise(af.sum_assured)"


def test_an_augmented_assignment_is_labelled_as_the_lowered_form() -> None:
    """No written right-hand side exists, so the label says what is printed."""
    af = _frame()
    af.reserve_factor = af.sum_assured
    af.reserve_factor *= pl.col("product_code") * pl.col("sum_assured")

    line = _defined_as(_failure_message(af))

    assert line.startswith(LOWERED_LABEL)
    assert 'col("sum_assured")' in line


def test_a_statement_with_no_retrievable_source_is_labelled_too() -> None:
    """A ``compile('<string>')`` snippet resolves no span at all, and says so."""
    af = _frame()
    exec(  # noqa: S102 — a no-file context is the condition under test
        compile(
            'af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")',
            "<string>",
            "exec",
        ),
        {"af": af, "pl": pl},
    )

    line = _defined_as(_failure_message(af))

    assert line.startswith(LOWERED_LABEL)
    assert 'col("product_code")' in line


def test_the_bare_label_never_carries_a_lowered_expression() -> None:
    """The honesty invariant, stated once over both fallback routes."""
    augmented = _frame()
    augmented.reserve_factor = augmented.sum_assured
    augmented.reserve_factor *= pl.col("product_code") * pl.col("sum_assured")

    unsourced = _frame()
    exec(  # noqa: S102 — a no-file context is the condition under test
        compile(
            'af.reserve_factor = pl.col("product_code") * pl.col("sum_assured")',
            "<string>",
            "exec",
        ),
        {"af": unsourced, "pl": pl},
    )

    for af in (augmented, unsourced):
        assert not _defined_as(_failure_message(af)).startswith("Defined as:")


# --- the shapes whose statement is not the column's own definition ----------
#
# A statement can mint a column without being that column's formula: a
# ``with_columns`` batch, a tuple assignment, the projection timeline. Its
# right-hand side is then the whole call or the whole tuple, and quoting it
# under the bare label shows a reader text that does not compute the number
# beside it. The graph refuses to publish that text as a node's ``formula``;
# these pin that the block refuses to print it as one.


def test_a_batch_call_is_labelled_as_the_lowered_form() -> None:
    """One call, three columns: its text is not the failing column's formula."""
    af = _frame()

    with pytest.raises(Exception, match="reserve_factor") as excinfo:
        af = af.with_columns(
            (pl.col("sum_assured") * 2.0).alias("doubled"),
            (pl.col("product_code") * pl.col("sum_assured")).alias("reserve_factor"),
            (pl.col("sum_assured") + 1.0).alias("bumped"),
        )

    line = _defined_as(str(excinfo.value))

    assert line.startswith(LOWERED_LABEL)
    assert "with_columns" not in line


def test_a_batch_built_by_a_comprehension_is_labelled_too() -> None:
    """The sharpest form: the statement's text never names the column at all."""
    af = _frame()

    with pytest.raises(Exception, match="reserve_factor") as excinfo:
        af = af.with_columns(*[_batch_expression(i) for i in range(3)])

    line = _defined_as(str(excinfo.value))

    assert line.startswith(LOWERED_LABEL)
    assert "for i in range" not in line


def test_a_tuple_assignment_is_labelled_as_the_lowered_form() -> None:
    """Both columns of a tuple write share one right-hand side that is neither."""
    af = _frame()
    af.doubled, af.reserve_factor = (
        af.sum_assured * 2.0,
        pl.col("product_code") * pl.col("sum_assured"),
    )

    line = _defined_as(_failure_message(af))

    assert line.startswith(LOWERED_LABEL)
    assert "af.sum_assured * 2.0," not in line


def test_a_projection_stamped_column_is_labelled_as_the_lowered_form() -> None:
    """The timeline stamps ``month`` from a configuration, not from a formula.

    Rendered from the record rather than from a collect failure: replay
    attributes a failure to the calculation that reproduces it, and no
    statement of a model's ever recomputes a stamped column. The record is
    the live one the timeline wrote, and it is what the block would be
    handed if a failure ever were attributed to it.
    """
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "issue_age": [40, 45]}))
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="maximum_age",
        until_value=60,
        frequency="annual",
    )
    month = next(
        record
        for record in af._calculations  # noqa: SLF001 -- the record under test
        if record.column == "month"
    )

    line = _defined_as(_attribution_block(month))

    assert month.origin == "projection"
    assert line.startswith(LOWERED_LABEL)
    assert "projection.set" not in line


def test_a_batch_call_written_into_a_subscript_is_labelled_by_its_door() -> None:
    """The door refuses what the statement's shape alone would let through.

    ``store["frame"] = af.with_columns(...)`` is a statement whose target
    names one thing literally, so capture records its right-hand side --
    and that right-hand side is still the whole call rather than the
    failing column's expression. What earns the caveated label here is the
    record's door, which is the test the exported ``formula`` applies and
    the one this line reads from.
    """
    af = _frame()
    store: dict[str, ActuarialFrame] = {}

    with pytest.raises(Exception, match="reserve_factor") as excinfo:
        store["frame"] = af.with_columns(
            (pl.col("product_code") * pl.col("sum_assured")).alias("reserve_factor"),
            (pl.col("sum_assured") + 1.0).alias("bumped"),
        )

    line = _defined_as(str(excinfo.value))

    assert line.startswith(LOWERED_LABEL)
    assert "with_columns" not in line


def test_a_loop_built_column_still_quotes_the_line_it_was_written_in() -> None:
    """The boundary of the rule: a computed target is still one column's own write.

    ``af[name] = ...`` names its column through a variable, so the name is
    not in the statement's text -- but the right-hand side beside it is
    exactly what computed that column, as it is for the ``setattr`` form,
    and the block quotes it.
    """
    af = _frame()
    for name in ["reserve_factor"]:
        af[name] = pl.col("product_code") * pl.col("sum_assured")

    line = _defined_as(_failure_message(af))

    assert line == 'Defined as:     pl.col("product_code") * pl.col("sum_assured")'


def test_a_lowered_expression_wrapping_a_newline_keeps_the_block_s_column() -> None:
    """Both branches pad, so neither breaks out to the left margin.

    The as-written branch has wrapped formulas to pad from the start; the
    lowered branch reached the left margin for any lowering carrying a
    newline, which a string literal written over two lines produces.
    Rendered from a record, since what is under test is the padding rather
    than the route that built the record.
    """
    record = CalculationRecord(
        column="reserve_factor",
        ordinal=1,
        operation_id=1,
        node=Col("reserve_factor"),
        expr=pl.lit("one\ntwo"),
        dtype=None,
        source=None,
        origin="batch",
    )

    lines = _defined_as_line(record).splitlines()

    assert lines[0].startswith(LOWERED_LABEL)
    assert lines[1].startswith(" " * len("  Failing column: "))
