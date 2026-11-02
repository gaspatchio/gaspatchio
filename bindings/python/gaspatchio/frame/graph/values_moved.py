# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What the numbers did between two versions of a model, line by line.

A change report says which calculations were edited and which can no longer
give what they gave. A reviewer then asks the two questions that report cannot
answer from the two audit files alone: **did they move, and by how much?**
Those are answered from the two results files the runs wrote, and this module
holds the shape of that answer -- the ``values`` member of a change report.
:func:`~gaspatchio.frame.graph.diff_with_results` fills it.

**A value has moved when it is unequal.** There is no tolerance in that
sentence: integers, text, dates, where the nulls are, whether a value is a
NaN, which way an infinity points and how long a timeline is are compared
exactly, and two floats are compared as two numbers. The sign of a zero is not
compared. A tolerance would be a number somebody has to defend, applied to
every model this report is ever written about.

**The specification's band is a label and never a filter.** Two correct
implementations of one calculation can part in the last places of a double,
and section 11.1.12 states how far: ``|a - b| <= 1e-12 * scale``, the scale
being the largest magnitude among the line's own values and the values it
reads, per policy. A moved line inside that band is still listed as moved, and
says that it is indistinguishable from arithmetic; the report never decides for
the reader that a movement does not matter.

**Each moved line says how far, and where.** How many cells moved, in how many
of the policies compared, from which period; the largest absolute movement;
the largest relative movement ``|after - before| / |before|``, with a zero
``before`` stated as a movement *from 0* and never divided; and the policy and
period of the cell that ranks the line, with both of its values.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Any, Final, Literal

__all__ = [
    "DataCause",
    "LineCause",
    "LineValues",
    "MovedCell",
    "PairedBy",
    "ValuesReport",
]

# How a line of the later run was paired with a line of the earlier one. By
# node id where both artifacts hold the node; by the framework's own record of
# a name-move; or by the change report's equal-fingerprint hint, which pairs
# but is never a claim that the two are one calculation.
PairedBy = Literal["id", "rename", "hint"]

# What the record says moved under a line whose definition did not. The book
# the run was over, the producer that computed it -- an engine, a release, a
# library -- or nothing the record states at all.
DataCause = Literal["book", "producer", "unexplained"]

# What the record says moved under one line whose definition did not. The
# comparison's own cause, or a hole the line reads whose stamp of what it held
# moved -- the side file a model's setup joined, edited between the runs.
LineCause = Literal["book", "hole", "producer", "unexplained"]

# How many policy names a joined or left count carries. The count is always
# whole; the names are for a reader, and a quarter's new business can be
# thousands of them.
NAMED_POLICIES: Final[int] = 20


def json_value(value: object) -> Any:  # noqa: ANN401 -- a cell of any declared type, as JSON carries it
    """Return one cell as JSON carries it.

    A finite number is itself; a non-finite float is the specification's
    sentinel text, ``"NaN"``, ``"Infinity"`` or ``"-Infinity"``, because JSON
    has no spelling for one; a date is its ISO text; a list is its elements,
    each the same way.

    Examples:
        >>> json_value(float("inf")), json_value(1.5), json_value(None)
        ('Infinity', 1.5, None)

    """
    if isinstance(value, float) and not math.isfinite(value):
        return (
            "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
        )
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return value.total_seconds()
    if isinstance(value, (list, tuple)):
        return [json_value(one) for one in value]
    known = value is None or isinstance(value, (bool, int, float, str))
    return value if known else str(value)


@dataclass(frozen=True, slots=True)
class MovedCell:
    """One cell of a line, on both sides: the one that ranks the line.

    Attributes:
        policy: The policy, as its identity spells it -- one column's value,
            or several in brackets -- or None where the rows were paired by
            position and no column names them.
        row: The policy's row in the later results file.
        period: The cell's place on the timeline, or None on a line holding
            one value per policy.
        before: The earlier run's value, as JSON carries it.
        after: The later run's value.

    """

    policy: str | None
    row: int
    period: int | None
    before: Any
    after: Any

    def to_dict(self) -> dict[str, Any]:
        """Return the cell as plain JSON data."""
        return {
            "policy": self.policy,
            "row": self.row,
            "period": self.period,
            "before": json_value(self.before),
            "after": json_value(self.after),
        }


@dataclass(frozen=True, slots=True)
class LengthMoved:
    """The timelines of a line that are not the same length on both sides.

    A horizon moved: the periods both runs hold are compared, and this says
    how many policies' timelines grew or shrank, naming the first of them with
    its two lengths. The two lengths are that policy's, not a claim about
    every policy.

    Attributes:
        policies: How many policies' timelines differ in length.
        policy: The first of them, as its identity spells it.
        before: Its timeline's length in the earlier run.
        after: Its length in the later run.

    """

    policies: int
    policy: str | None
    before: int
    after: int

    def to_dict(self) -> dict[str, Any]:
        """Return the count and the example as plain JSON data."""
        return {
            "policies": self.policies,
            "policy": self.policy,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class LineValues:
    """What one paired line's values did between the two runs.

    Attributes:
        node: The line in the later artifact.
        before_node: The line it was paired with in the earlier artifact.
        column: The column the later line defines, or None.
        paired_by: ``id``, ``rename`` or ``hint`` -- see :data:`PairedBy`.
        change: What the change report says happened to the definition:
            ``self`` (edited), ``inherited`` (something it reads moved),
            ``renamed``, ``added`` (paired by a hint), or None where the
            definition did not move at all.
        compared: Whether the values were compared. False only on a line
            holding one value per period where the two runs' timelines do
            not start on the same date (see :attr:`ValuesReport.periods`).
        moved: Whether any value compared is unequal, or a timeline's length
            differs.
        cells_compared: How many cells were compared.
        cells_moved: How many of them are unequal.
        policies_compared: How many policies were compared on this line.
        policies_moved: How many of them hold a cell that moved or a
            timeline whose length did.
        first_period_moved: The first period any policy moved at, or None.
        max_abs: The largest ``|after - before|`` between two finite
            numbers, or None where no such pair moved.
        max_relative: The largest ``|after - before| / |before|`` over two
            finite numbers with a non-zero ``before``, or None.
        from_zero: Whether some cell moved out of a ``before`` of zero,
            which no ratio describes and which outranks every finite ratio.
        worst: The cell that ranks the line, or None where nothing moved
            but a timeline's length.
        length_moved: The policies whose timelines differ in length, or None.
        within_band: On a moved line, whether every movement is inside
            section 11.1.12's band, so that it cannot be told from a
            difference in the order of arithmetic. False on a line of exact
            values that moved and on a float line beyond the band; None on a
            float line beyond the band where a value it reads is absent from
            a results file, so the band it would be held to is not in hand --
            and None on a line that did not move.
        cause: On a moved line whose definition did not move, what the record
            says moved under it (see :data:`LineCause`); None elsewhere. The
            book where it moved; else ``hole`` where the line reads, itself or
            through what it reads, a hole whose stamp moved; else the
            comparison's producer or nothing it states.
        holes: On a line whose cause is ``hole``, the holes it reads whose
            stamps moved, in the later artifact's order; None elsewhere.

    """

    node: str
    before_node: str
    column: str | None
    paired_by: PairedBy
    change: str | None
    compared: bool
    moved: bool
    cells_compared: int
    cells_moved: int
    policies_compared: int
    policies_moved: int
    first_period_moved: int | None
    max_abs: float | None
    max_relative: float | None
    from_zero: bool
    worst: MovedCell | None
    length_moved: LengthMoved | None
    within_band: bool | None
    cause: LineCause | None
    holes: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the line as plain JSON data, empty fields included."""
        return {
            "node": self.node,
            "before_node": self.before_node,
            "column": self.column,
            "paired_by": self.paired_by,
            "change": self.change,
            "compared": self.compared,
            "moved": self.moved,
            "cells_compared": self.cells_compared,
            "cells_moved": self.cells_moved,
            "policies_compared": self.policies_compared,
            "policies_moved": self.policies_moved,
            "first_period_moved": self.first_period_moved,
            "max_abs": json_value(self.max_abs),
            "max_relative": json_value(self.max_relative),
            "from_zero": self.from_zero,
            "worst": None if self.worst is None else self.worst.to_dict(),
            "length_moved": (
                None if self.length_moved is None else self.length_moved.to_dict()
            ),
            "within_band": self.within_band,
            "cause": self.cause,
            "holes": None if self.holes is None else list(self.holes),
        }


@dataclass(frozen=True, slots=True)
class ResultsRead:
    """One results file the values were read from, and what it says it is.

    Attributes:
        path: The file, as the audit file recorded it or as it was named.
        fingerprint: The SHA-256 of its bytes when it was read.
        read: ``recorded`` where the audit file named it and its checksum
            still matched, ``named`` where the caller named it.
        scope: ``final-schema`` or ``every-node``, as its manifest says.
        producer: What computed it, as its manifest says.

    """

    path: str
    fingerprint: str
    read: Literal["recorded", "named"]
    scope: str
    producer: str

    def to_dict(self) -> dict[str, Any]:
        """Return the file's account as plain JSON data."""
        return {
            "path": self.path,
            "fingerprint": self.fingerprint,
            "read": self.read,
            "scope": self.scope,
            "producer": self.producer,
        }


@dataclass(frozen=True, slots=True)
class PoliciesNamed:
    """A count of policies, and the first of them by name."""

    count: int
    policies: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the count and the names as plain JSON data."""
        return {"count": self.count, "policies": list(self.policies)}


@dataclass(frozen=True, slots=True)
class RowsPaired:
    """Which row of one file is which policy of the other, and how it was decided.

    Attributes:
        matched_by: ``identity`` -- the columns in ``on`` name each policy --
            or ``position``, used only where both files were run over one
            book, whose digest is taken over its rows in order.
        on: The identity columns, empty under ``position``.
        paired: How many policies both files hold.
        joined: The policies only the later file holds.
        left: The policies only the earlier file holds.

    """

    matched_by: Literal["identity", "position"]
    on: tuple[str, ...]
    paired: int
    joined: PoliciesNamed
    left: PoliciesNamed

    def to_dict(self) -> dict[str, Any]:
        """Return the pairing as plain JSON data."""
        return {
            "matched_by": self.matched_by,
            "on": list(self.on),
            "paired": self.paired,
            "joined": self.joined.to_dict(),
            "left": self.left.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PeriodsPaired:
    """Whether period ``t`` of one run is period ``t`` of the other.

    Attributes:
        aligned: True where both runs' timelines start on the same date for
            every policy compared, or neither run has a dated timeline. Only
            then is a line holding one value per period compared, period by
            period, by index.
        reason: Why they were not aligned, or None.

    """

    aligned: bool
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return the alignment as plain JSON data."""
        return {"aligned": self.aligned, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class DeclaredLine:
    """One line's movement for the policy the two artifacts carry values for."""

    node: str
    magnitude: float | None
    from_zero: bool
    period: int | None

    def to_dict(self) -> dict[str, Any]:
        """Return the line as plain JSON data."""
        return {
            "node": self.node,
            "magnitude": json_value(self.magnitude),
            "from_zero": self.from_zero,
            "period": self.period,
        }


@dataclass(frozen=True, slots=True)
class Declared:
    """The movement of the one policy the later artifact carries values for.

    The comparison page derives what moved for that policy from the two
    artifacts' own values; this is the same reading taken from the results
    files, line for line, so the two can be held against each other. Every
    line paired by node id is read, and the lines that moved are listed with
    how far: the largest relative movement and the period it is at, or a
    movement from zero, or neither where no ratio describes it.

    Attributes:
        policy: The policy, as the artifact's axis names it.
        lines: The lines that moved for it.

    """

    policy: str
    lines: tuple[DeclaredLine, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the policy's lines as plain JSON data."""
        return {"policy": self.policy, "lines": [line.to_dict() for line in self.lines]}


@dataclass(frozen=True, slots=True)
class ValuesReport:
    """What the two runs' numbers did, beside what the change report says moved.

    Attributes:
        results: The two files read, the earlier first.
        rows: How their rows were paired, and the policies only one holds.
        periods: Whether their timelines were paired by index.
        cause: What the record says moved under a line whose definition did
            not: the book, the producer, or nothing it states. One answer for
            the comparison, because the book and the producer are the
            comparison's, not a line's. A hole is a line's: each line says
            whether it reads one whose stamp moved (:attr:`LineValues.cause`).
        lines: Every paired line both files carry, in the later artifact's
            order.
        not_carried: The lines the change report lists whose values one of
            the two files does not carry, so nothing can be said of them.
        declared: The policy the later artifact carries values for, read
            from the results files, or None where its row cannot be named.

    """

    results: tuple[ResultsRead, ResultsRead]
    rows: RowsPaired
    periods: PeriodsPaired
    cause: DataCause
    lines: tuple[LineValues, ...]
    not_carried: tuple[str, ...]
    declared: Declared | None

    @property
    def drift(self) -> bool:
        """Whether a value moved that no change to a definition accounts for.

        A line whose definition moved is already drift in the change report.
        This adds the line whose definition did not move and whose values
        did, beyond section 11.1.12's band or where the band cannot be
        decided: a column written around the frame's record, a book that
        moved under it, an engine that computes it differently. A movement
        inside the band is counted apart and is not drift, because no
        comparison can tell it from the order arithmetic was done in.
        """
        return any(
            line.moved and line.change is None and line.within_band is not True
            for line in self.lines
        )

    def headline(self) -> dict[str, Any]:
        """Return the comparison's counts by kind of change, as a reviewer reads them.

        Edited lines that moved and that moved no number; inherited lines that
        moved and that moved only in identity; lines that moved under
        definitions that did not, by what the record says moved under them;
        the moved lines inside the band, counted apart; the listed lines no
        file carries; and how many policies joined and left.
        """
        edited = [line for line in self.lines if line.change not in (None, "inherited")]
        inherited = [line for line in self.lines if line.change == "inherited"]
        unmoved = [line for line in self.lines if line.change is None and line.moved]
        return {
            "edited": {
                "moved": [line.node for line in edited if line.moved],
                "moved_no_number": [line.node for line in edited if not line.moved],
            },
            "inherited": {
                "moved": [line.node for line in inherited if line.moved],
                "identity_only": [line.node for line in inherited if not line.moved],
            },
            "unmoved_definitions": {
                cause: [line.node for line in unmoved if line.cause == cause]
                for cause in ("book", "hole", "producer", "unexplained")
            },
            "within_band": [
                line.node for line in self.lines if line.moved and line.within_band
            ],
            "not_carried": list(self.not_carried),
            "joined": self.rows.joined.count,
            "left": self.rows.left.count,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return the values member as plain JSON data."""
        before, after = self.results
        return {
            "results": {"before": before.to_dict(), "after": after.to_dict()},
            "rows": self.rows.to_dict(),
            "periods": self.periods.to_dict(),
            "cause": self.cause,
            "headline": self.headline(),
            "lines": [line.to_dict() for line in self.lines],
            "declared": None if self.declared is None else self.declared.to_dict(),
        }
