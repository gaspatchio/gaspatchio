# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Graph nodes carry shape and kind derived from the shape SOT helpers."""

from __future__ import annotations

import json

import polars as pl

from gaspatchio import ActuarialFrame, set_default_mode
from gaspatchio.column.shape import kind_from_dtype, shape_from_dtype
from gaspatchio.frame.graph.calc_graph import GraphExporter
from gaspatchio.frame.graph.graph_builder import CalculationGraph
from gaspatchio.frame.graph.graph_models import DataSource


class TestDtypeHelpers:
    """The dtype-only classification helpers exposed by the shape SOT."""

    def test_shape_from_dtype(self) -> None:
        """List dtypes are list-shaped; plain dtypes scalar; None unknown."""
        assert shape_from_dtype(pl.List(pl.Float64)) == "list"
        assert shape_from_dtype(pl.Float64) == "scalar"
        assert shape_from_dtype(None) == "unknown"

    def test_kind_from_dtype(self) -> None:
        """Boolean dtypes are masks; other dtypes values; None unknown."""
        assert kind_from_dtype(pl.Boolean) == "boolean_mask"
        assert kind_from_dtype(pl.List(pl.Boolean)) == "boolean_mask"
        assert kind_from_dtype(pl.Float64) == "value"
        assert kind_from_dtype(pl.List(pl.Float64)) == "value"
        assert kind_from_dtype(None) == "unknown"


class TestNodeShapeKind:
    """Graph nodes are stamped with shape and kind at construction."""

    def test_input_nodes_carry_shape_and_kind(self) -> None:
        """Input nodes classify their schema dtype through the SOT helpers."""
        graph = CalculationGraph()
        graph.add_input_column("rates", pl.List(pl.Float64), DataSource.MODEL_POINTS)
        graph.add_input_column("age", pl.Int64, DataSource.MODEL_POINTS)
        graph.add_input_column("flag", pl.Boolean, DataSource.MODEL_POINTS)
        assert graph.nodes["rates"].data.shape == "list"
        assert graph.nodes["rates"].data.kind == "value"
        assert graph.nodes["age"].data.shape == "scalar"
        assert graph.nodes["age"].data.kind == "value"
        assert graph.nodes["flag"].data.shape == "scalar"
        assert graph.nodes["flag"].data.kind == "boolean_mask"

    def test_exported_computed_nodes_carry_shape(self) -> None:
        """A debug-mode trace exports computed nodes with resolved shapes."""
        set_default_mode("debug")
        try:
            af = ActuarialFrame({"age": [30, 40], "rates": [[0.1, 0.2], [0.3, 0.4]]})

            @af.trace
            def build(f: ActuarialFrame) -> None:
                f.double_rates = f.rates * 2.0

            build(af)
            payload = json.loads(GraphExporter(af).export())
        finally:
            set_default_mode("optimize")
        nodes = {n["id"]: n["data"] for n in payload["nodes"]}
        assert nodes["age"]["shape"] == "scalar"
        assert nodes["rates"]["shape"] == "list"
        assert nodes["double_rates"]["shape"] == "list"
        assert nodes["double_rates"]["kind"] == "value"

    def test_backfill_resolves_dtype_lost_by_tracing(self) -> None:
        """A None tracing dtype falls back to the frame's collected schema."""
        set_default_mode("debug")
        try:
            af = ActuarialFrame({"age": [30, 40], "rates": [[0.1, 0.2], [0.3, 0.4]]})

            @af.trace
            def build(f: ActuarialFrame) -> None:
                f.double_rates = f.rates * 2.0

            build(af)
            for op in af._computation_graph:  # noqa: SLF001
                if not isinstance(op, tuple):
                    op.expected_dtype = None
            payload = json.loads(GraphExporter(af).export())
        finally:
            set_default_mode("optimize")
        node = {n["id"]: n["data"] for n in payload["nodes"]}["double_rates"]
        assert node["shape"] == "list"
        assert node["kind"] == "value"
        assert node["dtype"] != "unknown"
