# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Calculation graph functionality for ActuarialFrame operations.

This package provides tools for building, analyzing, and exporting
directed acyclic graphs (DAGs) from traced actuarial calculations.
"""

from .calc_graph import GraphExporter
from .expr_analyzer import analyze_expression_tree, extract_dependencies
from .graph_builder import CalculationGraph
from .graph_models import (
    DataSource,
    GraphEdge,
    GraphExportConfig,
    GraphNode,
    NodeData,
    NodeType,
)

__all__ = [
    # Main exports
    "GraphExporter",
    # Expression analysis
    "analyze_expression_tree",
    "extract_dependencies",
    # Graph components
    "CalculationGraph",
    "GraphNode",
    "GraphEdge",
    "NodeData",
    "NodeType",
    "DataSource",
    "GraphExportConfig",
]