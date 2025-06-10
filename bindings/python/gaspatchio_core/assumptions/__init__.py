"""Gaspatchio Assumption API v2 - New modular assumption table system."""

# Core API
from ._analysis import DimensionInfo, TableSchema, analyze_table
from ._api import Table, get_table_metadata, list_tables, list_tables_with_metadata
from ._builder import TableBuilder

# Dimension types
from ._dimensions import (
    CategoricalDimension,
    ComputedDimension,
    DataDimension,
    Dimension,
    MeltDimension,
)

# Strategy types
from ._strategies import (
    AutoDetectOverflow,
    ExtendOverflow,
    FillConstant,
    FillForward,
    FillStrategy,
    LinearInterpolate,
    OverflowStrategy,
)

# Legacy metadata functions (kept for backward compatibility)
# from .api import get_table_metadata, list_tables_with_metadata  # Now using new API versions

__all__ = [
    # Core API
    "Table",
    "analyze_table",
    "TableBuilder",
    # Metadata functions
    "get_table_metadata",
    "list_tables",
    "list_tables_with_metadata",
    # Schema types
    "TableSchema",
    "DimensionInfo",
    # Dimensions
    "Dimension",
    "DataDimension",
    "MeltDimension",
    "CategoricalDimension",
    "ComputedDimension",
    # Strategies
    "OverflowStrategy",
    "ExtendOverflow",
    "AutoDetectOverflow",
    "FillStrategy",
    "LinearInterpolate",
    "FillConstant",
    "FillForward",
]
