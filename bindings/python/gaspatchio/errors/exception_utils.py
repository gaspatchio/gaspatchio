# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Utilities for enhancing exceptions with source location."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .frame_utils import get_source_location, is_user_code_frame

if TYPE_CHECKING:
    from types import FrameType, TracebackType

    from .models import SourceLocation


def attach(exc: BaseException, **attributes: object) -> None:
    """Set attributes on an exception whose class does not declare them.

    The error handlers decorate whatever was raised -- a Polars error, an
    ``AttributeError``, a ``ValidationError`` -- with what they found about
    it: its source location, the structured report, a marker that it has
    been through them already. Those classes are not this package's to give
    attributes to, so each one goes on the instance.

    Args:
        exc: The exception to decorate
        **attributes: Each attribute's name and value

    """
    for name, value in attributes.items():
        setattr(exc, name, value)


def extract_user_frame_from_exception(exc: Exception) -> SourceLocation | None:
    """Extract the source location of user code from an exception's traceback.

    Args:
        exc: The exception to extract location from

    Returns:
        SourceLocation of the user code that caused the error, or None

    """
    # Get the traceback from the exception
    tb = exc.__traceback__
    if not tb:
        return None

    # Walk through the traceback frames
    while tb:
        frame = tb.tb_frame
        filename = frame.f_code.co_filename

        # Check if this is user code
        if is_user_code_frame(filename):
            # Create a mock frame info object for get_source_location
            class FrameInfo:
                def __init__(self, frame: FrameType, tb: TracebackType) -> None:
                    self.filename = frame.f_code.co_filename
                    self.lineno = tb.tb_lineno
                    self.function = frame.f_code.co_name
                    self.frame = frame

            frame_info = FrameInfo(frame, tb)
            return get_source_location(frame_info, capture_multiline=True)

        tb = tb.tb_next

    return None


def enhance_exception_with_location(exc: Exception) -> None:
    """Enhance an exception with source location if not already present.

    This modifies the exception in-place by adding a source_location attribute.

    Args:
        exc: The exception to enhance

    """
    # Skip if already has source location
    if getattr(exc, "source_location", None):
        return

    # Try to extract location from traceback
    location = extract_user_frame_from_exception(exc)
    if location:
        attach(exc, source_location=location)
