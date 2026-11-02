# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``list.get`` and ``list.reverse``: positions within each policy's own list.

``list.get`` takes one stored position out of the list.

Positional selection, and 11.1.22 is at pains to say what it is not: not a
projection-period label, not a calendar date, not a relative shift. The shift
is ``projection.at_period``, which moves a whole timeline and fills what it
exposes; this reaches into one policy's list and takes the cell standing
there.

**A negative position counts back from that policy's own length**, so ``-1``
is the last period the policy has -- never the last cell of the bucket it
happens to be padded into. That distinction is the whole of this operation's
horizon rule, and a book of jagged terms makes every policy but the longest a
witness to it.

**Out of bounds refuses the whole invocation**, with no nullable or
fill-on-bounds mode anywhere behind the identifier. An empty list therefore
refuses: there is no position in it for anything to select.

``list.reverse`` (11.1.41) turns each policy's list end for end, and its
horizon rule is the same one: position ``t`` of the answer is the operand's
position ``T - 1 - t`` where ``T`` is **that policy's own** length. Reversed
across the bucket instead, a policy short of it would open on a padded cell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax.numpy as jnp

from gaspatchio_jax.capability import (
    ANY_CARRIER,
    NUMERIC,
    PER_PERIOD,
    PER_POLICY,
    Capability,
)
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import periods_of, resolve_position
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.typed import DomainRefused, Value

if TYPE_CHECKING:
    from gaspatchio.engines.format import Call
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Carrier

_SELECT: Final = "11.1.22"
_REVERSAL: Final = "11.1.41"
_SHAPES: Final = "11.1.18"

# 11.1.22's position domain, in the clause's own words: "a whole-number
# literal or a scalar i64 value ... a Boolean, decimal, text, date or
# list-shaped position is refused, including a decimal whose value happens to
# be integral".
_POSITION: Final[frozenset[Carrier]] = frozenset({"i64"})


@register(
    Capability(
        identifier="list.get",
        arity=(2,),
        carriers=(NUMERIC, _POSITION),
        shapes=(PER_PERIOD, PER_POLICY),
        # The reference producer refuses both forms too.
        refused_alike={
            "shape@0": "write the per-period column the selection means",
            "carrier@1": (
                "write the position as a whole number: to_integer() over a "
                "decimal, before the selection"
            ),
        },
        answers="scalar",
        checks=("list_get.bounds",),
        horizon="shift-or-select",
        clause=_SELECT,
        note="a negative position counts back from that policy's own length",
    )
)
def _list_get(call: Call, ctx: LoweringContext) -> Value:
    """Return the cell each policy's own position names, refusing one outside it."""
    value = ctx.lower(call.args[0])
    if value.shape != "list":
        raise DomainRefused(
            what=(
                "list.get is written over one value per policy, and it "
                "selects a position out of a per-period list"
            ),
            move="write the per-period column the selection means",
            clause=_SHAPES,
        )
    position_value = ctx.lower(call.args[1])
    if position_value.carrier != "i64":
        raise DomainRefused(
            what=(
                f"list.get is written with a {position_value.carrier} "
                "position, and a position is a whole number"
            ),
            move=(
                "write the position as a whole number: a decimal whose value "
                "happens to be integral is refused by this clause too"
            ),
            clause=_SELECT,
        )
    horizon = periods_of(value)
    position, inside = resolve_position(horizon, position_value.array)
    flag("list_get.bounds", ~inside)
    held = jnp.clip(position, 0, horizon.bucket - 1)
    selected = jnp.take_along_axis(value.array, held[:, None], axis=1)[:, 0]
    cells = value.dtype.removeprefix("list[").removesuffix("]")
    return Value(selected, value.carrier, "scalar", cells)


@register(
    Capability(
        identifier="list.reverse",
        arity=(1,),
        carriers=(ANY_CARRIER,),
        shapes=(PER_PERIOD,),
        # The reference producer refuses a per-policy operand too.
        refused_alike={"shape@0": "write the per-period column the reversal means"},
        horizon="shift-or-select",
        clause=_REVERSAL,
        note="each policy is reversed within its own length, never across the padding",
    )
)
def _list_reverse(call: Call, ctx: LoweringContext) -> Value:
    """Return each policy's own list end for end: position ``t`` reads ``T - 1 - t``.

    A gather inside each policy's bucket row, at the mirror of every position
    in that policy's own length. The cells past the horizon gather whatever
    the clip lands them on; they are padding, are trimmed on the way out, and
    every operation that could read one masks it to its own neutral first.
    """
    value = ctx.lower(call.args[0])
    if value.shape != "list":
        raise DomainRefused(
            what=(
                "list.reverse is written over one value per policy, and it "
                "turns a per-period list end for end"
            ),
            move="write the per-period column the reversal means",
            clause=_SHAPES,
        )
    horizon = periods_of(value)
    position = jnp.arange(horizon.bucket)[None, :]
    mirrored = jnp.clip(horizon.t[:, None] - 1 - position, 0, horizon.bucket - 1)
    turned = jnp.take_along_axis(
        value.array, jnp.broadcast_to(mirrored, value.array.shape), axis=1
    )
    return Value(turned, value.carrier, "list", value.dtype, horizon)
