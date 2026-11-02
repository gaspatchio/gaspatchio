# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Folds along the period axis: the four totals and the two running ones.

``sum`` is the present value of a whole discounted cashflow; ``mean`` the
average reserve held over a projection; ``min`` and ``max`` the lowest the
account value fell to and the high-water mark a fund reached. ``cum_sum`` and
``cum_prod`` are the same folds kept per period rather than reduced to one
number -- the premium taken to date, the running survival probability.

**Every one of them masks first.** A fold that read the padded cells would be
reading positions that are not periods of that policy, and the whole horizon
rule is one sentence: the operand goes to the fold's own neutral
element beyond the policy's own count -- 0 for a sum, 1 for a product,
``+inf`` for a minimum, ``-inf`` for a maximum -- so a cell past the end
contributes nothing whatever the bucket happens to be.

**The denominator of a mean is that policy's own periods and never the
grid's.** 11.1.15 says so outright, and it is the error that survives testing:
on a level timeline the two denominators are the same number, and they differ
for every policy but the longest as soon as the book is a real one.

**The folds are sequential scans.** A reduction whose order XLA may
choose reassociates differently at two static shapes -- a masked sum of one
book's own eighty-three values moves one unit in the last place between two
buckets -- and a model's answer must not depend on how wide a bucket the
engine picked. A scan has one order
whatever the shape is, so batch and bucket invariance is bit-identity rather
than a tolerance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax.numpy as jnp
from jax import lax

from gaspatchio_jax.capability import PER_PERIOD, Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import Horizon, mask_to_neutral, periods_of
from gaspatchio_jax.ieee import divided
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.typed import (
    INT64_MAX,
    INT64_MIN,
    DomainRefused,
    Value,
    carried_to,
    checked_add,
    checked_mul,
)

# What a fold is stated over: 11.1.14's own "per-period column" of numbers,
# and a run of flags. The totals, the average and the two running folds count
# a run of flags in whole numbers (11.1.9, 11.1.14): a total of flags is how
# many were set. The least and the greatest choose one of the run's own values
# (11.1.16, 11.1.17), so over a run of flags they answer a flag: whether every
# period was set, and whether any was.
_FOLDED: Final[frozenset[Carrier]] = frozenset({"i64", "f64", "bool"})
_COUNTED: Final[frozenset[Carrier]] = _FOLDED

# The type a running fold of whole numbers answers, per period.
WHOLE_NUMBER_RUN: Final = "list[i64]"

if TYPE_CHECKING:
    from collections.abc import Callable

    import jax

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.lowerings import Lowering
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Carrier

_RUNNING: Final = "11.1.9"
_SUM: Final = "11.1.14"
_SHAPES: Final = "11.1.18"

# What each fold's neutral element is: the value a cell can take without
# moving the answer. This is the whole of the horizon rule for this module.
_NEUTRAL: Final[dict[str, float]] = {
    # IEEE's additive identity is -0.0: a sum started from +0.0 turns a run
    # of negative noughts into a positive one, where the sum of one period is
    # that period (11.1.14). The empty sum is +0.0 and is set after the fold.
    "sum": -0.0,
    "mean": 0.0,
    "min": float("inf"),
    "max": float("-inf"),
    "cum_sum": -0.0,
    "cum_prod": 1.0,
}

# And how each one puts two values together.
_COMBINE: Final[dict[str, Callable[[jax.Array, jax.Array], jax.Array]]] = {
    "sum": lambda carry, cell: carry + cell,
    "mean": lambda carry, cell: carry + cell,
    "min": jnp.minimum,
    "max": jnp.maximum,
    "cum_sum": lambda carry, cell: carry + cell,
    "cum_prod": lambda carry, cell: carry * cell,
}

# The clause each identifier is stated in.
_CLAUSE: Final[dict[str, str]] = {
    "sum": _SUM,
    "mean": "11.1.15",
    "min": "11.1.16",
    "max": "11.1.17",
    "cum_sum": _RUNNING,
    "cum_prod": _RUNNING,
}


def running(
    cells: jax.Array,
    initial: jax.Array,
    combine: Callable[[jax.Array, jax.Array], jax.Array],
    *,
    reverse: bool = False,
) -> tuple[jax.Array, jax.Array]:
    """Return one sequential fold's last carry and its whole running answer.

    The scan runs along the period axis with the policies as the carry, which
    is the shape a fold of one policy's own timeline has: no value of one
    policy reaches another's answer, and the order the cells are combined in
    is the axis's own rather than one a reduction chose from the shape.
    """

    def step(carry: jax.Array, cell: jax.Array) -> tuple[jax.Array, jax.Array]:
        folded = combine(carry, cell)
        return folded, folded

    last, kept = lax.scan(step, initial, cells.T, reverse=reverse)
    return last, kept.T


# The move a fold over a per-policy value is refused with, by the declaration
# and by the lowering alike.
_FOLD_PERIODS: Final = (
    "fold the per-period column the model means: a fold down the rows of a "
    "model-point file is a different calculation and this vocabulary does not "
    "name it"
)


def _a_period_operand(value: Value, name: str) -> Value:
    """Return the operand, refusing a per-policy one.

    11.1.14's own paragraph: an engine's method of the same name applied to a
    per-policy column folds down the rows of the model-point file, which is a
    different calculation whose answer depends on the order those rows happen
    to stand in. This vocabulary does not name it, so it refuses here.
    """
    if value.shape != "list":
        raise DomainRefused(
            what=(
                f"{name} is written over one value per policy, and this "
                "operation folds one policy's own periods"
            ),
            move=_FOLD_PERIODS,
            clause=_SHAPES,
        )
    return value


def _flags_counted(value: Value, name: str) -> Value:
    """Return a run of flags as the whole numbers it counts, anything else as it is.

    11.1.9 and 11.1.14 fold a run of flags as the whole numbers it indicates:
    a total is how many periods were set, a running total how many have been
    so far, a running product whether every one has. The producer and the
    reader answer ``i64`` and ``list[i64]``, and so does this engine, through
    the same checked whole-number fold any run of whole numbers takes.
    """
    if value.carrier != "bool":
        return value
    return carried_to(value, "i64", clause=_CLAUSE[name])


def _a_run_of_no_periods(horizon: Horizon) -> None:
    """Flag a policy with no periods for the three folds that have none.

    ``sum`` answers nought over an empty run -- a fold that reached no period
    has lost none -- and 11.1.15 to 11.1.17 answer null: there is no value to
    be the average, the least or the greatest of. A null is a value this
    engine cannot hold or answer over, so the policies with no periods are
    named and counted rather than published as an infinity or a NaN, either
    of which reads as a number a reviewer could check.

    A flag rather than a count read here: a per-policy period count is a value
    like any other, and what refuses over it refuses at completion.
    """
    flag("reduction.no_periods", horizon.t == 0)


# The folds that build a value rather than choosing one, and so owe 11.1.25's
# range check when they build it out of whole numbers.
_ARITHMETIC_FOLDS: Final[frozenset[str]] = frozenset(
    {"sum", "mean", "cum_sum", "cum_prod"}
)


def _neutral_for(name: str, carrier: str) -> float | int:
    """Return the element a cell can take without moving this fold's answer.

    Nought for a sum and one for a product whatever the carrier is; for the
    least and the greatest it is the end of the type, which for a whole number
    is the end of ``i64`` rather than an infinity a whole number cannot hold.
    """
    if carrier == "i64" and name in ("min", "max"):
        return INT64_MAX if name == "min" else INT64_MIN
    return _NEUTRAL[name]


def _checked_running(
    name: str, cells: jax.Array, initial: jax.Array, *, reverse: bool = False
) -> tuple[jax.Array, jax.Array]:
    """Return an integer fold, with every product and sum outside ``i64`` flagged.

    The same sequential scan, with the typed path's own checked arithmetic
    inside it: an integer fold that wrapped would publish the hardware's
    answer, and 11.1.25 says outright that the wrap is not a portable one. The
    two operands the host re-judges a coarse product against travel out of the
    scan beside the result, because the left operand of a fold's product is
    the running carry and nothing outside the scan has it.
    """
    operation = checked_add if name in ("sum", "mean", "cum_sum") else checked_mul

    def step(
        carry: jax.Array, cell: jax.Array
    ) -> tuple[jax.Array, tuple[jax.Array, ...]]:
        checked = operation(carry, cell)
        return checked.result, (checked.result, checked.overflow, carry, cell)

    last, (kept, overflow, before, each) = lax.scan(
        step, initial, cells.T, reverse=reverse
    )
    flag(
        "i64.range",
        overflow.T,
        judgement="mul" if operation is checked_mul else None,
        operands=(before.T, each.T) if operation is checked_mul else (),
    )
    return last, kept.T


def _fold(
    name: str, value: Value, *, reverse: bool = False
) -> tuple[jax.Array, jax.Array]:
    """Return one masked fold's last carry and its whole running answer."""
    horizon = periods_of(value)
    neutral = _neutral_for(name, value.carrier)
    masked = mask_to_neutral(value, horizon, neutral)
    initial = jnp.full((masked.array.shape[0],), neutral, dtype=masked.array.dtype)
    if value.carrier == "i64" and name in _ARITHMETIC_FOLDS:
        # The least and the greatest of a run of whole numbers are two of its
        # own values and can leave no range; only the total and the product
        # have arithmetic to check.
        return _checked_running(name, masked.array, initial, reverse=reverse)
    return running(masked.array, initial, _COMBINE[name], reverse=reverse)


def whole_number_running_total(value: Value, *, reverse: bool) -> jax.Array:
    """Return the running total of a run of whole numbers, every sum checked.

    ``cum_sum``'s own checked fold, masked to nought beyond each policy's
    horizon, for a fold elsewhere that is a running total of whole numbers:
    ``projection.remaining_sum`` is ``cum_sum`` in reverse, and over a run of
    whole numbers 11.1.20 answers each period exactly, never through a double.
    """
    _last, kept = _fold("cum_sum", value, reverse=reverse)
    return kept


def _reduction(name: str) -> Lowering:
    """Return the lowering for one of the four folds to a single number."""

    def lowering(call: Call, ctx: LoweringContext) -> Value:
        read = _a_period_operand(ctx.lower(call.args[0]), name)
        # 11.1.15 answers an average, which is a decimal whatever the periods
        # were carried in; the other three answer a value of the run, and a
        # run of whole numbers has a whole least, greatest and total. So the
        # operand is widened for one of the four and for none of the others,
        # and the answer is the carrier the record declares either way.
        operand = (
            carried_to(read, "f64", clause=_CLAUSE[name])
            if name == "mean"
            else _flags_counted(read, name)
        )
        horizon = periods_of(operand)
        if name != "sum":
            _a_run_of_no_periods(horizon)
        total, _ = _fold(name, operand)
        if name == "sum" and operand.carrier == "f64":
            # 11.1.14: an empty sum is +0.0, on every side.
            total = jnp.where(horizon.t == 0, 0.0, total)
        if name == "mean":
            total = divided(total, horizon.t.astype(total.dtype))
        if read.carrier == "bool" and name in ("min", "max"):
            # The least or the greatest of the flags counted as 0 and 1 is
            # one of them, and is answered as the flag it is.
            return Value(total != 0, "bool", "scalar", _cell_name(read))
        return Value(total, operand.carrier, "scalar", _cell_name(operand))

    lowering.__name__ = name
    return lowering


def _cell_name(operand: Value) -> str:
    """Return the type one per-period operand's own cells stand under."""
    return operand.dtype.removeprefix("list[").removesuffix("]")


for _name in ("sum", "mean", "min", "max"):
    register(
        Capability(
            identifier=_name,
            arity=(1,),
            carriers=(_COUNTED if _name in ("sum", "mean") else _FOLDED,),
            shapes=(PER_PERIOD,),
            answers="scalar",
            # 11.1.15 divides, so it answers a decimal whatever it folded;
            # the other three answer in the periods' own carrier and say so
            # by not stating one.
            answers_carrier="f64" if _name == "mean" else None,
            checks=(
                ("reduction.no_periods", "i64.range")
                if _name != "sum"
                else ("i64.range",)
            ),
            horizon="reduction",
            clause=_CLAUSE[_name],
            # The reference producer refuses a fold over a per-policy value too.
            refused_alike={"shape@0": _FOLD_PERIODS},
            note=(
                "the fold is one policy's own periods, and the denominator of "
                "a mean is that policy's own count"
            ),
        )
    )(_reduction(_name))


def _cumulative(name: str) -> Lowering:
    """Return the lowering for one of the two running folds."""

    def lowering(call: Call, ctx: LoweringContext) -> Value:
        read = _a_period_operand(ctx.lower(call.args[0]), name)
        operand = _flags_counted(read, name)
        horizon = periods_of(operand)
        reverse = bool(dict(call.attrs).get("reverse", False))
        _last, kept = _fold(name, operand, reverse=reverse)
        # A run of flags counted is a run of whole numbers, and says so.
        dtype = operand.dtype if operand is read else WHOLE_NUMBER_RUN
        return Value(kept, operand.carrier, "list", dtype, horizon)

    lowering.__name__ = name
    return lowering


for _name in ("cum_sum", "cum_prod"):
    register(
        Capability(
            identifier=_name,
            arity=(1,),
            carriers=(_COUNTED,),
            shapes=(PER_PERIOD,),
            # 11.1.9 makes the direction part of the calculation and always
            # present. Under ``reverse`` this reads a later period, so the
            # class is the stronger of the two the identifier can take and the
            # masking is done either way -- a neutral cell past the horizon
            # changes a forward fold's answer no more than it changes a
            # reverse one's.
            attrs={"reverse": ("True", "False")},
            checks=("i64.range",),
            horizon="reverse-fold",
            clause=_RUNNING,
            # The reference producer refuses a running fold over a per-policy
            # value too.
            refused_alike={"shape@0": _FOLD_PERIODS},
            note="the direction is the record's, and both directions are masked",
        )
    )(_cumulative(_name))
