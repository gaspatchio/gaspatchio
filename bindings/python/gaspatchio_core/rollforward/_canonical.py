# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""IR → JSON canonical form.

Deterministic dict suitable for ``json.dumps(sort_keys=True)``. Two IRs
producing the same canonical form have identical spec_fingerprint.

Per spec §9.1:
  - States: name, init Expr (string-form), in declared order
  - Points: declared list, in declared order
  - Transitions: typed Op list, in declared order, with all Exprs canonicalised
  - Schedule: embedded canonical_form() dict
  - batch_axes: hashed only when NOT the engine default ('policy',)
  - track_increments: bool
  - lapse_when_all_non_positive: sorted state names
  - contract_boundary: Expr string-form when set, None otherwise
  - engine_binding: 'portable' | 'polars'
"""

from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING, Any

from gaspatchio_core.rollforward._engine_binding import derive_engine_binding

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._ir import IR
    from gaspatchio_core.rollforward._ops import Op

_DEFAULT_BATCH_AXES: tuple[str, ...] = ("policy",)


def _expr_canonical(expr: Any) -> str | None:  # noqa: ANN401
    if expr is None:
        return None
    return str(expr)


def _op_canonical(op: Op) -> dict[str, Any]:
    out: dict[str, Any] = {"op": type(op).__name__}
    for f in fields(op):  # type: ignore[arg-type]
        v = getattr(op, f.name)
        if v is None:
            out[f.name] = None
        elif hasattr(v, "canonical_name"):
            out[f.name] = v.canonical_name()
        elif isinstance(v, (int, float, str, bool)):
            out[f.name] = v
        else:
            # Polars Expr or similar — string-form
            out[f.name] = _expr_canonical(v)
    return out


def canonical_form(ir: IR) -> dict[str, Any]:
    """Return the JSON-encodable canonical form of an IR."""
    out: dict[str, Any] = {
        "states": [
            {"name": s.name, "init": _expr_canonical(s.init)} for s in ir.states
        ],
        "points": list(ir.points),
        "transitions": [_op_canonical(op) for op in ir.transitions],
        "schedule": ir.schedule.canonical_form(),
        "track_increments": ir.track_increments,
        "lapse_when_all_non_positive": sorted(ir.lapse_when_all_non_positive),
        "contract_boundary": _expr_canonical(ir.contract_boundary),
        "engine_binding": derive_engine_binding(ir),
    }
    # batch_axes — omit when default
    if ir.batch_axes != _DEFAULT_BATCH_AXES:
        out["batch_axes"] = list(ir.batch_axes)
    return out


__all__ = ["canonical_form"]
