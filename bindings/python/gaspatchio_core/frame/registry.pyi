"""Stub file for the accessor registry."""

from typing import Callable, Dict, Tuple, Type, TypeVar

T = TypeVar("T")

_ACCESSOR_REGISTRY: Dict[str, Tuple[Type, str]]
"""Global registry mapping accessor name to (accessor_class, kind)."""  # noqa: D400

def register_accessor(name: str, *, kind: str = ...) -> Callable[[Type[T]], Type[T]]:
    """
    Decorator factory to register an accessor class.

    Args:
        name: The name under which the accessor should be registered (e.g., 'date').
        kind: The type of object the accessor applies to, either 'frame' or 'column'.
              Defaults to 'column'.

    Returns:
        A decorator that registers the class.

    Raises:
        ValueError: If the kind is not 'frame' or 'column'.
        ValueError: If an accessor with the same name is already registered.
    """
    ...
