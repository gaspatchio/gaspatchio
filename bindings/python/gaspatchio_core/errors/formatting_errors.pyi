# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..frame.base import ActuarialFrame

class PerformanceWarning(Warning):
    """Warning for potential performance issues."""

    ...

def _extract_missing_column_robust(error_str: str) -> str | None:
    """Attempts to extract the missing column name from specific error patterns.
    Assumes error_str is derived from `str(ColumnNotFoundError)` or similar.
    """
    ...

def _find_similar_columns(
    missing_col: str, available_cols: List[str], max_suggestions: int = ...
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
    ...

def _format_column_error(
    frame: ActuarialFrame,
    original_exception: Exception,
    missing_col: str,
    original_msg: str,
) -> Exception:
    """Formats a helpful error message for a missing column, including original error."""
    ...

def _handle_execution_error(frame: ActuarialFrame, e: Exception) -> None:
    """Handle errors during collect() or profile(), providing context."""
    ...
