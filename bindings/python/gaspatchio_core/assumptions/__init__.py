"""
Gaspatchio Core Assumptions API - Metadata functions only

Main assumption functions (load_assumptions, assumption_lookup) are available
at the top level only: import gaspatchio_core as gs

This module only provides metadata and introspection functions.
For loading and lookup operations, use the top-level API:
    import gaspatchio_core as gs
    gs.load_assumptions(...)
    gs.assumption_lookup(...)
"""

# Import functions from the loader module
from ._loader import get_table_metadata, list_tables_with_metadata


# Explicitly prevent import of main functions
def __getattr__(name):
    if name in ("load_assumptions", "assumption_lookup"):
        raise ImportError(
            f"'{name}' is not available from gaspatchio_core.assumptions. "
            f"Use the top-level API instead:\n"
            f"  import gaspatchio_core as gs\n"
            f"  gs.{name}(...)"
        )
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# Only export metadata functions - main functions available at top level only
__all__ = [
    "get_table_metadata",
    "list_tables_with_metadata",
]
