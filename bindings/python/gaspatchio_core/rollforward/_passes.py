# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Compilation passes — CVXPY-style reduction chain.

Each pass implements ``Pass`` Protocol: ``name()`` returns a stable string
used in TRACE-level logs; ``apply(ir)`` returns a transformed IR. Passes
are pure functions over IRs (no shared mutable state); rerun-friendly.

Pass chain:
  Validate           — per-Op verify(); state/point consistency
  ResolveStateRefs   — compile-time check that every StateRef points
                       at a declared state and a declared point
  FoldConstants      — pass-through; Polars's optimiser folds eagerly
  AssignCaptureSlots — collect every (state, point) read-pair into
                       slot indices for Struct emission
  LowerToPolarsPlugin — IR + slot table → plugin_kwargs dict + args list
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Protocol

import polars as pl

from gaspatchio_core.rollforward._ops import (
    Add,
    Apply,
    Charge,
    DeductNAR,
    Floor,
    Grow,
    GrowCapped,
    Ratchet,
    Subtract,
)
from gaspatchio_core.rollforward._refs import StateRef

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._ir import IR
    from gaspatchio_core.rollforward._ops import Op


class Pass(Protocol):
    def name(self) -> str: ...
    def apply(self, ir: IR) -> IR: ...


@dataclass(frozen=True)
class Validate:
    """Per-Op verify(), state/point consistency, track_increments label gate."""

    def name(self) -> str:
        return "validate"

    def apply(self, ir: IR) -> IR:
        state_names = {s.name for s in ir.states}
        for op in ir.transitions:
            target = getattr(op, "target", None)
            if target is None:
                msg = f"{type(op).__name__} has no target StateRef"
                raise ValueError(msg)
            if target.state not in state_names:
                msg = (
                    f"{type(op).__name__} targets unknown state {target.state!r}; "
                    f"declared states are {sorted(state_names)}"
                )
                raise ValueError(msg)
            if target.point not in ir.points:
                msg = (
                    f"{type(op).__name__} targets unknown point {target.point!r}; "
                    f"declared points are {list(ir.points)}"
                )
                raise ValueError(msg)
            # Per-Op verify (e.g., Charge negative-literal check)
            op.verify()
            # When track_increments=True every label-bearing Op must have a label
            if ir.track_increments:
                op_fields = {f.name for f in fields(op)}  # type: ignore[arg-type]
                if "label" in op_fields and getattr(op, "label", None) is None:
                    msg = (
                        "track_increments=True requires every label-bearing Op to "
                        f"have label=...; {type(op).__name__} has label=None"
                    )
                    raise ValueError(msg)
        return ir


@dataclass(frozen=True)
class ResolveStateRefs:
    """Compile-time check that every StateRef references a declared state/point.

    Validate has already checked target StateRefs; this pass is a no-op
    transform reserved for cross-state-ref lowering work that integrates
    with the slot table.
    """

    def name(self) -> str:
        return "resolve_state_refs"

    def apply(self, ir: IR) -> IR:
        # Pass-through. Cross-state lowering happens in
        # AssignCaptureSlots + LowerToPolarsPlugin.
        return ir


@dataclass(frozen=True)
class FoldConstants:
    """Constant folding pass.

    Pass-through stub. Polars already does eager constant folding inside
    its query optimiser, so duplicating that here adds no value. Re-add
    real folding here if benchmarks identify a reduction opportunity.
    """

    def name(self) -> str:
        return "fold_constants"

    def apply(self, ir: IR) -> IR:
        return ir


@dataclass(frozen=True)
class AssignCaptureSlots:
    """Collect every (state, point) read into a sorted slot table.

    The slot table is what the kernel uses to decide which fields to
    emit on its per-row Struct output. Every state's ``eop`` is
    captured implicitly so user-side ``compiled.expr_for(state)`` works
    without an explicit ``point="eop"`` annotation.

    Returns the unchanged IR via ``apply``; the slot table is exposed via
    ``apply_with_slots``.
    """

    def name(self) -> str:
        return "assign_capture_slots"

    def apply(self, ir: IR) -> IR:
        return ir  # the IR itself is unchanged; the slots travel separately

    def apply_with_slots(self, ir: IR) -> tuple[IR, tuple[StateRef, ...]]:
        slots: set[StateRef] = set()
        # Implicit: every state's eop is a capture slot
        for s in ir.states:
            slots.add(StateRef(state=s.name, point="eop"))
        # Capture every Op's target so the kernel can address it.
        # Cross-state reads encoded as Polars Exprs (e.g. ``b["s"].at("p")``
        # returning a StateRef embedded inside a pl.Expr field) are picked
        # up by walking Op body Exprs in LowerToPolarsPlugin.
        for op in ir.transitions:
            target = getattr(op, "target", None)
            if target is not None:
                slots.add(target)
        # Sort for determinism: by state name, then by point order in the IR.
        ordered = tuple(
            sorted(slots, key=lambda r: (r.state, ir.points.index(r.point))),
        )
        return ir, ordered


def _single_column_name(expr: pl.Expr, op_name: str, field_name: str) -> str:
    """Return the single column name referenced by ``expr`` or raise.

    Op exprs (Add.expr, Subtract.expr, Charge.rate, Grow.rate, etc.)
    must be ``pl.col("name")`` — a bare column reference. Compound
    expressions like ``pl.col("a") + pl.col("b")`` raise
    ``NotImplementedError``: precompute them as input columns.
    """
    roots = expr.meta.root_names()
    if len(roots) != 1:
        msg = (
            f"Op exprs must be single-column refs; "
            f"{op_name}.{field_name} references {len(roots)} columns: {roots}"
        )
        raise NotImplementedError(msg)
    name = roots[0]
    expected = f'col("{name}")'
    actual = str(expr)
    if actual != expected:
        msg = (
            f"Op exprs must be bare column refs (pl.col(...)); "
            f"{op_name}.{field_name} is {actual!r}"
        )
        raise NotImplementedError(msg)
    return name


@dataclass(frozen=True)
class LowerToPolarsPlugin:
    """Lower an IR + slot table into a JSON-serialisable plugin_kwargs dict.

    The dict is consumed by the Rust kernel as the bridge between the
    compile-time IR and runtime execution.

    Kwargs schema:
      ir: canonical_form dict
      captures: list[[state, point]] in slot order
      track_increments: bool
      lapse_when_all_non_positive: list[str]  (sorted)
      contract_boundary: str | None  (Expr string-form when set)
      n_states, n_points, n_periods: ints
      bop_idx, eop_idx: indices into ir.points
      input_columns: column names referenced by Ops, in args order
      ops: list of resolved Op dicts with arg-indices
      captures_resolved: list of {state: int, point: int}
    """

    def name(self) -> str:
        return "lower_polars"

    def apply(self, ir: IR) -> IR:
        return ir

    def lower(
        self,
        ir: IR,
        slots: tuple[StateRef, ...],
    ) -> tuple[dict[str, object], list[pl.Expr]]:
        from gaspatchio_core.rollforward._canonical import canonical_form

        # ---- args list: state inits first, then unique input columns ----
        args: list[pl.Expr] = [s.init for s in ir.states]

        input_columns: list[str] = []
        column_index: dict[str, int] = {}

        def _register_column(name: str) -> int:
            if name in column_index:
                return column_index[name]
            idx = len(input_columns)
            input_columns.append(name)
            column_index[name] = idx
            return idx

        state_index = {s.name: i for i, s in enumerate(ir.states)}
        point_index = {p: i for i, p in enumerate(ir.points)}

        def _classify_arg(
            expr: pl.Expr,
            op_name: str,
            field_name: str,
        ) -> dict[str, object]:
            """Classify a ``pl.col(name)`` arg as Input or State.

            A name of the form ``"state@point"`` whose components match a
            declared state and point is a cross-state read; otherwise the
            name is a precomputed input column registered via
            ``_register_column``.
            """
            name = _single_column_name(expr, op_name, field_name)
            if "@" in name:
                state_name, point_name = name.split("@", 1)
                if state_name in state_index and point_name in point_index:
                    return {
                        "kind": "state",
                        "state": state_index[state_name],
                        "point": point_index[point_name],
                    }
            return {"kind": "input", "idx": _register_column(name)}

        ops: list[dict[str, object]] = []
        for op in ir.transitions:
            target = op.target  # type: ignore[attr-defined]
            target_state = state_index[target.state]
            target_point = point_index[target.point]
            entry = _resolve_op(
                op,
                target_state=target_state,
                target_point=target_point,
                classify=_classify_arg,
            )
            ops.append(entry)

        captures_resolved = [
            {"state": state_index[s.state], "point": point_index[s.point]}
            for s in slots
        ]

        n_periods = int(ir.schedule.canonical_form()["n_periods"])

        # Pre-resolve lapse state names → state indices.
        lapse_state_indices = sorted(
            state_index[name] for name in ir.lapse_when_all_non_positive
        )

        # Resolve contract_boundary Expr (if set) to an input-arg index.
        # Must be a single-column ref to a precomputed input list —
        # state-refs are not supported for the boundary mask.
        contract_boundary_arg: int | None = None
        if ir.contract_boundary is not None:
            contract_boundary_arg = _register_column(
                _single_column_name(
                    ir.contract_boundary,
                    "<rollforward>",
                    "contract_boundary",
                ),
            )

        kwargs: dict[str, object] = {
            "ir": canonical_form(ir),
            "captures": [[s.state, s.point] for s in slots],
            "track_increments": ir.track_increments,
            "lapse_when_all_non_positive": sorted(ir.lapse_when_all_non_positive),
            "contract_boundary": (
                str(ir.contract_boundary) if ir.contract_boundary is not None else None
            ),
            # Pre-resolved fields for the Rust kernel
            "n_states": len(ir.states),
            "n_points": len(ir.points),
            "n_periods": n_periods,
            "bop_idx": point_index["bop"],
            "eop_idx": point_index["eop"],
            "input_columns": list(input_columns),
            "ops": ops,
            "captures_resolved": captures_resolved,
            "lapse_state_indices": lapse_state_indices,
            "contract_boundary_arg": contract_boundary_arg,
        }
        # Append the registered input column expressions to args so the
        # kernel can locate them by index.
        args.extend(pl.col(name) for name in input_columns)

        # For jagged (per_policy_grid) schedules, thread the authoritative
        # per-policy period count as a trailing input so the kernel sizes each
        # policy's projection from its own horizon — independent of whichever
        # input list happens to be first, and correct even with no input lists.
        if getattr(ir.schedule, "_kind", None) == "per_policy_grid":
            kwargs["per_policy_lengths_arg"] = len(args)  # n_states + n_input_cols
            args.append(ir.schedule.per_policy_period_count_expr())

        return kwargs, args


def _resolve_op(  # noqa: PLR0911
    op: Op,
    *,
    target_state: int,
    target_point: int,
    classify: object,
) -> dict[str, object]:
    """Resolve a single Op into the JSON-serialisable kernel dict shape.

    Every ``*_arg`` slot is a tagged dict —
    ``{"kind": "input", "idx": int}`` for precomputed list-column refs,
    ``{"kind": "state", "state": int, "point": int}`` for cross-state reads.
    """
    # ``classify`` is callable (expr, op_name, field_name) -> dict
    cls = classify  # type: ignore[assignment]

    op_name = type(op).__name__
    base: dict[str, object] = {
        "op": op_name,
        "target_state": target_state,
        "target_point": target_point,
    }
    if isinstance(op, Add):
        base["expr_arg"] = cls(op.expr, op_name, "expr")  # type: ignore[operator]
        base["label"] = op.label
        return base
    if isinstance(op, Subtract):
        base["expr_arg"] = cls(op.expr, op_name, "expr")  # type: ignore[operator]
        base["label"] = op.label
        return base
    if isinstance(op, Charge):
        base["rate_arg"] = cls(op.rate, op_name, "rate")  # type: ignore[operator]
        base["label"] = op.label
        return base
    if isinstance(op, Grow):
        base["rate_arg"] = cls(op.rate, op_name, "rate")  # type: ignore[operator]
        base["label"] = op.label
        return base
    if isinstance(op, GrowCapped):
        base["rate_arg"] = cls(op.rate, op_name, "rate")  # type: ignore[operator]
        base["floor_arg"] = cls(op.floor, op_name, "floor")  # type: ignore[operator]
        base["cap_arg"] = cls(op.cap, op_name, "cap")  # type: ignore[operator]
        base["label"] = op.label
        return base
    if isinstance(op, DeductNAR):
        base["coi_rate_arg"] = cls(op.coi_rate, op_name, "coi_rate")  # type: ignore[operator]
        base["death_benefit_arg"] = cls(  # type: ignore[operator]
            op.death_benefit,
            op_name,
            "death_benefit",
        )
        base["label"] = op.label
        return base
    if isinstance(op, Ratchet):
        base["to_arg"] = cls(op.to, op_name, "to")  # type: ignore[operator]
        base["when_arg"] = (
            cls(op.when, op_name, "when") if op.when is not None else None  # type: ignore[operator]
        )
        base["label"] = op.label
        return base
    if isinstance(op, Floor):
        base["value"] = float(op.value)
        return base
    if isinstance(op, Apply):
        base["body_arg"] = cls(op.body, op_name, "body")  # type: ignore[operator]
        base["label"] = op.label
        return base
    msg = f"unknown Op type {op_name!r}"
    raise TypeError(msg)


__all__ = [
    "AssignCaptureSlots",
    "FoldConstants",
    "LowerToPolarsPlugin",
    "Pass",
    "ResolveStateRefs",
    "Validate",
]
