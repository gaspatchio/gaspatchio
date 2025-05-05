# gaspatchio_core/util/__init__.pyi
from contextlib import _GeneratorContextManager
from typing import Any

# Declare the functions moved from dsl/core.py

def get_default_mode() -> str:
    """Get the default execution mode ('debug' or 'optimize')."""
    ...

def set_default_mode(mode: str) -> None:
    """Set the default execution mode ('debug' or 'optimize').

    Raises:
        ValueError: If mode is not 'debug' or 'optimize'.
    """
    ...

def get_default_verbose() -> bool:
    """Get the default verbosity setting."""
    ...

def set_default_verbose(verbose: bool) -> None:
    """Set the default verbosity setting."""
    ...

def get_default_threads() -> int:
    """Get the default number of threads Polars should use (0 = auto)."""
    ...

def execution_mode(mode: str) -> _GeneratorContextManager[None]:
    """Context manager for temporarily changing the execution mode."""
    ...

def _expr_to_str(value: Any) -> str:
    """Convert a Polars expression or literal to a string representation.

    Note: This is intended for internal use.
    """
    ...
