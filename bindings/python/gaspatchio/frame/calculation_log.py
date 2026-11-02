# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: How the durable calculation log is written, and how its windows close
# ABOUTME: One mixin the ActuarialFrame inherits, so its class file holds the frame
"""Writing the durable calculation log, and closing its attribution windows.

``gaspatchio.frame.calculations`` says WHAT the log stores -- the record
vocabulary, the boundary marker, the sealed window, the structural
operation a door hands in. This module is the other half: WHEN a record is
minted, what ordinal and ``operation_id`` it gets, how the log is carried
onto a frame derived from an earlier one, and where the attribution window
opens, seals and closes.

Both halves are the audit trail. It is what ``af.graph`` folds into the
artifact a reviewer reads, and what a failing ``collect()`` walks back
through to name the calculation that broke. It was written inside
``ActuarialFrame``'s own class file, where four hundred lines of it stood
between a reader and the frame's vocabulary; here it sits beside the
records it writes.

``ActuarialFrame`` inherits :class:`_CalculationLogMixin`, so every method
below is reached exactly as it always was -- ``af._attribution_ops()``,
``af._seal_attribution_window(op)`` -- from the frame's own methods, from
the accessors that stamp a timeline, from the error boundary, and from the
suites. Inheritance rather than delegation because these methods ARE the
frame's: each one reads and writes the frame's own bookkeeping, and a
delegating copy of every signature in the class file would restate twelve
contracts in order to move them.

The state itself stays on the frame, declared below so this module type-
checks on its own. ``_calculations``, ``_baseline_df`` and
``_sealed_windows`` are the addresses the graph builder, the error
boundary and the suites already read; moving them behind a held object
would rename the audit trail's own coordinates without making one of them
clearer.

Nothing here decides what a calculation MEANS. The op-tree and the Polars
expression arrive already built, from ``ActuarialFrame.__setitem__`` and
its neighbours; this module records them truthfully and says which of them
a failure is still allowed to blame.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Literal

from .calculations import (
    CalculationRecord,
    OverwriteRecord,
    SealedWindow,
    capture_source_span,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    import polars as pl

    from gaspatchio._semantic.ir import OpNode

    from .calculations import (
        BoundaryRecord,
        LogEntry,
        MintedColumns,
        RecordOrigin,
        SelectionRecord,
        SourceSpan,
        StructuralOperation,
    )
    from .plan_writes import Origin


# How many closed attribution windows a frame keeps as suspects. Each one a
# failure walks back through costs a row-capped replay of its own, and the
# error path is inside the edit-run-refine loop; a model with more structural
# operations than this outstanding loses the oldest, which is exactly where
# every closed window was before they were kept at all. Phase-1 setup is
# where structural operations cluster, and a whole phase of them fits.
_MAX_SEALED_WINDOWS = 32

# How many structural operations one sealed window keeps in its chain. A
# window seals with one, and every later operation over an empty window joins
# it rather than sealing a window of its own -- so back to back structural
# calls with no calculation between them grow one tuple without bound. The
# chain is rebuilt on every append, and the confirmation replays the whole of
# it per candidate, so an unbounded chain costs the model's build time and
# the error path's alike: 2,000 consecutive `filter` calls measured 74 ms of
# build on their own. The newest are kept, because those are the operations
# nearest the plan the user collected and so the closest account of the rows
# it computed. Same bound as the sealed windows above, and for the same
# reason -- a run of structural calls long enough to reach it is one no model
# writes on purpose.
_MAX_WINDOW_OPERATIONS = 32


def _kernel_scratch_prefix() -> str:
    """Return the prefix the rollforward kernel's own scratch columns carry.

    A compiled rollforward materializes one struct column so the kernel
    runs once however many states are read back out of it, and
    ``collect()`` strips it off again. It is never part of the model's own
    schema: not a column anybody can ask where the numbers came from, and
    not one the model points supplied either.

    Read from the registry that mints the names rather than repeated here,
    and imported on call because the rollforward package imports the frame.
    """
    from gaspatchio.rollforward import _registry  # noqa: PLC0415 — import cycle

    return _registry.HIDDEN_PREFIX


# The prefix a superseded definition's own output rides under. Reassigning a
# column overwrites it in the plan, so the definition being replaced loses
# its values the moment the next one lands unless something carries them
# forward under a name of its own. That name is never part of the model's
# schema: `columns` does not list it, the graph mints no node for it, and
# `collect()` takes it back off the frame it hands over.
_RETAINED_PREFIX = "__gaspatchio_retained__"


def _retained_column_name(column: str, ordinal: int) -> str:
    """Return the hidden name one definition of ``column`` is carried under.

    The ordinal is what separates them: a column written three times is
    carried twice, once for each definition a later write replaces, and each
    has to reach an export as its own values rather than as whichever of
    them happened to be aliased last.

    Derived from the pair wherever it is needed rather than recorded beside
    the node. A name kept in two places is a name two places can disagree
    about, and the disagreement here would be a value shown against the
    wrong definition -- which is the one thing this whole mechanism exists
    to prevent.
    """
    return f"{_RETAINED_PREFIX}{ordinal}__{column}"


# For each door a model's column comes through: how the column was arriving,
# and the move that fixes its name there. The move differs because the name
# is changed in a different place -- the data before the frame is built, the
# other table before the join, the argument that named it, or the model's own
# line.
_RESERVED_NAME_DOORS: Final[dict[str, tuple[str, str]]] = {
    "arrival": (
        "arrived with the data this frame was built from",
        (
            "Rename it before building the frame: "
            "df.rename({{{name!r}: {suggested!r}}}) on a DataFrame or "
            "LazyFrame, or the key {suggested!r} in a dict."
        ),
    ),
    "assignment": (
        "is being written to this frame",
        "Give it a name without the prefix, such as {suggested!r}.",
    ),
    "rename": (
        "is the new name in this rename",
        "Rename it to a name without the prefix, such as {suggested!r}.",
    ),
    "join": (
        "arrives with the other table in this join",
        (
            "Rename it on the other table before the join: "
            "other.rename({{{name!r}: {suggested!r}}})."
        ),
    ),
    "scenario_column": (
        "is the name passed as scenario_column=",
        "Pass scenario_column= a name without the prefix, such as {suggested!r}.",
    ),
    "new_col_name": (
        "is the name passed as new_col_name=",
        "Pass new_col_name= a name without the prefix, such as {suggested!r}.",
    ),
}

# The doors data from outside the model comes through, and the move that takes
# a compiled rollforward's own working column off it. Before 1.0,
# run_to_parquet and for_each_scenario(return_full_grid=True) wrote that column
# into every batch file, so reading one of those files back brings it in.
# It is the kernel's scratch space, so it is dropped rather than renamed.
_KERNEL_COLUMN_DOORS: Final[dict[str, tuple[str, str]]] = {
    "arrival": (
        "arrived with the data this frame was built from",
        "Drop it before building the frame: df.drop({name!r}).",
    ),
    "join": (
        "arrives with the other table in this join",
        "Drop it from the other table before the join: other.drop({name!r}).",
    ),
}


def _working_prefixes() -> tuple[str, str]:
    """Return the two prefixes the frame keeps its own working columns under."""
    return (_kernel_scratch_prefix(), _RETAINED_PREFIX)


def _working_columns(names: Iterable[str]) -> list[str]:
    """Return the names among ``names`` that are the frame's own working columns.

    Every door a model's column comes through refuses a name under either
    prefix (:func:`_refuse_reserved_column_names`), so a name under one is
    one the frame minted for itself, however the plan came to hold it.
    """
    prefixes = _working_prefixes()
    return [name for name in names if name.startswith(prefixes)]


def _minted_by_the_kernel(name: str) -> bool:
    """Return whether ``name`` is exactly the column a compiled rollforward mints."""
    from gaspatchio.rollforward._registry import (  # noqa: PLC0415 — import cycle
        _is_minted_name,
    )

    return _is_minted_name(name)


def _refuse_reserved_column_names(
    names: Iterable[str],
    *,
    door: Literal[
        "arrival", "assignment", "rename", "join", "scenario_column", "new_col_name"
    ],
) -> None:
    """Refuse a model's column named under one of the frame's working prefixes.

    The frame keeps two kinds of working column in its plan: a compiled
    rollforward's result, under :func:`_kernel_scratch_prefix`, and the values
    of a definition a later assignment replaced, under ``_RETAINED_PREFIX``.
    Every reading of the frame's results takes both off by prefix --
    ``collect()``, ``profile()``, ``schema``, the whole-frame aggregations, a
    batched scenario run -- so a model's own column under either prefix
    vanished from all of them without a word, while the calculation graph
    still drew it and its edges.

    So the name is refused at every door a model's column comes through: the
    data a frame is built from, an assignment, a rename, a join, and the two
    arguments that name a new column, ``scenario_column=`` and
    ``new_col_name=``. The frame's own working columns reach the plan through
    none of them, and stay the only columns under either prefix.

    One name is told apart: the exact column a compiled rollforward mints,
    arriving from outside the model. Batch files written before 1.0 carry it,
    and it holds the kernel's working rather than a value, so the move is to
    drop it rather than rename it.

    Raises:
        ValueError: Naming the column, the prefix it starts with, and the
            move that fixes it from this door.

    """
    for name in names:
        # Both prefixes open with two underscores, so an ordinary column name
        # costs one comparison and nothing else.
        if not (isinstance(name, str) and name.startswith("__")):
            continue
        prefixes = _working_prefixes()
        prefix = next((p for p in prefixes if name.startswith(p)), None)
        if prefix is None:
            continue
        if door in _KERNEL_COLUMN_DOORS and _minted_by_the_kernel(name):
            how, move = _KERNEL_COLUMN_DOORS[door]
            msg = (
                f"The column {name!r} {how}, and it is exactly the column a "
                "compiled rollforward works in: run_to_parquet and "
                "for_each_scenario(return_full_grid=True) wrote it into their "
                "batch files before 1.0. It holds the kernel's working rather "
                "than a value of the model, and collect() would leave it out "
                f"of the results. {move.format(name=name)}"
            )
            raise ValueError(msg)
        how, move = _RESERVED_NAME_DOORS[door]
        msg = (
            f"The column {name!r} {how}, and {prefix!r} is a prefix the frame "
            "keeps for its own working columns: a compiled rollforward's "
            f"result under {prefixes[0]!r}, and the values of a definition a "
            f"later assignment replaced under {prefixes[1]!r}. collect() "
            "leaves every column under either prefix out of what it returns, "
            "so this one would vanish from the results without a word. "
            f"{move.format(name=name, suggested=name.lstrip('_'))}"
        )
        raise ValueError(msg)


@dataclass(slots=True)
class _RunScan:
    """How far the log has been read for one compiled rollforward's run.

    ``searched`` is where a search for the frame's first read of the run
    stopped without finding one; ``first`` is that read once it is found;
    ``checked`` is how far the log from the start of the first read's call
    has been judged for an input written again, and ``moved`` is the first
    such write once one is found -- a calculation, or a write over the input
    straight into the query plan. The log is only ever appended to, so what
    has been read stays read, and each later read of the run starts where
    the last one stopped.
    """

    searched: int = 0
    first: CalculationRecord | None = None
    checked: int = 0
    moved: CalculationRecord | OverwriteRecord | None = None


class _CalculationLogMixin:
    """The frame's durable calculation log, and its attribution windows.

    Inherited by ``ActuarialFrame`` and by nothing else. The attributes
    below are the frame's own, declared here because these methods read
    and write them; ``ActuarialFrame.__init__`` is what creates them, and
    ``_df`` and ``_schema`` are properties there rather than fields.
    """

    _calculations: list[LogEntry]
    _calculation_counts: dict[str, int]
    _next_operation_id: int
    _window_start: int
    _baseline_df: pl.LazyFrame | None
    _sealed_windows: list[SealedWindow]
    _selections: list[SelectionRecord]
    _initial_columns: frozenset[str]
    _wide_judged: bool
    _arrival_names: frozenset[str]
    _bare_arrivals: frozenset[str]
    _arrival_schema: dict[str, pl.DataType]
    _arrival_data: pl.LazyFrame | None
    _book_columns: frozenset[str] | None
    _rebuilt: dict[str, Origin]
    _retained_columns: set[str]
    _rollforward_runs: dict[str, int]
    _rollforward_scans: dict[str, _RunScan]
    _record_roots: dict[int, tuple[CalculationRecord, frozenset[str]]]
    _traced_run: bool
    _df: pl.LazyFrame | None
    _schema: dict[str, pl.DataType] | None

    def _roots_of(self, record: CalculationRecord) -> frozenset[str]:
        """Return the columns a record's expression reads, worked out once.

        Kept by the record's identity, with the record beside it so that an
        id is never mistaken for another record's after a copy.
        """
        cached = self._record_roots.get(id(record))
        if cached is not None and cached[0] is record:
            return cached[1]
        try:
            roots = frozenset(record.expr.meta.root_names())
        except Exception:  # noqa: BLE001 — meta inspection is best-effort
            roots = frozenset()
        self._record_roots[id(record)] = (record, roots)
        return roots

    def _mint_operation_id(self) -> int:
        """Return a fresh operation id, one per assignment call.

        An operation is one call at an assignment door, however many columns
        it defines: a setter assignment mints one id for its single column,
        a multi-column ``with_columns`` mints one id its whole batch shares.
        Transaction boundaries are therefore recorded as data, never
        inferred from adjacency by a later reader.
        """
        operation_id = self._next_operation_id
        object.__setattr__(self, "_next_operation_id", operation_id + 1)
        return operation_id

    def _record_calculation(  # noqa: PLR0913 — one parameter per record field; a config object here would just be the record
        self,
        column: str,
        *,
        node: OpNode,
        expr: pl.Expr,
        dtype: pl.DataType | None,
        operation_id: int,
        origin: RecordOrigin,
        source: SourceSpan | None,
    ) -> None:
        """Append one calculation to the durable log, advancing its ordinal.

        The ordinal is 1-based per column: a column's first assignment is
        ordinal 1, a later reassignment 2. Nothing here touches the
        attribution cursor — a record landing inside the current window is
        the normal case, and the events that move the cursor say so
        explicitly.
        """
        counts = self._calculation_counts
        ordinal = counts.get(column, 0) + 1
        counts[column] = ordinal
        self._calculations.append(
            CalculationRecord(
                column=column,
                ordinal=ordinal,
                operation_id=operation_id,
                node=node,
                expr=expr,
                dtype=dtype,
                source=source,
                origin=origin,
            )
        )

    def _record_minted_columns(
        self,
        columns: dict[str, tuple[OpNode, pl.Expr]],
        *,
        origin: RecordOrigin,
        source: SourceSpan | None = None,
    ) -> None:
        """Record the columns a STRUCTURAL operation put on the frame.

        ``rename``, ``join`` and ``projection.set`` each mint column names
        without an assignment ever being written, so each leaves records
        here. The columns of one call share one operation id and one source
        span, exactly as a ``with_columns`` batch does: they came from one
        statement and one plan step.

        ``source`` is that span, where the caller already knows it. Left
        out, it is walked off the live stack, which is the right answer for
        every step a model or a script took itself; a step taken on their
        behalf says where instead, because the walk would leave this
        framework into the caller's caller rather than into their model.

        The cursor is advanced past whatever this appends, which is the
        difference that matters. Attribution replays a window's tail as
        grouped ``with_columns`` calls against the window's baseline, and
        none of these records can honestly be replayed that way — a
        rename's source name is gone by the time the record exists, and no
        expression on this frame ever computed a joined or stamped column.
        Answering "where did this column come from?" and re-running the
        answer are different jobs; only the first one is being done here.

        Call this AFTER the ``_df`` mutation and after the schema has been
        refreshed: the dtype comes from the resolved post-operation schema,
        which is the only place it is true.
        """
        if not columns:
            return
        operation_id = self._mint_operation_id()
        if source is None:
            source = capture_source_span()
        schema = self._schema or {}
        for name, (node, expr) in columns.items():
            self._record_calculation(
                name,
                node=node,
                expr=expr,
                dtype=schema.get(name),
                operation_id=operation_id,
                origin=origin,
                source=source,
            )
        self._advance_window_cursor()

    def _record_overwrites(
        self,
        columns: Iterable[str],
        *,
        readable: bool,
        schema: Mapping[str, pl.DataType] | None,
        rescanned: bool = False,
    ) -> None:
        """Record the columns a write past the recording doors defined over.

        Called from the ``_df`` setter, which is the one route a write to the
        plan that records nothing passes through, once it has read which of
        the columns the frame accounted for the write defined. Each takes its
        column's next ordinal, as an assignment would, and the columns of one
        write share one operation id and the one line that wrote them.

        The attribution window closes past them, as it does past every entry
        a replay cannot apply. The write itself is not in the log, so a
        calculation logged before it, replayed onto the plan the write left,
        would be replayed onto a plan its window never held.

        Args:
            columns: The overwritten columns, in the order to record them.
            readable: False where the frame could not read which columns the
                write defined and is recording every column it accounted for
                that the plan still holds.
            schema: The plan's types after the write, or None where the plan
                could not say.
            rescanned: True where the plan written was nothing but a table
                in memory, values handed over in place of a plan.

        """
        names = list(columns)
        if not names:
            return
        operation_id = self._mint_operation_id()
        source = capture_source_span()
        counts = self._calculation_counts
        for column in names:
            ordinal = counts.get(column, 0) + 1
            counts[column] = ordinal
            self._calculations.append(
                OverwriteRecord(
                    column=column,
                    ordinal=ordinal,
                    operation_id=operation_id,
                    dtype=None if schema is None else schema.get(column),
                    source=source,
                    readable=readable,
                    rescanned=rescanned,
                )
            )
        self._advance_window_cursor()

    def _live_entries(self) -> dict[str, CalculationRecord | OverwriteRecord]:
        """Return each column's latest entry in the log: what its account rests on."""
        live: dict[str, CalculationRecord | OverwriteRecord] = {}
        for entry in self._calculations:
            if isinstance(entry, CalculationRecord | OverwriteRecord):
                live[entry.column] = entry
        return live

    def _accounted_columns(self) -> frozenset[str]:
        """Return the columns whose account this frame can vouch for now.

        A column whose latest entry is a calculation, and a column the data
        arrived with that nothing has written since. Not a column whose
        latest entry is a write past the doors: the frame already says it
        cannot account for that one, and a second write over it changes
        nothing the frame was vouching for. Nor a column the frame arrived
        holding that another frame calculated, which it never vouched for.
        """
        live = self._live_entries()
        calculated = {
            column
            for column, entry in live.items()
            if isinstance(entry, CalculationRecord)
        }
        arrived = {column for column in self._initial_columns if column not in live}
        return frozenset(calculated | arrived)

    def _unaccounted_columns(self) -> frozenset[str]:
        """Return the columns this frame holds that nothing accounts for.

        Every column a model holds should be one of three things: a
        calculation the frame recorded, a field the data arrived with, or a
        column of values injected at a known line. A column that is none of
        them — in the schema, absent from the log and from the arriving
        set — has no account of itself anywhere, and the calculation graph
        mints a typed leaf for it rather than inventing a source.

        This is the one place that difference is taken. The graph reads it
        to mint those leaves; the successor-carry below reads it so that a
        frame derived from this one does not quietly relabel them as
        columns its data arrived with. Two subtractions in two places would
        eventually disagree about what a model failed to explain, in the
        one artifact whose whole job is to say how each number was made.

        The rollforward kernel's own scratch columns are not in the answer:
        they are not part of the model's own schema at all (see
        :func:`_kernel_scratch_prefix`). Neither is a superseded definition
        carried forward under :func:`_retained_column_name`: it is a second
        copy of a column the log already accounts for, and calling it
        unexplained would mint a hole for a definition the graph already
        holds a node for.
        """
        recorded = {record.column for record in self._calculation_records()}
        hidden = (_kernel_scratch_prefix(), _RETAINED_PREFIX)
        unexplained = frozenset(self._schema or ()) - self._initial_columns - recorded
        return frozenset(
            column for column in unexplained if not column.startswith(hidden)
        )

    def _carry_calculation_log(
        self,
        successor: _CalculationLogMixin,
        minted: MintedColumns | None = None,
        *,
        boundary: BoundaryRecord | None = None,
    ) -> None:
        """Carry this frame's calculation log onto a frame derived from it.

        A derived frame — a projection timeline stamped onto model points, a
        scenario axis cross-joined in — is the same model one step further
        on, not a new one. Dropping the log there would make every column
        calculated before that step unanswerable, which is exactly the
        question an audit asks first.

        The attribution window does NOT carry. The successor's plan is
        structurally different from the one those calculations were applied
        to, so replaying them against it could name the wrong column; the
        successor's next record opens a fresh window over a fresh baseline.

        Copies, not shared references: two frames appending to one list
        would each end up holding the other's calculations.

        ``_traced_run`` carries for the same reason the log does: the
        successor is the frame the runner will collect, and whether the
        user asked for a traced run is a fact about the RUN, not about
        which frame object survived a cross-join.

        ``minted`` names the columns the derivation step created for itself
        — a timeline date exploded out of a start and an end, a date offset
        by a duration — with the op-tree and the expression each was built
        from, exactly as ``_record_minted_columns`` takes them, and with the
        one origin that labels all of them. The columns and their label
        arrive together because they are one fact: a caller able to hand
        over the columns alone would leave the label to a default and
        record a plain assignment's provenance for a column no assignment
        wrote. They are recorded on the successor BEFORE the arriving set
        below is worked out: a column with a record of its own is a
        calculation, and the arriving set has to be able to see that. A step
        that creates nothing (a cross-joined scenario axis is data, not a
        formula) passes nothing and the successor's log is this one's.

        ``boundary`` marks a step at which the plan stopped being a recipe:
        the successor holds values rather than the calculation that made
        them. It lands between the carried log and anything ``minted``
        records, which is what puts the columns that were live at the freeze
        on one side of it and the columns the step brought in on the other.
        Its ``position`` is restated here rather than trusted from the
        caller: what kind of reset it was and where it was written are the
        caller's to know, and where it falls in the log is this method's.
        """
        calculations = list(self._calculations)
        if boundary is not None:
            calculations.append(replace(boundary, position=len(calculations)))
        successor._calculations = calculations
        # The rows the model chose to value, carried with the log they are
        # positioned in: a successor values the rows this frame kept, and a
        # record that forgot the choice at a cross-join would say every row
        # of the book was valued.
        successor._selections = list(self._selections)
        successor._calculation_counts = dict(self._calculation_counts)
        successor._next_operation_id = self._next_operation_id
        successor._window_start = len(calculations)
        successor._baseline_df = None
        successor._sealed_windows = []
        successor._traced_run = self._traced_run
        # Whether the book's wide integer columns were judged where they
        # arrived: a fact about the book the run started over, which a
        # derivation step built over this frame's plan does not change.
        successor._wide_judged = self._wide_judged
        if minted is not None:
            successor._record_minted_columns(
                minted.columns, origin=minted.origin, source=minted.source
            )
        # Which of the successor's columns arrived with its data. A column
        # the carried log records is a calculation rather than an input, so
        # the phase-1 columns the model computed stay attributed to their
        # records.
        #
        # A cross-joined `scenario_id` is recorded above rather than left to
        # fall through here, and that is the point of the record: the model
        # points file has no such column, so calling it an arrival stated
        # positively that the book supplied it. What the axis is, is a whole
        # column handed to the model at a known line — `injected`, with the
        # plan's own call site on it.
        #
        # The two exclusions below are columns that reach the successor
        # looking exactly like that axis used to — present, unrecorded — and
        # are not inputs either. A column THIS frame could not account for
        # does not become accounted for by being carried one step further
        # on: calling it an input here would erase it and then say the model
        # points supplied it. The kernel's scratch column is not the model's
        # data on the successor any more than here, and neither is a
        # superseded definition carried forward beside it.
        recorded = {record.column for record in successor._calculation_records()}
        unaccounted = self._unaccounted_columns()
        hidden = (_kernel_scratch_prefix(), _RETAINED_PREFIX)
        successor._initial_columns = frozenset(
            column
            for column in successor._schema or ()
            if column not in recorded
            and column not in unaccounted
            and not column.startswith(hidden)
        )
        # The names those columns arrived under, which is this frame's
        # history plus whatever the step itself brought. A vendor name this
        # frame renamed away is not a column of the successor's, but the
        # successor carries the rename record that reads it -- so the
        # vendor name is part of what the successor can vouch for, and the
        # graph can still say which field of the source file each input
        # was. Left to the successor's own schema alone, an ordinary model
        # that renames its columns on the way in loses that the moment a
        # scenario axis widens it. A name this frame could not account for
        # is already out of the successor's arriving set, so it stays a
        # hole here too.
        successor._arrival_names = self._arrival_names | successor._initial_columns
        # And the types, merged the same way and over the same two sources:
        # what this frame recorded at its own door, plus the step's own
        # arrivals typed off the successor's schema. This frame's entries
        # win where both hold a name, because this record is the one that
        # was taken when the column arrived and a merge that let a later
        # step rewrite an entry would be a record that moves.
        successor._arrival_schema = {
            **{
                column: dtype
                for column, dtype in (successor._schema or {}).items()
                if column in successor._initial_columns
            },
            **self._arrival_schema,
        }
        # What the frame at the head of this chain was handed at its own
        # constructor, passed straight on rather than merged. A derivation
        # step's own new columns are already accounted for above -- the log
        # records the step that brought them -- so widening this set here
        # would only blur the one distinction it exists to draw: which
        # columns the model's data actually arrived with, as against which
        # columns a DataFrame handed to a fresh constructor happened to
        # hold. An export compares the two, and a rebuilt frame is the one
        # that comes back holding names the run never started with.
        successor._bare_arrivals = self._bare_arrivals
        # The columns the frame at the head of this chain arrived holding
        # that another frame calculated, passed on whole for the reason the
        # arrival names are: they are what the model's data was handed, under
        # the names it was handed them, and the calculations the successor
        # carries still read them by those names. A step further on does not
        # make them inputs, so the successor reports them as this frame does.
        successor._rebuilt = dict(self._rebuilt)
        # And the data those columns arrived in, passed on for the same
        # reason: the successor is the same model one step further on, built
        # over the same book, and an export of it digests that book rather
        # than whatever the step reshaped it into -- a timeline exploded out
        # of it, a scenario axis crossed onto it, values that went out of the
        # frame and came back.
        successor._arrival_data = self._arrival_data
        # And the book's columns, where a runner that watched the run begin
        # told the frame at the head of this chain: the successor is the same
        # run, over the same book.
        successor._book_columns = self._book_columns
        # The superseded definitions this frame is carrying, kept only where
        # the successor's plan actually still holds them. A cross-joined
        # scenario axis widens the plan and takes them along; a frame rebuilt
        # from values that came back from outside holds none, and claiming
        # otherwise would send a later drop looking for a column nothing
        # wrote. The successor's own schema is the test, and it is already
        # resolved above.
        successor._retained_columns = {
            name for name in self._retained_columns if name in (successor._schema or ())
        }
        # Where each compiled rollforward's struct went on the plan, by the
        # same positions, since the log above is carried entry for entry. A
        # successor whose plan dropped a struct answers for none of its
        # columns' runs anyway: the accessors that read one check the plan
        # holds it first.
        successor._rollforward_runs = dict(self._rollforward_runs)
        # How far the log has been read for each run, and the columns each
        # record reads: both are about entries the successor holds at the
        # same positions, so it carries on from where this frame stopped.
        successor._rollforward_scans = {
            name: replace(scan) for name, scan in self._rollforward_scans.items()
        }
        successor._record_roots = dict(self._record_roots)

    def _calculation_records(self) -> list[CalculationRecord]:
        """Return the whole log's calculations, boundary markers dropped."""
        return [
            entry
            for entry in self._calculations
            if isinstance(entry, CalculationRecord)
        ]

    def _open_attribution_window_if_needed(self) -> None:
        """Snapshot the pre-op plan when the first record of a window lands.

        Error-boundary diagnosis replays against this baseline, never
        against the applied ``_df``: ``_df`` already carries every recorded
        calculation, so replaying on top of it would apply self-referential
        assignments twice and blame the wrong column.

        The condition is the calculation log's own, and only its own: the
        baseline is refreshed exactly when the log's window is empty, which
        makes ``_baseline_df`` a snapshot of the plan as it stood at the
        window's start for every window there is. That is the invariant
        replay depends on — the window's records applied to the window's
        baseline reproduce the live plan, calculation for calculation.

        This is called before every ``_df`` mutation that lands a record,
        and again straight after the unrecorded ones a window must not
        straddle, so "window empty" and "the plan the window opened over"
        always name the same moment.
        """
        if self._window_start == len(self._calculations):
            object.__setattr__(self, "_baseline_df", self._df)

    def _advance_window_cursor(self) -> None:
        """Close the calculation log's attribution window at the log's end.

        The one way the window ever moves. Nothing is removed: what the
        model calculated stays answerable, only which calculations are
        candidates for blame changes.
        """
        object.__setattr__(self, "_window_start", len(self._calculations))

    def _attribution_ops(self) -> list[CalculationRecord]:
        """Return the calculations recorded since the window opened.

        The tail of the log, from the cursor on, with boundary markers
        dropped: a boundary defines no column, so it can never be the
        calculation a failure is attributed to.
        """
        return [
            entry
            # INVARIANT: no BoundaryRecord should ever reach this filter. A
            # boundary marks a plan reset, and every event that appends one
            # must advance the cursor past it in the same breath — replay
            # splices the window's records straight onto the window's
            # baseline, so a boundary inside the tail means records from
            # BEFORE the reset are about to be replayed onto a plan from
            # after it. `materialize()` is the only appender there is, and
            # it closes the window in the same breath, so a boundary that
            # DOES turn up here is a cursor bug at whatever appended it —
            # this filter is the second line of defence, not the contract.
            # An OverwriteRecord is held to the same rule for the same
            # reason: the write it marks is not in the log to be replayed,
            # and `_record_overwrites` closes the window past it.
            for entry in self._calculations[self._window_start :]
            if isinstance(entry, CalculationRecord)
        ]

    def _seal_attribution_window(self, operation: StructuralOperation) -> None:
        """Close the current window over the plan it opened over, and keep it.

        The move a structural plan change makes. The cursor advances exactly
        as it always did — the window ENDS here, because a record from
        before an unrecorded plan change cannot be replayed on top of the
        plan that follows it. What is added is that the window is not thrown
        away on the way past: its records and the baseline they were applied
        to are kept together, and that pair reconstructs the plan the frame
        held one step earlier (see ``SealedWindow``). ``operation`` — the
        structural operation itself, as a callable the frame ran its plan
        through — is kept with them, so a calculation named on that plan can
        be confirmed on the rows the operation went on to keep.

        A window with nothing in it seals nothing — there is no baseline to
        pair records with until the window's first record lands, and an
        empty window is not a suspect. Its operation is not lost, though: it
        joins the chain of the last sealed window, whose rows go on to
        survive this operation too, so a `filter` straight after a `filter`
        confirms through both. Only the newest ``_MAX_WINDOW_OPERATIONS`` of
        that chain are kept, for the reason given where it is defined.

        Only the newest ``_MAX_SEALED_WINDOWS`` are kept. Each one a failure
        walks back through costs a replay of its own, and the error path has
        to stay inside the edit-run-refine loop; a model with more structural
        operations than that loses the oldest, which is where every one of
        them was before sealing existed.
        """
        records = self._attribution_ops()
        if records:
            self._sealed_windows.append(
                SealedWindow(
                    records=tuple(records),
                    baseline=self._baseline_df,
                    operations=(operation,),
                )
            )
            del self._sealed_windows[:-_MAX_SEALED_WINDOWS]
        elif self._sealed_windows:
            last = self._sealed_windows[-1]
            self._sealed_windows[-1] = replace(
                last,
                operations=(*last.operations, operation)[-_MAX_WINDOW_OPERATIONS:],
            )
        self._advance_window_cursor()

    def _reset_attribution_window(self, operation: StructuralOperation) -> None:
        """Restart collect-error attribution after a structural plan change.

        Structural operations (filter, select, drop, sort, rename, join, the
        projection timeline, a date verb, a rollforward's materialisation)
        change the plan's SHAPE, so nothing recorded before them can be
        replayed against the plan that follows. Each hands its ``operation``
        in, the callable it ran the plan through, for the sealed window to
        keep (see ``_seal_attribution_window``).

        Some of them leave records of their own now: ``rename``, ``join`` and
        ``projection.set`` each say which names they minted. Those records
        are not replayable at all — a rename's source name is gone, and a
        joined or stamped column has no formula this frame ever applied — so
        each of those callers appends them AFTER this call and then advances
        the cursor a second time, via ``_record_minted_columns``, which
        seals nothing.

        The calculation log restarts by sealing its window and advancing the
        cursor: what the model calculated stays answerable after a filter,
        and stops being a suspect for anything the plan does from here. The
        next record snapshots a fresh baseline from the post-mutation plan.
        """
        self._seal_attribution_window(operation)

    def _close_attribution_window(self) -> None:
        """Narrow attribution to nothing after a successful materialisation.

        A successful collect proves every recorded calculation sound, so
        the window restarts — the next assignment snapshots the then-current
        plan as its baseline, and replay is scoped to what has happened
        since the last success.

        The sealed windows go with it, and for the same reason: a run that
        worked cleared every calculation that fed it, whichever side of a
        filter it was written on. This is the one thing that empties them.

        The cursor advances; the records do not move. Nothing is dropped
        here and nothing anywhere else drops one either: a model that ran
        successfully is exactly the model someone will ask questions about
        (see the memory contract on ``_calculations``).
        """
        self._sealed_windows.clear()
        self._advance_window_cursor()
