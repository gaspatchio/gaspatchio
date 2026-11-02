# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An error's own text is plain, whatever it is read on.

The message a panel writes is the exception's text, and where that text is read
is not known when it is written: a terminal, a log file, CI output, a notebook
cell, a subprocess another tool parses. A terminal's colour codes written into
it arrive at every other one of those as escape sequences. So no panel writes
one -- not the missing-column panel the default error mode builds at
``collect()``, which forced a terminal console on every run, and not the others,
which wrote colour whenever standard output was a terminal, whatever the
message was then read on.
"""

from __future__ import annotations

import io
import sys
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._semantic.ir import Col
from gaspatchio.errors.formatter import (
    AttributeErrorFormatter,
    FriendlyErrorFormatter,
    ValidationErrorFormatter,
)
from gaspatchio.errors.models import SourceLocation
from gaspatchio.errors.validation import ValidationError
from gaspatchio.frame.calculations import CalculationRecord, SourceSpan

if TYPE_CHECKING:
    from collections.abc import Callable

# Where every terminal control sequence begins.
_ESCAPE = "\x1b["


class _Terminal(io.StringIO):
    """A standard output that says it is a terminal."""

    def isatty(self) -> bool:
        return True


# Each panel is read twice: with standard output piped, and with it a terminal.
_OUTPUTS = pytest.mark.parametrize("output", ["piped", "terminal"])


def _standard_output(output: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make standard output a terminal, from inside the test that reads it.

    Inside the test rather than in a fixture: pytest puts its own capturing
    stream back on ``sys.stdout`` between a fixture's setup and the call.
    """
    if output == "terminal":
        monkeypatch.setattr(sys, "stdout", _Terminal())


def _missing_column_message(monkeypatch: pytest.MonkeyPatch, *, traced: bool) -> str:
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")
    book = pl.DataFrame({"premium": [100.0, 200.0]})
    # The default frame takes the column panel; a traced run takes its own.
    af = ActuarialFrame(book, mode="debug") if traced else ActuarialFrame(book)
    if traced:
        af._traced_run = True  # noqa: SLF001 -- what --mode debug's tracing sets
    af["commission"] = pl.col("premum") * 0.1
    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        af.collect()
    return str(caught.value)


@_OUTPUTS
def test_a_missing_column_at_collect_writes_its_source_line_plain(
    output: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _standard_output(output, monkeypatch)
    message = _missing_column_message(monkeypatch, traced=False)

    assert "Source Code:" in message
    assert 'af["commission"] = pl.col("premum") * 0.1' in message
    assert _ESCAPE not in message


@_OUTPUTS
def test_a_traced_run_writes_its_source_line_plain(
    output: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _standard_output(output, monkeypatch)
    message = _missing_column_message(monkeypatch, traced=True)

    assert "Source Code:" in message
    assert 'af["commission"] = pl.col("premum") * 0.1' in message
    assert _ESCAPE not in message


def _friendly() -> str:
    record = CalculationRecord(
        column="premium_total",
        ordinal=1,
        operation_id=0,
        node=Col("premium_total"),
        expr="col('premium') * 12",
        dtype=None,
        source=SourceSpan(
            file="model_calculation.py",
            line=27,
            end_line=27,
            function=None,
            statement='af["premium_total"] = af["premium"] * 12',
            rhs=None,
            target_literal=True,
        ),
        origin="assignment",
    )
    return FriendlyErrorFormatter(
        record=record,
        exception=ValueError("Test error message"),
        last_good_df=pl.DataFrame({"premium": [100.0, 150.0]}),
    ).format_error()


_LOCATION = SourceLocation(
    file_path="model_calculation.py",
    line_number=17,
    function_name=None,
    source_line="af.foo = bar.split(',')",
)


def _validation() -> str:
    error = ValidationError("Invalid option: 'bogus'")
    error.source_location = _LOCATION
    return ValidationErrorFormatter(error).format_error()


def _attribute() -> str:
    error = AttributeError("'NoneType' object has no attribute 'split'")
    return AttributeErrorFormatter(error, source_location=_LOCATION).format_error()


@pytest.mark.parametrize(
    "panel", [_friendly, _validation, _attribute], ids=lambda one: one.__name__
)
@_OUTPUTS
def test_every_other_panel_writes_its_source_line_plain(
    panel: Callable[[], str], output: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _standard_output(output, monkeypatch)
    message = panel()

    assert "   ```python" in message
    assert _ESCAPE not in message


def test_a_statement_over_several_lines_keeps_every_line_under_its_heading() -> None:
    """A statement arrives as its source was read: from its first token.

    So its first line has no indentation and the lines after it keep the
    file's -- here a statement written four spaces in, inside a function.
    The block moves the lines after the first left together, keeping their
    shape, so the statement reads as it was written.
    """
    from gaspatchio.errors.models import source_block

    written = "af.total = (\n        af.a\n        + af.b\n    )"
    assert source_block(written) == [
        "   ```python",
        "   af.total = (",
        "       af.a",
        "       + af.b",
        "   )",
        "   ```",
    ]


def test_a_hanging_continuation_stays_indented_under_the_first_line() -> None:
    """With no closing line of its own there is no column to dedent to."""
    from gaspatchio.errors.models import source_block

    assert source_block("af.total = af.a + \\\n        af.b") == [
        "   ```python",
        "   af.total = af.a + \\",
        "       af.b",
        "   ```",
    ]


def _a_multi_line_model() -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"premium": [100.0, 200.0], "age": [30, 70]}))
    # The trailing comma keeps the call on three lines under ruff format.
    af["commission"] = pl.col("premum") * pl.when(
        pl.col("age") > 65,
    ).then(0.2).otherwise(0.1)
    return af


def test_a_multi_line_call_reads_as_it_was_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AF_ERROR_MODE", "enhanced")
    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        _a_multi_line_model().collect()
    message = str(caught.value)

    block = message[message.index("   ```python") :].split("   ```\n", 1)[0]
    assert block.splitlines() == [
        "   ```python",
        '   af["commission"] = pl.col("premum") * pl.when(',
        '       pl.col("age") > 65,',
        "   ).then(0.2).otherwise(0.1)",
    ]
