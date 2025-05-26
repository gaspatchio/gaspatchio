"""
Gaspatchio Core Assumptions API - Metadata functions only

Main assumption functions (load_assumptions, assumption_lookup) are available
at the top level only: import gaspatchio_core as gs
"""

# Import functions from the loader module
from ._loader import get_table_metadata, list_tables_with_metadata, load_assumptions

# Only export metadata functions - main functions available at top level only
__all__ = [
    "get_table_metadata",
    "load_assumptions",
    "list_tables_with_metadata",
]
