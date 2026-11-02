# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Gaspatchio Assumption API v2 - New modular assumption table system."""

# Core API
from ._analysis import DimensionInfo, TableSchema, analyze_table
from ._api import (
    Table,
    TableSupersededError,
    get_table_metadata,
    list_tables,
    list_tables_with_metadata,
)
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

__all__ = [
    "AutoDetectOverflow",
    "CategoricalDimension",
    "ComputedDimension",
    "DataDimension",
    "Dimension",
    "DimensionInfo",
    "ExtendOverflow",
    "FillConstant",
    "FillForward",
    "FillStrategy",
    "LinearInterpolate",
    "MeltDimension",
    "OverflowStrategy",
    "Table",
    "TableBuilder",
    "TableSchema",
    "TableSupersededError",
    "analyze_table",
    "get_table_metadata",
    "list_tables",
    "list_tables_with_metadata",
]
