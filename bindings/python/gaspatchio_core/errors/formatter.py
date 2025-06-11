"""
Error formatting module for creating friendly, actionable error messages.

This module provides the FriendlyErrorFormatter class which converts raw Polars
exceptions into human-readable and LLM-parseable error messages with context,
suggestions, and data previews.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from .metadata import TracedOperation


class FriendlyErrorFormatter:
    """Format errors for human and LLM consumption."""

    def __init__(
        self,
        operation: TracedOperation,
        exception: Exception,
        last_good_df: pl.DataFrame,
        suggestions: list[str] | None = None,
    ):
        """
        Initialize the error formatter.

        Args:
            operation: The TracedOperation that failed
            exception: The original exception
            last_good_df: The last DataFrame that executed successfully
            suggestions: Optional list of fix suggestions

        """
        self.operation = operation
        self.exception = exception
        self.last_good_df = last_good_df
        self.suggestions = suggestions or []

    def format_error(self) -> str:
        """Create the friendly error message."""
        error_type = type(self.exception).__name__
        error_msg = str(self.exception)

        # Enhanced error with source location
        lines = [
            f"❌ Calculation error in {self.operation.metadata.file_name}:{self.operation.metadata.line_number}",
            f"   Failed operation: {self.operation.alias}",
            f"   Source: {self.operation.metadata.source_line}",
            "",
            f"Polars raised → {error_type}: {error_msg}",
            "",
            "💡 Suggestions:",
            *[f"   • {suggestion}" for suggestion in self.suggestions],
            "",
            "📊 Last good data (preview):",
            self._format_dataframe_preview(self.last_good_df),
        ]

        return "\n".join(lines)

    def format_for_llm(self) -> dict[str, Any]:
        """Structured format for LLM consumption."""
        return {
            "error_type": "column_calculation_error",
            "operation": {
                "name": self.operation.alias,
                "expression": str(self.operation.expression),
            },
            "error_location": {
                "file": self.operation.metadata.file_name,
                "line": self.operation.metadata.line_number,
                "code": self.operation.metadata.source_line,
                "function": self.operation.metadata.function_name,
            },
            "error_details": {
                "type": type(self.exception).__name__,
                "message": str(self.exception),
                "column_alias": self.operation.alias,
                "expression": str(self.operation.expression),
            },
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
            except Exception:
                # Fallback if anything fails
                available_columns = []
                dataframe_shape = [0, 0]

        return {
            "available_columns": available_columns,
            "dataframe_shape": dataframe_shape,
            "timestamp": self.operation.metadata.timestamp,
        }

    def _format_dataframe_preview(self, df: pl.DataFrame, max_rows: int = 5) -> str:
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

        except Exception as e:
            return f"  <Error displaying data: {e}>"

    def _truncate_wide_tables(
        self,
        df: pl.DataFrame,
        max_width: int | None = None,
    ) -> pl.DataFrame:
        """Truncate tables that are too wide for display."""
        if max_width is None:
            # Try to detect terminal width, default to 120
            try:
                terminal_size = shutil.get_terminal_size()
                max_width = min(terminal_size.columns, 120)
            except:
                max_width = 120

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
        truncated = pl.concat([first_part, ellipsis_df, last_part], how="horizontal")

        return truncated
