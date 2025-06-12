"""
Error formatting module for creating friendly, actionable error messages.

This module provides the FriendlyErrorFormatter class which converts raw Polars
exceptions into human-readable and LLM-parseable error messages with context,
suggestions, and data previews.
"""

from __future__ import annotations

import shutil
import sys
from typing import TYPE_CHECKING, Any

import polars as pl

# Import Rich for syntax highlighting
try:
    from rich.console import Console
    from rich.syntax import Syntax
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

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
        error_msg = self._clean_error_message(str(self.exception))

        # Enhanced error with source location
        lines = [
            "─" * 80,
            f"❌ Calculation Error",
            "─" * 80,
            "",
            f"📍 Location: {self.operation.metadata.file_name}:{self.operation.metadata.line_number}",
            f"   Function: {self.operation.metadata.function_name or 'module level'}",
            f"   Operation: {self.operation.alias}",
            "",
            "📝 Source Code:",
        ]
        
        # Add syntax-highlighted code
        source_code_lines = self._format_source_code(self.operation.metadata.source_line)
        lines.extend(source_code_lines)
        
        lines.extend([
            "",
            f"🔴 Error Details:",
            f"   Type: {error_type}",
            f"   Message: {error_msg}",
            "",
        ])
        
        if self.suggestions:
            lines.extend([
                "💡 Suggestions:",
                *[f"   • {suggestion}" for suggestion in self.suggestions[:3]],
                "",
            ])
        
        # Simplified data preview
        lines.extend([
            "📊 Calculation State Before Error:",
            "   (This shows the last successful calculation state)",
            self._format_dataframe_preview(self.last_good_df, max_rows=3),
            "",
            "─" * 80,
        ])

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
    
    def _format_source_code(self, source_line: str) -> list[str]:
        """Format source code with syntax highlighting if available."""
        # Check if we should use Rich syntax highlighting
        if RICH_AVAILABLE and self._should_use_rich_formatting():
            return self._format_source_code_rich(source_line)
        else:
            # Fallback to markdown-style fenced code blocks
            return [
                "   ```python",
                f"   {source_line}",
                "   ```",
            ]
    
    def _should_use_rich_formatting(self) -> bool:
        """Check if we should use Rich formatting (TTY and not piped)."""
        # Check if stdout is a TTY and not being piped
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    
    def _format_source_code_rich(self, source_line: str) -> list[str]:
        """Format source code with Rich syntax highlighting."""
        try:
            # Create a console with specific width to match our indentation
            console = Console(file=None, force_terminal=True, width=120)
            
            # Create syntax object with Python highlighting
            syntax = Syntax(
                source_line.strip(),
                "python",
                theme="monokai",  # Dark theme that works well in terminals
                line_numbers=False,
                word_wrap=False,
                indent_guides=False,
            )
            
            # Render to string
            with console.capture() as capture:
                console.print(syntax)
            
            highlighted = capture.get()
            
            # Split into lines and add our indentation
            highlighted_lines = []
            for line in highlighted.strip().split("\n"):
                highlighted_lines.append(f"   {line}")
            
            return highlighted_lines
            
        except Exception:
            # If Rich formatting fails, fall back to plain text
            return [
                "   ```python",
                f"   {source_line}",
                "   ```",
            ]
    
    def _clean_error_message(self, message: str) -> str:
        """Clean up error message for display."""
        # Remove excessive whitespace and newlines
        message = " ".join(message.split())
        # Truncate if too long
        if len(message) > 120:
            message = message[:117] + "..."
        return message
