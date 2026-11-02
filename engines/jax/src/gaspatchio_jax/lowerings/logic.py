# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Conjunction, disjunction and negation -- never bit operations.

Section 11.1.27 is short and its narrowness is the point. These three take
Boolean values, comparisons used as predicates, and **stored indicators**: a
direct reference to a column declared ``f64`` or ``list[f64]``, read under
section 11.1.18's checked rule exactly as a ``when_then`` condition reads it.
Every value of such a column is 0.0 or 1.0 or the run refuses by name; a
negative zero is zero. A number that is not a column reference -- a literal,
an arithmetic result -- is still a number until a comparison makes it a truth
value, and an engine that treated it as one anyway would be answering a
question the model did not write.

Every answer here is a truth value. Where the record declares the per-period
form ``list[f64]``, the node's declared type carries it back to 1.0 and 0.0
(11.1.26's stored indicator), so the two representations meet at the record.

**A per-policy result is a Boolean wherever it is read** (11.1.27): where a
side had no truth value -- a NaN reached its comparison -- the result is a
null, carried as ``Value.unknown`` with ``unknown_is_null`` set. An enclosing
``&`` or ``|`` reads that null under three-valued logic (false AND null is
false), a ``when`` reads it as a null condition (the otherwise), and anything
that would carry it on refuses, this engine carrying no null. A per-period
result stays its NaN indicator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax.numpy as jnp

from gaspatchio.engines.format import Col
from gaspatchio_jax.capability import Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import aligned, unknown_on
from gaspatchio_jax.lowerings import register, stepwise
from gaspatchio_jax.typed import DomainRefused, Value, outside_stored_predicate

if TYPE_CHECKING:
    from collections.abc import Generator

    import jax

    from gaspatchio.engines.format import Call, OpNode
    from gaspatchio_jax.horizon import Aligned
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Carrier

_LOGICAL: Final = "11.1.27"

# A truth value, or a stored indicator standing for one. The capability can
# only see an operand's declared carrier; whether an f64 operand is a column
# reference rather than a literal is the lowering's question, asked below.
_TRUTH: Final[frozenset[Carrier]] = frozenset({"bool", "f64"})
# What the manifest says beside the carriers, so the row does not claim a
# floating-point literal or arithmetic result the lowering refuses.
_STORED: Final = (
    "a floating-point operand is a direct reference to a stored 0/1 indicator "
    "column, checked under 11.1.18"
)


def _predicate(tree: OpNode, value: Value, name: str) -> Value:
    """Return one operand as a truth value, or say why it is not one.

    ``tree`` is the operand as the formula writes it: an ``f64`` operand is a
    stored indicator only where it is a direct column reference, and is then
    checked under 11.1.18 and read as the truth value it states.
    """
    if value.carrier == "bool":
        return value
    if value.carrier == "f64" and isinstance(tree, Col):
        flag("predicate.stored_f64", outside_stored_predicate(value.array))
        return Value(value.array != 0.0, "bool", value.shape, "bool", value.horizon)
    raise DomainRefused(
        what=(
            f"{name} met a {value.carrier} operand, and this clause takes "
            "Boolean values, comparisons used as predicates, and stored 0/1 "
            "indicator columns"
        ),
        move=(
            "write the comparison in the operand, so the truth value is a "
            "predicate rather than a number standing for one"
        ),
        clause=_LOGICAL,
    )


def _combined(
    name: str, left: Value, right: Value, axis: Aligned
) -> tuple[jax.Array | None, bool]:
    """Return the cells of ``left <name> right`` with no Boolean answer, and their kind.

    Per period a side with no truth value makes the indicator NaN, and the
    cells are that unknown. Per policy the result is a Boolean, null there; a
    side that is itself a per-policy result's null is read under
    three-valued logic -- false AND null is false, true OR null is true.
    A null in a per-period combination is a null element, which this engine
    does not carry, so it refuses those cells by name.
    """
    unknown = unknown_on((left, right), axis, nulls=False)
    nulls = unknown_on((left, right), axis, nulls=True)
    if axis.shape != "scalar":
        if nulls is not None:
            flag("comparison.unknown", nulls)
        return unknown, False
    if nulls is None:
        return unknown, unknown is not None
    sides = []
    for side, array in zip((left, right), axis.arrays, strict=True):
        cells = unknown_on((side,), axis)
        missing = jnp.zeros((), dtype=bool) if cells is None else cells
        # The side's answer where it has one: settles the result alone when it
        # is false under AND or true under OR.
        settles = ~missing & (~array if name == "and" else array)
        sides.append(settles)
    held = nulls & ~sides[0] & ~sides[1]
    return (held if unknown is None else held | unknown), True


@register(
    Capability(
        identifier="and",
        arity=(2,),
        carriers=(_TRUTH, _TRUTH),
        checks=("predicate.stored_f64", "comparison.unknown"),
        note=_STORED,
        clause=_LOGICAL,
    )
)
@stepwise
def _and(call: Call, _ctx: LoweringContext) -> Generator[OpNode, Value, Value]:
    """Return the conjunction of two truth values, in steps."""
    left = _predicate(call.args[0], (yield call.args[0]), "and")
    right = _predicate(call.args[1], (yield call.args[1]), "and")
    axis = aligned(left, right)
    unknown, is_null = _combined("and", left, right, axis)
    return Value(
        jnp.logical_and(*axis.arrays),
        "bool",
        axis.shape,
        "bool",
        axis.horizon,
        unknown,
        unknown_is_null=is_null,
    )


@register(
    Capability(
        identifier="or",
        arity=(2,),
        carriers=(_TRUTH, _TRUTH),
        checks=("predicate.stored_f64", "comparison.unknown"),
        note=_STORED,
        clause=_LOGICAL,
    )
)
@stepwise
def _or(call: Call, _ctx: LoweringContext) -> Generator[OpNode, Value, Value]:
    """Return the disjunction of two truth values, in steps."""
    left = _predicate(call.args[0], (yield call.args[0]), "or")
    right = _predicate(call.args[1], (yield call.args[1]), "or")
    axis = aligned(left, right)
    unknown, is_null = _combined("or", left, right, axis)
    return Value(
        jnp.logical_or(*axis.arrays),
        "bool",
        axis.shape,
        "bool",
        axis.horizon,
        unknown,
        unknown_is_null=is_null,
    )


@register(
    Capability(
        identifier="not_",
        arity=(1,),
        carriers=(_TRUTH,),
        checks=("predicate.stored_f64",),
        note=_STORED,
        clause=_LOGICAL,
    )
)
@stepwise
def _not(call: Call, _ctx: LoweringContext) -> Generator[OpNode, Value, Value]:
    """Return the negation of one truth value, in steps."""
    operand = _predicate(call.args[0], (yield call.args[0]), "not_")
    return Value(
        jnp.logical_not(operand.array),
        "bool",
        operand.shape,
        "bool",
        operand.horizon,
        operand.unknown,
        # Per policy the negation is a Boolean too: a null where its operand
        # had no truth value (11.1.27). A null is a null on either shape: a
        # per-period flag a `when` left null (11.1.28) negates to a null.
        unknown_is_null=operand.unknown is not None
        and (operand.shape == "scalar" or operand.unknown_is_null),
    )
