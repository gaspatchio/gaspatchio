"""Registry for frame and column accessors."""

from typing import Callable, Dict, Type, TypeAlias, TypeVar

T = TypeVar("T")

# Define a type alias for clarity
AccessorClass = Type
# REVERT: Use nested Dict[name, Dict[kind, class]] structure
AccessorRegistryDict: TypeAlias = Dict[str, Dict[str, AccessorClass]]

_ACCESSOR_REGISTRY: AccessorRegistryDict = {}


def register_accessor(
    name: str, *, kind: str = "column"
) -> Callable[[Type[T]], Type[T]]:
    """
    Decorator factory to register an accessor class.

    Args:
        name: The name under which the accessor should be registered (e.g., 'date').
        kind: The type of accessor, either "frame" or "column".
              Defaults to 'column'.

    Returns:
        A decorator that registers the class.

    Raises:
        ValueError: If the kind is not 'frame' or 'column'.
        ValueError: If an accessor with the same name and kind is already registered.
    """
    # Validate kind
    if kind not in ("frame", "column"):
        raise ValueError("Accessor kind must be 'frame' or 'column'")

    def decorator(cls: Type[T]) -> Type[T]:
        # REVERT: Logic for nested dict
        # Ensure the name entry exists as a dictionary
        if name not in _ACCESSOR_REGISTRY:
            _ACCESSOR_REGISTRY[name] = {}

        # Check if the specific kind is already registered for this name
        if kind in _ACCESSOR_REGISTRY[name]:
            raise ValueError(
                f"Accessor with name '{name}' and kind '{kind}' already registered."
            )

        # Register the class under the name and kind
        _ACCESSOR_REGISTRY[name][kind] = cls
        return cls

    return decorator


# Helper function to retrieve an accessor class
# REVERT: Update helper to use nested dict structure
def get_accessor(name: str, kind: str) -> AccessorClass | None:
    """Retrieve an accessor class from the registry."""
    return _ACCESSOR_REGISTRY.get(name, {}).get(kind)
