# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Static-walk derivation of engine_binding for an IR.

Closed-subset whitelist — operators safe to lower to portable backends
(JAX, future engines) without semantic divergence:

  - Polars Expr basics: pl.col, pl.lit, arithmetic (+, -, *, /, **)
  - Comparisons: ==, !=, <, <=, >, >=
  - Boolean: &, |, ~
  - when().then().otherwise()
  - Already-typed inputs: Schedule.year_fractions_expr,
    Curve.spot_rate / discount_factor / forward_rate
  - MortalityTable.at, Table.lookup

Anything outside this set — pl.max_horizontal, pl.min_horizontal, raw
.list / .arr namespace calls, autopatched extension methods — flips
engine_binding to ``'polars'``.

Implementation: serialize each Expr via meta string-form and look for
known non-portable signatures. False positives (rare) push a model to
``'polars'`` unnecessarily but never let an unsafe Expr pass as
``'portable'``. A typed AST walk can replace this if precision becomes
load-bearing.
"""

from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.rollforward._ir import IR, EngineBinding
    from gaspatchio_core.rollforward._ops import Op


_NON_PORTABLE_SIGNATURES: frozenset[str] = frozenset(
    {
        "max_horizontal",
        "min_horizontal",
        "sum_horizontal",
        "any_horizontal",
        "all_horizontal",
        # autopatched extension namespaces flagged conservatively
        ".gp.",
    }
)


def _expr_is_polars_only(expr: pl.Expr | None) -> bool:
    if expr is None:
        return False
    s = str(expr)
    return any(sig in s for sig in _NON_PORTABLE_SIGNATURES)


def _op_uses_polars_only(op: Op) -> bool:
    # Pull every Expr field off the dataclass and check each
    for f in fields(op):  # type: ignore[arg-type]
        value = getattr(op, f.name)
        if _expr_is_polars_only(value):
            return True
    return False


def derive_engine_binding(ir: IR) -> EngineBinding:
    """Return ``'portable'`` iff every Expr in the IR is closed-subset.

    Inspects:
      - Each transition Op's Expr-typed fields
      - The contract_boundary mask (if any)
      - Each State's init Expr
    """
    for state in ir.states:
        if _expr_is_polars_only(state.init):
            return "polars"
    for op in ir.transitions:
        if _op_uses_polars_only(op):
            return "polars"
    if _expr_is_polars_only(ir.contract_boundary):
        return "polars"
    return "portable"


__all__ = ["derive_engine_binding"]
