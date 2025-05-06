from __future__ import annotations

import logging as log
import re
from typing import TYPE_CHECKING, List

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

    pass


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
    missing_col: str, available_cols: List[str], max_suggestions=5
) -> List[str]:
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

    # Only add suggestions if similar_cols is not empty
    if similar_cols:
        error_msg += (
            "Did you mean one of these?\\n - " + "\\n - ".join(similar_cols) + "\\n\\n"
        )

    # Always list available columns
    error_msg += "Available columns are:\\n - " + "\\n - ".join(available_cols)
    error_msg += (
        f"\\n\\nOriginal Polars Error: {original_msg}"  # Include original message
    )

    # Return a new exception of the original type with the formatted message
    return type(original_exception)(error_msg)


def _handle_execution_error(frame: "ActuarialFrame", e: Exception):
    """Handle errors during collect() or profile(), providing context."""
    error_msg = str(e)
    error_msg_str = str(error_msg) if error_msg is not None else ""

    missing_col: str | None = None

    # Attempt extraction only if it's a known Polars error type or the message strongly suggests a column issue
    # Use `pl.exceptions.ColumnNotFoundError` when Polars is updated
    if isinstance(e, pl.ColumnNotFoundError) or (
        isinstance(e, Exception)
        and (
            "ColumnNotFoundError" in error_msg_str
            or "not found" in error_msg_str
            or "unable to find column" in error_msg_str
            or "MissingField"
            in error_msg_str  # Add other relevant Polars messages if needed
        )
    ):
        missing_col = _extract_missing_column_robust(error_msg_str)

        # Fallback only if primary extraction failed but context suggests it *should* be there
        if not missing_col and isinstance(e, pl.ColumnNotFoundError):
            match = re.search(r"column: \\\"(.*?)\\\" not found", error_msg_str)
            if match:
                missing_col = match.group(1)

    # If a missing column *was* identified, format the error
    if missing_col:
        try:
            formatted_exception = _format_column_error(
                frame, e, missing_col, error_msg_str
            )
            if getattr(frame, "_verbose", False):
                # Log the STR representation of the formatted exception
                log.error(f"Execution failed: {str(formatted_exception)}")
            raise formatted_exception from e
        except Exception as format_err:
            # If formatting itself fails, log the formatting error and raise the original
            log.error(
                f"Failed to format column error for '{missing_col}': {format_err}"
            )
            if getattr(frame, "_verbose", False):
                log.error(f"Original execution error: {error_msg_str}")
            raise e from None  # Raise original error
    else:
        # If no missing column identified by checks, log original and re-raise
        if getattr(frame, "_verbose", False):
            log.error(
                f"Execution failed (non-column error or unidentified): {error_msg_str}"
            )
        raise e
