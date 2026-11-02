# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The finance conversions, and the two discount-factor conventions.

Four scalar conversions and one per-period family. The four are arithmetic and
the family is the interesting one:

**Spot and forward are two different curves at the same horizon, and the
record keeps both operands either way.** Under ``spot`` a factor at a position
is that position's own rate raised to minus that position's own period, and a
scalar rate broadcasts across the list of periods. Under ``forward`` the rate
list is the whole of it: the answer has exactly as many factors as there are
rates, the first is 1 at the opening boundary, and the period operand supplies
no exponent, no length and no value -- it is retained because the caller wrote
it and the record does not drop what the caller wrote.

**The initial 1 belongs to the opening boundary.** 11.1.30 spells the two out
side by side at one horizon and they differ from the second position on, which
is why a reader may not infer one from the other.

**A zero denominator is a null, and a null is not a number.** ``discount``
answers null where the factor is zero and ``present_value`` answers null below
one period; this engine cannot hold a null and states no answer over one, so
it refuses those rows by name and with their count rather than publishing a
NaN that would read as a number a reviewer could check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax.numpy as jnp

from gaspatchio_jax.capability import EITHER_SHAPE, NUMERIC, PER_POLICY, Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import Aligned, aligned, mask_to_neutral, periods_of
from gaspatchio_jax.ieee import divided
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.lowerings.reduction import running
from gaspatchio_jax.typed import DomainRefused, Value, carried_to

if TYPE_CHECKING:
    from collections.abc import Mapping

    import jax

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Carrier

_CONVERSIONS: Final = "11.1.29"
_FACTORS: Final = "11.1.30"

_SIMPLE: Final = "simple"
_COMPOUND: Final = "compound"
_SPOT: Final = "spot"
_FORWARD: Final = "forward"

# The months a year is divided into, for the one conversion that names them.
_MONTHS: Final = 12.0

# Where a rate stops being a rate in this family.
_RATE_FLOOR: Final = -1.0

# 11.1.29's own operand domain for the two operations it states over policies:
# a finite decimal. A Boolean is a truth value and the producer refuses one.
_SCALAR_OPERANDS: Final[frozenset[Carrier]] = frozenset({"i64", "f64"})


def _named(carrier: str, like: Value) -> str:
    """Return the type name an answer stands under, in its operand's shape.

    A per-period answer's type is ``list[…]`` and a per-policy one's is the
    bare name. The two are one line apart and the value's own ``dtype`` is
    read where a nested call has no record to declare it.
    """
    return f"list[{carrier}]" if like.shape == "list" else carrier


def _double(value: Value, clause: str) -> Value:
    """Return one operand as a double, which is this family's whole domain."""
    return carried_to(value, "f64", clause=clause)


def _caught(check: str, cells: jax.Array) -> None:
    """Flag the cells a clause states no number for.

    A flag rather than a count read here and now: a value is knowable only
    once the calculation that produced it has run, and reading one at lowering
    time is reading it before that. The flag travels to completion, is held to
    the cells that are periods on the way, and refuses there with the check's
    own sentence and its count.
    """
    flag(check, cells)


@register(
    Capability(
        identifier="finance.to_monthly",
        arity=(1,),
        carriers=(NUMERIC,),
        attrs={"method": (_SIMPLE, _COMPOUND)},
        attrs_required=("method",),
        checks=("to_monthly.rate",),
        clause=_CONVERSIONS,
        note="a method token outside the two is not an alias for simple interest",
    )
)
def _to_monthly(call: Call, ctx: LoweringContext) -> Value:
    """Return the monthly equivalent of an annual rate, under the stated method."""
    rate = _double(ctx.lower(call.args[0]), _CONVERSIONS)
    method = str(dict(call.attrs)["method"])
    if method == _SIMPLE:
        return Value(
            divided(rate.array, float(_MONTHS)),
            "f64",
            rate.shape,
            _named("f64", rate),
            rate.horizon,
        )
    _caught("to_monthly.rate", rate.array < _RATE_FLOOR)
    return Value(
        jnp.power(1.0 + rate.array, 1.0 / _MONTHS) - 1.0,
        "f64",
        rate.shape,
        _named("f64", rate),
        rate.horizon,
    )


@register(
    Capability(
        identifier="finance.compound",
        arity=(1,),
        carriers=(NUMERIC,),
        attrs_required=("rate", "periods_per_year"),
        attrs_numeric=("rate",),
        attr_bounds={"periods_per_year": (1, None)},
        clause=_CONVERSIONS,
        note="the receiver is time, not an opening account value",
    )
)
def _compound(call: Call, ctx: LoweringContext) -> Value:
    """Return the growth factor over a number of periods at the stated rate."""
    periods = _double(ctx.lower(call.args[0]), _CONVERSIONS)
    attrs = dict(call.attrs)
    rate, per_year = _compounding(attrs)
    if rate <= _RATE_FLOOR or per_year <= 0:
        raise DomainRefused(
            what=(
                f"this compounding states rate={rate} over {per_year} periods "
                "a year, and the clause states a rate above -1 over a "
                "positive whole number of periods"
            ),
            move="check the basis the rate and the frequency were taken on",
            clause=_CONVERSIONS,
        )
    return Value(
        jnp.power(1.0 + rate, divided(periods.array, float(per_year))),
        "f64",
        periods.shape,
        _named("f64", periods),
        periods.horizon,
    )


def _compounding(attrs: Mapping[str, object]) -> tuple[float, int]:
    """Return the rate and the periods a year, refusing an attribute that is neither.

    Raises:
        DomainRefused: If either attribute is not the number 11.1.29 states.
            An attribute is a flat typed value (12.1), and one written as text
            names no rate at all.

    """
    rate, per_year = attrs.get("rate"), attrs.get("periods_per_year")
    if (
        not isinstance(rate, (int, float))
        or isinstance(rate, bool)
        or not isinstance(per_year, int)
        or isinstance(per_year, bool)
    ):
        raise DomainRefused(
            what=(
                f"this compounding states rate={rate!r} over "
                f"{per_year!r} periods a year, and the clause states a "
                "decimal rate over a whole number of periods"
            ),
            move="write the rate and the frequency as the numbers they are",
            clause=_CONVERSIONS,
        )
    return float(rate), int(per_year)


# The move a per-period operand of the two scalar valuations is refused with.
_PER_PERIOD_VALUATION: Final = (
    "write the per-period valuation as projection.prospective_value (11.1.21), "
    "which is the operation 11.1.29 names for it"
)


def _per_policy_only(axis: Aligned, name: str) -> None:
    """Refuse a per-period operand to the two operations stated over policies.

    11.1.29 states scalar operands only for ``finance.discount`` and
    ``finance.present_value`` and names the alternative in the same sentence.
    The declaration says so too, but a declaration is read one level deep:
    an operand that is a nested expression has no declared shape, so it
    reaches here unchecked and this is where the clause's own bound is kept.

    Raises:
        DomainRefused: If any operand stands per period.

    """
    if axis.shape != "list":
        return
    raise DomainRefused(
        what=(
            f"{name} is written over one value per period, and this clause "
            "states scalar operands only"
        ),
        move=_PER_PERIOD_VALUATION,
        clause=_CONVERSIONS,
    )


def _factor(rate: jax.Array, periods: jax.Array) -> jax.Array:
    """Return ``(1+r)^t``, the denominator both of the next two divide by."""
    return jnp.power(1.0 + rate, periods)


@register(
    Capability(
        identifier="finance.discount",
        arity=(3,),
        carriers=(_SCALAR_OPERANDS, _SCALAR_OPERANDS, _SCALAR_OPERANDS),
        # 11.1.29 states scalar operands only for these two, and names the
        # alternative itself: "a per-period cashflow valuation is the
        # separately specified projection.prospective_value".
        shapes=(PER_POLICY, PER_POLICY, PER_POLICY),
        # The reference producer refuses every operand held per period too.
        refused_alike={
            "shape@0": _PER_PERIOD_VALUATION,
            "shape@1": _PER_PERIOD_VALUATION,
            "shape@2": _PER_PERIOD_VALUATION,
        },
        answers_carrier="f64",
        checks=("discount.zero_factor",),
        clause=_CONVERSIONS,
        note=(
            "one value per policy: a per-period cashflow valuation is "
            "projection.prospective_value (11.1.21); an operand that is "
            "itself a calculation declares no shape, so a nested per-period "
            "operand is refused when the run reaches this lowering rather "
            "than by the tree reading, which reads a shape one level deep"
        ),
    )
)
def _discount(call: Call, ctx: LoweringContext) -> Value:
    """Return the value discounted back over the periods at the rate."""
    value, rate, periods = (
        _double(ctx.lower(argument), _CONVERSIONS) for argument in call.args
    )
    axis = aligned(value, rate, periods)
    _per_policy_only(axis, "finance.discount")
    denominator = _factor(axis.arrays[1], axis.arrays[2])
    _caught("discount.zero_factor", denominator == 0.0)
    return Value(divided(axis.arrays[0], denominator), "f64", "scalar", "f64")


@register(
    Capability(
        identifier="finance.present_value",
        arity=(3,),
        carriers=(_SCALAR_OPERANDS, _SCALAR_OPERANDS, _SCALAR_OPERANDS),
        shapes=(PER_POLICY, PER_POLICY, PER_POLICY),
        # The reference producer refuses every operand held per period too.
        refused_alike={
            "shape@0": _PER_PERIOD_VALUATION,
            "shape@1": _PER_PERIOD_VALUATION,
            "shape@2": _PER_PERIOD_VALUATION,
        },
        answers_carrier="f64",
        checks=("present_value.period",),
        clause=_CONVERSIONS,
        note=(
            "a per-row contribution, never a sum over periods: a per-period "
            "valuation is projection.prospective_value (11.1.21); an operand "
            "that is itself a calculation declares no shape, so a nested "
            "per-period operand is refused when the run reaches this lowering "
            "rather than by the tree reading, which reads a shape one level "
            "deep"
        ),
    )
)
def _present_value(call: Call, ctx: LoweringContext) -> Value:
    """Return one cashflow's own contribution, which is null below one period."""
    cashflow, rate, periods = (
        _double(ctx.lower(argument), _CONVERSIONS) for argument in call.args
    )
    axis = aligned(cashflow, rate, periods)
    _per_policy_only(axis, "finance.present_value")
    _caught("present_value.period", axis.arrays[2] < 1.0)
    return Value(
        divided(axis.arrays[0], _factor(axis.arrays[1], axis.arrays[2])),
        "f64",
        "scalar",
        "f64",
    )


@register(
    Capability(
        identifier="finance.discount_factor",
        arity=(2,),
        carriers=(NUMERIC, NUMERIC),
        shapes=(EITHER_SHAPE, EITHER_SHAPE),
        attrs={"method": (_SPOT, _FORWARD)},
        attrs_required=("method",),
        checks=("discount_factor.rate",),
        answers="list",
        # Under ``forward`` this is the running product of one over one plus
        # the rate, which reads every earlier period and none later; under
        # ``spot`` each position stands alone. The stronger of the two is
        # what the registration states.
        horizon="forward-fold",
        clause=_FACTORS,
        note=(
            "both operands are recorded under either method, and under "
            "forward the period operand supplies no exponent or length"
        ),
    )
)
def _discount_factor(call: Call, ctx: LoweringContext) -> Value:
    """Return the discount factors the stated convention gives."""
    rate = _double(ctx.lower(call.args[0]), _FACTORS)
    periods = _double(ctx.lower(call.args[1]), _FACTORS)
    method = str(dict(call.attrs)["method"])
    if method == _FORWARD:
        return _forward(rate)
    axis = aligned(rate, periods)
    if axis.horizon is None:
        raise DomainRefused(
            what=(
                "this discount factor is written over one value per policy "
                "on both operands, and the entry states forms with at least "
                "one per-period operand"
            ),
            move="write the per-period rate or the per-period periods column",
            clause=_FACTORS,
        )
    _caught("discount_factor.rate", axis.arrays[0] <= _RATE_FLOOR)
    factors = jnp.power(1.0 + axis.arrays[0], -axis.arrays[1])
    return Value(
        jnp.broadcast_to(factors, (axis.arrays[0].shape[0], axis.horizon.bucket)),
        "f64",
        "list",
        "list[f64]",
        axis.horizon,
    )


def _forward(rate: Value) -> Value:
    """Return exactly as many forward factors as there are rates.

    ``d[0] = 1`` at the opening boundary and ``d[t]`` the running product of
    one over one plus each earlier rate. The rate is masked to nought beyond
    the policy's own horizon so the carry the trim keeps is the carry its own
    periods built.
    """
    if rate.shape != "list":
        raise DomainRefused(
            what=(
                "a forward discount factor is written over one rate per "
                "policy, and this method takes the per-period rate list whose "
                "length is the answer's"
            ),
            move="write the per-period rate column the forward curve means",
            clause=_FACTORS,
        )
    horizon = periods_of(rate)
    masked = mask_to_neutral(rate, horizon, 0.0).array
    step = divided(1.0, 1.0 + masked)
    ones = jnp.ones((masked.shape[0],), dtype=masked.dtype)
    _last, inclusive = running(step, ones, jnp.multiply)
    opened = jnp.concatenate([ones[:, None], inclusive[:, :-1]], axis=1)
    return Value(opened, "f64", "list", "list[f64]", horizon)
