# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Graph nodes carry their shape from the shape SOT helper that resolves it."""

from __future__ import annotations

import json

import polars as pl

from gaspatchio import ActuarialFrame, set_default_mode
from gaspatchio._shape import shape_from_dtype
from gaspatchio.frame.graph.calc_graph import GraphExporter
from gaspatchio.frame.graph.graph_builder import fold
from gaspatchio.frame.graph.graph_models import Provenance


class TestDtypeHelpers:
    """The dtype-only classification helper exposed by the shape SOT."""

    def test_shape_from_dtype(self) -> None:
        """List dtypes are list-shaped; plain dtypes scalar; None unknown."""
        assert shape_from_dtype(pl.List(pl.Float64)) == "list"
        assert shape_from_dtype(pl.Float64) == "scalar"
        assert shape_from_dtype(None) == "unknown"


class TestNodeShapeKind:
    """Graph nodes are stamped with shape and provenance at construction."""

    def test_input_nodes_carry_shape_and_provenance(self) -> None:
        """An arriving column takes its shape from the schema dtype, and says so.

        What such a column *holds* is not a field of its own: a selection is
        read off ``dtype``, which is where the type vocabulary puts it and
        the only place that cannot disagree with itself.
        """
        af = ActuarialFrame(
            {
                "rates": [[0.1, 0.2], [0.3, 0.4]],
                "age": [30, 40],
                "flag": [True, False],
            }
        )
        graph = fold(af)
        assert graph.nodes["rates"].data.provenance is Provenance.MODEL_POINTS
        assert graph.nodes["rates"].data.shape == "list"
        assert graph.nodes["rates"].data.dtype == "list[f64]"
        assert graph.nodes["age"].data.shape == "scalar"
        assert graph.nodes["age"].data.dtype == "i64"
        assert graph.nodes["flag"].data.shape == "scalar"
        assert graph.nodes["flag"].data.dtype == "bool"

    def test_exported_computed_nodes_carry_shape(self) -> None:
        """A debug-mode trace exports computed nodes with resolved shapes."""
        set_default_mode("debug")
        try:
            af = ActuarialFrame({"age": [30, 40], "rates": [[0.1, 0.2], [0.3, 0.4]]})

            @af.trace
            def build(f: ActuarialFrame) -> None:
                f.double_rates = f.rates * 2.0

            build(af)
            artifact = json.loads(GraphExporter(af).export())
        finally:
            set_default_mode("optimize")
        nodes = {n["id"]: n for n in artifact["nodes"]}
        assert nodes["age"]["shape"] == "scalar"
        assert nodes["rates"]["shape"] == "list"
        assert nodes["double_rates@1"]["shape"] == "list"

    def test_backfill_resolves_dtype_a_record_could_not(self) -> None:
        """A None recorded dtype falls back to the frame's collected schema."""
        set_default_mode("debug")
        try:
            af = ActuarialFrame({"age": [30, 40], "rates": [[0.1, 0.2], [0.3, 0.4]]})

            @af.trace
            def build(f: ActuarialFrame) -> None:
                f.double_rates = f.rates * 2.0

            build(af)
            for record in af._calculations:  # noqa: SLF001
                record.dtype = None
            artifact = json.loads(GraphExporter(af).export())
        finally:
            set_default_mode("optimize")
        node = {n["id"]: n for n in artifact["nodes"]}["double_rates@1"]
        assert node["shape"] == "list"
        assert node["dtype"] != "unknown"
