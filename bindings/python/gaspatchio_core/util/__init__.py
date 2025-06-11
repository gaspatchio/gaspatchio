# gaspatchio_core/util/__init__.py
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

import polars as pl

from .utils import read_model_points, read_model_points_from_s3

# Global settings moved from dsl/core.py
_DEFAULT_MODE = os.environ.get("GASPATCHIO_MODE", "debug")
_DEFAULT_VERBOSE = os.environ.get("GASPATCHIO_VERBOSE", "True").lower() in (
    "true",
    "1",
    "yes",
)
_DEFAULT_THREADS = int(
    os.environ.get("GASPATCHIO_THREADS", "0"),
)  # 0 means use all available

# Error handling mode configuration
_DEFAULT_ERROR_MODE = os.environ.get(
    "AF_ERROR_MODE",
    "basic",
)  # basic, enhanced, debug, off

# Functions moved from dsl/core.py


def get_default_mode() -> str:
    """Get the default execution mode ('debug' or 'optimize')."""
    global _DEFAULT_MODE
    return _DEFAULT_MODE


def set_default_mode(mode: str) -> None:
    """Set the default execution mode ('debug' or 'optimize')."""
    global _DEFAULT_MODE
    if mode not in ("debug", "optimize"):
        raise ValueError(f"Invalid mode: {mode}. Must be 'debug' or 'optimize'")
    _DEFAULT_MODE = mode
    os.environ["GASPATCHIO_MODE"] = mode


def get_default_verbose() -> bool:
    """Get the default verbosity setting."""
    global _DEFAULT_VERBOSE
    return _DEFAULT_VERBOSE


def set_default_verbose(verbose: bool) -> None:
    """Set the default verbosity setting."""
    global _DEFAULT_VERBOSE
    _DEFAULT_VERBOSE = verbose
    # Note: Setting environment variable here might be less intuitive
    # os.environ["GASPATCHIO_VERBOSE"] = str(verbose)


def get_default_threads() -> int:
    """Get the default number of threads Polars should use (0 = auto)."""
    global _DEFAULT_THREADS
    return _DEFAULT_THREADS


def get_error_mode() -> str:
    """Get the error handling mode ('basic', 'enhanced', 'debug', or 'off')."""
    global _DEFAULT_ERROR_MODE
    # Check environment variable with case normalization
    env_mode = os.environ.get("AF_ERROR_MODE", _DEFAULT_ERROR_MODE)
    if env_mode:
        env_mode = env_mode.lower()
        # Map 'standard' to 'basic' for backward compatibility
        if env_mode == "standard":
            env_mode = "basic"
    return env_mode


def set_error_mode(mode: str) -> None:
    """Set the error handling mode ('basic', 'enhanced', 'debug', or 'off')."""
    global _DEFAULT_ERROR_MODE
    # Normalize case and handle 'standard' alias
    mode = mode.lower()
    if mode == "standard":
        mode = "basic"
    
    if mode not in ("basic", "enhanced", "debug", "off"):
        raise ValueError(
            f"Invalid error mode: {mode}. Must be 'basic', 'enhanced', 'debug', or 'off'",
        )
    _DEFAULT_ERROR_MODE = mode
    os.environ["AF_ERROR_MODE"] = mode


# Note: Setting default threads requires careful consideration due to Polars' global state


@contextmanager
def execution_mode(mode: str):
    """Context manager for temporarily changing the execution mode."""
    old_mode = get_default_mode()
    try:
        set_default_mode(mode)
        yield
    finally:
        set_default_mode(old_mode)


def _expr_to_str(value: Any) -> str:
    """Convert a Polars expression or literal to a string representation."""
    # Simplified version - original was in ActuarialFrame, might need access to frame state?
    # Let's assume it works standalone for now.
    if isinstance(value, pl.Expr):
        # Attempt to get a reasonable string representation of the expression
        # This might be complex and depends on the expression structure
        # For now, just use the default Polars string representation
        return str(value)
    if isinstance(value, str):
        # Handle string literals correctly (e.g., for column names)
        # return f'"{value}"' # Don't add extra quotes
        return str(value)
    # Handle other literals (numbers, booleans)
    return str(value)


__all__ = [
    "_expr_to_str",  # Keep internal for now?
    "execution_mode",
    "get_default_mode",
    "get_default_threads",
    "get_default_verbose",
    "get_error_mode",
    "read_model_points",
    "read_model_points_from_s3",
    "set_default_mode",
    "set_default_verbose",
    "set_error_mode",
]
