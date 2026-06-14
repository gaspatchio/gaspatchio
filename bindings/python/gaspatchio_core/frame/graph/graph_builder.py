# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Calculation graph builder with improved structure.

This module provides a cleaner implementation of the CalculationGraph class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

from .graph_models import DataSource, GraphEdge, GraphNode, NodeData, NodeType
from .graph_utils import clean_expression_string, simplify_dtype

if TYPE_CHECKING:
    from ...errors.metadata import TracedOperation


class CalculationGraph:
    """
    Builds and exports a calculation graph from traced operations.
    
    The graph represents the flow of calculations in an actuarial model,
    with nodes representing columns (input or computed) and edges representing
    dependencies between them.
    """
    
    def __init__(self):
        """Initialize an empty calculation graph."""
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self.input_columns: set[str] = set()
        self._node_order: list[str] = []  # Track order of node creation
    
    def add_input_column(
        self, 
        column_name: str, 
        dtype: pl.DataType | None = None, 
        source: DataSource = DataSource.MODEL_POINTS
    ) -> None:
        """
        Add an input column node to the graph.
        
        Args:
            column_name: Name of the input column
            dtype: Polars data type of the column
            source: Source of the data
        """
        if column_name in self.nodes:
            return
        
        node = self._create_input_node(column_name, dtype, source)
        self.nodes[column_name] = node
        self.input_columns.add(column_name)
        self._node_order.append(column_name)
        
        logger.trace(f"Added input node: {column_name} ({node.data.dtype})")
    
    def add_computed_operation(self, operation: TracedOperation) -> None:
        """
        Add a computed node and its edges to the graph.
        
        Args:
            operation: A TracedOperation object containing the operation details
        """
        from ...errors.metadata import TracedOperation
        
        if not isinstance(operation, TracedOperation):
            logger.warning(f"Skipping non-TracedOperation: {type(operation)}")
            return
        
        # Get dependencies
        dependencies = self._get_dependencies(operation)
        
        # Create the computed node
        node = self._create_computed_node(operation, dependencies)
        self.nodes[operation.alias] = node
        self._node_order.append(operation.alias)
        
        # Create edges
        self._create_edges(operation.alias, dependencies)
        
        logger.trace(f"Added computed node: {operation.alias} with {len(dependencies)} dependencies")
    
    def _create_input_node(
        self, 
        column_name: str, 
        dtype: pl.DataType | None, 
        source: DataSource
    ) -> GraphNode:
        """Create an input node."""
        dtype_str = simplify_dtype(str(dtype)) if dtype else "unknown"
        
        return GraphNode(
            id=column_name,
            type=NodeType.INPUT,
            label=column_name,
            data=NodeData(
                dtype=dtype_str,
                source=source,
                dependencies=[]
            )
        )
    
    def _create_computed_node(
        self, 
        operation: TracedOperation, 
        dependencies: list[str]
    ) -> GraphNode:
        """Create a computed node from an operation."""
        expr_str = clean_expression_string(str(operation.expression))
        source_location = f"{operation.metadata.display_filename}:{operation.metadata.line_number}"
        dtype_str = simplify_dtype(str(operation.expected_dtype)) if operation.expected_dtype else "unknown"
        
        return GraphNode(
            id=operation.alias,
            type=NodeType.COMPUTED,
            label=f"{operation.alias} = {expr_str}",
            data=NodeData(
                formula=expr_str,
                dependencies=dependencies,
                source_location=source_location,
                dtype=dtype_str
            )
        )
    
    def _get_dependencies(self, operation: TracedOperation) -> list[str]:
        """Extract dependencies from an operation."""
        if hasattr(operation, "dependencies") and operation.dependencies is not None:
            return operation.dependencies
        
        from .expr_analyzer import extract_dependencies
        return extract_dependencies(operation.expression)
    
    def _create_edges(self, target: str, dependencies: list[str]) -> None:
        """Create edges from dependencies to target node."""
        for dep in dependencies:
            # If dependency is not yet in graph, it must be an input
            if dep not in self.nodes and dep not in self.input_columns:
                self.add_input_column(dep, None, DataSource.INFERRED)
            
            self.edges.append(GraphEdge(source=dep, target=target))
    
    def get_node_stats(self) -> dict[str, Any]:
        """Get statistics about the graph."""
        input_nodes = sum(1 for n in self.nodes.values() if n.type == NodeType.INPUT)
        computed_nodes = sum(1 for n in self.nodes.values() if n.type == NodeType.COMPUTED)
        
        return {
            "total_nodes": len(self.nodes),
            "input_nodes": input_nodes,
            "computed_nodes": computed_nodes,
            "total_edges": len(self.edges),
            "node_names": list(self.nodes.keys()),
        }
    
    def to_dict(self) -> dict[str, Any]:
        """
        Convert the graph to a dictionary representation.
        
        Returns:
            Dictionary with "nodes" and "edges" keys
        """
        # Preserve order of nodes as they were created
        ordered_nodes = []
        for node_id in self._node_order:
            if node_id in self.nodes:
                node = self.nodes[node_id]
                ordered_nodes.append(node.model_dump())
        
        return {
            "nodes": ordered_nodes,
            "edges": [edge.model_dump() for edge in self.edges]
        }
    
    def find_roots(self) -> list[str]:
        """Find root nodes (nodes with no incoming edges)."""
        targets = {edge.target for edge in self.edges}
        return [node_id for node_id in self.nodes if node_id not in targets]
    
    def find_leaves(self) -> list[str]:
        """Find leaf nodes (nodes with no outgoing edges)."""
        sources = {edge.source for edge in self.edges}
        return [node_id for node_id in self.nodes if node_id not in sources]
    
    def get_dependencies(self, node_id: str) -> list[str]:
        """Get direct dependencies of a node."""
        return [edge.source for edge in self.edges if edge.target == node_id]
    
    def get_dependents(self, node_id: str) -> list[str]:
        """Get nodes that depend on the given node."""
        return [edge.target for edge in self.edges if edge.source == node_id]