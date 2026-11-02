# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The missing-column panel lists the columns the failing calculation could read.

A calculation that names a column which is not there fails at ``collect()``,
and the panel that explains it has a section headed "Calculation State Before
Error", "(Available columns at the point of failure)". The list under it was
the frame's columns at the time the error was formatted, which already
included the column whose definition had just failed: ``commission`` was
listed as available to the line that tried to define it. A reader who sees it
there can take a typo for an ordering problem and look in the wrong place.

The list is now the frame as it stood before the failing definition: the
columns the frame opened with, and each column an earlier calculation
defined. One defined later is not listed either, and the did-you-mean
suggestion is drawn from the same list.

The Location and the list come from one decision. Where the failing
definition cannot be established -- the plan already fails in a step run
before the calculations recorded since the frame was last reshaped -- the
panel claims no line, says why, and lists the frame's columns as they stand
under a heading that says they may include columns defined later.
"""

from __future__ import annotations

import inspect

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.errors import formatting_errors
from gaspatchio.util import set_error_mode


def _frame() -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame({"premium": [100.0, 200.0]}))


def _message(af: ActuarialFrame) -> str:
    """Collect ``af``, which must fail on a missing column, and return the panel."""
    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        af.collect()
    return str(caught.value)


def _listed(message: str) -> list[str]:
    """Return the columns the panel lists under its calculation-state heading."""
    state = message.split("Calculation State Before Error:", 1)[1]
    state = state.split("Did you mean", 1)[0]
    return [
        line.strip().strip("│").strip()
        for line in state.splitlines()
        if line.strip().startswith("│")
    ]


def test_the_failing_column_is_not_listed_as_available() -> None:
    """A typo in a new column's definition: ``commission`` was never there to read."""
    af = _frame()
    af["commission"] = pl.col("premum") * 0.1  # the typo

    message = _message(af)

    assert _listed(message) == ["premium"]
    assert "shape: (unknown, 1)" in message
    # The suggestion still names the near miss.
    assert "• premium" in message.split("Did you mean one of these?", 1)[1]


def test_a_column_defined_after_the_failing_one_is_not_listed() -> None:
    """A later definition was not there to read either."""
    af = _frame()
    af["commission"] = pl.col("premum") * 0.1
    af["tax"] = af["premium"] * 0.2

    assert _listed(_message(af)) == ["premium"]


def test_a_column_defined_before_the_failing_one_is_listed() -> None:
    """An earlier definition is part of what the failing line could read."""
    af = _frame()
    af["tax"] = af["premium"] * 0.2
    af["commission"] = pl.col("premum") * 0.1

    assert _listed(_message(af)) == ["premium", "tax"]


def test_a_redefinition_lists_the_column_it_replaces() -> None:
    """Redefining ``premium`` could have read the ``premium`` that was there."""
    af = _frame()
    af["premium"] = pl.col("premum") * 2.0

    assert _listed(_message(af)) == ["premium"]


def test_the_list_does_not_depend_on_source_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no source spans recorded, the failing definition is still found."""
    monkeypatch.setenv("GASPATCHIO_SOURCE_SPANS", "off")
    af = _frame()
    af["commission"] = pl.col("premum") * 0.1

    assert _listed(_message(af)) == ["premium"]


def test_the_plain_message_lists_the_same_columns() -> None:
    """The basic mode's plain list is drawn from the same state."""
    set_error_mode("basic")
    af = _frame()
    af["commission"] = pl.col("premum") * 0.1

    message = formatting_errors._format_column_message(  # noqa: SLF001
        af, "premum", 'unable to find column "premum"'
    )

    available = message.split("Available columns are:", 1)[1]
    available = available.split("Original Polars Error", 1)[0]
    assert [line.strip(" -") for line in available.strip().splitlines()] == ["premium"]


def test_a_failure_before_the_recorded_calculations_claims_no_line() -> None:
    """The filter fails first; the calculation after it is not named as the failure.

    The filter names the missing column on one line and the calculation
    after it names it again on the next. Polars stops at the filter, which
    reshaped the frame and so is not one of the recorded calculations the
    panel can point at. The panel must not name the next line as the
    failure, and must not say a calculation "was not found" as though that
    were a second error.
    """
    af = _frame()
    af = af.filter(pl.col("premum") > 0)
    af["c"] = pl.col("premum") * 0.1
    the_calculation_after_it = inspect.currentframe().f_lineno - 1

    message = _message(af)

    location = message.split("Location:", 1)[1].splitlines()[0]
    assert f":{the_calculation_after_it}" not in location
    assert "not established" in location
    assert "before the calculation" in message
    assert "Operation: c =" not in message
    assert "was not found" not in message
    assert "may include columns defined after the failing step" in " ".join(
        message.split()
    )


def test_the_plain_message_says_when_its_list_is_the_frame_as_it_stands() -> None:
    """Basic mode's plain list carries the same caveat where nothing is established."""
    set_error_mode("basic")
    af = _frame()
    af = af.filter(pl.col("premum") > 0)
    af["c"] = pl.col("premum") * 0.1

    message = formatting_errors._format_column_message(  # noqa: SLF001
        af, "premum", 'unable to find column "premum"'
    )

    assert "Available columns are:" not in message
    assert "may include columns defined after the failing step" in message


def test_the_fallback_heading_fits_the_panels_width() -> None:
    """The heading over the column list wraps inside the panel's 80-column rules."""
    af = _frame()
    af = af.filter(pl.col("premum") > 0)
    af["c"] = pl.col("premum") * 0.1

    message = _message(af)
    section = message.split("Calculation State Before Error:", 1)[1]
    heading = section.split("shape:", 1)[0].strip("\n").splitlines()

    assert len(heading) > 1, "the caveat is long enough to need a second line"
    assert [line for line in heading if len(line) > len("─" * 80)] == []


def test_the_operation_line_shows_a_division_as_the_division_written() -> None:
    """``/`` is written as ``/``, not as the kernel that divides, nor its path.

    The line printed the engine's raw text: the quotient kernel's name and
    the machine path of the library it lives in, where the record and the
    walk-through write the operator.
    """
    af = ActuarialFrame(pl.DataFrame({"a": [1.0], "b": [2.0]}))
    af.ratio = af.a / af.b + pl.col("nope")

    message = _message(af)
    (operation,) = [line for line in message.splitlines() if "Operation:" in line]

    assert operation.strip() == (
        'Operation: ratio = [([(col("a")) / (col("b"))]) + (col("nope"))]'
    )
    assert "ieee_div" not in message.split("🔴 Error Details:", 1)[0]


def test_the_operation_line_shows_a_per_period_when_as_the_when_written() -> None:
    """A ``when`` over a timeline is the ``when``, with its comparison.

    The line printed ``list_conditional`` -- the kernel's name, without the
    comparison it evaluates, which travels in its keyword arguments -- where
    the model wrote ``when(af.x > 1)``.
    """
    af = ActuarialFrame(pl.DataFrame({"x": [[1.0, 2.0]], "y": [[3.0, 4.0]]}))
    af.z = when(af.x > 1).then(af.y).otherwise(0.0) + pl.col("nope")

    message = _message(af)
    (operation,) = [line for line in message.splitlines() if "Operation:" in line]

    assert operation.strip() == (
        'Operation: z = [(.when([(col("x")) > (1)]).then(col("y"))'
        '.otherwise(dyn float: 0)) + (col("nope"))]'
    )
    assert "list_conditional" not in message.split("🔴 Error Details:", 1)[0]
