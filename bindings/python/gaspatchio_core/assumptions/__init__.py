"""
Gaspatchio Core Assumptions API
"""

# Import functions from the loader module
# BREAKING CHANGE: Remove direct exports to force users to use top-level imports only
from ._loader import get_table_metadata, list_tables_with_metadata

# Re-export only metadata functions - load_assumptions and assumption_lookup
# are now only available at the top level (gaspatchio_core.load_assumptions)
__all__ = [
    "get_table_metadata",
    "list_tables_with_metadata",
]
