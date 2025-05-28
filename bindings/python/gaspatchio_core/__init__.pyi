# ruff: noqa: F401 - symbols are publicly exposed
from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING, TypeAlias

import polars as pl

# Expose the functions submodule
from . import functions as functions

# Import types for the public API - metadata functions from assumptions
from .assumptions import get_table_metadata as get_table_metadata
from .assumptions import list_tables_with_metadata as list_tables_with_metadata
from .column import ColumnProxy as ColumnProxy
from .column import ExpressionProxy as ExpressionProxy
from .errors import PerformanceWarning as PerformanceWarning
from .frame import ActuarialFrame as ActuarialFrame
from .frame import run_model as run_model
from .util import execution_mode as execution_mode
from .util import get_default_mode as get_default_mode
from .util import set_default_mode as set_default_mode

# Type alias for the assumption_lookup function
if TYPE_CHECKING:
    from typing import Union

    IntoExpr = Union[str, pl.Expr]

# Define the main functions that are in __init__.py directly
def assumption_lookup(*keys: IntoExpr, table_name: str) -> pl.Expr:
    """Performs a high-performance lookup against a pre-registered assumption table.

    This function integrates with Polars expressions to retrieve values from
    assumption tables based on one or more key columns. It's designed for
    actuarial modeling, supporting both scalar and vector lookups. In a vector
    lookup, a key column can contain lists of values, and the function returns a
    corresponding list of results for each input list.

    The underlying mechanism uses efficient hash maps implemented in Rust for
    O(1) average-case lookup performance. Assumption tables must be registered
    globally using `load_assumptions` before they can be used with `assumption_lookup`.

    Args:
        *keys (IntoExpr): One or more key expressions to use for the lookup.
            Each key can be a column name (str) or a Polars expression (`pl.Expr`).
            The order of keys must match the order specified during table registration.
        table_name (str): The name of the assumption table (previously registered
            using `load_assumptions`) to perform the lookup against.

    Returns:
        pl.Expr: A Polars expression representing the looked-up values.
            If a key column contains lists (vector lookup), the result will also be a
            list of corresponding values for each input list.
    """
    ...

def load_assumptions(
    name: str,
    source: Union[str, pl.DataFrame],
    *,
    id: Union[str, list[str], None] = None,
    value: str = "rate",
    value_vars: Union[list[str], None] = None,
    overflow: Union[str, None] = "auto",
    max_overflow: int = 200,
    metadata: dict[str, any] | None = None,
) -> pl.DataFrame:
    """Load and register assumption tables from various sources.

    This function provides a unified interface for loading actuarial assumption
    tables from CSV files, Parquet files, or Polars DataFrames. It automatically
    detects the table format (curve vs wide table) and handles data transformation,
    overflow expansion, and registration for high-performance lookups.

    Args:
        name: Unique name for the assumption table. Used for lookups via
            assumption_lookup(). Must not conflict with existing table names.
        source: Data source - file path (str) or Polars DataFrame.
        id: Column name(s) to use as lookup keys. If None, auto-detects the
            first non-numeric column(s). Can be a single column name or list
            of column names for composite keys.
        value: Name for the value column in the output table. Defaults to "rate".
            For wide tables, this becomes the column name after melting.
        value_vars: For wide tables, specific columns to melt. If None, melts all
            numeric columns (excluding id columns). Useful for selective melting
            like ["MNS", "FNS", "MS", "FS"] from gender/smoking combinations.
        overflow: Overflow handling for wide tables. Options:
            - "auto": Auto-detect overflow columns (e.g., "Ult.", "Ultimate")
            - str: Explicit overflow column name
            - None: No overflow handling
        max_overflow: Maximum duration to expand overflow values to.
            Only used when overflow handling is enabled. Defaults to 200.
        metadata: Optional metadata dictionary to store with the table.
            Can be retrieved later for documentation purposes.

    Returns:
        pl.DataFrame: The processed and registered assumption table.
            For curves: [id_cols..., value_col]
            For wide tables: [id_cols..., "variable", value_col]

    Raises:
        ValueError: For invalid parameters or malformed data.
        FileNotFoundError: If source file doesn't exist.
    """
    ...

if TYPE_CHECKING:
    # Make submodules available for type checking if needed, but not strictly part of __all__
    from . import accessors as accessors
    from . import errors as errors
    from . import frame as frame
    from . import util as util

# Define __all__ to match __init__.py
__all__: list[str] = [
    # Core classes
    "ActuarialFrame",
    "ColumnProxy",
    "ExpressionProxy",
    # Assumptions
    "load_assumptions",
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
