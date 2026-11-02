# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The compiled rollforward, as a node the op-tree can read.

The rollforward already had a graph. ``rollforward/_ops.py`` is a typed
Op vocabulary, ``_ir.py`` is a frozen IR, ``_passes.py`` runs
``Validate`` -> ``ResolveStateRefs`` -> ``FoldConstants`` ->
``AssignCaptureSlots`` -> ``LowerToPolarsPlugin``, and the Rust kernel is
the executor. Rewriting any of that would be replacing a working compiler
with a second one. The egress methods therefore emit a node in the
op-tree's own vocabulary, and the lowering executes the existing compiled
kernel recipe. Only the raw kernel-expression and hidden-field extraction
bodies move here; the compiler, per-instance expression cache and shared
hidden-column registry keep their existing ownership.

That makes the node a *semantic record* rather than a build recipe --
which is exactly what makes the rollforward legible to everything that
reads op-trees. A COI charge on the net amount at risk reads its own
running account value, and in the node that read is a ``State`` child,
not a string buried in a plugin keyword argument:

    Call("rollforward.state",
         args=(Col("av_pp_init"),           # the state's opening value
               Col("coi_rate"),             # a precomputed input column
               Col("death_benefit"),        # another
               State("account_value@eop"),  # <- the running-state read
               ...),
         attrs=(("fingerprint", "sha256:..."),  # the machine
                ("schedule", "sha256:..."),     # the schedule it runs on
                ("state", "account_value"), ("point", "eop"),
                ("shared", True)))

``col_refs`` therefore reports what a rollforward reads from the frame,
and ``walk`` finds the state dependency, without either of them knowing
anything about rollforwards.

**The args are a record, not an argument list.** The kernel's own argument
order (state initialisers, then unique input columns, with cross-state
reads resolved to integer indices in its keyword arguments) is the
compiler's business and stays there. The lowering does not reconstruct the
call from ``args``; it resolves the compiled artefact by its published
``fingerprint`` and its ``schedule`` (see ``frame/lowering/artefacts.py``)
and builds the same kernel call or shared-field read the compiled object
used to build.
The compiler's argument order and kernel keywords are unchanged. The
honest trade-off: a backend that did not have this
kernel could read the node's structure but could not execute it from the
node alone -- it would need the IR. That is the price of not rewriting a
working compiler, and it is the reason the fingerprint is on the node.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

import polars as pl

from gaspatchio._dtypes import integers_as_i64, wider_than_i64_at
from gaspatchio._semantic.ir import Col, State
from gaspatchio.frame.lowering._polars.plugins import rollforward_kernel
from gaspatchio.frame.lowering._polars.validation import (
    WIDE_ROLLFORWARD_RULE,
    read_as_i64_where_it_fits,
)
from gaspatchio.frame.lowering.artefacts import rollforward_for
from gaspatchio.frame.lowering.columns import column_reference
from gaspatchio.frame.lowering.polars import register_lowering
from gaspatchio.rollforward._data import _raw_plugin_expr

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio._semantic.ir import AttrValue, Call, OpNode
    from gaspatchio.frame.lowering.context import LoweringContext
    from gaspatchio.rollforward._data import CompiledData
    from gaspatchio.rollforward._ir import IR


def _attrs(node: Call) -> dict[str, AttrValue]:
    """Read a call's typed configuration back as a dict."""
    return dict(node.attrs)


def _compiled(node: Call) -> CompiledData:
    """Resolve the compiled rollforward this call was emitted against.

    By the pair the call carries -- the machine's ``fingerprint`` and the
    ``schedule`` it runs on -- because the fingerprint leaves the schedule
    out and one machine on two schedules is two kernel runs.
    """
    return rollforward_for(_text(node, "fingerprint"), _text(node, "schedule"))


def _text(node: Call, key: str) -> str:
    """Read a required string attribute off the call."""
    value = _attrs(node)[key]
    if not isinstance(value, str):  # pragma: no cover - emission validates
        msg = f"{node.name}: {key!r} must be a string, got {value!r}"
        raise TypeError(msg)
    return value


@register_lowering("rollforward.state")
def _lower_state(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Read one state's per-period values out of the compiled rollforward.

    Every extraction from one compiled rollforward shares a single kernel
    run when the shared form is used: they all reference one hidden struct
    column the frame materialises once. The self-contained form embeds its
    own kernel call, which is what a raw Polars frame needs; no published
    door asks for it.
    """
    compiled = _compiled(node)
    field = f"{_text(node, 'state')}@{_text(node, 'point')}"
    if _attrs(node).get("shared", True):
        return _shared_field(compiled, field)
    return _self_contained_field(compiled, field)


@register_lowering("rollforward.increment")
def _lower_increment(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Read one labelled operation's signed per-period delta.

    Signed, and it is the movement the operation made in its target --
    the value after it minus the value before, in binary64 (spec section
    16.2), not the operand it computed: negative for charges, positive for
    credits, zero after a stop or a lapse -- where a source spreadsheet may
    keep computing a notional charge against the full face amount.
    """
    compiled = _compiled(node)
    field = f"increment_{_text(node, 'label')}"
    if _attrs(node).get("shared", True):
        return _shared_field(compiled, field)
    return _self_contained_field(compiled, field)


@register_lowering("rollforward.struct")
def _lower_struct(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Run the whole kernel call as one self-contained struct expression.

    The escape hatch for a plain Polars frame, where there is no
    ``ActuarialFrame`` to materialise a shared hidden column.
    """
    return _raw_plugin_expr(_compiled(node))


def _shared_field(compiled: CompiledData, field: str) -> pl.Expr:
    """Read a field from the struct the frame materialises once.

    Register the cached kernel expression under its run-derived hidden
    name -- the machine's fingerprint and its schedule's -- before returning
    the extraction. This makes sharing
    structural, independent of the engine deduplicating plugin calls.
    """
    from gaspatchio.rollforward import _registry  # noqa: PLC0415

    hidden_column = compiled._hidden_column  # noqa: SLF001
    _registry.register(hidden_column, compiled._cached_plugin_expr)  # noqa: SLF001
    _COMPILED_BY_COLUMN.setdefault(hidden_column, compiled)
    # The public compiled object wraps this raw extraction for proxy interoperation.
    return column_reference(hidden_column).struct.field(field)


# The compilation behind each hidden struct column, by the column's name, kept
# where the column is first named so the frame that materialises it can build
# the same kernel call over inputs it reads differently. First writer wins, as
# in the registry, and for its reason: the name embeds the run.
_COMPILED_BY_COLUMN: dict[str, CompiledData] = {}


def run_reading_wide_inputs_as_i64(
    hidden_column: str, schema: Mapping[str, pl.DataType]
) -> pl.Expr | None:
    """Return the run behind ``hidden_column`` with its wide inputs read as ``Int64``.

    The kernel reads its opening balances and its step amounts as doubles,
    whatever they arrive as, so a ``UInt64`` input holding 2**64 - 1 entered
    the run as 1.8446744073709552e19 and every premium added after it was
    lost in the rounding; a ``UInt128`` one stopped the plan with a panic.
    Section 10 reads a column wider than ``i64`` as the ``Int64`` its values
    fit and refuses arithmetic on one where a value does not, and a
    rollforward step is that arithmetic: each such input is handed to the
    kernel read the way arithmetic reads it, refused by name when the run
    reaches a value that does not fit. ``None`` where no input is that wide,
    and the compiled call stands as it is.
    """
    compiled = _COMPILED_BY_COLUMN.get(hidden_column)
    if compiled is None:
        return None
    args = compiled.plugin_args
    read = [_an_input_read_as_i64(arg, schema) for arg in args]
    if all(new is old for new, old in zip(read, args, strict=True)):
        return None
    return rollforward_kernel(tuple(read), compiled.plugin_kwargs)


def _an_input_read_as_i64(arg: pl.Expr, schema: Mapping[str, pl.DataType]) -> pl.Expr:
    """Return one kernel operand read as ``Int64`` where it is a column wider than it.

    An operand that is not a column -- a number a state opens at, which the
    compiler hands over as it was written -- is the kernel's as it is.
    """
    if not isinstance(arg, pl.Expr) or not arg.meta.is_column():
        return arg
    (column,) = arg.meta.root_names()
    dtype = schema.get(column)
    depth = None if dtype is None else wider_than_i64_at(dtype)
    if dtype is None or depth is None:
        return arg
    return read_as_i64_where_it_fits(
        arg,
        integers_as_i64(dtype, wide=True),
        depth=depth,
        column=column,
        rule=WIDE_ROLLFORWARD_RULE,
    )


def _self_contained_field(compiled: CompiledData, field: str) -> pl.Expr:
    """Extract ``field`` from a kernel call embedded in the expression itself.

    One kernel run per extraction, and no dependence on a frame
    materialising a hidden column -- the only form that works on a raw
    Polars frame. ``expr_for`` and ``increment_for`` both ask for the
    shared form, so nothing the package publishes reaches this one; the
    kernel tests emit it through a helper of their own under ``tests/``.
    """
    return compiled._cached_plugin_expr.struct.field(field)  # noqa: SLF001


# --- the semantic record ------------------------------------------------------


# Operations whose shape implicitly consumes the running balance.
# This is the framework's own escalation criterion for reaching for a
# rollforward at all ("we reach for the state-machine rollforward only when
# within-period charges actually depend on the running balance -- COI on net
# amount at risk, IUL floor/cap, GMDB ratchet"), so it is exactly the set
# whose state read belongs in the record.
_IMPLICIT_RUNNING_BALANCE: frozenset[str] = frozenset(
    {"Charge", "Grow", "GrowCapped", "DeductNAR", "Ratchet", "Floor", "Round"}
)

# The other three operations take their amount directly from one expression.
# Whether that amount reads the target balance is therefore a property of the
# classified operand, not of the operation class.
_AMOUNT_FIELD: dict[str, str] = {
    "Add": "expr",
    "Subtract": "expr",
    "Apply": "body",
}


def operand_nodes(ir: IR) -> tuple[OpNode, ...]:
    """Describe what a compiled rollforward reads, in the op-tree's vocabulary.

    Each state's opening value first, then, per transition in declared
    order: every expression the operation takes, plus a ``State`` node for
    its target when the operation's shape implicitly consumes the running
    balance.

    That last part is what makes a COI on the net amount at risk legible.
    The charge is ``coi_rate * (death_benefit - account_value)``; the
    account-value term never appears as a Polars expression anywhere,
    because the kernel computes it from the balance it is carrying. Without
    the ``State`` node the record would say the charge reads a rate and a
    death benefit and nothing else -- true of the *arguments*, false of the
    *calculation*.

    A read of a different state at a point also becomes a ``State`` node:
    the kernel spells those ``pl.col("account_value@bop")`` internally,
    which is a column name by convention only and is not a column on the
    frame. Everything else is a precomputed input column, so it becomes
    ``Col``; anything that is not a single column reference (a state
    initialiser may be any expression) becomes ``EngineNative``, the honest
    answer for an expression the tree did not build.

    Duplicates are kept. Two operations charging the same rate column read
    it twice, and flattening that would misreport the structure.

    Every operation is read by :func:`increments_of`, so that the flat run
    this function hands the emission path and the per-operation record the
    artifact carries are one walk of the Op vocabulary rather than two. A
    second walk would be a second place the record can be wrong, and the
    two would disagree the first time an Op gained a field.
    """
    state_names = {state.name for state in ir.states}
    point_names = set(ir.points)
    nodes: list[OpNode] = [
        classify_operand_expression(state.init, state_names, point_names)
        for state in ir.states
    ]
    for increment in increments_of(ir):
        nodes.extend(increment.operands)
    return tuple(nodes)


@dataclass(frozen=True)
class Increment:
    """One operation of a compiled rollforward, read into the op-tree's terms.

    Named for what the kernel calls it: with ``track_increments`` on, a
    labelled operation's signed per-period delta comes back as
    ``increment_<label>``, and this is the record of what produced it.

    ``operands`` is every expression the operation carries, in the order
    its own fields declare them, followed by the running state it consults
    where it consults one. ``settings`` is the rest of the operation's
    configuration -- a rounding precision, a timing convention, a floor's
    value -- and an optional expression the operation was *not* given
    appears there as null rather than being left out. Two machines
    differing only in a rounding precision are two machines, and a record
    that carried only the expressions would project them identically.
    """

    label: str | None
    operation: str
    target: State
    reads_running_balance: bool | None
    operands: tuple[OpNode, ...]
    settings: tuple[tuple[str, AttrValue], ...]


def increments_of(ir: IR) -> tuple[Increment, ...]:
    """Return what a compiled rollforward applies, one entry per operation.

    In declared order, which is the order the kernel applies them in: a
    rollforward is a sequence, and reordering two charges on one balance is
    a different answer rather than a different spelling.
    """
    state_names = {state.name for state in ir.states}
    point_names = set(ir.points)
    return tuple(_increment(op, state_names, point_names) for op in ir.transitions)


def _increment(op: object, state_names: set[str], point_names: set[str]) -> Increment:
    """Read one operation: its target, its expressions, and the rest of it.

    One pass over the operation's own fields, sorting each into the place
    that describes it. ``target`` and ``label`` are named outright; an
    expression becomes an operand, classified exactly as the compiler
    classifies it; anything else is configuration.
    """
    import polars as pl  # noqa: PLC0415 - the op-tree carries no engine import

    operation = type(op).__name__
    # Asked first: an operation this record cannot classify is refused before
    # anything is read off it, so the message names the operation rather than
    # one of its fields.
    amount_field = _amount_field(operation)
    target = _target_state_node(op)
    operands: list[OpNode] = []
    settings: list[tuple[str, AttrValue]] = []
    amount: OpNode | None = None
    for field in fields(op):  # type: ignore[arg-type]
        if field.name in ("target", "label"):
            continue
        value = getattr(op, field.name)
        if isinstance(value, pl.Expr):
            operand = classify_operand_expression(value, state_names, point_names)
            operands.append(operand)
            if field.name == amount_field:
                amount = operand
        else:
            settings.append((field.name, _setting(op, field.name, value)))
    reads_balance = _reads_running_balance(operation, target, amount)
    if operation in _IMPLICIT_RUNNING_BALANCE:
        operands.append(target)
    return Increment(
        label=getattr(op, "label", None),
        operation=operation,
        target=target,
        reads_running_balance=reads_balance,
        operands=tuple(operands),
        settings=tuple(settings),
    )


def _setting(op: object, name: str, value: object) -> AttrValue:
    """Return one piece of an operation's configuration, refusing an odd one.

    The four types an operation tree can carry, or absent. A field of some
    other type would have to be stringified to travel, and a record that
    quietly stringified part of a state machine would be wrong in exactly
    the document that exists to be checked -- so it refuses, and names the
    field, the way an unclassified operation does.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    msg = (
        f"{type(op).__name__}.{name} carries {value!r}, which this record "
        "cannot describe: an operation's configuration is text, a whole "
        "number, a decimal, a true/false flag, or absent, and anything else "
        "is an expression the record reports as an operand. Decide which of "
        "the two the field is and give it that type."
    )
    raise NotImplementedError(msg)


def _amount_field(operation: str) -> str | None:
    """Return the field carrying an explicit amount, validating the Op name."""
    if operation in _IMPLICIT_RUNNING_BALANCE:
        return None
    if operation in _AMOUNT_FIELD:
        return _AMOUNT_FIELD[operation]
    msg = (
        f"{operation} is a rollforward operation this record does not know how "
        "to classify: it is in neither _IMPLICIT_RUNNING_BALANCE nor "
        "_AMOUNT_FIELD in frame/lowering/rules/rollforward.py. Decide how its "
        "within-period amount reads the running balance."
    )
    raise NotImplementedError(msg)


def _reads_running_balance(
    operation: str, target: State, amount: OpNode | None
) -> bool | None:
    """Whether one increment's amount depends on the balance it changes.

    Seven operations answer from their shape. Add, Subtract and Apply answer
    from the classified expression that supplies their amount: either point
    of the target state is a read of that balance, while an input or another
    state is not. An expression the portable tree cannot classify answers
    ``None`` rather than guessing.
    """
    if operation in _IMPLICIT_RUNNING_BALANCE:
        return True
    if isinstance(amount, Col):
        return False
    if isinstance(amount, State):
        amount_state, _, _ = amount.name.partition("@")
        target_state, _, _ = target.name.partition("@")
        return amount_state == target_state
    return None


def _target_state_node(op: object) -> State:
    """Return the op's target as a ``State`` node, in the published spelling."""
    target = op.target  # type: ignore[attr-defined]
    return State(target.canonical_name())


def classify_operand_expression(
    expr: pl.Expr, state_names: set[str], point_names: set[str]
) -> OpNode:
    """Classify one operand expression the same way the compiler does.

    Public because it is *the* classifier: the artifact's account of a
    compiled rollforward reads a state's opening value through this
    function and through no other, so a second one -- which is a second
    place the record can be wrong -- never gets written.
    """
    from gaspatchio.frame.lowering.ingress import native_node  # noqa: PLC0415

    try:
        roots = list(expr.meta.root_names())
    except Exception:  # noqa: BLE001 - meta inspection is best-effort
        return native_node(expr)
    if len(roots) != 1 or str(expr) != f'col("{roots[0]}")':
        return native_node(expr)
    name = roots[0]
    if "@" in name:
        # StateRef.canonical_name() is "<state>@<point>"; this is the parse
        # side of that same spelling, and the only place the framework has
        # to read it back out of a column name.
        state, _, point = name.partition("@")
        if state in state_names and point in point_names:
            return State(name)
    return Col(name)
