"""
Gaspatchio Core - Actuarial computation framework
"""

# Import key components for easier access
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from gaspatchio_core.telemetry import (
    configure_telemetry,
)

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
from .assumptions.api import append_assumptions, assumption_lookup, load_assumptions
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
