# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Arithmetic, and the ten plain maths a projection is written with.

Two clauses in one module because they are one decision: section 11.1.25's
seven operators and section 11.1.12's ten functions are what a formula is
made of, and what governs both is the carrier each value is held in. The
seven are table-driven -- seven near-identical bodies would be seven places
for one rule to drift, and the clone detector reads this tree.

**The integers are the interesting half.** Two ``i64`` operands stay ``i64``
for ``add``, ``sub``, ``mul``, ``floordiv`` and ``mod``, which is what makes
``2**53 - 1 + 2`` come out exact rather than as the nearest double. Every one
of those carries a flag, and a flagged cell refuses at completion rather than
publishing the wrapped answer the hardware produced.

**``div`` always answers a double, and ``pow`` has a domain of its own.**
Both are the clause's own words rather than an engine's convenience.
"""

from __future__ import annotations

import math
from itertools import accumulate
from typing import TYPE_CHECKING, Final

import jax
import jax.numpy as jnp
from jax.scipy.special import ndtr

from gaspatchio.engines.format import BinOp, Call
from gaspatchio_jax.capability import Capability
from gaspatchio_jax.checks import Judgement, flag
from gaspatchio_jax.figures import (
    EXACT_SCALE,
    HELD_FIGURES,
    POWERS_OF_TEN,
    TENS,
    at_or_above,
    held_figures,
)
from gaspatchio_jax.horizon import Aligned, aligned
from gaspatchio_jax.ieee import apart, divided, multiplied
from gaspatchio_jax.lowerings import register, stepwise
from gaspatchio_jax.lowerings.rounding import half_away_from_zero
from gaspatchio_jax.typed import (
    INT64_MAX,
    INT64_MIN,
    JNP_OF,
    Checked,
    DomainRefused,
    Value,
    carried_to,
    checked_abs,
    checked_add,
    checked_floordiv,
    checked_mod,
    checked_mul,
    checked_pow,
    checked_sub,
    promote,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from gaspatchio.engines.format import OpNode
    from gaspatchio_jax.lowerings import Lowering
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Carrier

_ARITHMETIC: Final = "11.1.25"
_PLAIN: Final = "11.1.12"

# The five operations 11.1.25 keeps in i64 when both operands are, and the
# checked implementation of each.
_INTEGER_ARITHMETIC: Final = {
    "add": checked_add,
    "sub": checked_sub,
    "mul": checked_mul,
    "floordiv": checked_floordiv,
    "mod": checked_mod,
}

# The two that are coarse and are re-judged on the host, and under which name.
_COARSE: Final[dict[str, Judgement]] = {"mul": "mul", "pow": "pow"}

# 11.1.25's integer power promise.
_EXPONENT_FLOOR: Final = 0
_EXPONENT_CEILING: Final = 2**32 - 1

# The carriers arithmetic states a meaning over: 11.1.25's ``i64`` and
# ``f64``, and a Boolean, which "reads as the 0 or 1 it indicates" -- per
# period and per policy alike, the answer ``f64`` whatever the other operand
# is. A date or a text operand is not arithmetic in this vocabulary and
# refuses by name. The Boolean arrives by two doors: a column or a literal
# the record types ``bool``, and 11.1.26's comparison used as an operand,
# which has no declared type for the operand domain to read and reaches the
# lowering as a ``bool`` carrier. Both are carried to f64 below **whether
# one operand is Boolean or both are**: deciding it by whether an f64 happened
# to be standing beside it would make ``(a < b) + (a <= b)`` answer 1.0 where
# the clause answers 2.0. What 11.1.25 does not admit is a per-policy flag on
# both sides of one operation (:func:`_refuse_two_flags_per_policy`).
_ARITHMETIC_OPERANDS: Final[frozenset[Carrier]] = frozenset({"i64", "f64", "bool"})

# The registrations' sentence for that one exclusion, carried beside the
# status where the coverage manifest states the operand domain.
_TWO_FLAGS_NOTE: Final = (
    "a Boolean reads as its 0.0 or 1.0, and a per-policy Boolean on both sides "
    "of one operation is refused"
)

# A comparison used as an operand is 11.1.26's indicator, not a flag.
_COMPARISONS: Final = frozenset({"lt", "le", "gt", "ge", "eq", "ne"})

# 11.1.12's operand domain: a number, and a flag read as the 0.0 or 1.0 it
# indicates, as 11.1.25 reads one -- a stored Boolean or a comparison written
# as the operand, per policy as per period. Each lowering carries a Boolean to
# a double first, so every one of the ten answers ``f64`` over a flag.
_PLAIN_OPERANDS: Final[frozenset[Carrier]] = frozenset({"i64", "f64", "bool"})


def _as_double(value: Value) -> Value:
    """Return one operand as a double, checking what the widening costs."""
    return carried_to(value, "f64", clause=_ARITHMETIC)


def _numeric_operands(left: Value, right: Value, name: str) -> tuple[Value, Value]:
    """Return the two operands ready to compute, refusing what the clause excludes.

    A Boolean on either side is 11.1.26's stored indicator and is carried to
    ``f64`` before anything is promoted -- both of them where both are
    Boolean, so that the answer is a number rather than a truth value the
    integer path has no arithmetic for.
    """
    for operand in (left, right):
        if operand.carrier not in _ARITHMETIC_OPERANDS:
            raise DomainRefused(
                what=(
                    f"{name} met a {operand.carrier} operand, and the arithmetic "
                    "domain is i64 and f64"
                ),
                move=(
                    "convert the operand first, so the record carries the "
                    "conversion the model made"
                ),
                clause=_ARITHMETIC,
            )
    carried = tuple(
        _as_double(operand) if operand.carrier == "bool" else operand
        for operand in (left, right)
    )
    return promote(carried[0], carried[1], clause=_ARITHMETIC)


def _a_flag_per_policy(node: OpNode, value: Value) -> bool:
    """Say whether one arithmetic operand is a flag held once per policy.

    A Boolean column, literal, logical operation or conditional is a flag; a
    comparison written as the operand is 11.1.26's 0/1 indicator, a number,
    as the reference producer reads it. A per-period flag is a run and is
    admitted on either side.
    """
    if value.carrier != "bool" or value.shape != "scalar":
        return False
    written = (
        node.op
        if isinstance(node, BinOp)
        else node.name
        if isinstance(node, Call)
        else None
    )
    return written not in _COMPARISONS


def _refuse_two_flags_per_policy(call: Call, left: Value, right: Value) -> None:
    """Refuse 11.1.25's one excluded Boolean form: a per-policy flag on both sides.

    "A per-policy Boolean on both sides of one operation is not admitted." The
    reference producer refuses the line where it is written, so no record it
    writes carries one; a document that does is refused here by the clause's
    own sentence rather than answered in a type no formula wrote.
    """
    if not (
        _a_flag_per_policy(call.args[0], left)
        and _a_flag_per_policy(call.args[1], right)
    ):
        return
    raise DomainRefused(
        what=(
            f"{call.name} is written over a flag on both sides, one value per "
            "policy, and arithmetic between two per-policy flags is not admitted"
        ),
        move=(
            "write one of them as the amount it stands for, "
            "when(flag).then(1.0).otherwise(0.0), or the logical operator the "
            "line means"
        ),
        clause=_ARITHMETIC,
    )


def _integer(name: str, axis: Aligned, dtype: str) -> Value:
    """Return the integer answer, with every defect of it flagged."""
    a, b = axis.arrays
    checked: Checked = _INTEGER_ARITHMETIC[name](a, b)
    coarse = name == "mul"
    flag(
        "i64.range",
        checked.overflow,
        judgement=_COARSE["mul"] if coarse else None,
        operands=(a, b) if coarse else (),
    )
    if checked.zero_divisor is not None:
        flag("floordiv.zero_divisor", checked.zero_divisor)
    return Value(checked.result, "i64", axis.shape, dtype, axis.horizon)


def _double(name: str, axis: Aligned, dtype: str, *, flagged: bool = False) -> Value:
    """Return the floating-point answer, under 11.1.25's float clause.

    ``div``, ``floordiv`` and ``mod`` are each one IEEE operation per element,
    rounded where the clause rounds, whatever the divisor is -- a literal, a
    per-policy value spread over the periods, a per-period list -- which is
    the reference producer's own arithmetic: ``floor(a / b)`` and
    ``a - b * floor(a / b)``, every step in binary64.
    """
    a, b = axis.arrays
    if name == "add":
        result = a + b
    elif name == "sub":
        result = a - b
    elif name == "mul":
        if flagged:
            # A flag is its 0.0 or 1.0, and XLA rewrites a product by a
            # converted truth value into a selection of the other operand or
            # a constant +0.0 -- which drops the sign of a -0.0 the product
            # keeps, and so the sign of the infinity a division by it gives.
            # Each operand is held apart under the other, NaN wherever the
            # product is NaN, so the rewrite has no form to match.
            a, b = apart(a, b), apart(b, a)
        # Rounded before whatever reads it: a product feeding a sum would fuse
        # into one multiply-add, and a threshold after it would move a whole
        # step: gaspatchio_jax.ieee.
        result = multiplied(a, b)
    else:
        # One IEEE division, held apart from every rewrite of its form -- the
        # reciprocal of a literal, a quotient of a quotient: gaspatchio_jax.ieee.
        quotient = divided(a, b)
        if name == "div":
            result = quotient
        elif name == "floordiv":
            result = jnp.floor(quotient)
        else:
            # The clause's remainder, not the library's: ``jnp.remainder`` is
            # the exact remainder a language computes, and 11.1.25 states the
            # rounded one -- ``1.0 % 0.1`` is ``0.0`` here, where the exact
            # remainder is ``0.09999999999999995``. A zero divisor makes the
            # quotient infinite and the product NaN, so the answer is NaN, as
            # the clause states. The product is held apart too, or the
            # compiler fuses it and the subtraction into one multiply-add that
            # rounds once where the clause rounds twice; and so is the
            # divisor in it, or a literal nought times anything is folded to
            # nought and the stated NaN becomes the dividend. A NaN quotient
            # makes the product NaN, so the quotient is both witnesses. The
            # dividend is held apart as well: written as a product, ``t * 12``,
            # it would fuse with this subtraction just the same, and the
            # remainder of month 13 would be 0 (audit C2-F3). The quotient is
            # NaN wherever the dividend is, so the witness changes no number.
            whole = apart(b, quotient) * jnp.floor(quotient)
            result = apart(a, quotient) - apart(whole, quotient)
    return Value(result, "f64", axis.shape, dtype, axis.horizon)


def _power(left: Value, right: Value, axis: Aligned, dtype: str) -> Value:
    """Return the power, under 11.1.25's narrower type and shape promise."""
    a, b = axis.arrays
    if dtype == "i64":
        outside = (b < _EXPONENT_FLOOR) | (b > _EXPONENT_CEILING)
        flag("pow.integer_exponent", outside)
        checked = checked_pow(a, jnp.maximum(b, 0))
        flag(
            "i64.range",
            checked.overflow,
            judgement=_COARSE["pow"],
            operands=(a, b),
        )
        return Value(checked.result, "i64", axis.shape, dtype, axis.horizon)
    if left.shape == "scalar" and right.shape == "list":
        _refuse_a_negative_scalar_base(left)
    base = _as_double(left)
    exponent = _as_double(right)
    doubled = aligned(base, exponent)
    return Value(
        doubled.arrays[0] ** doubled.arrays[1],
        "f64",
        doubled.shape,
        dtype,
        doubled.horizon,
    )


def _refuse_a_negative_scalar_base(left: Value) -> None:
    """Flag 11.1.25's one excluded power, by the clause's own sentence.

    "A negative scalar base against a list exponent is explicitly outside this
    contract, including when every exponent is integral." A per-policy base
    below zero raised to a per-period exponent is the case, and the producer's
    own guarded logarithmic path answers a run of nulls there -- so a number
    from this engine would be a number the reference has no value for.
    """
    flag("pow.list_exponent_sign", left.array < 0)


# What each of 11.1.25's seven owes. ``pow`` carries two more than the rest:
# the exponent domain the integer clause promises, and the one power the
# clause puts outside itself -- a negative per-policy base against a
# per-period exponent.
_CHECKS_OF: Final[dict[str, tuple[str, ...]]] = {
    name: (
        ("i64.range", "mixed.2p53", "floordiv.zero_divisor")
        if name in ("floordiv", "mod")
        else (
            (
                "i64.range",
                "mixed.2p53",
                "pow.integer_exponent",
                "pow.list_exponent_sign",
            )
            if name == "pow"
            else ("i64.range", "mixed.2p53")
        )
    )
    for name in ("add", "sub", "mul", "div", "floordiv", "mod", "pow")
}


def _binary(name: str) -> Lowering:
    """Return the lowering for one of 11.1.25's seven operators, in steps.

    Both operands first, left then right, and then the clause -- so a sum of
    a few hundred terms is lowered from the plan's own stack, not one Python
    call inside the next (``gaspatchio_jax.lowerings``).
    """

    def steps(call: Call, ctx: LoweringContext) -> Generator[OpNode, Value, Value]:
        left = yield call.args[0]
        right = yield call.args[1]
        _refuse_two_flags_per_policy(call, left, right)
        flagged = "bool" in (left.carrier, right.carrier)
        left, right = _numeric_operands(left, right, name)
        dtype, _ = ctx.infer(call, (left, right))
        if name == "pow":
            return _power(left, right, aligned(left, right), dtype)
        if dtype == "i64" and name in _INTEGER_ARITHMETIC:
            return _integer(name, aligned(left, right), dtype)
        return _double(
            name,
            aligned(_as_double(left), _as_double(right)),
            dtype,
            flagged=flagged,
        )

    return stepwise(steps)


for _name in ("add", "sub", "mul", "div", "floordiv", "mod", "pow"):
    register(
        Capability(
            identifier=_name,
            arity=(2,),
            carriers=(_ARITHMETIC_OPERANDS, _ARITHMETIC_OPERANDS),
            alone_per_policy="bool",
            checks=_CHECKS_OF[_name],
            note=_TWO_FLAGS_NOTE,
        )
    )(_binary(_name))


# What each of the seven answers at a flag's 1.0 and at its 0.0, each the
# double nearest the value: e, ln 2 and Phi(1) are the three that are not
# whole. A flag is one of two numbers, so a call over one is one of two
# numbers, and they are written here rather than computed by XLA's CPU
# routines, whose exp lands a place above e at 1.0 on Linux, where the
# producer answers e.
_AT_A_FLAG: Final[dict[str, tuple[float, float]]] = {
    "sqrt": (1.0, 0.0),
    "cbrt": (1.0, 0.0),
    "exp": (2.718281828459045, 1.0),
    "log": (0.0, -math.inf),
    "log10": (0.0, -math.inf),
    "log1p": (0.6931471805599453, 0.0),
    "norm_cdf": (0.8413447460685429, 0.5),
}


def _unary_double(name: str) -> Lowering:
    """Return the lowering for one of the transcendentals or the two roots.

    ``norm_cdf`` is XLA's ``ndtr``: Φ in the complementary form, which keeps
    the lower tail's digits where ``0.5 * (1 + erf(x / sqrt 2))`` loses them,
    and answers 1.0 and 0.0 at the two infinities as 11.1.12 states. Over a
    flag the call answers one of its two values at 1.0 and 0.0.
    """
    functions = {
        "sqrt": jnp.sqrt,
        "cbrt": jnp.cbrt,
        "exp": jnp.exp,
        "log": jnp.log,
        "log10": jnp.log10,
        "log1p": jnp.log1p,
        "norm_cdf": ndtr,
    }

    def lowering(call: Call, ctx: LoweringContext) -> Value:
        lowered = ctx.lower(call.args[0])
        if lowered.carrier == "bool":
            one, nought = _AT_A_FLAG[name]
            return Value(
                jnp.where(lowered.array, jnp.float64(one), jnp.float64(nought)),
                "f64",
                lowered.shape,
                "f64",
                lowered.horizon,
            )
        operand = _as_double(lowered)
        return Value(
            functions[name](operand.array), "f64", operand.shape, "f64", operand.horizon
        )

    return lowering


for _name in ("sqrt", "cbrt", "exp", "log", "log10", "log1p", "norm_cdf"):
    register(
        Capability(
            identifier=_name,
            arity=(1,),
            carriers=(_PLAIN_OPERANDS,),
            answers_carrier="f64",
            clause=_PLAIN,
        )
    )(_unary_double(_name))


@register(
    Capability(
        identifier="abs",
        arity=(1,),
        carriers=(_PLAIN_OPERANDS,),
        checks=("i64.range",),
        clause=_PLAIN,
    )
)
def _abs(call: Call, ctx: LoweringContext) -> Value:
    """Return the value with its sign dropped, in the carrier it arrived in."""
    operand = ctx.lower(call.args[0])
    if operand.carrier == "i64":
        checked = checked_abs(operand.array)
        flag("i64.range", checked.overflow)
        return Value(checked.result, "i64", operand.shape, "i64", operand.horizon)
    doubled = _as_double(operand)
    return Value(jnp.abs(doubled.array), "f64", doubled.shape, "f64", doubled.horizon)


@register(
    Capability(
        identifier="sign", arity=(1,), carriers=(_PLAIN_OPERANDS,), clause=_PLAIN
    )
)
def _sign(call: Call, ctx: LoweringContext) -> Value:
    """Return which way the value points: minus one, zero, or one."""
    operand = ctx.lower(call.args[0])
    if operand.carrier == "i64":
        return Value(
            jnp.sign(operand.array), "i64", operand.shape, "i64", operand.horizon
        )
    doubled = _as_double(operand)
    return Value(jnp.sign(doubled.array), "f64", doubled.shape, "f64", doubled.horizon)


@register(
    Capability(
        identifier="round_sig_figs",
        arity=(1,),
        carriers=(_PLAIN_OPERANDS,),
        attr_bounds={"digits": (1, None)},
        checks=("i64.range",),
        clause=_PLAIN,
    )
)
def _round_sig_figs(call: Call, ctx: LoweringContext) -> Value:
    """Return the leading significant figures, a tie going away from zero.

    Section 11.1.12 states the tie rule rather than making it an attribute,
    and states it as away from zero for either sign -- which is not what most
    host languages do, so the arithmetic is written out rather than delegated.
    A double's figures are a spreadsheet's: the fifteen-digit decimal it is
    read as, kept to ``digits`` figures (:func:`_decimal_sig_figs`). Below the
    magnitudes that reading is exact at, and from ``10**37``, the engine's
    native scaling answers (:func:`_native_sig_figs`), as the reference
    producer's does: a floating-point residue where nought was meant rounds,
    rather than stopping a run.
    """
    read = ctx.lower(call.args[0])
    digits = int(dict(call.attrs).get("digits", 1) or 1)
    if read.carrier == "i64":
        return Value(
            _whole_sig_figs(read.array, digits),
            "i64",
            read.shape,
            read.dtype,
            read.horizon,
        )
    operand = _as_double(read)
    inside, kept = _decimal_sig_figs(operand.array, digits)
    answer = jnp.where(inside, kept, _native_sig_figs(operand.array, digits))
    return Value(
        answer.astype(JNP_OF["f64"]),
        "f64",
        operand.shape,
        operand.dtype,
        operand.horizon,
    )


# The reference producer's exact window for f figures: from 10**(f - 23) to
# below 10**37, each bound the least double at or above its power of ten.
_WINDOW_TOP: Final[float] = at_or_above(37)
_WINDOW_BOTTOM: Final[dict[int, float]] = {
    figures: at_or_above(figures - 1 - EXACT_SCALE)
    for figures in range(1, HELD_FIGURES + 1)
}


def _decimal_sig_figs(values: jax.Array, digits: int) -> tuple[jax.Array, jax.Array]:
    """Return where a double's figures are kept exactly, and the double kept so.

    The reference producer's steps, element by element. The value is read as
    its fifteen-significant-digit decimal, a sixteenth digit of 5 or more
    going away from zero (11.1.35, :func:`gaspatchio_jax.figures.held_figures`),
    that decimal is kept to ``digits`` figures, a half going away from zero
    (11.1.12), and the answer is the double nearest the result: 0.15 to one
    figure is 0.2, 781098.0 is 800000.0. The rest is whole-number arithmetic
    and one correctly rounded product or quotient by a power of ten a double
    holds. The first array is false outside the producer's window -- from
    ``10**(digits - 23)`` (``10**-8`` at fifteen figures or more) to below
    ``10**37`` -- where the caller answers by the native route instead.
    """
    figures = min(digits, HELD_FIGURES)
    low, high = _WINDOW_BOTTOM[figures], _WINDOW_TOP
    tens = jnp.asarray(TENS, dtype=jnp.float64)
    magnitude = jnp.abs(values)
    usable = jnp.isfinite(magnitude) & (magnitude > 0)
    within = (magnitude >= low) & (magnitude < high)
    held, k = held_figures(jnp.where(usable & within, magnitude, 1.0))
    cut = HELD_FIGURES + (held >= 10**HELD_FIGURES).astype(jnp.int64) - figures
    powers = jnp.asarray(POWERS_OF_TEN, dtype=jnp.int64)
    step = powers[cut]
    kept = held // step + (2 * (held % step) >= step).astype(jnp.int64)
    place = cut - k
    beyond = jnp.maximum(place - EXACT_SCALE, 0)
    answer = jnp.where(
        place >= 0,
        (kept * powers[beyond]).astype(jnp.float64)
        * tens[jnp.clip(place, 0, EXACT_SCALE)],
        divided(kept.astype(jnp.float64), tens[jnp.clip(-place, 0, EXACT_SCALE)]),
    )
    signed = jnp.where(values < 0, -answer, answer)
    return ~usable | within, jnp.where(usable, signed, values)


# The least normal double: below it the compiled logarithm reads a value as nought.
_LEAST_NORMAL: Final[float] = 2.0**-1022
# 10.0 squared and squared again, each square rounded, as an integer power of
# a double is taken by repeated squaring: 10**1, 10**2, 10**4, ... 10**256.
_SQUARES: Final[tuple[float, ...]] = tuple(
    accumulate(range(8), lambda square, _: square * square, initial=10.0)
)


def _power_of_ten(places: jax.Array) -> jax.Array:
    """Return ``10.0`` to the whole power ``places`` as Polars computes it.

    Polars raises ten to a whole power by repeated squaring, the bits of the
    power from the lowest, and a negative power as the reciprocal of the
    positive one -- so its ``10**-30`` is not the double nearest ``10**-30``.
    The native route answers as Polars' does only where its scale is the
    same double, so the scale is taken the same way here.
    """
    count = jnp.abs(places)
    raised = jnp.ones_like(places, dtype=jnp.float64)
    for bit, square in enumerate(_SQUARES):
        raised = jnp.where((count >> bit) & 1 == 1, raised * square, raised)
    return jnp.where(places < 0, apart(divided(1.0, raised), raised), raised)


def _native_sig_figs(values: jax.Array, digits: int) -> jax.Array:
    """Return the figures by binary64 scaling: the engines' route outside the window.

    ``round(x * 10**k) / 10**k``, a half away from zero, ``10**k`` taken as
    Polars takes it (:func:`_power_of_ten`), and the division held apart, or
    the compiler rewrites a division by a power as a product by the opposite
    power. ``10**k`` is not a double past ``k = 22``, so this lands a few units
    in the last place from the fifteen-digit reading, and on the other side of
    a half where the value is within a few units of one; a value whose scaling
    leaves the finite range is its own answer, and so is a subnormal one,
    whose logarithm the compiled code does not take (it reads it as nought).
    """
    normal = jnp.abs(values) >= _LEAST_NORMAL
    magnitude = jnp.where(normal, jnp.abs(values), 1.0)
    places = digits - 1 - jnp.floor(jnp.log10(magnitude)).astype(jnp.int64)
    factor = _power_of_ten(places)
    rounded = divided(half_away_from_zero(values * factor), factor)
    return jnp.where(
        ~normal | ~jnp.isfinite(values) | ~jnp.isfinite(rounded), values, rounded
    )


def _whole_sig_figs(values: jax.Array, digits: int) -> jax.Array:
    """Keep a whole number's leading figures in whole-number arithmetic.

    Through a double the figures came back wrong well inside the range a
    double names -- 781,098 to one figure was 799,999 -- so they are counted
    and the rest cut off in ``int64``, a tie going away from zero (section
    11.1.12), and the answer is the producer's exactly. The least ``i64``
    is read by the magnitude of the greatest, which differs from its own
    only in a last digit no rounding turns on. An answer that rounds up past
    ``i64`` is flagged rather than wrapped.
    """
    magnitude = jnp.where(values == INT64_MIN, INT64_MAX, jnp.abs(values))
    figures = 1 + sum(
        (magnitude >= POWERS_OF_TEN[place]).astype(jnp.int64) for place in range(1, 19)
    )
    cut = jnp.maximum(figures - digits, 0)
    step = jnp.asarray(POWERS_OF_TEN, dtype=jnp.int64)[cut]
    kept = magnitude // step + (2 * (magnitude % step) >= step).astype(jnp.int64)
    fits = kept <= INT64_MAX // step
    flag("i64.range", ~fits)
    whole = jnp.where(fits, kept * step, 0)
    return jnp.where(cut == 0, values, jnp.where(values < 0, -whole, whole))
