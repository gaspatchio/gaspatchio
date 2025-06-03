"""
Gaspatchio Core - Actuarial computation framework
"""

# Import key components for easier access
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

from gaspatchio_core.telemetry import (
    configure_telemetry,
)

# Import the typing helper if it exists, otherwise define locally for now
try:
    from gaspatchio_core.typing import IntoExpr
except ImportError:
    from typing import Union

    IntoExpr = Union[str, pl.Expr]

# Import submodules that need loading (e.g., for registration) or public exposure
# Important: Ensure accessor modules are imported to run registration decorators
# This needs to happen after Frame/ColumnProxy are defined if accessors depend on them.
from . import (
    accessors,  # noqa: F401 - Import for side effects (registration)
    functions,
)

# Import assumptions functionality - metadata from package, main functions directly
from .assumptions import (
    get_table_metadata,
    list_tables_with_metadata,
)
from .assumptions.api import append_assumptions, load_assumptions
from .column import ColumnProxy, ExpressionProxy
from .errors import PerformanceWarning
from .frame import ActuarialFrame, run_model
from .util import (
    execution_mode,  # Context manager
    get_default_mode,  # Getter
    set_default_mode,  # Setter
)

if TYPE_CHECKING:
    pass  # Keep this structure for potential future complex types

# Define LIB path consistently
LIB = Path(__file__).parent


def assumption_lookup(*keys: IntoExpr, table_name: str) -> pl.Expr:
    """Performs a high-performance lookup against a pre-registered assumption table.

    This function integrates with Polars expressions to retrieve values from
    assumption tables based on one or more key columns. It's designed for
    actuarial modeling, supporting both scalar and vector lookups. In a vector
    lookup, a key column can contain lists of values, and the function returns a
    corresponding list of results for each input list.

    The underlying mechanism uses efficient hash maps implemented in Rust for
    O(1) average-case lookup performance. Assumption tables must be registered
    globally using `register_table` (not detailed here but covered in other
    documentation) before they can be used with `assumption_lookup`.

    Args:
        *keys (IntoExpr): One or more key expressions to use for the lookup.
            Each key can be a column name (str) or a Polars expression (`pl.Expr`).
            The order of keys must match the order specified during table registration.
        table_name (str): The name of the assumption table (previously registered
            using `register_table`) to perform the lookup against.

    Returns:
        pl.Expr: A Polars expression representing the looked-up values.
            If a key column contains lists (vector lookup), the result will also be a
            list of corresponding values for each input list.


    """
    key_exprs = [pl.col(key) if isinstance(key, str) else key for key in keys]

    return register_plugin_function(
        plugin_path=LIB,
        function_name="lookup_by_table_and_hash",  # Must match #[polars_expr] function name
        args=key_exprs,
        kwargs={"table_name": table_name},
        is_elementwise=False,  # Vector lookup is not elementwise
    )


configure_telemetry(enable=True)


# Define the public API surface
__all__ = [
    # Core classes
    "ActuarialFrame",
    "ColumnProxy",
    "ExpressionProxy",
    # Assumptions
    "load_assumptions",
    "append_assumptions",
    "assumption_lookup",
    "get_table_metadata",
    "list_tables_with_metadata",
    # Execution
    "run_model",
    # Utilities
    "execution_mode",
    "get_default_mode",
    "set_default_mode",
    # Errors
    "PerformanceWarning",
    # Modules (for direct function access)
    "functions",
]
