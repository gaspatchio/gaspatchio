"""
Error formatting module for creating friendly, actionable error messages.

This module provides the FriendlyErrorFormatter class which converts raw Polars
exceptions into human-readable and LLM-parseable error messages with context,
suggestions, and data previews.
"""

from __future__ import annotations

import shutil
import sys
from typing import TYPE_CHECKING, Any, Optional

import polars as pl

# Import Rich for syntax highlighting
try:
    from rich.console import Console
    from rich.syntax import Syntax
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Import fuzzy matching if available
try:
    from thefuzz import fuzz
    FUZZ_AVAILABLE = True
except ImportError:
    FUZZ_AVAILABLE = False

if TYPE_CHECKING:
    from .metadata import TracedOperation
    from .validation import ValidationError

from .models import SourceLocation


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


class ValidationErrorFormatter:
    """Format validation errors with context and suggestions."""
    
    def __init__(self, error: ValidationError, frame: Any | None = None):
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
        
        # Add location if available
        if self.error.source_location:
            loc = self.error.source_location
            lines.extend([
                f"📍 Location: {loc.file_path}:{loc.line_number}",
                f"   Function: {loc.function_name or 'module level'}",
                "",
                "📝 Source Code:",
            ])
            
            # Add syntax-highlighted code
            if loc.source_line:
                source_code_lines = self._format_source_code(loc.source_line)
                lines.extend(source_code_lines)
                lines.append("")
        
        # Error details
        lines.extend([
            "🔴 Error Details:",
            f"   Type: ValidationError",
            f"   Message: {str(self.error)}",
        ])
        
        # Add context information if available
        if self.error.context.provided_value is not None:
            lines.append(f"   Provided Value: {repr(self.error.context.provided_value)}")
        
        if self.error.context.parameter_name:
            lines.append(f"   Parameter: {self.error.context.parameter_name}")
        
        lines.append("")
        
        # Add suggestions
        if self.suggestions or self.error.context.valid_options:
            lines.append("💡 Did you mean one of these?")
            
            # Show fuzzy match suggestions first
            for suggestion in self.suggestions[:3]:
                lines.append(f"   • {suggestion}")
            
            # Then show all valid options if available and not too many
            if (self.error.context.valid_options and 
                len(self.error.context.valid_options) <= 6 and 
                not self.suggestions):
                for option in self.error.context.valid_options:
                    lines.append(f"   • {option}")
            
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
                "expected_type": str(self.error.context.expected_type) if self.error.context.expected_type else None,
                "actual_type": str(self.error.context.actual_type) if self.error.context.actual_type else None,
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
        if not FUZZ_AVAILABLE:
            return
        
        # If we have a provided value and valid options, do fuzzy matching
        if (self.error.context.provided_value and 
            self.error.context.valid_options and
            isinstance(self.error.context.provided_value, str)):
            
            self.suggestions = self._suggest_valid_options(
                self.error.context.provided_value,
                self.error.context.valid_options
            )
    
    def _suggest_valid_options(self, invalid_value: str, valid_options: list[str]) -> list[str]:
        """Find similar valid options using fuzzy matching."""
        if not FUZZ_AVAILABLE or not valid_options:
            return []
        
        # Calculate similarity scores using different algorithms
        suggestions = []
        seen = set()
        
        # Try different fuzzy matching algorithms for better results
        algorithms = [
            ('ratio', fuzz.ratio),
            ('partial_ratio', fuzz.partial_ratio),
            ('token_sort_ratio', fuzz.token_sort_ratio),
        ]
        
        for algo_name, algo_func in algorithms:
            scores = [(opt, algo_func(invalid_value.lower(), opt.lower())) for opt in valid_options]
            scores.sort(key=lambda x: x[1], reverse=True)
            
            # Add high-scoring unique matches
            for opt, score in scores:
                if score > FUZZY_MATCH_THRESHOLD and opt not in seen:
                    suggestions.append(opt)
                    seen.add(opt)
                    if len(suggestions) >= 3:
                        return suggestions[:3]
        
        # If we have at least one suggestion, return what we have
        if suggestions:
            return suggestions[:3]
        
        # Try character-level edits for very close matches
        # This catches single character typos better
        for opt in valid_options:
            # Calculate edit distance manually for single char differences
            if abs(len(invalid_value) - len(opt)) <= 2:
                # Use token_set_ratio for order-independent matching
                score = fuzz.token_set_ratio(invalid_value.lower(), opt.lower())
                if score > 85:  # Higher threshold for this method
                    suggestions.append(opt)
                    if len(suggestions) >= 3:
                        break
        
        return suggestions[:3]
    
    def _format_source_code(self, source_line: str) -> list[str]:
        """Format source code with syntax highlighting if available."""
        # Reuse the formatting logic from FriendlyErrorFormatter
        formatter = FriendlyErrorFormatter.__new__(FriendlyErrorFormatter)
        return formatter._format_source_code(source_line)


# Import constants for fuzzy matching
from .constants import COMMON_ATTRIBUTES, FUZZY_MATCH_THRESHOLD, COMMON_VALIDATION_VALUES


class AttributeErrorFormatter:
    """Format AttributeError with context and suggestions."""
    
    def __init__(self, error: AttributeError, source_location: Optional[SourceLocation] = None, frame: Any | None = None):
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
        
        import re
        
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
        match = re.search(r"type object '([^']+)' has no attribute '([^']+)'", error_msg)
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
        if hasattr(self, 'module_name'):
            self._suggest_module_attributes()
        elif hasattr(self, 'type_name'):
            self._suggest_type_attributes()
        elif hasattr(self, 'object_type'):
            self._suggest_object_attributes()
        
        # If we still don't have suggestions and fuzzy matching is available
        if not self.suggestions and FUZZ_AVAILABLE:
            self._generate_fuzzy_suggestions()
    
    def _suggest_module_attributes(self) -> None:
        """Suggest attributes from a module."""
        available_attrs = []
        
        # Check if we have predefined common attributes for this module
        if self.module_name in COMMON_ATTRIBUTES:
            attrs_info = COMMON_ATTRIBUTES[self.module_name]
            if isinstance(attrs_info, dict):
                # Combine all attribute lists for the module
                for attr_list in attrs_info.values():
                    available_attrs.extend(attr_list)
            else:
                available_attrs = attrs_info
        
        # Also try to dynamically get attributes from the module
        try:
            import importlib
            module = importlib.import_module(self.module_name)
            dynamic_attrs = [attr for attr in dir(module) if not attr.startswith('_')]
            # Combine with predefined attrs, removing duplicates
            available_attrs = list(set(available_attrs + dynamic_attrs))
        except Exception:
            # If import fails, use only predefined attrs
            pass
        
        # Use fuzzy matching with multiple algorithms
        if FUZZ_AVAILABLE and available_attrs:
            self._fuzzy_match_attributes(available_attrs)
    
    def _fuzzy_match_attributes(self, available_attrs: list[str]) -> None:
        """Perform fuzzy matching against available attributes."""
        if not available_attrs or not self.attribute_name:
            return
        
        seen = set()
        algorithms = [
            ('ratio', fuzz.ratio),
            ('partial_ratio', fuzz.partial_ratio),
            ('token_sort_ratio', fuzz.token_sort_ratio),
        ]
        
        for algo_name, algo_func in algorithms:
            scores = [(attr, algo_func(self.attribute_name.lower(), attr.lower())) 
                     for attr in available_attrs]
            scores.sort(key=lambda x: x[1], reverse=True)
            
            for attr, score in scores:
                if score > FUZZY_MATCH_THRESHOLD and attr not in seen:
                    self.suggestions.append(attr)
                    seen.add(attr)
                    if len(self.suggestions) >= 3:
                        return
    
    def _suggest_type_attributes(self) -> None:
        """Suggest attributes from a type."""
        available_attrs = []
        
        # Map type names to our common attributes
        type_to_common = {
            "datetime.date": COMMON_ATTRIBUTES.get("datetime", {}).get("date_class", []),
            "datetime.datetime": COMMON_ATTRIBUTES.get("datetime", {}).get("datetime_class", []),
            "str": COMMON_ATTRIBUTES.get("str", []),
            "list": COMMON_ATTRIBUTES.get("list", []),
            "dict": COMMON_ATTRIBUTES.get("dict", []),
        }
        
        if self.type_name in type_to_common:
            available_attrs = type_to_common[self.type_name]
        
        # Try to get actual type attributes dynamically
        try:
            # Parse the type name to get the actual type
            if "." in self.type_name:
                module_name, class_name = self.type_name.rsplit(".", 1)
                import importlib
                module = importlib.import_module(module_name)
                type_obj = getattr(module, class_name)
            else:
                # Built-in type
                type_obj = eval(self.type_name)
            
            dynamic_attrs = [attr for attr in dir(type_obj) if not attr.startswith('_')]
            available_attrs = list(set(available_attrs + dynamic_attrs))
        except Exception:
            pass
        
        if FUZZ_AVAILABLE and available_attrs:
            self._fuzzy_match_attributes(available_attrs)
    
    def _suggest_object_attributes(self) -> None:
        """Suggest attributes based on object type."""
        # Map common object types to attribute sets
        if self.object_type == "NoneType":
            self.suggestions.append("(Note: You're trying to access an attribute on None)")
            return
        
        # Try to find similar type in our common attributes
        type_mapping = {
            "DataFrame": ["pandas_dataframe", "polars_dataframe"],
            "Series": ["pandas_series"],
            "LazyFrame": ["polars_dataframe"],
        }
        
        available_attrs = []
        for pattern, attr_keys in type_mapping.items():
            if pattern in self.object_type:
                for key in attr_keys:
                    if key in COMMON_ATTRIBUTES:
                        available_attrs.extend(COMMON_ATTRIBUTES[key])
        
        if FUZZ_AVAILABLE and available_attrs:
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
        
        # Add location if available
        if self.source_location:
            lines.extend([
                f"📍 Location: {self.source_location.file_path}:{self.source_location.line_number}",
                f"   Function: {self.source_location.function_name or 'module level'}",
                "",
                "📝 Source Code:",
            ])
            
            # Add syntax-highlighted code
            if self.source_location.source_line:
                source_code_lines = self._format_source_code(self.source_location.source_line)
                lines.extend(source_code_lines)
                lines.append("")
        
        # Error details
        lines.extend([
            "🔴 Error Details:",
            f"   Type: AttributeError",
            f"   Message: {str(self.error)}",
        ])
        
        if self.attribute_name:
            lines.append(f"   Missing Attribute: '{self.attribute_name}'")
        
        lines.append("")
        
        # Add suggestions
        if self.suggestions:
            lines.append("💡 Did you mean?")
            for suggestion in self.suggestions:
                lines.append(f"   • {suggestion}")
            lines.append("")
        
        # Add helpful context based on error type
        if hasattr(self, 'module_name') and self.module_name == "datetime":
            lines.extend([
                "ℹ️  Common datetime usage:",
                "   • datetime.date(2025, 1, 1) - Create a date",
                "   • datetime.datetime.now() - Current date and time",
                "   • datetime.timedelta(days=30) - Time duration",
                ""
            ])
        
        lines.append("─" * 80)
        return "\n".join(lines)
    
    def format_for_llm(self) -> dict[str, Any]:
        """Structured format for LLM consumption."""
        result = {
            "error_type": "attribute_error",
            "error_details": {
                "type": "AttributeError",
                "message": str(self.error),
                "attribute_name": getattr(self, 'attribute_name', None),
                "module_name": getattr(self, 'module_name', None),
                "object_type": getattr(self, 'object_type', None),
                "type_name": getattr(self, 'type_name', None),
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
    
    def _format_source_code(self, source_line: str) -> list[str]:
        """Format source code with syntax highlighting if available."""
        # Reuse the formatting logic from FriendlyErrorFormatter
        formatter = FriendlyErrorFormatter.__new__(FriendlyErrorFormatter)
        return formatter._format_source_code(source_line)
