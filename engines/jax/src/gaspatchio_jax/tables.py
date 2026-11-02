# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A basis as one dense grid, addressed by arithmetic, with an exact fallback.

An exact-match read of an assumption table is the operation an actuarial
projection does most: six of them in the shipped level 4 model, one per
policy per period, and under a search-per-key lowering they were most of the
model's warm time. What replaces the search is the thing the Rust kernel
already does -- for each key column a position rule rather than a search, and
one flat gather into a mixed-radix grid:

* **an integer axis**: position = ``key - offset``, which is arithmetic and
  holds nothing;
* **a text axis**: position = the interned code through a remap array, absent
  codes at -1;
* **the grid**: one flat array of ``prod(sizes)`` cells, with a validity bit
  per cell, so a key tuple the table has no row for lands somewhere harmless
  and is a miss rather than a wrong answer.

Timed on this laptop against the searching form at ten thousand policies over
83 periods, on 2026-09-21: 0.6 ms against 34 ms, and no temporaries against
23 MB.

**The fallback is exact, and it is taken on the kernel's own conditions.** A
key space wider than the signed integer a flat index is held in, a grid that
would be over a hundred mebibytes, or a density under ten per cent -- any of
the three and the basis is read through a binary search over its rows sorted
by their rank tuple instead, which costs what a search costs and answers the
same numbers. A run reports every basis that takes it, by name, with the
condition and the numbers, because a table on the slow path is a fact about
the model's data rather than about this engine.

**The packing of a rank tuple is not always available, and an engine that
assumed it was would answer the wrong row.** The fallback packs the rank
tuple into one integer only where ``prod(sizes)`` fits the type -- the same
number the grid's own overflow condition is about. Above it the search is
lexicographic over the tuple itself, because a packing whose radix has
overflowed maps two different tuples onto one integer: with axes of
``2**32 + 1`` keys, ``(0, 2**32)`` and ``(1, 0)`` pack onto the same value
under a radix one short, and a table carrying the first would answer it for
the second.

**A hit is an answer the basis can give.** The rank tuple lands on a row, and
that row's answer cell is one section 11.1.24 admits -- a blank or non-finite
answer cell at a key a query reaches is a *miss*, decided by the read's own
miss policy, not a defect in the table. A null query key is a miss on the same
rule: the absent code is a code no string is ever minted, so it selects
nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple

import jax
import jax.numpy as jnp
import numpy as np

from .checks import flag, spelled_position
from .interning import ABSENT
from .typed import JNP_OF, DomainRefused

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .interning import Dictionary
    from .typed import Carrier, Value

__all__ = [
    "ANY_BASIS",
    "Axis",
    "Basis",
    "Grid",
    "Landing",
    "SortedTuples",
    "Storage",
    "answer_at",
    "build",
    "conditions_met",
    "positions_of",
]

_LOOKUP: Final = "11.1.24"
_JOIN: Final = "11.1.2"

# The widest flat index this engine holds, which is the signed integer XLA
# computes it in.
MAX_FLAT_INDEX: Final[int] = 2**63 - 1

# Below this share of the grid's cells, the holes cost more than the search
# does. The kernel's own figure, and its own reason.
MIN_DENSITY: Final[float] = 0.10

# The same figure as the exact rational the condition is judged with, so
# that one number decides and the other reads it. A capacity of eighteen
# quintillion has no exact double, and a density judged as a float share
# would turn on a rounding at exactly the sizes the fallback exists for; a
# reciprocal taken in integers would be exact only for a threshold that is
# one over a whole number, which is a constraint on the constant nobody
# reading it would know about. A limited-denominator fraction is exact for
# any threshold anybody would write, and 0.10 is 1/10 under it.
_SHARE: Final[Fraction] = Fraction(MIN_DENSITY).limit_denominator()

# The largest dense grid this engine builds, in bytes of the value array.
MAX_VALUE_BYTES: Final[int] = 100 * 1024 * 1024
_BYTES_PER_CELL: Final[int] = 8

# 11.1.24's closed interval: where a whole number and a double still name the
# same value, so that a numeric key means one thing on both sides.
EXACT_KEY_LIMIT: Final[int] = 2**53

# Above this the flat index is carried in int64 rather than int32.
_INT32_LIMIT: Final[int] = 2**31 - 1

# Section 10's three spellings of a number that is not one, as an assumption
# payload carries them.
_NON_FINITE: Final[dict[str, float]] = {
    "NaN": math.nan,
    "Infinity": math.inf,
    "-Infinity": -math.inf,
}

# What each payload cell type is held in, and what a key column may be. A
# Boolean or a calendar day is a payload cell (section 15) and is not a key:
# 11.1.24 states the key domain as text against text, or a finite number
# against a number, and names every other pairing outside it.
_CELL_CARRIER: Final[dict[str, Carrier]] = {
    "f64": "f64",
    "i64": "i64",
    "bool": "bool",
    "str": "code",
}
_KEY_DTYPES: Final[frozenset[str]] = frozenset({"i64", "f64", "str"})

# What a duplicate key tuple means where one is met, for a basis read as a
# table. A join's right side says something else, and says it on its own
# registration.
_AMBIGUOUS = (
    "the basis is ambiguous at that tuple and the read refuses before selecting a value"
)


@dataclass(frozen=True, slots=True)
class Axis:
    """One key column of a basis, and how a key becomes a rank on it.

    Attributes:
        name: The column's own name in the payload.
        carrier: What its keys are held in -- a whole number or an interned
            code. A fractional key column refuses at :func:`build`, so an
            ``f64`` key column whose cells are all whole is an ``i64`` axis.
        ranks: The remap a text axis needs: code to rank, -1 where the basis
            carries no such string. Empty for an integer axis, whose rank is
            ``key - offset`` and needs no array at all -- which is what lets
            an axis of four billion keys exist at all, since the fallback it
            forces builds no grid to mark absence in.
        offset: The lowest key an integer axis carries, and 0 for a text one.
        size: How many ranks the axis has: the span for an integer axis, the
            number of distinct strings for a text one. The grid's own extent
            along this axis, and a factor of the capacity the conditions are
            judged on.

    """

    name: str
    carrier: Literal["i64", "code"]
    ranks: jax.Array
    offset: int
    size: int


@dataclass(frozen=True, slots=True)
class Grid:
    """A basis as one flat array, reached by arithmetic.

    Attributes:
        axes: One per key column, in the payload's own column order.
        strides: The mixed-radix multipliers, last axis 1.
        values: One cell per rank tuple, in the answer column's carrier.
        present: Whether the basis has a row at that cell.
        bad_answer: Whether that cell's answer is one 11.1.24 makes a miss -- not
            there, or not finite. Judged at the cells a query reaches, which
            is what this being a per-cell array rather than a table-wide
            verdict means.
        carrier: What the answer is held in. An ``f64`` for a lookup, which
            is 11.1.24's whole answer domain; a join brings whatever column
            the right side holds, so this is any of the four.

    """

    axes: tuple[Axis, ...]
    strides: tuple[int, ...]
    values: jax.Array
    present: jax.Array
    bad_answer: jax.Array
    carrier: Carrier


@dataclass(frozen=True, slots=True)
class SortedTuples:
    """A basis as its own rows, sorted by rank tuple and searched.

    Attributes:
        axes: One per key column, as the grid's.
        ranks: ``[rows, k]``, each row's rank tuple, in ascending
            lexicographic order.
        values: One per row, in the answer column's carrier.
        bad_answer: One per row, on 11.1.24's rule for an answer cell.
        packed: The mixed-radix packing of each row's rank tuple, where the
            capacity fits the index type, and None where it does not -- in
            which case the search compares the tuples themselves.
        carrier: What the answer is held in.

    """

    axes: tuple[Axis, ...]
    ranks: jax.Array
    values: jax.Array
    bad_answer: jax.Array
    packed: jax.Array | None
    carrier: Carrier


Storage = Grid | SortedTuples


@dataclass(frozen=True, slots=True)
class Basis:
    """What one payload is to the read that names it.

    A table says which of its columns is the answer and leaves the rest to be
    keys; a join's right side says neither, because its key is named on the
    node and every other column is one the join might bring. So the two
    arrive here the same way, with the second filling in what the first reads
    off the payload.

    Attributes:
        name: What a note and a refusal call this basis.
        keys: The key columns, or None to read them off the payload.
        answer: The answer column, or None for the payload's own ``value``.
        clause: What a refusal about this basis rests on.
        duplicates_mean: What one key tuple appearing twice means here, in
            the words of the clause that says so.

    """

    name: str = "this basis"
    keys: tuple[str, ...] | None = None
    answer: str | None = None
    clause: str = _LOOKUP
    duplicates_mean: str = _AMBIGUOUS


# What a payload is where the caller says nothing about it: a table, read
# for what it declares.
ANY_BASIS: Final[Basis] = Basis()


def conditions_met(rows: int, sizes: Sequence[int]) -> tuple[str, ...]:
    """Return the fallback conditions this key space meets, in deciding order.

    Three independent readings of one key space, each with its own sentence
    and its own numbers. A basis meeting two says both: a reader asking why a
    table is on the slow path is owed every reason it is, and the first is
    only the one that decided it.
    """
    capacity = math.prod(sizes)
    met: list[str] = []
    if capacity > MAX_FLAT_INDEX:
        met.append(
            f"its key space is {capacity} cells, wider than the "
            f"{MAX_FLAT_INDEX} a flat index holds"
        )
    if capacity * _BYTES_PER_CELL > MAX_VALUE_BYTES:
        met.append(
            f"a dense grid of {capacity} cells would be "
            f"{capacity * _BYTES_PER_CELL} bytes, above the {MAX_VALUE_BYTES} "
            "this engine builds one up to"
        )
    if rows * _SHARE.denominator < capacity * _SHARE.numerator:
        met.append(
            f"density is {rows / capacity:.4%} -- {rows} rows over {capacity} "
            f"cells -- below the {MIN_DENSITY:.0%} a dense grid is built at"
        )
    return tuple(met)


def validated_payload(
    payload: dict[str, Any], *, interning: Dictionary, basis: Basis = ANY_BASIS
) -> _Filled:
    """Validate the payload's own domain without constructing a lookup grid."""
    with jax.ensure_compile_time_eval():
        columns, rows = _sections(payload, basis)
        key_names, answer_name = _roles(columns, payload, basis)
        position = {name: index for index, name in enumerate(columns)}
        axes: list[Axis] = []
        ranked: list[list[int]] = []
        for name in key_names:
            cells = [row[position[name]] for row in rows]
            axis, ranks = _axis(name, payload, cells, interning, basis)
            axes.append(axis)
            ranked.append(ranks)
        _no_duplicate_tuple(ranked, rows, key_names, position, basis)
        carrier, values, bad = _answers(
            [row[position[answer_name]] for row in rows],
            payload,
            answer_name,
            interning,
            basis,
        )
        return _Filled(tuple(axes), ranked, values, bad, carrier)


def build(
    payload: dict[str, Any], *, interning: Dictionary, basis: Basis = ANY_BASIS
) -> tuple[Storage, str | None]:
    """Return the storage one payload takes, and the note a fallback earns.

    Raises:
        DomainRefused: If the payload is outside the domain the clause states
            for it -- no rows, a key column this vocabulary states no
            matching for, a key cell that is not a whole number or is not
            there, or one key tuple appearing twice.

    """
    # On the host, whether or not a trace is open. A basis is the payload's
    # own rows: it does not depend on the book, so a basis built inside a
    # trace would be a constant staged into every compiled program -- and,
    # worse, one that cannot be read back on the host, which is where the
    # duplicate-tuple test and the fallback decision live.
    with jax.ensure_compile_time_eval():
        filled = validated_payload(payload, interning=interning, basis=basis)
        axes = filled.axes
        rows = payload["rows"]
        sizes = tuple(axis.size for axis in axes)
        met = conditions_met(len(rows), sizes)
        strides = _strides(sizes)
        if met:
            return (
                _sorted_tuples(filled, sizes, strides),
                f"{basis.name} is read through the sorted-rows search rather "
                "than a dense grid: " + "; ".join(met),
            )
        return _grid(filled, strides), None


class Landing(NamedTuple):
    """Where one query lands, and what the basis has there.

    The two ways a key fails to answer are kept apart, because they are two
    different things to tell an actuary and they have two different next
    moves. A rank tuple that reaches no row is a key the basis does not
    carry: extend it. A rank tuple that reaches a row whose answer cell is
    not there, or is not finite, is a blank *at a reached key*: fill the
    cell. A single ``hit`` would have said "no rate here" to both.

    Attributes:
        position: The cell or the row each query reaches, clipped so that it
            is always safe to gather at. Not ``index``: a named tuple's field
            of that name overrides ``tuple.index`` and is a different thing
            from it.
        hit: The basis answers there -- reached a row, and that row's answer
            is one 11.1.24 admits.
        reached: The rank tuple lands on a row the basis carries, whatever
            that row's answer cell holds.

    """

    position: jax.Array
    hit: jax.Array
    reached: jax.Array


def positions_of(
    storage: Storage, keys: tuple[Value, ...], *, on_the_host: bool = True
) -> Landing:
    """Return where each query lands, and what the basis has there.

    Raises:
        DomainRefused: If a key is outside 11.1.24's bounded key domain -- a
            query key that is not finite, or one past the interval inside
            which a whole number and a double name the same value.

    """
    if len(keys) != len(storage.axes):
        message = f"{len(keys)} keys against {len(storage.axes)} axes"
        raise AssertionError(message)
    ranks: list[jax.Array] = []
    ok = jnp.ones((), dtype=bool)
    for axis, key in zip(storage.axes, keys, strict=True):
        rank, found = _rank_of(axis, key, on_the_host=on_the_host)
        ranks.append(rank)
        ok = ok & found
    if isinstance(storage, Grid):
        return _in_grid(storage, ranks, ok)
    return _in_rows(storage, ranks, ok)


def answer_at(
    storage: Storage,
    index: jax.Array,
    hit: jax.Array,
    *,
    missing: float | bool,
) -> jax.Array:
    """Return the answer at each position, with ``missing`` wherever there is none.

    The miss goes to a **positive** out-of-range index rather than to -1:
    ``jnp.take(mode="fill")`` wraps a negative index round to the end of the
    array and answers the last row, which is a wrong rate rather than a miss,
    and one shape of one bench disagreed until it was made positive.
    """
    beyond = storage.values.shape[0]
    return jnp.take(
        storage.values,
        jnp.where(hit, index, beyond),
        mode="fill",
        fill_value=missing,
    )


def _sections(
    payload: dict[str, Any], basis: Basis
) -> tuple[list[str], list[list[Any]]]:
    """Return the payload's column names and rows, refusing a basis with neither."""
    written = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(written, list) or not isinstance(rows, list):
        raise DomainRefused(
            what=f"{basis.name} carries no columns and rows to read",
            move="export the artifact again with the payload the entry declares",
            clause=basis.clause,
        )
    if not rows:
        raise DomainRefused(
            what=f"{basis.name} has no rows, so there is nothing for a key to select",
            move="supply the basis the model read, with its rows",
            clause=basis.clause,
        )
    return [str(column["name"]) for column in written], rows


def _roles(
    columns: list[str], payload: dict[str, Any], basis: Basis
) -> tuple[tuple[str, ...], str]:
    """Return the key columns in operand order and the answer column.

    A table's keys are ``columns`` with the answer removed, **in the
    ``columns`` order**: 11.1.24 says outright that ``dimensions`` is a set
    of names and that binding to it mis-keys a table whose columns stand in
    another order, silently.
    """
    answer = basis.answer or payload.get("value")
    if not isinstance(answer, str) or answer not in columns:
        raise DomainRefused(
            what=(
                f"{basis.name} does not name one answer column this read can "
                f"select from: it names {answer!r}"
            ),
            move="export the artifact again from the model that registered the basis",
            clause=basis.clause,
        )
    keys = basis.keys or tuple(name for name in columns if name != answer)
    absent = [name for name in keys if name not in columns]
    if absent:
        raise DomainRefused(
            what=(
                f"{basis.name} carries no column called {absent[0]!r}, which "
                "this read keys on"
            ),
            move="check the key against the columns the basis carries",
            clause=basis.clause,
        )
    if not keys:
        raise DomainRefused(
            what=f"{basis.name} has no key column, so nothing selects a row",
            move="supply a basis keyed by at least one column",
            clause=basis.clause,
        )
    if basis.keys is None and len(columns) - len(keys) != 1:
        raise DomainRefused(
            what=(
                f"{basis.name} leaves {len(columns) - len(keys)} columns over "
                "once its keys are taken, and a read selects exactly one answer"
            ),
            move="export the basis with one answer column beside its keys",
            clause=basis.clause,
        )
    return tuple(keys), answer


def _dtype_of(payload: dict[str, Any], name: str) -> str:
    """Return the neutral type one payload column declares."""
    for column in payload["columns"]:
        if str(column["name"]) == name:
            return str(column["dtype"])
    raise KeyError(name)  # pragma: no cover -- the caller checked the name


def _axis(
    name: str,
    payload: dict[str, Any],
    cells: list[Any],
    interning: Dictionary,
    basis: Basis,
) -> tuple[Axis, list[int]]:
    """Return one key column's axis and the rank each row takes on it."""
    dtype = _dtype_of(payload, name)
    if dtype not in _KEY_DTYPES:
        raise DomainRefused(
            what=(
                f"{basis.name} keys on {name!r}, which it carries as {dtype}: "
                "this clause states a matching for text against text and for "
                "a finite number against a number, and none for any other"
            ),
            move="key the read on a column of whole numbers or of text",
            clause=basis.clause,
        )
    if any(cell is None for cell in cells):
        raise DomainRefused(
            what=(
                f"{basis.name} carries a key cell in {name!r} that is not "
                "there, and a key that is not there selects nothing"
            ),
            move="fill the key column, or drop the rows that carry the gap",
            clause=basis.clause,
        )
    if dtype == "str":
        return _text_axis(name, [str(cell) for cell in cells], interning)
    return _integer_axis(name, cells, basis)


def _text_axis(
    name: str, cells: list[str], interning: Dictionary
) -> tuple[Axis, list[int]]:
    """Return a text axis: the run's own codes, remapped to ranks.

    The remap is indexed by code and is not an ordering over text -- the
    codes are this run's interning and mean nothing outside it, and a key is
    matched by equality alone (11.1.24). What the array does is turn one
    equality test into one gather.
    """
    codes = [interning.code_for(cell) for cell in cells]
    distinct = sorted(set(codes))
    rank_of = {code: rank for rank, code in enumerate(distinct)}
    remap = np.full(distinct[-1] + 1, -1, dtype=np.int64)
    for code, rank in rank_of.items():
        remap[code] = rank
    axis = Axis(
        name=name,
        carrier="code",
        ranks=jnp.asarray(remap),
        offset=0,
        size=len(distinct),
    )
    return axis, [rank_of[code] for code in codes]


def _integer_axis(name: str, cells: list[Any], basis: Basis) -> tuple[Axis, list[int]]:
    """Return an integer axis: the rank is the key's distance from the lowest.

    A key column of doubles whose cells are all whole is one of these, which
    is what every basis a gaspatchio model registers turns out to be -- the
    producer writes ages and durations as ``f64``. A fractional cell refuses,
    as the producer's own registration refuses it, because the position rule
    below has nowhere to put half a key.
    """
    keys: list[int] = []
    for cell in cells:
        number = float(cell)
        if not math.isfinite(number) or number != math.trunc(number):
            raise DomainRefused(
                what=(
                    f"{basis.name} carries the key {cell!r} in {name!r}, which "
                    "is not a whole number, and a key space is indexed by "
                    "whole numbers"
                ),
                move=("scale the key column to whole numbers, or key the read on text"),
                clause=basis.clause,
            )
        if abs(number) > EXACT_KEY_LIMIT:
            raise DomainRefused(
                what=(
                    f"{basis.name} carries the key {cell!r} in {name!r}, past "
                    "the interval inside which a whole number and a double "
                    "name the same value"
                ),
                move="rescale the key column so its keys meet inside it",
                clause=basis.clause,
            )
        keys.append(int(number))
    offset = min(keys)
    axis = Axis(
        name=name,
        carrier="i64",
        ranks=jnp.zeros((0,), dtype=jnp.int64),
        offset=offset,
        size=max(keys) - offset + 1,
    )
    return axis, [key - offset for key in keys]


def _answers(
    cells: list[Any],
    payload: dict[str, Any],
    name: str,
    interning: Dictionary,
    basis: Basis,
) -> tuple[Carrier, jax.Array, jax.Array]:
    """Return the answer column's carrier, its values, and each cell's miss verdict.

    A column of a type this engine does not hold as an answer refuses here.
    Section 15 carries a ``date`` or a ``list[T]`` column in a payload, and
    the reference producer answers a join bringing one, so for a join the
    refusal is this engine's own limit and names Polars as the move; a
    lookup's answer is an ``f64`` in 11.1.24's own words, so a table answering
    anything else was not written by a producer of this format.
    """
    dtype = _dtype_of(payload, name)
    carrier = _CELL_CARRIER.get(dtype)
    if carrier is None and basis.clause == _JOIN:
        raise DomainRefused(
            what=(
                f"{basis.name} brings the column {name!r} as {dtype}, and this "
                "engine holds a column a join brings only as a number, a whole "
                "number, a flag or text"
            ),
            move=(
                "run this model on Polars, which brings it; or drop the column "
                "from the right side before the join if the model does not use it"
            ),
            clause=_JOIN,
        )
    if carrier is None:
        raise DomainRefused(
            what=(
                f"the answer column {name!r} is carried as {dtype}, and a "
                "lookup answers a number (an f64)"
            ),
            move="export the basis with an answer column this grammar writes",
            clause=basis.clause,
        )
    # Gated on the carrier, because section 10's three spellings are a rule
    # about a column declared ``f64`` and nothing else: "an ``f64`` column
    # holding `"NaN"` holds that text, an ``f64`` column holding it holds the
    # number". Applied before the carrier was known, this quietly rewrote a
    # plan identifier spelled "Infinity" into an infinity -- a str answer
    # cell turned into a number nobody wrote.
    read = (
        [
            _NON_FINITE.get(cell, cell) if isinstance(cell, str) else cell
            for cell in cells
        ]
        if carrier == "f64"
        else list(cells)
    )
    bad = [
        cell is None or (carrier == "f64" and not math.isfinite(float(cell)))
        for cell in read
    ]
    # ``Any`` because the cells of one column are of one type and the four
    # this grammar writes have no common one narrower than that; numpy is
    # handed the type on the next line and refuses a cell that is not it.
    held: list[Any] = (
        [ABSENT if cell is None else interning.code_for(str(cell)) for cell in read]
        if carrier == "code"
        else [_neutral(carrier) if cell is None else _as_entered(cell) for cell in read]
    )
    return (
        carrier,
        jnp.asarray(np.asarray(held, dtype=np.dtype(JNP_OF[carrier]))),
        jnp.asarray(np.asarray(bad, dtype=bool)),
    )


def _as_entered(cell: Any) -> Any:  # noqa: ANN401 -- one cell of any carrier
    """Return a cell as data enters: a negative zero written as zero.

    Section 12.3 writes a data -0.0 as 0.0 where an assumption table enters,
    before it is hashed or read, so a sign-reading operation over a looked-up
    zero sees +0.0 on every side.
    """
    if isinstance(cell, float) and cell == 0.0:
        return 0.0
    return cell


def _neutral(carrier: Carrier) -> float | bool:
    """Return what stands in an answer array where the cell is not there."""
    if carrier == "f64":
        return math.nan
    if carrier == "bool":
        return False
    return 0


def _no_duplicate_tuple(
    ranked: list[list[int]],
    rows: list[list[Any]],
    key_names: tuple[str, ...],
    position: dict[str, int],
    basis: Basis,
) -> None:
    """Refuse a basis carrying one key tuple twice, naming the tuple.

    Whether or not the two answers agree: a basis that answers a key twice
    has not said which row a read selects, and an engine that took the first
    would be answering from the payload's order, which no fingerprint of it
    is taken over.

    Raises:
        DomainRefused: If any key tuple appears more than once.

    """
    seen: set[tuple[int, ...]] = set()
    for index, tuple_of in enumerate(zip(*ranked, strict=True)):
        if tuple_of in seen:
            written = ", ".join(
                f"{name}={rows[index][position[name]]!r}" for name in key_names
            )
            raise DomainRefused(
                what=(
                    f"{basis.name} carries the key tuple ({written}) more than "
                    f"once, and {basis.duplicates_mean}"
                ),
                move="take the basis back to one row per key tuple",
                clause=basis.clause,
            )
        seen.add(tuple_of)


def _strides(sizes: tuple[int, ...]) -> tuple[int, ...]:
    """Return the mixed-radix multipliers for these axis extents, last one 1."""
    strides = [1] * len(sizes)
    for index in range(len(sizes) - 2, -1, -1):
        strides[index] = strides[index + 1] * sizes[index + 1]
    return tuple(strides)


def _flat(ranked: list[list[int]], strides: tuple[int, ...]) -> list[int]:
    """Return each row's rank tuple as one mixed-radix integer."""
    return [
        sum(rank * stride for rank, stride in zip(tuple_of, strides, strict=True))
        for tuple_of in zip(*ranked, strict=True)
    ]


@dataclass(frozen=True, slots=True)
class _Filled:
    """One payload read through: its axes, its rows' ranks, and its answers."""

    axes: tuple[Axis, ...]
    ranked: list[list[int]]
    values: jax.Array
    bad: jax.Array
    carrier: Carrier


def _grid(filled: _Filled, strides: tuple[int, ...]) -> Grid:
    """Return the dense grid these rows fill, with a validity bit per cell."""
    axes, carrier = filled.axes, filled.carrier
    capacity = math.prod(axis.size for axis in axes)
    flat = np.asarray(_flat(filled.ranked, strides), dtype=np.int64)
    cells = np.full(capacity, _neutral(carrier), dtype=np.dtype(JNP_OF[carrier]))
    cells[flat] = np.asarray(filled.values)
    present = np.zeros(capacity, dtype=bool)
    present[flat] = True
    unanswerable = np.zeros(capacity, dtype=bool)
    unanswerable[flat] = np.asarray(filled.bad)
    return Grid(
        axes=axes,
        strides=strides,
        values=jnp.asarray(cells),
        present=jnp.asarray(present),
        bad_answer=jnp.asarray(unanswerable),
        carrier=carrier,
    )


def _sorted_tuples(
    filled: _Filled, sizes: tuple[int, ...], strides: tuple[int, ...]
) -> SortedTuples:
    """Return the rows sorted by rank tuple, packed where the packing is sound."""
    ranks = np.asarray(list(zip(*filled.ranked, strict=True)), dtype=np.int64)
    # Last key is the least significant, which is what lexicographic order by
    # the tuple means and what the packing below agrees with.
    order = np.lexsort(
        tuple(ranks[:, index] for index in range(ranks.shape[1] - 1, -1, -1))
    )
    capacity = math.prod(sizes)
    packed = (
        jnp.asarray(np.asarray(_flat(filled.ranked, strides), dtype=np.int64)[order])
        if capacity <= MAX_FLAT_INDEX
        else None
    )
    return SortedTuples(
        axes=filled.axes,
        ranks=jnp.asarray(ranks[order]),
        values=jnp.asarray(np.asarray(filled.values)[order]),
        bad_answer=jnp.asarray(np.asarray(filled.bad)[order]),
        packed=packed,
        carrier=filled.carrier,
    )


def _rank_of(
    axis: Axis, key: Value, *, on_the_host: bool = True
) -> tuple[jax.Array, jax.Array]:
    """Return each query key's rank on one axis, and whether the axis carries it."""
    if axis.carrier == "code":
        return _code_rank(axis, key)
    return _integer_rank(axis, key, on_the_host=on_the_host)


def _code_rank(axis: Axis, key: Value) -> tuple[jax.Array, jax.Array]:
    """Return a text key's rank, with a code from outside the basis at no rank.

    A code the basis never carried -- a string minted after it was built, and
    the absent code a null key takes -- is outside the remap and is a miss
    rather than an error: 11.1.24 makes a null query key a miss, and a string
    the basis does not carry is a key with no row, which is the same answer.
    """
    if key.carrier != "code":
        raise DomainRefused(
            what=(
                f"the key on {axis.name!r} is text in this basis and the query "
                f"supplies {key.carrier}, which this clause states no matching for"
            ),
            move="key the read on the column whose values the basis carries",
            clause=_LOOKUP,
        )
    codes = key.array.astype(jnp.int64)
    inside = (codes >= 0) & (codes < axis.ranks.shape[0])
    rank = jnp.take(axis.ranks, jnp.where(inside, codes, 0), mode="clip")
    return rank, inside & (rank >= 0)


def _integer_rank(
    axis: Axis, key: Value, *, on_the_host: bool = True
) -> tuple[jax.Array, jax.Array]:
    """Return a numeric key's rank, which is its distance from the axis's lowest.

    A fractional query key is valid and matches nothing: 11.1.24 admits one
    inside its interval, and no whole-number key equals it. A query key that
    is not finite, or is past the interval, is outside the bounded domain and
    refuses rather than answering.

    Raises:
        DomainRefused: If a query key is not finite or is past 11.1.24's
            closed interval.

    """
    if key.carrier not in ("i64", "f64"):
        raise DomainRefused(
            what=(
                f"the key on {axis.name!r} is a number in this basis and the "
                f"query supplies {key.carrier}, which this clause states no "
                "matching for"
            ),
            move="key the read on the column whose values the basis carries",
            clause=_LOOKUP,
        )
    numbers = key.array
    whole = jnp.ones((), dtype=bool)
    if key.carrier == "f64":
        _outside_the_interval(axis, numbers, on_the_host=on_the_host)
        whole = numbers == jnp.round(numbers)
        numbers = jnp.round(numbers)
    rank = numbers.astype(jnp.int64) - axis.offset
    return rank, whole & (rank >= 0) & (rank < axis.size)


def _outside_the_interval(axis: Axis, numbers: jax.Array, *, on_the_host: bool) -> None:
    """Report a query key this clause states no matching for.

    Where every key of the read arrived with the book this is answered here
    and now, and the report names the first one and counts the rest. Where a
    calculation produced one it is a flag instead, read at completion with
    every output withheld -- because inside a program being built there is no
    count to read, and a check that read one would be reading it before the
    calculation that decides it has run.

    Raises:
        DomainRefused: If a key that arrived is not finite or is past the
            interval.

    """
    outside = ~jnp.isfinite(numbers) | (jnp.abs(numbers) > EXACT_KEY_LIMIT)
    if not on_the_host:
        flag("lookup.key_range", outside, where=f"the key on {axis.name!r}")
        return
    caught = int(jnp.sum(outside))
    if not caught:
        return
    flat = numbers.reshape(-1)
    first = int(jnp.argmax(outside.reshape(-1)))
    where = spelled_position(first, numbers.shape)
    raise DomainRefused(
        what=(
            f"{caught} of the keys read on {axis.name!r} are outside the "
            f"interval this clause states a matching over -- the first at "
            f"{where}, which is {float(flat[first])!r}"
        ),
        move=(
            "guard the key with a when/then, so the model says what it means "
            "where the key is not a number the basis could carry"
        ),
        clause=_LOOKUP,
        count=caught,
    )


def _in_grid(storage: Grid, ranks: list[jax.Array], ok: jax.Array) -> Landing:
    """Return the flat cell each query reaches, and what the basis has there."""
    index = jnp.zeros_like(ranks[0])
    for rank, stride in zip(ranks, storage.strides, strict=True):
        index = index + rank * stride
    capacity = storage.values.shape[0]
    safe = jnp.where(ok, index, 0)
    reached = ok & storage.present[safe]
    hit = reached & ~storage.bad_answer[safe]
    if capacity <= _INT32_LIMIT:
        # The fit check: an int32 position keeps the
        # arithmetic inside the gather rather than materialising a wider
        # index array for the whole batch.
        return Landing(safe.astype(jnp.int32), hit, reached)
    return Landing(safe, hit, reached)


def _in_rows(storage: SortedTuples, ranks: list[jax.Array], ok: jax.Array) -> Landing:
    """Return the row each query finds, and whether its whole tuple is that row's."""
    query = jnp.stack(ranks, axis=-1)
    rows = storage.ranks.shape[0]
    if storage.packed is not None:
        wanted = jnp.zeros_like(ranks[0])
        for rank, stride in zip(ranks, _strides_of(storage), strict=True):
            wanted = wanted + rank * stride
        found = jnp.searchsorted(storage.packed, wanted)
    else:
        found = _lexicographic(storage.ranks, query)
    safe = jnp.clip(found, 0, rows - 1)
    same = jnp.all(storage.ranks[safe] == query, axis=-1)
    reached = ok & (found < rows) & same
    return Landing(safe, reached & ~storage.bad_answer[safe], reached)


def _strides_of(storage: SortedTuples) -> tuple[int, ...]:
    """Return the packing's multipliers, from the axes the rows were packed on."""
    return _strides(tuple(axis.size for axis in storage.axes))


def _lexicographic(ranks: jax.Array, query: jax.Array) -> jax.Array:
    """Return the first row whose rank tuple is not below each query's.

    A binary search comparing the tuples element by element, in exactly
    ``rows.bit_length()`` passes -- which is the depth of a search over
    ``rows + 1`` candidate positions and is the fewest that always converges.
    Taken this way rather than by packing because the caller reaching here is
    the one whose key space has no packing: two tuples would share an integer
    and the search would find the wrong row.
    """
    rows = ranks.shape[0]
    # Every shape below is the query's own minus its last axis, which is the
    # rank tuple: one search per policy for a per-policy key, and one per
    # policy per period where the keys are per-period (11.1.18).
    width = query.shape[:-1]
    lo = jnp.zeros(width, dtype=jnp.int64)
    hi = jnp.full(width, rows, dtype=jnp.int64)

    def step(
        _pass: int, carried: tuple[jax.Array, jax.Array]
    ) -> tuple[jax.Array, jax.Array]:
        low, high = carried
        middle = (low + high) // 2
        below = _tuple_below(ranks[jnp.clip(middle, 0, rows - 1)], query)
        return jnp.where(below, middle + 1, low), jnp.where(below, high, middle)

    settled, _high = jax.lax.fori_loop(0, rows.bit_length(), step, (lo, hi))
    return jnp.asarray(settled)


def _tuple_below(left: jax.Array, right: jax.Array) -> jax.Array:
    """Return whether each row of ``left`` is lexicographically below ``right``."""
    below = jnp.zeros(left.shape[:-1], dtype=bool)
    equal = jnp.ones(left.shape[:-1], dtype=bool)
    for position in range(left.shape[-1]):
        below = below | (equal & (left[..., position] < right[..., position]))
        equal = equal & (left[..., position] == right[..., position])
    return below
