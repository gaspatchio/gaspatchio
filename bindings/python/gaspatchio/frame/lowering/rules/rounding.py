# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lowerings for the three ways a value is moved to a whole step.

``af.premium.round(2)`` is the line that bills a premium in pennies;
``af.exact_years.floor()`` is the completed years a duration has run, and
``.ceil()`` the whole units a charge is levied in. Each answers one value
at a time, so a per-policy value rounds with the engine's own method and a
per-period one rounds inside each row's list -- the same pair of forms
every elementwise rule in this package picks between, on the shape the
tree resolved rather than on the kind of proxy the call was written on.

``round`` carries both the number of places and the tie rule, because both
move the money: half a penny going to the even neighbour is not half a
penny going away from zero. The two rules part company on the ties whose
away-from-zero neighbour is odd, which is enough of them to matter and few
enough that a model can be tested under one rule and billed under the
other without anybody noticing. The rule is read back off the record
rather than left to the engine's default, so a model rounded under one
rule cannot be re-run under another and still answer to the same digest.

What ``round`` moves is the value a spreadsheet holds, not the double
beneath it: the double's fifteen-significant-digit decimal (11.1.8, as
``excel.round`` reads its operand in 11.1.35). 2.675 is the double
2.67499999999999982..., which reads as 2.67500000000000 -- a half -- so it
is 2.68 at two places under either rule, and 0.285 is 0.28 to the even
neighbour and 0.29 away from zero. The reading is taken by the native
``excel.round`` kernel, which is exact at every magnitude, so the rule
costs three passes of compiled code rather than a chain of expressions.

A negative ``decimals`` rounds to tens, hundreds and coarser steps, as a
spreadsheet's ``ROUND(x, -2)`` does: ``af.face.round(-3)`` is a sum assured
banded to the thousand. A double is read and moved the same way, to a
multiple of ``10**n``; a whole number is moved in whole-number arithmetic,
where it is exact, and one whose answer no ``i64`` holds is refused by name.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Final, cast

import polars as pl

from gaspatchio._dtypes import I64_MAX, I64_MIN
from gaspatchio._semantic.ir import Col
from gaspatchio._semantic.operations import ROUND_OPERATION, ROUNDING_OPERATIONS
from gaspatchio.frame.lowering._polars.once import read_once
from gaspatchio.frame.lowering._polars.validation import (
    WIDE_CARRY_RULE,
    require_valid_rows,
    round_past_i64_refusal,
)
from gaspatchio.frame.lowering.polars import (
    a_flag_read_as_a_number,
    lower_arg,
    lower_arg_read_as_i64,
    register_elementwise,
    register_lowering,
)
from gaspatchio.frame.lowering.rules.maths import (
    in_double_precision,
    sig_figs_window,
    typed_element,
)

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import Call
    from gaspatchio.frame.lowering.context import LoweringContext


for _operation in ROUNDING_OPERATIONS:
    if _operation is not ROUND_OPERATION:
        register_elementwise(_operation.identifier, reads_a_number=True)


# The most places the reading is moved to exactly: 10**22 is the largest power
# of ten a double holds, so past it the step is no double.
_EXACT_PLACES: Final[int] = 22
# Places at which every double is already its own fifteen-digit value.
_EVERY_FIGURE: Final[int] = 400
# Where a fifteen-digit reading sits from a step's half, in steps: a half is
# 0.5 and the nearest reading that is not one is 0.4, and the doubles carry
# less than 0.03 of a step of error below 10**14 steps.
_A_HALF_STEP: Final[float] = 0.45
_HALF_TO_EVEN: Final[str] = "half_to_even"
# The coarsest step a double holds: past ten to the 308th no step is a double,
# and every finite double is less than half of one.
_LARGEST_DECIMAL_POWER: Final[int] = 308
# The coarsest step an i64 holds is ten to the 18th; ten to the 19th is past
# it, and half of it is the one whole number a tie can sit on there.
_I64_STEPS: Final[int] = 18
_I64_HALF_STEP: Final[int] = 5 * 10**18


@register_lowering(ROUND_OPERATION.identifier)
def _lower_round(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Move each value to the nearest step of the size the record names.

    A double -- or a single carried to one -- is moved by its fifteen-digit
    reading at up to 22 places either side of the point and below ``10**37``
    (:func:`_by_its_reading`); from ``10**37`` it is whole and its own answer.
    Past 22 places Polars' own rounding answers, and past 22 places to the
    left of the point the same scaling written out (:func:`_scaled_to_a_step`).
    A whole number is already on every step at or after the point and keeps
    its type; to the left of it, it is moved in whole numbers
    (:func:`_whole_numbers_to_a_step`).
    """
    attrs = dict(node.attrs)
    decimals = int(cast("int", attrs["decimals"]))
    mode = cast("str", attrs["mode"])
    if decimals < 0:
        return _to_a_coarser_step(node, ctx, -decimals, mode)
    value_expr, shape = lower_arg(node.args[0], ctx)
    value_expr = a_flag_read_as_a_number(
        node.args[0], value_expr, shape, ctx, call=f"{node.name}()"
    )
    element = typed_element(node, value_expr, ctx)
    if element in (pl.Float64, pl.Float32) and decimals <= _EXACT_PLACES:
        return in_double_precision(
            value_expr, shape, element, lambda x: _by_its_reading(x, decimals, mode)
        )
    if shape == "list":
        return value_expr.list.eval(
            pl.element().round(decimals, mode=mode)  # type: ignore[arg-type]
        )
    return value_expr.round(decimals, mode=mode)  # type: ignore[arg-type]


def _to_a_coarser_step(
    node: Call, ctx: LoweringContext | None, places: int, mode: str
) -> pl.Expr:
    """Move each value to the nearest multiple of ``10**places``, ``places >= 1``.

    A double is moved by its fifteen-digit reading while the step is a double
    that holds exactly (to ``10**22``); past it, by the scaling written out;
    and past ``10**308``, where no step is a double, every finite value is
    under half a step and answers a nought of its own sign. A whole number is
    moved in whole numbers, a column wider than ``i64`` read as the ``Int64``
    its values fit. A fixed-point decimal is refused by name: Polars' rounding
    takes no step coarser than a unit on one, and its conversion of one to a
    whole number rounds (1.4999 came back 2), so no route through its
    expressions moves one exactly.
    """
    value_expr, shape = lower_arg_read_as_i64(node.args[0], ctx, rule=WIDE_CARRY_RULE)
    value_expr = a_flag_read_as_a_number(
        node.args[0], value_expr, shape, ctx, call=f"{node.name}()"
    )
    element = typed_element(node, value_expr, ctx)
    if element.is_integer():
        column = node.args[0].name if isinstance(node.args[0], Col) else None
        return _whole_numbers_to_a_step(value_expr, shape, places, mode, column)
    if element in (pl.Float64, pl.Float32):
        return in_double_precision(
            value_expr, shape, element, lambda x: _doubles_to_a_step(x, places, mode)
        )
    reason = (
        f"round(decimals=-{places}) moves a value to a multiple of 10**{places}, "
        f"and this value is a {element}: only a double or a whole number is "
        "moved to a step left of the point"
    )
    if isinstance(element, pl.Decimal):
        reason += (
            ", because a fixed-point decimal has no exact route there in this "
            "engine. Carry it as a double first -- (af.value * 1.0).round"
            f"(-{places}) -- which reads it as its fifteen significant figures"
        )
    raise TypeError(reason + ".")


def _doubles_to_a_step(x: pl.Expr, places: int, mode: str) -> pl.Expr:
    """Return a double moved to the nearest multiple of ``10**places``.

    The value is written into the plan once (:func:`read_once`), however
    often the route reads it.
    """
    if places <= _EXACT_PLACES:
        return _by_its_reading(x, -places, mode)
    if places > _LARGEST_DECIMAL_POWER:
        return read_once(
            x, answer=lambda v: pl.when(v.is_finite()).then(v * 0.0).otherwise(v)
        )
    return read_once(x, answer=lambda v: _scaled_to_a_step(v, places, mode))


def _scaled_to_a_step(x: pl.Expr, places: int, mode: str) -> pl.Expr:
    """Return the native scaling past 22 places left of the point.

    The value scaled down by ``10**22`` and by the rest of the step, each the
    double nearest it, rounded to a whole number by the tie rule, and scaled
    back up by the double nearest ``10**places``: three products, which every
    engine computes alike (a quotient by a literal Polars would take as a
    product by its reciprocal). Two factors down, because ``10**-308`` is
    below the least normal double, which an engine may read as nought. An
    answer the scaling carries past the largest double is the value itself.
    """
    first = float(Fraction(1, 10**_EXACT_PLACES))
    rest = float(Fraction(1, 10 ** (places - _EXACT_PLACES)))
    up = float(10**places)
    steps = ((x * first) * rest).round(0, mode=mode)  # type: ignore[arg-type]
    rounded = steps * up
    return pl.when(rounded.is_finite()).then(rounded).otherwise(x)


def _whole_numbers_to_a_step(
    value: pl.Expr, shape: str, places: int, mode: str, column: str | None
) -> pl.Expr:
    """Move whole numbers to the nearest multiple of ``10**places`` exactly.

    Counted in ``Int64``: the steps below, the rest, and a half decided by the
    tie rule. An answer no ``i64`` holds -- 2**63 - 1 to tens is
    9223372036854775810 -- is refused by name rather than wrapped. A narrower
    whole-number type is carried to ``Int64`` first, which holds it exactly.
    """
    message = round_past_i64_refusal(column)
    rounded, fits = _to_a_step_exactly(pl.element().cast(pl.Int64), places, mode)

    def per_period(run: pl.Expr) -> pl.Expr:
        every = run.list.eval(fits).list.all().fill_null(value=True)
        return run.list.eval(rounded) + require_valid_rows(every, message=message)

    def per_policy(one: pl.Expr) -> pl.Expr:
        kept, held = _to_a_step_exactly(one.cast(pl.Int64), places, mode)
        return kept + require_valid_rows(held, message=message)

    # The value is written into the plan once (:func:`read_once`).
    return read_once(value, answer=per_period if shape == "list" else per_policy)


def _to_a_step_exactly(x: pl.Expr, places: int, mode: str) -> tuple[pl.Expr, pl.Expr]:
    """Return ``x`` at its nearest multiple of ``10**places``, and whether it fits.

    The magnitude is read as ``2**63 - 1`` for the least ``i64``, whose own
    has no ``i64``: the two differ in a last digit that never sits on a half
    of any step, so they round alike. Past ``10**18`` the step is no ``i64``:
    at ``10**19`` a value moves to nought, or to the step itself, which no
    ``i64`` holds; past it every value is under half a step.
    """
    magnitude = (
        pl.when(x == I64_MIN).then(pl.lit(I64_MAX, dtype=pl.Int64)).otherwise(x.abs())
    )
    away = mode != _HALF_TO_EVEN
    if places > _I64_STEPS:
        nought = pl.when(x.is_null()).then(x).otherwise(pl.lit(0, dtype=pl.Int64))
        if places > _I64_STEPS + 1:
            return nought, pl.lit(value=True)
        half = pl.lit(_I64_HALF_STEP, dtype=pl.Int64)
        past = (magnitude >= half) if away else (magnitude > half)
        return nought, (~past).fill_null(value=True)
    step = pl.lit(10**places, dtype=pl.Int64)
    count = magnitude // step
    twice_rest = 2 * (magnitude % step)
    tie = twice_rest == step
    up = (twice_rest > step) | (tie if away else tie & (count % 2 == 1))
    kept = count + up.cast(pl.Int64)
    fits = (kept <= pl.lit(I64_MAX // 10**places, dtype=pl.Int64)).fill_null(value=True)
    whole = pl.when(fits).then(kept * step).otherwise(pl.lit(0, dtype=pl.Int64))
    return pl.when(x < 0).then(-whole).otherwise(whole), fits


def _by_its_reading(x: pl.Expr, decimals: int, mode: str) -> pl.Expr:
    """Return a double's fifteen-digit reading moved to ``decimals`` places.

    Away from zero this is ``excel.round`` exactly, and the kernel answers it.
    To the even neighbour the two part company only where the reading is
    exactly a half. There the reading has at most ``decimals + 1`` places, so
    the kernel's answers at one and two more places are the reading itself,
    half a step nearer zero than the answer away from zero. Few values pass
    those two tests, and only they are compared with the reading itself --
    the kernel's slowest path, at a place past every figure -- so a column
    pays for the reading where a tie is possible and nowhere else. On a half
    with an odd count of steps the even neighbour is one step nearer zero,
    and the kernel hands that back as the double nearest it. (A quotient by
    the step would not do: Polars takes a division by a literal as a product
    by its reciprocal.) From ``10**37`` every double is a whole number and is
    its own answer -- Polars' own rounding scales it and can hand back a
    neighbour -- and so are a NaN and an infinity.
    """
    return read_once(x, answer=lambda value: _the_reading_moved(value, decimals, mode))


def _the_reading_moved(x: pl.Expr, decimals: int, mode: str) -> pl.Expr:
    """Return :func:`_by_its_reading` over ``x``, a value written into the plan once."""
    from gaspatchio.frame.lowering._excel.round import (  # noqa: PLC0415
        round as excel_round,
    )

    away = excel_round(x, decimals)
    if mode == _HALF_TO_EVEN:
        # Steps per unit, and the step itself: both doubles that hold exactly
        # on whichever side of the point the step lies.
        per_unit = float(Fraction(10) ** decimals)
        step_size = float(Fraction(10) ** -decimals)
        finer = excel_round(x, decimals + 1)
        maybe = ((away.abs() - finer.abs()) * per_unit > _A_HALF_STEP) & (
            excel_round(x, decimals + 2) == finer
        )
        reading = excel_round(pl.when(maybe).then(x).otherwise(0.0), _EVERY_FIGURE)
        a_half = maybe & (reading == finer)
        odd = (away.abs() * per_unit).round() % 2 == 1
        # A step nearer zero, within a few units of the decimal it stands for,
        # which the kernel hands back as the double nearest that decimal.
        nearer = excel_round(away.abs() - step_size, decimals)
        even = pl.when(x < 0).then(-nearer).otherwise(nearer)
        away = pl.when(a_half & odd).then(even).otherwise(away)
    _, top = sig_figs_window(1)
    return pl.when(x.abs() < top).then(away).otherwise(x)
