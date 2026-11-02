# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What moved between two versions of a model, and by how much.

A model-change review asks three things of two quarters. **What did somebody
edit?** :func:`~gaspatchio.frame.graph.diff_artifacts` answers that from the
two audit files, and says which calculations can no longer give what they
gave. **What did that move, and by how much?** No audit file can say: whether
a row of a table is reached depends on the book, so a calculation the identity
says *can* have moved may have moved no number at all. The two results files
the runs wrote can say, and :func:`diff_with_results` reads them beside the
change report and writes what it finds into the report's ``values`` member.

**Pairing is the change report's own.** A line of the later run is paired with
the line of the earlier run the report pairs it with: the same node id; the
node a recorded rename moved from; or the node an equal-fingerprint hint
names, compared and labelled ``hint``, never claimed as a rename. An added or
removed line has nothing to be compared with and gets no values.

**Rows are paired by the policy, and never quietly by position.** The columns
both results files record as naming each row -- the policy id, and the
scenario column on a scenario run -- or the columns the caller names. A policy
only one file holds is counted and named, as joined or left, and is never a
reason to refuse: a quarter's new business and its lapses are part of what a
reviewer is reading. Position is used only where both files were run over one
book, whose digest is taken over its rows in order.

**Periods are paired by index only where the timelines start together.** A
book revalued at a later date has a period 12 that is not the earlier book's
period 12, so where any compared policy's ``projection_start_date`` differs
between the two runs no line holding one value per period is compared, and
the report says so. Where both timelines start together and one is longer --
a horizon moved -- the periods both hold are compared and the difference in
length is stated.

**What moved and what explains it are two answers.** A line whose definition
moved is the change report's to explain: it was edited, or something it reads
was. A line whose definition held and whose values moved is explained by the
book the run was over, by the producer that computed it, or by nothing the
record states -- a column written around the frame's own account of it, which
is drift whatever else is true.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import polars as pl

from gaspatchio.engines._agreement import (
    TOLERANCE,
    policy_magnitude,
    read_line,
    read_scale,
)
from gaspatchio.engines.protocol import ResultManifest, read_manifest

from ._model_files import file_sha
from .diff import diff_artifacts, results_file_recorded
from .value_extractor import _a_count_past_the_calendar
from .values_moved import (
    NAMED_POLICIES,
    DataCause,
    Declared,
    DeclaredLine,
    LengthMoved,
    LineCause,
    LineValues,
    MovedCell,
    PairedBy,
    PeriodsPaired,
    PoliciesNamed,
    ResultsRead,
    RowsPaired,
    ValuesReport,
    json_value,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from .diff import Change, DataChange, DiffReport

__all__ = [
    "diff_with_results",
    "page_movement",
    "recorded_results",
    "roots_of",
    "with_values",
]

# The column a dated timeline states its first boundary in, on every calendar
# form of the projection axis. A fixed-step axis has none, and needs none: its
# periods are steps, not dates.
_START: Final[str] = "projection_start_date"

# The two sides as a sentence names them.
_EARLIER: Final[str] = "earlier"
_LATER: Final[str] = "later"

# The move a refusal to pair rows names.
_NAME_THE_IDENTITY: Final[str] = (
    "Name the column that identifies a policy with --policy-id-column <column> "
    "(once more for a scenario column)."
)


def diff_with_results(  # noqa: PLR0913 -- two documents, two files, and how the rows and the files were named
    before: dict[str, Any],
    after: dict[str, Any],
    before_results: Path | str,
    after_results: Path | str,
    *,
    row_identity: Sequence[str] | None = None,
    recorded: bool = False,
) -> DiffReport:
    """Compare two artifacts of one model, and the two runs' numbers beside them.

    The change report :func:`~gaspatchio.frame.graph.diff_artifacts` writes,
    with its ``values`` member filled from the two results files: for every
    line the report pairs and both files carry, whether its values moved, in
    how many policies, from which period, by how much, and at which policy and
    period the largest movement is.

    Args:
        before: The earlier artifact, parsed.
        after: The later artifact, parsed.
        before_results: The results file the earlier run wrote.
        after_results: The results file the later run wrote.
        row_identity: The columns that name a policy in both files, where the
            caller names them; they decide over whatever the files record.
        recorded: Whether the two files are the ones the audit files record,
            found and checked against their checksums, rather than files the
            caller named. It is written into the report and changes nothing
            else.

    Returns:
        The change report, ``values`` filled.

    Raises:
        ValueError: A file that is not a results file this can read; a
            results file that is not of its own artifact; two files whose
            rows nothing shows to be the same policies. The message says
            which, naming the side.

    Examples:
        A rate edited from 1% to 2% moves the line that holds it in every
        policy, and doubles it:

        >>> import json, tempfile
        >>> from pathlib import Path
        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> from gaspatchio.engines.protocol import write_with_manifest
        >>> from gaspatchio.engines.reference import polars_reference
        >>> from gaspatchio.frame.graph import GraphExporter, diff_with_results
        >>> folder = Path(tempfile.mkdtemp())
        >>> def run(rate: float, name: str) -> dict:
        ...     af = ActuarialFrame(
        ...         pl.DataFrame(
        ...             {"policy_id": ["P1", "P2"], "sum_assured": [100.0, 200.0]}
        ...         )
        ...     )
        ...     af.claims = af.sum_assured * rate
        ...     results, manifest = polars_reference(af, row_identity="policy_id")
        ...     write_with_manifest(results, manifest, folder / name)
        ...     return json.loads(GraphExporter(af).export())
        >>> report = diff_with_results(
        ...     run(0.01, "q1.parquet"),
        ...     run(0.02, "q2.parquet"),
        ...     folder / "q1.parquet",
        ...     folder / "q2.parquet",
        ... )
        >>> line = next(one for one in report.values.lines if one.node == "claims@1")
        >>> line.change, line.policies_moved, line.max_relative
        ('self', 2, 1.0)

    """
    return with_values(
        diff_artifacts(before, after),
        (before, after),
        (Path(before_results), Path(after_results)),
        row_identity=row_identity,
        recorded=recorded,
    )


def with_values(
    report: DiffReport,
    documents: tuple[dict[str, Any], dict[str, Any]],
    results: tuple[Path, Path],
    *,
    row_identity: Sequence[str] | None = None,
    recorded: bool = False,
) -> DiffReport:
    """Return a change report already made, with its ``values`` member filled.

    :func:`diff_with_results` in two steps, for a caller that has the change
    report in hand before it decides whether there are results to read --
    ``gspio diff``, which reports two artifacts it cannot compare before it
    looks for a results file at all.

    Args:
        report: :func:`~gaspatchio.frame.graph.diff_artifacts` over the two
            documents.
        documents: The earlier and the later artifact, parsed.
        results: The earlier and the later run's results files.
        row_identity: As :func:`diff_with_results` takes it.
        recorded: As :func:`diff_with_results` takes it.

    Returns:
        The report, ``values`` filled.

    Raises:
        ValueError: As :func:`diff_with_results` raises it.

    """
    earlier = _Side.read(_EARLIER, documents[0], results[0], recorded=recorded)
    later = _Side.read(_LATER, documents[1], results[1], recorded=recorded)
    values = _values(report, earlier, later, row_identity)
    return dataclasses.replace(report, values=values)


# --- where an audit file's results file is --------------------------------


def roots_of(audit_file: Path, document: Mapping[str, Any]) -> list[Path]:
    """Return the directories an audit file's recorded paths may be written against.

    Every path in an audit file is written against the model's root -- the
    directory the model file sits in, or the repository it sits in -- and the
    root itself is not carried. The audit file is read where it sits, so the
    root is found by climbing from its directory to the first directory that
    holds the model file the document names; the audit file's own directory
    comes last, for a document that names no model file.

    Args:
        audit_file: Where the audit file was read from.
        document: The audit file, parsed.

    Returns:
        The candidate roots, nearest first.

    """
    model = document.get("model")
    source = model.get("source_path") if isinstance(model, dict) else None
    here = audit_file.resolve().parent
    found = [
        ancestor
        for ancestor in (here, *here.parents)
        if isinstance(source, str) and (ancestor / source).is_file()
    ]
    return [*found[:1], here]


def recorded_results(
    document: Mapping[str, Any], roots: Sequence[Path], *, side: str
) -> Path | str:
    """Return the results file an audit file records, or the sentence saying why not.

    The file is the one whose bytes still carry the checksum the audit file
    recorded, found under one of ``roots`` at the path the audit file
    records. A file at that path whose checksum differs is not the one the
    run wrote -- written again, or written over by another run -- and is not
    read: values compared from it would be values of a run nobody recorded.

    Args:
        document: The audit file, parsed.
        roots: Where its paths may be written against (:func:`roots_of`).
        side: ``earlier`` or ``later``, as the sentence names the document.

    Returns:
        The file, or one sentence saying why there is none to read.

    """
    path, fingerprint = results_file_recorded(document)
    if fingerprint is None:
        return f"the {side} audit file records no results file"
    if path is None:
        return (
            f"the {side} audit file records a results file's checksum and no "
            "path to find it at"
        )
    stale: Path | None = None
    for root in roots:
        candidate = (root / path).resolve()
        if not candidate.is_file():
            continue
        if file_sha(candidate) == fingerprint:
            return candidate
        stale = stale or candidate
    if stale is not None:
        return (
            f"the file at {stale} is not the results file the {side} audit file "
            "records: its checksum differs, so it was written again after that "
            "run, or another run wrote over it"
        )
    return (
        f"the {side} audit file records its results file at {path}, and no file "
        f"is there (looked under {', '.join(str(root) for root in roots)})"
    )


# --- the two sides -----------------------------------------------------------


@dataclass(slots=True)
class _Side:
    """One run: its audit file, its results file and what they say they are.

    ``rows`` is the file's row for each paired policy, in the pairing's
    order, or None where that is the file's own order -- the common case, two
    runs over one book in one order, where gathering every column again would
    copy the whole file for nothing. ``magnitudes`` keeps a column's
    per-policy magnitude once it is read, since one column is a read of many
    lines.
    """

    name: str
    document: dict[str, Any]
    frame: pl.DataFrame
    manifest: ResultManifest
    read_as: ResultsRead
    nodes: dict[str, dict[str, Any]]
    rows: pl.Series | None = None
    magnitudes: dict[str, pl.Series] = field(default_factory=dict)

    @classmethod
    def read(
        cls, name: str, document: dict[str, Any], path: Path, *, recorded: bool
    ) -> _Side:
        """Read one results file, and hold it to its own artifact.

        Raises:
            ValueError: The file cannot be read as results, or its manifest
                says it is the results of another artifact.

        """
        try:
            frame = pl.read_parquet(path)
            manifest = read_manifest(path)
        except Exception as error:
            message = (
                f"The {name} results file {path} is not a result this can read: {error}"
            )
            raise ValueError(message) from error
        stated = str(document.get("graph_fingerprint") or "")
        if manifest.graph_fingerprint != stated:
            message = (
                f"The {name} results are not of the {name} artifact: the artifact "
                f"states {stated} and the results file {path.name} states "
                f"{manifest.graph_fingerprint}. Comparing them would put one "
                "model's numbers under another model's node names. Name the "
                "results file the run of that audit file wrote, or export the "
                "audit file again from the run that wrote these results."
            )
            raise ValueError(message)
        nodes = {
            str(node["id"]): node
            for node in document.get("nodes") or []
            if isinstance(node, dict) and "id" in node
        }
        # A recorded file was found by its checksum, so the audit file already
        # states it; a named one is hashed here, once.
        stamp = results_file_recorded(document)[1] if recorded else file_sha(path)
        read_as = ResultsRead(
            path=str(path),
            fingerprint=stamp or "",
            read="recorded" if recorded else "named",
            scope=manifest.scope,
            producer=manifest.producer,
        )
        return cls(name, document, frame, manifest, read_as, nodes)

    def column_for(self, node_id: str) -> str | None:
        """Return the column carrying that node here, or None where it is absent."""
        name = self.manifest.columns.get(node_id)
        return name if name is not None and name in self.frame.columns else None

    def values_for(self, node_id: str) -> pl.Series | None:
        """Return that node's values for the paired policies, or None.

        Not yet judged against the calendar: a line whose values did not
        move is measured by equality alone, which reads no cell as a value,
        so a date past the calendar in it is nothing this diff writes. A
        line that moved is judged by :meth:`refuse_past_the_calendar` before
        any of its cells is read.
        """
        name = self.column_for(node_id)
        if name is None:
            return None
        return self.gathered(name)

    def gathered(self, column: str) -> pl.Series:
        """Return a column's values for the paired policies, as they are held."""
        values = self.frame.get_column(column)
        return values if self.rows is None else values.gather(self.rows)

    def paired(self, column: str) -> pl.Series:
        """Return a column's values for the paired policies, read as dates can be.

        Raises:
            ValueError: The column holds a date or a timestamp outside the
                years 1 to 9999 for a paired policy.

        """
        values = self.gathered(column)
        self.refuse_past_the_calendar(column, values)
        return values

    def refuse_past_the_calendar(self, column: str, values: pl.Series) -> None:
        """Refuse by name a date or timestamp outside the years 1 to 9999.

        Such a value is judged on its count, before it is read as a value:
        past about 262,000 years from 1970 the engine's own conversion
        panics, with an exception no ``except Exception`` catches, and from
        the year 10000 up to there the host language refuses it naming no
        column. Either is this one refusal, naming the side and the column.

        Raises:
            ValueError: ``values`` holds such a date or timestamp.

        """
        past = _a_count_past_the_calendar(values)
        if past is not None:
            raise ValueError(_a_value_past_the_calendar(self.name, column, past))

    def row_of(self, policy: int) -> int:
        """Return the file's row for one paired policy."""
        return policy if self.rows is None else int(self.rows[policy])

    def magnitude_for(self, node_id: str) -> pl.Series | None:
        """Return that node's per-policy magnitude for the paired policies, or None."""
        name = self.column_for(node_id)
        if name is None:
            return None
        kept = self.magnitudes.get(name)
        if kept is None:
            kept = policy_magnitude(self.frame.get_column(name))
            if self.rows is not None:
                kept = kept.gather(self.rows)
            self.magnitudes[name] = kept
        return kept


def _a_value_past_the_calendar(side: str, column: str, said: str) -> str:
    """Return the refusal a compared date outside the years 1 to 9999 earns."""
    return (
        f"The {side} results hold a date outside the years 1 to 9999 in column "
        f"{column!r} ({said}), so the values are not compared. The change report "
        "writes a date as ISO-8601 calendar text, which has no such year, and "
        "section 11.1.33 puts a date result outside those years outside the "
        "domain. The usual causes are an open-ended 9999-12-31 carried past the "
        "calendar -- excel.edate or excel.eomonth on it -- and a count read in "
        "another unit than it was written in, as epoch nanoseconds cast to "
        "milliseconds. Keep the sentinel out of the arithmetic with a when() on "
        "it, or read the count in its own unit, and run the model again."
    )


# --- rows --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Rows:
    """The pairing of the two files' rows, and each paired policy's name."""

    paired: RowsPaired
    names: list[str | None]


def _pair_rows(earlier: _Side, later: _Side, told: Sequence[str] | None) -> _Rows:
    """Pair the two files' rows by policy, or say why they cannot be.

    Raises:
        ValueError: No identity both files carry, and no one book to show
            that position is the pairing; an identity naming one policy
            twice; identity columns of two types.

    """
    identity = _identity(earlier, later, told)
    if identity is None:
        if (
            earlier.manifest.inputs_digest != later.manifest.inputs_digest
            or earlier.frame.height != later.frame.height
        ):
            message = (
                "Neither results file records which columns name its rows, and "
                "the two were run over different books, so nothing shows which "
                f"row of one is which policy of the other. {_NAME_THE_IDENTITY}"
            )
            raise ValueError(message)
        earlier.rows = None
        later.rows = None
        nobody = PoliciesNamed(0, ())
        return _Rows(
            RowsPaired("position", (), later.frame.height, nobody, nobody),
            [None] * later.frame.height,
        )

    for side in (earlier, later):
        absent = [column for column in identity if column not in side.frame.columns]
        if absent:
            message = (
                f"The {side.name} results carry no {_listed(absent)} column, which "
                "names the policies the two files are paired on. "
                f"{_NAME_THE_IDENTITY}"
            )
            raise ValueError(message)
        _refuse_repeats(side, identity)

    keys = list(identity)
    for side in (earlier, later):
        for key in keys:
            side.refuse_past_the_calendar(key, side.frame.get_column(key))
    left = earlier.frame.select(keys).with_row_index("_before")
    right = later.frame.select(keys).with_row_index("_after")
    try:
        both = right.join(left, on=keys, how="inner").sort("_after")
        joined = right.join(left, on=keys, how="anti")
        gone = left.join(right, on=keys, how="anti")
    except pl.exceptions.PolarsError as error:
        message = (
            f"The two results files hold {_listed(keys)} in types that do not "
            f"compare ({error}), so their policies cannot be paired. Write both "
            "runs over books that spell a policy the same way."
        )
        raise ValueError(message) from error
    earlier.rows = _in_order(both.get_column("_before"), earlier.frame.height)
    later.rows = _in_order(both.get_column("_after"), later.frame.height)
    return _Rows(
        RowsPaired(
            "identity",
            tuple(keys),
            both.height,
            _named(joined, keys),
            _named(gone, keys),
        ),
        _names(both, keys),
    )


def _in_order(rows: pl.Series, height: int) -> pl.Series | None:
    """Return a side's rows to gather by, or None where they are every row in order."""
    rows = rows.cast(pl.Int64)
    if rows.len() == height and rows.equals(
        pl.int_range(height, dtype=pl.Int64, eager=True), check_names=False
    ):
        return None
    return rows


def _identity(
    earlier: _Side, later: _Side, told: Sequence[str] | None
) -> tuple[str, ...] | None:
    """Return the columns naming a policy in both files, or None where none does.

    The columns the caller names; else the columns both manifests record;
    else the columns one manifest records, where the other file carries them
    too -- a pairing on those values is a pairing by identity, and the report
    says which columns it was.
    """
    if told:
        return tuple(told)
    was, now = earlier.manifest.row_identity, later.manifest.row_identity
    if was is not None and was == now:
        return was
    for recorded in (now, was):
        if recorded is not None and all(
            column in earlier.frame.columns and column in later.frame.columns
            for column in recorded
        ):
            return recorded
    return None


def _refuse_repeats(side: _Side, identity: tuple[str, ...]) -> None:
    """Refuse a file whose identity names one policy on two rows."""
    repeated = side.frame.select(identity).filter(pl.struct(identity).is_duplicated())
    if repeated.height == 0:
        return
    shown = _names(repeated.unique(maintain_order=True), list(identity))
    message = (
        f"The {side.name} results carry {_listed(shown)} more than once under "
        f"{_listed(identity)}, so one policy's row cannot be told from another's. "
        "On a scenario run, name the policy column and the scenario column "
        "together, each with --policy-id-column."
    )
    raise ValueError(message)


def _names(frame: pl.DataFrame, keys: Sequence[str]) -> list[str | None]:
    """Return each row's policy as a sentence names it."""
    columns = [frame.get_column(key).to_list() for key in keys]
    if len(columns) == 1:
        return [None if value is None else str(value) for value in columns[0]]
    return [
        "(" + ", ".join(str(value) for value in values) + ")"
        for values in zip(*columns, strict=True)
    ]


def _named(frame: pl.DataFrame, keys: Sequence[str]) -> PoliciesNamed:
    """Return how many policies a frame holds, and the first of them by name."""
    first = _names(frame.head(NAMED_POLICIES), keys)
    return PoliciesNamed(frame.height, tuple(str(name) for name in first))


def _listed(values: Iterable[object], limit: int = 5) -> str:
    """Return a few values as text, so a sentence names them rather than counts."""
    shown = [str(value) for value in values]
    if len(shown) <= limit:
        return ", ".join(shown)
    return ", ".join(shown[:limit]) + f" and {len(shown) - limit} more"


# --- periods -----------------------------------------------------------------


def _periods(
    earlier: _Side, later: _Side, names: Sequence[str | None]
) -> PeriodsPaired:
    """Return whether period ``t`` of one run is period ``t`` of the other.

    Read off each policy's ``projection_start_date`` in the two files: equal
    for every paired policy, or neither run with a dated timeline at all.
    """
    carried = [_START in side.frame.columns for side in (earlier, later)]
    if all(carried):
        # Compared on what is held before either is read as a date: start
        # dates that agree are not written anywhere, so only a timeline that
        # moved is judged against the calendar.
        was = earlier.gathered(_START)
        now = later.gathered(_START)
        moved = ~was.eq_missing(now)
        if not moved.any():
            return PeriodsPaired(aligned=True, reason=None)
        earlier.refuse_past_the_calendar(_START, was)
        later.refuse_past_the_calendar(_START, now)
        first = int(moved.arg_true()[0])
        reason = (
            f"The two runs' timelines start on different dates for "
            f"{int(moved.sum())} of the {len(names)} policies compared "
            f"({names[first] or f'row {first}'}: {was[first]} then {now[first]}), "
            "so period t of one is not period t of the other; only the lines "
            "holding one value per policy were compared."
        )
        return PeriodsPaired(aligned=False, reason=reason)
    dated = [
        any(node.get("column") == _START for node in side.nodes.values())
        for side in (earlier, later)
    ]
    if not any(dated):
        return PeriodsPaired(aligned=True, reason=None)
    missing = " and ".join(
        side.name
        for side, has in zip((earlier, later), carried, strict=True)
        if not has
    )
    reason = (
        f"The {missing} results carry no {_START}, so nothing shows the two "
        "timelines start on the same date; only the lines holding one value per "
        "policy were compared."
    )
    return PeriodsPaired(aligned=False, reason=reason)


# --- what moved under a line whose definition did not ----------------------


def _cause(
    data: Sequence[DataChange], earlier: ResultManifest, later: ResultManifest
) -> DataCause:
    """Return what the record says moved under a line whose definition held.

    The book, where the change report says the two books differ, or could not
    compare them and the two results files were computed over different
    inputs. Else the producer, where the two files say different things
    computed them -- an engine, or one engine on another library. Else
    nothing the record states.
    """
    book = next((one for one in data if one.kind == "model_points"), None)
    if book is not None and (
        book.reason is None or earlier.inputs_digest != later.inputs_digest
    ):
        return "book"
    if earlier.producer != later.producer or earlier.versions != later.versions:
        return "producer"
    return "unexplained"


def _holes_read(data: Sequence[DataChange], later: _Side) -> dict[str, tuple[str, ...]]:
    """Return, per line of the later artifact, the moved holes it reads.

    A hole moved where the change report compared its two stamps and they
    differ. A line reads one where it is that hole's node, or reads it through
    any line it reads, as the later artifact's ``reads`` record them; the
    names follow the later artifact's node order.
    """
    moved = {
        entry.name
        for entry in data
        if entry.kind == "hole" and entry.reason is None and entry.name is not None
    }
    if not moved:
        return {}
    order = list(later.nodes)
    found: dict[str, frozenset[str]] = {}

    def reached(node_id: str) -> frozenset[str]:
        if node_id in found:
            return found[node_id]
        found[node_id] = frozenset()  # a cycle in a malformed record reads nothing
        node = later.nodes.get(node_id) or {}
        own = (
            {node_id}
            if node.get("kind") == "hole" and node.get("column") in moved
            else set()
        )
        for read in node.get("reads") or ():
            if isinstance(read, str):
                own |= reached(read)
        found[node_id] = frozenset(own)
        return found[node_id]

    named: dict[str, tuple[str, ...]] = {}
    for node_id in order:
        holes = reached(node_id)
        if holes:
            named[node_id] = tuple(
                str(later.nodes[hole].get("column")) for hole in order if hole in holes
            )
    return named


def _line_cause(
    cause: DataCause, holes: tuple[str, ...], *, said: bool
) -> tuple[LineCause | None, tuple[str, ...] | None]:
    """Return a line's ``cause`` and ``holes``: the book, else a hole, else the rest."""
    if not said:
        return None, None
    if cause != "book" and holes:
        return "hole", holes
    return cause, None


# --- one line ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Measured:
    """What one line's two columns came to, before it is labelled."""

    cells_compared: int
    cells_moved: int
    policies_moved: int
    first_period: int | None
    max_abs: float | None
    max_relative: float | None
    from_zero: bool
    worst: tuple[int, int | None, object, object] | None
    lengths: tuple[int, int, int, int] | None

    @property
    def moved(self) -> bool:
        """Whether any cell or any timeline's length moved."""
        return self.cells_moved > 0 or self.lengths is not None


def _depth(dtype: pl.DataType) -> int:
    """Return how deep a list type nests."""
    depth = 0
    while isinstance(dtype, pl.List):
        inner = dtype.inner
        dtype = inner if isinstance(inner, pl.DataType) else inner()
        depth += 1
    return depth


def _leaf(dtype: pl.DataType) -> pl.DataType:
    """Return the scalar type at the bottom of a possibly nested list type."""
    while isinstance(dtype, pl.List):
        inner = dtype.inner
        dtype = inner if isinstance(inner, pl.DataType) else inner()
    return dtype


def _one_null_list(values: pl.Series) -> pl.Series:
    """Read a policy with no timeline as a timeline of one null value.

    The reading section 11.1.12's comparison gives it: it then parts from a
    timeline of one value on where its nulls are, and from a longer one on
    its length.
    """
    if not isinstance(values.dtype, pl.List) or values.null_count() == 0:
        return values
    one_null = pl.Series([[None]], dtype=values.dtype)
    return values.fill_null(pl.lit(one_null).first())


def _cells(
    before: pl.Series, after: pl.Series
) -> tuple[pl.DataFrame, pl.DataFrame | None]:
    """Return a line's paired cells, and each policy's two timeline lengths.

    One row per cell both sides hold: ``p`` the policy, ``t`` the period
    (null on a line of one value per policy), ``b`` and ``a`` the two values.
    A timeline is compared over the periods both sides hold; the lengths say
    where they part.
    """
    rows = before.len()
    policy = pl.int_range(rows, dtype=pl.Int64, eager=True)
    if _depth(before.dtype) == 0 or _depth(after.dtype) == 0:
        return (
            pl.DataFrame(
                {"p": policy, "t": pl.repeat(None, rows, dtype=pl.Int64, eager=True)}
            ).with_columns(b=before, a=after),
            None,
        )
    held = _one_null_list(before)
    other = _one_null_list(after)
    was = held.list.len().cast(pl.Int64)
    now = other.list.len().cast(pl.Int64)
    common = was.zip_with(was <= now, now)
    index = pl.int_ranges(0, common, dtype=pl.Int64, eager=True)
    cells = pl.DataFrame(
        {
            "p": policy,
            "t": index,
            "b": held.list.gather(index),
            "a": other.list.gather(index),
        }
    ).explode(["t", "b", "a"], empty_as_null=False)
    lengths = pl.DataFrame({"lb": was, "la": now, "common": common})
    return cells.filter(cells.get_column("t").is_not_null()), lengths


def _comparable(
    before: pl.Series, after: pl.Series
) -> tuple[pl.Series, pl.Series, bool]:
    """Return two columns of cells in one type, and whether that type is a float.

    Two numbers compare as numbers -- a line edited from integers to floats
    has not moved where the values are the same -- and two values of other
    types compare as themselves, or as their text where the types differ.
    """
    left, right = before.dtype, after.dtype
    if left.is_numeric() and right.is_numeric():
        if left.is_integer() and right.is_integer():
            return before.cast(pl.Int64), after.cast(pl.Int64), False
        return before.cast(pl.Float64), after.cast(pl.Float64), True
    if left == right:
        return before, after, False
    try:
        return before.cast(pl.String), after.cast(pl.String), False
    except pl.exceptions.PolarsError:
        return (
            pl.Series(before.to_list(), dtype=pl.Object).cast(pl.String, strict=False),
            pl.Series(after.to_list(), dtype=pl.Object).cast(pl.String, strict=False),
            False,
        )


def _measure(before: pl.Series, after: pl.Series) -> _Measured:
    """Return how far one line's values moved over the paired policies.

    A cell moved where its two values are unequal: numbers as numbers, with
    NaN equal to NaN and a zero equal to a zero of either sign; nulls in the
    same place equal; everything else exactly. The largest relative movement
    is taken over two finite numbers with a non-zero earlier value, and a
    movement out of zero outranks every finite one. The worst cell is the one
    that ranks the line: out of zero, the largest later value; else the
    largest relative movement; else the first cell that moved -- the first
    in the book's order and the timeline's at a tie.
    """
    cells, lengths = _cells(before, after)
    held, other, is_float = _comparable(cells.get_column("b"), cells.get_column("a"))
    moved = ~held.eq_missing(other)
    policy = cells.get_column("p")
    period = cells.get_column("t")

    length_rows = pl.Series("row", [], dtype=pl.Int64)
    shared = pl.Series("common", [], dtype=pl.Int64)
    if lengths is not None:
        apart = lengths.get_column("lb") != lengths.get_column("la")
        length_rows = pl.int_range(lengths.height, dtype=pl.Int64, eager=True).filter(
            apart
        )
        shared = lengths.get_column("common").filter(apart)
    moved_policies = pl.concat([policy.filter(moved), length_rows]).n_unique()
    first_candidates = [
        _int(value)
        for value in (period.filter(moved).min(), shared.min())
        if value is not None
    ]
    first = min(first_candidates) if first_candidates else None

    max_abs: float | None = None
    max_relative: float | None = None
    from_zero = False
    worst_at: int | None = None
    if is_float and moved.any():
        finite = (held.is_finite() & other.is_finite()).fill_null(value=False) & moved
        apart = (other - held).abs()
        max_abs = _float(apart.filter(finite).max())
        zero = finite & (held == 0.0)
        ratioed = finite & (held != 0.0)
        relative = apart / held.abs()
        max_relative = _float(relative.filter(ratioed).max())
        if zero.any():
            from_zero = True
            worst_at = _first_largest(other.abs(), zero)
        elif ratioed.any():
            worst_at = _first_largest(relative, ratioed)
    if worst_at is None and moved.any():
        worst_at = int(moved.arg_true()[0])

    worst = None
    if worst_at is not None:
        at_period = period[worst_at]
        worst = (
            int(policy[worst_at]),
            None if at_period is None else int(at_period),
            cells.get_column("b")[worst_at],
            cells.get_column("a")[worst_at],
        )
    length_example = None
    if lengths is not None and length_rows.len() > 0:
        row = int(length_rows[0])
        length_example = (
            int(length_rows.len()),
            row,
            int(lengths.get_column("lb")[row]),
            int(lengths.get_column("la")[row]),
        )
    return _Measured(
        cells_compared=cells.height,
        cells_moved=int(moved.sum()),
        policies_moved=int(moved_policies),
        first_period=first,
        max_abs=max_abs,
        max_relative=max_relative,
        from_zero=from_zero,
        worst=worst,
        lengths=length_example,
    )


def _first_largest(values: pl.Series, among: pl.Series) -> int:
    """Return the first position of the largest of ``values`` where ``among`` holds."""
    largest = values.filter(among).max()
    return int((among & (values == largest)).arg_true()[0])


def _int(value: object) -> int:
    """Return a Polars aggregate over periods or rows as an int."""
    if isinstance(value, int):
        return value
    message = f"A period came back as {type(value).__name__}."
    raise TypeError(message)


def _float(value: object) -> float | None:
    """Return a Polars aggregate as a float, or None where there is none."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    message = f"A numeric aggregate came back as {type(value).__name__}."
    raise TypeError(message)


def _within_band(
    node: str,
    before_node: str,
    earlier: _Side,
    later: _Side,
    values: tuple[pl.Series, pl.Series],
) -> bool | None:
    """Return whether a moved line is inside section 11.1.12's band, or None.

    Each side's scale is taken from what **its own** artifact says the line
    reads, as each side's file carries it: the edit under review may be
    exactly that the line reads something new. A float line beyond the band
    with a read absent from its own file is undecided, because the scale in
    hand can only be smaller than the true one; a line of exact values that
    moved is outside any band.
    """
    before, after = values
    if not (_leaf(before.dtype).is_float() or _leaf(after.dtype).is_float()):
        return False
    if _depth(before.dtype) != _depth(after.dtype):
        return False
    absent = False
    floors: list[list[pl.Series]] = [[], []]
    for at, (side, line) in enumerate(((earlier, before_node), (later, node))):
        for read in side.nodes.get(line, {}).get("reads") or []:
            magnitude = side.magnitude_for(str(read))
            if magnitude is None:
                absent = True
                continue
            floors[at].append(magnitude)
    floor = read_scale(floors[0], floors[1], before.len())
    reading = read_line(before, after, exact=False, read_scale=floor)
    if reading.parted:
        return False
    if reading.max_ratio is None or reading.max_ratio <= TOLERANCE:
        return True
    return None if absent else False


# --- every line --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Pair:
    """One line of the later artifact, the line it is paired with, and how."""

    node: str
    before_node: str
    paired_by: PairedBy
    change: str | None


def _pairs(report: DiffReport, earlier: _Side, later: _Side) -> list[_Pair]:
    """Return every line the change report pairs, in the later artifact's order.

    The same node id; else the node a recorded rename moved from; else the
    node an equal-fingerprint hint names. An added line with no hint, and a
    removed line, have nothing to be paired with.
    """
    changes: dict[str, Change] = {change.node: change for change in report.calculations}
    pairs: list[_Pair] = []
    for node_id in later.nodes:
        change = changes.get(node_id)
        said = _said(change)
        if node_id in earlier.nodes:
            pairs.append(_Pair(node_id, node_id, "id", said))
        elif change is not None and change.renamed_from is not None:
            pairs.append(_Pair(node_id, change.renamed_from, "rename", said))
        elif change is not None and (hint := _hint(change)) is not None:
            pairs.append(_Pair(node_id, hint, "hint", said))
    return pairs


def _said(change: Change | None) -> str | None:
    """Return what the change report says of a line's definition, or None."""
    if change is None:
        return None
    if change.kind == "changed":
        return change.change_origin
    return change.kind


def _hint(change: Change) -> str | None:
    """Return the departed node an added line's hint names, or None."""
    return change.fingerprint_equal_to or change.values_equal_to


def _values(
    report: DiffReport,
    earlier: _Side,
    later: _Side,
    told: Sequence[str] | None,
) -> ValuesReport:
    """Return the values member: every paired line both files carry, measured."""
    rows = _pair_rows(earlier, later, told)
    periods = _periods(earlier, later, rows.names)
    cause = _cause(report.data, earlier.manifest, later.manifest)
    holes_read = _holes_read(report.data, later) if cause != "book" else {}
    lines: list[LineValues] = []
    not_carried: list[str] = []
    measured_by_node: dict[str, tuple[pl.Series, pl.Series]] = {}
    for pair in _pairs(report, earlier, later):
        before = earlier.values_for(pair.before_node)
        after = later.values_for(pair.node)
        if before is None or after is None:
            if pair.change is not None:
                not_carried.append(pair.node)
            continue
        listed = _depth(before.dtype) > 0 or _depth(after.dtype) > 0
        if listed and not periods.aligned:
            lines.append(_not_compared(pair, later, rows.paired.paired))
            continue
        still = before.dtype == after.dtype and before.equals(after, check_names=False)
        if not still:
            # A moved line has its cells read -- the one that ranks it, the
            # declared policy's -- so it is judged against the calendar first.
            earlier.refuse_past_the_calendar(
                earlier.column_for(pair.before_node) or pair.before_node, before
            )
            later.refuse_past_the_calendar(
                later.column_for(pair.node) or pair.node, after
            )
        line = _line(
            pair,
            earlier=earlier,
            later=later,
            values=(before, after),
            rows=rows,
            cause=cause,
            holes=holes_read.get(pair.node, ()),
            still=still,
        )
        lines.append(line)
        # A line that held moved on no row, so the declared policy's reading
        # of it is "not moved" without reading its cells.
        if pair.paired_by == "id" and not still:
            measured_by_node[pair.node] = (before, after)
    return ValuesReport(
        results=(earlier.read_as, later.read_as),
        rows=rows.paired,
        periods=periods,
        cause=cause,
        lines=tuple(lines),
        not_carried=tuple(not_carried),
        declared=_declared(later, rows.names, measured_by_node),
    )


def _not_compared(pair: _Pair, later: _Side, paired: int) -> LineValues:
    """Return a line holding one value per period whose periods could not be paired."""
    return LineValues(
        node=pair.node,
        before_node=pair.before_node,
        column=later.nodes[pair.node].get("column"),
        paired_by=pair.paired_by,
        change=pair.change,
        compared=False,
        moved=False,
        cells_compared=0,
        cells_moved=0,
        policies_compared=paired,
        policies_moved=0,
        first_period_moved=None,
        max_abs=None,
        max_relative=None,
        from_zero=False,
        worst=None,
        length_moved=None,
        within_band=None,
        cause=None,
    )


def _line(  # noqa: PLR0913 -- one pair, two sides, its two columns, the rows and the cause
    pair: _Pair,
    *,
    earlier: _Side,
    later: _Side,
    values: tuple[pl.Series, pl.Series],
    rows: _Rows,
    cause: DataCause,
    holes: tuple[str, ...],
    still: bool,
) -> LineValues:
    """Return one paired line, measured and labelled.

    ``still`` is whether the two columns are equal as held, which the caller
    has already asked.
    """
    before, after = values
    if still:
        measured = _Measured(
            cells_compared=_cell_count(after),
            cells_moved=0,
            policies_moved=0,
            first_period=None,
            max_abs=None,
            max_relative=None,
            from_zero=False,
            worst=None,
            lengths=None,
        )
    else:
        measured = _measure(before, after)
    worst = None
    if measured.worst is not None:
        policy, period, was, now = measured.worst
        worst = MovedCell(
            policy=rows.names[policy],
            row=later.row_of(policy),
            period=period,
            before=was,
            after=now,
        )
    lengths = None
    if measured.lengths is not None:
        count, policy, was_length, now_length = measured.lengths
        lengths = LengthMoved(count, rows.names[policy], was_length, now_length)
    within = (
        _within_band(pair.node, pair.before_node, earlier, later, values)
        if measured.moved
        else None
    )
    line_cause, line_holes = _line_cause(
        cause, holes, said=measured.moved and pair.change is None
    )
    return LineValues(
        node=pair.node,
        before_node=pair.before_node,
        column=later.nodes[pair.node].get("column"),
        paired_by=pair.paired_by,
        change=pair.change,
        compared=True,
        moved=measured.moved,
        cells_compared=measured.cells_compared,
        cells_moved=measured.cells_moved,
        policies_compared=rows.paired.paired,
        policies_moved=measured.policies_moved,
        first_period_moved=measured.first_period,
        max_abs=measured.max_abs,
        max_relative=measured.max_relative,
        from_zero=measured.from_zero,
        worst=worst,
        length_moved=lengths,
        within_band=within,
        cause=line_cause,
        holes=line_holes,
    )


def _cell_count(values: pl.Series) -> int:
    """Return how many cells a line holds: one per policy, or one per period."""
    if _depth(values.dtype) == 0:
        return values.len()
    return int(_one_null_list(values).list.len().sum())


# --- the policy the artifacts carry values for ------------------------------


def _declared(
    later: _Side,
    names: Sequence[str | None],
    measured: Mapping[str, tuple[pl.Series, pl.Series]],
) -> Declared | None:
    """Return the movement of the policy the later artifact carries values for.

    That policy is the first entry of the artifact's policy axis, where it
    names one policy and no fold or cut. Its row is found among the paired
    policies by the name the axis gives it, and each line paired by node id
    is read on that row the way the comparison page reads the two artifacts'
    own values, so that the two readings can be held against each other.
    ``measured`` holds only the lines that moved: a line equal as held moved
    on no row, so the page reads it as not moved too, and its cells are not
    read. None where the axis names no single policy, or where no paired row
    answers to it -- or to more than one.
    """
    axis = later.document.get("policies")
    entry = axis[0] if isinstance(axis, list) and axis else None
    if (
        not isinstance(entry, dict)
        or entry.get("aggregation") is not None
        or entry.get("filter") is not None
        or not isinstance(entry.get("policy_id"), str)
    ):
        return None
    policy = entry["policy_id"]
    found = [at for at, name in enumerate(names) if name == policy]
    if len(found) != 1:
        return None
    row = found[0]
    lines = []
    for node, (before, after) in measured.items():
        moved, magnitude, period, from_zero = page_movement(
            before.slice(row, 1).to_list()[0],
            after.slice(row, 1).to_list()[0],
        )
        if moved:
            lines.append(DeclaredLine(node, magnitude, from_zero, period))
    return Declared(policy, tuple(lines))


# The answer for a pair of values that did not move.
_STILL: Final[tuple[bool, float | None, int | None, bool]] = (False, None, None, False)

# A value one timeline holds and the other does not.
_ABSENT: Final = object()


def page_movement(
    before: object, after: object
) -> tuple[bool, float | None, int | None, bool]:
    """Return how far one policy's value moved, read as the comparison page reads it.

    The page compares two artifacts' own values for the one policy they carry,
    and this is that reading taken on two results files: ``(moved, magnitude,
    period, from_zero)``. A value is each sample as the artifact spells it --
    a non-finite float as its sentinel text -- and two of them moved where
    they are unequal. A pair that is not two finite numbers moved with no
    magnitude; a zero earlier value moved *from 0*; otherwise the magnitude
    is ``|after - before| / |before|``. On a timeline the periods are read in
    order and the largest movement wins, a movement from zero above every
    ratio, the first period at a tie, and a difference in length is a
    movement with no magnitude.

    Examples:
        >>> page_movement([1.0, 2.0], [1.0, 3.0])
        (True, 0.5, 1, False)
        >>> page_movement(0.0, 5.0)
        (True, None, None, True)
        >>> page_movement(float("nan"), float("nan"))
        (False, None, None, False)

    """
    if isinstance(before, list) or isinstance(after, list):
        was = before if isinstance(before, list) else []
        now = after if isinstance(after, list) else []
        out: tuple[bool, float | None, int | None, bool] = (
            len(was) != len(now),
            None,
            None,
            False,
        )
        for at in range(max(len(was), len(now))):
            step = page_movement(
                was[at] if at < len(was) else _ABSENT,
                now[at] if at < len(now) else _ABSENT,
            )
            if not step[0]:
                continue
            out = _larger(out, (True, step[1], at, step[3]))
        return out
    was_said = _ABSENT if before is _ABSENT else json_value(before)
    now_said = _ABSENT if after is _ABSENT else json_value(after)
    if (
        was_said is not _ABSENT
        and now_said is not _ABSENT
        and _same(was_said, now_said)
    ):
        return _STILL
    was_number = _approximately(was_said)
    now_number = _approximately(now_said)
    if was_number is None or now_number is None:
        return (True, None, None, False)
    if not (math.isfinite(was_number) and math.isfinite(now_number)):
        return (True, None, None, False)
    if was_number == 0:
        return (True, None, None, True)
    return (True, abs(now_number - was_number) / abs(was_number), None, False)


def _same(before: object, after: object) -> bool:
    """Whether two values the page holds are one value, as its strict equality says."""
    if isinstance(before, bool) or isinstance(after, bool):
        return type(before) is type(after) and before == after
    return before == after


def _approximately(value: object) -> float | None:
    """Return the number behind a value, or None where it is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _larger(
    a: tuple[bool, float | None, int | None, bool],
    b: tuple[bool, float | None, int | None, bool],
) -> tuple[bool, float | None, int | None, bool]:
    """Return the larger of two movements, as the page ranks them."""
    if not a[0]:
        return b
    if not b[0]:
        return a
    if a[3] != b[3]:
        return a if a[3] else b
    if a[1] is None:
        return a if b[1] is None else b
    if b[1] is None:
        return a
    return b if b[1] > a[1] else a
