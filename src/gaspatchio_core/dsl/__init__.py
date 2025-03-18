# DSL package

# Import from the original DSL
# Import from the debuggable DSL
from gaspatchio_core.dsl.debuggable import (
    ActuarialFrame,
    ColumnProxy,
    ExpressionProxy,
    execution_mode,
    get_default_mode,
    get_default_verbose,
    run_model,
    set_default_mode,
    set_default_verbose,
)
from gaspatchio_core.dsl.dsl import (
    ModelContext,
    PolarVar,
    col,
    p_fill_series,
    p_floor,
    p_round_down,
    run_model_function,
)

__all__ = [
    # Original DSL
    "ModelContext",
    "PolarVar",
    "col",
    "p_fill_series",
    "p_floor",
    "p_round_down",
    "run_model_function",
    # Debuggable DSL
    "ActuarialFrame",
    "ColumnProxy",
    "ExpressionProxy",
    "execution_mode",
    "get_default_mode",
    "get_default_verbose",
    "run_model",
    "set_default_mode",
    "set_default_verbose",
]
