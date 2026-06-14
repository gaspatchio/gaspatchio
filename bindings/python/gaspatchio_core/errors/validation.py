# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Enhanced validation error handling with source context capture."""

import functools
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from gaspatchio_core.errors.models import SourceLocation
from gaspatchio_core.errors.frame_utils import find_calling_user_code, capture_multiline_source, is_user_code_frame


@dataclass(slots=True)
class ValidationContext:
    """Context information for validation errors."""
    valid_options: Optional[list[str]] = None
    provided_value: Optional[Any] = None
    expected_type: Optional[type] = None
    actual_type: Optional[type] = None
    parameter_name: Optional[str] = None
    additional_info: Optional[dict[str, Any]] = None


class ValidationError(ValueError):
    """Enhanced validation error with source context.
    
    This error class extends ValueError to maintain backward compatibility
    while adding rich context for better error messages.
    """
    
    def __init__(self, message: str, **context: Any) -> None:
        """Initialize validation error with context.
        
        Args:
            message: The error message
            **context: Additional context passed to ValidationContext
        """
        super().__init__(message)
        self.context = ValidationContext(**context)
        self.source_location: Optional[SourceLocation] = None
        self._enhanced_message: Optional[str] = None
    
    @property
    def enhanced_message(self) -> str:
        """Get enhanced error message with context."""
        if self._enhanced_message:
            return self._enhanced_message
        return str(self)


F = TypeVar("F", bound=Callable[..., Any])


def _get_frame_from_args(args: tuple[Any, ...]) -> Optional[Any]:
    """Extract ActuarialFrame from function arguments if present."""
    if not args:
        return None
    
    # Check if first arg is self/cls and second is frame
    if len(args) >= 2:
        # Check if it's a method call (first arg is self)
        first_arg = args[0]
        if hasattr(first_arg, "__class__"):
            # Check if second arg looks like a frame
            second_arg = args[1]
            if hasattr(second_arg, "_mode"):
                return second_arg
    
    # Check if first arg is frame
    if hasattr(args[0], "_mode"):
        return args[0]
    
    return None


def _get_source_context(frame_info: Any) -> Optional[str]:
    """Extract source code context from frame info."""
    # Handle both FrameInfo and other frame objects
    code_context = None
    if hasattr(frame_info, 'code_context'):
        code_context = frame_info.code_context
    elif hasattr(frame_info, 'frame') and hasattr(frame_info.frame, 'f_code'):
        # Try to get the source line manually
        try:
            import linecache
            filename = frame_info.filename if hasattr(frame_info, 'filename') else frame_info.frame.f_code.co_filename
            lineno = frame_info.lineno if hasattr(frame_info, 'lineno') else frame_info.frame.f_lineno
            line = linecache.getline(filename, lineno)
            if line:
                code_context = [line]
        except Exception:
            pass
    
    if not code_context:
        return None
    
    # Join the context lines
    context = "".join(code_context)
    return context.strip()


def _should_enhance_error(frame: Optional[Any]) -> bool:
    """Check if we should enhance the error based on mode."""
    if not frame:
        return False
    
    # Check frame mode
    if hasattr(frame, "_mode") and frame._mode == "debug":
        return True
    
    # Check global error mode if available
    try:
        from gaspatchio_core.errors.formatting_errors import get_error_mode
        error_mode = get_error_mode()
        return error_mode in ["enhanced", "debug"]
    except ImportError:
        return False


def capture_validation_context(func: F) -> F:
    """Decorator to capture source context for validation errors.
    
    This decorator intercepts validation errors (ValueError, TypeError, KeyError)
    and enhances them with source location information when in debug mode.
    """
    
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (ValueError, TypeError, KeyError, ValidationError) as e:
            # Check if we should enhance the error
            frame = _get_frame_from_args(args)
            if not _should_enhance_error(frame):
                raise
            
            # If it's already a ValidationError with source location, just raise it
            if isinstance(e, ValidationError) and e.source_location:
                raise
            
            try:
                # For ValidationError raised by raise_validation_error, we need to look
                # further up the stack to find the actual caller
                current_frame = inspect.currentframe()
                if not current_frame:
                    raise
                
                # Walk up the stack to find the first frame outside this module
                frame_to_use = None
                for frame_record in inspect.getouterframes(current_frame):
                    frame_obj = frame_record.frame
                    filename = frame_record.filename
                    
                    # Look for frames from the model code
                    if "model_projection.py" in filename:
                        frame_to_use = frame_record
                        break
                    
                    # Skip frames from validation.py and the decorated function
                    if (not filename.endswith("/validation.py") and 
                        not filename.endswith("/date.py") and
                        not filename.endswith("/formatting_errors.py") and
                        not filename.endswith("/runner.py") and
                        frame_obj.f_code.co_name != func.__name__ and
                        frame_obj.f_code.co_name != "wrapper"):
                        # This might be the calling code
                        if not frame_to_use:  # Keep the first non-framework frame
                            frame_to_use = frame_record
                
                if frame_to_use:
                    # Get source line using linecache
                    import linecache
                    source_line = linecache.getline(frame_to_use.filename, frame_to_use.lineno).strip()
                    
                    # Create source location from the found frame
                    source_location = SourceLocation(
                        file_path=frame_to_use.filename,
                        line_number=frame_to_use.lineno,
                        function_name=frame_to_use.function,
                        source_line=source_line if source_line else None
                    )
                    
                    # If it's already a ValidationError, just add location
                    if isinstance(e, ValidationError):
                        e.source_location = source_location
                        raise
                    
                    # Convert to ValidationError
                    enhanced = ValidationError(str(e))
                    enhanced.__cause__ = e
                    enhanced.source_location = source_location
                    
                    # Try to extract context from the original error
                    if isinstance(e, ValueError) and "Invalid" in str(e):
                        # Try to parse validation context from error message
                        msg = str(e)
                        if ":" in msg:
                            parts = msg.split(":", 1)
                            if len(parts) == 2:
                                enhanced.context.provided_value = parts[1].strip()
                    
                    raise enhanced
            except Exception:
                # If enhancement fails, just re-raise original
                raise e from None
            
            raise
    
    return wrapper  # type: ignore[return-value]


def raise_validation_error(
    message: str,
    *,
    valid_options: Optional[list[str]] = None,
    provided_value: Optional[Any] = None,
    expected_type: Optional[type] = None,
    actual_type: Optional[type] = None,
    parameter_name: Optional[str] = None,
    **additional_context: Any
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
        additional_info=additional_context if additional_context else None
    )
    
    # Try to capture source location from the caller
    try:
        location, _ = find_calling_user_code()
        if location:
            error.source_location = location
    except Exception:
        # If we can't get source location, continue without it
        pass
    
    raise error