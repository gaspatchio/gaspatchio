# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

import polars as pl  # Import polars for exception type checking
from loguru import logger

from .metadata import TracedOperation
from .validation import ValidationError

# Import thefuzz only if available, provide fallback
try:
    from thefuzz import fuzz
except ImportError:
    fuzz = None

# Import Rich for syntax highlighting
try:
    from rich.console import Console
    from rich.syntax import Syntax
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

if TYPE_CHECKING:
    # Avoid circular import during runtime, import for type checking only
    from ..frame.base import ActuarialFrame


# ADDED: Define custom warning class
class PerformanceWarning(Warning):
    """Warning for potential performance issues."""


def _extract_missing_column_robust(error_str: str) -> str | None:
    """Attempts to extract the missing column name from specific error patterns.
    Assumes error_str is derived from `str(ColumnNotFoundError)` or similar.
    """
    # Pattern 1: Search for word characters followed by a newline.
    # Removed ^ anchor to allow matching even if not at the absolute start.
    match = re.search(r"([a-zA-Z0-9_]+)\n", error_str)
    if match:
        col_name = match.group(1)
        # Relax the length check, maybe short names are valid
        if col_name.lower() != "traceback":
            return col_name

    # Pattern 2/3 Combined: Variations like 'column "name" not found' etc.
    # Trying a broader pattern to catch different quoting/spacing.
    match = re.search(
        # Optional 'Error:', optional context words, quote, capture name, quote.
        r"(?:Error:\s*)?(?:column|Field not found:|unable to find column)\s*.*?('|\")([^\'\"]+)\1",
        error_str,
        re.IGNORECASE,
    )
    if match:
        # The actual column name is in group 2
        return match.group(2)

    # Pattern 4: Specific "ColumnNotFoundError: name" format.
    match = re.search(r"ColumnNotFoundError:\s*([a-zA-Z0-9_]+)", error_str)
    if match:
        return match.group(1)

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

    try:
        # Use fuzz.WRatio - often better for mixed-case and partial matches.
        # Calculate scores for all available columns.
        scores = [(col, fuzz.WRatio(missing_col, col)) for col in available_cols]

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        # Filter matches based on score cutoff.
        # WRatio score is 0-100.
        score_cutoff = 86
        similar_cols = [match[0] for match in scores if match[1] >= score_cutoff]

        # Absolute threshold check
        # If the best score itself is low, return empty
        if scores and scores[0][1] < 70:
            return []

        # Return top N suggestions
        return similar_cols[:max_suggestions]
    except Exception:
        # If fuzzy matching fails, return empty list
        return []


def _format_source_code_snippet(source_line: str) -> str:
    """Format source code with syntax highlighting if available."""
    # Check if Rich is available for syntax highlighting
    if RICH_AVAILABLE:
        try:
            from rich.console import Console
            from rich.syntax import Syntax
            from rich.text import Text
            
            # Create a syntax object with Python highlighting
            syntax = Syntax(source_line.strip(), "python", theme="monokai", line_numbers=False)
            
            # Render to string with console
            console = Console(force_terminal=True, width=100, legacy_windows=False)
            with console.capture() as capture:
                console.print("   ", syntax, sep="")
            
            return capture.get().rstrip()
        except Exception as e:
            # Fallback to plain text if Rich fails
            logger.trace(f"Rich syntax highlighting failed: {e}")
    
    # Fallback: Use markdown-style code block
    return f"   ```python\n   {source_line}\n   ```"


def _find_column_reference_in_graph(
    frame: ActuarialFrame,
    missing_col: str,
) -> dict[str, Any] | None:
    """
    Search the computation graph for operations that reference the missing column.
    
    Returns dict with file, line, function, operation, and source if found.
    """
    if not hasattr(frame, '_computation_graph') or not frame._computation_graph:
        return None
    
    # Search through the computation graph
    for operation in frame._computation_graph:
        # Skip tuple operations (legacy format)
        if isinstance(operation, tuple):
            continue
            
        # Check if this operation references the missing column
        try:
            # Get the expression string
            expr_str = str(operation.expression)
            
            # Check if the missing column is referenced in the expression
            # Look for patterns like col("missing_col") or ["missing_col"]
            if (f'col("{missing_col}")' in expr_str or 
                f"col('{missing_col}')" in expr_str or
                f'["{missing_col}"]' in expr_str or
                f"['{missing_col}']" in expr_str):
                
                # Found the operation that references the missing column
                if hasattr(operation, 'metadata') and operation.metadata:
                    return {
                        'file': operation.metadata.display_filename,
                        'line': operation.metadata.line_number,
                        'function': operation.metadata.function_name or 'module level',
                        'operation': f"{operation.alias} = {operation.expression}",
                        'source': operation.metadata.source_line
                    }
        except Exception:
            # Skip if we can't process this operation
            continue
    
    return None


def _format_column_message(
    frame: ActuarialFrame,
    missing_col: str,
    original_msg: str,
) -> str:
    """Format a helpful error message for a missing column."""
    try:
        # For LazyFrame, use collect_schema().names() to avoid warning
        if hasattr(frame._df, 'collect_schema'):
            available_cols = frame._df.collect_schema().names()
        else:
            # For eager DataFrame, use columns directly
            available_cols = frame._df.columns
    except Exception:
        # Fallback to tracked column order
        available_cols = frame._column_order if frame._column_order else []

    similar_cols = _find_similar_columns(missing_col, available_cols)

    # Check if we should use rich formatting
    from ..util import get_error_mode
    error_mode = get_error_mode()
    # Always use rich formatting when enhanced mode is on
    use_rich = error_mode in ["enhanced", "debug"]
    
    if use_rich:
        # Try to find the source location from computation graph
        source_location = _find_column_reference_in_graph(frame, missing_col)
        
        # Rich formatted error message
        error_msg = f"\n{'─' * 80}\n"
        error_msg += "❌ Calculation Error\n"
        error_msg += f"{'─' * 80}\n\n"
        
        if source_location:
            error_msg += f"📍 Location: {source_location['file']}:{source_location['line']}\n"
            error_msg += f"   Function: {source_location['function']}\n"
            error_msg += f"   Operation: {source_location['operation']}\n\n"
            
            error_msg += "📝 Source Code:\n"
            # Format source code with syntax highlighting
            formatted_source = _format_source_code_snippet(source_location['source'])
            error_msg += formatted_source + "\n\n"
        else:
            error_msg += "📍 Location: (Source location not available)\n"
            error_msg += "   Operation: Column reference\n\n"
        
        error_msg += "🔴 Error Details:\n"
        error_msg += f"   Type: ColumnNotFoundError\n"
        error_msg += f"   Message: Column '{missing_col}' not found\n\n"
        
        error_msg += "📊 Calculation State Before Error:\n"
        error_msg += "   (Available columns at the point of failure)\n"
        # Get shape safely
        try:
            if hasattr(frame._df, 'shape'):
                rows = frame._df.shape[0]
            else:
                rows = "unknown"
        except Exception:
            rows = "unknown"
        error_msg += f"   shape: ({rows}, {len(available_cols)})\n"
        error_msg += "   ┌" + "─" * 78 + "┐\n"
        
        # Format columns in a table-like structure
        for i, col in enumerate(available_cols):
            if i < 5 or i >= len(available_cols) - 1:  # Show first 5 and last column
                error_msg += f"   │ {col:<76} │\n"
            elif i == 5:
                error_msg += f"   │ ... ({len(available_cols) - 6} more columns) ...{' ' * 49} │\n"
        
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
        
        error_msg += "Available columns are:\n - " + "\n - ".join(available_cols)
        error_msg += (
            f"\n\nOriginal Polars Error: {original_msg}"
        )

    return error_msg


def _format_column_error(
    frame: ActuarialFrame,
    original_exception: Exception,
    missing_col: str,
    original_msg: str,
) -> Exception:
    """Legacy function - formats a helpful error message for a missing column."""
    # This is kept for backward compatibility but just calls the new function
    error_msg = _format_column_message(frame, missing_col, original_msg)
    return type(original_exception)(error_msg)


def _is_compilation_error(e: Exception) -> bool:
    """
    Detect if an exception is a compilation error.

    Compilation errors occur during query optimization before execution.
    """
    error_str = str(e)

    # Check for specific compilation error patterns
    if isinstance(e, pl.exceptions.ComputeError):
        # Many compilation errors are ComputeError type
        if any(
            pattern in error_str
            for pattern in [
                "FAILED HERE RESOLVING",
                "got invalid or ambiguous dtypes",
                "type coercion",
                "schema mismatch",
            ]
        ):
            return True

    # Check for column not found during compilation
    if isinstance(e, pl.exceptions.ColumnNotFoundError):
        # If there's optimization context, it's compilation
        if (
            "query optimization" in error_str
            or "FAILED HERE" in error_str
            or "Resolved plan" in error_str
        ):
            return True

    # Check for other compilation-specific patterns
    compilation_patterns = [
        "failed during query optimization",
        "unable to determine output schema",
        "cannot resolve expression type",
        "type inference failed",
    ]

    return any(pattern in error_str for pattern in compilation_patterns)


def _handle_frame_error(frame: ActuarialFrame, e: Exception):
    """Handle errors during frame operations, providing enhanced context and suggestions.
    
    This handles both execution errors (from collect/profile) and validation errors.
    """
    # Skip if already processed (any kind of processing)
    if any(
        hasattr(e, attr)
        for attr in [
            "_enhanced_processed",
            "_basic_formatted",
            "enhanced_error",
            "_dispatch_enhanced",
        ]
    ):
        raise e

    # Import locally to avoid circular dependencies and only import when needed
    from ..util import get_error_mode

    # Check if we should use enhanced error handling
    error_mode = get_error_mode()
    
    # Handle ValidationError with enhanced formatting
    if isinstance(e, ValidationError) and error_mode in ["enhanced", "debug"]:
        return _handle_validation_error(frame, e)
    
    # Handle AttributeError with enhanced formatting
    if isinstance(e, AttributeError) and error_mode in ["enhanced", "debug"]:
        return _handle_attribute_error(frame, e)

    # Early exit for production mode - just re-raise
    if not (
        frame._tracing or frame._mode == "debug" or error_mode in ["enhanced", "debug"]
    ):
        raise e

    # NEW: Check for compilation errors FIRST
    if _is_compilation_error(e) and error_mode in ["enhanced", "debug"]:
        # Route to compilation handler
        logger.debug("Detected compilation error, routing to compilation handler")
        return _handle_compilation_error(frame, e)

    # Check if we have metadata-enabled operations (TracedOperation) in the graph
    has_traced_operations = False
    if frame._computation_graph:
        # Check if any operations are TracedOperation objects (not tuples)
        has_traced_operations = any(
            not isinstance(op, tuple) for op in frame._computation_graph
        )

    # Try enhanced error handling if we have traced operations
    if has_traced_operations and error_mode in ["enhanced", "debug"]:
        try:
            # Import error handling components locally to avoid circular imports
            from .boundary import ErrorBoundaryFinder
            from .formatter import FriendlyErrorFormatter
            from .suggestions import ErrorSuggestionEngine

            # Find the failing operation using binary search
            finder = ErrorBoundaryFinder(frame, e)
            fail_idx, fail_op, last_good_df = finder.find_failing_operation()

            if fail_op is not None and hasattr(fail_op, "metadata"):
                # Generate suggestions based on the error and context
                engine = ErrorSuggestionEngine()
                suggestions = engine.suggest_fixes(
                    e,
                    fail_op,
                    list(last_good_df.columns) if last_good_df is not None else [],
                )

                # Format the error with enhanced information
                formatter = FriendlyErrorFormatter(
                    operation=fail_op,
                    exception=e,
                    last_good_df=last_good_df,
                    suggestions=suggestions,
                )

                # Create enhanced exception with same type as original
                try:
                    enhanced_msg = formatter.format_error()
                    llm_context = formatter.format_for_llm()

                    # Log enhanced error if verbose mode is on
                    if getattr(frame, "_verbose", False):
                        logger.debug(
                            f"Enhanced error handling applied: operation at index {fail_idx}",
                        )

                    # Instead of creating a new exception, modify the original one
                    # This preserves the exception type while updating the message
                    e.args = (enhanced_msg,)
                    e.llm_context = llm_context
                    # Mark the exception as already processed to prevent re-processing
                    e._enhanced_processed = True
                    raise e
                except Exception as format_step_error:
                    # Log which specific step failed (without the full enhanced error message)
                    logger.debug(f"Exception modification failed: {type(format_step_error).__name__}")
                    if getattr(frame, "_verbose", False):
                        logger.trace(
                            f"Specific formatting step failed: {format_step_error}",
                        )
                    # Don't raise the formatting error, just continue to fallback
                    pass
            # No metadata available, log this case
            if getattr(frame, "_verbose", False):
                logger.debug(
                    "Enhanced error handling: no metadata available for failing operation",
                )

        except Exception as format_error:
            # If enhanced error handling fails, fall back to basic formatting
            logger.debug(f"Enhanced error handling failed, falling back to basic formatting")
            if getattr(frame, "_verbose", False):
                logger.trace(
                    f"Enhanced error handling failed: {format_error}, falling back to basic formatting",
                )

    # Fall back to basic column error formatting for column-related errors
    _handle_basic_column_error(frame, e)
    # This should never reach here as _handle_basic_column_error always raises


# Backward compatibility alias
_handle_execution_error = _handle_frame_error


def _handle_basic_column_error(frame: ActuarialFrame, e: Exception):
    """Handle basic column errors with similarity suggestions (fallback method)."""
    # Skip if already enhanced
    if hasattr(e, "enhanced_error"):
        raise e

    error_msg = str(e)
    error_msg_str = str(error_msg) if error_msg is not None else ""

    missing_col: str | None = None

    # Attempt extraction only if it's a known Polars error type or the message strongly suggests a column issue
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

        # Fallback only if primary extraction failed but context suggests it *should* be there
        if not missing_col and isinstance(e, pl.exceptions.ColumnNotFoundError):
            match = re.search(r"column: \\\"(.*?)\\\" not found", error_msg_str)
            if match:
                missing_col = match.group(1)

    # If a missing column *was* identified, format the error
    if missing_col:
        try:
            # Format the message but modify the original exception
            formatted_msg = _format_column_message(frame, missing_col, error_msg_str)
            e.args = (formatted_msg,)
            e._basic_formatted = True
            if getattr(frame, "_verbose", False):
                logger.trace(f"Column error formatted: {missing_col}")
            raise e
        except Exception as format_err:
            # If formatting itself fails, log and raise original
            logger.debug(f"Failed to format column error: {format_err}")
            raise e
    else:
        # If no missing column identified, just re-raise
        if getattr(frame, "_verbose", False):
            logger.trace(f"Execution failed: {error_msg_str}")
        raise e


def _is_column_reference_compilation_error(e: Exception) -> bool:
    """Check if this is a compilation error due to missing column reference."""
    if isinstance(e, pl.exceptions.ColumnNotFoundError):
        return True

    error_str = str(e)
    patterns = [
        "column not found",
        "ColumnNotFoundError",
        "no column named",
        "unable to find column",
    ]
    return any(pattern in error_str for pattern in patterns)


def _handle_compilation_error_enhanced(frame: ActuarialFrame, e: Exception):
    """
    Handle compilation errors with enhanced context using operation replay.

    This function uses CompilationErrorFinder to replay operations and find
    the exact failing operation with full context.
    """
    try:
        # Import compilation-specific components
        from .compilation_finder import CompilationErrorFinder

        # Find the failing operation using compilation-aware replay
        finder = CompilationErrorFinder(frame, e)
        fail_idx, fail_op, last_good_df = finder.find_failing_operation()

        if fail_op and last_good_df is not None:
            # Build enhanced error using Pydantic models
            enhanced_error = _build_enhanced_compilation_error(
                exception=e,
                operation=fail_op,
                operation_index=fail_idx,
                dataframe=last_good_df,
                total_operations=len(frame._computation_graph),
            )

            # Determine output format based on context
            if _is_interactive_console():
                error_message = enhanced_error.to_console(use_emoji=True)
            else:
                error_message = enhanced_error.to_console(use_emoji=False)

            # Instead of creating a new exception, modify the original
            # This prevents re-wrapping and re-processing
            e.args = (error_message,)  # Update the message

            # Attach structured data for programmatic access
            e.enhanced_error = enhanced_error
            e.llm_context = enhanced_error.to_llm_context()

            # Attach methods directly to the exception instance
            def _to_json():
                return enhanced_error.to_json()

            def _to_dict():
                return enhanced_error.to_dict()

            e.to_json = _to_json
            e.to_dict = _to_dict

            # Mark as already processed
            e._enhanced_processed = True

            raise e
        # Fallback to basic handling if we can't find the operation
        return _handle_basic_column_error(frame, e)

    except Exception as finder_error:
        # If enhanced handling fails, just log and re-raise original
        logger.debug(f"Enhanced compilation error finder failed: {finder_error}")
        raise e


def _handle_compilation_error(frame: ActuarialFrame, e: Exception):
    """Handle Polars compilation/optimization errors with helpful messages."""
    from ..util import get_error_mode

    error_mode = get_error_mode()
    error_msg = str(e)

    # NEW: Check for column reference errors with enhanced handling
    if _is_column_reference_compilation_error(e):
        if error_mode in ["enhanced", "debug"] and frame._computation_graph:
            _handle_compilation_error_enhanced(frame, e)
            # Should never reach here as enhanced handler always raises
        else:
            # Fall back to basic column error handling
            _handle_basic_column_error(frame, e)
            # Should never reach here as basic handler always raises

    # Check for common compilation error patterns
    if "got invalid or ambiguous dtypes" in error_msg:
        # Extract the problematic expression and operation
        problem_expr = None
        operation_name = None

        # Try to extract the expression causing the issue
        if "in expression" in error_msg:
            try:
                expr_part = error_msg.split("in expression '")[1].split("'")[0]
                problem_expr = expr_part
            except (IndexError, AttributeError):
                pass

        # Try to extract the operation from the resolved plan
        if "FAILED HERE RESOLVING" in error_msg:
            try:
                lines = error_msg.split("\n")
                for line in lines:
                    if "FAILED HERE RESOLVING" in line:
                        operation_name = (
                            line.split("'")[1] if "'" in line else "query optimization"
                        )
                        break
            except (IndexError, AttributeError):
                operation_name = "query optimization"

        # Create enhanced error message for type coercion issues
        enhanced_msg = _format_type_coercion_error(
            error_msg,
            problem_expr,
            operation_name,
            frame,
        )

        if error_mode in ["enhanced", "debug"]:
            # Create enhanced exception with helpful context
            new_exception = type(e)(enhanced_msg)
            if hasattr(e, "__cause__"):
                new_exception.__cause__ = e.__cause__

            # Add LLM context for programmatic access
            new_exception.llm_context = {
                "error_type": "compilation_error",
                "sub_type": "type_coercion",
                "problem_expression": problem_expr,
                "operation": operation_name,
                "suggestions": [
                    "Ensure consistent data types in operations (all scalar or all list)",
                    "Use explicit casting with .cast() to resolve type ambiguity",
                    "Check if list columns are being mixed with scalar operations",
                    "Consider using .explode() to convert list columns to scalar before operations",
                ],
                "original_error": error_msg,
            }

            raise new_exception from e

    # For other compilation errors, provide general enhancement
    if error_mode in ["enhanced", "debug"]:
        enhanced_msg = f"""
❌ Query compilation failed during optimization

Failed operation: query optimization

💡 Polars compilation error:
{error_msg}

📊 Suggestions:
   • Check for data type mismatches in your expressions
   • Ensure column operations use consistent types
   • Consider breaking complex expressions into simpler steps
   • Use explicit type casting where needed

🔍 This error occurred during query optimization before execution.
   The computation graph was built successfully but Polars couldn't 
   optimize the query due to type inference issues.
"""

        new_exception = type(e)(enhanced_msg)
        new_exception.llm_context = {
            "error_type": "compilation_error",
            "sub_type": "optimization_failure",
            "original_error": error_msg,
            "suggestions": [
                "Check for data type mismatches in expressions",
                "Ensure column operations use consistent types",
                "Break complex expressions into simpler steps",
                "Use explicit type casting where needed",
            ],
        }
        raise new_exception from e

    # Basic mode - just re-raise original
    raise e


def _is_interactive_console() -> bool:
    """Detect if running in an interactive console."""
    import sys

    # Check if stdout is a terminal
    if not hasattr(sys.stdout, "isatty"):
        return False

    if not sys.stdout.isatty():
        return False

    # Check for common CI environment variables
    ci_vars = ["CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", "GITLAB_CI"]
    if any(os.environ.get(var) for var in ci_vars):
        return False

    # Check for Jupyter/IPython
    try:
        get_ipython()  # type: ignore
        return True
    except NameError:
        pass

    return True


def _build_enhanced_compilation_error(
    exception: Exception,
    operation: TracedOperation,
    operation_index: int,
    dataframe: pl.DataFrame,
    total_operations: int,
) -> EnhancedError:
    """Build structured enhanced error from components."""
    from .models import (
        ColumnInfo,
        DataFrameContext,
        EnhancedError,
        ErrorMetadata,
        ErrorType,
        OperationContext,
        SourceLocation,
    )

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
        alias=operation.alias,
        expression=str(operation.expression),
        source=SourceLocation(
            file_path=operation.metadata.file_name,
            line_number=operation.metadata.line_number,
            function_name=operation.metadata.function_name,
            source_line=operation.metadata.source_line,
        ),
        expected_dtype=str(operation.expected_dtype)
        if operation.expected_dtype
        else None,
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
        operation=operation,
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
    """Classify the error type based on exception."""
    from .models import ErrorType

    if isinstance(exception, pl.exceptions.ColumnNotFoundError):
        return ErrorType.COLUMN_NOT_FOUND

    error_str = str(exception)
    if "type mismatch" in error_str or "ambiguous dtypes" in error_str:
        return ErrorType.TYPE_MISMATCH
    if "invalid operation" in error_str:
        return ErrorType.INVALID_OPERATION
    if "schema" in error_str:
        return ErrorType.SCHEMA_CONFLICT

    return ErrorType.UNKNOWN


def _generate_compilation_suggestions(
    error_type: ErrorType,
    missing_column: str | None,
    available_columns: list[str],
    operation: TracedOperation,
) -> list[Suggestion]:
    """Generate suggestions for compilation errors."""
    from .models import ErrorType, Suggestion, SuggestionType

    suggestions = []

    if error_type == ErrorType.COLUMN_NOT_FOUND and missing_column:
        # Find similar columns
        similar_cols = _find_similar_columns(missing_column, available_columns)

        for col in similar_cols[:3]:  # Top 3 suggestions
            suggestions.append(
                Suggestion(
                    text=f"Did you mean '{col}'?",
                    type=SuggestionType.TYPO_FIX,
                    relevance_score=0.9,
                    code_example=f"{operation.alias} = pl.col('{col}')",
                ),
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
        if operation.metadata.line_number > 5:
            suggestions.append(
                Suggestion(
                    text=f"Check operations before line {operation.metadata.line_number} which might create this column",
                    type=SuggestionType.DOCUMENTATION,
                    relevance_score=0.6,
                ),
            )

    elif error_type == ErrorType.TYPE_MISMATCH:
        suggestions.append(
            Suggestion(
                text="Use .cast() to explicitly convert types",
                type=SuggestionType.TYPE_CAST,
                relevance_score=0.9,
                code_example="col('amount').cast(pl.Float64)",
            ),
        )

        suggestions.append(
            Suggestion(
                text="Check if mixing list columns with scalar operations",
                type=SuggestionType.DOCUMENTATION,
                relevance_score=0.8,
            ),
        )

    return suggestions


def _format_type_coercion_error(
    error_msg: str,
    problem_expr: str | None,
    operation_name: str | None,
    frame: ActuarialFrame,
) -> str:
    """Format a type coercion error with helpful suggestions."""
    # Extract the problematic types if available
    problematic_types = None
    if "got invalid or ambiguous dtypes:" in error_msg:
        try:
            types_part = error_msg.split("got invalid or ambiguous dtypes: '")[1].split(
                "'",
            )[0]
            problematic_types = types_part
        except (IndexError, AttributeError):
            pass

    enhanced_msg = f"""❌ Data type mismatch in {operation_name or "operation"}

🔍 Problem: {problem_expr or "Expression"} has ambiguous types: {problematic_types or "mixed types"}

💡 Common causes:
   • Mixing list columns with scalar values
   • Operations between different numeric types  
   • Missing type specifications in complex expressions

📊 Suggestions:
   • Use .cast() to explicitly convert types: col.cast(pl.Float64)
   • Check if you're mixing list operations with scalar operations
   • For list columns, consider .explode() to convert to scalar first
   • Ensure fill_null() uses compatible types (e.g., 0.0 for float lists)

🛠️  Example fixes:
   • Instead of: list_col.fill_null(0.0)
   • Try: list_col.fill_null([0.0]) for list types
   • Or: list_col.explode().fill_null(0.0) to work with scalars

Original Polars error:
{error_msg}"""

    return enhanced_msg


def _handle_validation_error(frame: ActuarialFrame, e: ValidationError):
    """Handle validation errors with enhanced formatting."""
    # Import formatter locally to avoid circular imports
    from .formatter import ValidationErrorFormatter
    
    # Create formatter and generate enhanced message
    formatter = ValidationErrorFormatter(e, frame)
    enhanced_msg = formatter.format_error()
    llm_context = formatter.format_for_llm()
    
    # Update the exception with enhanced message
    e.args = (enhanced_msg,)
    e._enhanced_message = enhanced_msg
    e.llm_context = llm_context
    e._enhanced_processed = True
    
    # Re-raise the enhanced exception
    raise e


def _handle_attribute_error(frame: ActuarialFrame, e: AttributeError):
    """Handle attribute errors with enhanced formatting."""
    # Import formatter locally to avoid circular imports
    from .formatter import AttributeErrorFormatter
    
    # Get source location if not already attached
    source_location = getattr(e, 'source_location', None)
    
    # Create formatter and generate enhanced message
    formatter = AttributeErrorFormatter(e, source_location, frame)
    enhanced_msg = formatter.format_error()
    llm_context = formatter.format_for_llm()
    
    # Update the exception with enhanced message
    e.args = (enhanced_msg,)
    e._enhanced_message = enhanced_msg
    e.llm_context = llm_context
    e._enhanced_processed = True
    
    # Re-raise the enhanced exception
    raise e
