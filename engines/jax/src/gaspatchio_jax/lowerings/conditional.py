# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``when_then``: the conditional, with both branches evaluated.

Section 11.1.28 licenses this outright -- "selection does not promise lazy
branch execution" -- and a traced engine could not avoid it anyway: a trace
is a graph, and both branches are in it before the condition has a value.
The consequence the clause draws is the one that matters to a model author:
a branch's own refusal is not suppressed by standing behind a false
condition, so a conditional is not an escape from a checked conversion.

**A stored floating-point condition is checked, not coerced.** A column of
ones and zeros used directly as the condition is section 11.1.18's checked
non-null finite 0/1 rule, and a value that is neither refuses by name. An
engine that read 0.5 as true would be inventing a truthiness this vocabulary
does not have.

**The branches are a matched pair of one type, and that is the clause's own
rule.** 11.1.28 states two ``i64``, two ``f64``, two ``bool``, two ``str`` or
two ``date`` branches, with ``i64`` and ``f64`` meeting inside the exact
integer range -- a mortality table identifier chosen by sex is text either way
and is an ordinary line of an ordinary model. A flag beside a whole number is
the pair's double, the flag its 0.0/1.0 indicator, as 11.1.25 reads a flag
beside a number in arithmetic. What the clause puts outside
itself, and this engine refuses, is a pair from two different families: a
branch of text opposite a branch of number is not one column with two possible
values, and the conversion that would make it one is a conversion nobody
wrote.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax.numpy as jnp

from gaspatchio_jax.capability import ANY_CARRIER, Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import aligned, unknown_on
from gaspatchio_jax.lowerings import register, stepwise
from gaspatchio_jax.typed import (
    DomainRefused,
    Value,
    a_flag_beside_a_whole_number,
    carried_to,
    outside_stored_predicate,
    promote,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    import jax

    from gaspatchio.engines.format import Call, OpNode
    from gaspatchio_jax.horizon import Aligned
    from gaspatchio_jax.plan import LoweringContext

_CONDITIONAL: Final = "11.1.28"


def _truth(condition: Value) -> Value:
    """Return the condition as a truth value, checking a stored indicator."""
    if condition.carrier == "bool":
        return condition
    if condition.carrier == "f64":
        flag(
            "predicate.stored_f64",
            outside_stored_predicate(condition.array),
        )
        return Value(
            condition.array != 0.0, "bool", condition.shape, "bool", condition.horizon
        )
    raise DomainRefused(
        what=(
            f"a {condition.carrier} value stood as a condition, and this "
            "clause takes a comparison or a stored 0/1 indicator"
        ),
        move="write the comparison the condition means",
        clause=_CONDITIONAL,
    )


@register(
    Capability(
        identifier="when_then",
        arity=(3,),
        # A comparison or a stored 0/1 indicator for the condition, and two
        # branches of one semantic family after it.
        carriers=(frozenset({"bool", "f64"}), ANY_CARRIER, ANY_CARRIER),
        matched_carriers=True,
        # The family rule is about the two *branches*. A condition is a truth
        # value and stands in no family with either of them, and a rule that
        # took it in refused a Boolean column beside two text branches for
        # "comparing a number and text" -- a sentence about an operation this
        # is not.
        matched_operands=(1, 2),
        matched_says="selects between",
        matched_because="states no common type for them",
        checks=("predicate.stored_f64", "mixed.2p53", "comparison.unknown"),
        clause=_CONDITIONAL,
    )
)
@stepwise
def _when_then(call: Call, _ctx: LoweringContext) -> Generator[OpNode, Value, Value]:
    """Return the then value where the condition holds and the otherwise where not.

    In steps, the condition, the then and the otherwise in that order, so a
    ``when`` nested a few hundred deep in its ``otherwise`` lowers from the
    plan's own stack (``gaspatchio_jax.lowerings``).
    """
    condition = _truth((yield call.args[0]))
    then = yield call.args[1]
    otherwise = yield call.args[2]
    if a_flag_beside_a_whole_number(then.carrier, otherwise.carrier):
        # A flag beside a whole number is the pair's double, the flag read as
        # its 0.0/1.0 indicator, as arithmetic reads one beside a number; the
        # whole number is carried with its +-2**53 check.
        then = carried_to(then, "f64", clause=_CONDITIONAL)
        otherwise = carried_to(otherwise, "f64", clause=_CONDITIONAL)
    then, otherwise = promote(then, otherwise, clause=_CONDITIONAL)
    axis = aligned(condition, then, otherwise)
    # Named rather than spread: with a spread of unknown length mypy may pick
    # jnp.where's one-argument overload (which returns a tuple) on some jax
    # stub versions, as the Linux lane's did.
    held, if_true, if_false = axis.arrays
    # A per-policy logical result is a Boolean, null where a side had no
    # truth value (11.1.27): a null condition selects the otherwise where the
    # whole conditional is per policy, and is a null element per period,
    # which this engine does not carry.
    nulls = unknown_on((condition,), axis, nulls=True)
    if nulls is not None and axis.shape == "scalar":
        held = held & ~nulls
    elif nulls is not None:
        flag("comparison.unknown", nulls)
    selected = jnp.where(held, if_true, if_false)
    # 11.1.28: where the condition has no truth value (a NaN reached its
    # comparison) the answer is NaN, or a null where it holds none -- which
    # this engine does not carry, so it refuses those cells by name. A branch
    # that is itself a test with no truth value keeps that where selected.
    unknown = unknown_on((condition,), axis, nulls=False)
    if unknown is not None and then.carrier == "f64":
        selected = jnp.where(unknown, jnp.nan, selected)
        unknown = None
    elif unknown is not None and then.carrier != "bool":
        flag("comparison.unknown", unknown)
        unknown = None
    unknown, is_null = _a_flag_s_unknown(unknown, held, (then, otherwise), axis)
    return Value(
        selected,
        then.carrier,
        axis.shape,
        then.dtype,
        axis.horizon,
        unknown,
        unknown_is_null=is_null,
    )


def _a_flag_s_unknown(
    unknown: jax.Array | None,
    held: jax.Array,
    branches: tuple[Value, Value],
    axis: Aligned,
) -> tuple[jax.Array | None, bool]:
    """Return the cells of a flag answer with no truth value, and whether they are null.

    ``unknown`` is where the condition had none, which leaves a flag answer
    null (11.1.28: a flag holds no NaN). Per policy that null is the
    per-policy Boolean 11.1.27 describes, and every reader already reads it
    so. **Per period it is a null element**, which this engine does not
    carry: it is marked a null, so that whatever reads it -- arithmetic,
    ``&``, ``~``, another ``when``'s condition, a null test -- refuses those
    cells by name, as storing it does, rather than reading them as a NaN
    indicator.

    A branch that is itself a test keeps what it had where it is selected:
    a NaN comparison's unknown, or a per-policy result's null. Per period the
    two cannot be carried as one, so where nulls and NaN unknowns meet in
    one answer the null cells are refused here, by name, and the NaN ones
    carried on.
    """
    nans, nulls = _selected_cells(held, branches, axis)
    if axis.shape == "scalar":
        # A per-policy flag with no truth value is a null flag (11.1.28).
        found = _joined(_joined(unknown, nans), nulls)
        return found, found is not None
    if unknown is not None and nans is not None:
        # Neither branch is selected where the condition has no truth value.
        nans = nans & ~unknown
    nulls = _joined(unknown, nulls)
    if nulls is not None and nans is not None:
        flag("comparison.unknown", nulls)
        return nans, False
    if nulls is not None:
        return nulls, True
    return nans, False


def _selected_cells(
    held: jax.Array, branches: tuple[Value, Value], axis: Aligned
) -> tuple[jax.Array | None, jax.Array | None]:
    """Return the selected branch's NaN unknowns and its nulls, each None if none."""
    found: list[jax.Array | None] = []
    for nulls in (False, True):
        cells = [unknown_on((branch,), axis, nulls=nulls) for branch in branches]
        if cells[0] is None and cells[1] is None:
            found.append(None)
            continue
        none = jnp.zeros((), dtype=bool)
        found.append(
            jnp.where(
                held,
                none if cells[0] is None else cells[0],
                none if cells[1] is None else cells[1],
            )
        )
    return found[0], found[1]


def _joined(one: jax.Array | None, other: jax.Array | None) -> jax.Array | None:
    """Return the union of two cell masks, None where both are."""
    if one is None:
        return other
    if other is None:
        return one
    return one | other
