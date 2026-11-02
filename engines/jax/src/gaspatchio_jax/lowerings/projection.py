# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The projection family: survival, shifts, the recurrence and the two valuations.

Nine operations and four horizon classes between them, which is why the class
is on each registration rather than argued once for the module:

* ``cumulative_survival`` is a **forward fold** -- the running product of
  one-minus-the-decrement -- and a forward fold cannot reach a cell it has not
  passed, so nothing past the horizon is in any answer before it. The masking
  is done anyway, to 1, because a padded decrement would otherwise poison the
  carry the trim keeps.
* ``accumulate`` is the **recurrence** 11.1.20 states outright, and the clause
  says outright what not to do with it: "an implementation must not replace it
  with a division by a cumulative product". A zero multiplier is an ordinary
  value in an account-value roll-forward and a division would lose the whole
  policy on it. Under ``reverse`` it runs from each policy's own last period
  back to its first, which is a reverse fold's reach: its class is the stronger
  of the two, as ``cum_sum``'s is, and the padding is masked either way.
* ``remaining_sum`` and ``prospective_value`` are **reverse folds**: every
  answer reads the periods after it, so the cashflow goes to 0 beyond the
  policy's own horizon before a single suffix is taken. The cashflow is the
  one that moves a value -- a padded 100 is in every answer before it -- and
  the rate is masked for the other reason: it reaches no earlier position,
  and what a padded rate can do is trip the clause's own rate check and
  refuse a run over a cell nobody in the model wrote.
* The three shifts are **selections**: the boundary they fill at is that
  policy's own last period, never the bucket's last cell.
* ``with_period`` and ``broadcast_to_periods`` **generate** to the bucket and
  are trimmed, and a negative position in either resolves against the policy's
  own length.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax.numpy as jnp

from gaspatchio.engines.format import Lit
from gaspatchio_jax.capability import (
    ANY_CARRIER,
    EITHER_SHAPE,
    NUMERIC,
    PER_PERIOD,
    PER_POLICY,
    Capability,
)
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import (
    Horizon,
    aligned,
    boundary,
    mask_to_neutral,
    periods_of,
    resolve_position,
    spread,
)
from gaspatchio_jax.ieee import divided, multiplied
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.lowerings.reduction import (
    WHOLE_NUMBER_RUN,
    running,
    whole_number_running_total,
)
from gaspatchio_jax.typed import (
    DomainRefused,
    Value,
    carried_to,
    outside_prospective_rate,
)

if TYPE_CHECKING:
    import jax

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.ieee import Operand
    from gaspatchio_jax.lowerings import Lowering
    from gaspatchio_jax.plan import LoweringContext

_SHIFTS: Final = "11.1.19"
_RECURRENCE: Final = "11.1.20"
_VALUATION: Final = "11.1.21"
_OVERRIDES: Final = "11.1.32"
_SHAPES: Final = "11.1.18"

# 11.1.21's two conventions, and the one kind of discount this entry states.
_BEGINNING: Final = "beginning_of_period"
_END: Final = "end_of_period"
_RATE: Final = "rate"

# The floor 11.1.21 puts under a discount rate: at -1 the factor discounts to
# nothing at all and below it the sign of the value turns over.

# The scalar types 11.1.32 admits on the value a broadcast repeats.
_BROADCAST_CARRIERS: Final = ANY_CARRIER - frozenset({"date"})


# The move a per-period initial value is refused with, by the declaration and
# by the lowering alike: the reference producer's own.
_ONE_INITIAL: Final = (
    "write the initial value once per policy: the recurrence starts from it and "
    "runs over the per-period multiplier and addend"
)


def _period_operand(value: Value, name: str, clause: str) -> Value:
    """Return a per-period operand as a double, refusing a per-policy one."""
    if value.shape != "list":
        raise DomainRefused(
            what=(
                f"{name} is written over one value per policy, and this "
                "operation is along one policy's own periods"
            ),
            move="write the per-period column this line means",
            clause=_SHAPES,
        )
    return carried_to(value, "f64", clause=clause)


@register(
    Capability(
        identifier="projection.cumulative_survival",
        arity=(1,),
        carriers=(NUMERIC,),
        shapes=(PER_PERIOD,),
        attrs={"from_survival": ("False",)},
        horizon="forward-fold",
        clause=_SHIFTS,
        note=(
            "the decrement form: a running product of one minus the "
            "decrement, with start_at as the opening boundary"
        ),
    )
)
def _cumulative_survival(call: Call, ctx: LoweringContext) -> Value:
    """Return the running survival probability of one policy's own decrements.

    11.1.19: ``c[t] = product(1 - q[u], u=0..t)``. With a ``start_at`` of
    ``a`` the answer is ``[a, c[0], ..., c[T-2]]`` -- ``a`` is the value at the
    opening boundary and never an extra factor in every later product, which
    is the reading that would quietly scale a whole survival curve.
    """
    decrement = _period_operand(ctx.lower(call.args[0]), "cumulative_survival", _SHIFTS)
    horizon = periods_of(decrement)
    survives = Value(1.0 - decrement.array, "f64", "list", "list[f64]", horizon)
    masked = mask_to_neutral(survives, horizon, 1.0)
    initial = jnp.ones((masked.array.shape[0],), dtype=masked.array.dtype)
    _last, running_product = running(masked.array, initial, jnp.multiply)
    start_at = dict(call.attrs).get("start_at")
    if start_at is None:
        return Value(running_product, "f64", "list", "list[f64]", horizon)
    opened = jnp.concatenate(
        [
            jnp.full((running_product.shape[0], 1), float(start_at)),
            running_product[:, :-1],
        ],
        axis=1,
    )
    return Value(opened, "f64", "list", "list[f64]", horizon)


def _shift(name: str, offset: int | None) -> Lowering:
    """Return the lowering for one of 11.1.19's three shifts.

    One body for three, because they are one operation with three offsets and
    three near-identical bodies would be three places for the boundary rule to
    drift. The boundary is the policy's own: a ``next_period`` that filled at
    the bucket's last cell would hand every policy short of the bucket a
    padded cell as its last period.
    """

    def lowering(call: Call, ctx: LoweringContext) -> Value:
        value = _period_operand(ctx.lower(call.args[0]), name, _SHIFTS)
        horizon = periods_of(value)
        fill = carried_to(ctx.lower(call.args[1]), "f64", clause=_SHIFTS)
        step = offset if offset is not None else _relative_period(call)
        landing = jnp.clip(
            jnp.arange(horizon.bucket)[None, :] + step, 0, horizon.bucket - 1
        )
        gathered = jnp.take_along_axis(
            value.array, jnp.broadcast_to(landing, value.array.shape), axis=1
        )
        answered = jnp.where(boundary(horizon, step), spread(fill, horizon), gathered)
        return Value(answered, "f64", "list", "list[f64]", horizon)

    lowering.__name__ = name
    return lowering


def _relative_period(call: Call) -> int:
    """Return the offset ``at_period`` names, refusing one that is not whole.

    Raises:
        DomainRefused: If the attribute is absent or is not a whole number.
            11.1.19 states the shift by a *relative period*, and a fractional
            one names no position at all.

    """
    stated = dict(call.attrs).get("relative_period")
    if not isinstance(stated, int) or isinstance(stated, bool):
        raise DomainRefused(
            what=(
                f"projection.at_period is written with "
                f"relative_period={stated!r}, and a shift is by a whole "
                "number of periods"
            ),
            move="write the offset the model means as a whole number",
            clause=_SHIFTS,
        )
    return stated


for _name, _offset in (
    ("projection.previous_period", -1),
    ("projection.next_period", 1),
    ("projection.at_period", None),
):
    register(
        Capability(
            identifier=_name,
            arity=(2,),
            carriers=(NUMERIC, NUMERIC),
            shapes=(PER_PERIOD, PER_POLICY),
            attr_bounds=(
                {"relative_period": (None, None)} if _offset is None else None
            ),
            horizon="shift-or-select",
            clause=_SHIFTS,
            note="the boundary is that policy's own last period, not the grid's",
        )
    )(_shift(_name, _offset))


@register(
    Capability(
        identifier="projection.accumulate",
        arity=(3,),
        carriers=(NUMERIC, NUMERIC, NUMERIC),
        # 11.1.20: the initial value is a literal or a scalar column, and
        # "at least one of multiplier and addend is a finite Float64 list ...
        # the other may be a list of the same length or a finite numeric
        # literal". That is a disjunction over two positions, which one
        # admitted set per position cannot state -- so both steps admit
        # either shape here and the lowering's own refusal below carries the
        # rule: a line with no per-period step at all has nothing to supply
        # the periods.
        shapes=(PER_POLICY, EITHER_SHAPE, EITHER_SHAPE),
        # The reference producer refuses a per-period initial value too.
        refused_alike={"shape@0": _ONE_INITIAL},
        # 11.1.20 makes the direction part of the calculation and always
        # present. Under ``reverse`` an answer reads every later period, so the
        # class is the stronger of the two the identifier can take -- the
        # precedent ``cum_sum`` sets -- and a padding witness holds both.
        attrs={"reverse": ("True", "False")},
        horizon="reverse-fold",
        clause=_RECURRENCE,
        note=(
            "the linear recurrence itself, stepped period by period in the "
            "record's direction, a reverse run starting at each policy's own "
            "last period: 11.1.20 excludes replacing it with a division by a "
            "cumulative product"
        ),
    )
)
def _accumulate(call: Call, ctx: LoweringContext) -> Value:
    """Return ``s[t] = s[t-1] * multiplier[t] + addend[t]``, opening at ``initial``.

    Stepped, never divided. 11.1.20 says a zero or negative multiplier is an
    ordinary value here, and the shortcut -- a cumulative product divided back
    out -- loses the whole policy at the first zero. An account value that
    went to nothing for one month is an account value, not a defect.

    Under ``reverse`` the same step runs the scan from the bucket's last cell
    back: ``s[t] = s[t+1] * multiplier[t] + addend[t]``, opening at ``initial``
    after the policy's last period. A jagged book is the whole difficulty
    there, because a policy short of the bucket meets its padding *first*. The
    padding is a multiplier of 1 and an addend of 0, and the carry is also
    held unchanged across a padded cell rather than stepped through it, so
    each policy opens at its own last period on exactly ``initial`` -- a
    negative zero included, which ``-0.0 * 1 + 0`` would turn positive.
    """
    initial = carried_to(ctx.lower(call.args[0]), "f64", clause=_RECURRENCE)
    if initial.shape == "list":
        raise DomainRefused(
            what=(
                "projection.accumulate is written over one value per period at "
                "its initial value, and the recurrence starts once per policy"
            ),
            move=_ONE_INITIAL,
            clause=_RECURRENCE,
        )
    multiplier = carried_to(ctx.lower(call.args[1]), "f64", clause=_RECURRENCE)
    addend = carried_to(ctx.lower(call.args[2]), "f64", clause=_RECURRENCE)
    axis = aligned(multiplier, addend)
    if axis.horizon is None:
        raise DomainRefused(
            what=(
                "this recurrence is written with no per-period step at all, "
                "so nothing supplies the periods to step over"
            ),
            move=(
                "write the multiplier or the addend as the per-period column "
                "it is: 11.1.20 takes that operand's own length as the count"
            ),
            clause=_RECURRENCE,
        )
    horizon = axis.horizon
    steps = jnp.broadcast_to(axis.arrays[0], (initial.array.shape[0], horizon.bucket))
    added = jnp.broadcast_to(axis.arrays[1], steps.shape)
    steps = jnp.where(horizon.active, steps, 1.0)
    added = jnp.where(horizon.active, added, 0.0)

    def one_period(
        carry: jax.Array, step: tuple[jax.Array, jax.Array, jax.Array]
    ) -> tuple[jax.Array, jax.Array]:
        # The product rounded before the addend is added, as 11.1.20 states
        # two operations: fused, the carry moves by a place per period.
        moved = jnp.where(step[2], multiplied(carry, step[0]) + step[1], carry)
        return moved, moved

    from jax import lax  # noqa: PLC0415 -- the one scan this module takes

    _last, kept = lax.scan(
        one_period,
        initial.array,
        (steps.T, added.T, horizon.active.T),
        reverse=_direction(call),
    )
    return Value(kept.T, "f64", "list", "list[f64]", horizon)


def _direction(call: Call) -> bool:
    """Return whether the recurrence runs back from each policy's last period.

    Raises:
        DomainRefused: If ``reverse`` is not a truth value. 11.1.11 records it
            as a flag, and a direction read out of a number or a word would be
            a direction nobody wrote.

    """
    stated = dict(call.attrs).get("reverse", False)
    if not isinstance(stated, bool):
        raise DomainRefused(
            what=(
                f"projection.accumulate is written with reverse={stated!r}, and "
                "the direction is true or false"
            ),
            move="write the direction the model means as true or false",
            clause=_RECURRENCE,
        )
    return stated


@register(
    Capability(
        identifier="projection.remaining_sum",
        arity=(1,),
        carriers=(NUMERIC,),
        shapes=(PER_PERIOD,),
        # The reference producer refuses a per-policy operand too.
        refused_alike={"shape@0": "write the per-period column this line means"},
        checks=("i64.range",),
        horizon="reverse-fold",
        clause=_RECURRENCE,
        note="the inclusive suffix sum, masked to nought beyond the horizon",
    )
)
def _remaining_sum(call: Call, ctx: LoweringContext) -> Value:
    """Return the inclusive suffix sum: what is still to come at each period.

    Over a run of whole numbers, and a run of flags counted as the whole
    numbers they indicate, 11.1.20 answers ``list[i64]``, each period exact:
    the same checked running total ``cum_sum`` takes in reverse, refusing a
    period whose sum leaves ``i64`` by name. Over decimals it is the suffix
    sum of doubles.
    """
    read = ctx.lower(call.args[0])
    if read.shape == "list" and read.carrier in ("i64", "bool"):
        whole = carried_to(read, "i64", clause=_RECURRENCE)
        kept = whole_number_running_total(whole, reverse=True)
        return Value(kept, "i64", "list", WHOLE_NUMBER_RUN, periods_of(whole))
    value = _period_operand(read, "remaining_sum", _RECURRENCE)
    horizon = periods_of(value)
    masked = mask_to_neutral(value, horizon, 0.0)
    initial = jnp.zeros((masked.array.shape[0],), dtype=masked.array.dtype)
    _last, kept = running(masked.array, initial, jnp.add, reverse=True)
    return Value(kept, "f64", "list", "list[f64]", horizon)


def _discounting(written: object, masked_rate: jax.Array) -> tuple[Operand, jax.Array]:
    """Return each period's discount and each boundary's, as the producer forms them.

    A rate the model wrote as a number is the reference producer's closed
    form: ``v = 1 / (1 + r)`` once, on the host, and ``B[t] = v ** t``. A rate
    column is its running product, ``B[t] = B[t-1] * v[t-1]``. The two are the
    same value to the last place or two and not the same doubles, so the
    engine forms each the producer's way. A written rate of exactly -1 has
    no ``v`` to form on the host; it takes the running product, whose
    infinite factor the rate check refuses.
    """
    if (
        isinstance(written, Lit)
        and isinstance(written.value, (int, float))
        and not isinstance(written.value, bool)
        and 1.0 + float(written.value) != 0.0
    ):
        v = 1.0 / (1.0 + float(written.value))
        periods = jnp.arange(masked_rate.shape[1], dtype=masked_rate.dtype)
        opening = jnp.broadcast_to(jnp.power(v, periods)[None, :], masked_rate.shape)
        return v, opening
    factor = divided(1.0, 1.0 + masked_rate)
    ones = jnp.ones((masked_rate.shape[0],), dtype=masked_rate.dtype)
    _last, inclusive = running(factor, ones, jnp.multiply)
    return factor, jnp.concatenate([ones[:, None], inclusive[:, :-1]], axis=1)


@register(
    Capability(
        identifier="projection.prospective_value",
        arity=(2,),
        carriers=(NUMERIC, NUMERIC),
        shapes=(PER_PERIOD, EITHER_SHAPE),
        # The reference producer refuses a per-policy cashflow too.
        refused_alike={"shape@0": "write the per-period column this line means"},
        attrs={"timing": (_BEGINNING, _END), "discount_kind": (_RATE,)},
        checks=("prospective_value.rate",),
        horizon="reverse-fold",
        clause=_VALUATION,
        note=(
            "the rate form: a factor convention is not inferred from a rate "
            "one, and the rate is masked before the suffix sums are taken"
        ),
    )
)
def _prospective_value(call: Call, ctx: LoweringContext) -> Value:
    """Return 11.1.21's suffix valuation of one policy's own cashflows.

    ``v[t] = 1/(1+rate[t])``, ``B[0] = 1``, ``B[t] = product(v[u], u<t)``, and
    the answer at ``t`` is the discounted remainder divided back to ``t``'s own
    boundary. Under ``beginning_of_period`` the current cashflow is
    undiscounted; under ``end_of_period`` each cashflow carries its own
    period's rate.

    **Both operands are masked, and the two masks do different work.** The
    cashflow goes to nought, and that one is the suffix sums: a padded
    cashflow of 100 is in every answer before it, at every position. The rate
    goes to nought -- a factor of one -- for a narrower reason. ``B[t]`` is a
    product of the rates strictly *before* ``t``, so a padded rate is in no
    ``B[t]`` the policy has and cannot move a value that way; what it can do
    is be exactly -1, whose factor is infinite, whose weighted cashflow is
    ``0 x inf``, and whose NaN the reverse fold then carries back into every
    period the policy does have.
    """
    cashflows = _period_operand(
        ctx.lower(call.args[0]), "prospective_value", _VALUATION
    )
    rate = carried_to(ctx.lower(call.args[1]), "f64", clause=_VALUATION)
    axis = aligned(cashflows, rate)
    horizon = axis.horizon
    if horizon is None:  # pragma: no cover -- cashflows were required per-period
        message = "per-period cashflows reached valuation without an aligned horizon"
        raise AssertionError(message)
    masked_flows = jnp.where(horizon.active, axis.arrays[0], 0.0)
    masked_rate = jnp.where(horizon.active, axis.arrays[1], 0.0)
    flag("prospective_value.rate", outside_prospective_rate(masked_rate))
    factor, opening = _discounting(call.args[1], masked_rate)
    # End of period: each cashflow carries its own period's discount too, and
    # the two factors are multiplied together before the cashflow is -- the
    # reference producer's grouping, ``cf * (v_open * v)``, which rounds
    # differently from ``(cf * v_open) * v``.
    if str(dict(call.attrs).get("timing", _END)) == _END:
        weighted = multiplied(masked_flows, opening * factor)
    else:
        weighted = multiplied(masked_flows, opening)
    zeros = jnp.zeros((masked_flows.shape[0],), dtype=masked_flows.dtype)
    _total, remaining = running(weighted, zeros, jnp.add, reverse=True)
    return Value(divided(remaining, opening), "f64", "list", "list[f64]", horizon)


@register(
    Capability(
        identifier="projection.with_period",
        arity=(1,),
        carriers=(NUMERIC,),
        shapes=(PER_PERIOD,),
        # The reference producer refuses a per-policy operand too.
        refused_alike={"shape@0": "write the per-period column this line means"},
        attrs_required=("period", "value"),
        attrs_numeric=("value",),
        attr_bounds={"period": (None, None)},
        horizon="generator",
        clause=_OVERRIDES,
        note="an override never extends a shorter policy or fills an empty list",
    )
)
def _with_period(call: Call, ctx: LoweringContext) -> Value:
    """Return the column with one period replaced, where that period exists.

    11.1.32: a negative ``period`` names the cell that far back from **that
    policy's own** length, and where the named cell does not exist the column
    comes back as it was. An override that extended a shorter policy would be
    minting a period nobody projected.
    """
    value = _period_operand(ctx.lower(call.args[0]), "with_period", _OVERRIDES)
    horizon = periods_of(value)
    attrs = dict(call.attrs)
    stated = attrs["period"]
    written = attrs["value"]
    if (
        not isinstance(stated, int)
        or isinstance(stated, bool)
        or not isinstance(written, (int, float))
        or isinstance(written, bool)
    ):
        raise DomainRefused(
            what=(
                f"projection.with_period names period={stated!r} and "
                f"value={written!r}, and this override is a decimal at a "
                "whole number of positions"
            ),
            move=(
                "write the position and the replacement as the numbers they "
                "are: an attribute is a flat typed value"
            ),
            clause=_OVERRIDES,
        )
    replacement = float(written)
    position, inside = resolve_position(horizon, jnp.full((1,), stated))
    at = (jnp.arange(horizon.bucket)[None, :] == position[:, None]) & inside[:, None]
    return Value(
        jnp.where(at, replacement, value.array), "f64", "list", "list[f64]", horizon
    )


@register(
    Capability(
        identifier="projection.broadcast_to_periods",
        arity=(2,),
        carriers=(_BROADCAST_CARRIERS, ANY_CARRIER),
        shapes=(PER_POLICY, PER_PERIOD),
        # The reference producer refuses an axis held once per policy too; a
        # value held per period it answers, so that form keeps the Polars move.
        refused_alike={"shape@1": "write the axis column whose length the model means"},
        horizon="generator",
        clause=_OVERRIDES,
        note=(
            "only the axis operand's length matters, never its values "
            "(11.1.32), and a calendar day is outside the bounded scalars"
        ),
    )
)
def _broadcast_to_periods(call: Call, ctx: LoweringContext) -> Value:
    """Return one per-policy value repeated once per cell of the axis operand."""
    value = ctx.lower(call.args[0])
    axis = ctx.lower(call.args[1])
    if value.shape == "list":
        raise DomainRefused(
            what=(
                "projection.broadcast_to_periods is written over one value per "
                "period at operand 0, and this engine repeats one value per policy"
            ),
            move=(
                "run this model on Polars, which repeats the whole run, or "
                "write the per-policy value the broadcast means"
            ),
            clause=_SHAPES,
        )
    if axis.shape != "list":
        raise DomainRefused(
            what=(
                "this broadcast names no per-period axis, so there is no "
                "length to repeat the value to"
            ),
            move="write the axis column whose length the model means",
            clause=_SHAPES,
        )
    horizon: Horizon = periods_of(axis)
    repeated = jnp.broadcast_to(
        spread(value, horizon), (value.array.shape[0], horizon.bucket)
    )
    return Value(repeated, value.carrier, "list", f"list[{value.dtype}]", horizon)
