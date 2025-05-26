"""
Provides the Python interface for the table registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

# Import the internal Rust module. The exact name depends on your maturin setup.
# It's often `_internal` or `package_name._internal`.
# Assuming it's gaspatchio_core._internal for now.
try:
    from gaspatchio_core import _internal
except ImportError as e:
    raise ImportError(
        "Could not import the internal Rust module. "
        "Make sure the project is built correctly. "
        f"Original error: {e}"
    ) from e

if TYPE_CHECKING:
    import polars as pl

# --- Transformation Spec Helper --- (Could be moved to a separate types module)


# Define a simple structure for the transform spec dictionary for type hinting
# This could eventually be a Pydantic model if more complex validation is needed.
class WideToLongTransformSpec(Dict[str, Any]):
    transform_type: str = "WideToLong"
    id_vars: List[str]
    value_vars: List[str]
    var_name: str
    value_name: str


# --- Table Registry Class ---


class TableRegistry:
    """Provides methods to register and manage assumption tables.

    This class acts as a Python wrapper around the underlying Rust registry.
    """

    def __init__(self):
        """Initializes the registry wrapper."""
        # Create an instance of the Rust PyTableRegistry
        self._registry = _internal.PyTableRegistry()

    def register_table(
        self,
        name: str,
        df: pl.DataFrame,
        keys: List[str],
        value_column: str,
        transform_spec: Optional[WideToLongTransformSpec] = None,
    ) -> None:
        """Registers a table (DataFrame) with the global registry.

        Args:
            name: The unique name for this table in the registry.
            df: The DataFrame containing the assumption data.
            keys: List of column names to use as lookup keys *after* transformation.
            value_column: The name of the column containing the values *after* transformation.
            transform_spec: Optional dictionary specifying how to transform the input `df`
                before creating the lookup index. Required keys depend on `transform_type`.
                For `WideToLong`: `transform_type`, `id_vars`, `value_vars`, `var_name`, `value_name`.

        Raises:
            ValueError: If registration fails in the underlying Rust implementation
                (e.g., duplicate name, invalid keys/columns, transformation error).
        """
        try:
            # Call the Rust method via the internal instance
            self._registry.register_table(
                name,
                df,  # PyO3 handles the conversion from Polars DF
                keys,
                value_column,
                transform_spec,  # Pass the dictionary directly
            )
        except Exception as e:
            # Convert potential PyO3 errors (like PyValueError from Rust) to Python ValueError
            # Or handle specific Rust errors if needed
            raise ValueError(f"Failed to register table '{name}': {e}") from e


class AssumptionTableRegistry:
    """Provides methods to register and manage assumption tables.

    This class acts as a Python wrapper around the underlying Rust registry.
    """

    def __init__(self):
        """Initializes the registry wrapper."""
        # Create an instance of the Rust PyTableRegistry
        self._registry = _internal.PyAssumptionTableRegistry()

    def register_table(
        self,
        name: str,
        df: pl.DataFrame,
        keys: List[str],
        value_column: str,
    ) -> None:
        """Registers a table (DataFrame) with the global registry.

        Args:
            name: The unique name for this table in the registry.
            df: The DataFrame containing the assumption data.
            keys: List of column names to use as lookup keys *after* transformation.
            value_column: The name of the column containing the values *after* transformation.
            transform_spec: Optional dictionary specifying how to transform the input `df`
                before creating the lookup index. Required keys depend on `transform_type`.
                For `WideToLong`: `transform_type`, `id_vars`, `value_vars`, `var_name`, `value_name`.

        Raises:
            ValueError: If registration fails in the underlying Rust implementation
                (e.g., duplicate name, invalid keys/columns, transformation error).
        """
        try:
            # Call the Rust method via the internal instance
            self._registry.register_table(
                name,
                df,  # PyO3 handles the conversion from Polars DF
                keys,
                value_column,
            )
        except Exception as e:
            # Convert potential PyO3 errors (like PyValueError from Rust) to Python ValueError
            # Or handle specific Rust errors if needed
            raise ValueError(f"Failed to register table '{name}': {e}") from e
