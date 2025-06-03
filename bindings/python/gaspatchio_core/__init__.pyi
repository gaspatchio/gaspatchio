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
def assumption_lookup(*keys: IntoExpr, table_name: str) -> pl.Expr: ...
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
    lookup_keys: Union[list[str], None] = None,
    additional_keys: dict[str, any] | None = None,
) -> pl.DataFrame: ...
def append_assumptions(
    name: str,
    source: Union[str, pl.DataFrame],
    *,
    additional_keys: dict[str, any],
) -> pl.DataFrame: ...

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
