# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Utilities for working with stack frames and source location."""

import inspect
import linecache
from pathlib import Path
from types import FrameType
from typing import Any, Protocol

from loguru import logger

from gaspatchio._source import is_framework_or_interpreter_file

from .constants import MAX_MULTILINE_CAPTURE
from .models import SourceLocation


class FrameRecord(Protocol):
    """A stack frame already read into the three facts a location needs.

    ``inspect.FrameInfo`` is one; so is the record
    ``extract_user_frame_from_exception`` builds from a traceback entry,
    whose line number is the traceback's rather than the frame's.
    """

    @property
    def filename(self) -> str:
        """Path of the file the frame's code came from."""
        ...

    @property
    def lineno(self) -> int:
        """Line the frame was executing."""
        ...

    @property
    def function(self) -> str:
        """Name of the code object, ``<module>`` at module scope."""
        ...


def is_user_code_frame(filename: str) -> bool:
    """Check if a frame is from user code (not internal framework).

    Decided by the path the frame's code object recorded, never by the
    file's name: a model in ``validation.py`` is the user's even though the
    framework has a module of that name, because the framework's copy lives
    under the framework's own package directory and the model's does not.
    ``is_framework_or_interpreter_file`` is the rule, the one the capture of
    each calculation's source line follows too.

    Args:
        filename: The filename from the frame

    Returns:
        True if this appears to be user code, False if it's framework code

    """
    return not is_framework_or_interpreter_file(filename)


def capture_multiline_source(
    filename: str, line_number: int, max_lines: int = MAX_MULTILINE_CAPTURE
) -> str:
    """Capture a potentially multi-line statement from source code.

    This function reads from the given line and continues until parentheses
    are balanced or max_lines is reached.

    Args:
        filename: Path to the source file
        line_number: Starting line number (1-indexed)
        max_lines: Maximum number of lines to capture

    Returns:
        The captured source code as a string

    """
    try:
        # Try to read the file
        with Path(filename).open(encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, ValueError):
        # Unreadable, or not UTF-8 (UnicodeDecodeError is a ValueError):
        # fall back to linecache for single line
        line = linecache.getline(filename, line_number)
        return line.rstrip() if line else ""

    # Check bounds
    start_idx = line_number - 1  # Convert to 0-indexed
    if start_idx < 0 or start_idx >= len(lines):
        return ""

    # Start with the current line
    source_lines = [lines[start_idx].rstrip()]

    # Count parentheses/brackets/braces
    open_chars = (
        source_lines[0].count("(")
        + source_lines[0].count("[")
        + source_lines[0].count("{")
    )
    close_chars = (
        source_lines[0].count(")")
        + source_lines[0].count("]")
        + source_lines[0].count("}")
    )

    # Continue reading lines until balanced or max reached
    line_idx = start_idx + 1
    while (
        open_chars > close_chars
        and line_idx < len(lines)
        and len(source_lines) < max_lines
    ):
        next_line = lines[line_idx].rstrip()
        source_lines.append(next_line)

        # Update counts
        open_chars += next_line.count("(") + next_line.count("[") + next_line.count("{")
        close_chars += (
            next_line.count(")") + next_line.count("]") + next_line.count("}")
        )

        line_idx += 1

    return "\n".join(source_lines)


def get_source_location(
    frame: FrameType | FrameRecord, capture_multiline: bool = True
) -> SourceLocation | None:
    """Extract source location information from a frame.

    Args:
        frame: A raw frame, or a record of one (``FrameRecord``)
        capture_multiline: Whether to capture multi-line statements

    Returns:
        SourceLocation object or None if extraction fails

    """
    try:
        if isinstance(frame, FrameType):
            filename = frame.f_code.co_filename
            line_number = frame.f_lineno
            function_name = frame.f_code.co_name
        else:
            filename = frame.filename
            line_number = frame.lineno
            function_name = frame.function

        # Get source code
        if capture_multiline:
            source_line = capture_multiline_source(filename, line_number)
        else:
            source_line = linecache.getline(filename, line_number).strip()

        return SourceLocation(
            file_path=filename,
            line_number=line_number,
            function_name=function_name if function_name != "<module>" else None,
            source_line=source_line or None,
        )
    # Runs while an error is already being raised, and its contract is None
    # on failure: a location is never worth losing that error over. What it
    # caught is logged.
    except Exception as failure:  # noqa: BLE001 -- see above
        logger.debug(f"No source location for the failing frame: {failure!r}")
        return None


def find_calling_user_code() -> tuple[SourceLocation | None, Any | None]:
    """Find the source location of the calling user code.

    This walks up the stack to find the first user code frame.

    Returns:
        Tuple of (SourceLocation, frame) or (None, None) if not found

    """
    current_frame = inspect.currentframe()
    if not current_frame:
        return None, None

    # Start from the caller of this function
    frame = current_frame.f_back
    while frame:
        filename = frame.f_code.co_filename
        if is_user_code_frame(filename):
            location = get_source_location(frame, capture_multiline=True)
            return location, frame
        frame = frame.f_back

    return None, None
