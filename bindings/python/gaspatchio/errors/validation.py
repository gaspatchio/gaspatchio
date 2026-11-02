# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Enhanced validation error handling with source context capture."""

import functools
import linecache
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict, Unpack

from gaspatchio.errors.frame_utils import (
    find_calling_user_code,
)
from gaspatchio.errors.models import SourceLocation
from gaspatchio.util import _ENHANCING_ERROR_MODES, _ERROR_MODE_OFF, get_error_mode


@dataclass(slots=True)
class ValidationContext:
    """Context information for validation errors."""

    valid_options: list[str] | None = None
    provided_value: Any | None = None
    expected_type: type | None = None
    actual_type: type | None = None
    parameter_name: str | None = None
    additional_info: dict[str, Any] | None = None


class _ValidationContextFields(TypedDict, total=False):
    """The keywords ``ValidationError`` passes on to ``ValidationContext``."""

    valid_options: list[str] | None
    provided_value: object
    expected_type: type | None
    actual_type: type | None
    parameter_name: str | None
    additional_info: dict[str, Any] | None


class ValidationError(ValueError):
    """Enhanced validation error with source context.

    This error class extends ValueError to maintain backward compatibility
    while adding rich context for better error messages.
    """

    def __init__(
        self, message: str, **context: Unpack[_ValidationContextFields]
    ) -> None:
        """Initialize validation error with context.

        Args:
            message: The error message
            **context: Additional context passed to ValidationContext

        """
        super().__init__(message)
        self.context = ValidationContext(**context)
        self.source_location: SourceLocation | None = None


def _get_frame_from_args(args: tuple[object, ...]) -> object | None:
    """Extract ActuarialFrame from function arguments if present."""
    # A method's frame follows self or cls, so the second argument is asked
    # first; a function's frame is its first.
    for candidate in (*args[1:2], *args[:1]):
        if hasattr(candidate, "_mode"):
            return candidate
    return None


def _should_enhance_error(frame: object | None) -> bool:
    """Report whether a caught validation error should be rewritten.

    ``AF_ERROR_MODE=off`` is the operator's kill-switch and nothing
    overrides it -- a frame in debug mode included. Short of that, a frame
    running in debug mode enhances whatever the session is set to.
    Otherwise the session-wide error mode decides, and it decides on its
    own: a validator called with no frame among its arguments -- a plain
    function taking a rate or a term -- is the ordinary case, and used to
    be excluded from enhancement entirely, which left the mode with
    nothing to switch on.

    Parameters
    ----------
    frame : ActuarialFrame or None
        The frame the decorated call was made against, if one was among
        its positional arguments.

    Returns
    -------
    bool
        Whether to rewrite the error with the caller's source location.

    """
    error_mode = get_error_mode()
    if error_mode == _ERROR_MODE_OFF:
        return False

    if frame is not None and getattr(frame, "_mode", None) == "debug":
        return True

    return error_mode in _ENHANCING_ERROR_MODES


def _caller_location() -> SourceLocation | None:
    """Locate the line outside this framework that made the failing call.

    Walks past every frame the framework's own machinery contributes --
    the same walk expression lineage uses to attribute a calculation --
    and reads the line it lands on. ``None`` when there is no such frame
    or the walk itself fails: a location is worth having but never worth
    losing the error over.

    Returns
    -------
    SourceLocation or None
        Where the caller made the call, or ``None`` if it cannot be
        established.

    """
    try:
        from gaspatchio.frame.calculations import (  # noqa: PLC0415 -- import cycle
            _MODULE_SCOPE_NAME,
            _nearest_external_frame,
        )

        frame = _nearest_external_frame()
        if frame is None:
            return None
        filename = frame.f_code.co_filename
        line_number = frame.f_lineno
        # A module-level frame's code object calls itself "<module>" -- a
        # marker for "no enclosing scope", not a function a reader could
        # open -- so it is normalized to None, as frame_utils does on its
        # own capture path. The source line is None when there is nothing
        # to read: an exec-compiled snippet, stdin, a bare REPL.
        function_name = frame.f_code.co_name
        return SourceLocation(
            file_path=filename,
            line_number=line_number,
            function_name=(
                None if function_name == _MODULE_SCOPE_NAME else function_name
            ),
            source_line=linecache.getline(filename, line_number).strip() or None,
        )
    except Exception:  # noqa: BLE001 -- never lose the error over its location
        return None


def _provided_value(error: Exception) -> str | None:
    """Read the offending value out of a ``"...: <value>"`` message.

    Validators in this codebase report the value they rejected after a
    colon (``"Invalid frequency: fortnightly"``). Recovering it lets the
    rewritten error carry it as context rather than only inside prose.

    Parameters
    ----------
    error : Exception
        The error the decorated function raised.

    Returns
    -------
    str or None
        The rejected value as written, or ``None`` if the message does
        not carry one.

    """
    message = str(error)
    if not isinstance(error, ValueError) or "Invalid" not in message:
        return None
    _, separator, tail = message.partition(":")
    if not separator:
        return None
    return tail.strip() or None


def capture_validation_context[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Capture the caller's source location onto a validation error.

    A validation helper knows the value is wrong; it does not know which
    line passed it. This decorator supplies that half: it catches the
    ``ValueError``, ``TypeError`` or ``KeyError`` the helper raised,
    finds the first frame outside the framework -- the model author's
    line -- and reports the failure from there. A plain error is
    converted to a ``ValidationError`` raised *from* the original, so the
    original message, type and traceback are all still on the chain; a
    ``ValidationError`` that arrives already typed keeps its identity and
    only gains the location.

    Enhancement applies in the ``enhanced`` and ``debug`` error modes,
    and under ``basic`` on a frame explicitly in debug mode. Under
    ``off`` the error propagates untouched whatever the frame asks for:
    the environment variable is the operator's kill-switch and a frame's
    own mode does not override it. Locating the caller can fail -- a
    frame with no readable source, an unresolvable stack -- and when it
    does the error is still raised, with no location on it. Nothing here
    swallows the failure it was handed.

    Parameters
    ----------
    func : Callable
        The validation function to wrap.

    Returns
    -------
    Callable
        ``func``, with its validation errors located.

    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except (ValueError, TypeError, KeyError) as e:
            # ValidationError is a ValueError, so it arrives here too.
            if not _should_enhance_error(_get_frame_from_args(args)):
                raise

            if isinstance(e, ValidationError):
                # Already the right type: it needs a location, not a
                # rewrite, and only if it does not already carry one.
                if e.source_location is None:
                    e.source_location = _caller_location()
                raise

            enhanced = ValidationError(str(e), provided_value=_provided_value(e))
            enhanced.source_location = _caller_location()
            raise enhanced from e

    return wrapper


def raise_validation_error(
    message: str,
    *,
    valid_options: list[str] | None = None,
    provided_value: object = None,
    expected_type: type | None = None,
    actual_type: type | None = None,
    parameter_name: str | None = None,
    **additional_context: object,
) -> None:
    """Raise a ValidationError with rich context.

    This is a convenience function for raising validation errors with
    all the context needed for helpful error messages.

    Args:
        message: The error message
        valid_options: List of valid options if applicable
        provided_value: The value that was provided
        expected_type: The expected type
        actual_type: The actual type received
        parameter_name: Name of the parameter being validated
        **additional_context: Any additional context

    Raises:
        ValidationError: Always raises with the provided context

    """
    error = ValidationError(
        message,
        valid_options=valid_options,
        provided_value=provided_value,
        expected_type=expected_type,
        actual_type=actual_type,
        parameter_name=parameter_name,
        additional_info=additional_context or None,
    )

    # Capture the caller's source location. find_calling_user_code walks
    # the stack and returns None where it finds no user frame; the one step
    # that can fail, reading the location, already answers None on failure.
    location, _ = find_calling_user_code()
    if location:
        error.source_location = location

    raise error
