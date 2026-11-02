# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The compiled machine's two forms: its identity, and the kernel's payload.

**The identity form** (:func:`identity_form`, :func:`compiled_identity`) is the
compilation body the ``gaspatchio_rollforward_ir`` facet publishes, less its
``schedule`` member, hashed under the section 12.3 recipe grammar (spec 12.1). It is
taken over what the file holds -- the operand trees, the settings, the
operation names -- and not over any engine's rendering of an expression, so a
reader holding the facet recomputes the identity of the machine it is about to
run, and a second producer reaches the same string from the same machine.

**The kernel form** (:func:`canonical_form`) is the dict the Rust kernel is
handed as its ``ir`` argument. It names no identity and is never hashed.
Deterministic dict suitable for ``json.dumps(sort_keys=True)``. It holds the
**machine**, and only the machine:
  - States: name, init Expr (string-form), in declared order
  - Points: declared list, in declared order
  - Transitions: typed Op list, in declared order, with all Exprs canonicalised
    -- each Op's kind, target, operands, label, rounding and timing settings
  - batch_axes: hashed only when NOT the engine default ('policy',)
  - track_increments: bool
  - lapse_when_all_non_positive: sorted state names
  - contract_boundary: Expr string-form when set, None otherwise
  - engine_binding: 'portable' | 'polars'

**The schedule is left out of the identity.** It is the data the machine runs
over -- how many periods, on what calendar or axis -- and not an operation the
machine applies, so a re-sourced schedule is a data change and leaves the
identity and the ``rollforward:`` node id where they were (spec 16). The schedule
still reaches the record: every rollforward call carries its ``source_sha()``
beside the fingerprint (``CompiledRollforward._emit``), so
``graph_fingerprint`` moves with it, and the pair is what the process
resolves a compilation by (``frame/lowering/artefacts.py``).
"""

from __future__ import annotations

import hashlib
from dataclasses import fields
from typing import TYPE_CHECKING, Any, Final

from gaspatchio._identity import SHA256_PREFIX, canonical_bytes
from gaspatchio.rollforward._engine_binding import derive_engine_binding

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio.rollforward._ir import IR
    from gaspatchio.rollforward._ops import Op

# The one member of a published compilation body its identity leaves out.
SCHEDULE_MEMBER: Final[str] = "schedule"


def identity_form(ir: IR) -> dict[str, Any]:
    """Return what the compiled fingerprint is taken over: the body, less schedule.

    Built by the facet's own projection (``machine_body``), so the identity
    and the body a file carries are one structure and cannot disagree.
    """
    # The graph package imports the lowering rules, which import this one.
    from gaspatchio.frame.graph.rollforward_ir import (  # noqa: PLC0415 — import cycle
        machine_body,
    )

    body = machine_body(ir)
    del body[SCHEDULE_MEMBER]
    return body


def compiled_identity(body: Mapping[str, Any]) -> str:
    """Return the identity a published compilation body names itself by.

    The section 12.3 recipe-grammar hash of the body exactly as published,
    less its ``schedule`` member: what the producer stamps as the compiled
    fingerprint, and what ``validate --deep`` and ``run-artifact`` recompute
    from a file and hold to the body's key.

    Raises:
        TypeError: If the body holds a value the recipe grammar cannot write.

    """
    form = {key: value for key, value in body.items() if key != SCHEDULE_MEMBER}
    return f"{SHA256_PREFIX}{hashlib.sha256(canonical_bytes(form)).hexdigest()}"


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
        "track_increments": ir.track_increments,
        "lapse_when_all_non_positive": sorted(ir.lapse_when_all_non_positive),
        "contract_boundary": _expr_canonical(ir.contract_boundary),
        "engine_binding": derive_engine_binding(ir),
    }
    # batch_axes — omit when default
    if ir.batch_axes != _DEFAULT_BATCH_AXES:
        out["batch_axes"] = list(ir.batch_axes)
    return out


__all__ = ["SCHEDULE_MEMBER", "canonical_form", "compiled_identity", "identity_form"]
