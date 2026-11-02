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
from loguru import logger

from gaspatchio.frame.lowering.columns import column_reference
from gaspatchio.frame.lowering.rules.schedule import _per_policy_period_count
from gaspatchio.rollforward._canonical import canonical_form
from gaspatchio.rollforward._data import CompiledData
from gaspatchio.rollforward._ops import (
    RESERVED_LABEL_CHARACTER,
    Add,
    Apply,
    Charge,
    DeductNAR,
    Floor,
    Grow,
    GrowCapped,
    Ratchet,
    Round,
    Subtract,
)
from gaspatchio.rollforward._refs import StateRef

if TYPE_CHECKING:
    from gaspatchio.rollforward._ir import IR
    from gaspatchio.rollforward._ops import Op


def _verify_label_characters(ir: IR) -> None:
    """Refuse a label carrying the character reserved for structural steps.

    Every step of a tracked rollforward emits an increment, and the two that
    carry no label — ``Floor`` and ``Round`` — emit under the synthetic key
    the kernel builds for them, ``floor@3``. A label free to carry ``@``
    could be spelled to collide with one, which is two movements under one
    struct field name and a waterfall row that cites one step and reads
    another.

    Refused whether or not this rollforward tracks, because the reservation
    is a fact about the label vocabulary rather than about a flag: a label
    accepted today and refused the moment tracking is switched on would make
    that flag a breaking change to a model that already ran.
    """
    for op in ir.transitions:
        label = getattr(op, "label", None)
        if label is None or RESERVED_LABEL_CHARACTER not in label:
            continue
        msg = (
            f"{type(op).__name__} carries the label {label!r}, and "
            f"{RESERVED_LABEL_CHARACTER!r} is reserved. A rollforward's "
            "structural steps — Floor and Round — have no label to give, so "
            "the kernel names their movements after the step: a Floor "
            "declared third emits 'floor@3'. A label carrying "
            f"{RESERVED_LABEL_CHARACTER!r} could be spelled to collide with "
            "one, which would put two movements under one name. Rename the "
            f"label without {RESERVED_LABEL_CHARACTER!r}."
        )
        raise ValueError(msg)


def _verify_unique_increment_labels(ir: IR) -> None:
    """Refuse duplicate labels under track_increments.

    Each labelled op emits its own ``increment_{label}`` struct field, so
    labels must be unique — two fields with one name cannot coexist. A
    structural step's key cannot collide with one of these: ``@`` is
    reserved and refused above, and no two structural steps share an ordinal.
    """
    seen: dict[str, str] = {}
    for op in ir.transitions:
        label = getattr(op, "label", None)
        if label is None:
            continue
        if label in seen:
            msg = (
                f"track_increments=True: duplicate op label {label!r} "
                f"({seen[label]} and {type(op).__name__}). Each labelled op "
                "emits its own increment field, so labels must be unique."
            )
            raise ValueError(msg)
        seen[label] = type(op).__name__


def _apply_refusal(op: Apply) -> NotImplementedError:
    """Return the refusal for a step the kernel has no evaluation for.

    ``Apply`` sets a state to its body at the target's point. It is in the
    operation vocabulary -- the artifact format names it -- but the kernel
    cannot evaluate it, so a compilation carrying one used to build and
    then fail inside every ``collect()``. It is refused by the first pass,
    before a tracked rollforward would ask for the step's label, and again
    where the kernel's arguments are built, so no path hands it an Apply.

    No named operation sets a balance outright, which is what the step does.
    Two of them compose to it exactly for a finite balance: subtracting the
    balance itself, read as ``pl.col("<state>@<point>")``, clears it, and
    adding the new value sets it, with both movements booked. An infinite or
    NaN balance stays NaN, since inf - inf is NaN, where setting it outright
    would give the new value. That is what the refusal names, and where it
    stops.
    """
    target = op.target
    named = "" if op.label is None else f" (label={op.label!r})"
    balance = f"pl.col('{target.state}@{target.point}')"
    msg = (
        f"The .apply() step on state {target.state!r}{named} sets the "
        f"balance to its body at {target.point!r}, and the rollforward "
        "kernel has no evaluation for that: a compilation carrying it could "
        "never run. A compiled rollforward runs its named operations, and "
        "none of them sets the balance outright yet. To set it to a column, "
        f"take the balance off and add the column: .subtract({balance})"
        ".add(<the column>), which sets any finite balance to the column and "
        "books both movements. Any other step is "
        "the operation that says what it does -- add, subtract, charge, "
        "grow, grow_capped, deduct_nar, ratchet, floor or round -- and where "
        "it is arithmetic over columns rather than over the running balance, "
        "work it out as a column of the frame before the rollforward and add "
        "or subtract that column."
    )
    return NotImplementedError(msg)


class Pass(Protocol):
    def name(self) -> str: ...
    def apply(self, ir: IR) -> IR: ...


@dataclass(frozen=True)
class Validate:
    """Per-Op verify(), state/point consistency, the two label gates."""

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
            if isinstance(op, Apply):
                raise _apply_refusal(op)
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
        _verify_label_characters(ir)
        if ir.track_increments:
            _verify_unique_increment_labels(ir)
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


def _bare_column_name(expr: pl.Expr) -> str | None:
    """Return the one column ``expr`` is a bare reference to, or None.

    The compiler's own test for what an op's field may be, asked without
    the refusal: a bare ``pl.col(name)`` and nothing wrapped around it.
    ``_single_column_name`` is the raising caller and the artifact's
    increments summary is the reading one, and they share this function so
    that what the record says an increment reads is decided by the same
    test that decided whether the compilation could be built at all.
    """
    roots = expr.meta.root_names()
    if len(roots) != 1:
        return None
    name = roots[0]
    return name if str(expr) == f'col("{name}")' else None


# The column a refusal suggests a literal be put in, where the field's own name
# would make a poor one.
_LITERAL_COLUMN_NAMES = {"expr": "amount", "to": "level", "when": "fires"}


def _literal_refusal(expr: pl.Expr, op_name: str, field_name: str) -> str:
    """Return the refusal for a number written where an amount is read.

    The builder reads a number as the literal it is, since a number cannot
    be a column's name. The kernel fetches each amount from a column of the
    frame at the period it has reached, so a literal gives it nothing to
    fetch, and the move is to put the number in a column. A ratchet's
    ``when=`` is told, besides, that one which fires every period takes
    none.
    """
    try:
        shown = repr(pl.select(expr).item())
    except Exception:  # noqa: BLE001 -- the value is only for the message
        shown = str(expr)
    column = _LITERAL_COLUMN_NAMES.get(field_name, field_name)
    every_period = (
        " A ratchet that fires every period takes no when= at all."
        if (op_name, field_name) == ("Ratchet", "when")
        else ""
    )
    return (
        "A compiled rollforward reads each amount from a column of the frame, "
        f"one value per period, and {op_name}.{field_name} is the value "
        f"{shown}: the kernel has no column to fetch it from. Put it in a "
        f"column of the frame first -- af[{column!r}] = {shown} -- and give "
        f"{op_name}.{field_name} that column, af[{column!r}].{every_period}"
    )


def _single_column_name(expr: pl.Expr, op_name: str, field_name: str) -> str:
    """Return the single column name referenced by ``expr`` or raise.

    Op exprs (Add.expr, Subtract.expr, Charge.rate, Grow.rate, etc.)
    must be ``pl.col("name")`` — a bare column reference. Compound
    expressions like ``pl.col("a") + pl.col("b")`` raise
    ``NotImplementedError``: precompute them as input columns.

    Both refusals say the same three things a reader needs — what a
    compiled rollforward reads, why this expression cannot be one of
    those reads, and the move that fixes it — because the actuary meeting
    either of them is holding a charge rate or a boundary they wrote as
    arithmetic, and "must be a single-column ref" names none of that.
    They are worded for every caller of this function: an op's own field
    and the machine's contract boundary are both one named column read
    once per period.
    """
    name = _bare_column_name(expr)
    if name is not None:
        return name
    roots = expr.meta.root_names()
    # Through an alias too: pl.lit(5.0).alias("x") is still the value 5.0.
    if not roots and expr.meta.is_literal(allow_aliasing=True):
        raise NotImplementedError(_literal_refusal(expr, op_name, field_name))
    balances = [root for root in roots if RESERVED_LABEL_CHARACTER in root]
    if len(roots) != 1:
        move = (
            _running_balance_move(balances)
            if balances
            else (
                f"Work the expression out as a column of the frame before the "
                f"rollforward runs, and give {op_name}.{field_name} a bare "
                f"pl.col() reference to that column."
            )
        )
        msg = (
            f"A compiled rollforward reads one named column of the frame at "
            f"each period, and {op_name}.{field_name} is an expression over "
            f"{len(roots)} of them: {roots}. The kernel steps the machine "
            f"forward by fetching the column each part of it names at the "
            f"period it has reached, and evaluates no arithmetic of its own "
            f"inside the recursion, so an expression combining columns names "
            f"nothing for it to fetch. {move}"
        )
        raise NotImplementedError(msg)
    move = (
        _running_balance_move(balances)
        if balances
        else (
            f"Work the wrapping out as a column of the frame before the "
            f"rollforward runs, and give {op_name}.{field_name} a bare "
            f"pl.col() reference to that column."
        )
    )
    msg = (
        f"A compiled rollforward reads one named column of the frame at "
        f"each period, and {op_name}.{field_name} is {str(expr)!r} rather "
        f"than a bare reference to {roots[0]!r}. The kernel fetches the column "
        f"named and applies nothing further to it, so everything wrapped "
        f"around the reference would be dropped without a word and the "
        f"machine would run on a number the model never asked for. {move}"
    )
    raise NotImplementedError(msg)


def _running_balance_move(balances: list[str]) -> str:
    """Return the move for arithmetic over a balance the machine computes.

    A ``state@point`` read is a running balance: it has no column until the
    machine has run, so the move the other refusals name -- work the
    expression out as a column first -- cannot be made. Arithmetic that
    moves one balance by a share of another is most often probability
    moving between states, which is a set of per-state accumulations
    rather than a rollforward, so that is the route named.
    """
    named = ", ".join(repr(name) for name in balances)
    one = len(balances) == 1
    return (
        f"{named} {'is a running balance' if one else 'are running balances'} "
        f"the machine itself computes, which {'has' if one else 'have'} no "
        f"column until it has run, so the expression cannot be worked out "
        f"beforehand. If the states hold probabilities moving between them "
        f"-- multi-state occupancy, such as disability with recovery -- that "
        f"is not a rollforward: write one projection.accumulate() per state, "
        f"ordered so each state's inflow reads only states already computed "
        f"(on a fixed-step axis, af.projection.set(n_periods=..., "
        f"step_years=...), where the source has no calendar), and with "
        f"recovery repeat those calls in sweeps until a sweep changes "
        f"nothing. A balance read on its own -- a ratchet reading the fund "
        f"-- is a bare pl.col() of it."
    )


@dataclass(frozen=True)
class LowerToPolarsPlugin:
    """Lower an IR + slot table into the kernel's plugin_kwargs dict.

    The dict is consumed by the Rust kernel as the bridge between the
    compile-time IR and runtime execution. It crosses the plugin boundary
    as pickle (protocol 5): Polars pickles plugin kwargs and the kernel
    deserialises them via serde into ``RollforwardKwargs``
    (``core/src/polars_functions/rollforward.rs``), so every value here
    must be picklable and match that struct — JSON appears only in the
    fingerprint path, which hashes the IR's canonical form.

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

        # The kernel's period count. A per-policy grid states none (spec 11.1.37): the
        # kernel sizes each policy from the per-policy lengths threaded below,
        # and reads this only as a capacity hint, so it is nought there.
        is_jagged = getattr(ir.schedule, "_kind", None) == "per_policy_grid"
        n_periods = 0 if is_jagged else ir.schedule._shared_period_count()

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
            # Declared book shape: a calendar-grid / inception schedule means
            # every policy's inputs must span exactly n_periods (checked per
            # row in the kernel — never inferred from the batch, which would
            # make behaviour depend on streaming chunk boundaries). Jagged
            # horizons are declared via a per_policy_grid schedule instead.
            "require_uniform": not is_jagged,
        }
        # Append the registered input column expressions to args so the
        # kernel can locate them by index.
        args.extend(column_reference(name) for name in input_columns)

        # For jagged (per_policy_grid) schedules, thread the authoritative
        # per-policy period count as a trailing input so the kernel sizes each
        # policy's projection from its own horizon — independent of whichever
        # input list happens to be first, and correct even with no input lists.
        if is_jagged:
            kwargs["per_policy_lengths_arg"] = len(args)  # n_states + n_input_cols
            args.append(_per_policy_period_count(ir.schedule))

        return kwargs, args


def _resolve_op(  # noqa: PLR0911, C901 — one flat branch per Op type; both metrics scale with the IR's op count, and a dispatch table would hide which fields each Op lowers
    op: Op,
    *,
    target_state: int,
    target_point: int,
    classify: object,
) -> dict[str, object]:
    """Resolve a single Op into the kernel's tagged-dict shape.

    Every ``*_arg`` slot is a tagged dict —
    ``{"kind": "input", "idx": int}`` for precomputed list-column refs,
    ``{"kind": "state", "state": int, "point": int}`` for cross-state reads.
    """
    # ``classify`` is callable (expr, op_name, field_name) -> dict
    cls = classify

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
        base["round_charge"] = op.round_charge
        base["label"] = op.label
        return base
    if isinstance(op, Grow):
        base["rate_arg"] = cls(op.rate, op_name, "rate")  # type: ignore[operator]
        base["round_charge"] = op.round_charge
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
        base["nar_at_end_of_period"] = op.nar_timing == "end_of_period"
        base["coi_discount_rate_arg"] = (
            None
            if op.coi_discount_rate is None
            else cls(op.coi_discount_rate, op_name, "coi_discount_rate")  # type: ignore[operator]
        )
        base["credited_rate_arg"] = (
            None
            if op.credited_rate is None
            else cls(op.credited_rate, op_name, "credited_rate")  # type: ignore[operator]
        )
        base["corridor_factor_arg"] = (
            None
            if op.corridor_factor is None
            else cls(op.corridor_factor, op_name, "corridor_factor")  # type: ignore[operator]
        )
        base["round_charge"] = op.round_charge
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
    if isinstance(op, Round):
        base["decimals"] = int(op.decimals)
        return base
    if isinstance(op, Apply):
        raise _apply_refusal(op)
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


def _compile_ir[CompiledT: CompiledData](
    ir: IR, compiled_type: type[CompiledT]
) -> CompiledT:
    """Run the compiler passes and construct the requested data/authoring object."""
    ir = Validate().apply(ir)
    logger.trace(f"[validate]              ok — {len(ir.transitions)} transitions")

    ir = ResolveStateRefs().apply(ir)
    logger.trace("[resolve_state_refs]    ok")

    ir = FoldConstants().apply(ir)
    logger.trace("[fold_constants]        ok")

    slots_pass = AssignCaptureSlots()
    ir, slots = slots_pass.apply_with_slots(ir)
    logger.trace(f"[assign_capture_slots]  ok — {len(slots)} slots")

    lower = LowerToPolarsPlugin()
    plugin_kwargs, plugin_args = lower.lower(ir, slots)
    logger.trace(f"[lower_polars]          ok — {len(plugin_kwargs)} kwargs")

    return compiled_type(
        ir=ir,
        plugin_kwargs=plugin_kwargs,
        capture_slots=slots,
        plugin_args=tuple(plugin_args),
    )
