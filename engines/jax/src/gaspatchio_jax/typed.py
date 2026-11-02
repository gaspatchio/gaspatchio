# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every value in the type the node record declares, and integers that refuse.

This replaced a float64 carrier for everything: an ``i64`` node
computes in int64, an ``f64`` node in float64, a date as a count of days, a
Boolean as a Boolean, text as an interned code. The reason is one witness: a
float carrier loses an integer inside its own check.
``2**53 - 1 + 2`` is exactly ``2**53 + 1``, a number float64 cannot hold, so
an engine that added it as a float would answer ``2**53`` and then pass its
own range check with the wrong number in hand.

**Promotion happens where the specification states it and nowhere else.**
Section 11.1.25 keeps two ``i64`` operands in ``i64`` for ``add``, ``sub``,
``mul``, ``floordiv`` and ``mod``; an ``f64`` operand promotes; ``div``
always answers ``f64``. The ±2⁵³ check applies at that mixed boundary --
where the clause names it -- and not to a calculation that stayed integral,
which is what lets a pure-integer model be exact at the signed endpoints.

**Integers refuse rather than wrap.** The wrapping the hardware does is not a
portable answer and section 11.1.25 says so outright. Every integer operation
here hands back its result *and* a flag: exact where an exact test is cheap
in the trace, coarse where it is not. A coarse flag is an over-approximation
and never an under-approximation, and the cells it catches are re-judged on
the host with Python integers, which have no range at all -- so the coarse
test costs a little work at completion and gives up no correctness. The two
that are coarse are ``mul`` and ``pow``, where an exact in-trace test would
need a product wider than the type the product is in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, NamedTuple

import jax.numpy as jnp

from gaspatchio.engines.format import Lit

from .checks import flag

if TYPE_CHECKING:
    from collections.abc import Container, Sequence

    import jax
    from jax.typing import DTypeLike

    from gaspatchio.engines.report import Group

    from .horizon import Horizon

__all__ = [
    "CARRIER_OF_DTYPE",
    "COARSE_PRODUCT",
    "EXACT_IN_DOUBLE",
    "INT64_MAX",
    "INT64_MIN",
    "JNP_OF",
    "PAST_I64_LITERAL_MOVE",
    "Carrier",
    "Checked",
    "DomainRefused",
    "Shape",
    "Value",
    "carried_to",
    "cell_of",
    "checked_abs",
    "checked_add",
    "checked_floordiv",
    "checked_mod",
    "checked_mul",
    "checked_neg",
    "checked_pow",
    "checked_sub",
    "promote",
    "require_carrier",
]

# What a value is held in inside the trace. ``date`` is a count of days from
# 1970-01-01 and ``code`` is an interned text code; both are integers to XLA
# and neither is an integer to this vocabulary, which is why they are carriers
# of their own rather than ``i64`` with a note beside it.
Carrier = Literal["f64", "i64", "bool", "date", "code"]
Shape = Literal["scalar", "list"]

# The dtype each carrier is held in, as XLA's calls take it. Typed by what the
# calls accept rather than by what the names are: JAX's stubs have spelled
# ``jnp.float64`` as ``Any`` and as a scalar type of their own, and both are a
# DTypeLike.
JNP_OF: Final[dict[Carrier, DTypeLike]] = {
    "f64": jnp.float64,
    "i64": jnp.int64,
    "bool": jnp.bool_,
    "date": jnp.int64,
    "code": jnp.int32,
}

# The artifact's own type names, and the carrier each is held in. Section 10's
# five scalar types; a list type is the same carrier under a list shape.
CARRIER_OF_DTYPE: Final[dict[str, Carrier]] = {
    "f64": "f64",
    "i64": "i64",
    "bool": "bool",
    "date": "date",
    "str": "code",
}

# How a per-period type writes itself in section 10's vocabulary.
_LIST: Final[str] = "list["


def cell_of(dtype: str) -> Carrier | None:
    """Return the carrier one declared type's cells are held in.

    ``list[f64]`` is an ``f64`` per period, and what it is held in is what an
    ``f64`` is held in. The shape is a separate question, asked separately,
    because an operand domain that ran the two together would have five
    carriers become ten and every registration state both twice.
    """
    named = dtype[len(_LIST) : -1] if dtype.startswith(_LIST) else dtype
    return CARRIER_OF_DTYPE.get(named)


INT64_MIN: Final[int] = -(2**63)
INT64_MAX: Final[int] = 2**63 - 1

# The move a whole-number literal past that range is refused with, whether it
# stands on its own or as a member of a band: section 10 carries a whole
# number as an i64, so the record holds no such literal, and what the author
# meant is one of two things the vocabulary can say.
PAST_I64_LITERAL_MOVE: Final[str] = (
    "if the value is an identifier, compare its digits as text, through "
    "to_text(); if it is a quantity, write it as a decimal literal where its "
    "magnitude matters and its last digits do not"
)

# 11.1.38's interval: where the doubles stop being closer together than one.
EXACT_IN_DOUBLE: Final[int] = 2**53


def outside_double_exact(values: jax.Array) -> jax.Array:
    """Test the signed bounds without overflowing at the smallest i64."""
    return (values < -EXACT_IN_DOUBLE) | (values > EXACT_IN_DOUBLE)


def outside_integer_conversion(values: jax.Array) -> jax.Array:
    """Return cells an explicit float-to-integer conversion cannot carry."""
    return (
        ~jnp.isfinite(values)
        | (jnp.floor(values) != values)
        | (values < INT64_MIN)
        | (values >= -float(INT64_MIN))
    )


def outside_stored_predicate(values: jax.Array) -> jax.Array:
    """Return stored indicators that state neither false nor true."""
    return ~jnp.isin(values, jnp.asarray([0.0, 1.0]))


def outside_prospective_rate(values: jax.Array) -> jax.Array:
    """Return rates outside the prospective-value domain."""
    return values <= -1


# 11.1.25's integer power promise: two integers answer an integer only for an
# exponent in [0, 2**32 - 1].
INTEGER_EXPONENTS: Final = range(2**32)


def arithmetic_carrier(
    name: str,
    carriers: Sequence[Carrier | None],
    *,
    per_period: bool,
    exponent: int | None = None,
) -> Carrier | None:
    """Share numeric promotion between preparation and the actual lowering.

    Division and per-period power return doubles even with integer operands.
    A Boolean arithmetic operand supplies a double indicator under §11.1.26.
    Unknown metadata stays unknown unless the operation fixes the result type.

    So does a power whose exponent is written as an integer outside 11.1.25's
    integer promise -- ``a ** -1`` is ``1 / a`` -- because the record holds
    that exponent and the reference producer answers it in binary64:
    ``exponent`` is that literal (:func:`written_exponent`), or None.
    """
    past_the_promise = exponent is not None and exponent not in INTEGER_EXPONENTS
    if (
        name == "div"
        or (name == "pow" and (per_period or past_the_promise))
        or any(carrier in {"f64", "bool"} for carrier in carriers)
    ):
        return "f64"
    return "i64" if all(carrier == "i64" for carrier in carriers) else None


def written_exponent(name: str, arguments: Sequence[object]) -> int | None:
    """Return the exponent a power writes as an integer literal, or None."""
    if name != "pow" or len(arguments) != 2:  # noqa: PLR2004 -- base and exponent
        return None
    exponent = arguments[1]
    if isinstance(exponent, Lit) and type(exponent.value) is int:
        return exponent.value
    return None


# The threshold the product flag is coarse at. Below it no product of two
# int64 values can have left the range, so a cell under it needs no second
# look; above it the cell is re-judged on the host with Python integers.
COARSE_PRODUCT: Final[int] = 2**62

# How many bits of an exponent the integer power walks. An int64 exponent
# outside [0, 2**32-1] is outside 11.1.25's integer promise and refuses before
# this is reached, so 32 passes cover every exponent the clause admits.
_EXPONENT_BITS: Final[int] = 32

# The order the numeric carriers promote in: a Boolean joins an integer, an
# integer joins a double. Text and dates are not on this ladder at all.
_NUMERIC_RANK: Final[dict[Carrier, int]] = {"bool": 0, "i64": 1, "f64": 2}


class DomainRefused(Exception):  # noqa: N818 -- a refusal, in this framework's word
    """An invocation outside the domain this vocabulary states for it.

    Carries the sentence and the clause rather than a code: the report the
    caller builds needs both, and an exception that carried only a name would
    have the caller inventing the words a second time.

    **The group and the count travel with it where the refusal has them.** A
    refusal met while lowering is ordinarily about the tree -- the types the
    records declare, knowable with no book at all -- and that is the default.
    But a key the basis does not carry is a refusal about *values*, and which
    group it belongs in is the question of when it became knowable: before
    anything was compiled, where every key arrived with the book, and only at
    the end where a calculation produced one. The lowering that knows which
    says so here rather than leaving the report to guess.
    """

    def __init__(
        self,
        what: str,
        move: str,
        clause: str,
        *,
        group: Group = "tree",
        count: int | None = None,
    ) -> None:
        """Carry what was met, what to do about it, and where it is stated."""
        super().__init__(what)
        self.what = what
        self.move = move
        self.clause = clause
        self.group = group
        self.count = count


@dataclass(frozen=True, slots=True)
class Value:
    """One column of a run: the numbers, what they are, and what shape they are.

    Attributes:
        array: ``[B]`` for a per-policy value, ``[B, bucket]`` for a
            per-period one.
        carrier: What the numbers are held in.
        shape: Per policy or per period, in the artifact's own two words.
        dtype: The type the node record declares for a graph node, or the type
            the operation contract infers for a nested call.
        horizon: Where each policy's own timeline stops, for a per-period
            value, and None for a per-policy one. **On the value and not on
            the run**, because one document carries per-period columns of
            more than one length: section 11.1.37 gives a boundary sequence
            ``T + 1`` cells and the period values beside it ``T``, and a run
            holding one horizon would be padding one of the two against the
            other's count.
        unknown: For a truth value, the cells that have none -- a comparison
            one of whose operands was NaN (11.1.26) -- in ``array``'s own
            shape, and None where every cell has one. ``array`` holds an
            arbitrary truth value there. A double read from it is NaN there
            (:func:`carried_to`); anything that would need a null instead
            refuses, this engine carrying none.
        unknown_is_null: Whether the ``unknown`` cells are nulls rather than
            the unknown of a NaN comparison. A per-policy ``&``, ``|`` or ``~``
            result is a Boolean wherever it is read (11.1.27): where a side had
            no truth value it is a null, which an enclosing ``&`` or ``|``
            reads under three-valued logic and a ``when`` reads as a null
            condition. Anything that would carry the null on refuses, this
            engine carrying none.

    """

    array: jax.Array
    carrier: Carrier
    shape: Shape
    dtype: str
    horizon: Horizon | None = None
    unknown: jax.Array | None = None
    unknown_is_null: bool = False


class Checked(NamedTuple):
    """An integer result and what was wrong with it, per cell.

    Attributes:
        result: The value, valid wherever neither flag is set.
        overflow: Cells whose answer is outside ``i64``. Exact for every
            operation but ``mul`` and ``pow``, where it is the coarse flag the
            module docstring describes and the host re-judges.
        zero_divisor: Cells whose divisor was zero, for the two operations
            that have one, and None for the rest.

    """

    result: jax.Array
    overflow: jax.Array
    zero_divisor: jax.Array | None = None


def carried_to(value: Value, carrier: Carrier, *, clause: str) -> Value:
    """Return ``value`` in ``carrier``, checking what the conversion costs.

    The one conversion that can lose something is an integer to a double past
    ±2⁵³, and that is the boundary 11.1.25 names its check at. A Boolean to
    either number is the indicator 11.1.26 states; every other pairing is
    refused rather than guessed.
    """
    if value.carrier == carrier:
        return value
    if value.carrier == "i64" and carrier == "f64":
        flag("mixed.2p53", outside_double_exact(value.array))
        return Value(
            value.array.astype(JNP_OF["f64"]),
            "f64",
            value.shape,
            _named(carrier),
            value.horizon,
        )
    if value.carrier == "bool" and carrier in ("i64", "f64"):
        array = value.array.astype(JNP_OF[carrier])
        if value.unknown is not None:
            # 11.1.26: a truth value a NaN left unknown is a NaN indicator; a
            # whole number holds no NaN, and its null this engine does not
            # carry. A per-policy logical result is a null there (11.1.27),
            # read as a number too.
            if carrier == "f64" and not value.unknown_is_null:
                array = jnp.where(value.unknown, jnp.nan, array)
            else:
                flag("comparison.unknown", value.unknown)
        return Value(array, carrier, value.shape, _named(carrier), value.horizon)
    raise DomainRefused(
        what=(
            f"a {value.carrier} value cannot be carried to {carrier}: this "
            "vocabulary states no conversion between them"
        ),
        move=(
            "write the conversion you mean -- to_float, to_integer or to_text "
            "-- so the record says which one the model made"
        ),
        clause=clause,
    )


def require_carrier(
    value: Value, admitted: Container[Carrier], identifier: str, clause: str
) -> Value:
    """Return ``value`` where its carrier is admitted, and refuse it where not.

    The one place a declared operand domain is enforced at run time. A
    capability that states a domain and a lowering that does not hold to it
    would be two answers to one question -- and the coverage table, which is
    generated from the first, would be describing the second.
    """
    if value.carrier in admitted:
        return value
    raise DomainRefused(
        what=(
            f"{identifier} was written over a {value.carrier} value, which is "
            "outside the domain this clause states for it"
        ),
        move="convert the operand first, so the record carries the conversion",
        clause=clause,
    )


def _named(carrier: Carrier) -> str:
    """Return the artifact's type name for a carrier, for a nested value."""
    for name, held in CARRIER_OF_DTYPE.items():
        if held == carrier:
            return name
    raise KeyError(carrier)  # pragma: no cover -- the table above is total


def a_flag_beside_a_whole_number(left: Carrier | None, right: Carrier | None) -> bool:
    """Say whether two branches are a flag and a whole number, in either order.

    Section 11.1.28 answers that pair as a double, the flag read as the 0.0
    or 1.0 indicator 11.1.25 reads it as beside a number in arithmetic, so
    the pair takes the double carrier rather than the integer one
    :func:`promote` would give two numbers of those ranks.
    """
    return {left, right} == {"bool", "i64"}


def promote(left: Value, right: Value, *, clause: str) -> tuple[Value, Value]:
    """Return the two operands in one carrier, as 11.1.25's clause states it.

    Two integers stay integers. A double on either side promotes the other,
    and that is where the ±2⁵³ check lives. Dates promote only with dates and
    codes only with codes -- there is no ordering between text and a number
    and no arithmetic on a calendar day in this vocabulary.
    """
    if left.carrier == right.carrier:
        return left, right
    ranks = (_NUMERIC_RANK.get(left.carrier), _NUMERIC_RANK.get(right.carrier))
    if ranks[0] is None or ranks[1] is None:
        raise DomainRefused(
            what=(
                f"a {left.carrier} operand met a {right.carrier} one, and this "
                "vocabulary states no common type for them"
            ),
            move=(
                "convert one side explicitly, so the record carries the "
                "conversion the model made rather than the engine's guess"
            ),
            clause=clause,
        )
    target: Carrier = left.carrier if ranks[0] >= ranks[1] else right.carrier
    return (
        carried_to(left, target, clause=clause),
        carried_to(right, target, clause=clause),
    )


def checked_add(a: jax.Array, b: jax.Array) -> Checked:
    """Return ``a + b`` and the cells that left ``i64``.

    Exact: two operands of one sign whose sum takes the other sign is the
    whole of integer addition overflow, and both tests are one comparison.
    """
    result = a + b
    alike = (a >= 0) == (b >= 0)
    return Checked(result, alike & ((result >= 0) != (a >= 0)))


def checked_sub(a: jax.Array, b: jax.Array) -> Checked:
    """Return ``a - b`` and the cells that left ``i64``. Exact, as addition is."""
    result = a - b
    differ = (a >= 0) != (b >= 0)
    return Checked(result, differ & ((result >= 0) != (a >= 0)))


def checked_mul(a: jax.Array, b: jax.Array) -> Checked:
    """Return ``a * b`` and a coarse flag over the cells that may have left ``i64``.

    The flag is the product taken in float64 against 2⁶², plus the two cells
    a float product cannot see -- ``INT64_MIN`` against ``-1``, whose exact
    answer is one past the top and whose float product is exactly 2⁶³. Coarse
    because an exact test needs a 128-bit product, which int64 XLA has not
    got; over-approximating and re-judging the caught cells on the host with
    Python integers is exact and costs one pass over a handful of cells.
    """
    result = a * b
    wide = jnp.abs(a.astype(JNP_OF["f64"]) * b.astype(JNP_OF["f64"]))
    edge = ((a == -1) & (b == INT64_MIN)) | ((b == -1) & (a == INT64_MIN))
    return Checked(result, (wide > COARSE_PRODUCT) | edge)


def _safe_divisor(b: jax.Array) -> jax.Array:
    """Return ``b`` with its zeros replaced.

    So that the trace itself never divides by zero: the cells that would have
    are flagged beside the result and refuse at completion.
    """
    return jnp.where(b == 0, jnp.ones_like(b), b)


def checked_floordiv(a: jax.Array, b: jax.Array) -> Checked:
    """Return the quotient rounded toward negative infinity, and its two defects.

    11.1.25: floor is not truncation, so ``-7 // 3`` is ``-3``. A zero divisor
    yields null under the clause, and a null minted by a division is a refusal
    here rather than a value, since this engine holds no null.
    ``INT64_MIN // -1`` is the one quotient outside the type.
    """
    zero = b == 0
    result = jnp.floor_divide(a, _safe_divisor(b))
    edge = (a == INT64_MIN) & (b == -1)
    return Checked(jnp.where(zero, jnp.zeros_like(result), result), edge, zero)


def checked_mod(a: jax.Array, b: jax.Array) -> Checked:
    """Return the remainder carrying the divisor's sign, and its zero divisor.

    ``7 % -3`` is ``-2`` and ``-7 % 3`` is ``2``: the remainder follows the
    divisor, which is what ``left - right * floor(left/right)`` gives.
    """
    zero = b == 0
    result = jnp.remainder(a, _safe_divisor(b))
    return Checked(
        jnp.where(zero, jnp.zeros_like(result), result),
        jnp.zeros_like(zero),
        zero,
    )


def checked_neg(a: jax.Array) -> Checked:
    """Return ``-a`` and the one cell that has no negative inside ``i64``."""
    return Checked(-a, a == INT64_MIN)


def checked_abs(a: jax.Array) -> Checked:
    """Return ``|a|`` and the one cell whose magnitude is outside ``i64``."""
    return Checked(jnp.abs(a), a == INT64_MIN)


def checked_pow(a: jax.Array, n: jax.Array) -> Checked:
    """Return ``a ** n`` for whole non-negative ``n``, by repeated checked products.

    Exponentiation by squaring, with the square taken only while a bit of the
    exponent is still to come -- otherwise a base that is about to be thrown
    away would flag an overflow the answer never had. Every product's flag is
    the coarse one above, so the caller judges the caught cells on the host
    with the base and the exponent in hand.
    """
    result = jnp.ones_like(a)
    base = a
    remaining = n
    caught = jnp.zeros(a.shape, dtype=bool)
    for _ in range(_EXPONENT_BITS):
        take = (remaining & 1) == 1
        product = checked_mul(result, base)
        result = jnp.where(take, product.result, result)
        caught = caught | (take & product.overflow)
        remaining = remaining >> 1
        more = remaining != 0
        squared = checked_mul(base, base)
        base = jnp.where(more, squared.result, base)
        caught = caught | (more & squared.overflow)
    return Checked(result, caught)
