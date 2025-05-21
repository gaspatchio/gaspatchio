"""
Gaspatchio Core - Actuarial computation framework
"""

# Import key components for easier access
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

# Explicitly import the public API components
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
