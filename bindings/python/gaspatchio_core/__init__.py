"""
Gaspatchio Core - Actuarial computation framework
"""

# Import key components for easier access
# Explicitly import the public API components
# Explicitly import the public API components
# BREAKING CHANGE: Import directly from source modules, not the assumptions package
# Import assumption_lookup from the standalone .py file (not the package)
import importlib.util
import sys
from pathlib import Path

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

# Load assumption_lookup from the standalone assumptions.py module
_assumptions_module_path = Path(__file__).parent / "assumptions.py"
_spec = importlib.util.spec_from_file_location(
    "assumptions_module", _assumptions_module_path
)
_assumptions_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_assumptions_module)
assumption_lookup = _assumptions_module.assumption_lookup

from .assumptions._loader import (
    get_table_metadata,
    list_tables_with_metadata,
    load_assumptions,
)
from .column import ColumnProxy, ExpressionProxy
from .errors import PerformanceWarning
from .frame import ActuarialFrame, run_model
from .util import (
    execution_mode,  # Context manager
    get_default_mode,  # Getter
    set_default_mode,  # Setter
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
