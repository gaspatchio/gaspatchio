# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Calculation graph builder for ActuarialFrame operations.

This module provides functionality to build a directed acyclic graph (DAG)
from traced operations, enabling visualization and analysis of calculation dependencies.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
from loguru import logger

from .filter_handler import DataFrameFilter
from .graph_builder import CalculationGraph
from .graph_models import DataSource, GraphExportConfig
from .trace_generator import TraceGenerator
from .value_extractor import SampleValueExtractor

if TYPE_CHECKING:
    from ..base import ActuarialFrame


class GraphExporter:
    """Handles exporting calculation graphs with optional data enhancement."""

    def __init__(self, af: ActuarialFrame):
        """
        Initialize the exporter with an ActuarialFrame.
        
        Args:
            af: ActuarialFrame with computation graph populated

        """
        self.af = af
        self._validate_computation_graph()

    def _validate_computation_graph(self) -> None:
        """Validate that the ActuarialFrame has a traced computation graph.

        Bare (name, expr) tuples — recorded on every frame for collect-error
        attribution (#39) — carry no metadata and cannot drive a calc graph;
        only TracedOperation records (debug-mode runs) count.
        """
        operations = getattr(self.af, "_computation_graph", None) or []
        if not any(not isinstance(op, tuple) for op in operations):
            raise ValueError(
                "No computation graph found. Ensure the model was run in debug mode "
                "by setting GSPIO_MODE=debug environment variable."
            )

    def export(
        self,
        result_df: pl.DataFrame | None = None,
        config: GraphExportConfig | None = None
    ) -> str:
        """
        Export the calculation graph to JSON.
        
        Args:
            result_df: Optional pre-computed DataFrame with actual values
            config: Optional export configuration
            
        Returns:
            JSON string representing the calculation graph

        """
        if config is None:
            config = GraphExportConfig()

        logger.info(f"Building calculation graph from {len(self.af._computation_graph)} operations")

        # Prepare DataFrame if provided
        if result_df is not None:
            result_df = self._prepare_dataframe(result_df, config)

        # Build the graph structure
        graph = self._build_graph_structure()

        # Enhance with sample values if DataFrame provided
        if result_df is not None:
            self._enhance_with_values(graph, result_df, config)

            # Add traces if requested
            if config.include_traces:
                self._add_traces(graph, result_df, config)

        # Log statistics
        self._log_statistics(graph, result_df)

        return json.dumps(graph.to_dict(), indent=2)

    def _prepare_dataframe(
        self,
        df: pl.DataFrame,
        config: GraphExportConfig
    ) -> pl.DataFrame:
        """Prepare DataFrame by applying filters if specified."""
        logger.debug(f"Result DataFrame has {len(df)} rows and columns: {df.columns}")

        if config.filter_expr:
            filter_handler = DataFrameFilter(df)
            df = filter_handler.apply_filter(config.filter_expr)

        return df

    def _build_graph_structure(self) -> CalculationGraph:
        """Build the basic graph structure from operations."""
        graph = CalculationGraph()

        # Add input columns
        self._add_input_columns(graph)

        # Add computed operations (skipping bare attribution tuples — no metadata)
        for operation in self.af._computation_graph:
            if isinstance(operation, tuple):
                continue
            graph.add_computed_operation(operation)

        self._backfill_unresolved_dtypes(graph)
        return graph

    def _backfill_unresolved_dtypes(self, graph: CalculationGraph) -> None:
        """Resolve dtype/shape/kind from the final schema where tracing could not.

        Tracing-time dtype inference is a per-assignment probe and can return
        None (a probe failure also cascades to downstream assignments). The
        collected schema holds the authoritative dtype for every column that
        survived to the frame — prefer it over exporting "unknown".
        """
        from gaspatchio.column.shape import kind_from_dtype, shape_from_dtype

        from .graph_utils import simplify_dtype

        try:
            schema = self.af._df.collect_schema()  # noqa: SLF001
        except Exception as e:  # noqa: BLE001 — schema failure downgrades, never breaks export
            logger.warning(f"Could not collect schema for dtype backfill: {e}")
            return

        for node in graph.nodes.values():
            data = node.data
            if "unknown" not in (data.dtype, data.shape, data.kind):
                continue
            dtype = schema.get(node.id)
            if dtype is None:
                continue
            if data.dtype == "unknown":
                data.dtype = simplify_dtype(str(dtype))
            if data.shape == "unknown":
                data.shape = shape_from_dtype(dtype)
            if data.kind == "unknown":
                data.kind = kind_from_dtype(dtype)

    def _add_input_columns(self, graph: CalculationGraph) -> None:
        """Identify and add input columns to the graph."""
        try:
            schema = self.af._df.collect_schema()
            potential_inputs = set(schema.names())
            # Tuple-recorded columns (#39) are computed too — counting them
            # as inputs would export wrong lineage (a computed column shown
            # as a raw model-point field with no formula).
            computed_columns = {
                op[0] if isinstance(op, tuple) else op.alias
                for op in self.af._computation_graph
                if isinstance(op, tuple) or hasattr(op, "alias")
            }

            # Initial input columns are those in schema but not computed
            initial_inputs = potential_inputs - computed_columns

            for col_name in initial_inputs:
                dtype = schema.get(col_name)
                graph.add_input_column(col_name, dtype, DataSource.MODEL_POINTS)

            logger.trace(f"Identified {len(initial_inputs)} initial input columns")
        except Exception as e:
            logger.warning(f"Could not extract schema for input detection: {e}")

    def _enhance_with_values(
        self,
        graph: CalculationGraph,
        df: pl.DataFrame,
        config: GraphExportConfig
    ) -> None:
        """Add sample values to graph nodes."""
        extractor = SampleValueExtractor(df, config.policy_id, config.policy_id_column)

        for node_id, node in graph.nodes.items():
            sample_value = extractor.extract(node_id)
            if sample_value is not None:
                node.data.value_sample = sample_value
                logger.trace(f"Added sample value for {node_id}: {sample_value}")

    def _add_traces(
        self,
        graph: CalculationGraph,
        df: pl.DataFrame,
        config: GraphExportConfig
    ) -> None:
        """Add calculation traces to computed nodes."""
        logger.info("Generating calculation traces for computed nodes")

        # Build value map
        node_values = {
            node_id: node.data.value_sample
            for node_id, node in graph.nodes.items()
            if node.data.value_sample is not None
        }

        # Initialize trace generator
        trace_gen = TraceGenerator(node_values)

        # Process computed nodes
        computed_count = 0
        trace_count = 0

        for node_id, node in graph.nodes.items():
            if node.type.value == "computed":
                computed_count += 1

                if node.data.value_sample is None:
                    logger.trace(f"Skipping trace for {node_id}: no sample value")
                    continue

                try:
                    trace = trace_gen.generate_trace(
                        node.data.formula,
                        node.data.dependencies,
                        node.data.value_sample
                    )
                    node.data.trace = trace
                    trace_count += 1
                    logger.trace(f"Generated trace for {node_id} with {len(trace)} steps")
                except Exception as e:
                    logger.warning(f"Failed to generate trace for {node_id}: {e}")

        logger.info(f"Generated traces for {trace_count}/{computed_count} computed nodes")

    def _log_statistics(self, graph: CalculationGraph, df: pl.DataFrame | None) -> None:
        """Log graph statistics."""
        stats = graph.get_node_stats()
        logger.info(
            f"Graph built: {stats['total_nodes']} nodes "
            f"({stats['input_nodes']} inputs, {stats['computed_nodes']} computed), "
            f"{stats['total_edges']} edges"
        )

        if df is not None:
            nodes_with_values = sum(
                1 for node in graph.nodes.values()
                if node.data.value_sample is not None
            )
            logger.info(f"Added sample values to {nodes_with_values}/{stats['total_nodes']} nodes")

