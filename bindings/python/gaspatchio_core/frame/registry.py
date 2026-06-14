# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Registry for frame and column accessors."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")

# Define a type alias for clarity
AccessorClass = type

# REVERT: Use nested Dict[name, Dict[kind, class]] structure
type AccessorRegistryDict = dict[str, dict[str, AccessorClass]]

_ACCESSOR_REGISTRY: AccessorRegistryDict = {}

_INVALID_KIND_MSG = "Accessor kind must be 'frame' or 'column'"


def register_accessor(
    name: str, *, kind: str = "column"
) -> Callable[[type[T]], type[T]]:
    """Return a decorator that registers the class under *name* and *kind*.

    Parameters
    ----------
    name : str
        The name under which the accessor should be registered (e.g. ``'date'``).
    kind : str, optional
        The type of accessor, either ``"frame"`` or ``"column"``.
        Defaults to ``'column'``.

    Returns
    -------
    Callable[[type[T]], type[T]]
        A decorator that registers and returns the class unchanged.

    Raises
    ------
    ValueError
        If *kind* is not ``'frame'`` or ``'column'``.
    ValueError
        If a *different* class is already registered under the same *name* and
        *kind*.  The error message names both the existing and the incoming
        class to help diagnose accidental double-imports.
    TypeError
        If the decorated class does not inherit from the expected base class
        (``BaseFrameAccessor`` for ``kind='frame'``, ``BaseColumnAccessor`` for
        ``kind='column'``).

    """
    # Validate kind up front so the error is raised before the decorator runs.
    if kind not in ("frame", "column"):
        raise ValueError(_INVALID_KIND_MSG)

    def decorator(cls: type[T]) -> type[T]:
        # --- Task 2: validate inheritance ---
        # Import inside the decorator to avoid circular imports at module load time.
        from gaspatchio_core.accessors.base import (  # noqa: PLC0415
            BaseColumnAccessor,
            BaseFrameAccessor,
        )

        if kind == "frame" and not issubclass(cls, BaseFrameAccessor):
            msg = (
                f"Cannot register '{cls.__name__}' as a frame accessor: "
                f"it must inherit from BaseFrameAccessor.  "
                f"Add 'BaseFrameAccessor' to its base classes."
            )
            raise TypeError(msg)

        if kind == "column" and not issubclass(cls, BaseColumnAccessor):
            msg = (
                f"Cannot register '{cls.__name__}' as a column accessor: "
                f"it must inherit from BaseColumnAccessor.  "
                f"Add 'BaseColumnAccessor' to its base classes."
            )
            raise TypeError(msg)

        # --- REVERT: Logic for nested dict ---
        # Ensure the name entry exists as a dictionary.
        if name not in _ACCESSOR_REGISTRY:
            _ACCESSOR_REGISTRY[name] = {}

        # --- Task 1: idempotent same-class registration ---
        if kind in _ACCESSOR_REGISTRY[name]:
            existing = _ACCESSOR_REGISTRY[name][kind]
            if existing is cls:
                # Same class re-registered — succeed silently (idempotent).
                return cls
            # Different class — raise with both names for clarity.
            msg = (
                f"Cannot register '{cls.__name__}' as accessor "
                f"name='{name}', kind='{kind}': already registered by "
                f"'{existing.__name__}'.  Use a different name or remove the "
                f"earlier registration."
            )
            raise ValueError(msg)

        # Register the class under the name and kind.
        _ACCESSOR_REGISTRY[name][kind] = cls
        return cls

    return decorator


# Helper function to retrieve an accessor class
# REVERT: Update helper to use nested dict structure
def get_accessor(name: str, kind: str) -> AccessorClass | None:
    """Retrieve an accessor class from the registry.

    Parameters
    ----------
    name : str
        The accessor name to look up.
    kind : str
        Either ``"frame"`` or ``"column"``.

    Returns
    -------
    AccessorClass | None
        The registered class, or ``None`` if not found.

    """
    return _ACCESSOR_REGISTRY.get(name, {}).get(kind)


def list_registered_accessors() -> AccessorRegistryDict:
    """Return a shallow copy of the accessor registry.

    Returns a ``dict[name, dict[kind, class]]`` snapshot of everything
    currently registered.  Mutating the returned dict does not affect the
    live registry; however, the inner dicts are *shallow* copies, so
    replacing a class value inside a returned inner dict will not propagate
    either (the inner dicts are also copied one level deep).

    Returns
    -------
    AccessorRegistryDict
        Shallow copy of the registry mapping
        ``{name: {kind: accessor_class}}``.

    Examples
    --------
    >>> list_registered_accessors()  # doctest: +SKIP
    {'date': {'frame': <class '...DateFrameAccessor'>, ...}, ...}

    """
    return {name: dict(kinds) for name, kinds in _ACCESSOR_REGISTRY.items()}
