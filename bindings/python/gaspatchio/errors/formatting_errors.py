# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Handlers that turn a frame's failures into readable, actionable messages."""

from __future__ import annotations

import os
import re
import sys
import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, NoReturn

import polars as pl  # Import polars for exception type checking
from loguru import logger

from gaspatchio._warning import GaspatchioWarning
from gaspatchio.util import _ENHANCING_ERROR_MODES, _ERROR_MODE_OFF, get_error_mode

# The two modules are read by attribute, not name by name, so that a test
# replacing ``boundary.search_collect_failure`` or
# ``compilation_finder.CompilationErrorFinder`` is the one this module calls.
from . import boundary, compilation_finder
from .boundary import AmbiguousAttribution
from .constants import PLAN_DUMP_BOUNDARY
from .exception_utils import attach
from .formatter import (
    AttributeErrorFormatter,
    FriendlyErrorFormatter,
    ValidationErrorFormatter,
    blocks_text,
    graph_facts,
    operands_already_named,
    reading_text,
)
from .models import (
    ColumnInfo,
    DataFrameContext,
    EnhancedError,
    ErrorMetadata,
    ErrorType,
    OperationContext,
    SourceLocation,
    Suggestion,
    SuggestionType,
    source_block,
)
from .policy_locator import policy_line
from .suggestions import ErrorSuggestionEngine
from .validation import ValidationError

# Import thefuzz only if available, provide fallback
try:
    from thefuzz import fuzz
except ImportError:
    fuzz = None

if TYPE_CHECKING:
    from collections.abc import Callable

    # Avoid circular import during runtime, import for type checking only
    from gaspatchio.frame.base import ActuarialFrame
    from gaspatchio.frame.calculations import CalculationRecord

    from .formatter import GraphFacts


class PerformanceWarning(GaspatchioWarning):
    """A pattern in the user's own code that Polars cannot run fast.

    A ``GaspatchioWarning``, so a filter on either class reaches it.
    """


def _extract_missing_column_robust(error_str: str) -> str | None:
    """Extract the missing column name from specific error patterns.

    Assumes error_str is derived from `str(ColumnNotFoundError)` or similar.
    """
    # polars appends a query-plan dump after the human-readable message, at
    # PLAN_DUMP_BOUNDARY: "... failure: ... DF [...]; PROJECT */2 COLUMNS".
    # Only the leading message names the missing column, so scope every
    # bare-token heuristic to that header. The plan dump's uppercase "COLUMNS"
    # token ends a line and would otherwise be picked up by the
    # word-before-newline pattern (the failure mode introduced by polars 1.42's
    # richer error text).
    header = error_str.split(PLAN_DUMP_BOUNDARY, 1)[0]

    # Pattern 1 (most reliable): a quoted column name after a "column"-ish
    # keyword. polars phrasings: `unable to find column "NAME"; ...`,
    # `column "NAME" not found`. Tried first so a quoted name always wins.
    match = re.search(
        # Optional 'Error:', optional context words, quote, capture name, quote.
        r"(?:Error:\s*)?(?:column|Field not found:|unable to find column)"
        r"\s*.*?('|\")([^\'\"]+)\1",
        header,
        re.IGNORECASE,
    )
    if match:
        # The actual column name is in group 2
        return match.group(2)

    # Pattern 2: Specific "ColumnNotFoundError: name" format.
    match = re.search(r"ColumnNotFoundError:\s*([a-zA-Z0-9_]+)", header)
    if match:
        return match.group(1)

    # Pattern 3 (legacy fallback): older polars emitted the bare column name
    # alone on the first line. Scoped to the header so the plan dump can't
    # shadow it; only used when the quoted patterns above did not match.
    match = re.search(r"([a-zA-Z0-9_]+)\n", header)
    if match:
        col_name = match.group(1)
        # Relax the length check, maybe short names are valid
        if col_name.lower() != "traceback":
            return col_name

    return None


def _find_similar_columns(
    missing_col: str,
    available_cols: list[str],
    max_suggestions=5,
) -> list[str]:
    """
    Find column names similar to the missing column using thefuzz library (WRatio).

    Args:
        missing_col: The missing column name
        available_cols: List of available column names
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of column names similar to the missing one

    """
    if not missing_col or not available_cols:
        return []

    # Guard against fuzz library issues
    if fuzz is None:
        return []

    # Use fuzz.WRatio - often better for mixed-case and partial matches.
    # Calculate scores for all available columns.
    scores = [(col, fuzz.WRatio(missing_col, col)) for col in available_cols]

    # Sort by score descending
    scores.sort(key=lambda x: x[1], reverse=True)

    # Filter matches based on score cutoff.
    # WRatio score is 0-100.
    score_cutoff = 86
    similar_cols = [match[0] for match in scores if match[1] >= score_cutoff]

    # Return top N suggestions
    return similar_cols[:max_suggestions]


def _reads_column(record: CalculationRecord, column: str) -> bool:
    """Return whether a calculation's expression names ``column`` as a column.

    Looks for the patterns an expression prints a column reference as,
    ``col("column")`` or ``["column"]``, in either quote.
    """
    expr_str = str(record.expr)
    return (
        f'col("{column}")' in expr_str
        or f"col('{column}')" in expr_str
        or f'["{column}"]' in expr_str
        or f"['{column}']" in expr_str
    )


@dataclass(frozen=True, slots=True)
class _WhereItFailed:
    """Where the missing-column panel can say a missing column was asked for.

    One decision, which the panel's Location, its list of columns and the
    heading over that list all read, so no part of the panel can claim what
    another part disowns. Where the failing definition is established,
    ``record`` is that calculation and ``readable`` the columns it could
    read. Where it is not, both are ``None`` and ``unestablished`` says, in
    a sentence, what is known instead: the panel claims no line it has not
    shown to be the failure.
    """

    record: CalculationRecord | None
    readable: list[str] | None
    unestablished: str | None


def _where_it_failed(frame: ActuarialFrame, missing_col: str) -> _WhereItFailed:
    """Decide which calculation asked for ``missing_col``, and what it could read.

    The failing definition is the first calculation in the attribution
    window to name the column: a column one calculation could read stays
    readable to every later one in the window, so an earlier mention would
    have failed first. What it could read is the frame as it stood before
    it -- the columns the window opened over, then each column an earlier
    operation in the window defined; a calculation defined in the same
    operation reads none of its siblings.

    It is established only where that holds up: the plan the window opened
    over resolves, and the column is not among what the calculation could
    read. Otherwise the failure is in a step the window does not record --
    a filter, select or join run before it, which reshaped the frame -- and
    the decision says that rather than pointing at a line that merely names
    the column too.
    """
    try:
        records = frame._attribution_ops()  # noqa: SLF001 -- the frame's own log
    except Exception:  # noqa: BLE001 -- the panel still says what it can
        records = []
    naming = next((r for r in records if _reads_column(r, missing_col)), None)
    if naming is None:
        return _WhereItFailed(
            None,
            None,
            f"No calculation recorded since the frame was last filtered, "
            f"selected, joined or otherwise reshaped names '{missing_col}'.",
        )
    readable = _columns_before(frame, records, naming)
    if readable is None:
        return _WhereItFailed(
            None,
            None,
            f"The plan already fails before {_the_calculation(naming)} that names "
            f"'{missing_col}', in a step run ahead of it, such as a filter, "
            f"select or join.",
        )
    if missing_col in readable:
        return _WhereItFailed(
            None,
            None,
            f"{_the_calculation(naming).capitalize()} names '{missing_col}', and "
            f"the column was there for it to read.",
        )
    return _WhereItFailed(naming, readable, None)


def _columns_before(
    frame: ActuarialFrame,
    records: list[CalculationRecord],
    failing: CalculationRecord,
) -> list[str] | None:
    """Return the frame's columns before ``failing``, or ``None`` if its plan fails."""
    baseline = getattr(frame, "_baseline_df", None)
    if baseline is None:
        return None
    try:
        columns = list(baseline.collect_schema().names())
    except Exception:  # noqa: BLE001 -- a plan that will not resolve is the answer
        return None
    for record in records:
        if record.operation_id >= failing.operation_id:
            break
        if record.column not in columns:
            columns.append(record.column)
    return columns


def _the_calculation(record: CalculationRecord) -> str:
    """Name a calculation by where it was written, or by its column where unknown."""
    if record.source is None:
        return f"the calculation defining '{record.column}'"
    return f"the calculation at {record.source.file}:{record.source.line}"


# How many of the panel's columns are listed before the rest are counted; the
# last column is always listed too.
_PANEL_LEADING_COLUMNS = 5

# A statement this close to the top of its file has too little above it for
# "check the operations before it" to point anywhere.
_TOO_EARLY_TO_LOOK_BACK = 5

# The two headings over the panel's column list: the state the failing
# calculation saw, or -- where no calculation is established as the failure
# -- the frame's columns now, said to be that rather than passed off as the
# first.
_AT_THE_POINT_OF_FAILURE = "   (Available columns at the point of failure)\n"
_AS_THE_FRAME_STANDS = (
    "   (The frame's columns as they stand, which may include columns\n"
    "    defined after the failing step)\n"
)


def _rendered(expr: object) -> str:
    """Return a recorded expression as a reader is shown one, everywhere.

    The engine's own text names the framework's quotient kernels and the
    machine path of the library they live in --
    ``col("a")./…/_internal.cpython-313-darwin.so:ieee_div([col("b")])`` --
    where the walk-through in an audit export, and the text a fingerprint
    is taken over, write the operator the kernel computes and no path:
    ``[(col("a")) / (col("b"))]``. A panel that printed the raw text
    showed the reader a Rust function and a path on somebody else's disk
    in place of the division they wrote. One rendering, so the panel and
    the record say the same thing about the same line. A list kernel is
    written as the operation it computes the same way: a per-period
    ``when`` as the ``when`` the line wrote, not ``list_conditional``.
    """
    from gaspatchio.frame.graph.graph_utils import (  # noqa: PLC0415 — import cycle
        clean_expression_string,
    )
    from gaspatchio.frame.lowering._polars.rendering import (  # noqa: PLC0415 — beside the one above
        conditional_comparisons,
    )

    comparisons = conditional_comparisons(expr) if isinstance(expr, pl.Expr) else None
    return clean_expression_string(str(expr), comparisons=comparisons)


def _location_lines(where: _WhereItFailed) -> str:
    """Return the panel's Location section, from the one decision."""
    record = where.record
    if record is None:
        # A path stays whole on its line, so it can be copied as it stands.
        reason = textwrap.fill(
            where.unestablished or "",
            width=77,
            initial_indent="   ",
            subsequent_indent="   ",
            break_long_words=False,
            break_on_hyphens=False,
        )
        return f"📍 Location: not established\n{reason}\n\n"
    operation = f"   Operation: {record.column} = {_rendered(record.expr)}\n\n"
    if record.source is None:
        return "📍 Location: (Source location not available)\n" + operation
    return (
        f"📍 Location: {record.source.file}:{record.source.line}\n"
        + operation
        + "📝 Source Code:\n"
        # Plain text: this panel is the exception's message (``source_block``).
        + "\n".join(source_block(record.source.statement))
        + "\n\n"
    )


def _frame_columns(frame: ActuarialFrame) -> list[str]:
    """Return the frame's columns as they stand."""
    # The plan itself, which no public property returns as what it is:
    # ``to_frame`` hands back the same object annotated as a DataFrame.
    plan = frame._df  # noqa: SLF001 -- see above
    if plan is None:
        # No plan to read: fall back to the tracked column order
        return frame.columns
    try:
        # collect_schema().names() reads a LazyFrame without a warning, and
        # reads an eager DataFrame too
        columns = plan.collect_schema().names()
    except pl.exceptions.PolarsError:
        # A plan whose schema will not resolve: fall back to the tracked
        # column order
        return frame.columns
    return columns


def _format_column_message(
    frame: ActuarialFrame,
    missing_col: str,
    original_msg: str,
) -> str:
    """Format a helpful error message for a missing column."""
    # One decision for the Location, the list and its heading: what the
    # failing calculation could have read, where it is established, and the
    # frame's columns as they stand, said to be that, where it is not.
    where = _where_it_failed(frame, missing_col)
    available_cols = _frame_columns(frame) if where.readable is None else where.readable

    similar_cols = _find_similar_columns(missing_col, available_cols)

    # Check if we should use rich formatting
    error_mode = get_error_mode()
    # Always use rich formatting when enhanced mode is on
    use_rich = error_mode in _ENHANCING_ERROR_MODES

    if use_rich:
        # Rich formatted error message
        error_msg = f"\n{'─' * 80}\n"
        error_msg += "❌ Calculation Error\n"
        error_msg += f"{'─' * 80}\n\n"
        error_msg += _location_lines(where)

        error_msg += "🔴 Error Details:\n"
        error_msg += "   Type: ColumnNotFoundError\n"
        error_msg += f"   Message: Column '{missing_col}' not found\n\n"

        error_msg += "📊 Calculation State Before Error:\n"
        error_msg += (
            _AT_THE_POINT_OF_FAILURE
            if where.readable is not None
            else _AS_THE_FRAME_STANDS
        )
        # The frame's plan is lazy, and a lazy plan does not know its row
        # count without running it
        error_msg += f"   shape: (unknown, {len(available_cols)})\n"
        error_msg += "   ┌" + "─" * 78 + "┐\n"

        # Format columns in a table-like structure
        for i, col in enumerate(available_cols):
            if i < _PANEL_LEADING_COLUMNS or i >= len(available_cols) - 1:
                error_msg += f"   │ {col:<76} │\n"
            elif i == _PANEL_LEADING_COLUMNS:
                hidden = len(available_cols) - _PANEL_LEADING_COLUMNS - 1
                error_msg += f"   │ ... ({hidden} more columns) ...{' ' * 49} │\n"

        error_msg += "   └" + "─" * 78 + "┘\n\n"

        if similar_cols:
            error_msg += "💡 Did you mean one of these?\n"
            for col in similar_cols[:3]:
                error_msg += f"   • {col}\n"
            error_msg += "\n"

        error_msg += "─" * 80
    else:
        # Simple formatted error message (original)
        error_msg = f"Column '{missing_col}' not found in the DataFrame.\n\n"

        if similar_cols:
            error_msg += (
                "Did you mean one of these?\n - " + "\n - ".join(similar_cols) + "\n\n"
            )

        heading = (
            "Available columns are:"
            if where.readable is not None
            else "Available columns are (the frame's columns as they stand, which "
            "may include columns defined after the failing step):"
        )
        error_msg += heading + "\n - " + "\n - ".join(available_cols)
        error_msg += f"\n\nOriginal Polars Error: {original_msg}"

    return error_msg


def _reads_as_an_indicator(column: str) -> str:
    """Render ``column`` the way the model would have to write it back."""
    return f"af.{column}" if column.isidentifier() else f"af[{column!r}]"


def _stored_predicate_sentence(column: str | None) -> str:
    """Return the refusal a stored numeric predicate earns, in the order it earns it.

    What went wrong, then why the rule is the rule, then the move that makes
    the model say what it means. A column of 0s and 1s is the one numeric
    column a condition can read on its own; a probability, a rate or a
    proportion is a number the model has to compare before it means true or
    false, and comparing it is the whole fix. The same sentence serves a
    stored indicator read by ``&``, ``|`` or ``~`` (§11.1.27), which applies the
    same check, so the remedy names that spelling too.
    """
    named = f"Column {column!r}" if column else "A numeric column"
    written = _reads_as_an_indicator(column) if column else "af.flag"
    return (
        f"{named} is used as a condition but holds a value that is neither "
        "0.0 nor 1.0.\n"
        "\n"
        "A stored indicator is exactly 0.0 (false) or 1.0 (true) in every "
        "period. A null, a fraction such as 0.5, and a non-finite value are "
        "none of those, so there is no answer to give for that row and the "
        "run stops here rather than choosing one.\n"
        "\n"
        f"If {written} holds a probability, a rate or a proportion rather "
        "than an indicator, it is not a condition on its own -- compare it "
        f"and use the comparison: when({written} == 1.0) for an exact match, "
        f"or when({written} > 0.5) for a threshold. As an operand of &, | or "
        f"~ the same comparison goes in brackets: ({written} == 1.0)."
    )


def _checked_integer_sentence(column: str | None) -> str:
    """Return the refusal a failed whole-number conversion earns.

    ``to_integer`` converts exactly or not at all, which is the point of it:
    a duration in completed years, a count of whole units, a policy number
    used as a key. Every way of getting a whole number out of something that
    is not one -- rounding, truncating, treating an absence as nought -- is a
    decision about the model, so the refusal hands that decision back rather
    than taking it.
    """
    named = f"Column {column!r}" if column else "A numeric column"
    written = _reads_as_an_indicator(column) if column else "af.value"
    return (
        f"{named} is converted to a whole number but holds a value that is "
        "not one.\n"
        "\n"
        "A whole-number conversion is exact or it does not happen. A "
        "fraction, an absent value, a non-finite value, and a number outside "
        "the signed 64-bit range are none of them whole, so the run stops "
        "here rather than rounding on your behalf.\n"
        "\n"
        f"Say which rounding you mean and the conversion follows: "
        f"{written}.floor().to_integer() for completed years and whole units, "
        f"{written}.ceil().to_integer() to go up, {written}.round(0)"
        f".to_integer() for the nearest. If the value can be absent, fill it "
        f"first -- {written}.fill_null(0.0)."
    )


def _sig_figs_past_i64_sentence(column: str | None) -> str:
    """Return the refusal a whole number rounded up past ``i64`` earns.

    Kept to its leading figures, a whole number near the top of the range
    can round up past it -- 2**63 - 1 to ten figures is 9,223,372,037 x
    10**9 -- and no ``i64`` holds the answer.
    """
    named = f"Column {column!r}" if column else "A whole-number column"
    written = _reads_as_an_indicator(column) if column else "af.value"
    return (
        f"{named} holds a whole number that rounds, to the significant figures "
        "asked for, past the signed 64-bit range.\n"
        "\n"
        "Every integer in a calculation graph is an i64, and round_sig_figs "
        "keeps a whole number whole: kept to its leading figures this one "
        "rounds up past [-2**63, 2**63 - 1], where there is no whole number to "
        "write the answer as. The run stops here rather than wrapping it.\n"
        "\n"
        "Keep fewer figures, or carry the value as a decimal first -- "
        f"({written} * 1.0).round_sig_figs(...) -- where its magnitude matters "
        "and its last digits do not."
    )


def _finer_unit_sentence(column: str | None) -> str:
    """Return the refusal a value the finer of two time units cannot hold earns.

    A conditional over a microsecond branch and a nanosecond one answers in
    nanoseconds, so neither branch loses its last digits. A nanosecond count
    reaches only the years 1677 to 2262, and a branch holding a date outside
    them -- an open-ended 9999-12-31 is the usual one -- has no answer in the
    finer unit. Rounding the other branch to the coarser unit would lose
    digits the model never said it could spare, so the run stops and names
    the two ways out.
    """
    named = f"Column {column!r}" if column else "A branch of this conditional"
    return (
        f"{named} holds a date and time or a duration that the finer of the "
        "conditional's two time units cannot hold.\n"
        "\n"
        "A conditional whose two branches are in different time units -- "
        "microseconds and nanoseconds, say -- answers in the finer one, so "
        "neither branch loses digits. A nanosecond count reaches only the "
        "years 1677 to 2262, and this value lies outside the unit it is "
        "carried to. The run stops here rather than answering a null.\n"
        "\n"
        "Write a value the finer unit holds (an open-ended date before 2262), "
        "or, if the digits past the coarser unit are not part of the value, "
        "convert the finer column to the coarser unit where the data is "
        "loaded, so the record shows the conversion."
    )


def _decimal_pair_sentence(column: str | None) -> str:
    """Return the refusal a value the pair's decimal type cannot hold earns.

    A conditional whose branches are two fixed-point decimals, or a decimal
    and a whole number, answers in the one decimal type Polars gives the
    pair: the larger number of places, and room for 38 digits. A branch
    holding a value with more whole digits than that type leaves room for --
    ``2**62`` beside twenty places needs thirty-nine -- has no answer in it.
    Dropping places from the other branch would lose digits the model never
    said it could spare, so the run stops and names the two ways out.
    """
    named = f"Column {column!r}" if column else "A branch of this conditional"
    return (
        f"{named} holds a value that the decimal type the conditional answers "
        "in cannot hold.\n"
        "\n"
        "A conditional whose two branches are fixed-point decimals, or a "
        "decimal and a whole number, answers in one decimal type: the larger "
        "number of decimal places of the two, with room for 38 digits in all. "
        "This value has more whole digits than that type leaves room for "
        "beside those places. The run stops here rather than answering a "
        "null.\n"
        "\n"
        "Put the two branches in one type where the data is loaded: a decimal "
        "with fewer places, so the conversion shows where it was made, or a "
        "double, if the digits past fifteen figures are not part of the values."
    )


def _integer_range_sentence(column: str | None) -> str:
    """Return the refusal a whole number no ``i64`` carries earns.

    The value is whole, so the rounding advice the fractional case gives
    would be advice about a defect this column does not have. What it is
    instead is a number with more digits than a signed 64-bit integer holds
    -- a warehouse identifier, a hash -- and the move that keeps every one of
    them is text, which is the same remedy the audit export offers for the
    same boundary.
    """
    named = f"Column {column!r}" if column else "A whole-number column"
    written = _reads_as_an_indicator(column) if column else "af.value"
    return (
        f"{named} holds a whole number outside the signed 64-bit range.\n"
        "\n"
        "Every integer in a calculation graph travels as a signed 64-bit "
        "value, and outside [-2**63, 2**63 - 1] there is no exact one to "
        "give. Rounding would not help -- the value is already whole -- so "
        "the run stops here rather than wrapping it.\n"
        "\n"
        f"Keep every digit by holding the column as text -- "
        f"{written}.to_text() -- which is what an identifier is for. If the "
        "column really is a quantity within range, the width it was stored "
        "in is not the problem and the value out of range is."
    )


def _wide_arithmetic_sentence(column: str | None) -> str:
    """Return the refusal arithmetic on a whole number no ``i64`` carries earns.

    A ``UInt64``, ``Int128`` or ``UInt128`` column holding such a number
    keeps the width it arrived in, so ``to_text`` can write the number by
    its digits; arithmetic on it would compute in that width and wrap where
    the record says ``i64``, so the run stops instead. The two moves are the
    two things such a column can be: an identifier, which is text, or a
    quantity, whose narrower type is the author's to choose.
    """
    return _wide_read_sentence(
        column,
        refused="arithmetic on it is refused",
        because="arithmetic in that type would wrap",
        instead="wrapping it",
        operand="An operand of this arithmetic",
    )


def _wide_read_sentence(
    column: str | None, *, refused: str, because: str, instead: str, operand: str
) -> str:
    """Return the one sentence every read of a column past ``i64`` is refused in.

    Arithmetic was the first such read refused; a sum, a running fold, an
    absolute value and a rollforward compute in the same width, or carry the
    value into doubles, where the record says ``i64``, and each is refused in
    the same words with its own operation named.
    """
    named = f"Column {column!r}" if column else operand
    written = _reads_as_an_indicator(column) if column else "af.value"
    return (
        f"{named} holds a whole number outside the signed 64-bit range, and "
        f"{refused}.\n"
        "\n"
        "Every integer in a calculation graph is an i64. A column whose values "
        "all fit one is read as one; this one holds a value that does not, so "
        f"it keeps its wider type, and {because} where the record says i64. "
        f"The run stops here rather than {instead}.\n"
        "\n"
        f"If the column is an identifier, keep every digit as text -- "
        f"{written}.to_text(). If it is a quantity, no i64 holds it as it "
        "stands: choose the narrower type it is to be carried in yourself, "
        "and state it on the model points before the run -- rescaled to a "
        "unit whose values fit an Int64, where a reader can see the unit."
    )


# The reads past ``i64`` other than arithmetic: what is refused, why it would
# go wrong in the column's own width, and what the run declined to do.
_WIDE_READS: Final[dict[str, tuple[str, str, str]]] = {
    "sum": ("its sum is refused", "a sum in that type would wrap", "wrapping it"),
    "running sum": (
        "a running sum of it is refused",
        "a running sum in that type would wrap",
        "wrapping it",
    ),
    "running product": (
        "a running product of it is refused",
        "a running product in that type would wrap",
        "wrapping it",
    ),
    "remaining sum": (
        "a remaining sum of it is refused",
        "a remaining sum in that type would wrap",
        "wrapping it",
    ),
    "absolute value": (
        "its absolute value is refused",
        "an absolute value in that type wraps at the type's least value",
        "wrapping it",
    ),
    "rollforward": (
        "a rollforward reading it is refused",
        "the rollforward would carry it into a double that cannot hold its digits",
        "rounding it",
    ),
    "significant figures": (
        "rounding it to significant figures is refused",
        "the rounding would carry it into a double that cannot hold its digits",
        "rounding it",
    ),
    "operation": (
        "an operation carrying it is refused",
        "an operation that carries it answers in that type",
        "carrying it",
    ),
    "band": (
        "placing it in a band is refused",
        (
            "a band's breakpoints are decimals, so placing it would read it as "
            "a double that cannot hold its digits,"
        ),
        "rounding it",
    ),
}


def wide_read_refusal(column: str | None, read: str) -> str:
    """Return the refusal a read in ``_WIDE_READS`` earns, for a door outside the plan.

    The plan's own reads smuggle a rule out and are lifted back to this
    sentence (:func:`_lift_plan_refusal`); a fold that holds the collected
    values -- ``run_aggregated``'s ``Sum`` -- raises it directly.
    """
    return _wide_read_headline(read)(column)


def integer_total_refusal(column: str, total: int, where: str = "") -> str:
    """Return the refusal a total of whole numbers that no ``i64`` holds earns.

    A fold totals an integer column in its own width, so a book of 2**62,
    2**62 and 5 summed to 9.2e18 one policy at a time and to -9.2e18 two at a
    time: wrapped, and moved by ``batch_size``. The total is now taken
    exactly, and where it lies outside ``[-2**63, 2**63 - 1]`` the fold is
    refused by its column and its exact value, whatever the batches were.
    ``where`` names the scenario for a total taken within one.
    """
    named = _reads_as_an_indicator(column)
    return (
        f"Column {column!r} totals {total}{where}, outside the signed 64-bit "
        "range, and its sum is refused.\n"
        "\n"
        "Every integer in a calculation graph is an i64, a total as much as a "
        "column, and this total has no i64 to be written in: summed in the "
        "column's own width it would wrap, and the answer would move with how "
        "the policies were batched. The run stops here rather than wrapping "
        "it.\n"
        "\n"
        "If the column is a quantity, carry it as a decimal before it is "
        f"summed -- {named} * 1.0 -- or rescale it to a unit whose total fits "
        "an Int64, where a reader can see the unit. If it is an identifier, "
        "it is not a number to total."
    )


def _wide_read_headline(read: str) -> Callable[[str | None], str]:
    """Return the headline one of the reads in ``_WIDE_READS`` is owed."""
    refused, because, instead = _WIDE_READS[read]

    def headline(column: str | None) -> str:
        return _wide_read_sentence(
            column,
            refused=refused,
            because=because,
            instead=instead,
            operand=f"The operand of this {read}",
        )

    return headline


def _checked_float_sentence(column: str | None) -> str:
    """Return the refusal a whole number outside the exact range earns.

    ``to_float`` widens rather than rounds. Every whole number up to 2**53
    has a double of its own; above that the doubles are further apart than
    one, so two neighbouring policy numbers would arrive as one value and a
    later comparison would find them equal. The rule is the range, not the
    number: ``2**53 + 2`` is a double exactly and is refused all the same,
    because its neighbour ``2**53 + 1`` is not, and the sentence says the
    rule it applies. The refusal hands that back rather than taking it, and
    names the two ways out: text keeps every digit, and an explicit
    rescaling says what was given up.
    """
    named = f"Column {column!r}" if column else "A numeric column"
    written = _reads_as_an_indicator(column) if column else "af.value"
    return (
        f"{named} holds a whole number outside [-2**53, 2**53], where no "
        "double names every whole number exactly: two neighbours can share "
        "one double.\n"
        "\n"
        "Above 2**53 the doubles are more than one apart, so two "
        "neighbouring whole numbers can arrive as the same floating-point "
        "value and everything downstream would read them as equal. The run "
        "stops at the edge of the range rather than merging them, even for "
        "a number that is itself a double.\n"
        "\n"
        f"If the column is an identifier rather than a quantity, keep every "
        f"digit as text -- {written}.to_text(). If it is a quantity and the "
        "precision above 2**53 is not part of it, rescale it in the model "
        "where a reader can see the unit you moved it to."
    )


# Where Polars reports the values a strict cast could not convert:
# ``... failed in column 'literal' for 1 out of 1 values: ["<the sentence>"]``.
# That list is the channel a plan refusal actually travels through, and it is
# the ONLY place the lift may look. The same sentence is also a literal in the
# plan, so it appears in the resolved-plan dump (PLAN_DUMP_BOUNDARY) that
# *any* resolution-time error on a plan carrying the check prints -- an
# arithmetic clash three columns away included. Matching the whole text put this
# project's refusal at the top of somebody else's error, with the real
# headline four lines down, for every model holding a stored indicator. If a
# later Polars words this line differently the lift stops firing and the
# engine's own message stands: the failure direction is a refusal that reads
# badly, never a wrong sentence in front of a right one.
_REPORTED_VALUES = re.compile(
    r"failed in column '[^']*' for \d+ out of \d+ values: \[(.*?)\]"
)


def _round_past_i64_sentence(column: str | None) -> str:
    """Return the refusal a whole number rounded to a step past ``i64`` earns.

    Rounded to tens or a coarser step, a whole number near either end of the
    range moves past it -- 2**63 - 1 to tens is 9,223,372,036,854,775,810 --
    and no ``i64`` holds the answer.
    """
    named = f"Column {column!r}" if column else "A whole-number column"
    written = _reads_as_an_indicator(column) if column else "af.value"
    return (
        f"{named} holds a whole number that rounds, to the step asked for, "
        "past the signed 64-bit range.\n"
        "\n"
        "Every integer in a calculation graph is an i64, and round with a "
        "negative decimals keeps a whole number whole: moved to its nearest "
        "multiple of the step this one lands outside [-2**63, 2**63 - 1], "
        "where there is no whole number to write the answer as. The run stops "
        "here rather than wrapping it.\n"
        "\n"
        "Round to a finer step, or carry the value as a decimal first -- "
        f"({written} * 1.0).round(...) -- where its magnitude matters and its "
        "last digits do not."
    )


def _fold_past_i64_headline(
    fold: str, *, per_period: bool
) -> Callable[[str | None], str]:
    """Return the refusal a fold of whole numbers whose answer no ``i64`` holds earns.

    A sum, a running sum or product and a remaining sum of a per-period
    whole-number column are taken exactly, and an answer outside
    ``[-2**63, 2**63 - 1]`` -- the total, or one period of a running fold --
    has no ``i64`` to be written in. Taken in the column's own width the fold
    wrapped: ``[2**63 - 1, 1]`` summed to ``-2**63``.
    """
    where = " in some period" if per_period else ""

    def headline(column: str | None) -> str:
        named = f"Column {column!r}" if column else "A whole-number column"
        written = _reads_as_an_indicator(column) if column else "af.value"
        return (
            f"{named} holds whole numbers whose {fold}{where} lies outside the "
            f"signed 64-bit range, and the {fold} is refused.\n"
            "\n"
            "Every integer in a calculation graph is an i64, a total as much as "
            "a column, and this one has no i64 to be written in: taken in the "
            "column's own width it would wrap, and [2**63 - 1, 1] would sum to "
            "-2**63. The run stops here rather than wrapping it.\n"
            "\n"
            "If the column is a quantity, carry it as a decimal before the "
            f"{fold} -- ({written} * 1.0) -- or rescale it to a unit whose "
            "totals fit an Int64, where a reader can see the unit. If it is an "
            "identifier, it is not a number to total."
        )

    return headline


def _absolute_value_past_i64_sentence(column: str | None) -> str:
    """Return the refusal the absolute value of ``-2**63`` earns.

    ``-2**63`` is the one ``i64`` whose absolute value, ``2**63``, no ``i64``
    holds; in its own width ``abs`` answered ``-2**63`` back.
    """
    named = f"Column {column!r}" if column else "A whole-number column"
    written = _reads_as_an_indicator(column) if column else "af.value"
    return (
        f"{named} holds -2**63, whose absolute value 2**63 lies outside the "
        "signed 64-bit range, and its absolute value is refused.\n"
        "\n"
        "Every integer in a calculation graph is an i64, and -2**63 is the one "
        "whose absolute value has no i64 to be written in: taken in its own "
        "width it comes back as -2**63, a negative absolute value. The run "
        "stops here rather than wrapping it.\n"
        "\n"
        "If the column is a quantity, carry it as a decimal first -- "
        f"({written} * 1.0).abs() -- where its magnitude matters and its last "
        "digit does not. If it is an identifier, it is not a number to take "
        "the absolute value of."
    )


def _clip_past_2_53_sentence(column: str | None) -> str:
    """Return the refusal a per-period clip of a large whole number earns.

    The clip a bound read from a column takes is held in doubles, and above
    2**53 a double does not tell two neighbouring whole numbers apart, so the
    value would be compared with its bounds, and answered, as its nearest
    double.
    """
    named = f"Column {column!r}" if column else "A whole-number column"
    written = _reads_as_an_indicator(column) if column else "af.value"
    return (
        f"{named} is held between bounds a column gives, and a value or a "
        "bound of it lies at or beyond 2**53 in magnitude, so the clip is refused.\n"
        "\n"
        "A per-period value held between bounds read from columns is compared "
        "in doubles, and above 2**53 the doubles are more than one apart: the "
        "value would be compared, and answered, as the nearest double, which "
        "can be a different whole number. The run stops here rather than "
        "answering one.\n"
        "\n"
        "Write the bounds as numbers in the line, which hold whole numbers "
        f"exactly -- {written}.clip(0, 14) -- or carry the value as a decimal "
        f"first -- ({written} * 1.0).clip(...) -- where its magnitude matters "
        "and its last digits do not."
    )


def _plan_refusals() -> tuple[tuple[str, Callable[[str | None], str]], ...]:
    """Pair each smuggled sentence with the headline it is owed.

    A table rather than a chain of branches, because the smuggling trick is
    one mechanism with several users: anything built on ``require_valid_rows``
    gets a readable first line by adding a row here, and nothing gets one by
    accident.
    """
    from gaspatchio.frame.lowering._polars.validation import (  # noqa: PLC0415 — import cycle
        ABSOLUTE_VALUE_PAST_I64_RULE,
        CHECKED_FLOAT_RULE,
        CHECKED_INTEGER_RULE,
        CLIP_PAST_2_53_RULE,
        DECIMAL_PAIR_RULE,
        FINER_UNIT_RULE,
        INTEGER_RANGE_RULE,
        REMAINING_SUM_PAST_I64_RULE,
        ROUND_PAST_I64_RULE,
        RUNNING_PRODUCT_PAST_I64_RULE,
        RUNNING_SUM_PAST_I64_RULE,
        SIG_FIGS_PAST_I64_RULE,
        STORED_PREDICATE_RULE,
        SUM_PAST_I64_RULE,
        WIDE_ABSOLUTE_VALUE_RULE,
        WIDE_ARITHMETIC_RULE,
        WIDE_BAND_RULE,
        WIDE_CARRY_RULE,
        WIDE_REMAINING_SUM_RULE,
        WIDE_ROLLFORWARD_RULE,
        WIDE_RUNNING_PRODUCT_RULE,
        WIDE_RUNNING_SUM_RULE,
        WIDE_SIG_FIGS_RULE,
        WIDE_SUM_RULE,
    )

    return (
        (STORED_PREDICATE_RULE, _stored_predicate_sentence),
        (CHECKED_INTEGER_RULE, _checked_integer_sentence),
        (CHECKED_FLOAT_RULE, _checked_float_sentence),
        (INTEGER_RANGE_RULE, _integer_range_sentence),
        (FINER_UNIT_RULE, _finer_unit_sentence),
        (DECIMAL_PAIR_RULE, _decimal_pair_sentence),
        (SIG_FIGS_PAST_I64_RULE, _sig_figs_past_i64_sentence),
        (ROUND_PAST_I64_RULE, _round_past_i64_sentence),
        (CLIP_PAST_2_53_RULE, _clip_past_2_53_sentence),
        (ABSOLUTE_VALUE_PAST_I64_RULE, _absolute_value_past_i64_sentence),
        (SUM_PAST_I64_RULE, _fold_past_i64_headline("sum", per_period=False)),
        (
            RUNNING_SUM_PAST_I64_RULE,
            _fold_past_i64_headline("running sum", per_period=True),
        ),
        (
            RUNNING_PRODUCT_PAST_I64_RULE,
            _fold_past_i64_headline("running product", per_period=True),
        ),
        (
            REMAINING_SUM_PAST_I64_RULE,
            _fold_past_i64_headline("remaining sum", per_period=True),
        ),
        (WIDE_ARITHMETIC_RULE, _wide_arithmetic_sentence),
        (WIDE_SUM_RULE, _wide_read_headline("sum")),
        (WIDE_RUNNING_SUM_RULE, _wide_read_headline("running sum")),
        (WIDE_RUNNING_PRODUCT_RULE, _wide_read_headline("running product")),
        (WIDE_REMAINING_SUM_RULE, _wide_read_headline("remaining sum")),
        (WIDE_ABSOLUTE_VALUE_RULE, _wide_read_headline("absolute value")),
        (WIDE_ROLLFORWARD_RULE, _wide_read_headline("rollforward")),
        (WIDE_SIG_FIGS_RULE, _wide_read_headline("significant figures")),
        (WIDE_CARRY_RULE, _wide_read_headline("operation")),
        (WIDE_BAND_RULE, _wide_read_headline("band")),
    )


def _lift_plan_refusal(error: BaseException) -> None:
    """Put a refusal the lazy plan smuggled out at the top of ``error``'s message.

    A lazy plan cannot raise. The one thing it can do is fail an operation,
    so a per-row refusal is written as a string that will not cast to Int64
    and the sentence comes back as one of the values Polars says it could not
    convert -- under a headline about types, three lines above an expression
    dump. The refusal is right and the delivery is not, and this is where the
    delivery is put right: the sentence goes first, and everything the engine
    said, including the column attribution below it, is kept underneath.

    The match is against that list of failing values and never against the
    whole message -- see ``_REPORTED_VALUES`` for what goes wrong when it is
    widened, which is the opposite of what this function is for.

    Not called under ``AF_ERROR_MODE=off``, where the contract is that the
    original exception is re-raised untouched.
    """
    from gaspatchio.frame.lowering._polars.validation import (  # noqa: PLC0415 — import cycle
        refused_column,
    )

    if getattr(error, "_plan_refusal_lifted", False):
        return
    text = str(error)
    found = _REPORTED_VALUES.search(text)
    if found is None:
        return
    reported = found.group(1)
    for rule, headline in _plan_refusals():
        if rule in reported:
            error.args = (f"{headline(refused_column(reported))}\n\n{text}",)
            attach(error, _plan_refusal_lifted=True)
            return


def _handle_frame_error(frame: ActuarialFrame, e: Exception) -> None:
    """Handle errors during frame operations, with enhanced context and suggestions.

    This handles both execution errors (from collect/profile) and validation
    errors. Whatever leaves here is checked for a refusal the lazy plan
    smuggled out (:func:`_lift_plan_refusal`) before it reaches the caller, so
    a sentence this project wrote is the first line a reader meets rather than
    a payload inside somebody else's type error.

    Under ``AF_ERROR_MODE=off`` that check does not run either. ``off`` means
    the exception leaves exactly as the engine raised it, and a door that
    rewrote the first line would be enhancing under the one setting that says
    not to.
    """
    try:
        return _diagnose_frame_error(frame, e)
    except BaseException as raised:
        if get_error_mode() != _ERROR_MODE_OFF:
            _lift_plan_refusal(raised)
            _lift_integer_power(raised)
            _lift_a_position_a_run_does_not_hold(raised)
            _lift_text_that_is_not_a_date(raised)
            _without_the_plugin_path(raised)
        raise


# Polars' integer power takes its exponent as an unsigned 32-bit integer, and
# an exponent column holding a value outside [0, 2**32 - 1] fails that
# conversion with this hint beneath it. The hint is what tells this failure
# apart from every other failed strict cast, so it is the one thing the lift
# keys on; if a later Polars words it differently, the lift stops firing and
# the engine's own message stands (pinned by
# ``test_polars_still_words_the_integer_power_failure_this_way``).
_INTEGER_POWER_HINT = (
    "if you were trying to raise an integer to a negative integer power"
)
_INTEGER_POWER_EXPONENT = re.compile(
    r"conversion from `[iu]\d+` to `u32` failed in column '([^']*)'"
)
# The call in the expression dump beneath: ``col("a").pow([col("k")])``, or
# ``2.pow([col("k")])`` for a whole-number base the frame states as an i64
# (``dyn int: 2.pow(...)`` from a raw Polars literal), read only to write the
# move in the author's names; anything else is written as ``base`` and
# ``exponent``.
_INTEGER_POWER_CALL = re.compile(
    r'(?:col\("(?P<base>[^"]+)"\)|(?:dyn int: )?(?<![\w.])(?P<literal>-?\d+))'
    r'\.pow\(\[(?:col\("(?P<exponent>[^"]+)"\)\])?'
)


def _integer_power_sentence(text: str) -> str:
    """Return the refusal an integer power over an out-of-range exponent earns.

    Two integers have an integer power only for an exponent from 0 to
    2**32 - 1 (section 11.1.25). An exponent written in the line is read
    where the line is written, and one outside that range makes the power a
    double; an exponent held in a column is only seen when the run reaches
    it, and the answer type of the line cannot change then. So the move is
    the author's: write the power in floating point.
    """
    call = _INTEGER_POWER_CALL.search(text)
    base = call.group("base") if call else None
    literal = call.group("literal") if call else None
    exponent = call.group("exponent") if call else None
    written_base = _reads_as_an_indicator(base) if base else literal
    written_exponent = _reads_as_an_indicator(exponent) if exponent else None
    headline = (
        f"{written_base} ** {written_exponent} raises an integer"
        if written_base and written_exponent
        else "An integer is raised"
    )
    b, e = written_base or "base", written_exponent or "exponent"
    as_double = (
        f"{literal}.0 ** {e}" if literal is not None else f"{b}.to_float() ** {e}"
    )
    return (
        f"{headline} to an integer exponent that holds a value outside 0 to "
        "2**32 - 1.\n"
        "\n"
        "Two integers have an integer power only for an exponent from 0 to "
        "2**32 - 1: a negative power is a fraction, and a larger one has no "
        "integer to give either, so the run stops here rather than choosing "
        "the answer's type for you.\n"
        "\n"
        "Write to_float() on either operand and the power is the floating-point "
        f"one, which takes any exponent: {as_double}, or {b} ** {e}.to_float(). "
        "An exponent written in the line, such as ** -1, is read that way "
        "already."
    )


def _lift_integer_power(error: BaseException) -> None:
    """Put the integer-power refusal at the top of Polars' failed conversion.

    ``af.a ** af.k`` over integer columns with a negative ``k`` failed with
    Polars' own ``conversion from `i64` to `u32` failed in column 'k'``, a
    sentence about types that names neither the power nor the move. The
    gaspatchio sentence goes first and the engine's text, with its
    expression, stays underneath, as a lifted plan refusal's does. Not called
    under ``AF_ERROR_MODE=off``.
    """
    if getattr(error, "_integer_power_lifted", False):
        return
    if len(error.args) != 1 or not isinstance(error.args[0], str):
        return
    text = error.args[0]
    if _INTEGER_POWER_HINT not in text or not _INTEGER_POWER_EXPONENT.search(text):
        return
    error.args = (f"{_integer_power_sentence(text)}\n\n{text}",)
    attach(error, _integer_power_lifted=True)


# Polars' one line for a strict read by position that finds no value: a
# position past a policy's run, and -- since the lowering reads a missing run
# or position as an empty run (``rules/selection.py``) -- a missing one too.
_POSITION_NOT_HELD = "get index is out of bounds"
# The receiver, where the lowering read a column: ``.otherwise(col("av"))``
# just before ``.list.get(``. A computed receiver is not named after one of
# its inputs.
_POSITION_RECEIVER = re.compile(r'\.otherwise\(col\("([^"]+)"\)\)\.list\.get\(')


def _position_sentence(column: str | None) -> str:
    """Return the refusal a read by position that finds no value earns."""
    named = f"column {column!r}" if column else "a per-period column"
    written = _reads_as_an_indicator(column) if column else "af.value"
    return (
        f"A position is read from {named} with list.get that one policy's run "
        "does not hold, so the read is refused.\n"
        "\n"
        "Each policy's run holds as many values as that policy has periods. A "
        "position past its last period -- or, counted from the end, before "
        "its first -- has no value to give, and neither has a position in a "
        "run that is missing or a position that is missing itself, so the run "
        "stops rather than answer one. A book whose policies have different "
        "terms reaches this when one position is read across all of them.\n"
        "\n"
        "Read only the positions each policy holds: test the position against "
        f"the run's own length, {written}.list.len(), in a when() that gives "
        "the value for a policy whose run is shorter; read the last period "
        f"with {written}.list.get(-1); or fill a missing run or position "
        "before it is read. The Policy line below names the first policy it "
        "stops at."
    )


def _lift_a_position_a_run_does_not_hold(error: BaseException) -> None:
    """Put the read-by-position refusal at the top of Polars' own line.

    ``af.av.list.get(36)`` over a book holding a 24-period policy failed with
    ``get index is out of bounds`` and an expression dump, which names
    neither the run, the policy nor a way through; a missing run or position
    said the same. The engine's text stays underneath. Not called under
    ``AF_ERROR_MODE=off``.
    """
    if getattr(error, "_position_lifted", False):
        return
    if not isinstance(error, pl.exceptions.ComputeError):
        return
    if len(error.args) != 1 or not isinstance(error.args[0], str):
        return
    text = error.args[0]
    if text.split("\n", 1)[0].strip() != _POSITION_NOT_HELD:
        return
    receiver = _POSITION_RECEIVER.search(text)
    column = receiver.group(1) if receiver else None
    error.args = (f"{_position_sentence(column)}\n\n{text}",)
    attach(error, _position_lifted=True, _engine_first_line=_POSITION_NOT_HELD)


# Polars' line for text a strict parse cannot read as a date or a date and
# time, with the column it read and the values it could not.
_NOT_A_DATE = re.compile(
    r"conversion from `str` to `(date|datetime[^`]*)` failed in column "
    r"'([^']*)' for \d+ out of \d+ values: \[(.*)\]"
)


def _lift_text_that_is_not_a_date(error: BaseException) -> None:
    """Put the strict-parse refusal at the top of Polars' failed conversion.

    ``af.t.str.to_date("%Y-%m-%d")`` over ``"31/12/2025"`` refuses, as section
    11.1.7 says a strict parse does, but in Polars' words, whose advice is
    Polars' own. The sentence names the column, the text that did not read
    and the two ways through. The engine's text stays underneath. Not called
    under ``AF_ERROR_MODE=off``.
    """
    if getattr(error, "_not_a_date_lifted", False):
        return
    if not isinstance(error, pl.exceptions.InvalidOperationError):
        return
    if len(error.args) != 1 or not isinstance(error.args[0], str):
        return
    text = error.args[0]
    found = _NOT_A_DATE.match(text.split("\n", 1)[0])
    if found is None:
        return
    kind, column, values = found.groups()
    what = "a date" if kind == "date" else "a date and time"
    first = values.split('", "', 1)[0].strip('"')
    sentence = (
        f"Column {column!r} holds text that does not read as {what} in the "
        f'format the line gives -- "{first}" among them -- so the parse is '
        "refused.\n"
        "\n"
        "A strict parse (the default) reads every value or none: a value it "
        "cannot read is a mistake in the format or in the data, and the run "
        "stops rather than guess which.\n"
        "\n"
        "Write the format the text is in -- str.to_date('%d/%m/%Y') for "
        "31/12/2025 -- or, where some values are meant to be missing, "
        "strict=False, which reads each value that does not fit as a null."
    )
    error.args = (f"{sentence}\n\n{text}",)
    attach(error, _not_a_date_lifted=True, _engine_first_line=found.group(0))


def _without_the_plugin_path(error: BaseException) -> None:
    """Take the extension's filesystem path out of ``error``'s message.

    Polars names a plugin call by the library it was loaded from, so a failed
    lookup reads ``col("age")./home/<name>/.../_internal.cpython-313-darwin.so:
    lookup_by_table_and_hash()``: the reader's home directory, published into
    every log the error reaches, in the one line that says which call failed.
    The path is the record's ``<plugin>`` stand-in here as it is in the
    artifact (``without_plugin_library_paths``), and the symbol -- the part that
    names the lookup -- is kept. Only a message that carries a path is
    rewritten, and under ``AF_ERROR_MODE=off`` none is: that setting hands the
    engine's exception over exactly as it was raised.
    """
    from gaspatchio.frame.lowering._polars.rendering import (  # noqa: PLC0415 — import cycle
        without_plugin_library_paths,
    )

    if len(error.args) != 1 or not isinstance(error.args[0], str):
        return
    scrubbed = without_plugin_library_paths(error.args[0])
    if scrubbed != error.args[0]:
        error.args = (scrubbed,)


def _diagnose_frame_error(frame: ActuarialFrame, e: Exception) -> None:
    """Route one frame error to the tier and the panel it has earned."""
    # Skip if already processed (any kind of processing)
    if any(
        hasattr(e, attr)
        for attr in [
            "_enhanced_processed",
            "_basic_formatted",
            "_column_attributed",
            "enhanced_error",
            "_dispatch_enhanced",
        ]
    ):
        raise e

    # Check if we should use enhanced error handling
    error_mode = get_error_mode()

    # AF_ERROR_MODE wins: under `off` the original exception is re-raised
    # before any frame-side condition below is consulted.
    if error_mode == _ERROR_MODE_OFF:
        raise e

    # Handle ValidationError with enhanced formatting
    if isinstance(e, ValidationError) and error_mode in _ENHANCING_ERROR_MODES:
        return _handle_validation_error(frame, e)

    # Handle AttributeError with enhanced formatting
    if isinstance(e, AttributeError) and error_mode in _ENHANCING_ERROR_MODES:
        return _handle_attribute_error(frame, e)

    # Whether the model ran under `--mode debug` (the trace decorator sets
    # it) and the frame's own mode: neither is public, and frame/base.py,
    # which hands its own failures to this module, is where both are kept.
    traced_run = frame._traced_run  # noqa: SLF001 -- see above
    debug_frame = frame._mode == "debug"  # noqa: SLF001 -- see above

    # Early exit for production mode - just re-raise
    if not (traced_run or debug_frame or error_mode in _ENHANCING_ERROR_MODES):
        raise e

    # A name polars could not resolve takes the did-you-mean route before
    # anything else, because the frame's own column list answers it better
    # than any replay can: the calculation that named a column which is not
    # there has no healthy version to walk back to. One question decides it
    # (``_is_column_reference_compilation_error``) and the tier decides which
    # panel builds it. Every other resolution-time failure -- a plugin
    # refusing the dtypes it was handed, an arithmetic clash, an ambiguous
    # supertype -- falls through to the one diagnosis below, which names the
    # failing column instead of printing a general list of things to check.
    if (
        _is_column_reference_compilation_error(e)
        and error_mode in _ENHANCING_ERROR_MODES
    ):
        logger.debug("Unresolved column reference, routing to the column handler")
        if traced_run:
            return _handle_compilation_error_enhanced(frame, e)
        return _handle_basic_column_error(frame, e)

    # The verbose diagnosis panel is the traced run's tier. Every calculation
    # now carries a source span, traced or not, so the tier is no longer a
    # question of which records hold metadata — it is a question of whether
    # the user asked for a traced run (`--mode debug` routes the model
    # function through the trace decorator, which sets `_traced_run`). The
    # default path keeps the terse attribution block. Both tiers run the one
    # search, `search_collect_failure`; they differ in how a name is drawn.
    if traced_run and error_mode in _ENHANCING_ERROR_MODES:
        _diagnose_traced_run(frame, e)
    else:
        # Collect-time column attribution (#39): raises with the column name
        # appended when a recorded assignment reproduces the error, else
        # returns.
        _attribute_collect_error(frame, e)

    # Fall back to basic column error formatting for column-related errors.
    # _handle_basic_column_error always raises, so nothing returns from here.
    return _handle_basic_column_error(frame, e)


# Where every value in the attribution block starts, counted from the left
# margin: the two spaces of block indent plus the widest label, measured
# off that label rather than typed as a number. A formula wrapped over
# several lines is padded to it, so the block stays one column rather than
# the continuation lines breaking out to the margin and reading as if the
# message had ended.
_BLOCK_GUTTER = " " * len("  Failing column: ")

# What the `Defined as` line is called when there is no as-written formula
# to quote and the engine's lowering is printed instead. Three different
# absences reach it — a column minted through a door no statement of the
# author's defines (a batch call, a rename, a join, the projection
# timeline), a statement with no single written right-hand side (an
# augmented assignment, a tuple target), and a statement whose source could
# not be retrieved at all (stdin, `exec`, `compile('<string>')`, a bare
# REPL) — and the label claims none of them, because the record cannot
# presently tell them apart. What it does claim is the only thing that
# matters to a reader about to go looking for the line: that what follows
# is the engine's form, not theirs.
_LOWERED_LABEL = "Defined as (lowered; as-written formula not recorded):"


def _attribution_text(
    attribution: CalculationRecord | AmbiguousAttribution,
    frame: ActuarialFrame,
    exception: BaseException,
    last_good: pl.DataFrame | None = None,
) -> str:
    """Render what the replay found as the text appended to a collect-time error.

    A named calculation gets the block, with what the frame's graph says
    about it; a refusal gets one line. Every delivery of a block or a line
    -- the default path, the panic door, and the traced run's refusal --
    renders through here, so the outcomes are rendered once and read the
    same on every path. ``last_good`` -- the frame the named calculation was
    applied to -- is where a list kernel's refusal finds its policy
    (``policy_line``).
    """
    if isinstance(attribution, AmbiguousAttribution):
        return _refusal_line(attribution)
    return _attribution_block(
        attribution,
        graph_facts(frame, attribution),
        diagnosis=str(exception),
        policy=policy_line(attribution, last_good, exception),
    )


def _rendered_attribution(
    attribution: CalculationRecord | AmbiguousAttribution,
    frame: ActuarialFrame,
    exception: BaseException,
    last_good: pl.DataFrame | None = None,
) -> str | None:
    """Return the attribution's text, or ``None`` when rendering it raised.

    The one guard on the rendering path. The finder's replay is guarded by
    ``_replayable``; the text that follows it was not -- the block reads
    the graph's ``_as_written`` for its ``Defined as`` line, the refusal
    formats a span per record -- and a renderer that raised REPLACED the
    user's error with its own, the original demoted to ``__context__``.
    A rendering failure now degrades to today's output for an unattributed
    error: the caller re-raises the message it was handed, with no block
    or line appended and nothing chained to it. The block is dropped whole
    rather than reprinted under the lowered label, because that label
    claims the as-written formula was not recorded, and it was. Only an
    ``Exception`` is consumed; an interrupt propagates as it always did.

    The block's two graph questions sit inside this guard as well, and each
    is guarded on its own besides (``graph_facts``): a question the graph
    cannot answer costs its line, and the block still prints.
    """
    try:
        return _attribution_text(attribution, frame, exception, last_good)
    except Exception as render_error:  # noqa: BLE001 -- never make the error worse
        logger.debug(
            f"Attribution rendering failed ({render_error!r}); "
            "re-raising the original error without it"
        )
        return None


def _refusal_line(attribution: AmbiguousAttribution) -> str:
    """Render the one line printed when the replay declines to name a column.

    The sentence says what is true and no more: this many definitions
    reproduce the failure's leading line under replay, so none is named as
    the one that failed. The definitions are listed as reproducing -- one
    of them may be sound in the plan the user collected, healed at run
    time by a later structural operation, and the replay cannot tell which.
    It gives no advice of its own, and it is one line so that a refusal
    reads as one fact rather than as a diagnosis.

    Nothing this line says can move the advice printed beneath it.
    ``suggestions.py`` chooses a family from the exception's class, the
    failing column's lowering and the operand dtypes the graph holds, and
    reads no part of a message for any class this line can accompany, so
    the advice is the same whether this line is appended or not. It does
    still parse one string -- a missing column's NAME, in
    ``_extract_column_name`` -- and that branch is out of this line's reach
    by class: a ``ColumnNotFoundError`` is not admitted at the one call
    site, so no attribution of one is ever refused here. The wording stays
    clear of ``cast``, ``date``, ``time``, ``null``, ``missing``, ``path``
    and ``lengths`` all the same, because a refusal that borrows diagnostic
    vocabulary it is not entitled to reads as a diagnosis -- not because
    anything downstream reads it. The file paths it quotes are the user's,
    exactly as the ``At:`` line's are.
    """
    listed = ", ".join(
        f"{record.column!r} at {record.source.file}:{record.source.line}"
        if record.source is not None
        else repr(record.column)
        for record in attribution.reproducing
    )
    return (
        f"\n\n  Not attributed: {len(attribution.reproducing)} definitions reproduce "
        f"this failure's leading line under replay ({listed}), so none is named "
        "as the one that failed."
    )


def _attribution_block(
    record: CalculationRecord,
    facts: GraphFacts | None = None,
    diagnosis: str = "",
    policy: str | None = None,
) -> str:
    """Render the failing calculation as the block appended to an error (#39).

    Names the column, the formula that defines it, and — whenever the
    calculation's source span resolved — the file and line of the statement
    that defined it. The span is what the retiring machinery could only
    offer on traced runs; every recorded calculation carries one now, so
    the default path reports a location too.

    With ``facts`` -- what the frame's graph says about the calculation --
    two more lines follow. ``Blocks:`` names what is downstream of the
    failing definition, capped at four names with a count of the rest, and
    says ``nothing downstream`` when the walk finds nothing, so that the
    line's absence means exactly one thing: the graph could not answer.
    ``Reading:`` names the definitions the formula read with the dtype the
    graph holds for each, and is left out when ``diagnosis`` -- the
    failure's own text -- already quotes every operand, which polars' dtype
    refusal does and a jagged-list clash does not.

    Where the graph could not name a column's type at all, both go quiet
    and a ``Graph:`` line carries the refusal instead, on the same rule the
    verbose panel uses (``FriendlyErrorFormatter._graph_lines``): a block
    two lines poorer on a fixed-width ``Array`` reads as a block that knows
    less about arrays, when what it has is a refusal ending in the cast
    that would carry the column.

    With ``policy`` -- the policy a list kernel refused, found in the frame
    (``policy_line``) -- a ``Policy:`` line follows the location.
    """
    block = f"\n\n  Failing column: {record.column!r}\n  {_defined_as_line(record)}"
    if record.source is not None:
        block += f"\n  At:             {record.source.file}:{record.source.line}"
    if policy is not None:
        block += f"\n  Policy:         {policy}"
    if facts is None:
        return block
    said = False
    if facts.blocks is not None:
        block += f"\n  Blocks:         {blocks_text(facts.blocks)}"
        said = True
    if facts.reading is not None and not operands_already_named(
        diagnosis, facts.reading
    ):
        block += f"\n  Reading:        {reading_text(facts.reading)}"
        said = True
    if not said and facts.unnamed is not None:
        block += f"\n  Graph:          {facts.unnamed}"
    return block


def _defined_as_line(record: CalculationRecord) -> str:
    """Render the block's `Defined as` line for one recorded calculation.

    The record holds two renderings of the same calculation: the expression
    the author typed and the engine's lowering of it (``expr``). This
    prints the first, because the reader's next move is to open the file
    and edit that line, and ``af.product_code * af.sum_assured`` is the
    text they will find there — ``[(col("product_code")) *
    (col("sum_assured"))]`` has to be reversed before it can be searched
    for.

    Which text counts as the first is not a question this line answers for
    itself. ``graph_builder._as_written`` already answers it for the
    exported ``formula``, and answers it by refusing: a column minted
    through the batch door, a rename, a join or the projection timeline has
    a statement, but that statement's right-hand side is the whole call,
    and "reporting it against one column would show a reviewer text that
    does not compute the number beside it". An error message that quoted
    what the artifact refuses to publish would be the same substitution
    this line exists to forbid, pointing the other way — so the rule is
    read from there rather than restated here, and a reader who compares
    the block against the graph finds the same text under both.

    When no written expression was recorded the lowered form is still worth
    printing, and the label says so rather than letting it pass for the
    author's own text. The caveat leads rather than trails the expression
    on purpose: a long lowering would push a trailing caveat past the
    reader's terminal width, which is exactly where the misreading it
    exists to prevent would happen. Either rendering can arrive with
    newlines in it — a wrapped formula as the author wrapped it, a lowering
    of a struct — so both are padded to the block's own column.
    """
    from gaspatchio.frame.graph.graph_builder import (  # noqa: PLC0415 — import cycle
        _as_written,
    )

    written = _as_written(record)
    line = (
        f"{_LOWERED_LABEL} {_rendered(record.expr)}"
        if written is None
        else f"Defined as:     {written}"
    )
    return line.replace("\n", f"\n{_BLOCK_GUTTER}")


def _attribute_collect_error(frame: ActuarialFrame, e: Exception) -> None:
    """Name the failing column in a collect-time error, or return (#39).

    Outside traced debug runs this is the whole diagnosis: replay names the
    calculation, and the original exception is re-raised with its column,
    expression and source location appended. When replay finds nothing
    certain this returns and the caller's fallback chain handles the error
    untouched; when it finds two definitions that both reproduce the
    failure, the error is re-raised with one line saying so and no column
    named (``_refusal_line``). A rendering that raises returns the same
    way an unattributed error does (``_rendered_attribution``).
    """
    # An exception the enhanced/basic machinery already rewrote must not be
    # decorated a second time (nor pay a second replay) — the enhanced
    # path's own raise is swallowed by its surrounding except, so control
    # can reach here with the message already rewritten.
    if any(
        hasattr(e, attr)
        for attr in ("_enhanced_processed", "_basic_formatted", "enhanced_error")
    ):
        return

    # Attribution replay is enhanced-tier machinery: AF_ERROR_MODE=off or
    # =basic is an explicit opt-out that a debug-mode frame must not
    # override.
    if get_error_mode() not in _ENHANCING_ERROR_MODES:
        return

    attribution, last_good = boundary.search_collect_failure(frame, e)
    if attribution is None:
        return
    _deliver_attribution(frame, e, attribution, last_good)


def _deliver_attribution(
    frame: ActuarialFrame,
    e: Exception,
    attribution: CalculationRecord | AmbiguousAttribution,
    last_good: pl.DataFrame | None = None,
) -> None:
    """Append what the replay found to ``e`` and raise it; return if it will not render.

    The one delivery for a block or a refusal line, whichever path found
    it. A rendering that raises leaves ``e`` as it was handed in and
    returns, so the caller's fallback chain delivers the original text
    (``_rendered_attribution``).
    """
    text = _rendered_attribution(attribution, frame, e, last_good)
    if text is None:
        return
    e.args = (f"{e}{text}",)
    # Processed-marker idiom used throughout this module (_basic_formatted,
    # _enhanced_processed): prevents double-decoration on re-entry.
    attach(e, _column_attributed=True)
    raise e


def _diagnose_traced_run(frame: ActuarialFrame, e: Exception) -> None:
    """Diagnose a traced run's collect failure through the one finder.

    The traced run's tier is the verbose panel, and it used to be built
    from a finder of its own -- the base ``ErrorBoundaryFinder``:
    class-only, no leading-line check, no ambiguity pass, not admitted by
    the tuple, over the live window alone -- so the same model answered
    two ways depending on a flag. The search is ``search_collect_failure``'s
    now, the one the default block runs. A record gets the panel, with the
    graph's two facts on it; a refusal is delivered as the one line the
    default path prints, through the same renderer; nothing found returns,
    and the caller's fallback chain runs. A panel that cannot be built
    degrades to the terse block rather than to a second search.
    """
    attribution, last_good = boundary.search_collect_failure(frame, e)
    if attribution is None:
        if getattr(frame, "_verbose", False):
            logger.debug("Enhanced error handling: replay attributed no calculation")
        return
    if isinstance(attribution, AmbiguousAttribution) or last_good is None:
        _deliver_attribution(frame, e, attribution)
        return
    if _traced_panel(frame, e, attribution, last_good):
        raise e
    _deliver_attribution(frame, e, attribution, last_good)


def _traced_panel(
    frame: ActuarialFrame,
    e: Exception,
    record: CalculationRecord,
    last_good: pl.DataFrame,
) -> bool:
    """Write the traced run's panel onto ``e``; ``False`` when it could not be built.

    The panel is ``FriendlyErrorFormatter``'s: the record, the state the
    calculation was applied to, the advice the router chose, and the
    graph's two facts (``graph_facts``, each question guarded on its own).
    The graph is asked once and its answer is handed to both -- the router
    reads the operand dtypes off it, the panel prints them -- so the two
    cannot disagree about what the failing formula read.
    """
    try:
        facts = graph_facts(frame, record)
        suggestions = ErrorSuggestionEngine().suggest_fixes(
            e, record, list(last_good.columns), facts
        )
        formatter = FriendlyErrorFormatter(
            record=record,
            exception=e,
            last_good_df=last_good,
            suggestions=suggestions,
            facts=facts,
        )
        enhanced_msg = formatter.format_error()
        llm_context = formatter.format_for_llm()
    except Exception as panel_error:  # noqa: BLE001 -- the panel degrades to the block
        logger.debug(
            f"Traced-run panel could not be built ({type(panel_error).__name__}); "
            "delivering the block instead"
        )
        return False
    if getattr(frame, "_verbose", False):
        logger.debug(f"Enhanced error handling applied: {record.column!r}")
    # The original exception is modified rather than replaced, so its type
    # survives while its message becomes the panel; the marker prevents a
    # second pass over it.
    e.args = (enhanced_msg,)
    attach(e, llm_context=llm_context, _enhanced_processed=True)
    return True


def _handle_plan_lowering_panic(
    frame: ActuarialFrame,
    panic: BaseException,
) -> NoReturn:
    """Convert an attributed schema-derivation panic into a SchemaError (#54).

    A schema mismatch inside a ``when().then()`` branch fails during IR plan
    lowering, where polars panics instead of raising — pyo3's
    ``PanicException`` is a ``BaseException``, so it bypasses both
    ``except Exception`` at the collect boundary and the #39 attribution
    that names the failing column. This is the dedicated boundary for that
    escape: when the panic is the known schema-derivation failure AND replay
    attributes it to a recorded assignment, it is re-raised as a catchable
    ``SchemaError`` carrying the #39 attribution block, chained to the
    original panic. A panic that replay reproduces from two definitions is
    converted the same way — reproduction is what earns the conversion —
    and carries the one-line refusal instead of the block.

    Everything else re-raises untouched: non-panic ``BaseException``s
    (interrupts), panics of any other origin, the AF_ERROR_MODE=off/basic
    opt-out, panics attribution cannot reproduce, and panics whose
    attribution cannot be rendered (``_rendered_attribution``) — per the
    fallback contract, an unattributed error passes through rather than
    being rewritten into something that merely looks diagnosed, and a
    ``SchemaError`` with nothing to carry would be that rewrite.
    """
    if not boundary.is_plan_lowering_panic(panic):
        raise panic

    if get_error_mode() not in _ENHANCING_ERROR_MODES:
        raise panic

    attribution = boundary.search_collect_failure(frame, panic).attribution
    text = (
        None
        if attribution is None
        else _rendered_attribution(attribution, frame, panic)
    )
    if text is None:
        raise panic
    attributed = pl.exceptions.SchemaError(f"{panic}{text}")
    # Processed-marker idiom used throughout this module: prevents
    # double-decoration if the converted error re-enters a handler.
    attach(attributed, _column_attributed=True)
    raise attributed from panic


# Backward compatibility alias
_handle_execution_error = _handle_frame_error


def _handle_basic_column_error(frame: ActuarialFrame, e: Exception) -> NoReturn:
    """Handle basic column errors with similarity suggestions (fallback method)."""
    # Skip if already enhanced
    if hasattr(e, "enhanced_error"):
        raise e

    error_msg = str(e)
    error_msg_str = str(error_msg) if error_msg is not None else ""

    missing_col: str | None = None

    # Attempt extraction only if it's a known Polars error type or the message
    # strongly suggests a column issue
    if isinstance(e, pl.exceptions.ColumnNotFoundError) or (
        isinstance(e, Exception)
        and (
            "ColumnNotFoundError" in error_msg_str
            or "not found" in error_msg_str
            or "unable to find column" in error_msg_str
            or "MissingField" in error_msg_str
        )
    ):
        missing_col = _extract_missing_column_robust(error_msg_str)

        # Fallback only if primary extraction failed but context suggests it
        # *should* be there
        if not missing_col and isinstance(e, pl.exceptions.ColumnNotFoundError):
            match = re.search(r"column: \\\"(.*?)\\\" not found", error_msg_str)
            if match:
                missing_col = match.group(1)

    # If a missing column *was* identified, format the error
    if missing_col:
        # The raise that delivers the message has to happen OUTSIDE the try
        # below. Raised inside, it was caught by this function's own fallback
        # handler, which then logged that formatting had failed -- on every
        # success. The user's message was right either way (the fallback
        # re-raises the same object, already rewritten), but a debug session
        # was told the opposite of what happened. Same defect the enhanced
        # path's `panel_built` flag above repairs; the repair here is a
        # different shape -- no flag, because both branches deliver the same
        # object, so a flag would be an unread variable to explain.
        try:
            # Format the message but modify the original exception
            formatted_msg = _format_column_message(frame, missing_col, error_msg_str)
            e.args = (formatted_msg,)
            attach(e, _basic_formatted=True)
            if getattr(frame, "_verbose", False):
                logger.trace(f"Column error formatted: {missing_col}")
        except Exception as format_err:
            # A genuine formatting failure: say so, and deliver the original
            # message unrewritten -- chained to the formatter's own error, so
            # the cause travels on the object a caller catches and not only in
            # a log line a sink level can filter away.
            logger.debug(f"Failed to format column error: {format_err}")
            raise e from format_err
        raise e

    # If no missing column identified, just re-raise
    if getattr(frame, "_verbose", False):
        logger.trace(f"Execution failed: {error_msg_str}")
    raise e


# What polars prints when it stopped while still RESOLVING the plan, rather
# than while executing it. Any one of the three is the whole of that test:
# ``PLAN_DUMP_BOUNDARY`` heads the dump (spelled once, in ``constants.py``,
# where its readers take it from), ``FAILED HERE`` marks the node inside it,
# and ``query optimization`` is the older spelling. The distinction is what
# the missing-column route turns on -- a name polars could not resolve is a
# name the user can be shown alternatives for, while a failure raised after
# the plan resolved is a computation that went wrong on real values, which
# the attribution block diagnoses far better.
_PLAN_RESOLUTION_MARKERS = (PLAN_DUMP_BOUNDARY, "FAILED HERE", "query optimization")

# The look-alike catch: how a failure that is NOT polars' own
# ``ColumnNotFoundError`` says it could not find a column. Reached only by a
# class the marker above lets through, which today means a plugin's own
# ``ComputeError`` raised while polars was deriving the plugin's output
# schema. No first-party plugin message contains any of these phrases and no
# shape built through the public API reaches them; they are kept for a
# third-party plugin that words its refusal that way, and they are the only
# words this predicate reads.
_MISSING_COLUMN_PHRASES = (
    "column not found",
    "ColumnNotFoundError",
    "no column named",
    "unable to find column",
)


def _is_column_reference_compilation_error(e: Exception) -> bool:
    """Return whether polars refused this while resolving a column name.

    The one question the missing-column route turns on, asked in one place.
    It used to be two: a "compilation error" test over eleven phrases and a
    "column reference" test over four more, both consulted in sequence on
    every failure, each free to be reworded without the other. What they
    decided between them is what this decides, in the order the facts
    deserve -- the plan-resolution marker first, because a failure raised
    after the plan resolved belongs to the attribution block whatever it
    says about columns, then the exception's CLASS, which is polars' own
    structural answer to "is this a missing column", and only then, for a
    class that is not it, the wording.

    Nine of the fifteen phrases went with the merge, leaving the seven
    strings the two constants above hold. Four (``failed during query
    optimization``, ``unable to determine output schema``, ``cannot resolve
    expression type``, ``type inference failed``) appear nowhere in the
    polars build this framework pins. Three (``got invalid or ambiguous
    dtypes``, ``type coercion``, ``schema mismatch``) name a failure that is
    not a missing column. ``FAILED HERE RESOLVING`` restates ``FAILED HERE``,
    which is kept above. ``Resolved plan`` is the one that narrows rather
    than restates: it is BROADER than the kept ``PLAN_DUMP_BOUNDARY``, so a
    message heading its dump with the short spelling alone would be refused
    here where it was admitted before. Empty on this build -- of forty
    failure shapes driven, twenty-two carry ``Resolved plan`` and all
    twenty-two carry the full header.
    """
    error_str = str(e)
    if not any(marker in error_str for marker in _PLAN_RESOLUTION_MARKERS):
        return False
    if isinstance(e, pl.exceptions.ColumnNotFoundError):
        return True
    return any(phrase in error_str for phrase in _MISSING_COLUMN_PHRASES)


def _handle_compilation_error_enhanced(frame: ActuarialFrame, e: Exception) -> NoReturn:
    """
    Handle compilation errors with enhanced context using operation replay.

    This function uses CompilationErrorFinder to replay operations and find
    the exact failing operation with full context.
    """
    # Whether the finder actually built a panel. The raise that delivers it
    # has to happen OUTSIDE the try below, and so does the handover to basic
    # formatting: raised inside, each was caught by this function's own
    # fallback handler, which then logged that the finder had failed -- on
    # every success, with the whole panel pasted after the claim. The user's
    # message was right either way (the fallback re-raises the same object,
    # already rewritten), but a debug session was told the opposite of what
    # happened. Third path with this defect, after the traced-run tier's
    # `panel_built` flag above and the basic formatter below; the flag is
    # needed here for the reason it is needed there and not there -- the two
    # outcomes deliver differently, one raising and one delegating.
    panel_built = False
    try:
        # Find the failing operation using compilation-aware replay
        finder = compilation_finder.CompilationErrorFinder(frame, e)
        fail_idx, fail_op, last_good_df = finder.find_failing_operation()

        # Replay may decline to name a calculation (an ambiguous
        # multi-column operation) — fall through to basic handling instead.
        if fail_op is not None and last_good_df is not None:
            # Build enhanced error using Pydantic models
            enhanced_error = _build_enhanced_compilation_error(
                exception=e,
                record=fail_op,
                operation_index=fail_idx,
                dataframe=last_good_df,
                total_operations=len(finder.groups),
            )

            # Determine output format based on context
            if _is_interactive_console():
                error_message = enhanced_error.to_console(use_emoji=True)
            else:
                error_message = enhanced_error.to_console(use_emoji=False)

            # Instead of creating a new exception, modify the original
            # This prevents re-wrapping and re-processing
            e.args = (error_message,)  # Update the message

            # Attach structured data for programmatic access, the report's
            # own serialisers as methods of the exception, and the marker
            # that it has been processed
            attach(
                e,
                enhanced_error=enhanced_error,
                llm_context=enhanced_error.to_llm_context(),
                to_json=enhanced_error.to_json,
                to_dict=enhanced_error.to_dict,
                _enhanced_processed=True,
            )

            panel_built = True

    except Exception as finder_error:
        # A genuine finder failure: say so, and deliver the original message
        # unrewritten -- chained to the finder's own error, so the cause
        # travels on the object a caller catches and not only in a log line a
        # sink level can filter away.
        logger.debug(f"Enhanced compilation error finder failed: {finder_error}")
        raise e from finder_error

    if panel_built:
        raise e
    # Fallback to basic handling if we can't find the operation. Outside the
    # try as well: the basic handler's own delivering raise used to land in
    # the fallback above, which logged the handover as a finder failure.
    return _handle_basic_column_error(frame, e)


def _is_interactive_console() -> bool:
    """Detect if running in an interactive console."""
    # Check if stdout is a terminal
    if not hasattr(sys.stdout, "isatty"):
        return False

    if not sys.stdout.isatty():
        return False

    # A terminal under CI is not a reader at a console
    ci_vars = ["CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", "GITLAB_CI"]
    return not any(os.environ.get(var) for var in ci_vars)


def _build_enhanced_compilation_error(
    exception: Exception,
    record: CalculationRecord,
    operation_index: int,
    dataframe: pl.DataFrame,
    total_operations: int,
) -> EnhancedError:
    """Build structured enhanced error from components."""
    # Determine error type
    error_type = _classify_error_type(exception)

    # Extract missing column if applicable
    missing_column = None
    if error_type == ErrorType.COLUMN_NOT_FOUND:
        missing_column = _extract_missing_column_robust(str(exception))

    # Build metadata
    metadata = ErrorMetadata(
        error_type=error_type,
        error_category="compilation",
        original_message=str(exception),
    )

    # Build operation context
    operation_context = OperationContext(
        index=operation_index,
        total_operations=total_operations,
        alias=record.column,
        expression=_rendered(record.expr),
        source=_source_location(record),
        expected_dtype=str(record.dtype) if record.dtype is not None else None,
    )

    # Build dataframe context
    columns = [
        ColumnInfo(name=col, dtype=str(dtype))
        for col, dtype in dataframe.schema.items()
    ]

    dataframe_context = DataFrameContext(
        shape=dataframe.shape,
        columns=columns,
        preview_rows=dataframe.limit(5).to_dicts() if not dataframe.is_empty() else [],
    )

    # Generate suggestions
    suggestions = _generate_compilation_suggestions(
        error_type=error_type,
        missing_column=missing_column,
        available_columns=[col.name for col in columns],
        record=record,
    )

    # Build complete error
    return EnhancedError(
        metadata=metadata,
        operation=operation_context,
        dataframe=dataframe_context,
        suggestions=suggestions,
        additional_context={
            "missing_column": missing_column,
            "execution_mode": "compilation",
        },
    )


def _classify_error_type(exception: Exception) -> ErrorType:
    """Name the category of a failure from its class.

    "Which kind of failure is this" is a question polars already answers
    structurally, with the exception it chose to raise. It used to be asked
    of the message instead -- ``"type mismatch" in error_str`` and three
    more -- which reads the failure's own words back to it and mistakes any
    sentence carrying them for the category: polars' own
    ``column datatype mismatch`` contains ``type mismatch``, and ``schema``
    answered ``SCHEMA_CONFLICT`` for any message carrying the word, wherever
    it came from. Measured over forty-two failure shapes: twenty-three
    carried a plan dump and none of those dumps contained the word, and the
    four messages that did took it from polars' own diagnosis -- a concat of
    clashing schemas, a scan handed a schema of the wrong width, and two
    ``map_batches`` shapes whose output did not match the schema polars had
    -- where it describes the failure rather than naming a category.

    ``TYPE_MISMATCH`` has no producer now. It was the answer only the
    substring test gave, and the class that would earn it --
    ``InvalidOperationError`` -- is the one polars raises for an arithmetic
    refusal, which reaches the attribution block rather than this report.
    The member stays on the enum, which is public.
    """
    if isinstance(exception, pl.exceptions.ColumnNotFoundError):
        return ErrorType.COLUMN_NOT_FOUND
    if isinstance(exception, pl.exceptions.SchemaError):
        return ErrorType.SCHEMA_CONFLICT
    if isinstance(exception, pl.exceptions.InvalidOperationError):
        return ErrorType.INVALID_OPERATION
    return ErrorType.UNKNOWN


def _source_location(record: CalculationRecord) -> SourceLocation:
    """Render a calculation's source span as the model the reports consume.

    A span that could not be resolved (stdin, an ``exec``-compiled snippet,
    a bare REPL) degrades to a placeholder rather than dropping the whole
    enhanced report: the column and its expression are still worth showing.
    """
    if record.source is None:
        return SourceLocation(
            file_path="<source unavailable>",
            line_number=0,
            function_name=None,
            source_line="",
        )
    return SourceLocation(
        file_path=record.source.file,
        line_number=record.source.line,
        function_name=record.source.function,
        source_line=record.source.statement,
    )


def _generate_compilation_suggestions(
    error_type: ErrorType,
    missing_column: str | None,
    available_columns: list[str],
    record: CalculationRecord,
) -> list[Suggestion]:
    """Generate suggestions for compilation errors."""
    suggestions = []

    if error_type == ErrorType.COLUMN_NOT_FOUND and missing_column:
        # Find similar columns
        similar_cols = _find_similar_columns(missing_column, available_columns)

        suggestions.extend(
            Suggestion(
                text=f"Did you mean '{col}'?",
                type=SuggestionType.TYPO_FIX,
                relevance_score=0.9,
                code_example=f"{record.column} = pl.col('{col}')",
            )
            for col in similar_cols[:3]  # Top 3 suggestions
        )

        # Suggest checking available columns
        suggestions.append(
            Suggestion(
                text="Use af.columns to list all available columns",
                type=SuggestionType.DOCUMENTATION,
                relevance_score=0.7,
            ),
        )

        # Check if this might be created by earlier operations
        if record.source is not None and record.source.line > _TOO_EARLY_TO_LOOK_BACK:
            suggestions.append(
                Suggestion(
                    text=(
                        f"Check operations before line {record.source.line} "
                        "which might create this column"
                    ),
                    type=SuggestionType.DOCUMENTATION,
                    relevance_score=0.6,
                ),
            )

    return suggestions


def _handle_validation_error(frame: ActuarialFrame, e: ValidationError) -> NoReturn:
    """Handle validation errors with enhanced formatting."""
    # Create formatter and generate enhanced message
    formatter = ValidationErrorFormatter(e, frame)
    enhanced_msg = formatter.format_error()
    llm_context = formatter.format_for_llm()

    # Update the exception with enhanced message
    e.args = (enhanced_msg,)
    attach(e, llm_context=llm_context, _enhanced_processed=True)

    # Re-raise the enhanced exception
    raise e


def _handle_attribute_error(frame: ActuarialFrame, e: AttributeError) -> NoReturn:
    """Handle attribute errors with enhanced formatting."""
    # Get source location if not already attached
    source_location = getattr(e, "source_location", None)

    # Create formatter and generate enhanced message
    formatter = AttributeErrorFormatter(e, source_location, frame)
    enhanced_msg = formatter.format_error()
    llm_context = formatter.format_for_llm()

    # Update the exception with enhanced message
    e.args = (enhanced_msg,)
    attach(e, llm_context=llm_context, _enhanced_processed=True)

    # Re-raise the enhanced exception
    raise e


# What the API reference documents from this module.
__all__ = ["PerformanceWarning"]
