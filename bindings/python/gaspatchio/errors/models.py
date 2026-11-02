# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Pydantic models for structured error handling.

This module provides structured models for error information that can be
formatted for multiple outputs: console display, JSON APIs, and LLM context.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from textwrap import dedent
from typing import Any

from pydantic import BaseModel, Field

from .constants import PLAN_DUMP_BOUNDARY, PLAN_DUMP_OMITTED

# The report's compact column line lists every column of a frame this narrow;
# a wider frame gets its first _COLUMNS_LISTED_BEFORE_COUNT and a count.
_COLUMNS_LISTED_IN_FULL = 8
_COLUMNS_LISTED_BEFORE_COUNT = 6

# What a statement's own closing line starts with, where it has one.
_CLOSERS = (")", "]", "}")


def source_block(statement: str) -> list[str]:
    """Return a model's statement as an error panel shows it: fenced and plain.

    A panel becomes the exception's own message, and where that message is
    read is not known when it is written -- a terminal, a log file, CI output,
    a notebook cell, a subprocess another tool parses. Terminal colour codes
    written into it would travel to every one of those as escape sequences,
    so the statement is plain text, every line of it indented under its
    heading. Colour, if a reader wants it, is for whatever displays the text.

    **A statement reads as it was written, wherever in the file it was.** Its
    source is read from its first token, so the first line arrives with no
    indentation and every line after it with the file's. Those lines move
    left together, keeping their shape: the statement's own closing line,
    where it has one -- a bracket, as a multi-line call closes -- lands under
    the first, and a continuation with none sits one indent in from it.
    """
    first, *rest = statement.strip().splitlines() or [""]
    body = dedent("\n".join(rest)).splitlines()
    if body and not body[-1].startswith(_CLOSERS):
        body = [f"    {line}" if line.strip() else line for line in body]
    fenced = [f"   {line}".rstrip() for line in (first, *body)]
    return ["   ```python", *fenced, "   ```"]


class ErrorType(str, Enum):
    """Types of errors that can occur."""

    COLUMN_NOT_FOUND = "column_not_found"
    TYPE_MISMATCH = "type_mismatch"
    INVALID_OPERATION = "invalid_operation"
    SCHEMA_CONFLICT = "schema_conflict"
    UNKNOWN = "unknown"


class SuggestionType(str, Enum):
    """Kinds of advice a suggestion can carry.

    Two members, because two are what the advice builder stamps: a
    named column to use instead of the one that was not found, and a
    pointer to the documentation. Three more once described kinds of
    advice this package has never given -- a cast, a split operation, a
    worked example -- and nothing ever constructed them.
    """

    TYPO_FIX = "typo_fix"
    DOCUMENTATION = "documentation"


class SourceLocation(BaseModel):
    """Source code location information.

    ``source_line`` is the text of the line, when there is text to read.
    A frame can genuinely have none -- stdin, an ``exec``-compiled snippet,
    a file edited since it was imported -- and the location is still worth
    reporting: the file and the line number are what send a reader to the
    right place. It is ``None`` in that case, never an empty string standing
    in for a line nobody can show.
    """

    file_path: str
    line_number: int
    function_name: str | None
    source_line: str | None


class ColumnInfo(BaseModel):
    """Information about a DataFrame column."""

    name: str
    dtype: str
    null_count: int | None = None
    unique_count: int | None = None


class ErrorMetadata(BaseModel):
    """Metadata about the error."""

    error_type: ErrorType
    error_category: str = "compilation"
    original_message: str
    timestamp: datetime = Field(default_factory=datetime.now)
    severity: str = "error"

    def display_header(self) -> str:
        """Format header for console display."""
        emoji = {
            ErrorType.COLUMN_NOT_FOUND: "🔍",
            ErrorType.TYPE_MISMATCH: "🔢",
            ErrorType.INVALID_OPERATION: "⚠️",
            ErrorType.SCHEMA_CONFLICT: "📊",
            ErrorType.UNKNOWN: "❌",
        }.get(self.error_type, "❌")

        return f"{emoji} {self.error_type.value.replace('_', ' ').title()}"


class OperationContext(BaseModel):
    """Context about the failing operation."""

    index: int
    total_operations: int
    alias: str
    expression: str
    source: SourceLocation
    expected_dtype: str | None = None


class DataFrameContext(BaseModel):
    """Context about the DataFrame state."""

    shape: tuple[int, int]
    columns: list[ColumnInfo]
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)


class Suggestion(BaseModel):
    """A suggestion for fixing the error."""

    text: str
    type: SuggestionType
    relevance_score: float = Field(ge=0.0, le=1.0)
    code_example: str | None = None


class EnhancedError(BaseModel):
    """Complete enhanced error information."""

    metadata: ErrorMetadata
    operation: OperationContext
    dataframe: DataFrameContext
    suggestions: list[Suggestion] = Field(default_factory=list)
    additional_context: dict[str, Any] = Field(default_factory=dict)

    def to_console(self, use_emoji: bool = True) -> str:
        """Format for console display with optional emoji."""
        lines = []

        # Header with separator
        lines.append("─" * 80)
        if use_emoji:
            lines.append(f"❌ {self.metadata.display_header()}")
        else:
            lines.append(f"ERROR: {self.metadata.error_type.value}")
        lines.append("─" * 80)
        lines.append("")

        # Source location. The enclosing scope is reported only when it is
        # actually known: "module level" is a claim, and a calculation
        # written inside main() reported as module level sends the reader --
        # and any LLM reading over their shoulder -- to the wrong place. An
        # omitted line says nothing, which is the honest answer here.
        lines.append(
            f"📍 Location: {self.operation.source.file_path}:"
            f"{self.operation.source.line_number}"
        )
        if self.operation.source.function_name is not None:
            lines.append(f"   Function: {self.operation.source.function_name}")
        lines.append(
            f"   Operation: {self.operation.alias} = "
            f"{self._truncate_expression(self.operation.expression)}"
        )
        lines.append("")

        # Source code, when there is a line to show. A frame with no
        # readable source (stdin, an exec-compiled snippet, a bare REPL)
        # gets no block at all rather than a heading over the word "None".
        if self.operation.source.source_line:
            lines.append("📝 Source Code:")
            lines.extend(source_block(self.operation.source.source_line))
            lines.append("")

        # Original error (simplified)
        lines.append("🔴 Error Details:")
        lines.append(f"   {self._format_original_error()}")
        lines.append("")

        # Suggestions
        if self.suggestions:
            if use_emoji:
                lines.append("💡 Suggestions:")
            else:
                lines.append("Suggestions:")
            for i, suggestion in enumerate(
                sorted(self.suggestions, key=lambda s: s.relevance_score, reverse=True)[
                    :3
                ],
                1,
            ):
                lines.append(f"   {i}. {suggestion.text}")
                if suggestion.code_example:
                    lines.append(f"      Example: {suggestion.code_example}")
            lines.append("")

        # DataFrame context (condensed)
        lines.append("📊 Calculation State Before Error:")
        lines.append("   (Showing available columns at the point of failure)")
        lines.append(self._format_columns_compact())

        lines.append("─" * 80)

        return "\n".join(lines)

    def to_json(self) -> str:
        """Export as JSON string."""
        return self.model_dump_json(indent=2)

    def to_dict(self) -> dict[str, Any]:
        """Export as dictionary."""
        return self.model_dump()

    def to_llm_context(self) -> dict[str, Any]:
        """
        Export optimized for LLM consumption.

        Flattens structure and adds helpful context.
        """
        return {
            "error_type": self.metadata.error_type.value,
            "error_category": self.metadata.error_category,
            "failing_operation": {
                "index": self.operation.index,
                "total": self.operation.total_operations,
                "alias": self.operation.alias,
                "expression": self.operation.expression,
                "source_file": self.operation.source.file_path,
                "source_line": self.operation.source.line_number,
                "source_function": self.operation.source.function_name,
                "code": self.operation.source.source_line,
            },
            "dataframe_shape": list(self.dataframe.shape),
            "available_columns": [
                {"name": col.name, "type": col.dtype} for col in self.dataframe.columns
            ],
            "suggestions": [
                {
                    "text": s.text,
                    "type": s.type.value,
                    "score": s.relevance_score,
                    "example": s.code_example,
                }
                for s in sorted(
                    self.suggestions, key=lambda s: s.relevance_score, reverse=True
                )
            ],
            "original_error": self.metadata.original_message,
            **self.additional_context,
        }

    def _truncate_expression(self, expression: str, max_length: int = 60) -> str:
        """Truncate long expressions for display."""
        if len(expression) <= max_length:
            return expression
        return expression[: max_length - 3] + "..."

    def _format_original_error(self) -> str:
        """Render polars' text as the panel's one-line ``Error Details:`` field.

        The twin of ``FriendlyErrorFormatter._clean_error_message``, on the
        other panel, and the same contract. Polars often hands over two
        things: a diagnosis addressed to the reader, then the query plan it
        failed resolving. They are split here on ``PLAN_DUMP_BOUNDARY`` and
        treated as what they are.

        The diagnosis is kept **whole**. It used to share a 117-character
        budget with the dump, and on this panel's commonest error that budget
        cut the answer out of the sentence: a ``ColumnNotFoundError`` names
        the column it could not find and then lists the columns that do
        exist, which is the reader's next move, and the cut landed two names
        into that list. The dump never had to contribute -- the diagnosis
        alone overran the budget -- so a budget is not the shape of the fix.
        There is deliberately none now: a truncated diagnosis is the defect.

        The dump is dropped, not truncated. It is a tree, and this field is
        one line, so any slice of it survives only as a smear of node names
        with the newlines removed -- and the panel already answers the
        question the plan would: the failing operation, the statement that
        defined it, its file and line, and the columns that existed before it
        ran. The untouched polars text stays reachable on
        ``to_llm_context()``, which the compilation handler stamps on the
        exception alongside this panel, so nothing is destroyed by the
        omission -- only left out of the field it could not be read in.

        Returns:
            The message on one line, with a stated omission when a plan dump
            followed it.

        """
        message = self.metadata.original_message
        diagnosis, boundary, _dump = message.partition(PLAN_DUMP_BOUNDARY)
        cleaned = " ".join(diagnosis.split())
        if not boundary:
            return cleaned
        return f"{cleaned} {PLAN_DUMP_OMITTED}".strip()

    def _format_columns_compact(self) -> str:
        """Format columns in a compact, readable way."""
        columns = self.dataframe.columns
        if len(columns) <= _COLUMNS_LISTED_IN_FULL:
            # Show all columns if there are few
            col_strs = [f"{col.name} ({col.dtype})" for col in columns]
            return "   " + ", ".join(col_strs)
        # Show the first few and count of remaining
        first_cols = columns[:_COLUMNS_LISTED_BEFORE_COUNT]
        col_strs = [f"{col.name} ({col.dtype})" for col in first_cols]
        remaining = len(columns) - _COLUMNS_LISTED_BEFORE_COUNT
        return f"   {', '.join(col_strs)}, ... and {remaining} more"
