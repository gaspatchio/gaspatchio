"""Stub file for the accessor registry."""

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_ACCESSOR_REGISTRY: dict[str, dict[str, type]]
"""Global registry mapping accessor name to ``{kind: accessor_class}``."""  # noqa: D400

def register_accessor(name: str, *, kind: str = ...) -> Callable[[type[T]], type[T]]:
    """
    Decorator factory to register an accessor class.

    Args:
        name: The name under which the accessor should be registered (e.g., 'date').
        kind: The type of object the accessor applies to, either 'frame' or 'column'.
              Defaults to 'column'.

    Returns:
        A decorator that registers and returns the class unchanged.

    Raises:
        ValueError: If the kind is not 'frame' or 'column'.
        ValueError: If a different class is already registered under the same name and kind.
        TypeError: If the decorated class does not inherit from the expected base class.
    """
    ...

def get_accessor(name: str, kind: str) -> type | None:
    """
    Retrieve an accessor class from the registry.

    Args:
        name: The accessor name to look up.
        kind: Either 'frame' or 'column'.

    Returns:
        The registered class, or None if not found.
    """
    ...

def list_registered_accessors() -> dict[str, dict[str, type]]:
    """
    Return a shallow copy of the accessor registry.

    Returns a ``dict[name, dict[kind, class]]`` snapshot of everything
    currently registered.  Mutating the returned dict does not affect the
    live registry.

    Returns:
        Shallow copy of the registry mapping ``{name: {kind: accessor_class}}``.
    """
    ...
