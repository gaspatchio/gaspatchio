# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Error formatting module for creating friendly, actionable error messages.

This module provides the FriendlyErrorFormatter class which converts raw Polars
exceptions into human-readable and LLM-parseable error messages with context,
suggestions, and data previews.
"""

from __future__ import annotations

import builtins
import importlib
import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import polars as pl
from loguru import logger

# A declared dependency of the package, so it is always there to import.
from thefuzz import fuzz

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio.frame.base import ActuarialFrame
    from gaspatchio.frame.calculations import CalculationRecord

    from .validation import ValidationError

from .constants import (
    COMMON_ATTRIBUTES,
    FUZZY_MATCH_THRESHOLD,
    MAX_OPTIONS_LISTED,
    MAX_SUGGESTIONS,
    PLAN_DUMP_BOUNDARY,
    PLAN_DUMP_OMITTED,
    TYPO_LENGTH_SLACK,
    TYPO_MATCH_THRESHOLD,
)
from .models import SourceLocation, source_block
from .policy_locator import policy_line

# How many downstream names the ``Blocks:`` line prints before it counts
# the rest: enough to rank the fix, few enough that a wide model does not
# print a wall under one error.
_BLOCKS_NAMED = 4


class Operand(NamedTuple):
    """One definition a failing formula read, as the graph holds it."""

    node: str
    column: str
    dtype: str


@dataclass(frozen=True, slots=True)
class GraphFacts:
    """What the calculation graph says about one failing calculation.

    ``blocks`` is everything downstream of the failing definition -- the
    columns this one failure means cannot be produced -- in the order the
    model built them, the failing node itself left out. ``reading`` is the
    definitions its formula read, each with the dtype the graph holds for
    it (``unknown`` where the graph could not resolve one, never guessed).
    Either is ``None`` when the graph could not answer that question, which
    is a different fact from an empty answer and is kept distinct: an empty
    ``blocks`` prints as nothing downstream, a ``None`` prints no line.

    ``projected`` is whether the frame the failure came from carries a
    projection schedule at all. It is not the graph's answer but the
    frame's, and it rides here because this is what the advice router is
    handed: a family that would otherwise offer the projection as a cause
    to check can withhold it where the answer is knowably no. ``None``
    means nobody asked, which costs the refinement rather than the advice.

    ``unnamed`` is the graph's own refusal when it could not name a
    column's type at all, carried rather than swallowed so the panel can
    say why its ``Blocks:`` and ``Reading:`` lines are missing and what to
    do about it. ``None`` where the graph answered, or where it declined
    for some reason that carries no remedy for the reader.
    """

    blocks: tuple[str, ...] | None
    reading: tuple[Operand, ...] | None
    projected: bool | None = None
    unnamed: str | None = None


class _GraphAnswer(NamedTuple):
    """One question put to the graph: its answer, and its refusal if it declined."""

    answer: object | None
    refusal: BaseException | None


def _downstream_of(frame: ActuarialFrame, node: str) -> _GraphAnswer:
    """Return every node ahead of ``node``, or the refusal that stopped the question."""
    try:
        affected = frame.graph.affected(node)
    except Exception as refusal:  # noqa: BLE001 -- one line lost, the error kept
        logger.debug(
            f"The graph could not say what {node!r} blocks ({refusal!r}); "
            "leaving that line out"
        )
        return _GraphAnswer(None, refusal)
    return _GraphAnswer(tuple(reached for reached in affected if reached != node), None)


def _read_by(frame: ActuarialFrame, node: str) -> _GraphAnswer:
    """Return what ``node``'s formula read, or the refusal that stopped the question."""
    try:
        nodes = frame.graph._graph.nodes  # noqa: SLF001 -- the accessor's own fold
        reading = tuple(
            Operand(
                node=read,
                column=nodes[read].data.column or read,
                dtype=nodes[read].data.dtype,
            )
            for read in frame.graph.precedents(node)
        )
    except Exception as refusal:  # noqa: BLE001 -- one line lost, the error kept
        logger.debug(
            f"The graph could not say what {node!r} read ({refusal!r}); "
            "leaving that line out"
        )
        return _GraphAnswer(None, refusal)
    return _GraphAnswer(reading, None)


def _unnameable(concerned: frozenset[str], *asked: _GraphAnswer) -> str | None:
    """Return the refusal to print when the graph has no name for a column's type.

    ``UnmappedDtypeError`` is the one refusal the graph raises that the
    reader can act on: it names the column, says the vocabulary has no
    name for its type, and ends with the cast that carries it. Both
    questions raise the same one on such a frame, so the first is taken
    and the second would only repeat it. Every other refusal stays in the
    debug log, because a reader told "the graph declined" with no move to
    make is worse served than by the silence.

    It is printed only where it is about the failure: the column refused is
    the failing column or one its formula reads (``concerned``). The graph
    folds the whole frame, so a type it cannot name anywhere on it silences
    both questions -- and a ``UInt64`` past ``i64`` in an unrelated column
    put that column's refusal under a list read that failed for its own
    reason, sending the reader to fix a column the failure never touched.
    A refusal naming no column, or another one, stays in the debug log.
    """
    from gaspatchio._dtypes import UnmappedDtypeError  # noqa: PLC0415

    for question in asked:
        refusal = question.refusal
        if isinstance(refusal, UnmappedDtypeError) and refusal.column in concerned:
            return str(refusal)
    return None


def _concerned_columns(record: CalculationRecord) -> frozenset[str]:
    """Return the failing column and the columns its formula reads, by name."""
    try:
        read = record.expr.meta.root_names()
    except Exception as refusal:  # noqa: BLE001 -- the failing column is still known
        logger.debug(f"Could not read {record.column!r}'s operands ({refusal!r})")
        read = []
    return frozenset((record.column, *read))


def graph_facts(frame: ActuarialFrame, record: CalculationRecord) -> GraphFacts:
    """Ask the frame's graph what ``record``'s failure blocks and what it read.

    Two questions to ``af.graph``, each guarded on its own so that one the
    graph cannot answer costs its line and nothing else -- the graph never
    turns one error into two. The graph is folded once, on the first
    question, and cached against the calculation log, so the second question
    and any later ``af.graph`` question on the same frame read the cached
    fold. The node asked about is the record's own definition,
    ``column@ordinal``, so a superseded definition answers for itself rather
    than for the one the frame holds now.

    Two facts come off the frame rather than off the graph. Whether it
    carries a projection schedule is one, asked here because this is where
    the frame is in hand and the router is not given one. The refusal that
    silenced both questions is the other: a frame holding a fixed-width
    ``Array`` has a type the graph's vocabulary cannot name, and that used
    to cost the panel two lines with the reason going only to a debug log
    nobody reading the panel can see.
    """
    node = f"{record.column}@{record.ordinal}"
    blocks = _downstream_of(frame, node)
    reading = _read_by(frame, node)
    return GraphFacts(
        blocks=cast("tuple[str, ...] | None", blocks.answer),
        reading=cast("tuple[Operand, ...] | None", reading.answer),
        projected=getattr(frame, "_projection", None) is not None,
        unnamed=_unnameable(_concerned_columns(record), blocks, reading),
    )


def operands_already_named(diagnosis: str, reading: Sequence[Operand]) -> bool:
    """Return whether the failure's own leading line quotes every operand by name.

    Polars' dtype refusal names both sides (``lhs: column 'product_code',
    rhs: column 'sum_assured'``), and a ``Reading:`` line restating them is
    noise; a jagged-list clash names nothing, and there the line is the
    whole diagnosis. Only the leading line is read -- the line the replay
    itself matches on -- because everything polars appends after it (the
    expression the error occurred in, the plan dump, the context stack)
    quotes every column in the plan and would silence the line always. A
    quoted name is the test, because a bare substring would find ``age``
    inside ``coverage``.
    """
    head = diagnosis.split("\n", 1)[0]
    return bool(reading) and all(
        f"'{operand.column}'" in head or f'"{operand.column}"' in head
        for operand in reading
    )


def blocks_text(blocks: Sequence[str]) -> str:
    """Render the ``Blocks:`` value: up to four names, then a count of the rest."""
    if not blocks:
        return "nothing downstream"
    named = ", ".join(blocks[:_BLOCKS_NAMED])
    rest = len(blocks) - _BLOCKS_NAMED
    return named if rest <= 0 else f"{named} (+{rest} more)"


def reading_text(reading: Sequence[Operand]) -> str:
    """Render the ``Reading:`` value: each node with the dtype the graph holds."""
    return ", ".join(f"{operand.node} ({operand.dtype})" for operand in reading)


class FriendlyErrorFormatter:
    """Format errors for human and LLM consumption."""

    def __init__(
        self,
        record: CalculationRecord,
        exception: Exception,
        last_good_df: pl.DataFrame,
        suggestions: list[str] | None = None,
        facts: GraphFacts | None = None,
    ) -> None:
        """
        Initialize the error formatter.

        Args:
            record: The CalculationRecord replay attributed the failure to
            exception: The original exception
            last_good_df: The last DataFrame that executed successfully
            suggestions: Optional list of fix suggestions
            facts: What the calculation graph says about the failing
                calculation, when it was asked

        """
        self.record = record
        self.exception = exception
        self.last_good_df = last_good_df
        self.suggestions = suggestions or []
        self.facts = facts
        # The policy a list kernel refused, found in the frame the record was
        # applied to: the kernel names no row of its own (policy_locator).
        self.policy = policy_line(record, last_good_df, exception)

    @property
    def _location(self) -> str:
        """Where the failing calculation was written, or a stated absence.

        A calculation whose source span could not be resolved -- one written
        at stdin, in an ``exec``-compiled snippet, or in a bare REPL -- says
        so rather than printing a plausible-looking wrong file and line.
        """
        if self.record.source is None:
            return "(source location not available)"
        return f"{self.record.source.file}:{self.record.source.line}"

    @property
    def _function(self) -> str | None:
        """The scope the failing calculation was written in, when it is known.

        ``None`` for a calculation written at module level, and for one whose
        span could not be resolved at all. Both are reported by leaving the
        line out: naming a scope the calculation was not written in sends the
        reader to the wrong place, and "module level" is a claim rather than
        an absence.
        """
        if self.record.source is None:
            return None
        return self.record.source.function

    @property
    def _statement(self) -> str:
        """The whole statement that defined the failing column.

        Statement-scoped, not line-scoped: a conditional chain wrapped over
        several lines is shown start to end rather than truncated to
        whichever physical line the interpreter happened to be on.
        """
        if self.record.source is None:
            return str(self.record.expr)
        return self.record.source.statement

    def format_error(self) -> str:
        """Create the friendly error message."""
        error_type = type(self.exception).__name__
        error_msg = self._clean_error_message(str(self.exception))

        # Enhanced error with source location
        lines = [
            "─" * 80,
            "❌ Calculation Error",
            "─" * 80,
            "",
            f"📍 Location: {self._location}",
        ]
        if self._function is not None:
            lines.append(f"   Function: {self._function}")
        lines.append(f"   Operation: {self.record.column}")
        if self.policy is not None:
            lines.append(f"   Policy: {self.policy}")
        lines.extend(self._graph_lines())
        lines.extend(
            [
                "",
                "📝 Source Code:",
            ]
        )

        # Plain text: the panel is the exception's message (``source_block``).
        lines.extend(source_block(self._statement))

        lines.extend(
            [
                "",
                "🔴 Error Details:",
                f"   Type: {error_type}",
                f"   Message: {error_msg}",
                "",
            ]
        )

        if self.suggestions:
            lines.extend(
                [
                    "💡 Suggestions:",
                    *[f"   • {suggestion}" for suggestion in self.suggestions[:3]],
                    "",
                ]
            )

        # Simplified data preview
        lines.extend(
            [
                "📊 Calculation State Before Error:",
                "   (This shows the last successful calculation state)",
                self._format_dataframe_preview(self.last_good_df, max_rows=3),
                "",
                "─" * 80,
            ]
        )

        return "\n".join(lines)

    def _graph_lines(self) -> list[str]:
        """Return the panel's ``Blocks:`` and ``Reading:`` lines, on the block's rule.

        Nothing when the graph was not asked; a ``Blocks:`` line whenever it
        answered, saying nothing downstream rather than going quiet; a
        ``Reading:`` line unless the diagnosis already quotes every operand
        (``operands_already_named``).

        Where the graph could not name a column's type at all, both of
        those go quiet and the refusal takes their place. Going quiet with
        no word for it is what a fixed-width ``Array`` column used to do:
        two lines missing from the panel and the reason in a debug log,
        which reads to the user as a panel that simply knows less about
        arrays than about lists. The refusal is the framework's own and
        ends with the cast that carries the column into the vocabulary, so
        printing it is printing the move rather than the shrug.
        """
        if self.facts is None:
            return []
        lines: list[str] = []
        if self.facts.blocks is not None:
            lines.append(f"   Blocks: {blocks_text(self.facts.blocks)}")
        if self.facts.reading is not None and not operands_already_named(
            str(self.exception), self.facts.reading
        ):
            lines.append(f"   Reading: {reading_text(self.facts.reading)}")
        if not lines and self.facts.unnamed is not None:
            lines.append(f"   Graph: {self.facts.unnamed}")
        return lines

    def format_for_llm(self) -> dict[str, Any]:
        """Structured format for LLM consumption.

        ``blocks`` and ``reading`` carry the graph's two facts uncapped and
        as data; each is ``None`` when the graph was not asked or could not
        answer, which is a different fact from an empty list.

        ``unnamed`` says WHY they are both ``None`` where the reason is one
        the reader can act on -- a column whose type the graph's vocabulary
        has no name for. Two nulls and no reason is the same silence the
        panel used to print, in the surface an agent reads.
        """
        source = self.record.source
        facts = self.facts
        return {
            "error_type": "column_calculation_error",
            "operation": {
                "name": self.record.column,
                "expression": str(self.record.expr),
            },
            "error_location": {
                "file": source.file if source is not None else None,
                "line": source.line if source is not None else None,
                "function": self._function,
                "code": self._statement,
            },
            "error_details": {
                "type": type(self.exception).__name__,
                "message": str(self.exception),
                "column_alias": self.record.column,
                "expression": str(self.record.expr),
            },
            "blocks": (
                None if facts is None or facts.blocks is None else list(facts.blocks)
            ),
            "reading": (
                None
                if facts is None or facts.reading is None
                else [operand._asdict() for operand in facts.reading]
            ),
            "unnamed": None if facts is None else facts.unnamed,
            "policy": self.policy,
            "suggestions": self.suggestions,
            "context": self._get_context_info(),
        }

    def _get_context_info(self) -> dict[str, Any]:
        """Get context information, handling both LazyFrame and DataFrame."""
        available_columns = []
        dataframe_shape = [0, 0]

        if self.last_good_df is not None:
            try:
                if isinstance(self.last_good_df, pl.LazyFrame):
                    # For LazyFrame, collect schema and get column names
                    available_columns = list(self.last_good_df.collect_schema().names())
                    # Shape is not available for LazyFrame without collecting
                    dataframe_shape = ["unknown", len(available_columns)]
                else:
                    # For DataFrame, direct access
                    available_columns = list(self.last_good_df.columns)
                    dataframe_shape = list(self.last_good_df.shape)
            except pl.exceptions.PolarsError:
                # A lazy plan whose schema will not resolve has no columns
                # to report
                available_columns = []
                dataframe_shape = [0, 0]

        return {
            "available_columns": available_columns,
            "dataframe_shape": dataframe_shape,
        }

    def _format_dataframe_preview(
        self, df: pl.DataFrame | pl.LazyFrame | None, max_rows: int = 5
    ) -> str:
        """Format a DataFrame preview for display."""
        if df is None:
            return "  <No data available>"

        try:
            # Convert to eager if lazy
            if isinstance(df, pl.LazyFrame):
                df = df.limit(max_rows).collect()

            # Limit rows for preview
            preview_df = df.head(max_rows)

            # Handle wide tables
            preview_df = self._truncate_wide_tables(preview_df)

            # Get string representation and indent
            df_str = str(preview_df)
            lines = df_str.split("\n")
            indented_lines = ["  " + line for line in lines]

            # Add truncation note if necessary
            if len(df) > max_rows:
                indented_lines.append(f"  ... ({len(df) - max_rows} more rows)")

            return "\n".join(indented_lines)

        except pl.exceptions.PolarsError as e:
            # Only a lazy frame runs anything here, and polars reports what
            # stopped it; the panel shows that in the preview's place
            return f"  <Error displaying data: {e}>"

    def _truncate_wide_tables(self, df: pl.DataFrame) -> pl.DataFrame:
        """Truncate tables that are too wide for display."""
        # If we have too many columns, show first few and last few
        max_cols = 8  # Show up to 8 columns in preview

        if len(df.columns) <= max_cols:
            return df

        # Show first 4 and last 4 columns with ellipsis
        first_cols = df.columns[:4]
        last_cols = df.columns[-4:]

        # Create truncated dataframe
        first_part = df.select(first_cols)
        last_part = df.select(last_cols)

        # Add ellipsis column
        ellipsis_df = pl.DataFrame({"...": ["..."] * len(df)})

        # Combine parts
        return pl.concat([first_part, ellipsis_df, last_part], how="horizontal")

    def _clean_error_message(self, message: str) -> str:
        """Render polars' text as the panel's one-line ``Message:`` field.

        Polars often hands over two things joined by a blank line: a
        diagnosis addressed to the reader, then the query plan it failed
        resolving. They are split here on ``PLAN_DUMP_BOUNDARY`` and treated
        as what they are.

        The diagnosis is kept **whole**. It used to share a 117-character
        budget with the dump, which meant the panel cut its own advice
        mid-word -- polars' ``try an explicit cast first`` arrived as ``try
        an expli...``. There is deliberately no budget now: a truncated
        diagnosis is the defect, and the sentence the reader must act on is
        the last thing that should be spent.

        The dump is dropped, not truncated. It is a tree, and this field is
        one line, so any slice of it survives only as a smear of node names
        with the newlines removed -- and the panel already answers the
        question the plan would have: the failing column, the statement that
        defined it, its file and line, and the state before it ran. The
        untouched polars text stays reachable on ``format_for_llm()``, which
        the traced-run handler stamps on the exception before it replaces the
        message, so nothing is destroyed by the omission -- only left out of
        the field it could not be read in.

        Args:
            message: ``str(exception)`` as polars raised it.

        Returns:
            The diagnosis on one line, with a stated omission when a plan
            dump followed it.

        """
        diagnosis, boundary, _dump = message.partition(PLAN_DUMP_BOUNDARY)
        cleaned = " ".join(diagnosis.split())
        if not boundary:
            return cleaned
        return f"{cleaned} {PLAN_DUMP_OMITTED}".strip()


class ValidationErrorFormatter:
    """Format validation errors with context and suggestions."""

    def __init__(
        self, error: ValidationError, frame: ActuarialFrame | None = None
    ) -> None:
        """Initialize the validation error formatter.

        Args:
            error: The ValidationError instance
            frame: Optional ActuarialFrame for additional context

        """
        self.error = error
        self.frame = frame
        self.suggestions: list[str] = []

        # Generate suggestions based on error context
        self._generate_suggestions()

    def format_error(self) -> str:
        """Create the friendly validation error message."""
        lines = [
            "─" * 80,
            "❌ Validation Error",
            "",
        ]

        # Add location if available. The enclosing scope is named only when
        # it is genuinely known -- "module level" is a claim, not an
        # absence, so an unresolved scope omits the line rather than guess.
        if self.error.source_location:
            loc = self.error.source_location
            lines.append(f"📍 Location: {loc.file_path}:{loc.line_number}")
            if loc.function_name is not None:
                lines.append(f"   Function: {loc.function_name}")
            lines.extend(
                [
                    "",
                    "📝 Source Code:",
                ]
            )

            if loc.source_line:
                lines.extend(source_block(loc.source_line))
                lines.append("")

        # Error details
        lines.extend(
            [
                "🔴 Error Details:",
                "   Type: ValidationError",
                f"   Message: {self.error!s}",
            ]
        )

        # Add context information if available
        if self.error.context.provided_value is not None:
            lines.append(f"   Provided Value: {self.error.context.provided_value!r}")

        if self.error.context.parameter_name:
            lines.append(f"   Parameter: {self.error.context.parameter_name}")

        lines.append("")

        # Add suggestions
        if self.suggestions or self.error.context.valid_options:
            lines.append("💡 Did you mean one of these?")

            # Show fuzzy match suggestions first
            lines.extend(
                f"   • {suggestion}"
                for suggestion in self.suggestions[:MAX_SUGGESTIONS]
            )

            # Then show all valid options if available and not too many
            if (
                self.error.context.valid_options
                and len(self.error.context.valid_options) <= MAX_OPTIONS_LISTED
                and not self.suggestions
            ):
                lines.extend(
                    f"   • {option}" for option in self.error.context.valid_options
                )

            lines.append("")

        lines.append("─" * 80)
        return "\n".join(lines)

    def format_for_llm(self) -> dict[str, Any]:
        """Structured format for LLM consumption."""
        result = {
            "error_type": "validation_error",
            "error_details": {
                "type": "ValidationError",
                "message": str(self.error),
            },
            "context": {
                "provided_value": self.error.context.provided_value,
                "valid_options": self.error.context.valid_options,
                "parameter_name": self.error.context.parameter_name,
                "expected_type": str(self.error.context.expected_type)
                if self.error.context.expected_type
                else None,
                "actual_type": str(self.error.context.actual_type)
                if self.error.context.actual_type
                else None,
                "additional_info": self.error.context.additional_info,
            },
            "suggestions": self.suggestions,
        }

        if self.error.source_location:
            loc = self.error.source_location
            result["error_location"] = {
                "file": loc.file_path,
                "line": loc.line_number,
                "function": loc.function_name,
                "code": loc.source_line,
            }

        return result

    def _generate_suggestions(self) -> None:
        """Generate suggestions based on error context."""
        # If we have a provided value and valid options, do fuzzy matching
        if (
            self.error.context.provided_value
            and self.error.context.valid_options
            and isinstance(self.error.context.provided_value, str)
        ):
            self.suggestions = self._suggest_valid_options(
                self.error.context.provided_value, self.error.context.valid_options
            )

    def _suggest_valid_options(
        self, invalid_value: str, valid_options: list[str]
    ) -> list[str]:
        """Find similar valid options using fuzzy matching."""
        if not valid_options:
            return []

        # Calculate similarity scores using different algorithms
        suggestions = []
        seen = set()

        # Try different fuzzy matching algorithms for better results
        algorithms = [
            ("ratio", fuzz.ratio),
            ("partial_ratio", fuzz.partial_ratio),
            ("token_sort_ratio", fuzz.token_sort_ratio),
        ]

        for _, algo_func in algorithms:
            scores = [
                (opt, algo_func(invalid_value.lower(), opt.lower()))
                for opt in valid_options
            ]
            scores.sort(key=lambda x: x[1], reverse=True)

            # Add high-scoring unique matches
            for opt, score in scores:
                if score > FUZZY_MATCH_THRESHOLD and opt not in seen:
                    suggestions.append(opt)
                    seen.add(opt)
                    if len(suggestions) >= MAX_SUGGESTIONS:
                        return suggestions[:MAX_SUGGESTIONS]

        # If we have at least one suggestion, return what we have
        if suggestions:
            return suggestions[:MAX_SUGGESTIONS]

        # Try character-level edits for very close matches
        # This catches single character typos better
        for opt in valid_options:
            # Calculate edit distance manually for single char differences
            if abs(len(invalid_value) - len(opt)) <= TYPO_LENGTH_SLACK:
                # Use token_set_ratio for order-independent matching
                score = fuzz.token_set_ratio(invalid_value.lower(), opt.lower())
                if score > TYPO_MATCH_THRESHOLD:
                    suggestions.append(opt)
                    if len(suggestions) >= MAX_SUGGESTIONS:
                        break

        return suggestions[:MAX_SUGGESTIONS]


# ``COMMON_ATTRIBUTES`` holds two shapes under one name: a module's entry is
# named groups of attribute names ("date_class", "instance_methods", ...),
# and every other entry is a single flat list. The two readers below are
# where each shape is checked before it is used, so the callers get a list
# of attribute names or nothing -- never one shape where they expected the
# other.
_AttributeGroups = dict[str, list[str]]


def _attribute_groups(name: str) -> _AttributeGroups:
    """Return the named attribute groups registered under *name*, if any."""
    entry = COMMON_ATTRIBUTES.get(name)
    if isinstance(entry, dict):
        return cast("_AttributeGroups", entry)
    return {}


def _attribute_list(name: str) -> list[str]:
    """Return the flat list of attribute names under *name*, if any.

    A copy: callers extend and sort what comes back, and the list inside
    ``COMMON_ATTRIBUTES`` is module state shared by every formatter.
    """
    entry = COMMON_ATTRIBUTES.get(name)
    if isinstance(entry, list):
        return list(entry)
    return []


def _named_type(type_name: str) -> object | None:
    """Return the type an ``AttributeError`` message names, or ``None``.

    The name is text out of an exception message, which any code can raise
    with any text in it, so it is looked up and never evaluated: a bare name
    among the builtins, a dotted one (``datetime.date``, as Python prints a
    type defined in C) in its module, if that module is already imported --
    a type the error was raised on is already loaded, and looking it up
    imports nothing.
    """
    if "." not in type_name:
        return getattr(builtins, type_name, None)
    module_name, class_name = type_name.rsplit(".", 1)
    module = sys.modules.get(module_name)
    return None if module is None else getattr(module, class_name, None)


class AttributeErrorFormatter:
    """Format AttributeError with context and suggestions."""

    def __init__(
        self,
        error: AttributeError,
        source_location: SourceLocation | None = None,
        frame: ActuarialFrame | None = None,
    ) -> None:
        """Initialize the attribute error formatter.

        Args:
            error: The AttributeError instance
            source_location: Optional source location information
            frame: Optional ActuarialFrame for additional context

        """
        self.error = error
        self.source_location = source_location
        self.frame = frame
        self.suggestions: list[str] = []

        # Parse error message to extract details
        self._parse_error()
        # Generate suggestions
        self._generate_suggestions()

    def _parse_error(self) -> None:
        """Parse the error message to extract module/object and attribute names."""
        error_msg = str(self.error)

        # Common patterns in AttributeError messages
        # "module 'datetime' has no attribute 'ate'"
        # "'NoneType' object has no attribute 'split'"
        # "type object 'datetime.date' has no attribute 'ate'"

        # Pattern 1: module 'X' has no attribute 'Y'
        match = re.search(r"module '([^']+)' has no attribute '([^']+)'", error_msg)
        if match:
            self.module_name = match.group(1)
            self.attribute_name = match.group(2)
            self.error_type = "module_attribute"
            return

        # Pattern 2: 'TypeName' object has no attribute 'Y'
        match = re.search(r"'([^']+)' object has no attribute '([^']+)'", error_msg)
        if match:
            self.object_type = match.group(1)
            self.attribute_name = match.group(2)
            self.error_type = "object_attribute"
            return

        # Pattern 3: type object 'X' has no attribute 'Y'
        match = re.search(
            r"type object '([^']+)' has no attribute '([^']+)'", error_msg
        )
        if match:
            self.type_name = match.group(1)
            self.attribute_name = match.group(2)
            self.error_type = "type_attribute"
            return

        # Default
        self.error_type = "unknown"
        self.attribute_name = None

    def _generate_suggestions(self) -> None:
        """Generate suggestions based on the error context."""
        if not self.attribute_name:
            return

        # Try to get available attributes if we have module/type info
        if hasattr(self, "module_name"):
            self._suggest_module_attributes()
        elif hasattr(self, "type_name"):
            self._suggest_type_attributes()
        elif hasattr(self, "object_type"):
            self._suggest_object_attributes()

        # If we still don't have suggestions, match fuzzily
        if not self.suggestions:
            self._generate_fuzzy_suggestions()

    def _suggest_module_attributes(self) -> None:
        """Suggest attributes from a module."""
        available_attrs: list[str] = []

        # Check if we have predefined common attributes for this module
        groups = _attribute_groups(self.module_name)
        if groups:
            # Combine all attribute lists for the module
            for attr_list in groups.values():
                available_attrs.extend(attr_list)
        else:
            available_attrs = _attribute_list(self.module_name)

        # Also try to dynamically get attributes from the module
        try:
            module = importlib.import_module(self.module_name)
        except ImportError:
            # A module the interpreter cannot import by that name (one built
            # at runtime, say): the predefined attrs stand alone
            module = None
        if module is not None:
            dynamic_attrs = [attr for attr in dir(module) if not attr.startswith("_")]
            # Combine with predefined attrs, removing duplicates
            available_attrs = list(set(available_attrs + dynamic_attrs))

        # Use fuzzy matching with multiple algorithms
        if available_attrs:
            self._fuzzy_match_attributes(available_attrs)

    def _fuzzy_match_attributes(self, available_attrs: list[str]) -> None:
        """Perform fuzzy matching against available attributes."""
        if not available_attrs or not self.attribute_name:
            return

        seen = set()
        algorithms = [
            ("ratio", fuzz.ratio),
            ("partial_ratio", fuzz.partial_ratio),
            ("token_sort_ratio", fuzz.token_sort_ratio),
        ]

        for _, algo_func in algorithms:
            scores = [
                (attr, algo_func(self.attribute_name.lower(), attr.lower()))
                for attr in available_attrs
            ]
            scores.sort(key=lambda x: x[1], reverse=True)

            for attr, score in scores:
                if score > FUZZY_MATCH_THRESHOLD and attr not in seen:
                    self.suggestions.append(attr)
                    seen.add(attr)
                    if len(self.suggestions) >= MAX_SUGGESTIONS:
                        return

    def _suggest_type_attributes(self) -> None:
        """Suggest attributes from a type."""
        available_attrs = []

        # Map type names to our common attributes
        type_to_common = {
            "datetime.date": _attribute_groups("datetime").get("date_class", []),
            "datetime.datetime": _attribute_groups("datetime").get(
                "datetime_class", []
            ),
            "str": _attribute_list("str"),
            "list": _attribute_list("list"),
            "dict": _attribute_list("dict"),
        }

        if self.type_name in type_to_common:
            available_attrs = type_to_common[self.type_name]

        # Add the type's own attributes, where the name finds one
        type_obj = _named_type(self.type_name)
        if type_obj is not None:
            dynamic_attrs = [attr for attr in dir(type_obj) if not attr.startswith("_")]
            available_attrs = list(set(available_attrs + dynamic_attrs))

        if available_attrs:
            self._fuzzy_match_attributes(available_attrs)

    def _suggest_object_attributes(self) -> None:
        """Suggest attributes based on object type."""
        # Map common object types to attribute sets
        if self.object_type == "NoneType":
            self.suggestions.append(
                "(Note: You're trying to access an attribute on None)"
            )
            return

        # Try to find similar type in our common attributes
        type_mapping = {
            "DataFrame": ["pandas_dataframe", "polars_dataframe"],
            "Series": ["pandas_series"],
            "LazyFrame": ["polars_dataframe"],
        }

        available_attrs: list[str] = []
        for pattern, attr_keys in type_mapping.items():
            if pattern in self.object_type:
                for key in attr_keys:
                    available_attrs.extend(_attribute_list(key))

        if available_attrs:
            self._fuzzy_match_attributes(available_attrs)

    def _generate_fuzzy_suggestions(self) -> None:
        """Generate fuzzy suggestions when specific context isn't available."""
        # Combine all common attributes from various sources
        all_common_attrs = set()

        # Add attributes from all common types
        for attrs in COMMON_ATTRIBUTES.values():
            if isinstance(attrs, list):
                all_common_attrs.update(attrs)
            elif isinstance(attrs, dict):
                for attr_list in attrs.values():
                    all_common_attrs.update(attr_list)

        # Convert to list and fuzzy match
        if all_common_attrs:
            self._fuzzy_match_attributes(list(all_common_attrs))

    def format_error(self) -> str:
        """Create the friendly error message."""
        lines = [
            "─" * 80,
            "❌ Attribute Error",
            "",
        ]

        # Add location if available. The enclosing scope is named only when
        # it is genuinely known -- "module level" is a claim, not an
        # absence, so an unresolved scope omits the line rather than guess.
        if self.source_location:
            lines.append(
                f"📍 Location: {self.source_location.file_path}:"
                f"{self.source_location.line_number}"
            )
            if self.source_location.function_name is not None:
                lines.append(f"   Function: {self.source_location.function_name}")
            lines.extend(
                [
                    "",
                    "📝 Source Code:",
                ]
            )

            if self.source_location.source_line:
                lines.extend(source_block(self.source_location.source_line))
                lines.append("")

        # Error details
        lines.extend(
            [
                "🔴 Error Details:",
                "   Type: AttributeError",
                f"   Message: {self.error!s}",
            ]
        )

        if self.attribute_name:
            lines.append(f"   Missing Attribute: '{self.attribute_name}'")

        lines.append("")

        # Add suggestions
        if self.suggestions:
            lines.append("💡 Did you mean?")
            lines.extend(f"   • {suggestion}" for suggestion in self.suggestions)
            lines.append("")

        # Add helpful context based on error type
        if hasattr(self, "module_name") and self.module_name == "datetime":
            lines.extend(
                [
                    "ℹ️  Common datetime usage:",
                    "   • datetime.date(2025, 1, 1) - Create a date",
                    "   • datetime.datetime.now() - Current date and time",
                    "   • datetime.timedelta(days=30) - Time duration",
                    "",
                ]
            )

        lines.append("─" * 80)
        return "\n".join(lines)

    def format_for_llm(self) -> dict[str, Any]:
        """Structured format for LLM consumption."""
        result = {
            "error_type": "attribute_error",
            "error_details": {
                "type": "AttributeError",
                "message": str(self.error),
                "attribute_name": getattr(self, "attribute_name", None),
                "module_name": getattr(self, "module_name", None),
                "object_type": getattr(self, "object_type", None),
                "type_name": getattr(self, "type_name", None),
            },
            "suggestions": self.suggestions,
        }

        if self.source_location:
            result["error_location"] = {
                "file": self.source_location.file_path,
                "line": self.source_location.line_number,
                "function": self.source_location.function_name,
                "code": self.source_location.source_line,
            }

        return result
