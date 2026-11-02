# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Registry for frame and column accessors."""

from __future__ import annotations

import keyword
from dataclasses import dataclass
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

# The frame accessors ``ActuarialFrame`` declares as properties of its own.
# They are the framework's five, and they resolve from the class whatever
# this registry holds: emptying an entry here does not stop ``af.date``
# returning ``DateFrameAccessor``, because the declared property answers
# first and falls back to importing the built-in class. So they are
# declared OUTSIDE the registry, and two seams read this set to stay true
# of that.  ``_accessor_read_destination`` says ``af.<name>`` goes on
# reaching the frame accessor for these names whatever the registry holds,
# which is what a reader actually meets; and the shadow refusal below
# exempts them, because a name whose class attribute IS the accessor
# shadows nothing.  Anything else the class carries -- ``collect``,
# ``filter``, ``columns``, ``schema``, ``max`` -- wins attribute access
# over a frame accessor added under the same name, which is what that
# refusal is for.
_FRAME_DECLARED_ACCESSORS = frozenset(
    {"date", "excel", "finance", "graph", "projection"}
)


@dataclass(frozen=True, slots=True)
class _AccessorBindings:
    """Classes supplied by package composition, never imported by the registry."""

    frame: type
    frame_accessor: type
    column_accessor: type


_bindings: _AccessorBindings | None = None


def _configure_accessors(bindings: _AccessorBindings) -> None:
    """Bind class checks once the package has constructed its public classes."""
    global _bindings  # noqa: PLW0603 -- explicit package composition
    _bindings = bindings


def _accessor_bindings() -> _AccessorBindings:
    """Return the composed classes, refusing plainly before composition.

    Every path through ``import gaspatchio`` composes them before any user
    code runs, so this refusal is for a registration made from inside the
    package's own import -- a new module that registers an accessor at import
    time and is imported before ``gaspatchio/__init__.py`` has finished. A bare
    ``NameError`` on a module global would name neither cause nor fix.
    """
    if _bindings is None:
        msg = (
            "Accessor registration ran before gaspatchio finished importing: "
            "the ActuarialFrame and accessor base classes are not bound yet. "
            "Register accessors after 'import gaspatchio' completes, not from a "
            "module the package imports while it is still initialising."
        )
        raise RuntimeError(msg)
    return _bindings


def _frame_attribute_kind(name: str, attribute: object) -> str:
    """Say what ``af.<name>`` already is, for a name the class declares.

    ``ActuarialFrame`` carries these names as methods -- ``sum``, ``filter``,
    ``collect`` -- and as read-only properties -- ``columns``, ``dtypes``,
    ``schema``. The refusal in ``__setattr__`` tells an actuary what stopped
    them, so it has to be right about which of the two it was: ``af.sum``
    hands back a bound method, ``af.columns`` hands back the column names,
    and neither is the column the assignment meant to write. Anything else
    the class may come to carry under a public name is told the one thing
    still true of it.
    """
    if isinstance(attribute, property):
        return f"af.{name} is the frame's own {name} property."
    # Held in a variable, not tested inside the `if`: mypy narrows an `object`
    # tested with callable() to a class it invents in this module, and stubtest
    # reads that class as one of the names the module exports.
    is_method = callable(attribute)
    if is_method:
        return f"af.{name} is the frame's own {name}() method."
    return f"af.{name} is an attribute the frame already carries."


def _refuse_a_name_with_no_attribute_spelling(name: str) -> None:
    """Refuse a name that cannot be written after a dot.

    An accessor is reached by writing its name after a dot -- ``af.<name>``
    for a frame accessor, ``af.<column>.<name>`` for a column one. A name
    that is not a Python identifier, or that is a keyword, has no such
    door, and the name still reached ``_ACCESSOR_REGISTRY``, where
    ``ActuarialFrame``'s assignment refusal read it and printed
    ``af.<name> = ...`` back as a spelling to avoid -- ``af.not an
    identifier = ...``, ``af.class = ...``. Refuse the name here, where the
    mistake is, rather than quoting it later in a sentence nobody can act
    on. ``af["..."]`` remains the door for a COLUMN of any name, and is
    unaffected by this.

    Raises
    ------
    ValueError
        If *name* is not a Python identifier, or is a Python keyword.

    """
    if not isinstance(name, str) or not name.isidentifier():
        msg = (
            f"Cannot add an accessor under the name {name!r}: an accessor is "
            f"reached as af.<name>, and {name!r} is not a Python identifier, "
            f"so it has no attribute spelling. Use a name "
            f"str.isidentifier() accepts."
        )
        raise ValueError(msg)
    if keyword.iskeyword(name):
        msg = (
            f"Cannot add an accessor under the name '{name}': '{name}' is a "
            f"Python keyword, so it cannot be written after a dot. Use a "
            f"name that is not a Python keyword."
        )
        raise ValueError(msg)


def _refuse_a_frame_name_the_class_already_carries(name: str, cls: type) -> None:
    """Refuse a frame accessor the class attribute of that name would hide.

    A frame accessor is reached only as ``af.<name>``, and a name
    ``ActuarialFrame`` already carries as a method or property wins that
    lookup: the class attribute is found before ``__getattr__`` runs, so
    the accessor is unreachable by any spelling. The entry still landed in
    the registry, and ``ActuarialFrame``'s assignment refusal then read it
    and said ``af.<name> goes on reaching the frame accessor``, which is
    false -- it goes on reaching the method. Refuse the name here, where
    the mistake is, and say which class attribute it would have been
    hidden by.

    The five in ``_FRAME_DECLARED_ACCESSORS`` are exempt because their
    class attribute IS the accessor: ``ActuarialFrame.date`` is a property
    that hands back the frame accessor, so there is no shadow, and this is
    how the framework's own five arrive here.

    Raises
    ------
    ValueError
        If ``ActuarialFrame`` carries *name* and *name* is not one of the
        five it declares as accessor properties.

    """
    if name in _FRAME_DECLARED_ACCESSORS:
        return
    declared = getattr(_accessor_bindings().frame, name, None)
    if declared is None:
        return
    msg = (
        f"Cannot add '{cls.__name__}' as a frame accessor named "
        f"'{name}': ActuarialFrame already carries that name, and "
        f"a name the class carries wins attribute access, so "
        f"af.{name} would never reach the accessor. "
        f"{_frame_attribute_kind(name, declared)} Use a name the "
        f"frame does not already use."
    )
    raise ValueError(msg)


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
        If *name* is not a Python identifier, or is a Python keyword.  An
        accessor is reached as ``af.<name>`` or ``af.<column>.<name>``, so a
        name with no attribute spelling names a door nobody can walk
        through.
    ValueError
        If *kind* is ``'frame'`` and ``ActuarialFrame`` already carries
        *name* as a method or property of its own.  The class attribute wins
        attribute access, so the accessor would be unreachable by any
        spelling.  The five the frame declares as accessor properties --
        ``date``, ``excel``, ``finance``, ``graph``, ``projection`` -- are
        exempt: their class attribute IS the accessor.
    ValueError
        If a *different* class is already registered under the same *name* and
        *kind*.  The error message names both the existing and the incoming
        class to help diagnose accidental double-imports.  The same class
        statement run again -- one module and one qualified name, as when a
        helper is imported afresh with the model that loads it -- is not a
        different class: it takes the earlier definition's place.
    TypeError
        If the decorated class does not inherit from the expected base class
        (``BaseFrameAccessor`` for ``kind='frame'``, ``BaseColumnAccessor`` for
        ``kind='column'``).

    """
    # Validate kind up front so the error is raised before the decorator runs.
    if kind not in ("frame", "column"):
        raise ValueError(_INVALID_KIND_MSG)

    # Judge the name up front too, for the same reason: the refusal lands
    # at the decoration site rather than inside the decorator.
    _refuse_a_name_with_no_attribute_spelling(name)

    def decorator(cls: type[T]) -> type[T]:
        # The base-class check runs before any entry is made, so a class that
        # could never be an accessor of this kind is refused rather than left
        # half-recorded under its name.
        if kind == "frame" and not issubclass(cls, _accessor_bindings().frame_accessor):
            msg = (
                f"Cannot declare '{cls.__name__}' as a frame accessor: "
                f"it must inherit from BaseFrameAccessor.  "
                f"Add 'BaseFrameAccessor' to its base classes."
            )
            raise TypeError(msg)

        if kind == "column" and not issubclass(
            cls, _accessor_bindings().column_accessor
        ):
            msg = (
                f"Cannot declare '{cls.__name__}' as a column accessor: "
                f"it must inherit from BaseColumnAccessor.  "
                f"Add 'BaseColumnAccessor' to its base classes."
            )
            raise TypeError(msg)

        # The name must also be one a frame accessor can actually be
        # reached under; a class attribute of that name would hide it.
        if kind == "frame":
            _refuse_a_frame_name_the_class_already_carries(name, cls)

        # --- REVERT: Logic for nested dict ---
        # Ensure the name entry exists as a dictionary.
        if name not in _ACCESSOR_REGISTRY:
            _ACCESSOR_REGISTRY[name] = {}

        # Decorating the same class again under the same name and kind is a
        # no-op, so a module reached twice through two import paths does not
        # raise; only a *different* class under a name already taken does.
        if kind in _ACCESSOR_REGISTRY[name]:
            existing = _ACCESSOR_REGISTRY[name][kind]
            if existing is cls:
                # Same class re-registered — succeed silently (idempotent).
                return cls
            if _one_declaration(existing, cls):
                # The same class statement run again -- a helper module
                # imported afresh because the model loading it was -- is the
                # declaration as its file now reads, and takes its place.
                _ACCESSOR_REGISTRY[name][kind] = cls
                return cls
            # Different class — raise with both names for clarity.
            msg = (
                f"Cannot declare '{cls.__name__}' as the accessor "
                f"name='{name}', kind='{kind}': that name is already taken by "
                f"'{existing.__name__}'.  Use a different name, or remove the "
                f"earlier declaration."
            )
            raise ValueError(msg)

        # Register the class under the name and kind.
        _ACCESSOR_REGISTRY[name][kind] = cls
        return cls

    return decorator


def _one_declaration(existing: type, cls: type) -> bool:
    """Return whether two classes are one class statement, run twice.

    The same module and the same qualified name: a module executed again
    makes a new class object from the same statement, and that is the
    declaration edited or not, never a second one competing for the name.
    """
    return (
        existing.__module__ == cls.__module__
        and existing.__qualname__ == cls.__qualname__
    )


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


# The decorator a custom accessor registers with, as the extending skill
# documents it.
__all__ = ["register_accessor"]
