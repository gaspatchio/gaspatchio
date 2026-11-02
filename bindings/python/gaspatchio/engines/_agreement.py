# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Section 11.1.12's agreement rule for one line, in one Polars pass.

The rule is written here once. ``gspio compare`` reads every line it compares
through :func:`read_line`, and a comparison of two versions of a model
(``gspio diff --results``) is meant to call the same function, so that the
two commands cannot come to hold two versions of one rule.

**What one call is given.** The two columns of one line, row ``i`` of each
being the same policy, and a per-policy scale floor taken from what the line
reads (:func:`read_scale`, over :func:`policy_magnitude` of each read). In a
comparison of one artifact both sides read the same nodes. In a comparison of
two versions each side's floor is taken from **its own** artifact's reads,
because the edit may be exactly that a line reads something new.

**What it decides.** Integers, Booleans, strings, dates and datetimes are
exact, at every list depth, with a null list read as a list of one null --
the reading compare has always given it. A float line is exact in its
lengths, its null positions, its NaN class and the sign of its infinities,
in that order of a policy's timeline, and the first policy to part on one of
them decides which. Elsewhere two finite values are held to the band:
``|a - b| <= 1e-12 * scale``, the scale being the largest finite magnitude of
the line and of its reads over **that policy's** timeline, on both sides.
The sign of a zero is not compared. A line that parts on an exact aspect
reports what the policies before the first parted one came to, as compare's
reports always have.

**Why one column at a time.** A line is two columns; its reads are one float
per policy each, which a caller computes once and keeps. Nothing here turns
a column into Python objects, so a book's peak memory is its two files and
one line's working set, rather than every line's values as Python lists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import polars as pl

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "STRICT_ABSOLUTE",
    "STRICT_RELATIVE",
    "TOLERANCE",
    "Cell",
    "LineReading",
    "policy_magnitude",
    "read_line",
    "read_scale",
]

# The agreement band, 1e-12 of the line's scale (section 11.1.12). One place,
# because the lower bound an indeterminate line prints is this number divided
# into the difference, and two spellings of it would print a bound that was not
# the bound the verdict used.
TOLERANCE: Final = 1e-12

# The fixed floor, printed beside every verdict as the strict floor and deciding
# none: |a-b| <= STRICT_ABSOLUTE + STRICT_RELATIVE * |reference|, the same
# allowance on every line, so one report can be held against another.
STRICT_ABSOLUTE: Final = 1e-10
STRICT_RELATIVE: Final = 1e-12

# The exact aspects a float line can part on, by the names a report prints.
LENGTH: Final = "length"
NULL_POSITIONS: Final = "null-positions"
NAN_CLASS: Final = "nan-class"
INF_SIGN: Final = "inf-sign"

# A cell's place in a policy's timeline, one index per list level. Three is
# the deepest list the artifact's type vocabulary names, so three keys hold
# any place, padded with -1 where a place is shallower. Padding sorts a list's
# own length check before any of its elements, and an element's null check
# before anything inside it -- the order a timeline is read in.
_KEYS: Final = ("k0", "k1", "k2")
_UNSET: Final = -1
_ELEMENT_EVENT: Final = 0
_LENGTH_EVENT: Final = 1

# Each value's class, so that two classes can be compared as two integers.
_NULL, _NAN, _POSITIVE_INF, _NEGATIVE_INF, _FINITE = range(5)


@dataclass(frozen=True, slots=True)
class Cell:
    """One cell of a line, on both sides.

    Attributes:
        policy: The policy's row, in the pairing the caller handed in.
        period: Its place in that policy's timeline, one index per list
            level; empty for a line with one value per policy.
        before: The before side's value.
        after: The after side's value.

    """

    policy: int
    period: tuple[int, ...]
    before: float
    after: float


@dataclass(frozen=True, slots=True)
class LineReading:
    """What one line's two columns came to, under section 11.1.12.

    Attributes:
        parted: An exact aspect parted the two -- a value of an exact type, a
            length, a null position, a NaN, an infinity's sign -- or a
            policy whose every value is zero on both sides held a
            difference. The band has nothing to say about either.
        parted_on: The aspect a float line parted on, at the first policy
            that parted and the first place in its timeline; None for a line
            of an exact type, whose type is what parted it.
        parted_policy: The first policy that parted, or None.
        max_abs: The largest absolute difference between two finite values,
            over the policies before the first that parted.
        max_ratio: Over those policies, the largest of each one's largest
            difference divided by its own scale; None where no policy had a
            scale above zero.
        scale: The scale of the first policy whose ratio was the largest; 0
            where there was none.
        strict: Whether every difference was within the fixed floor, 1e-10
            plus 1e-12 of the before value. False on a line that parted.
        worst: The cell whose difference decided ``max_ratio``: the first
            cell in the deciding policy's timeline with that policy's largest
            difference. None where no difference was found.

    """

    parted: bool
    parted_on: str | None
    parted_policy: int | None
    max_abs: float
    max_ratio: float | None
    scale: float
    strict: bool
    worst: Cell | None


def read_line(
    before: pl.Series,
    after: pl.Series,
    *,
    exact: bool,
    read_scale: pl.Series | None = None,
) -> LineReading:
    """Read one line's two columns under section 11.1.12's agreement rule.

    Args:
        before: The before side's column, one row per policy.
        after: The after side's column, its row ``i`` the same policy as the
            before side's row ``i``.
        exact: Whether the line's declared type is decided by its own digits
            -- an integer, a Boolean, a string, a date or a datetime, at any
            list depth. False for a float line, which is held to the band.
        read_scale: One float per policy: the largest finite magnitude among
            the values the line reads, on both sides (see :func:`read_scale`).
            None where the line reads nothing in reach. Ignored on an exact
            line.

    Returns:
        What the two came to, before any verdict: a caller states the
        verdict, because only it knows which reads were absent.

    Raises:
        ValueError: The two columns, or the scale, hold different numbers of
            policies.

    """
    rows = before.len()
    if after.len() != rows or (read_scale is not None and read_scale.len() != rows):
        message = (
            f"One line's two columns and its scale hold {rows}, {after.len()} "
            f"and {rows if read_scale is None else read_scale.len()} policies; "
            "pair the rows before reading the line."
        )
        raise ValueError(message)
    if exact:
        return _exact_line(before, after)
    return _banded_line(before, after, read_scale)


def policy_magnitude(values: pl.Series) -> pl.Series:
    """Return each policy's largest finite numeric magnitude, through every list.

    Integers count as their value and floats as theirs; NaNs, infinities,
    nulls, Booleans, strings and dates count as nothing, and a policy with
    none of what counts is 0. This is a line's contribution to the scale of
    every line that reads it, so a caller reading many lines computes it
    once per column and keeps it.

    Args:
        values: One column, one row per policy.

    Returns:
        A Float64 column, one value per row of ``values``.

    """
    depth, leaf = _depth_and_leaf(values.dtype)
    if not (leaf.is_integer() or leaf.is_float()):
        return pl.zeros(values.len(), pl.Float64, eager=True)
    floats = values.cast(_nested(pl.Float64(), depth))
    if depth == 0:
        finite = floats.is_finite().fill_null(value=False)
        zeros = pl.zeros(floats.len(), pl.Float64, eager=True)
        return floats.abs().zip_with(finite, zeros)
    if depth == 1:
        # Every magnitude, NaNs and infinities included. Where each policy's
        # largest of those is finite, no infinity was among them, and a NaN
        # either was not or was passed over by the maximum -- so the number is
        # the largest finite magnitude, read without first sorting out what
        # to leave out. Where any is not finite, the values are read again.
        quick = floats.list.eval(pl.element().abs()).list.max()
        if quick.is_finite().fill_null(value=True).all():
            return quick.fill_null(0.0)
    return floats.list.eval(_largest(pl.element(), depth - 1)).list.max().fill_null(0.0)


def read_scale(
    before: Sequence[pl.Series], after: Sequence[pl.Series], rows: int
) -> pl.Series:
    """Return each policy's scale floor from what a line reads, on both sides.

    Args:
        before: :func:`policy_magnitude` of each read the before side's
            artifact names, in the caller's pairing.
        after: The same for the after side's artifact. In a comparison of
            one artifact the two name the same reads; in a comparison of two
            versions each names its own.
        rows: The number of policies, for a line that reads nothing.

    Returns:
        A Float64 column, one value per policy: the largest of them all, or
        0 where there are none.

    """
    return _largest_of([*before, *after], rows)


# --- exact lines ---------------------------------------------------------------


def _exact_line(before: pl.Series, after: pl.Series) -> LineReading:
    """Read a line whose declared type is decided by its own digits."""
    left, right = _comparable(before, after)
    same = _one_null_list(left).eq_missing(_one_null_list(right))
    if same.all():
        return LineReading(
            parted=False,
            parted_on=None,
            parted_policy=None,
            max_abs=0.0,
            max_ratio=None,
            scale=0.0,
            strict=True,
            worst=None,
        )
    return LineReading(
        parted=True,
        parted_on=None,
        parted_policy=int(same.not_().arg_true()[0]),
        max_abs=0.0,
        max_ratio=None,
        scale=0.0,
        strict=False,
        worst=None,
    )


def _comparable(before: pl.Series, after: pl.Series) -> tuple[pl.Series, pl.Series]:
    """Return two exact columns in one physical type, value for value.

    Every integer width is one i64, as the declared type says. Two datetimes
    of different units or zones are compared as instants to the microsecond,
    the precision a datetime value has always been read at here; a zoned one
    against an unzoned one is never equal, value for value, and keeps only
    where its nulls are.
    """
    depth, left = _depth_and_leaf(before.dtype)
    _, right = _depth_and_leaf(after.dtype)
    if left.is_integer():
        target = _nested(pl.Int64(), depth)
        return before.cast(target), after.cast(target)
    if not isinstance(left, pl.Datetime) or left == right:
        return before, after
    zoned = left.time_zone is not None
    if isinstance(right, pl.Datetime) and zoned == (right.time_zone is not None):
        target = _nested(pl.Datetime("us", "UTC" if zoned else None), depth)
        return before.cast(target), after.cast(target)
    return _marked(before, depth, 0), _marked(after, depth, 1)


def _marked(values: pl.Series, depth: int, mark: int) -> pl.Series:
    """Replace every datetime with ``mark``, keeping the nulls and the shape."""
    if depth == 0:
        return values.dt.epoch("us") * 0 + mark
    return values.list.eval(_per_leaf(pl.element(), depth - 1, mark))


def _per_leaf(value: pl.Expr, depth: int, mark: int) -> pl.Expr:
    """Mark every datetime of a list ``depth`` levels below ``value``."""
    if depth == 0:
        return value.dt.epoch("us") * 0 + mark
    return value.list.eval(_per_leaf(pl.element(), depth - 1, mark))


# --- float lines ---------------------------------------------------------------


def _banded_line(
    before: pl.Series, after: pl.Series, read_scale: pl.Series | None
) -> LineReading:
    """Read a float line: its exact aspects, then its band, per policy."""
    depth, _ = _depth_and_leaf(before.dtype)
    target = _nested(pl.Float64(), depth)
    left = before.cast(target)
    right = after.cast(target)

    # A policy that has not parted has its finite values in the same places
    # on both sides, so its own magnitude is the larger of the two columns'.
    floors = [policy_magnitude(left), policy_magnitude(right)]
    if read_scale is not None:
        floors.append(read_scale)
    scale = _largest_of(floors, left.len())

    alike = _alike(left, right, depth)
    if alike is not None:
        return _band(alike, scale, None, None, (left, right, depth))

    leaves, events = _walk(left, right, depth, track=False)
    parted_policy = _first_policy(events)
    parted_on = None
    if parted_policy is not None:
        parted_on = _first_aspect(left, right, depth, parted_policy)
        leaves = leaves.filter(leaves.get_column("p") < parted_policy)
    held = leaves.get_column("b")
    other = leaves.get_column("a")
    finite = (held.is_finite() & other.is_finite()).fill_null(value=False)
    cells = _Cells(
        held=held.filter(finite),
        other=other.filter(finite),
        policy=leaves.get_column("p").filter(finite),
        worst=None,
    )
    return _band(cells, scale, parted_policy, parted_on, (left, right, depth))


@dataclass(frozen=True, slots=True)
class _Cells:
    """A line's finite value pairs, before and after, and whose policy each is.

    ``worst`` is each policy's largest difference, where the cells came in
    whole policies and it was cheaper to take it per policy than per cell;
    ``policy`` is then None, because every cell's policy is its row's.
    """

    held: pl.Series
    other: pl.Series
    policy: pl.Series | None
    worst: pl.Series | None


def _alike(left: pl.Series, right: pl.Series, depth: int) -> _Cells | None:
    """Return a line's cells where no exact aspect can part it, else None.

    That is a line one list deep at most, with no null timeline, every
    policy's two timelines one length, and every value finite on both sides:
    nothing is left for the exact aspects to decide, and each policy's
    largest difference is taken over its own timeline without first pairing
    every value with its policy.
    """
    if depth > 1 or left.null_count() or right.null_count():
        return None
    if depth == 1:
        if not (left.list.len() == right.list.len()).all():
            return None
        held = left.explode(empty_as_null=False)
        other = right.explode(empty_as_null=False)
    else:
        held, other = left, right
    finite = (held.is_finite() & other.is_finite()).fill_null(value=False)
    if not finite.all():
        return None
    if depth == 0:
        return _Cells(held=held, other=other, policy=None, worst=(left - right).abs())
    apart = (left - right).list.eval(pl.element().abs()).list.max()
    return _Cells(held=held, other=other, policy=None, worst=apart.fill_null(0.0))


def _band(
    cells: _Cells,
    scale: pl.Series,
    parted_policy: int | None,
    parted_on: str | None,
    line: tuple[pl.Series, pl.Series, int],
) -> LineReading:
    """Hold a line's finite cells to the band, over the policies before any parted.

    A policy's ratio is its largest difference over its own scale. Taken per
    cell it is the same number -- dividing by one positive scale keeps the
    order of a policy's differences -- so whichever way the cells came, the
    largest ratio and the first policy reaching it are the ones per policy.
    """
    difference = (cells.held - cells.other).abs()
    loose = (difference > STRICT_ABSOLUTE + STRICT_RELATIVE * cells.held.abs()).any()
    if cells.policy is None:
        worst = cells.worst if cells.worst is not None else difference
        over = scale
        ratio = worst / over
        policy = pl.int_range(scale.len(), dtype=pl.Int64, eager=True)
    else:
        worst = difference
        over = scale.gather(cells.policy)
        ratio = worst / over
        policy = cells.policy
    positive = over > 0.0
    unscaled = (~positive & (worst > 0.0)).any()

    compared = scale if parted_policy is None else scale.head(parted_policy)
    scaled = compared > 0.0
    max_ratio: float | None = None
    deciding: int | None = None
    if scaled.any():
        max_ratio = _number(ratio.filter(positive).max(), default=0.0)
        if max_ratio > 0.0:
            reaching = positive & (ratio == max_ratio)
            deciding = _number_of(policy.filter(reaching).min())
        else:
            deciding = int(scaled.arg_true()[0])

    cell = None
    if deciding is not None and max_ratio is not None and max_ratio > 0.0:
        cell = _worst_cell(*line, deciding)
    return LineReading(
        parted=parted_policy is not None or unscaled,
        parted_on=parted_on,
        parted_policy=parted_policy,
        max_abs=_number(difference.max(), default=0.0),
        max_ratio=max_ratio,
        scale=0.0 if deciding is None else _number(scale[deciding], default=0.0),
        strict=parted_policy is None and not loose,
        worst=cell,
    )


def _walk(
    before: pl.Series, after: pl.Series, depth: int, *, track: bool
) -> tuple[pl.DataFrame, list[pl.DataFrame]]:
    """Return a line's paired leaf values, and every place an exact aspect parts.

    Each list level is checked and then exploded: a policy's top-level
    lengths, then at each deeper level whether an element is a list on one
    side and a null on the other, and the two lists' lengths. Only pairs
    that are alike go down a level, so a parted pair is reported once, where
    it parted. ``track`` keeps each value's place in its timeline, which the
    one policy a report names needs and the whole book does not.
    """
    frame = pl.DataFrame(
        {
            "p": pl.int_range(before.len(), dtype=pl.Int64, eager=True),
            "b": _one_null_list(before),
            "a": _one_null_list(after),
        }
    )
    events: list[pl.DataFrame] = []
    keys: list[str] = []
    if depth == 0 and track:
        frame = frame.with_columns(pl.lit(0, dtype=pl.Int64).alias(_KEYS[0]))
        keys.append(_KEYS[0])
    for level in range(depth):
        held = frame.get_column("b")
        other = frame.get_column("a")
        left_length = held.list.len()
        right_length = other.list.len()
        down = left_length == right_length
        if level == 0:
            events += _events(frame, ~down, keys, _LENGTH_EVENT, LENGTH)
        else:
            both = held.is_not_null() & other.is_not_null()
            nulls = held.is_null() != other.is_null()
            events += _events(frame, nulls, keys, _ELEMENT_EVENT, NULL_POSITIONS)
            events += _events(frame, both & ~down, keys, _LENGTH_EVENT, LENGTH)
            down = (both & down).fill_null(value=False)
        if not down.all():
            frame = frame.filter(down)
        exploded = ["b", "a"]
        if track:
            index = pl.int_ranges(0, frame.get_column("b").list.len(), eager=True)
            frame = frame.with_columns(index.alias(_KEYS[level]))
            keys.append(_KEYS[level])
            exploded.append(_KEYS[level])
        frame = frame.explode(exploded, empty_as_null=False)

    held = frame.get_column("b")
    other = frame.get_column("a")
    if not (held.is_finite() & other.is_finite()).fill_null(value=False).all():
        parted = _class_of(held) != _class_of(other)
        events += _events(frame, parted, keys, _ELEMENT_EVENT, None)
    return frame, events


def _events(
    frame: pl.DataFrame,
    parted: pl.Series,
    keys: Sequence[str],
    event: int,
    aspect: str | None,
) -> list[pl.DataFrame]:
    """Return the places ``parted`` marks, each with its place and its aspect.

    ``aspect`` None is a leaf's: which of a null, a NaN or an infinity's sign
    parted the two values, read off the pair.
    """
    if not parted.any():
        return []
    marked = frame.filter(parted)
    padding = [
        marked.get_column(key)
        if key in keys
        else pl.repeat(_UNSET, marked.height, dtype=pl.Int64, eager=True).alias(key)
        for key in _KEYS
    ]
    if aspect is None:
        held = marked.get_column("b")
        other = marked.get_column("a")
        nulls = held.is_null() | other.is_null()
        nans = (held.is_nan() | other.is_nan()).fill_null(value=False)
        # 0 a null, 1 a NaN, 2 an infinity's sign: the order compare has
        # always named a parted pair's aspect in.
        code = (~nulls).cast(pl.Int8) * (1 + (~nans).cast(pl.Int8))
        named = code.replace_strict(
            {0: NULL_POSITIONS, 1: NAN_CLASS, 2: INF_SIGN}, return_dtype=pl.String
        )
    else:
        named = pl.repeat(aspect, marked.height, dtype=pl.String, eager=True)
    return [
        pl.DataFrame(
            [
                marked.get_column("p"),
                *padding,
                pl.repeat(event, marked.height, dtype=pl.Int64, eager=True).alias(
                    "event"
                ),
                named.alias("aspect"),
            ]
        )
    ]


def _first_policy(events: Sequence[pl.DataFrame]) -> int | None:
    """Return the first policy any event names, or None where nothing parted."""
    if not events:
        return None
    return _number_of(pl.concat(events).get_column("p").min())


def _first_aspect(left: pl.Series, right: pl.Series, depth: int, policy: int) -> str:
    """Return the aspect one policy parts on first, reading its timeline in order."""
    _, events = _walk(left.slice(policy, 1), right.slice(policy, 1), depth, track=True)
    first = pl.concat(events).sort([*_KEYS, "event"]).row(0, named=True)
    return str(first["aspect"])


def _worst_cell(left: pl.Series, right: pl.Series, depth: int, policy: int) -> Cell:
    """Return the first cell of one policy holding that policy's largest difference."""
    leaves, _ = _walk(left.slice(policy, 1), right.slice(policy, 1), depth, track=True)
    held = leaves.get_column("b")
    other = leaves.get_column("a")
    finite = leaves.filter(
        (held.is_finite() & other.is_finite()).fill_null(value=False)
    )
    difference = (finite.get_column("b") - finite.get_column("a")).abs()
    row = finite.filter(difference == difference.max()).row(0, named=True)
    return Cell(
        policy=policy,
        period=tuple(int(row[key]) for key in _KEYS[:depth]),
        before=float(row["b"]),
        after=float(row["a"]),
    )


def _class_of(values: pl.Series) -> pl.Series:
    """Return which of five kinds each value is: null, NaN, +inf, -inf or finite.

    One integer per value, so that two sides' kinds compare as two columns.
    """
    nan = values.is_nan().fill_null(value=False).cast(pl.Int8)
    positive = (values == math.inf).fill_null(value=False).cast(pl.Int8)
    negative = (values == -math.inf).fill_null(value=False).cast(pl.Int8)
    kind = _FINITE - (_FINITE - _NAN) * nan
    kind = kind - (_FINITE - _POSITIVE_INF) * positive
    kind = kind - (_FINITE - _NEGATIVE_INF) * negative
    return kind * values.is_not_null().cast(pl.Int8) + _NULL


# --- shapes --------------------------------------------------------------------


def _depth_and_leaf(dtype: pl.DataType) -> tuple[int, pl.DataType]:
    """Return how deep a list type nests, and the scalar type at its bottom."""
    depth = 0
    while isinstance(dtype, pl.List):
        inner = dtype.inner
        dtype = inner if isinstance(inner, pl.DataType) else inner()
        depth += 1
    return depth, dtype


def _nested(leaf: pl.DataType, depth: int) -> pl.DataType:
    """Return ``leaf`` wrapped in ``depth`` levels of list."""
    dtype = leaf
    for _ in range(depth):
        dtype = pl.List(dtype)
    return dtype


def _largest(value: pl.Expr, depth: int) -> pl.Expr:
    """Return the largest finite magnitude of a list ``depth`` levels deep."""
    if depth == 0:
        return value.filter(value.is_finite()).abs()
    return value.list.eval(_largest(pl.element(), depth - 1)).list.max()


def _largest_of(columns: Sequence[pl.Series], rows: int) -> pl.Series:
    """Return the largest of several per-policy columns; zeros where none is given."""
    if not columns:
        return pl.zeros(rows, pl.Float64, eager=True)
    return pl.DataFrame(
        {f"c{index}": one for index, one in enumerate(columns)}
    ).max_horizontal()


def _one_null_list(values: pl.Series) -> pl.Series:
    """Read a null list as a list holding one null, as a timeline of one value.

    A line with one value per policy is a timeline of one value, so a policy
    with no timeline at all reads as one null value rather than as no
    values: it then parts from a timeline of one value on its null position,
    and from a timeline of any other length on its length.
    """
    if not isinstance(values.dtype, pl.List) or values.null_count() == 0:
        return values
    one_null = pl.Series([[None]], dtype=values.dtype)
    return values.fill_null(pl.lit(one_null).first())


def _number(value: object, *, default: float) -> float:
    """Return a Polars aggregate as a float, or ``default`` where it is null."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    message = f"A numeric aggregate came back as {type(value).__name__}."
    raise TypeError(message)


def _number_of(value: object) -> int:
    """Return a Polars aggregate over row numbers as an int."""
    if isinstance(value, int):
        return value
    message = f"A row number came back as {type(value).__name__}."
    raise TypeError(message)
