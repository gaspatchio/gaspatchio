"""
Data classes and utilities for capturing operation metadata.

This module provides the core metadata structures for tracking ActuarialFrame
operations with source location information for enhanced error reporting.
"""

import inspect
import linecache
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class OperationMetadata:
    """Metadata for a traced operation including source location."""

    file_name: str
    line_number: int
    source_line: str
    function_name: str | None = None
    timestamp: float | None = None  # For performance debugging

    @property
    def is_jupyter(self) -> bool:
        """Check if this metadata comes from a Jupyter notebook."""
        return "<ipython-input-" in self.file_name or "ipython-input-" in self.file_name

    @property
    def display_filename(self) -> str:
        """Get a human-readable filename for display."""
        if self.is_jupyter:
            # Extract cell number from Jupyter filename
            if "<ipython-input-" in self.file_name:
                try:
                    cell_part = self.file_name.split("<ipython-input-")[1].split(">")[0]
                    cell_num = cell_part.split("-")[0]
                    # Check if cell_num is actually a number
                    int(cell_num)  # This will raise ValueError if not a number
                    return f"Jupyter Cell {cell_num}"
                except (IndexError, ValueError):
                    return "Jupyter Notebook"
            return "Jupyter Notebook"
        return self.file_name


@dataclass
class TracedOperation:
    """Complete operation with metadata for error tracking."""

    alias: str
    expression: Any  # pl.Expr, but avoiding import here to prevent circular deps
    metadata: OperationMetadata
    expected_dtype: Any | None = None  # pl.DataType, but avoiding import here


def capture_source_context(
    depth: int = 2,
    include_timestamp: bool = False,
) -> OperationMetadata:
    """
    Capture source context from the call stack.

    Args:
        depth: How many frames up to look (2 = caller of caller)
        include_timestamp: Whether to include timestamp for performance debugging

    Returns:
        OperationMetadata with file, line, and source information

    """
    frame = inspect.currentframe()
    try:
        # Navigate up the stack to the desired depth
        for _ in range(depth):
            if frame.f_back is None:
                break
            frame = frame.f_back

        filename = frame.f_code.co_filename
        lineno = frame.f_lineno
        function_name = frame.f_code.co_name

        # Get source line safely with special handling for different contexts
        source_line = _get_source_line_safe(filename, lineno)

        timestamp = time.time() if include_timestamp else None

        return OperationMetadata(
            file_name=filename,
            line_number=lineno,
            source_line=source_line,
            function_name=function_name,
            timestamp=timestamp,
        )
    finally:
        # Clean up frame reference to avoid memory leaks
        del frame


def _get_source_line_safe(filename: str, lineno: int) -> str:
    """
    Safely get source line with fallbacks for different environments.

    Args:
        filename: Source filename
        lineno: Line number

    Returns:
        Source line text or fallback message

    """
    try:
        source_line = linecache.getline(filename, lineno).strip()
        if source_line:
            return source_line
    except Exception:
        pass

    # Fallback for different contexts
    if "<ipython-input-" in filename or "ipython-input-" in filename:
        return "<Jupyter notebook cell>"
    if filename == "<stdin>":
        return "<interactive input>"
    if filename == "<string>":
        return "<compiled string>"
    if filename.endswith(".pyc") or "__pycache__" in filename:
        return "<compiled code>"
    return "<source unavailable>"
