# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""frame.lowering -- turning the semantic op-tree into engine expressions.

``lower_polars`` is the sole producer of Polars expressions from an
``OpNode`` (see ``gaspatchio._semantic.ir``); ``LoweringContext`` is the
frame view it consults for the shape-dependent rules, built from a proxy's
parent frame by ``context_for``. ``to_node`` is the opposite door: it turns
one operand -- proxy, raw expression, or plain value -- into the node that
stands for it, recording a raw Polars expression in ``NATIVE_REFS`` on the
way through. ``LOWERINGS`` is the ``Call`` registry accessor modules
extend as their expression-building bodies relocate here.
``LoweringError`` is the loud-refusal exception raised for any node this
backend has no rule for.
"""

from __future__ import annotations

from gaspatchio.frame.lowering import polars, rules
from gaspatchio.frame.lowering.context import LoweringContext, context_for
from gaspatchio.frame.lowering.ingress import NATIVE_REFS, to_node
from gaspatchio.frame.lowering.polars import (
    LOWERINGS,
    LoweringError,
    lower_polars,
)

__all__ = [
    "LOWERINGS",
    "NATIVE_REFS",
    "LoweringContext",
    "LoweringError",
    "context_for",
    "lower_polars",
    "to_node",
]


def _load_rules() -> None:
    """Load the concrete rules when the dispatcher first needs them."""
    rules.load()


polars._load_rules = _load_rules  # noqa: SLF001 - composition root wires the backend
