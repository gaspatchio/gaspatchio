# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars-specific lowering for Gaspatchio's DSL.

This subpackage contains everything that knows about Polars:
- plugin function wrappers (``plugins.py``)
- list-aware operator implementations (``operators.py``)
- boolean-mask arithmetic-as-logic (``masks.py``)
- ``list.eval`` restrictions (``list_eval.py``)

The frontend (``column/``, ``frame/``, ``functions/``) imports from here
when it needs to emit Polars expressions; nothing in ``polars_backend/``
imports from ``column/`` at module load time. The ``masks.py`` and
``list_eval.py`` modules contain bounded function-local imports from
``column/`` for proxy-type dispatch — documented at the call sites.
"""

from gaspatchio_core.polars_backend.list_eval import unwrap_for_list_eval
from gaspatchio_core.polars_backend.masks import (
    boolean_and,
    boolean_not,
    boolean_or,
    to_boolean_expr,
)
from gaspatchio_core.polars_backend.operators import (
    dispatch_list_op,
    execute_list_clip,
    execute_list_pow,
)
from gaspatchio_core.polars_backend.plugins import (
    accumulate,
    fill_series,
    floor,
    list_clip,
    list_conditional,
    list_pow,
    round,
    round_to_int,
)

__all__ = [
    "accumulate",
    "boolean_and",
    "boolean_not",
    "boolean_or",
    "dispatch_list_op",
    "execute_list_clip",
    "execute_list_pow",
    "fill_series",
    "floor",
    "list_clip",
    "list_conditional",
    "list_pow",
    "round",
    "round_to_int",
    "to_boolean_expr",
    "unwrap_for_list_eval",
]
