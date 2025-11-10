# ruff: noqa: F401 - symbols are publicly exposed
from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING, TypeAlias

import polars as pl

# Expose the functions submodule
from . import functions as functions

# Import types for the public API - NEW v2 assumption API
from .assumptions import Table as Table
from .assumptions import TableBuilder as TableBuilder
from .assumptions import get_table_metadata as get_table_metadata
from .assumptions import list_tables as list_tables
from .assumptions import list_tables_with_metadata as list_tables_with_metadata

# Core proxy classes
from .column import ColumnProxy as ColumnProxy
from .column import ExpressionProxy as ExpressionProxy

# Frame and error classes
from .errors import PerformanceWarning as PerformanceWarning
from .frame import ActuarialFrame as ActuarialFrame
from .frame import run_model as run_model

# Functions
from .functions.conditional import when as when

# Utility functions
from .util import execution_mode as execution_mode
from .util import get_default_mode as get_default_mode
from .util import set_default_mode as set_default_mode

# Type alias for the assumption_lookup function
if TYPE_CHECKING:
    from typing import Union

    type IntoExpr = str | pl.Expr

# Define the main functions that are in __init__.py directly (legacy API)
def assumption_lookup(*keys: IntoExpr, table_name: str) -> pl.Expr: ...
def load_assumptions(
    name: str,
    source: str | pl.DataFrame,
    *,
    id: str | list[str] | None = None,
    value: str = "rate",
    value_vars: list[str] | None = None,
    overflow: str | None = "auto",
    max_overflow: int = 200,
    metadata: dict[str, any] | None = None,
    lookup_keys: list[str] | None = None,
    additional_keys: dict[str, any] | None = None,
) -> pl.DataFrame: ...
def append_assumptions(
    name: str,
    source: str | pl.DataFrame,
    *,
    additional_keys: dict[str, any],
) -> pl.DataFrame: ...

if TYPE_CHECKING:
    # Make submodules available for type checking if needed, but not strictly part of __all__
    from . import accessors as accessors
    from . import assumptions as assumptions
    from . import errors as errors
    from . import frame as frame
    from . import util as util

# Define __all__ to match __init__.py exactly
__all__: list[str] = [
    # Core classes
    "ActuarialFrame",
    "ColumnProxy",
    "ExpressionProxy",
    # Assumptions API v2
    "Table",
    "TableBuilder",
    "get_table_metadata",
    "list_tables",
    "list_tables_with_metadata",
    # Execution
    "run_model",
    # Utilities
    "execution_mode",
    "get_default_mode",
    "set_default_mode",
    # Errors
    "PerformanceWarning",
    # Functions
    "when",
    # Modules (for direct function access)
    "functions",
]
