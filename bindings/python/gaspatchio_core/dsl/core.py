from __future__ import annotations

from typing import TYPE_CHECKING

# ADDED: Import thefuzz
# Import utilities from the new location

# COMMENTED OUT: Import custom functions - will be moved later
# from gaspatchio_core.functions import fill_series as core_fill_series
# from gaspatchio_core.functions import floor as core_floor
# from gaspatchio_core.functions import round as core_round
# from gaspatchio_core.functions import round_to_int as core_round_to_int

# ADDED: Import directly from Rust bindings temporarily
# REMOVED: Moved this try/except block to functions/vector.py
# try:
#     # Assuming functions are exposed via _internal, adjust if needed
#     from gaspatchio_core._internal import (
#         fill_series as core_fill_series,
#     )
#     from gaspatchio_core._internal import (
#         floor as core_floor,
#     )
#     from gaspatchio_core._internal import (
#         round as core_round,
#     )
#     from gaspatchio_core._internal import (
#         round_to_int as core_round_to_int,
#     )
# except ImportError:
#     print(
#         "Warning: Could not import core functions from Rust bindings (during transition)."
#     )
#
#     # Define dummies or raise - depends on desired behavior if bindings are missing
#     def core_fill_series(*args, **kwargs):
#         raise NotImplementedError("Rust bindings missing")
#
#     def core_floor(*args, **kwargs):
#         raise NotImplementedError("Rust bindings missing")
#
#     def core_round(*args, **kwargs):
#         raise NotImplementedError("Rust bindings missing")
#
#     def core_round_to_int(*args, **kwargs):
#         raise NotImplementedError("Rust bindings missing")


# ADDED: Import telemetry module

# ADD TYPE_CHECKING import for DateColumnAccessor
if TYPE_CHECKING:
    # Removed: DateFrameAccessor import, as it's not used in base.py
    # Removed: FinanceFrameAccessor import
    pass

# ADDED: Import error handling functions from the new location

# REMOVED Global settings - moved to util/__init__.py
# REMOVED Utility functions - moved to util/__init__.py
# REMOVED Context Manager - moved to util/__init__.py

# REMOVED ActuarialFrame - moved to frame/base.py


# REMOVED: run_model moved to frame/execution.py
# def run_model(model_func: Callable, df: ActuarialFrame) -> ActuarialFrame:
#     """Run a model function on an ActuarialFrame"""
#     # Need to import ActuarialFrame here if it's used in type hint
#     # This might suggest moving run_model into the frame module later
#
#     # If we're in debug mode, just run the function directly
#     if df._mode == "debug":
#         result = model_func(df)
#         return df if result is None else result
#
#     # In optimize mode, use the tracer (Tracer logic is currently excluded from base ActuarialFrame)
#     # This run_model needs adjustment once tracing is extracted and reintegrated.
#     # For now, it won't properly trace.
#     # traced_func = df.trace(model_func)
#     # traced_func(df)
#     print(
#         "Warning: optimize mode in run_model is not fully functional without tracing."
#     )
#     result = model_func(df)  # Execute directly for now
#     return df if result is None else result


# Commented out for now - proxy patching belongs with proxy definition
# _autopatch(ColumnProxy)
# _autopatch(ExpressionProxy)

# Import plugins module at the end to trigger registration AFTER core classes are defined
from . import plugins  # noqa: F401 - Ensures registration happens
