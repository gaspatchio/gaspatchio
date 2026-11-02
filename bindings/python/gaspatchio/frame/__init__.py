# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The ActuarialFrame, its model runner, and its calculation graph."""

from .base import ActuarialFrame
from .execution import run_model
from .graph import (
    CalcGraph,
    GraphExportConfig,
    GraphExporter,
    analyze_expression_tree,
    extract_dependencies,
    fold,
)

__all__ = [
    "ActuarialFrame",
    "CalcGraph",
    "GraphExportConfig",
    "GraphExporter",
    "analyze_expression_tree",
    "extract_dependencies",
    "fold",
    "run_model",
]

# Registration is a composition concern. Graph inspection itself reads only the
# frame view, while virtual ABC registration preserves accessor runtime checks.
from gaspatchio.accessors.base import BaseColumnAccessor as _BaseColumnAccessor
from gaspatchio.accessors.base import BaseFrameAccessor as _BaseFrameAccessor
from gaspatchio.frame.graph.calc_graph import GraphFrameAccessor as _GraphFrameAccessor
from gaspatchio.frame.registry import (
    _AccessorBindings,
    _configure_accessors,
)
from gaspatchio.frame.registry import (
    register_accessor as _register_accessor,
)

_configure_accessors(
    _AccessorBindings(ActuarialFrame, _BaseFrameAccessor, _BaseColumnAccessor)
)
_BaseFrameAccessor.register(_GraphFrameAccessor)
_register_accessor("graph", kind="frame")(_GraphFrameAccessor)
