# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Bounds and bands: ``clip``, ``cut``, ``is_in`` and ``replace``.

Four ways of saying which group a value belongs to -- held between a floor
and a cap, placed in one of a band's intervals, a member of a set, or swapped
one for one. What identifies each of the last three is the values written
into it, which the tree carries as sequence literals rather than handing to
an engine to keep; that is why the members are read off the node here and
never lowered as a column.

**A crossed pair of bounds is answered by testing the lower first.** Section
11.1.3 states the order outright, and it is the whole of the answer: bounds
of 8 and 2 over 1, 5, 10 give 8, 8, 2 and not 2, 2, 2. Stating it does not
make crossed bounds sound, and the clause says that too.

**A ``cut`` with no labels is refused rather than named.** Where the formula
wrote no labels, each interval names itself after its own bounds and the
naming is the producing engine's -- two implementations may spell it
differently, so this engine has no reproducible answer and says so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax
import jax.numpy as jnp
import numpy as np

from gaspatchio_jax.capability import ANY_CARRIER, DATE, NUMERIC, Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import aligned
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.typed import (
    EXACT_IN_DOUBLE,
    INT64_MAX,
    INT64_MIN,
    JNP_OF,
    PAST_I64_LITERAL_MOVE,
    DomainRefused,
    Value,
    carried_to,
    promote,
    require_carrier,
)

if TYPE_CHECKING:
    from gaspatchio.engines.format import Call, OpNode
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Carrier

_CLIP: Final = "11.1.3"
_CUT: Final = "11.1.4"
_IS_IN: Final = "11.1.5"
_REPLACE: Final = "11.1.6"

# Where a literal member's range is stated, since the operations' own clauses
# state none: section 10 carries a whole number as a signed 64-bit integer, and
# 11.1.26 states a comparison between a whole number and a double -- which is
# what matching a value among members is -- only within 2^53 of zero.
_WIDTHS: Final = "10"
_MIXED_COMPARISON: Final = "11.1.26"

# How many operands a clip carries beside the value, per `bounds` setting.
_BOTH: Final = "both"
_LOWER: Final = "lower"
_UPPER: Final = "upper"

# What a cut's third operand is, where it has one.
_LABELS_OPERAND: Final = 2


def _members(
    ctx: LoweringContext, node: OpNode, carrier: Carrier, clause: str
) -> Value:
    """Keep a literal's own family and exact numbers before any promotion."""
    written = ctx.sequence(node)
    if not written:
        return Value(jnp.asarray([], dtype=JNP_OF[carrier]), carrier, "scalar", carrier)
    numeric = all(isinstance(member, (int, float)) for member in written)
    text = all(isinstance(member, str) for member in written)
    if (carrier == "code" and not text) or (carrier != "code" and not numeric):
        raise DomainRefused(
            what=(
                "the literal members and receiver belong to different semantic families"
            ),
            move="write an explicit conversion before matching or replacing values",
            clause=clause,
        )
    if text:
        return Value(
            jnp.asarray(
                [ctx.literal_code(str(member)) for member in written],
                dtype=JNP_OF["code"],
            ),
            "code",
            "scalar",
            "str",
        )
    chosen: Carrier = (
        "f64"
        if any(isinstance(member, float) for member in written)
        else "i64"
        if any(type(member) is int for member in written)
        else "bool"
    )
    for member in written:
        if not isinstance(member, int):
            continue
        if member < INT64_MIN or member > INT64_MAX:
            raise DomainRefused(
                what=(
                    f"the integer literal {member} is outside the signed 64-bit "
                    "range a whole number is carried in"
                ),
                move=PAST_I64_LITERAL_MOVE,
                clause=_WIDTHS,
            )
        if chosen == "f64" and (member < -EXACT_IN_DOUBLE or member > EXACT_IN_DOUBLE):
            raise DomainRefused(
                what=(
                    "an integer literal past 2^53 is matched among "
                    "floating-point members, where two whole numbers would "
                    "share one double"
                ),
                move="keep the literal integral or rescale the mixed numeric values",
                clause=_MIXED_COMPARISON,
            )
    return Value(jnp.asarray(written, dtype=JNP_OF[chosen]), chosen, "scalar", chosen)


@register(
    Capability(
        identifier="clip",
        # The value and one or two bounds; 11.1.3 says a clip with no bound at
        # all is not this operation and is never written.
        arity=(2, 3),
        # A bound answers "how large may this be", which a truth value does
        # not; the producer refuses a Boolean here as well. A whole number
        # held between decimal bounds has two answers -- the bound, and the
        # bound cast into the value's type, which is what the producer gives
        # -- and 11.1.3 states neither of them. A decimal held between whole
        # numbers has one: "a decimal value answers decimals", the bound read
        # as its double, exactly within 2^53.
        carriers=(frozenset({"i64", "f64"}),),
        matched_exactly=True,
        checks=("mixed.2p53",),
        attrs={"bounds": (_BOTH, _LOWER, _UPPER)},
        clause=_CLIP,
    )
)
def _clip(call: Call, ctx: LoweringContext) -> Value:
    """Return the value held between the bounds the node names."""
    value = require_carrier(ctx.lower(call.args[0]), NUMERIC, "clip", _CLIP)
    bounds = str(dict(call.attrs).get("bounds", _BOTH))
    lowered = [ctx.lower(argument) for argument in call.args[1:]]
    if not lowered:
        raise DomainRefused(
            what="a clip with no bound at all is not this operation",
            move="name the bound the model means, as an operand",
            clause=_CLIP,
        )
    if value.carrier == "i64" and any(bound.carrier == "f64" for bound in lowered):
        raise DomainRefused(
            what=(
                "clip holds a whole number between decimal bounds, and the "
                "answer's own type would not be on the record"
            ),
            move=(
                "convert the value to a decimal first, or write the bound as "
                "the whole number it stands for"
            ),
            clause=_CLIP,
        )
    held = value
    # A whole-number bound beside a decimal value is read as its double; the
    # value keeps its own type, as 11.1.3 states.
    lowered = [promote(held, bound, clause=_CLIP)[1] for bound in lowered]
    axis = aligned(held, *lowered)
    original = axis.arrays[0]
    capped = original
    if bounds in (_BOTH, _UPPER):
        capped = jnp.minimum(capped, axis.arrays[-1])
    if bounds in (_BOTH, _LOWER):
        # 11.1.3: the lower bound is tested first, and against the **original**
        # value rather than the capped one. Crossed bounds of 8 and 2 over
        # 1, 5, 10 are then 8, 8, 2 -- a step at the lower bound rather than a
        # constant, which is the answer the clause states and the one a
        # per-policy and a per-period value have to agree on.
        capped = jnp.where(original < axis.arrays[1], axis.arrays[1], capped)
    return Value(capped, held.carrier, axis.shape, held.dtype, axis.horizon)


@register(
    Capability(
        identifier="cut",
        # The value, the breakpoints and the labels. Without the labels each
        # interval names itself after its own bounds and the naming is the
        # producing engine's, which is not an answer this engine can give.
        arity=(3,),
        carriers=(NUMERIC,),
        literal_operands=(1, 2),
        attrs={"include_breaks": ("False",)},
        checks=("mixed.2p53", "cut.nan"),
        clause=_CUT,
    )
)
def _cut(call: Call, ctx: LoweringContext) -> Value:
    """Return the label of the interval the breakpoints place each value in."""
    value = require_carrier(ctx.lower(call.args[0]), NUMERIC, "cut", _CUT)
    if len(call.args) <= _LABELS_OPERAND:
        raise DomainRefused(
            what=(
                "this cut names no labels, so each interval is named by the "
                "producing engine and two implementations may spell it "
                "differently"
            ),
            move="write the labels out, one per interval",
            clause=_CUT,
        )
    breaks = _members(ctx, call.args[1], value.carrier, _CUT)
    value, breaks = promote(value, breaks, clause=_CUT)
    labels = _members(ctx, call.args[2], "code", _CUT)
    left_closed = bool(dict(call.attrs).get("left_closed", False))
    numbers = value.array
    # 11.1.4: a NaN lies in no interval -- it is neither above a breakpoint
    # nor below it -- so its band is a null, which this engine does not carry.
    if value.carrier == "f64":
        flag("cut.nan", jnp.isnan(numbers))
    above = (
        numbers[..., None] >= breaks.array
        if left_closed
        else numbers[..., None] > breaks.array
    )
    index = jnp.sum(above.astype(JNP_OF["i64"]), axis=-1)
    return Value(labels.array[index], "code", value.shape, "str", value.horizon)


@register(
    Capability(
        identifier="is_in",
        arity=(2,),
        # Every carrier but a date. A band of dates is a set literal this
        # grammar cannot spell -- 12.1 admits a date as a literal's whole
        # payload and never as a member of a sequence -- so the members would
        # have to arrive some other way, which 11.1.5 says is a different
        # line. Lowering one is left for later, and until then the
        # declaration says what this lowering does.
        carriers=(ANY_CARRIER - DATE,),
        literal_operands=(1,),
        checks=("mixed.2p53",),
        clause=_IS_IN,
    )
)
def _is_in(call: Call, ctx: LoweringContext) -> Value:
    """Return whether each value is one of the members the formula names."""
    value = ctx.lower(call.args[0])
    members = _members(ctx, call.args[1], value.carrier, _IS_IN)
    held, members = promote(value, members, clause=_IS_IN)
    return Value(
        jnp.isin(held.array, members.array), "bool", value.shape, "bool", value.horizon
    )


@register(
    Capability(
        identifier="replace",
        arity=(3,),
        # As ``is_in`` above: the values replaced are a sequence literal, and
        # a date is not a member of one (12.1).
        carriers=(ANY_CARRIER - DATE,),
        literal_operands=(1,),
        checks=("mixed.2p53",),
        clause=_REPLACE,
    )
)
def _replace(call: Call, ctx: LoweringContext) -> Value:
    """Return each named value swapped for the one opposite it, the rest kept."""
    value = ctx.lower(call.args[0])
    old = _members(ctx, call.args[1], value.carrier, _REPLACE)
    new = _replacements(call, ctx, value, len(old.array))
    held, old = promote(value, old, clause=_REPLACE)
    result = value.array
    for position in range(len(old.array)):
        result = jnp.where(held.array == old.array[position], new[position], result)
    return Value(result, value.carrier, value.shape, value.dtype, value.horizon)


def _replacements(
    call: Call, ctx: LoweringContext, value: Value, count: int
) -> jnp.ndarray:
    """Read literal replacements on the host, including their exact conversion."""
    with jax.ensure_compile_time_eval():
        return _literal_replacements(call, ctx, value, count)


def _literal_replacements(
    call: Call, ctx: LoweringContext, value: Value, count: int
) -> jnp.ndarray:
    """Return the replacements, whether written one each or one for all."""
    written = call.args[2]
    from gaspatchio.engines.format import Lit  # noqa: PLC0415 -- one node test

    scalar = isinstance(written, Lit) and not isinstance(written.value, tuple)
    if isinstance(written, Lit) and isinstance(written.value, (float, int, bool, str)):
        # Use the same literal-family checks for one replacement and a sequence.
        written = Lit((written.value,))
    members = _members(ctx, written, value.carrier, _REPLACE)
    if len(members.array) != (1 if scalar else count):
        raise DomainRefused(
            what="the old and replacement sequences have different lengths",
            move=(
                "write one replacement per key, or one scalar replacement for all keys"
            ),
            clause=_REPLACE,
        )
    if members.carrier != value.carrier:
        if value.carrier in ("i64", "bool") and members.carrier in (
            "f64",
            "i64",
            "bool",
        ):
            numbers = np.asarray(members.array)
            valid = (
                np.isin(numbers, [0, 1])
                if value.carrier == "bool"
                else (
                    np.isfinite(numbers)
                    & (numbers == np.floor(numbers))
                    & (numbers >= INT64_MIN)
                    & (numbers < -float(INT64_MIN))
                )
            )
            if not np.all(valid):
                raise DomainRefused(
                    what=(
                        "a replacement cannot be represented exactly in the "
                        "receiver's logical dtype"
                    ),
                    move="convert the receiver explicitly before replacing its values",
                    clause=_REPLACE,
                )
            members = Value(
                members.array.astype(JNP_OF[value.carrier]),
                value.carrier,
                "scalar",
                value.dtype,
            )
        else:
            members = carried_to(members, value.carrier, clause=_REPLACE)
    return jnp.broadcast_to(members.array, (count,))
