from __future__ import annotations

import logging as log
import re
from typing import TYPE_CHECKING

import polars as pl  # Import polars for exception type checking

# Import thefuzz only if available, provide fallback
try:
    from thefuzz import fuzz
except ImportError:
    fuzz = None

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


def _format_column_error(
    frame: ActuarialFrame,
    original_exception: Exception,
    missing_col: str,
    original_msg: str,
) -> Exception:
    """Formats a helpful error message for a missing column, including original error."""
    try:
        # Use columns property which works for both Lazy and Eager frames
        available_cols = frame._df.columns
    except Exception:
        available_cols = frame._column_order  # Fallback

    similar_cols = _find_similar_columns(missing_col, available_cols)

    # Format error message with proper newlines
    error_msg = f"Column '{missing_col}' not found in the DataFrame.\n\n"

    # Only add suggestions if similar_cols is not empty
    if similar_cols:
        error_msg += (
            "Did you mean one of these?\n - " + "\n - ".join(similar_cols) + "\n\n"
        )

    # Always list available columns
    error_msg += "Available columns are:\n - " + "\n - ".join(available_cols)
    error_msg += (
        f"\n\nOriginal Polars Error: {original_msg}"  # Include original message
    )

    # Return a new exception of the original type with the formatted message
    return type(original_exception)(error_msg)


def _handle_execution_error(frame: ActuarialFrame, e: Exception):
    """Handle errors during collect() or profile(), providing enhanced context and suggestions."""
    # Import locally to avoid circular dependencies and only import when needed
    from ..util import get_error_mode

    # Check if we should use enhanced error handling
    error_mode = get_error_mode()

    # Early exit for production mode - just re-raise
    if not (
        frame._tracing or frame._mode == "debug" or error_mode in ["enhanced", "debug"]
    ):
        raise e

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

                    # Create new exception and store LLM context for programmatic access
                    new_exception = type(e)(enhanced_msg)
                    new_exception.llm_context = llm_context

                    # Log enhanced error if verbose mode is on
                    if getattr(frame, "_verbose", False):
                        log.info(
                            f"Enhanced error handling applied: operation at index {fail_idx}",
                        )
                        log.debug(f"Enhanced error details: {enhanced_msg}")

                    raise new_exception from e
                except Exception as format_step_error:
                    # Log which specific step failed
                    if getattr(frame, "_verbose", False):
                        log.exception(
                            f"Specific formatting step failed: {format_step_error}",
                        )
                        log.exception("Full traceback for formatting failure:")
                    raise format_step_error
            # No metadata available, log this case
            if getattr(frame, "_verbose", False):
                log.debug(
                    "Enhanced error handling: no metadata available for failing operation",
                )

        except Exception as format_error:
            # If enhanced error handling fails, fall back to basic formatting
            if getattr(frame, "_verbose", False):
                log.warning(
                    f"Enhanced error handling failed: {format_error}, falling back to basic formatting",
                )

    # Fall back to basic column error formatting for column-related errors
    _handle_basic_column_error(frame, e)


def _handle_basic_column_error(frame: ActuarialFrame, e: Exception):
    """Handle basic column errors with similarity suggestions (fallback method)."""
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
            formatted_exception = _format_column_error(
                frame,
                e,
                missing_col,
                error_msg_str,
            )
            if getattr(frame, "_verbose", False):
                log.error(f"Column error formatted: {missing_col}")
            raise formatted_exception from e
        except Exception as format_err:
            # If formatting itself fails, log the formatting error and raise the original
            log.exception(
                f"Failed to format column error for '{missing_col}': {format_err}",
            )
            if getattr(frame, "_verbose", False):
                log.exception(f"Original execution error: {error_msg_str}")
            raise e from None  # Raise original error
    else:
        # If no missing column identified by checks, log original and re-raise
        if getattr(frame, "_verbose", False):
            log.error(
                f"Execution failed (non-column error or unidentified): {error_msg_str}",
            )
        raise e


def _handle_compilation_error(frame: "ActuarialFrame", e: Exception):
    """Handle Polars compilation/optimization errors with helpful messages."""
    from ..util import get_error_mode
    
    error_mode = get_error_mode()
    error_msg = str(e)
    
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
                lines = error_msg.split('\n')
                for line in lines:
                    if "FAILED HERE RESOLVING" in line:
                        operation_name = line.split("'")[1] if "'" in line else "query optimization"
                        break
            except (IndexError, AttributeError):
                operation_name = "query optimization"
        
        # Create enhanced error message for type coercion issues
        enhanced_msg = _format_type_coercion_error(
            error_msg, problem_expr, operation_name, frame
        )
        
        if error_mode in ["enhanced", "debug"]:
            # Create enhanced exception with helpful context
            new_exception = type(e)(enhanced_msg)
            if hasattr(e, '__cause__'):
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
                    "Consider using .explode() to convert list columns to scalar before operations"
                ],
                "original_error": error_msg
            }
            
            raise new_exception from e
    
    # For other compilation errors, provide general enhancement
    if error_mode in ["enhanced", "debug"]:
        enhanced_msg = f"""
❌ Query compilation failed during optimization

Failed operation: {operation_name or 'query optimization'}

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
                "Use explicit type casting where needed"
            ]
        }
        raise new_exception from e
    
    # Basic mode - just re-raise original
    raise e


def _format_type_coercion_error(error_msg: str, problem_expr: str | None, operation_name: str | None, frame: "ActuarialFrame") -> str:
    """Format a type coercion error with helpful suggestions."""
    
    # Extract the problematic types if available
    problematic_types = None
    if "got invalid or ambiguous dtypes:" in error_msg:
        try:
            types_part = error_msg.split("got invalid or ambiguous dtypes: '")[1].split("'")[0]
            problematic_types = types_part
        except (IndexError, AttributeError):
            pass
    
    enhanced_msg = f"""❌ Data type mismatch in {operation_name or 'operation'}

🔍 Problem: {problem_expr or 'Expression'} has ambiguous types: {problematic_types or 'mixed types'}

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
