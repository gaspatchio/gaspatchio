# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A comparison of whole numbers, dates and times, and durations, decided exactly.

A per-period comparison runs through the ``list_conditional`` kernel, which
reads both sides as doubles. A double names every whole number only up to
``2**53``, so past it two neighbouring values became one: ``2**53 + 1 > 2**53``
answered false in every period, a nanosecond date and time one unit after
another compared equal to it, and ``2**63 - 1 == 2**63 - 2`` answered true --
where the same line written per policy, which Polars compares in the values'
own type, answered each exactly. Section 11.1.26 states the six comparisons
exact over the full range of the type they compare, on both routes.

**The kernel is handed the difference, not the two values.** Each side is
read as the whole number it is held as -- a date and time or a duration as its
count of units, both in the finer of the two units -- in ``Int128``, where the
difference of two 64-bit values never overflows, and the kernel compares that
difference with nought. Rounding to a double keeps a number's sign and turns
no whole number but nought into nought, so ``x - y`` compared with ``0`` in
doubles is ``x`` compared with ``y`` exactly, for all six comparisons. A
128-bit value has no wider type to take a difference in, so it is cut into
32-bit pieces -- each of which a double holds -- and the sign of the first
piece that differs decides it.

**Per policy, Polars compares two values of one type exactly**, and is left
to it. Two of different types are read in one that holds both first
(:func:`per_policy_operands`): two whole numbers of different widths, and two
dates and times or durations in different units or zones, which Polars
compared in the coarser unit -- a nanosecond after a microsecond value equal
to it -- are read as counts of the finer unit, as the per-period route reads
them, so the two routes give one answer.

Two per-period sides of different lengths are refused by the kernel, naming
both lengths, as before: the shorter run is not padded and the longer not cut.
A null on either side is a null answer, value by value and policy by policy,
as it was.

**A ``Decimal`` is a count of its last place**, and two of them -- or one
beside a whole number, which has no places -- are decided the same way. A
double holds a decimal only to about fifteen figures, so ``0.1 + 1e-20``
compared equal to ``0.1`` in every period while the per-policy route, which
Polars compares in a common decimal type, answered it exactly; and that
common type silently answered null where it could not hold one side
(``10**30`` beside a column of twenty places). Each side is cut into its
whole part and its fraction carried to the more places of the two, each in
32-bit pieces, and the first piece that differs decides, on both routes.

A whole number beside a double, two doubles, two dates, two times of day, two
flags and two narrow whole numbers are left as they were: a double already
holds every value of the narrow ones, and a whole number beside a double is
the mixed comparison 11.1.26 states only inside ``[-2**53, 2**53]``.
"""

from __future__ import annotations

from typing import Final

import polars as pl

from gaspatchio.frame.lowering._polars.plugins import list_conditional

# Nanoseconds in one unit of each time unit Polars carries.
_NANOSECONDS: Final[dict[str, int]] = {"ns": 1, "us": 1_000, "ms": 1_000_000}

# The whole-number types a double does not hold every value of.
_WIDE_WHOLE: Final = (pl.Int64, pl.UInt64, pl.Int128, pl.UInt128)

# The two whole-number types no other type holds the difference of.
_WIDEST: Final = (pl.Int128, pl.UInt128)

# One more than the greatest 32-bit piece, and how many a 128-bit value has.
_PIECE: Final = 2**32
_PIECES: Final = 4


def _element(dtype: pl.DataType) -> pl.DataType:
    """Return a per-period type's element type, or the type itself, as an instance."""
    inner = dtype.inner if isinstance(dtype, pl.List) else dtype
    if isinstance(inner, type) and issubclass(inner, pl.DataType):
        # A type written as its class, ``pl.List(pl.Int64)``, holds the class.
        return inner()
    return inner if isinstance(inner, pl.DataType) else dtype


def _family(dtype: pl.DataType) -> str | None:
    """Return which held whole number a value of ``dtype`` is, or None.

    A ``Decimal`` is a whole number of units of its last place -- a count, as
    a date and time is -- so it is one too.
    """
    if isinstance(dtype, pl.Decimal):
        return "decimal"
    if isinstance(dtype, pl.Datetime):
        return "datetime"
    if isinstance(dtype, pl.Duration):
        return "duration"
    if dtype.is_integer():
        return "whole"
    return None


def _unit(dtype: pl.DataType) -> int:
    """Return how many nanoseconds one unit of ``dtype`` is; 1 for a number."""
    unit = getattr(dtype, "time_unit", None)
    return _NANOSECONDS[unit] if isinstance(unit, str) else 1


def _held_exactly(left: pl.DataType, right: pl.DataType) -> bool:
    """Say whether a double already holds every value of both sides."""
    return not any(isinstance(dtype, _WIDE_WHOLE) for dtype in (left, right))


def _in_one_family(left: pl.DataType, right: pl.DataType) -> str | None:
    """Return the family both sides are held in, where a double does not suffice.

    A ``Decimal`` beside a whole number is a pair of decimals, the whole
    number one with no places.
    """
    family, other = _family(left), _family(right)
    if "decimal" in {family, other} and {family, other} <= {"decimal", "whole"}:
        return "decimal"
    if family is None or family != other:
        return None
    if family == "whole" and _held_exactly(left, right):
        return None
    return family


def per_period_operands(
    left: tuple[pl.Expr, pl.DataType],
    right: tuple[pl.Expr, pl.DataType],
    *,
    right_per_period: bool,
) -> tuple[pl.Expr, pl.Expr] | None:
    """Return the two operands to hand the kernel so its doubles decide exactly.

    ``left`` is the per-period side, already on the kernel's left; ``right``
    is per period where ``right_per_period`` says so, and one value per
    policy otherwise. Each comes with the type it resolves to. None where the
    pair is not one this module decides: the kernel's doubles are then
    already exact, or the comparison is a mixed one 11.1.26 bounds.
    """
    left_type, right_type = _element(left[1]), _element(right[1])
    family = _in_one_family(left_type, right_type)
    if family is None:
        return None
    if family == "decimal":
        places = _common_places(left_type, right_type)
        return _keyed(
            _decimal_pieces(left, places, per_period=True),
            _decimal_pieces(right, places, per_period=right_per_period),
            right_per_period=right_per_period,
        )
    if isinstance(left_type, _WIDEST) or isinstance(right_type, _WIDEST):
        return _by_pieces(left, right, right_per_period=right_per_period)
    finer = min(_unit(left_type), _unit(right_type))
    ours = _counted(left[0], left_type, finer, per_period=True)
    theirs = _counted(right[0], right_type, finer, per_period=right_per_period)
    if not right_per_period:
        return (ours - theirs).cast(pl.List(pl.Float64)), pl.lit(0.0)
    # The two runs are subtracted only where their lengths agree, so the
    # kernel, not the subtraction, is what refuses two of different lengths.
    alike = pl.when(ours.list.len() == theirs.list.len()).then(theirs).otherwise(ours)
    apart = (ours - alike).cast(pl.List(pl.Float64))
    return _checked_by_the_kernel(left[0], right[0], apart), pl.lit(0.0)


def per_policy_operands(
    left: tuple[pl.Expr, pl.DataType],
    right: tuple[pl.Expr, pl.DataType],
) -> tuple[pl.Expr, pl.Expr] | None:
    """Return two per-policy operands in a type that holds them both, or None.

    Polars compares two whole numbers of one type exactly, and two of
    different signedness or width in a type that need not hold both:
    ``UInt64`` ``2**64 - 1`` against an ``Int64`` answered null. A pair with a
    side wider than ``i64`` is read in ``Int128``, which holds every ``UInt64``
    and ``Int64``; a ``UInt128`` beside a signed number is decided by its
    pieces.

    Two dates and times, or two durations, held in different units -- or two
    dates and times in different time zones -- are read as their counts of
    the finer unit, in ``Int128``, as the per-period route reads them. Polars
    compared two units in the coarser one, cutting the finer side down to
    it, so a nanosecond after a microsecond value compared equal to it, and
    refused two zones when the frame ran. ``Int128`` holds the finer count of
    every value either unit holds, so nothing is cut and nothing is refused.
    Everything else is left to Polars, which is exact for it.
    """
    left_type, right_type = _element(left[1]), _element(right[1])
    if left_type == right_type:
        return None
    family = _in_one_family(left_type, right_type)
    if family in {"datetime", "duration"}:
        return _in_the_finer_unit(left, right)
    if family == "decimal":
        places = _common_places(left_type, right_type)
        ours = _decimal_pieces(left, places, per_period=False)
        theirs = _decimal_pieces(right, places, per_period=False)
        return _signed_key(ours, theirs, per_period=False), pl.lit(0)
    if family != "whole":
        return None
    return _whole_numbers_in_one_type(left, right)


def _whole_numbers_in_one_type(
    left: tuple[pl.Expr, pl.DataType], right: tuple[pl.Expr, pl.DataType]
) -> tuple[pl.Expr, pl.Expr] | None:
    """Return two per-policy whole numbers of different types in one holding both."""
    left_type, right_type = _element(left[1]), _element(right[1])
    if not any(
        isinstance(dtype, (*_WIDEST, pl.UInt64)) for dtype in (left_type, right_type)
    ):
        return None
    if pl.UInt128 not in (left_type, right_type):
        return left[0].cast(pl.Int128), right[0].cast(pl.Int128)
    if all(dtype.is_unsigned_integer() for dtype in (left_type, right_type)):
        return left[0].cast(pl.UInt128), right[0].cast(pl.UInt128)
    ours, theirs = _pieces(left, per_period=False), _pieces(right, per_period=False)
    return _signed_key(ours, theirs, per_period=False), pl.lit(0)


def _in_the_finer_unit(
    left: tuple[pl.Expr, pl.DataType], right: tuple[pl.Expr, pl.DataType]
) -> tuple[pl.Expr, pl.Expr]:
    """Return two per-policy times of different types as counts of the finer unit.

    A count is taken from the epoch in coordinated universal time, so two
    times in different time zones compare by the instant each names, as
    11.1.26 states; Polars refused that pair when the frame ran.
    """
    left_type, right_type = _element(left[1]), _element(right[1])
    finer = min(_unit(left_type), _unit(right_type))
    return (
        _counted(left[0], left_type, finer, per_period=False),
        _counted(right[0], right_type, finer, per_period=False),
    )


def wide_literal(value: int) -> pl.Expr:
    """Return a whole number past ``i64`` as the narrowest Polars literal holding it.

    Reached only for a literal compared against a column still wider than
    ``i64``, the one place such a literal is admitted: a comparison reads a
    value by its digits and cannot wrap it.
    """
    return pl.lit(value, dtype=wide_literal_dtype(value))


def wide_literal_dtype(value: int) -> pl.DataType:
    """Return the narrowest whole-number type holding ``value``, past ``i64``."""
    for dtype, low, high in (
        (pl.UInt64(), 0, 2**64),
        (pl.Int128(), -(2**127), 2**127),
        (pl.UInt128(), 0, 2**128),
    ):
        if low <= value < high:
            return dtype
    msg = f"{value} is outside every whole-number type a column can hold"
    raise ValueError(msg)


def _counted(
    value: pl.Expr, dtype: pl.DataType, finer: int, *, per_period: bool
) -> pl.Expr:
    """Return ``value`` in ``Int128``, as its count of ``finer`` units if a time."""
    held = value.to_physical() if dtype.is_temporal() else value
    counted = held.cast(pl.List(pl.Int128) if per_period else pl.Int128)
    scale = _unit(dtype) // finer
    return counted * pl.lit(scale, dtype=pl.Int128) if scale != 1 else counted


def _checked_by_the_kernel(left: pl.Expr, right: pl.Expr, apart: pl.Expr) -> pl.Expr:
    """Return ``apart`` passed through the kernel over the two runs it was taken from.

    The kernel pairs ``left`` with ``right`` period by period and selects
    ``apart`` either way, so what comes back is the difference wherever the
    two runs agree in length, a null wherever either side is null, and the
    kernel's own refusal, naming both lengths, where a policy's two runs
    differ.
    """
    return list_conditional(left, right, apart, apart, "eq")


def _pieces(side: tuple[pl.Expr, pl.DataType], *, per_period: bool) -> list[pl.Expr]:
    """Return a whole number's four 32-bit pieces, the highest first, as ``Int64``.

    A value is its highest piece times ``2**96`` plus three pieces in
    ``[0, 2**32)``, each the floor division's remainder, so two values are in
    the order of the first piece where they differ, whatever their types.
    """
    held = pl.UInt128 if _element(side[1]) == pl.UInt128 else pl.Int128
    value = side[0].cast(pl.List(held) if per_period else held)
    piece = pl.List(pl.Int64) if per_period else pl.Int64
    pieces = []
    for k in reversed(range(_PIECES)):
        shifted = value // pl.lit(_PIECE**k, dtype=held) if k else value
        if k != _PIECES - 1:
            shifted = shifted % pl.lit(_PIECE, dtype=held)
        pieces.append(shifted.cast(piece))
    return pieces


def _signed_key(
    ours: list[pl.Expr], theirs: list[pl.Expr], *, per_period: bool
) -> pl.Expr:
    """Return a small whole number with the sign of ``ours - theirs``.

    The sign of each piece's difference, weighted so the first that is not
    nought outweighs every later one together.
    """
    key: pl.Expr | None = None
    weights = [2**place for place in reversed(range(len(ours)))]
    for weight, (one, other) in zip(
        weights, zip(ours, theirs, strict=True), strict=True
    ):
        difference = one - other
        sign = (
            difference.list.eval(pl.element().sign())
            if per_period
            else difference.sign()
        )
        term = sign * weight
        key = term if key is None else key + term
    return key  # type: ignore[return-value]


def _by_pieces(
    left: tuple[pl.Expr, pl.DataType],
    right: tuple[pl.Expr, pl.DataType],
    *,
    right_per_period: bool,
) -> tuple[pl.Expr, pl.Expr]:
    """Return a 128-bit comparison's operands for the kernel: a small key, nought."""
    return _keyed(
        _pieces(left, per_period=True),
        _pieces(right, per_period=right_per_period),
        right_per_period=right_per_period,
    )


def _keyed(
    ours: list[pl.Expr], theirs: list[pl.Expr], *, right_per_period: bool
) -> tuple[pl.Expr, pl.Expr]:
    """Return the kernel's operands for two values read as pieces: a key, nought."""
    if not right_per_period:
        key = _signed_key(ours, theirs, per_period=True)
        return key.cast(pl.List(pl.Float64)), pl.lit(0.0)
    alike = [
        pl.when(one.list.len() == other.list.len()).then(other).otherwise(one)
        for one, other in zip(ours, theirs, strict=True)
    ]
    key = _signed_key(ours, alike, per_period=True).cast(pl.List(pl.Float64))
    return _checked_by_the_kernel(ours[-1], theirs[-1], key), pl.lit(0.0)


def _common_places(left: pl.DataType, right: pl.DataType) -> int:
    """Return the most places either side is held to; a whole number has none."""
    return max(getattr(dtype, "scale", 0) or 0 for dtype in (left, right))


def _decimal_pieces(
    side: tuple[pl.Expr, pl.DataType], places: int, *, per_period: bool
) -> list[pl.Expr]:
    """Return a number as its whole part's pieces, then its fraction's, at ``places``.

    A ``Decimal`` is held as a count of its last place in ``Int128``. Its
    whole part is that count floor-divided by ``10**scale`` and its fraction
    what is left, a count in ``[0, 10**scale)``, carried to ``places`` --
    which no ``Int128`` overflows, since ``10**38`` is the most it reaches.
    Two numbers are in the order of their whole parts and then of their
    fractions, so each is cut into the four 32-bit pieces a double holds
    (:func:`_pieces`) and the first piece that differs decides. A whole
    number is its own whole part with no fraction.
    """
    dtype = _element(side[1])
    run = pl.List(pl.Int128) if per_period else pl.Int128
    if not isinstance(dtype, pl.Decimal):
        whole = side
        fraction = side[0].cast(run) * pl.lit(0, dtype=pl.Int128)
    else:
        scale = dtype.scale or 0
        counts = side[0].to_physical()
        unit = pl.lit(10**scale, dtype=pl.Int128)
        fraction = (counts % unit) * pl.lit(10 ** (places - scale), dtype=pl.Int128)
        whole = (counts // unit, pl.Int128())
    return [
        *_pieces(whole, per_period=per_period),
        *_pieces((fraction, pl.Int128()), per_period=per_period),
    ]
