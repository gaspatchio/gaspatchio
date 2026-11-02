# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What a model says about a value that is not there.

Section 11.1.13 keeps a null and a NaN apart, and so does this engine -- but
for a reason worth stating plainly, because it decides what four of these
eight do here.

**Inside a run of this engine, no value is null.** A null-bearing input
column refuses at the door, with its row count, and a null a calculation would
have minted -- an integer division by zero -- refuses at completion rather
than becoming a value. So a run that has reached the trace has no nulls in
it, and ``is_null`` is false everywhere, ``is_not_null`` true everywhere, and
``fill_null`` fills nothing. That is not a shortcut: it is the same answer
Polars gives over the same book, reached because the book was refused if it
could have given another.

The three NaN and infinity tests are real tests, and over a whole-number
column they answer what the clause says they answer: false for a NaN, false
for an infinity, true for finite, because an integer holds none of those and
a producer that refused there would be refusing a line that is merely
trivially answered. ``fill_nan`` is the real fill of the two: it replaces a
NaN, which a run does hold, and over a whole-number column it replaces
nothing for the same reason the NaN test answers false there.

**A test a NaN left unknown, per period, is its NaN indicator** (11.1.26-27:
per period the unknown is a NaN, as ``NaN * 0.0`` is), and a NaN is not a
null (11.1.13): ``is_null`` over it is false in every period and
``fill_null`` keeps the NaN. Per policy the same unknown is stored as a null
(11.1.27) and what a null test reads inline there is not stated, so this
engine refuses those cells by name (``comparison.unknown``) rather than
pick one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax.numpy as jnp

from gaspatchio.engines.format import Col
from gaspatchio_jax.capability import ANY_CARRIER, NUMERIC, Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import aligned
from gaspatchio_jax.lowerings import register, stepwise
from gaspatchio_jax.typed import Carrier, Value, promote, require_carrier

if TYPE_CHECKING:
    from collections.abc import Generator

    from gaspatchio.engines.format import Call, OpNode
    from gaspatchio_jax.lowerings import Lowering
    from gaspatchio_jax.plan import LoweringContext

_ABSENCE: Final = "11.1.13"

# What a NaN can stand in: a number, and only a number. 11.1.13 states the
# fill over a decimal and a whole number and withholds it past them, and the
# reference producer refuses a Boolean, text or a date there.
_NUMBERS: Final[frozenset[Carrier]] = frozenset({"i64", "f64"})

# The condition an answer about nulls holds under here, published beside the
# status so a reader can see what it rests on rather than taking it on trust.
_NO_NULLS = (
    "no value in a run is null: a null-bearing input refuses at the door "
    "and a null an integer division would mint refuses at completion"
)


def _unknown_per_policy(value: Value) -> None:
    """Refuse the cells of a truth value that are a null this engine does not carry.

    Per period a comparison's unknown is the NaN indicator, which is no null;
    per policy it is stored as a null (11.1.27), and what a null test or a
    null fill reads inline there is not stated. A per-period flag a ``when``
    left null where its condition had no truth value (11.1.28) is a null
    element, which ``is_null`` would answer true at: refused by name, as every
    other reader of it is, rather than answered false.
    """
    if value.unknown is not None and (value.shape == "scalar" or value.unknown_is_null):
        flag("comparison.unknown", value.unknown)


def _constant(name: str, *, answer: bool) -> Lowering:
    """Return the lowering for a null test, which in this engine is a constant."""

    def steps(call: Call, _ctx: LoweringContext) -> Generator[OpNode, Value, Value]:
        operand = yield call.args[0]
        _unknown_per_policy(operand)
        return Value(
            jnp.full(operand.array.shape, answer, dtype=bool),
            "bool",
            operand.shape,
            "bool",
            operand.horizon,
        )

    steps.__name__ = name
    steps.__qualname__ = name
    return stepwise(steps)


for _name, _answer in (("is_null", False), ("is_not_null", True)):
    register(
        Capability(
            identifier=_name,
            arity=(1,),
            carriers=(ANY_CARRIER,),
            checks=("comparison.unknown",),
            clause=_ABSENCE,
            note=_NO_NULLS,
        )
    )(_constant(_name, answer=_answer))


def _float_test(name: str) -> Lowering:
    """Return the lowering for one of the four tests of a non-finite value."""
    tests = {
        "is_nan": jnp.isnan,
        "is_not_nan": lambda array: ~jnp.isnan(array),
        "is_finite": jnp.isfinite,
        "is_infinite": jnp.isinf,
    }
    whole_number = {
        "is_nan": False,
        "is_not_nan": True,
        "is_finite": True,
        "is_infinite": False,
    }

    def lowering(call: Call, ctx: LoweringContext) -> Value:
        operand = require_carrier(ctx.lower(call.args[0]), NUMERIC, name, _ABSENCE)
        if operand.carrier != "f64":
            answer = whole_number[name]
            return Value(
                jnp.full(operand.array.shape, answer, dtype=bool),
                "bool",
                operand.shape,
                "bool",
                operand.horizon,
            )
        return Value(
            tests[name](operand.array), "bool", operand.shape, "bool", operand.horizon
        )

    lowering.__name__ = name
    return lowering


for _name in ("is_nan", "is_not_nan", "is_finite", "is_infinite"):
    register(
        Capability(
            identifier=_name,
            arity=(1,),
            # 11.1.13 states the answer over a number and a whole number and
            # withholds it past them: a Boolean, a date and text cannot hold a
            # NaN, and a consumer must accept either an answer or a refusal
            # there. This engine refuses, so the domain says numbers.
            carriers=(NUMERIC,),
            clause=_ABSENCE,
        )
    )(_float_test(_name))


@register(
    Capability(
        identifier="fill_null",
        arity=(2,),
        carriers=(ANY_CARRIER, ANY_CARRIER),
        # The value and the fill are promoted against each other, so what
        # fills a gap has to be the same kind of thing as what is missing: a
        # date filled with a number is not a fill this vocabulary states.
        matched_carriers=True,
        checks=("comparison.unknown",),
        clause=_ABSENCE,
        note=_NO_NULLS,
    )
)
@stepwise
def _fill_null(call: Call, ctx: LoweringContext) -> Generator[OpNode, Value, Value]:
    """Return the value where it is present and the fill where it is missing.

    The fill is lowered rather than skipped: section 11.1.28's rule that a
    branch's own refusal is not suppressed applies here too, and a fill that
    would refuse must refuse whether or not a gap reaches it. A per-period
    test a NaN left unknown is filled as the NaN indicator it is: carried
    beside a number it is NaN there, and a NaN is not a gap.
    """
    operand = call.args[0]
    absent = None
    if isinstance(operand, Col):
        # The one read of a column that takes its absences as what they are:
        # a left join's policy with no row, kept as null (11.1.2), filled.
        value, absent = ctx.column_with_its_absences(operand.name)
    else:
        value = yield operand
        _unknown_per_policy(value)
    fill = yield call.args[1]
    if fill.unknown is not None:
        flag("comparison.unknown", fill.unknown)
    value, fill = promote(value, fill, clause=_ABSENCE)
    if absent is None:
        return value
    axis = aligned(value, fill)
    held, filler = axis.arrays
    gaps = absent if axis.shape == "scalar" else absent[:, None]
    return Value(
        jnp.where(gaps, filler, held),
        value.carrier,
        axis.shape,
        value.dtype,
        axis.horizon,
    )


@register(
    Capability(
        identifier="fill_nan",
        arity=(2,),
        # A NaN is a decimal's, so the value is a number, and so is what
        # stands in for one: a Boolean or text fill would be a conversion
        # nobody wrote, and 11.1.13 states the fill over numbers alone.
        carriers=(_NUMBERS, _NUMBERS),
        checks=("mixed.2p53",),
        clause=_ABSENCE,
    )
)
def _fill_nan(call: Call, ctx: LoweringContext) -> Value:
    """Return the value where it is not NaN and the fill where it is.

    Over a per-period value a per-policy fill reaches every NaN period of its
    policy and a per-period fill the same period, which is 11.1.18's
    alignment and nothing of this operation's own. A whole-number value holds
    no NaN, so it comes back as it stands, in the type it shares with the
    fill. A per-period fill for a per-policy value is outside 11.1.13; this
    engine aligns it as it aligns every other pair of operands, so the tree
    check and the run give one answer about it.
    """
    value = require_carrier(ctx.lower(call.args[0]), _NUMBERS, "fill_nan", _ABSENCE)
    fill = ctx.lower(call.args[1])
    value, fill = promote(value, fill, clause=_ABSENCE)
    axis = aligned(value, fill)
    held, filler = axis.arrays
    return Value(
        jnp.where(jnp.isnan(held), filler, held),
        value.carrier,
        axis.shape,
        value.dtype,
        axis.horizon,
    )
