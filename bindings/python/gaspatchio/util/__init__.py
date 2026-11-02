# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# gaspatchio/util/__init__.py
"""Execution settings shared across gaspatchio, and the model point readers."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import polars as pl

from .utils import read_model_points, read_model_points_from_s3

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(slots=True)
class _Defaults:
    """The process-wide defaults the getters below read and the setters write.

    One mutable object rather than four module globals, so a setter changes
    an attribute instead of rebinding a name with ``global``.
    """

    mode: str
    verbose: bool
    threads: int  # 0 means use all available
    error_mode: str  # enhanced (default), basic, debug, off


_DEFAULTS: Final = _Defaults(
    mode=os.environ.get("GASPATCHIO_MODE", "debug"),
    verbose=os.environ.get("GASPATCHIO_VERBOSE", "True").lower()
    in ("true", "1", "yes"),
    threads=int(os.environ.get("GASPATCHIO_THREADS", "0")),
    error_mode=os.environ.get("AF_ERROR_MODE", "enhanced"),
)

# The error modes, spelled once. AF_ERROR_MODE and set_error_mode() accept
# exactly these, and every reader imports them rather than writing the names
# out, so the set the setter accepts and the sets the handlers branch on
# cannot drift apart.
_ERROR_MODES: Final = frozenset({"basic", "enhanced", "debug", "off"})
# The modes under which a caught error is rewritten with the framework's full
# diagnosis -- the panels, the attribution, a validation error's location --
# on any frame. Basic does less, and only on a frame in debug mode (the
# default): a missing column becomes a plain list of the frame's columns, and
# a validator called on that frame locates its error. Off rewrites nothing.
_ENHANCING_ERROR_MODES: Final = frozenset({"enhanced", "debug"})
# The operator's kill-switch: nothing is rewritten, whatever a frame asks.
_ERROR_MODE_OFF: Final = "off"

# Functions moved from dsl/core.py


def get_default_mode() -> str:
    """Get the default execution mode ('debug' or 'optimize')."""
    return _DEFAULTS.mode


def set_default_mode(mode: str) -> None:
    """Set the default execution mode ('debug' or 'optimize').

    Raises:
        ValueError: If mode is not 'debug' or 'optimize'.

    """
    if mode not in ("debug", "optimize"):
        msg = f"Invalid mode: {mode}. Must be 'debug' or 'optimize'"
        raise ValueError(msg)
    _DEFAULTS.mode = mode
    os.environ["GASPATCHIO_MODE"] = mode


def get_default_verbose() -> bool:
    """Get the default verbosity setting."""
    return _DEFAULTS.verbose


def set_default_verbose(verbose: bool) -> None:
    """Set the default verbosity setting."""
    _DEFAULTS.verbose = verbose
    # Note: this does not write GASPATCHIO_VERBOSE back to the environment;
    # setting the environment variable here might be less intuitive.


def get_default_threads() -> int:
    """Get the default number of threads Polars should use (0 = auto)."""
    return _DEFAULTS.threads


def get_error_mode() -> str:
    """Get the error handling mode ('enhanced' (default), 'basic', 'debug', or 'off').

    The ``AF_ERROR_MODE`` environment variable wins; when it is unset, the
    programmatic default set by :func:`set_error_mode` applies -- though that
    setter writes the variable too, so a mode set programmatically is read
    back as the variable rather than as the default; a frame's own
    ``mode="debug"`` adds detail *within* an enhancing mode and never turns
    enhancement on under ``off``.
    """
    # Always check environment variable first (this allows environment to
    # override programmatic settings)
    env_mode = os.environ.get("AF_ERROR_MODE")
    if env_mode:
        env_mode = env_mode.lower()
        # Map 'standard' to 'basic' for backward compatibility
        if env_mode == "standard":
            env_mode = "basic"
        return env_mode

    # Fall back to global setting if no environment variable
    return _DEFAULTS.error_mode


def set_error_mode(mode: str) -> None:
    """Set the error handling mode ('basic', 'enhanced', 'debug', or 'off')."""
    # Normalize case and handle 'standard' alias
    mode = mode.lower()
    if mode == "standard":
        mode = "basic"

    if mode not in _ERROR_MODES:
        msg = (
            f"Invalid error mode: {mode}. "
            "Must be 'basic', 'enhanced', 'debug', or 'off'"
        )
        raise ValueError(msg)
    _DEFAULTS.error_mode = mode
    # Always update environment variable for consistency
    os.environ["AF_ERROR_MODE"] = mode


# Note: Setting default threads requires careful consideration due to Polars'
# global state


@contextmanager
def execution_mode(mode: str) -> Iterator[None]:
    """Context manager for temporarily changing the execution mode."""
    old_mode = get_default_mode()
    try:
        set_default_mode(mode)
        yield
    finally:
        set_default_mode(old_mode)


def _expr_to_str(value: object) -> str:
    """Convert a Polars expression or literal to a string representation."""
    # Simplified version - original was in ActuarialFrame, might need access to
    # frame state? Let's assume it works standalone for now.
    if isinstance(value, pl.Expr):
        # Attempt to get a reasonable string representation of the expression
        # This might be complex and depends on the expression structure
        # For now, just use the default Polars string representation
        return str(value)
    if isinstance(value, str):
        # Handle string literals correctly (e.g., for column names), returning
        # the value without extra quotes around it.
        return str(value)
    # Handle other literals (numbers, booleans)
    return str(value)


__all__ = [
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
