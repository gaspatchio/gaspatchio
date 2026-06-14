# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Utilities for working with stack frames and source location."""

import inspect
import linecache
from pathlib import Path
from typing import Any, Optional, Tuple

from .constants import INTERNAL_MODULE_PATTERNS, FRAMEWORK_FILE_PATTERNS, MAX_MULTILINE_CAPTURE
from .models import SourceLocation


def is_user_code_frame(filename: str) -> bool:
    """Check if a frame is from user code (not internal framework).
    
    Args:
        filename: The filename from the frame
        
    Returns:
        True if this appears to be user code, False if it's framework code
    """
    # Check if it's an internal module
    for pattern in INTERNAL_MODULE_PATTERNS:
        if pattern in filename:
            return False
    
    # Check if it's a framework file
    for pattern in FRAMEWORK_FILE_PATTERNS:
        if filename.endswith(pattern):
            return False
    
    # Check for other indicators of non-user code
    if "<" in filename or ">" in filename:  # Built-in or generated code
        return False
    
    # If it has a .py extension and isn't excluded, it's probably user code
    return filename.endswith(".py")


def find_user_code_frame(start_frame: Optional[Any] = None) -> Optional[inspect.FrameInfo]:
    """Find the first frame from user code in the call stack.
    
    Args:
        start_frame: Frame to start searching from (defaults to current frame)
        
    Returns:
        The first FrameInfo from user code, or None if not found
    """
    if start_frame is None:
        start_frame = inspect.currentframe()
    
    if not start_frame:
        return None
    
    # Get all outer frames
    try:
        frames = inspect.getouterframes(start_frame)
        for frame_info in frames:
            if is_user_code_frame(frame_info.filename):
                return frame_info
    except Exception:
        pass
    
    return None


def capture_multiline_source(filename: str, line_number: int, max_lines: int = MAX_MULTILINE_CAPTURE) -> str:
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
        with open(filename, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        # Fallback to linecache for single line
        line = linecache.getline(filename, line_number)
        return line.rstrip() if line else ""
    
    # Check bounds
    start_idx = line_number - 1  # Convert to 0-indexed
    if start_idx < 0 or start_idx >= len(lines):
        return ""
    
    # Start with the current line
    source_lines = [lines[start_idx].rstrip()]
    
    # Count parentheses/brackets/braces
    open_chars = source_lines[0].count('(') + source_lines[0].count('[') + source_lines[0].count('{')
    close_chars = source_lines[0].count(')') + source_lines[0].count(']') + source_lines[0].count('}')
    
    # Continue reading lines until balanced or max reached
    line_idx = start_idx + 1
    while open_chars > close_chars and line_idx < len(lines) and len(source_lines) < max_lines:
        next_line = lines[line_idx].rstrip()
        source_lines.append(next_line)
        
        # Update counts
        open_chars += next_line.count('(') + next_line.count('[') + next_line.count('{')
        close_chars += next_line.count(')') + next_line.count(']') + next_line.count('}')
        
        line_idx += 1
    
    return '\n'.join(source_lines)


def get_source_location(frame: Any, capture_multiline: bool = True) -> Optional[SourceLocation]:
    """Extract source location information from a frame.
    
    Args:
        frame: Frame object or FrameInfo
        capture_multiline: Whether to capture multi-line statements
        
    Returns:
        SourceLocation object or None if extraction fails
    """
    try:
        # Handle different frame types
        if hasattr(frame, 'filename') and hasattr(frame, 'lineno'):
            # FrameInfo object
            filename = frame.filename
            line_number = frame.lineno
            function_name = frame.function if hasattr(frame, 'function') else frame.frame.f_code.co_name
        elif hasattr(frame, 'f_code'):
            # Raw frame object
            filename = frame.f_code.co_filename
            line_number = frame.f_lineno
            function_name = frame.f_code.co_name
        else:
            return None
        
        # Get source code
        if capture_multiline:
            source_line = capture_multiline_source(filename, line_number)
        else:
            source_line = linecache.getline(filename, line_number).strip()
        
        return SourceLocation(
            file_path=filename,
            line_number=line_number,
            function_name=function_name if function_name != '<module>' else None,
            source_line=source_line if source_line else None
        )
    except Exception:
        return None


def find_calling_user_code() -> Tuple[Optional[SourceLocation], Optional[Any]]:
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