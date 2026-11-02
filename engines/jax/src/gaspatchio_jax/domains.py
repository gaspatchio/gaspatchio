# SPDX-FileCopyrightText: 2026 Opio Inc.
# SPDX-License-Identifier: Apache-2.0

"""Input-known predicates, without evaluating the calculation graph.

Only direct input and literal operands are read here. A computed sibling is
used for its declared type, never its value. Predicates are the same functions
the numerical lowerings use; result-dependent checks remain in the trace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jax.numpy as jnp

from gaspatchio.engines.format import BinOp, Call, Col, Lit, WhenThen
from gaspatchio_jax.checks import CHECKS, flag
from gaspatchio_jax.horizon import aligned, periods_of, resolve_position
from gaspatchio_jax.lowerings import LOWERINGS
from gaspatchio_jax.typed import (
    EXACT_IN_DOUBLE,
    Value,
    a_flag_beside_a_whole_number,
    arithmetic_carrier,
    cell_of,
    outside_double_exact,
    outside_integer_conversion,
    outside_prospective_rate,
    outside_stored_predicate,
    written_exponent,
)

if TYPE_CHECKING:
    import jax

    from gaspatchio.engines.format import OpNode
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Carrier


def _known(node: OpNode, ctx: LoweringContext) -> Value | None:
    """Read a leaf only when the node's version says it arrived with the book."""
    # A calculation operand is bound by this record's versioned reads. The
    # attribute-named fallback in resolves_to_an_input does not own these
    # operands.
    if isinstance(node, Col) and ctx.node.read_kinds.get(node.name) == "input":
        return ctx.lower(node)
    if isinstance(node, Lit) and not isinstance(node.value, tuple):
        return ctx.lower(node)
    return None


def _carrier(node: OpNode, ctx: LoweringContext) -> Carrier | None:
    """Read declared types even where the corresponding value is computed."""
    if isinstance(node, Col):
        return cell_of(ctx.node.read_dtypes.get(node.name, "unknown"))
    if isinstance(node, Lit):
        values = node.value if isinstance(node.value, tuple) else (node.value,)
        types = {type(value) for value in values}
        return (
            "f64"
            if float in types
            else "i64"
            if int in types
            else "bool"
            if bool in types
            else "code"
            if types == {str}
            else None
        )
    if isinstance(node, BinOp):
        node = Call(node.op, (node.left, node.right))
    if isinstance(node, WhenThen):
        node = Call("when_then", (node.cond, node.then, node.otherwise))
    if isinstance(node, Call):
        return _computed_carrier(node, ctx)
    return None


def _computed_carrier(node: Call, ctx: LoweringContext) -> Carrier | None:
    """Infer only numeric types; no operation is executed for this question."""
    arguments = node.args[1:] if node.name == "when_then" else node.args
    carriers: tuple[Carrier | None, ...] = tuple(
        _carrier(argument, ctx) for argument in arguments
    )
    if node.name == "to_float":
        # An explicit conversion fixes its result even for a computed operand.
        return "f64"
    if node.name in _ARITHMETIC:
        return arithmetic_carrier(
            node.name,
            carriers,
            per_period=_shape(node, ctx) == "list",
            exponent=written_exponent(node.name, node.args),
        )
    if node.name == "when_then" and all(
        carrier in {"i64", "f64", "bool"} for carrier in carriers
    ):
        if "f64" in carriers or a_flag_beside_a_whole_number(*carriers):
            return "f64"
        return "i64" if "i64" in carriers else "bool"
    registered = LOWERINGS.get(node.name)
    answer = registered[1].answers_carrier if registered else None
    return cell_of(answer) if answer is not None else None


def _held(name: str, mask: jax.Array, value: Value) -> None:
    """Record only actual input cells, never the bucket's padding."""
    if value.horizon is not None:
        mask = mask & value.horizon.active
    flag(name, mask)


# Each single-operand entry names the same predicate the lowering calls.
_SINGLE = {
    "to_integer.integral": (0, "f64", outside_integer_conversion),
    "to_float.exact": (0, "i64", outside_double_exact),
    "predicate.stored_f64": (0, "f64", outside_stored_predicate),
    "prospective_value.rate": (1, None, outside_prospective_rate),
}
_ARITHMETIC = frozenset({"add", "sub", "mul", "div", "pow", "floordiv", "mod"})
_PREPARATION = _SINGLE.keys() | {
    "mixed.2p53",
    "list_get.bounds",
}


def _shape(node: OpNode, ctx: LoweringContext) -> str | None:
    """Infer only axis metadata, including a computed comparison's sibling."""
    if isinstance(node, Col):
        dtype = ctx.node.read_dtypes.get(node.name)
        return (
            None if dtype is None else "list" if dtype.startswith("list[") else "scalar"
        )
    if isinstance(node, Lit):
        return "scalar" if not isinstance(node.value, tuple) else None
    if isinstance(node, BinOp):
        node = Call(node.op, (node.left, node.right))
    if isinstance(node, WhenThen):
        node = Call("when_then", (node.cond, node.then, node.otherwise))
    if isinstance(node, Call):
        registration = LOWERINGS.get(node.name)
        if registration is not None and registration[1].answers is not None:
            return registration[1].answers
        shapes = tuple(_shape(argument, ctx) for argument in node.args)
        return (
            "list"
            if "list" in shapes
            else "scalar"
            if all(shape == "scalar" for shape in shapes)
            else None
        )
    return None


def _mixed(call: Call, ctx: LoweringContext, known: tuple[Value | None, ...]) -> None:
    """Check known integers even when their floating sibling is computed."""
    carriers: tuple[Carrier | None, ...] = tuple(
        _carrier(argument, ctx) for argument in call.args
    )
    positions = (1, 2) if call.name == "when_then" else tuple(range(len(known)))
    if call.name in {"cut", "replace"}:
        positions = (0, 1)
    mixed = any(carriers[index] == "f64" for index in positions)
    if call.name == "when_then":
        # A flag beside a whole number carries the whole number to a double.
        mixed = mixed or a_flag_beside_a_whole_number(carriers[1], carriers[2])
    if call.name in _ARITHMETIC:
        mixed = (
            arithmetic_carrier(
                call.name,
                carriers,
                per_period=_shape(call, ctx) == "list",
                exponent=written_exponent(call.name, call.args),
            )
            == "f64"
        )
    _mixed_positions(call, known, positions, mixed=mixed)
    if call.name == "replace" and carriers[0] == "f64":
        # Replacement values convert to the receiver's carrier independently of
        # key matching. A decimal new value does not widen an integer receiver.
        _mixed_positions(call, known, (2,), mixed=True)


def _mixed_positions(
    call: Call,
    known: tuple[Value | None, ...],
    positions: tuple[int, ...],
    *,
    mixed: bool,
) -> None:
    """Check the operands participating in one actual numeric conversion."""
    for index in positions:
        value = known[index]
        if value is not None and mixed and value.carrier == "i64":
            _held("mixed.2p53", outside_double_exact(value.array), value)
        argument = call.args[index]
        if mixed and isinstance(argument, Lit) and isinstance(argument.value, tuple):
            flag(
                "mixed.2p53",
                jnp.asarray(
                    [
                        isinstance(member, int)
                        and not -EXACT_IN_DOUBLE <= member <= EXACT_IN_DOUBLE
                        for member in argument.value
                    ],
                    dtype=bool,
                ),
            )


def _bounds(known: tuple[Value | None, ...]) -> None:
    """Check a position against the actual arriving list lengths."""
    value, position = known
    if value is not None and position is not None:
        _, inside = resolve_position(periods_of(value), position.array)
        flag("list_get.bounds", ~inside)


def _single(name: str, known: tuple[Value | None, ...]) -> None:
    """Apply one shared predicate at the stage its own operand permits."""
    index, carrier, predicate = _SINGLE[name]
    value = known[index]
    stage = CHECKS[name].stage_for(operand_is_computed=value is None)
    if stage == "inputs" and value is not None and carrier in (None, value.carrier):
        _held(name, predicate(value.array), value)


def check_inputs(call: Call, ctx: LoweringContext) -> None:
    """Answer the operation inventory's direct-operand checks before compilation."""
    registration = LOWERINGS.get(call.name)
    checks = (
        ()
        if registration is None
        else tuple(name for name in registration[1].checks if name in _PREPARATION)
    )
    if not checks:
        # Result-only checks belong to their numerical owner. In particular a
        # state extraction carries the machine's operands, not its own bindings.
        return
    known = tuple(_known(argument, ctx) for argument in call.args)
    for name in checks:
        if name == "mixed.2p53":
            _mixed(call, ctx, known)
        elif name == "list_get.bounds":
            _bounds(known)
        elif name in _SINGLE:
            _single(name, known)
    if call.name == "projection.prospective_value" and all(
        value is not None for value in known
    ):
        aligned(*(value for value in known if value is not None))
