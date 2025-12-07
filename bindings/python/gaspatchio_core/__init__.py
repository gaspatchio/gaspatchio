"""Gaspatchio Core - Actuarial computation framework."""

# Import key components for easier access
from __future__ import annotations

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

# Import assumptions functionality - new API
from .assumptions import (
    Table,
    TableBuilder,
    get_table_metadata,
    list_tables,
    list_tables_with_metadata,
)
from .column import ColumnProxy, ExpressionProxy
from .errors import PerformanceWarning
from .frame import ActuarialFrame, run_model
from .functions.conditional import when
from .scenarios import (
    batch_scenarios,
    describe_scenarios,
    sensitivity_analysis,
    with_scenarios,
)
from .util import (
    execution_mode,  # Context manager
    get_default_mode,  # Getter
    set_default_mode,  # Setter
)

configure_telemetry(enable=True)


# Define the public API surface
__all__ = [
    "ActuarialFrame",
    "ColumnProxy",
    "ExpressionProxy",
    "PerformanceWarning",
    "Table",
    "TableBuilder",
    "batch_scenarios",
    "describe_scenarios",
    "execution_mode",
    "functions",
    "get_default_mode",
    "get_table_metadata",
    "list_tables",
    "list_tables_with_metadata",
    "run_model",
    "sensitivity_analysis",
    "set_default_mode",
    "when",
    "with_scenarios",
]
