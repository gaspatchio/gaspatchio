from __future__ import annotations

import logging as log
import re
from typing import TYPE_CHECKING, List

from thefuzz import process

if TYPE_CHECKING:
    # Avoid circular import during runtime, import for type checking only
    from ..frame.base import ActuarialFrame


class PerformanceWarning(Warning):
    """Warning for potential performance issues."""

    pass


def _extract_missing_column_robust(error_str: str) -> str | None:
    """Attempts to extract the missing column name from specific error patterns.
    Assumes error_str is derived from `str(ColumnNotFoundError)` or similar.
    """
    # Pattern 1: Starts with column name, followed by newline
    # Example: 'invalid_start\n\nResolved plan...'
    match = re.match(r"^([^\s\'\"]+)\n", error_str)  # Raw string for regex
    if match:
        return match.group(1)

    # Pattern 2: contains "column 'col_name' not found"
    match = re.search(
        r"column\s*\'([^\']*)\'\s*not found", error_str, re.IGNORECASE
    )  # Raw string
    if match:
        return match.group(1)

    # Pattern 3: contains "unable to find column \"col_name\""
    match = re.search(
        r"unable to find column \\\"([^\\\"]*)\\\"", error_str
    )  # Raw string
    if match:
        return match.group(1)

    # Pattern 4: Format like "ColumnNotFoundError: policy_duration_as_int"
    match = re.search(r"ColumnNotFoundError:\s*([^\s\'\"]+)", error_str)  # Raw string
    if match:
        return match.group(1)

    # Pattern 5 (handled in _handle_execution_error)

    # If no patterns match, return None
    return None


def _find_similar_columns(
    missing_col: str, available_cols: List[str], max_suggestions=5
) -> List[str]:
    """
    Find column names similar to the missing column using thefuzz library.

    Args:
        missing_col: The missing column name
        available_cols: List of available column names
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of column names similar to the missing one
    """
    if not missing_col or not available_cols:
        return []

    # Use process.extract to find the most similar columns
    # score_cutoff is 0-100, higher is better
    matches = process.extract(
        missing_col, available_cols, limit=max_suggestions, score_cutoff=60
    )  # Adjust score_cutoff as needed

    # Extract just the column names
    similar_cols = [match[0] for match in matches]
    return similar_cols


def _format_column_error(
    frame: "ActuarialFrame",
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

    # Use double backslashes for newlines in f-string
    error_msg = f"Column '{missing_col}' not found in the DataFrame.\\n\\n"

    if similar_cols:
        error_msg += (
            "Did you mean one of these?\\n - " + "\\n - ".join(similar_cols) + "\\n\\n"
        )

    error_msg += "Available columns are:\\n - " + "\\n - ".join(available_cols)
    error_msg += (
        f"\\n\\nOriginal Polars Error: {original_msg}"  # Include original message
    )

    # Return a new exception of the original type with the formatted message
    return type(original_exception)(error_msg)


def _handle_execution_error(frame: "ActuarialFrame", e: Exception):
    """Handle errors during collect() or profile(), providing context."""
    error_msg = str(e)
    # Ensure error message is string
    error_msg_str = str(error_msg) if error_msg is not None else ""

    # Default column name if extraction fails
    missing_col: str | None = None

    # Try robust extraction first
    missing_col = _extract_missing_column_robust(error_msg_str)

    # Fallback to simple regex if robust method fails
    if not missing_col:
        match = re.search(
            r"column: \\\"(.*?)\\\" not found", error_msg_str
        )  # Raw string
        if match:
            missing_col = match.group(1)

    # Add Pattern 5 from _extract_missing_column_robust here, as it needs frame access
    if not missing_col:
        try:
            for col in frame._column_order:
                if col in error_msg_str:
                    missing_col = col
                    break  # Take the first match
        except AttributeError:
            pass  # frame might not have _column_order yet

    # If a missing column is identified, try to provide suggestions
    if missing_col:
        formatted_exception = _format_column_error(frame, e, missing_col, error_msg_str)
        # Consider logging the original traceback here if needed
        if getattr(frame, "_verbose", False):  # Safely access _verbose
            log.error(f"Execution failed: {formatted_exception}")
            # log.exception("Original Traceback:", exc_info=e) # Optional: Log full traceback
        raise formatted_exception from e  # Raise the formatted error
    else:
        # If no specific column identified, just log and re-raise
        if getattr(frame, "_verbose", False):  # Safely access _verbose
            log.error(f"Execution failed: {error_msg_str}")
            # log.exception("Traceback:", exc_info=e) # Optional: Log full traceback
        # Re-raise the original exception if no specific formatting applied
        raise e
