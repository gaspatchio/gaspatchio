from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any, Dict, Literal, Type

if TYPE_CHECKING:
    # Import core classes only for type checking to avoid circular imports
    pass

log = logging.getLogger(__name__)

# Registry to store registered accessor classes
_ACCESSOR_REGISTRY: Dict[Literal["frame", "column"], Dict[str, Type[Any]]] = {
    "frame": {},
    "column": {},
}

# --- Entry Point Discovery ---
ENTRY_POINT_GROUP = "gaspatchio.accessors"


def discover_plugins():
    """Discover and register accessor plugins using entry points."""
    log.debug(f"Discovering plugins in entry point group '{ENTRY_POINT_GROUP}'")
    try:
        entry_points = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception as e:
        log.error(f"Error retrieving entry points for group '{ENTRY_POINT_GROUP}': {e}")
        return

    for entry_point in entry_points:
        log.debug(f"Processing entry point: {entry_point.name}")
        try:
            # Convention: entry point name is "{kind}.{accessor_name}"
            kind_str, accessor_name = entry_point.name.split(".", 1)

            if kind_str not in ("frame", "column"):
                log.warning(
                    f"Skipping entry point '{entry_point.name}': "
                    f"Invalid kind '{kind_str}' in name. Must start with 'frame.' or 'column.'"
                )
                continue

            kind: Literal["frame", "column"] = kind_str  # Type cast after validation

            loaded_cls = entry_point.load()
            log.debug(
                f"Loaded class {loaded_cls.__name__} from entry point '{entry_point.name}'"
            )

            # Use the existing registration logic (handles warnings, dynamic property setting)
            register_accessor(name=accessor_name, kind=kind)(loaded_cls)

        except ValueError as e:
            log.warning(
                f"Skipping entry point '{entry_point.name}': Invalid name format or kind. {e}"
            )
        except ImportError as e:
            log.warning(f"Could not load entry point '{entry_point.name}': {e}")
        except AttributeError as e:
            log.warning(
                f"Error processing entry point '{entry_point.name}' (likely loading issue): {e}"
            )
        except Exception as e:
            log.error(
                f"Unexpected error processing entry point '{entry_point.name}': {e}",
                exc_info=True,
            )


# --- END Entry Point Discovery ---


def register_accessor(name: str, *, kind: Literal["frame", "column"]):
    """
    Decorator to register a custom accessor class for ActuarialFrame or its proxies.

    Args:
        name: The name under which the accessor will be available (e.g., 'risk' for `.risk`).
        kind: 'frame' to register on ActuarialFrame, 'column' to register on
              ColumnProxy and ExpressionProxy.

    Raises:
        ValueError: If the kind is invalid or the name is already registered for the kind.
        TypeError: If the decorated object is not a class.
    """
    if kind not in ("frame", "column"):
        raise ValueError(
            f"Invalid accessor kind: '{kind}'. Must be 'frame' or 'column'."
        )

    def decorator(accessor_cls: Type[Any]):
        if not isinstance(accessor_cls, type):
            raise TypeError("Accessor must be a class.")

        if name in _ACCESSOR_REGISTRY[kind]:
            log.warning(
                f"Accessor '{name}' of kind '{kind}' is already registered. Overwriting."
            )
            # Or raise ValueError(f"Accessor '{name}' already registered for kind '{kind}'.")

        _ACCESSOR_REGISTRY[kind][name] = accessor_cls

        # Dynamically add the property to the target class(es)
        # We need to import the core classes *here* after they are defined
        # to avoid circular dependencies at the module level.
        from .core import ActuarialFrame, ColumnProxy, ExpressionProxy

        if kind == "frame":
            target_classes = [ActuarialFrame]
        else:  # kind == "column"
            target_classes = [ColumnProxy, ExpressionProxy]

        for target_cls in target_classes:
            if hasattr(target_cls, name):
                log.warning(
                    f"Attribute '{name}' already exists on class '{target_cls.__name__}'. "
                    f"Accessor registration might shadow it."
                )

            # Use a factory function within the lambda to capture the correct accessor_cls
            def _create_accessor(instance, cls_to_instantiate=accessor_cls):
                return cls_to_instantiate(instance)

            setattr(target_cls, name, property(_create_accessor))

        log.debug(
            f"Registered {kind} accessor '{name}' with class {accessor_cls.__name__}"
        )
        return accessor_cls

    return decorator


def get_registered_accessors(kind: Literal["frame", "column"]) -> Dict[str, Type[Any]]:
    """Get the registry for a specific kind of accessor."""
    return _ACCESSOR_REGISTRY.get(kind, {})


# --- Discover plugins on module import ---
discover_plugins()
