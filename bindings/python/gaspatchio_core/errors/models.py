"""
Pydantic models for structured error handling.

This module provides structured models for error information that can be
formatted for multiple outputs: console display, JSON APIs, and LLM context.
"""
from __future__ import annotations

import sys
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

# Import Rich for syntax highlighting
try:
    from rich.console import Console
    from rich.syntax import Syntax
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class ErrorType(str, Enum):
    """Types of errors that can occur."""
    COLUMN_NOT_FOUND = "column_not_found"
    TYPE_MISMATCH = "type_mismatch"
    INVALID_OPERATION = "invalid_operation"
    SCHEMA_CONFLICT = "schema_conflict"
    UNKNOWN = "unknown"


class SuggestionType(str, Enum):
    """Types of suggestions."""
    TYPO_FIX = "typo_fix"
    TYPE_CAST = "type_cast"
    OPERATION_SPLIT = "operation_split"
    DOCUMENTATION = "documentation"
    CODE_EXAMPLE = "code_example"


class SourceLocation(BaseModel):
    """Source code location information."""
    file_path: str
    line_number: int
    function_name: str | None
    source_line: str
    
    @property
    def display_location(self) -> str:
        """Format for display."""
        return f"{self.file_path}:{self.line_number}"


class ColumnInfo(BaseModel):
    """Information about a DataFrame column."""
    name: str
    dtype: str
    null_count: Optional[int] = None
    unique_count: Optional[int] = None
    
    def display(self, include_stats: bool = False) -> str:
        """Format for display."""
        base = f"{self.name} ({self.dtype})"
        if include_stats and self.null_count is not None:
            base += f" - {self.null_count} nulls"
        return base


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
            ErrorType.UNKNOWN: "❌"
        }.get(self.error_type, "❌")
        
        return f"{emoji} {self.error_type.value.replace('_', ' ').title()}"


class OperationContext(BaseModel):
    """Context about the failing operation."""
    index: int
    total_operations: int
    alias: str
    expression: str
    source: SourceLocation
    expected_dtype: Optional[str] = None
    
    def display(self, max_expr_length: int = 80) -> str:
        """Format for console display."""
        expr = self.expression
        if len(expr) > max_expr_length:
            expr = expr[:max_expr_length-3] + "..."
        
        return f"""Operation {self.index + 1}/{self.total_operations}:
   {self.alias} = {expr}
   at {self.source.display_location}"""


class DataFrameContext(BaseModel):
    """Context about the DataFrame state."""
    shape: Tuple[int, int]
    columns: List[ColumnInfo]
    preview_rows: List[Dict[str, Any]] = Field(default_factory=list)
    dataframe_schema: Optional[str] = None
    
    def display_columns(self, max_display: int = 10) -> str:
        """Format columns for display."""
        if len(self.columns) <= max_display:
            return "\n".join(f"   • {col.display()}" for col in self.columns)
        else:
            displayed = self.columns[:max_display]
            lines = [f"   • {col.display()}" for col in displayed]
            lines.append(f"   ... and {len(self.columns) - max_display} more columns")
            return "\n".join(lines)
    
    def display_preview(self) -> str:
        """Format preview for display."""
        if not self.preview_rows:
            return "   [No preview available]"
        
        # Simple table representation
        if len(self.preview_rows) == 1:
            return "   [1 row preview available in JSON format]"
        else:
            return f"   [{len(self.preview_rows)} rows preview available in JSON format]"


class Suggestion(BaseModel):
    """A suggestion for fixing the error."""
    text: str
    type: SuggestionType
    relevance_score: float = Field(ge=0.0, le=1.0)
    code_example: Optional[str] = None
    
    def display(self) -> str:
        """Format for console display."""
        if self.code_example:
            return f"   • {self.text}\n     Example: {self.code_example}"
        return f"   • {self.text}"


class EnhancedError(BaseModel):
    """Complete enhanced error information."""
    metadata: ErrorMetadata
    operation: OperationContext
    dataframe: DataFrameContext
    suggestions: List[Suggestion] = Field(default_factory=list)
    additional_context: Dict[str, Any] = Field(default_factory=dict)
    
    def to_console(self, use_emoji: bool = True) -> str:
        """
        Format for console display with optional emoji.
        """
        lines = []
        
        # Header with separator
        lines.append("─" * 80)
        if use_emoji:
            lines.append(f"❌ {self.metadata.display_header()}")
        else:
            lines.append(f"ERROR: {self.metadata.error_type.value}")
        lines.append("─" * 80)
        lines.append("")
        
        # Source location
        lines.append(f"📍 Location: {self.operation.source.file_path}:{self.operation.source.line_number}")
        lines.append(f"   Function: {self.operation.source.function_name or 'module level'}")
        lines.append(f"   Operation: {self.operation.alias} = {self._truncate_expression(self.operation.expression)}")
        lines.append("")
        
        # Source code
        lines.append("📝 Source Code:")
        source_code_lines = self._format_source_code(self.operation.source.source_line)
        lines.extend(source_code_lines)
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
            for i, suggestion in enumerate(sorted(self.suggestions, key=lambda s: s.relevance_score, reverse=True)[:3], 1):
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
    
    def to_dict(self) -> dict:
        """Export as dictionary."""
        return self.model_dump()
    
    def to_llm_context(self) -> dict:
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
                "code": self.operation.source.source_line
            },
            "dataframe_shape": list(self.dataframe.shape),
            "available_columns": [
                {"name": col.name, "type": col.dtype} 
                for col in self.dataframe.columns
            ],
            "suggestions": [
                {
                    "text": s.text,
                    "type": s.type.value,
                    "score": s.relevance_score,
                    "example": s.code_example
                }
                for s in sorted(self.suggestions, key=lambda s: s.relevance_score, reverse=True)
            ],
            "original_error": self.metadata.original_message,
            **self.additional_context
        }
    
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
    
    def _truncate_expression(self, expression: str, max_length: int = 60) -> str:
        """Truncate long expressions for display."""
        if len(expression) <= max_length:
            return expression
        return expression[:max_length - 3] + "..."
    
    def _format_original_error(self) -> str:
        """Format the original error message in a cleaner way."""
        msg = self.metadata.original_message
        # Remove excessive newlines and whitespace
        msg = " ".join(msg.split())
        # Truncate if too long
        if len(msg) > 120:
            msg = msg[:117] + "..."
        return msg
    
    def _format_columns_compact(self) -> str:
        """Format columns in a compact, readable way."""
        columns = self.dataframe.columns
        if len(columns) <= 8:
            # Show all columns if there are few
            col_strs = [f"{col.name} ({col.dtype})" for col in columns]
            return "   " + ", ".join(col_strs)
        else:
            # Show first 6 and count of remaining
            first_cols = columns[:6]
            col_strs = [f"{col.name} ({col.dtype})" for col in first_cols]
            remaining = len(columns) - 6
            return f"   {', '.join(col_strs)}, ... and {remaining} more"