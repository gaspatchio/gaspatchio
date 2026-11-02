# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The two groups a run can refuse in before it computes anything, in words.

Every refusal here names the actuarial thing, where it is, how many rows it
is about, the next move, and the clause of the specification it rests on.
One report carries every finding rather than the first one found: an engine
that stopped on each defect in turn would send a reader round the edit-run
loop once per column, and the loop is the thing this framework treats as the
budget.

**The tree group and the inputs group are told apart by what they needed.**
A finding from the document and its payloads alone was available before any
book was read, so nothing about the run cost anything. A finding from the
book was available before anything was compiled. Both close with "Nothing was
computed."; the third group, which the plan's completion stage builds, closes
with "No results were published." -- a different fact about the clock and
about what is on disk.

**The null refusal lives here.** A null in a column a lowered node reads as a
value refuses with its row count, rather than travelling into a trace that has
no representation for one. That is what lets the absence family answer what it
answers (see :mod:`gaspatchio_jax.lowerings.missing`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final

import numpy as np
import polars as pl

from gaspatchio.engines.report import Refusal

from .checks import CHECKS, spelled_position

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import jax

    from gaspatchio.engines.format import ExecutionInspection

    from .checks import Carried, FlagBook

__all__ = [
    "Finding",
    "completion_refusals",
    "document_refusals",
    "domain_refusal",
    "dtype_name",
    "findings_of",
    "findings_tallied",
    "input_mismatch",
    "input_missing",
    "merged_findings",
    "read_as_i64",
]

# The one profile this engine reads. The audit profile carries no operation
# trees, so there is nothing to lower and the refusal says which to export.
EXECUTABLE: Final = "executable"


def document_refusals(
    document: Mapping[str, Any], inspection: ExecutionInspection
) -> list[Refusal]:
    """Return what is wrong with the document itself, before any node is read."""
    refusals = [
        Refusal(
            group="tree",
            where=finding.where,
            count=None,
            what=finding.message,
            move=(
                "export the artifact again from the model that wrote it, so "
                "the document and its digests agree"
            ),
            clause=finding.section,
        )
        for finding in inspection.validation.findings
        if finding.severity == "error"
    ]
    profile = document.get("profile")
    if profile != EXECUTABLE:
        refusals.append(
            Refusal(
                group="tree",
                where="profile",
                count=None,
                what=(
                    f"this artifact is the {profile!r} profile, which carries "
                    "no operation trees to lower"
                ),
                move='export it with profile="executable"',
                clause="8.1",
            )
        )
    # The general move is the one a missing or unverified payload needs. A
    # finding that names a move of the model's own -- the line a column was
    # written at -- states that one instead, and only that one.
    refusals.extend(
        Refusal(
            group="tree",
            where=finding.where,
            count=None,
            what=finding.message,
            move=finding.move
            or "export the artifact again with the payloads it declares",
            clause=finding.check,
        )
        for finding in inspection.findings
    )
    return refusals


# Where an arriving column's requirement is stated: the node record, which
# carries the column, its type and its shape. A node id is not a clause -- it
# names *which* requirement, which belongs in the sentence.
_INPUT_CLAUSE: Final = "8.2"

# What a null value is: 11.1.13 keeps a null and a NaN two absences, so a
# null read as a value is refused rather than carried as a NaN, and fill_null
# is the model's own move. A null key cites nothing: 11.1.24 makes one a miss
# its read's own policy answers, and refusing it is a limit of this engine,
# which can carry an absent key only as a text code. The sentence says so.
_NULL_VALUE_CLAUSE: Final = "11.1.13"

# The clause the type vocabulary rests on: every integer is ``i64``, and a
# width wider than one is judged on its values.
_TYPES_CLAUSE: Final = "10"


def input_missing(node_id: str, column: str) -> Refusal:
    """Return the refusal for an input column the book does not carry."""
    return Refusal(
        group="inputs",
        where=column,
        count=None,
        what=(
            f"the artifact reads {column!r} at node {node_id} and this book "
            "does not carry it"
        ),
        move=f"supply {column!r}, under the name the artifact's input node gives it",
        clause=_INPUT_CLAUSE,
    )


def domain_refusal(node_id: str, refused: Exception) -> Refusal:
    """Return the refusal one domain refusal met while lowering stands for.

    The ``tree`` group by default: what was met is ordinarily a fact about
    the operation tree and the types the records declare, knowable without
    the book. Nothing was published and nothing could have been, which is the
    claim that group's closing sentence makes.

    A refusal about *values* says so on itself and keeps its own group. A key
    the basis does not carry is the case: where every key arrived with the
    book it was knowable before anything was compiled, which is the inputs
    group, and where a calculation produced one it was not, which is
    completion. The lowering knows which and the report says which.
    """
    what = getattr(refused, "what", str(refused))
    move = getattr(refused, "move", "run this model on Polars")
    clause = getattr(refused, "clause", None)
    return Refusal(
        group=getattr(refused, "group", "tree"),
        where=node_id,
        count=getattr(refused, "count", None),
        what=what,
        move=move,
        clause=clause or None,
    )


def _not_carried(
    requirement: Any,  # noqa: ANN401 -- InputRequirement is the core's frozen dataclass
    series: pl.Series,
) -> Refusal | None:
    """Return the refusal for a column of a type this engine holds no value of."""
    stated = requirement.dtype
    if stated not in _NOT_CARRIED:
        return None
    return Refusal(
        group="inputs",
        where=series.name,
        count=None,
        what=(
            f"the artifact reads {series.name!r} as {stated} at node "
            f"{requirement.node_id}, and this engine carries no date and "
            "time: the type is section 10's, and holding one here is a "
            "limit of this engine, not a fault in the model or the book"
        ),
        move="run this model on Polars, which carries a date and time",
        clause=_TYPES_CLAUSE,
    )


def input_mismatch(
    requirement: Any,  # noqa: ANN401 -- InputRequirement is the core's frozen dataclass
    series: pl.Series,
    *,
    keys_only: bool = False,
) -> Refusal | None:
    """Return what is wrong with one arriving column, or None if nothing is.

    Three readings in the order a reader wants them: the type the artifact
    declared against the type that arrived, the shape, and the null count --
    counted over a per-period column's own cells as well as its rows, because
    a period carrying no value is as much a null as a policy carrying none.

    **The null refusal is narrowed for a column every read of which is a
    key.** Section 11.1.24 makes a null key a miss, answered by the read's own
    policy, so such a column travels into the trace as the absent code rather
    than refusing at the door -- and only for text, which is where an absent
    code exists. There is no number the absent key could be carried as that
    is not also a key some basis could legitimately hold, so a null in a
    numeric key column refuses here and says which.
    """
    stated = requirement.dtype
    refused = _past_i64(series) or _not_carried(requirement, series)
    if refused is not None:
        return refused
    arrived = dtype_name(series.dtype)
    if arrived != stated:
        return Refusal(
            group="inputs",
            where=series.name,
            count=None,
            what=(
                f"the artifact reads {series.name!r} as {stated} at node "
                f"{requirement.node_id} and this book carries it as {arrived}"
            ),
            move=f"cast {series.name!r} to {stated} before the run",
            clause=_INPUT_CLAUSE,
        )
    missing = _absent_cells(series)
    if not missing:
        return None
    if keys_only and stated == "str":
        return None
    if keys_only:
        return Refusal(
            group="inputs",
            where=series.name,
            count=missing,
            what=(
                f"{series.name!r} is read only as a key and carries values "
                "that are not there. This engine carries an absent key only "
                "as a code, which only text has, so a missing number here is "
                "a limit of this engine and not a fault in the model"
            ),
            move=(
                "guard the read with a when/then, or fill the gaps, so the "
                "model says what a missing key means here"
            ),
            clause=None,
        )
    return Refusal(
        group="inputs",
        where=series.name,
        count=missing,
        what=(
            f"{series.name!r} carries values that are not there, and this "
            "engine states no answer over a null"
        ),
        move=(
            "fill the gaps with fill_null, or drop the policies that "
            "carry them, so the model says what a missing value means"
        ),
        clause=_NULL_VALUE_CLAUSE,
    )


def _absent_cells(series: pl.Series) -> int:
    """Return how many values of one column are not there, cells and rows alike.

    A policy with no column at all is one absence; a policy whose third period
    carries no value is another. An empty list is neither -- it is a policy
    with a column of no periods -- so the count is taken as the periods each
    row has less the periods that carry a value, which leaves an empty row at
    nought.
    """
    outer = int(series.null_count())
    if not isinstance(series.dtype, pl.List):
        return outer
    held = series.list.len() - series.list.drop_nulls().list.len()
    return outer + int(held.fill_null(0).sum())


# Section 10's scalar names, and the Polars types they arrive in.
_DTYPE_NAMES: dict[type[pl.DataType], str] = {
    pl.Int64: "i64",
    pl.Float64: "f64",
    pl.Boolean: "bool",
    pl.String: "str",
    pl.Date: "date",
}


# The types section 10 names that this engine holds no value of: a book
# column declared as one is refused by its type, rather than told to become
# the type it already is.
_NOT_CARRIED: Final[frozenset[str]] = frozenset({"datetime", "list[datetime]"})

# The integer widths every value of which an ``i64`` holds exactly.
_NARROWER_THAN_I64: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.Int8, pl.Int16, pl.Int32, pl.UInt8, pl.UInt16, pl.UInt32}
)

# The float widths narrower than ``f64``: every value of one is a double
# exactly, so it is read as ``f64``, as the producer reads it.
_NARROWER_THAN_F64: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.Float16, pl.Float32}
)

# The integer widths an ``i64`` may not hold: read as one only where every
# value fits, as the producer reads them where the book enters the frame.
_WIDER_THAN_I64: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.UInt64, pl.Int128, pl.UInt128}
)


def _widened(dtype: pl.DataType, *, wide: bool = False) -> pl.DataType:
    """Return ``dtype`` with a narrow integer, or a list of one, read as ``i64``.

    A narrow float, or a list of one, is read as ``f64`` the same way. With
    ``wide``, a ``UInt64``, ``Int128`` or ``UInt128`` is read as ``i64``
    too: the caller has found every value fits.
    """
    base = dtype.base_type()
    if base in _NARROWER_THAN_I64 or (wide and base in _WIDER_THAN_I64):
        return pl.Int64()
    if base in _NARROWER_THAN_F64:
        return pl.Float64()
    if isinstance(dtype, pl.Decimal):
        # A fixed-point decimal is the number it denotes: with places the
        # double nearest it, with none a whole number -- ``i64`` where its
        # digits always fit or every value does, else ``Int128`` for the
        # wide rule to judge.
        if (dtype.scale or 0) > 0:
            return pl.Float64()
        precision = dtype.precision if dtype.precision is not None else 38
        return pl.Int64() if precision <= _DECIMAL_DIGITS_I64 or wide else pl.Int128()
    if isinstance(dtype, pl.List) and isinstance(dtype.inner, pl.DataType):
        inner = _widened(dtype.inner, wide=wide)
        return dtype if inner == dtype.inner else pl.List(inner)
    return dtype


# The most digits a decimal of no places carries with every value an ``i64``.
_DECIMAL_DIGITS_I64: Final = 18


def _wide_depth(dtype: pl.DataType, depth: int = 0) -> int | None:
    """Return how many lists deep ``dtype`` holds an integer wider than ``i64``.

    A fixed-point decimal of no places whose digits may pass ``i64`` counts.
    """
    if dtype.base_type() in _WIDER_THAN_I64:
        return depth
    if (
        isinstance(dtype, pl.Decimal)
        and (dtype.scale or 0) == 0
        and (dtype.precision is None or dtype.precision > _DECIMAL_DIGITS_I64)
    ):
        return depth
    if isinstance(dtype, pl.List) and isinstance(dtype.inner, pl.DataType):
        return _wide_depth(dtype.inner, depth + 1)
    return None


def _cells_past_i64(series: pl.Series, depth: int) -> pl.Series:
    """Return the values of a wide integer column that no ``i64`` carries.

    Asked of the non-strict cast itself, which answers null exactly where a
    value does not fit; an absent value is not a value out of range.
    """
    values = series
    for _ in range(depth):
        values = values.explode(empty_as_null=True)
    return values.filter(
        values.is_not_null() & values.cast(pl.Int64, strict=False).is_null()
    )


def read_as_i64(book: pl.DataFrame) -> pl.DataFrame:
    """Return the book with every integer an ``i64`` holds read as ``i64``.

    The record names every integer ``i64`` (section 10), and the reference
    producer reads an ``Int32`` sum assured -- or an ``Int8`` through
    ``UInt32`` column, or a list of one -- as ``Int64`` where it enters the
    frame, so the run computes in the type its record states; and a
    ``Float32`` or ``Float16`` column, or a list of one, as ``Float64``. This
    door does the same, so the book the producer ran is the book this engine
    takes: refusing it with "cast 'sa' to i64" would send the reader to do by
    hand what the producer did for them. The widening is exact, so the book's
    digest -- which tags a column by its neutral type, not its width -- does
    not move.

    A ``UInt64``, ``Int128`` or ``UInt128`` column is one rule with the
    producer's door: read as ``i64`` where every value fits, and left in its
    width where one does not, to be refused by name where the tree reads it
    (:func:`input_mismatch`).
    """
    casts: dict[str, pl.DataType] = {}
    for name, dtype in book.schema.items():
        depth = _wide_depth(dtype)
        fits = depth is not None and _cells_past_i64(book[name], depth).is_empty()
        read = _widened(dtype, wide=fits)
        if read != dtype:
            casts[name] = read
    return book.cast(pl.Schema(casts), strict=True) if casts else book


def _past_i64(series: pl.Series) -> Refusal | None:
    """Return the refusal for a column still wider than ``i64``, or None.

    :func:`read_as_i64` reads such a column as ``i64`` where every value
    fits, so one still that wide here holds a value no ``i64`` carries. The
    record names it ``i64`` and this engine computes in ``i64``, so carrying
    it would wrap; it is refused by that value, with the two moves the
    producer's own refusal names.
    """
    depth = _wide_depth(series.dtype)
    if depth is None:
        return None
    past = _cells_past_i64(series, depth)
    if past.is_empty():
        return None
    name = series.name
    return Refusal(
        group="inputs",
        where=name,
        count=past.len(),
        what=(
            f"{name!r} arrives as {series.dtype} and holds {past[0]}, which is "
            "outside the signed 64-bit range, so it keeps that width; this "
            "engine carries every integer the record names as i64, and "
            "arithmetic on such a column is refused rather than wrapped"
        ),
        move=(
            f"if {name!r} is an identifier, cast it to String in the book the "
            "model is run and exported over, where to_text() reads it "
            "unchanged; if it is a quantity, choose the narrower type it is "
            "carried in and state it on the book before the run"
        ),
        clause=_TYPES_CLAUSE,
    )


def dtype_name(dtype: pl.DataType) -> str:
    """Return the artifact's own name for one arriving column's type."""
    for polars_type, name in _DTYPE_NAMES.items():
        if dtype == polars_type:
            return name
    if isinstance(dtype, pl.List):
        # ``inner`` is typed as either a type or an instance; a list built by
        # a frame always carries an instance, and a type there would be a
        # column nothing has read the element type of.
        inner = dtype.inner
        named = dtype_name(inner) if isinstance(inner, pl.DataType) else str(inner)
        return f"list[{named}]"
    return str(dtype)


@dataclass(frozen=True, slots=True)
class Finding:
    """What one check caught, in terms that survive being batched.

    A run over a million policies is a run over many batches, and a check
    caught what it caught in whichever of them the cell fell in. What a
    reader needs is one sentence per check: which column, how many cells in
    the whole book, and one of them to look at. So a finding carries the
    count and the first position *in the book*, and two findings of one check
    add up.

    Attributes:
        name: The check, keyed into :data:`CHECKS`.
        where: The node or column it is about.
        count: How many cells it caught.
        first: The first cell it caught, as a reader would name it.
        at: The same cell as the numbers behind that sentence -- the policy
            and the period -- so two findings of one check can be ordered
            without reading each other's prose. A wording change to
            :func:`spelled_position` would silently reorder them otherwise.
        note: The sentence this reports where it is not a refusal, and None
            where it is.

    """

    name: str
    where: str
    count: int
    first: str
    at: tuple[int, int]
    note: str | None = None

    @property
    def refuses(self) -> bool:
        """Return whether this finding withholds the run's results."""
        return self.note is None

    def refusal(self, *, operand_is_computed: bool = True) -> Refusal:
        """Return this finding as the refusal a reader is handed."""
        check = CHECKS[self.name]
        return Refusal(
            group=check.stage_for(operand_is_computed=operand_is_computed),
            where=self.where or self.name,
            count=self.count,
            what=f"{check.what} ({self.name}, first at {self.first})",
            move=check.move,
            clause=check.clause,
        )

    def sentence(self) -> str:
        """Return this finding as the note a reader is handed, with its count."""
        return f"{self.count} {self.note}"


def findings_of(flags: FlagBook, rows: np.ndarray | None = None) -> tuple[Finding, ...]:
    """Return one finding per check that caught something in this batch.

    ``rows`` is which policy of the book each row of the batch is, so the
    first position a finding names is a policy of the book rather than a
    policy of a batch nobody asked for.
    """
    found: list[Finding] = []
    for entry in flags.entries:
        positions = entry.confirmed()
        if positions:
            found.append(_found(entry.carried(), len(positions), positions[0], rows))
    return tuple(found)


def findings_tallied(
    carried: Sequence[Carried],
    tallies: jax.Array,
    masks: Sequence[jax.Array],
    operands: Sequence[Sequence[jax.Array]],
    rows: np.ndarray | None = None,
) -> tuple[Finding, ...]:
    """Return one finding per check a compiled program counted a caught cell for.

    What :func:`findings_of` returns over the same checks' masks, read off
    what the program counted where it computed them: ``tallies`` is
    every check's count and first caught cell (:func:`~gaspatchio_jax.checks.
    tallied`), and ``masks`` and ``operands`` are the coarse checks' own, in
    the order the coarse checks were carried. **A coarse check is judged
    exactly as ever**: its count is of the cells the in-trace test caught,
    so where it is above nought the mask and operands are read back and
    judged on the host; where it is nought, nothing of the check is read.

    Raises:
        ValueError: If the coarse checks carried and the masks handed back
            are not one for one -- a program read against another's checks,
            which is a defect.

    """
    counts, firsts = np.asarray(tallies)
    coarse = dict(
        zip(
            (at for at, check in enumerate(carried) if check.judgement is not None),
            zip(masks, operands, strict=True),
            strict=True,
        )
    )
    found: list[Finding] = []
    for at, check in enumerate(carried):
        count, first = int(counts[at]), int(firsts[at])
        if count and at in coarse:
            positions = check.judged(*coarse[at])
            count, first = len(positions), positions[0] if positions else 0
        if count:
            found.append(_found(check, count, first, rows))
    return tuple(found)


def _found(check: Carried, count: int, first: int, rows: np.ndarray | None) -> Finding:
    """Return one check's finding: its count, and its first cell named in the book."""
    flat = _in_the_book(first, check.shape, rows)
    return Finding(
        name=check.name,
        where=check.where or check.name,
        count=count,
        first=spelled_position(flat, check.shape),
        at=_policy_and_period(flat, check.shape),
        note=check.note,
    )


def _policy_and_period(flat: int, shape: tuple[int, ...]) -> tuple[int, int]:
    """Return the policy and period one flat position stands at."""
    if len(shape) < _TWO_AXES:
        return (flat, 0)
    return (flat // shape[1], flat % shape[1])


def _in_the_book(flat: int, shape: tuple[int, ...], rows: np.ndarray | None) -> int:
    """Return one caught cell's flat position with the book's own policy in it."""
    if rows is None:
        return flat
    if len(shape) < _TWO_AXES:
        return int(rows[flat])
    return int(rows[flat // shape[1]]) * shape[1] + flat % shape[1]


# One axis is policies; two are policies by periods.
_TWO_AXES: Final = 2


def merged_findings(found: Sequence[Finding]) -> tuple[Finding, ...]:
    """Return one finding per check and place, with the counts of every batch.

    The first position is the earliest one any batch caught, by the book's
    own row: a reader told "the first at policy 900,013" should be able to
    open that policy and see it, whichever batch it was computed in.
    """
    held: dict[tuple[str, str], Finding] = {}
    for one in found:
        key = (one.name, one.where)
        standing = held.get(key)
        if standing is None:
            held[key] = one
            continue
        earliest = min(standing, one, key=lambda finding: finding.at)
        held[key] = replace(
            standing,
            count=standing.count + one.count,
            first=earliest.first,
            at=earliest.at,
        )
    return tuple(held.values())


def completion_refusals(flags: FlagBook) -> list[Refusal]:
    """Return one refusal per check that caught something, with its count."""
    return [one.refusal() for one in findings_of(flags) if one.refuses]
