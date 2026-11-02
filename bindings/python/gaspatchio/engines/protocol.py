# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What an engine is, what it hands back, and where the values come out.

The framework's public edge for a second engine. A document and the book's
input columns go in; the columns the manifest names come out, through a sink
that makes them visible at one moment and not before. The Polars path does
not use any of this and is not rewritten to fit it -- the seam is for the
engines that arrive later, and the core exercises it with no engine
installed.

**One result manifest, four readers.** The producer-side reference adapter
writes one, an engine writes one, the comparator reads two, and a sink
carries one into the result file's metadata. They are the same object
because the question each of them asks is the same question: which node is
in which column, in what type, matched to the other side by what, over which
graph and which book. A comparison whose two sides answered that question in
two shapes would be comparing on assumptions rather than on statements.

**Two sinks, one executor.** :class:`FrameSink` accumulates in memory and
hands back a frame -- the frame door's answer. :class:`ParquetSink` writes
each batch away beside the destination as it arrives and renames one
finished file into place on publish -- the file door's. Publication is the
only moment anything becomes visible, which is what makes "nothing partial
is ever published" a property of the sink rather than a discipline every
engine has to remember.

**The book's order is the sink's to keep.** An engine may compute a book in
an order of its own -- the JAX engine groups policies by the width of their
timelines -- and hand each batch over the moment it finishes, with the book
positions of its rows. Both sinks put every row back where its policy stood
when they publish, and refuse a set of positions that is not the book's, so
no engine has to hold a finished batch back to keep a reader's order.

**An engine that knows its batches keep the book's order says so first.**
It knows before its first batch -- the JAX engine's batching plan is settled
before anything is computed -- and it says so as it opens the sink. The file
sink then writes each batch straight into the one result, so every row is
written once rather than staged and written again to restore the order. The
promise is held against every batch's positions, so a batch that breaks it
is refused rather than written out of place.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Protocol, get_args

import numpy as np
import polars as pl
from polars.io.plugins import register_io_source

from gaspatchio._identity import content_sha_of

from .report import EngineRefusal, Refusal, RunReport

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

    from numpy.typing import ArrayLike


__all__ = [
    "VALUE_BEARING",
    "ArrowStreamExportable",
    "Engine",
    "EngineResult",
    "FrameSink",
    "NodeStatus",
    "ParquetSink",
    "Producer",
    "ResultManifest",
    "Scope",
    "Sink",
    "TreeStatus",
    "digest_of_inputs",
    "read_manifest",
    "write_with_manifest",
]

TreeStatus = Literal["lowered", "lowered-off-trace", "refused"]
Scope = Literal["final-schema", "every-node"]

# The node kinds that carry values, and the one place that list is written.
# A rollforward node is one whole compilation and holds no column, so nothing
# can be two sides of a comparison of it; a hole is the absence of an account
# and holds no values either. The ``every-node`` scope means exactly these
# three, and the adapter that writes a manifest and the comparator that reads
# one have to mean the same thing by it.
VALUE_BEARING: frozenset[str] = frozenset({"computed", "input", "state"})

# Every key a manifest writes into a result file's metadata carries this, so
# a file's own columns and a reader's bookkeeping cannot collide however a
# model names a column.
_METADATA_PREFIX = "gaspatchio."

# The suffix an unpublished result carries while it is being written. It is
# not a Parquet file by name, so nothing downstream picks it up as one, and
# the uuid keeps two runs writing to one destination from writing over each
# other's working.
_UNPUBLISHED = "unpublished"


@dataclass(frozen=True, slots=True)
class NodeStatus:
    """What one engine can do with one node, and on what grounds.

    Attributes:
        node_id: The node this is about.
        status: Lowered into the trace, lowered outside it, or refused.
        condition: What the status holds under -- "operands are inputs or
            literals" for an off-trace lowering, the refusal's own sentence
            where it refuses. Never a bare status: an identifier alone says
            nothing about the invocation the model actually wrote.
        clause: The specification clause the status rests on.

    """

    node_id: str
    status: TreeStatus
    condition: str | None
    clause: str | None


@dataclass(frozen=True, slots=True)
class ResultManifest:
    """What one side of a comparison is: its columns, its types, its book.

    Attributes:
        scope: ``final-schema`` -- the nodes the model's own schema holds --
            or ``every-node``, which carries every value-bearing node by
            node id, so a comparison can take a line's scale from the values
            it reads as well as from its own.
        columns: Node id to the column carrying it. Under ``every-node``
            that is every computed node, every input and every state
            balance, and never a bare rollforward structural node, which is
            a compilation rather than a value.
        dtypes: Node id to the type the node record declares -- the
            artifact's own vocabulary, not an engine's spelling.
        row_identity: The columns that together name each row once -- the
            policy-id column, then the scenario column where a scenario axis
            crossed the book -- or None where no column the run resolved
            names each row once. A comparison pairs two files' rows by it,
            and pairs them by position only where it can show the two are in
            one order (see :func:`~gaspatchio.engines.compare.compare_results`).
        graph_fingerprint: The artifact these results are of.
        inputs_digest: sha256 over the input columns the artifact's input
            nodes name, in name order, as Parquet bytes.
        producer: ``polars`` or the engine's name.
        versions: What produced it -- interpreter, library and extension
            identities, so a result that moves can be placed.

    """

    scope: Scope
    columns: dict[str, str]
    dtypes: dict[str, str]
    row_identity: tuple[str, ...] | None
    graph_fingerprint: str
    inputs_digest: str
    producer: str
    versions: dict[str, str]

    def to_metadata(self) -> dict[str, str]:
        """Return the manifest as flat JSON-valued file metadata.

        Flat because Parquet's key-value metadata is flat, and JSON-valued
        so that a column name carrying a comma or a brace survives the trip
        -- which a delimiter-joined encoding would not.
        """
        return {
            f"{_METADATA_PREFIX}scope": json.dumps(self.scope),
            f"{_METADATA_PREFIX}columns": json.dumps(self.columns, sort_keys=True),
            f"{_METADATA_PREFIX}dtypes": json.dumps(self.dtypes, sort_keys=True),
            f"{_METADATA_PREFIX}row_identity": json.dumps(
                None if self.row_identity is None else list(self.row_identity)
            ),
            f"{_METADATA_PREFIX}graph_fingerprint": json.dumps(self.graph_fingerprint),
            f"{_METADATA_PREFIX}inputs_digest": json.dumps(self.inputs_digest),
            f"{_METADATA_PREFIX}producer": json.dumps(self.producer),
            f"{_METADATA_PREFIX}versions": json.dumps(self.versions, sort_keys=True),
        }

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, str]) -> ResultManifest:
        """Return the manifest a result file carries, or say what is missing.

        A file with no manifest is not a result this comparison can place:
        it may hold the right numbers under the right names and still be of
        another graph, another book or another scope, and none of that is
        recoverable from the columns.
        """
        read: dict[str, object] = {}
        for field in (
            "scope",
            "columns",
            "dtypes",
            "row_identity",
            "graph_fingerprint",
            "inputs_digest",
            "producer",
            "versions",
        ):
            key = f"{_METADATA_PREFIX}{field}"
            if key not in metadata:
                message = (
                    f"This file carries no {key!r}, so it does not say which "
                    "graph, which book or which scope its columns are of. "
                    "Write it with gspio run-model --results, gspio "
                    "run-single-policy --results, gspio calc-graph --results "
                    "or gspio run-artifact, which put the manifest in the "
                    "file's own metadata."
                )
                raise ValueError(message)
            problem = _member_damage(field, metadata[key])
            if problem is not None:
                message = (
                    f"This file's result manifest is damaged: {problem}. It "
                    "no longer says in full which graph, which book or which "
                    "scope its columns are of. Write the results again with "
                    "the gspio command that produced them."
                )
                raise ValueError(message)
            read[field] = json.loads(metadata[key])
        return cls(
            scope=read["scope"],  # type: ignore[arg-type]
            columns=read["columns"],  # type: ignore[arg-type]
            dtypes=read["dtypes"],  # type: ignore[arg-type]
            row_identity=_identity_read(read["row_identity"]),
            graph_fingerprint=read["graph_fingerprint"],  # type: ignore[arg-type]
            inputs_digest=read["inputs_digest"],  # type: ignore[arg-type]
            producer=read["producer"],  # type: ignore[arg-type]
            versions=read["versions"],  # type: ignore[arg-type]
        )


# The JSON shape each manifest member is written in, by ``to_metadata``. A
# member of another shape was not written by it, and is named rather than
# read: a list where the columns' mapping belongs would otherwise reach the
# comparison and fail there with a traceback. ``row_identity`` is read, in
# either of its two forms, by ``_identity_read``.
_TEXT_MEMBERS: Final = frozenset(
    {"scope", "graph_fingerprint", "inputs_digest", "producer"}
)
_MAPPING_MEMBERS: Final = frozenset({"columns", "dtypes", "versions"})
_SCOPES: Final = frozenset(get_args(Scope))


def _member_damage(field: str, raw: str) -> str | None:
    """Return what is wrong with one manifest member as written, or None.

    A member that does not parse as JSON, or parses to a shape its writer
    never writes -- text where text belongs, a mapping of text to text where
    a mapping belongs, one of the two scopes for ``scope`` -- is damage, and
    the sentence names the member and what it holds instead.
    """
    key = f"{_METADATA_PREFIX}{field}"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as unread:
        return f"{key} does not parse ({unread.msg})"
    except RecursionError:
        return f"{key} nests deeper than any manifest is written"
    if field in _TEXT_MEMBERS and not isinstance(value, str):
        return f"{key} is {_shape_of(value)}, where its writer states text"
    if field == "scope" and value not in _SCOPES:
        return f"{key} is {value!r}, which is neither of {sorted(_SCOPES)}"
    if field in _MAPPING_MEMBERS and not (
        isinstance(value, dict) and all(isinstance(one, str) for one in value.values())
    ):
        return (
            f"{key} is {_shape_of(value)}, where its writer states a mapping "
            "of names to text"
        )
    return None


def _shape_of(value: object) -> str:
    """Return a JSON value's shape in words, for a damaged member's sentence."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a true-or-false value"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    return "a mapping whose values are not all text"


def _identity_read(stated: object) -> tuple[str, ...] | None:
    """Return the columns a manifest's ``row_identity`` names, in either form.

    A list of column names now; one name, as a file written before a row
    could be named by more than one column states it; or null. Anything else
    is a manifest that does not say which columns name a row, and is refused
    rather than read as no identity -- which would send the comparison to
    position on the strength of a member it could not read.
    """
    if stated is None:
        return None
    if isinstance(stated, str):
        return (stated,)
    if (
        isinstance(stated, list)
        and stated
        and all(isinstance(one, str) for one in stated)
    ):
        return tuple(stated)
    message = (
        f"This file's {_METADATA_PREFIX}row_identity is {stated!r}, which is "
        "neither null nor the names of the columns that name its rows. Write "
        "the results again with the gspio command that produced them."
    )
    raise ValueError(message)


@dataclass(frozen=True, slots=True)
class EngineResult:
    """What a run hands back: the values, what they are, and what was noted.

    Attributes:
        columns: One row per input row, columns as the manifest names them.
            A sink that published to a file carries the schema here and no
            rows -- see :class:`ParquetSink`, which says so in its own words.
        manifest: What these columns are.
        report: What the run wants said and did not stop for.

    """

    columns: pl.DataFrame
    manifest: ResultManifest
    report: RunReport


class ArrowStreamExportable(Protocol):
    """Anything that hands its rows over as an Arrow C stream.

    The boundary a batch crosses on its way to a sink, stated in Arrow's terms
    rather than one library's: a ``polars.DataFrame`` is one, and so is a
    ``pyarrow.Table`` or a ``RecordBatchReader``, or whatever an engine in
    another language hands across. The sink takes the rows without copying
    them -- the capsule interface lends the buffers, it does not duplicate
    them.
    """

    def __arrow_c_stream__(self, requested_schema: object | None = None) -> object:
        """Return a PyCapsule holding an ``ArrowArrayStream``."""
        ...


class Sink(Protocol):
    """Where a run's values go, and the one moment they become visible."""

    def open(self, manifest: ResultManifest, *, in_order: bool = False) -> None:
        """Take the run's manifest, and whether its batches arrive in the book's order.

        ``in_order`` is the engine's promise, made before its first batch,
        that every batch it hands over is the book's next rows: the first
        starts at row 0 and each one starts where the one before it ended.
        It lets a file sink write each batch where it will stand in the
        result, the moment it arrives, so nothing has to be read back and
        written a second time to put the book in order -- in row groups
        sized from the first batch's rows, which a file begun cannot resize.
        So an engine makes it only where its rows cannot widen either: the
        JAX engine for a book whose batching plan runs it front to back and
        whose policies share one timeline on every axis, as levels 4 and 5
        do. The promise is checked against every batch's positions, not
        trusted (see :meth:`write_batch`).
        """
        ...

    def write_batch(
        self, frame: ArrowStreamExportable, *, rows: ArrayLike | None = None
    ) -> None:
        """Take one batch of rows, in the manifest's columns, and where they stand.

        Any Arrow stream: the JAX engine hands a ``polars.DataFrame``, and an
        engine that builds its batches in pyarrow or outside Python hands
        those as they are. Each sink here reads the batch as a Polars frame,
        which for a Polars frame is the frame itself and for anything else is
        a borrow of its buffers.

        ``rows`` says where each row of the batch stands in the book: its
        position, counted from zero, ascending within the batch. Batches may
        arrive in any order. An engine that computes a book in an order of
        its own -- the JAX engine groups policies by the width of their
        timelines -- hands each batch over the moment it finishes, and the
        sink puts every row back where its policy stood when it publishes.
        ``None`` means the batch is the book's next rows, in order, after the
        last batch written. A run uses one form throughout: a batch with no
        positions follows the batch written before it, and a run that places
        its batches by position has no "before" to follow.

        Raises:
            ValueError: If the positions are not whole numbers from zero, one
                per row and ascending; if the run mixes the two forms; or if
                the run promised the book's order when it opened the sink and
                this batch is not the book's next rows. Each is a defect in
                the engine, and the sink leaves nothing behind before it says
                so.

        """
        ...

    def publish(self, report: RunReport) -> EngineResult:
        """Make everything written visible at once, in the book's order.

        Raises:
            ValueError: If the rows written are not the book's rows exactly
                once each -- a position missing, or one held twice. The
                message says how many. Nothing is published, and nothing
                written remains.

        """
        ...

    def abandon(self) -> None:
        """Leave nothing visible behind."""
        ...


class Engine(Protocol):
    """A second implementation of the model the artifact describes."""

    name: str
    version: str

    def validate_tree(self, document: dict[str, object]) -> tuple[NodeStatus, ...]:
        """Say what this engine can do with each node, reading no book."""
        ...

    def run(
        self,
        document: dict[str, object],
        inputs: pl.DataFrame,
        sink: Sink,
        *,
        every_node: bool = False,
    ) -> EngineResult:
        """Run the document over the book and publish through the sink."""
        ...


@dataclass(frozen=True, slots=True)
class Producer:
    """What produced a result that carries no rows, and what it read.

    A per-policy result says this in its manifest, beside the columns the
    manifest describes. An aggregation publishes no columns -- folding on the
    device is worth doing precisely because the rows never leave it -- so the
    same facts travel on their own: which engine, under which versions, over
    which graph and which book. ``run_aggregated``'s audit record writes them
    out beside the totals, so a reported number can still be placed.

    Attributes:
        engine: The engine's name, as ``engine=`` and ``--engine`` spell it.
        versions: What produced it, in the result manifest's own keys.
        graph_fingerprint: The artifact the totals are of.
        inputs_digest: The book, digested as a result manifest digests it:
            the artifact's input columns in name order, under the
            specification's content grammar (section 12.3).
        notes: What the run wanted said and did not stop for -- the compile
            cache's outcome, how the book was batched.

    """

    engine: str
    versions: dict[str, str]
    graph_fingerprint: str
    inputs_digest: str
    notes: tuple[str, ...] = ()


class FrameSink:
    """Keeps the batches in memory and hands back one frame, in the book's order.

    The frame door's sink: ``af.collect(engine=...)`` is asked for values in
    the caller's own process, so there is nothing to publish to but memory.
    Nothing is visible until :meth:`publish`, which is the same contract the
    file sink keeps -- a run that refuses part way through leaves the caller
    with an exception and no half-built frame. Batches handed over with their
    book positions are put back in the book's order at publication, with one
    gather over the whole frame.
    """

    def __init__(self) -> None:
        """Start with nothing written and no manifest taken."""
        self._manifest: ResultManifest | None = None
        self._batches: list[pl.DataFrame] = []
        self._placement = _Placement()

    def open(self, manifest: ResultManifest, *, in_order: bool = False) -> None:
        """Take the manifest this run writes under, and the order it promised.

        The frame is put in the book's order at publication whichever way
        the batches came. A promise of the book's order is still held
        against every batch, so the two sinks refuse a broken one alike.
        """
        self._close()
        self._manifest = manifest
        self._placement = _Placement(in_order=in_order)

    def write_batch(
        self, frame: ArrowStreamExportable, *, rows: ArrayLike | None = None
    ) -> None:
        """Hold one batch of rows, and where they stand in the book.

        Raises:
            RuntimeError: If the sink is not open.
            ValueError: As :meth:`Sink.write_batch` says. Everything held is
                dropped first.
            polars.exceptions.PolarsError: If the batch's columns are not the
                first batch's (see :func:`_same_columns`). Everything held is
                dropped first.

        """
        if self._manifest is None:
            raise RuntimeError(_NOT_OPEN)
        held = _as_frame(frame)
        try:
            if self._batches:
                _same_columns(self._batches[0], held)
            self._placement.place(held.height, rows)
        except BaseException:
            self.abandon()
            raise
        self._batches.append(held)

    def publish(self, report: RunReport) -> EngineResult:
        """Return every batch as one frame, in the book's order, under the manifest.

        Raises:
            RuntimeError: If the sink is not open.
            ValueError: If the rows written are not the book's rows exactly
                once each. Everything held is dropped first.

        """
        manifest = self._manifest
        if manifest is None:
            raise RuntimeError(_NOT_OPEN)
        batches, placement = self._batches, self._placement
        # Published once: what was handed over is the caller's now, and a
        # second publication would be a second answer to one run.
        self._close()
        if not batches:
            return EngineResult(
                columns=pl.DataFrame(schema={}), manifest=manifest, report=report
            )
        written = placement.covered()
        frame = _in_the_books_order(pl.concat(batches, how="vertical"), written)
        return EngineResult(columns=frame, manifest=manifest, report=report)

    def abandon(self) -> None:
        """Drop everything written, and the manifest with it.

        An abandoned sink takes no more batches and publishes nothing until it
        is opened again, so an engine that carried on past its own failure
        cannot publish whatever happened to be left.
        """
        self._close()

    def _close(self) -> None:
        """Let go of everything this run handed over, and of the manifest."""
        self._manifest = None
        self._batches = []
        self._placement = _Placement()


class ParquetSink:
    """Writes each batch away as it arrives, and renames one file into place.

    The file door's sink. A run that refuses at completion has already
    written every batch, and the one thing that must not happen is that
    those bytes are found later under the name a finished result goes by.
    So nothing carries the destination's name until the end.

    **One batch at a time, never the book.** Every batch is written away
    the moment it is handed over, and nothing of it is kept once it has
    been -- not even the first batch: a batch held while the next is
    computed is two batches in memory at the run's peak, and a book far
    larger than the machine's memory is never held whole.

    **Where a batch goes depends on the order the batches come in,** which
    the engine says as it opens the sink (see :meth:`Sink.open`):

    - **In the book's order.** Every batch goes straight into the one result,
      ``<name>.<uuid>.unpublished``, through Polars' own writer, so each row
      is encoded and written once. The file's row groups are a block of the
      first batch's rows -- a block of every batch's where rows cannot
      widen, which is where an engine makes the promise. What stays in
      memory is what that writer has in flight, a few row groups of the file
      (see :class:`_Stream`).
    - **In any other order.** Every batch goes to a part file of its own in
      ``<name>.<uuid>.unpublished.d/``, and what stays in memory is where
      each row stands in the book: eight bytes a policy. At publication the
      parts are streamed into ``<name>.<uuid>.unpublished`` in the book's
      own order, a block at a time: every row written a second time, which
      is the price of an order that is only known at the end. Each part is a
      result file in its own right, manifest and all, so a run of one batch
      has its one part renamed as it stands.

    **Publication is one rename** of that finished file into place -- one
    atomic operation on the same file system, so there is no window in which
    the destination holds half a run. The uuid keeps two runs to one
    destination out of each other's working.

    **What comes back holds the schema and no rows.** The values are in the
    file, which is the whole point of writing them there: a sink whose
    purpose is to keep the book off the heap cannot then hand the book back.
    The report carries a note naming the file, so nothing about this is
    silent.
    """

    def __init__(
        self, path: Path | str, *, row_identity: Sequence[str] | None = None
    ) -> None:
        """Name the destination; nothing is created until a batch needs it.

        Args:
            path: Where the result is published.
            row_identity: The columns the caller knows name each row of the
                book once -- the command that read the book resolves them.
                An engine is handed the artifact and the book, and neither
                says which column is a policy's identity, so the manifest it
                opens with states none; the sink states these in its place,
                where the engine's manifest states none and its columns carry
                every one of them. The sink keeps the book's order, so a
                column naming each book row once names each result row once.

        """
        self._path = Path(path)
        self._row_identity = None if row_identity is None else tuple(row_identity)
        self._manifest: ResultManifest | None = None
        self._temporary: Path | None = None
        self._staging: Path | None = None
        self._placement = _Placement()
        # The first batch with no rows: the columns the file will carry.
        self._schema: pl.DataFrame | None = None
        # Each staged part, and the row-group size it was written in.
        self._parts: list[tuple[Path, int]] = []
        # The widest row seen, in bytes held in memory: what sizes a block.
        self._row_bytes = 1
        # The result being written as its batches arrive, once a batch in the
        # book's order has brought rows to write.
        self._stream: _Stream | None = None

    def open(self, manifest: ResultManifest, *, in_order: bool = False) -> None:
        """Take the manifest, and reserve this run's names beside the destination.

        A run in the book's order needs one name, the result it writes
        into. A run in any other order needs a staging directory beside it
        as well, for the parts it puts back in order at the end. A sink
        opened again before it was settled is abandoned first: whatever the
        earlier run wrote is removed rather than left beside the destination
        under a name nothing will ever publish or clear.
        """
        self.abandon()
        working = f"{self._path.name}.{uuid.uuid4().hex}.{_UNPUBLISHED}"
        carried = set(manifest.columns.values())
        if (
            manifest.row_identity is None
            and self._row_identity
            and carried.issuperset(self._row_identity)
        ):
            manifest = replace(manifest, row_identity=self._row_identity)
        self._manifest = manifest
        self._placement = _Placement(in_order=in_order)
        self._temporary = self._path.with_name(working)
        self._staging = None if in_order else self._path.with_name(f"{working}.d")

    def write_batch(
        self, frame: ArrowStreamExportable, *, rows: ArrayLike | None = None
    ) -> None:
        """Write one batch away: into the result itself, or a part of its own.

        Into the result where the run promised the book's order, and into a
        part file where it did not, keeping only where its rows stand (see
        the class's own account). Either way the sink keeps nothing of the
        batch once this returns.

        Whatever stops a batch being written -- a position that cannot be
        the book's, a full disk, an interrupt -- removes everything this run
        has written and closes the sink before it propagates: a run that
        lost a batch has nothing left worth publishing.

        Raises:
            RuntimeError: If the sink is not open.
            ValueError: As :meth:`Sink.write_batch` says.
            polars.exceptions.PolarsError: If the batch's columns are not the
                first batch's (see :func:`_same_columns`).
            BaseException: What stopped the writer of a run in the book's
                order. What its source raised comes out as it was raised --
                a key pressed as ``KeyboardInterrupt`` -- rather than inside
                the ``ComputeError`` Polars wraps round it; what Polars'
                writer met itself -- a full disk -- as Polars raised it, a
                ``polars.exceptions.ComputeError`` naming the operating
                system's error.

        """
        if self._manifest is None:
            raise RuntimeError(_NOT_OPEN)
        held = _as_frame(frame)
        try:
            if self._schema is not None:
                _same_columns(self._schema, held)
            self._placement.place(held.height, rows)
            if held.height:
                self._row_bytes = max(
                    self._row_bytes, -(-int(held.estimated_size()) // held.height)
                )
            if self._placement.in_order:
                self._write_through(held)
            else:
                self._stage(held, self._placement.positions[-1])
        except BaseException:
            self.abandon()
            raise
        if self._schema is None:
            self._schema = held.clear()

    def _write_through(self, frame: pl.DataFrame) -> None:
        """Write one batch into the result itself, where its rows will stand.

        The writer starts with the first batch that has rows, which is when
        the size of a row -- and so of a row group of the file, one block of
        rows -- is first known. A batch of no rows has nothing to add.
        """
        if not frame.height:
            return
        if self._stream is None:
            if self._manifest is None or self._temporary is None:  # pragma: no cover
                raise RuntimeError(_NOT_OPEN)
            # Held before its thread starts: a key pressed while it starts
            # then finds a stream to stop.
            self._stream = _Stream(
                frame.schema,
                self._manifest,
                self._temporary,
                rows=self._rows_in(_BLOCK_BYTES),
            )
            self._stream.start()
        self._stream.write(frame)

    def _stage(self, frame: pl.DataFrame, placed: np.ndarray) -> None:
        """Write one batch to a part file of its own, and keep only its name.

        As a result file, manifest and all, so that a run of one batch has
        nothing left to write at publication: its one part is renamed into
        place as it stands. In row groups of its share of a block (see
        :meth:`_share_of_a_block`), which for a run of one batch is a whole
        block -- the layout of every file this sink publishes.
        """
        if self._manifest is None or self._staging is None:  # pragma: no cover
            raise RuntimeError(_NOT_OPEN)
        if not self._parts:
            # This run's own name, reserved at open: nothing stands there yet,
            # and a directory that did would be another run's.
            self._staging.mkdir()
        group = self._share_of_a_block(placed)
        part = self._staging / f"{len(self._parts):08d}.parquet"
        write_with_manifest(frame, self._manifest, part, row_group_size=group)
        self._parts.append((part, group))

    def _share_of_a_block(self, placed: np.ndarray) -> int:
        """Return the rows one part's row groups hold: its share of a block.

        Publication reads a part back :data:`_READ_AHEAD` row groups at a time
        and holds each read until its last row has gone into a block. A part
        whose rows are every fourth policy of the book gives a quarter of each
        block, so its groups are a quarter of a block, and every part being
        read at once holds its own share of a few blocks: all of them
        together, a few blocks, however finely the engine's groups interleave.
        A part whose rows run in the book's order is a whole block to a group
        -- and a run of one batch, the book in its own order, is written in
        exactly the layout of a published file, because it is published as it
        stands.
        """
        block = self._rows_in(_BLOCK_BYTES)
        if placed.size < _TWO:
            return block
        span = int(placed[-1]) - int(placed[0]) + 1
        share = -(-block * int(placed.size) // span)
        return max(self._rows_in(_LEAST_PART_GROUP_BYTES), min(block, share))

    def publish(self, report: RunReport) -> EngineResult:
        """Finish the file in the book's order, rename it into place, and say where.

        Raises:
            RuntimeError: If the sink is not open.
            EngineRefusal: If no batch was ever written. An engine publishes
                at least one batch -- empty where the book is empty, carrying
                its schema either way -- so a publication with none is a run
                that finished without producing anything, and this door
                refuses it exactly as the frame door does. The alternative,
                writing a Parquet file of no columns and renaming it into
                place, leaves a *file* on disk that a later reader takes for
                a result: the one thing this sink exists to make impossible.
            ValueError: If the rows written are not the book's rows exactly
                once each. Nothing is published and nothing staged remains.
            BaseException: What stopped the file being finished: a key
                pressed as ``KeyboardInterrupt``, and a full disk as Polars
                raised it -- a ``polars.exceptions.ComputeError`` naming the
                operating system's error. Nothing is published and nothing
                written remains.

        """
        manifest, temporary = self._manifest, self._temporary
        if manifest is None or temporary is None:
            raise RuntimeError(_NOT_OPEN)
        schema = self._schema
        if schema is None:
            self.abandon()
            raise EngineRefusal(
                RunReport(
                    refusals=(
                        Refusal(
                            group="completion",
                            where=manifest.producer,
                            count=None,
                            what=(
                                f"the {manifest.producer} engine published no "
                                "batch, so there are no values to write"
                            ),
                            move=(
                                "an engine publishes at least one batch -- "
                                "empty where the book is empty, carrying its "
                                "schema either way"
                            ),
                            clause=None,
                        ),
                    ),
                    notes=report.notes,
                )
            )
        try:
            if self._placement.in_order:
                self._finish(schema, manifest, temporary)
            else:
                self._put_in_order(schema, manifest, temporary)
            # One rename, on the same file system, so there is no window in
            # which the destination holds half a run.
            temporary.replace(self._path)
        except BaseException:
            # Whatever stopped publication -- a defect, a full disk, an
            # interrupt -- nothing of this run may remain to be found later.
            self.abandon()
            raise
        # Published once. A second publication would rename a second file
        # over the first; closed, the sink refuses it instead.
        self._close()
        where = (
            f"the values are in {self._path} rather than in this result: "
            "a sink that writes to a file does not also hold the book"
        )
        noted = RunReport(refusals=report.refusals, notes=(*report.notes, where))
        return EngineResult(columns=schema, manifest=manifest, report=noted)

    def _finish(
        self, schema: pl.DataFrame, manifest: ResultManifest, temporary: Path
    ) -> None:
        """Finish the one result every batch was written straight into.

        A run that handed over no rows at all -- an empty book -- started no
        writer, and its result is its columns and no rows, written as a run
        of one empty batch always has been.

        The finished file is held to the rows handed over, as the staged
        route holds its parts to the book: its footer's count against the
        count placed. A row lost between the sink and Polars' writer would
        otherwise publish a result one piece short, and nothing in it would
        say so.

        Raises:
            RuntimeError: If the file holds more or fewer rows than were
                handed over. Nothing is published.

        """
        if self._stream is None:
            write_with_manifest(schema, manifest, temporary)
            return
        self._stream.finish()
        written = pl.scan_parquet(temporary).select(pl.len()).collect().item()
        if written != self._placement.rows:
            message = (
                f"The result holds {_counted(written, 'row', 'rows')} and "
                f"{_counted(self._placement.rows, 'row was', 'rows were')} "
                "handed over to be written: rows were lost or doubled between "
                "the sink and Polars' writer. That is a defect in the file "
                "sink, not in the model, and nothing it wrote remains."
            )
            raise RuntimeError(message)

    def _put_in_order(
        self, schema: pl.DataFrame, manifest: ResultManifest, temporary: Path
    ) -> None:
        """Write the staged parts into the temporary in the book's order; clear them.

        Raises:
            ValueError: If the rows staged are not the book's rows exactly
                once each.

        """
        staging = self._staging
        if staging is None:  # pragma: no cover -- reserved at open on this route
            raise RuntimeError(_NOT_OPEN)
        self._placement.covered()
        (first, _group), *more = self._parts
        if more:
            self._assemble(schema, manifest, temporary)
        else:
            # One batch covering the book in one ascending run of positions
            # is the book in its own order, and its part is already a result
            # file: nothing to merge and nothing to write.
            first.replace(temporary)
        # Everything staged goes before anything is published -- whatever
        # else stands in the directory, a Finder's .DS_Store say -- so the
        # rename that publishes is the last thing that happens.
        shutil.rmtree(staging)

    def _assemble(
        self, schema: pl.DataFrame, manifest: ResultManifest, temporary: Path
    ) -> None:
        """Stream the staged parts into the temporary, in the book's own order.

        Through Polars' own writer, which pulls the parts as a source a block
        at a time. None of the book is held whole. What publication holds is
        three things, each bounded however large the book, and a block is
        :data:`_BLOCK_BYTES` of rows as they sit in memory:

        - **The block being put in order**, and its gathered copy: two
          blocks.
        - **Each part's current read**, which is :data:`_READ_AHEAD` of its
          row groups, held until its last row has gone into a block. A
          part's row groups are its share of a block (see
          :meth:`_share_of_a_block`), so all the parts being read hold about
          four blocks together, however finely they interleave -- up to
          eight for the moment a block crosses from one part to the next.
        - **What Polars' writer has in flight.** It encodes row groups of the
          file on every thread at once, holding each one's rows and encoded
          pages until the group is written: up to about two blocks per
          thread, since a row group of the file is one block.

        With 64 MiB blocks on a sixteen-thread laptop that is at most about
        2.6 GiB, whatever the size of the book. Measured on one, publication
        added 0.31 GiB over a jagged level-4 book of 100,000 policies in five
        parts, 0.86 GiB over 100,000 level-4 policies in two, and 1.01 GiB
        over 32 parts interleaved row by row: the writer rarely has every
        thread's group in flight at once.

        Polars reports anything a source raises as its own ``ComputeError``.
        The source here records what it raised, and that is what comes out
        of publication -- a part that cannot be read, a key pressed as
        ``KeyboardInterrupt`` -- rather than a wrapper naming neither. What
        Polars' writer meets itself, a full disk, comes out as Polars raised
        it: a ``ComputeError`` naming the operating system's error.
        """
        parts = list(self._parts)
        positions = list(self._placement.positions)
        block = self._rows_in(_BLOCK_BYTES)
        met: list[BaseException] = []

        def read(
            with_columns: list[str] | None,
            predicate: pl.Expr | None,
            n_rows: int | None,
            _batch_size: int | None,
        ) -> Iterator[pl.DataFrame]:
            try:
                left = n_rows
                staged = [_Part(path, group) for path, group in parts]
                for whole in _in_blocks(staged, positions, block):
                    taken = (
                        whole if with_columns is None else whole.select(with_columns)
                    )
                    if predicate is not None:
                        taken = taken.filter(predicate)
                    if left is not None:
                        taken = taken.head(left)
                        left -= taken.height
                    yield taken
                    if left == 0:
                        return
            except GeneratorExit:
                raise
            except BaseException as error:
                met.append(error)
                raise

        try:
            register_io_source(
                read, schema=schema.schema, validate_schema=True
            ).sink_parquet(
                temporary,
                metadata=manifest.to_metadata(),
                row_group_size=block,
                # The bound above is the streaming engine's: a session that
                # prefers the in-memory one would put the whole book in memory.
                engine="streaming",
            )
        except Exception:
            if met:
                raise met[0] from None
            raise

    def _rows_in(self, size: int) -> int:
        """Return how many of this result's rows fit in ``size`` bytes of memory."""
        return max(1, size // self._row_bytes)

    def abandon(self) -> None:
        """Remove the temporary and everything staged, and the manifest with them.

        A result being written as its batches arrive has its writer stopped
        first, and waited for: a writer still running could otherwise go on
        writing to the file after it was removed. An abandoned sink takes no
        more batches and publishes nothing until it is opened again, so an
        engine that carried on past its own failure cannot publish whatever
        happened to be left.
        """
        stream, temporary, staging = self._stream, self._temporary, self._staging
        if stream is not None:
            # Told first, by a plain store rather than a call: a second key
            # press can interrupt a call, and a writer told this much stops by
            # itself and takes its file with it, whatever happens below.
            stream.abandoned = True
        try:
            if stream is not None:
                stream.stop()
        finally:
            self._close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if staging is not None and staging.exists():
                shutil.rmtree(staging)

    def _close(self) -> None:
        """Forget this run's names and everything it handed over; touch no file."""
        self._manifest = None
        self._temporary = None
        self._staging = None
        self._placement = _Placement()
        self._schema = None
        self._parts = []
        self._row_bytes = 1
        self._stream = None


# How much of a result one block of publication holds in memory while it is
# put back in the book's order: the staged parts are read back and written out
# a block at a time, whatever the size of the book. A block is also one row
# group of every file this sink publishes, and Polars' writer holds up to about
# two of those per thread while it encodes them -- which is what the size is
# chosen against (see ``ParquetSink._assemble``). Smaller groups hold less in
# flight and compress less well. Against a file written as one row group, a
# file of 30,000 distinct level-4 policies costs 3 per cent more disk at this
# size and 9 per cent at half of it; a file of policies tiled from a thousand,
# whose repeats one group compresses away, 28 and 72 per cent.
_BLOCK_BYTES: Final = 64 * 1024**2

# How many of its own row groups a staged part reads at once. Polars decodes
# the groups of one read side by side, so reading one at a time is five times
# slower (level 4, a 30,000-policy part, 3.7 s against 0.75 s at eight); and a
# part's groups are its share of a block, so four of them across every part
# being read come to about four blocks, however finely the parts interleave.
_READ_AHEAD: Final = 4

# The smallest row group a staged part is written in, however small its share
# of a block. A part of one policy in a hundred would otherwise be written a
# few rows to a group, and a group costs its writer and its reader the same
# bookkeeping however few rows it holds.
_LEAST_PART_GROUP_BYTES: Final = 1024**2

# What the file sink names its writer's thread, so that a thread left running
# can be told apart from every other thread of the process.
_WRITER: Final = "gaspatchio writer"

# How often, in seconds, a thread waiting on the writer or its source looks up
# as well as when it is woken: a wake-up that never came costs this, not a run.
_LOOK_UP: Final = 0.1

# How long, in seconds, a writer thread asked to start may take to say it is
# running. A key pressed inside ``Thread.start`` can land either side of the
# thread being made; made, it says so in microseconds, and one that has not
# said so in this long was never made.
_STARTING: Final = 5.0

# How long, in seconds, the writer may go without taking a row or writing a
# byte before a thread waiting on it gives up and says so. A writer at work
# does one or the other many times a second, on the slowest disk; one that has
# done neither for a minute has stopped for a reason of its own.
_PATIENCE: Final = 60.0

# What a sink says when it is used outside the life a run gives it.
_NOT_OPEN: Final = (
    "This sink was used without being opened, or after it was abandoned: "
    "open it with the run's manifest first."
)

# The two ways a batch says where its rows stand, as a refusal names them.
_BY_POSITION: Final = "with its book positions"
_IN_ORDER: Final = "as the book's next rows"

# What every refusal of an engine's positions ends with. The positions are the
# engine's own bookkeeping, not anything the model wrote, and the sink has
# already removed what it was holding by the time this is read.
_A_DEFECT: Final = (
    "That is a defect in the engine that wrote them, not in the model, and "
    "nothing it wrote remains."
)


class _Placement:
    """Where every row written so far stands in the book.

    One account for both sinks, so the two agree on what a batch's positions
    may be and on what a finished run's must be: every row of the book, each
    exactly once.
    """

    def __init__(self, *, in_order: bool = False) -> None:
        """Start with no rows placed, no form chosen, and the order promised or not.

        Under a promise of the book's order the positions themselves are not
        kept. Each batch has to start where the rows placed so far end, so
        their count is all the account needs, and a run that kept its promise
        has placed every row of the book once by the time it ends.
        """
        self.in_order = in_order
        self.form: str | None = None
        self.positions: list[np.ndarray] = []
        self.rows = 0

    def place(self, height: int, rows: ArrayLike | None) -> None:
        """Take one batch's positions, or say why they cannot be the book's.

        Raises:
            ValueError: If the positions are not whole numbers from zero, one
                per row and ascending; if this batch is handed in the other
                form from the batches before it; or if the run promised the
                book's order and this batch is not its next rows.

        """
        form = _IN_ORDER if rows is None else _BY_POSITION
        if self.form is not None and form != self.form:
            message = (
                f"A batch was handed {form} after batches handed {self.form}. "
                "A run hands every batch one way: a batch with no positions "
                "follows the batch written before it, and once batches are "
                f"placed by position there is no 'before' to follow. {_A_DEFECT}"
            )
            raise ValueError(message)
        placed = (
            np.arange(self.rows, self.rows + height, dtype=np.int64)
            if rows is None
            else _positions_of(rows, height)
        )
        if self.in_order:
            self._as_promised(placed)
        else:
            self.positions.append(placed)
        self.form = form
        self.rows += height

    def _as_promised(self, placed: np.ndarray) -> None:
        """Refuse a batch that is not the book's next rows, in a run that promised them.

        The positions ascend (see :func:`_positions_of`), so they are the
        book's next rows exactly when the first and the last are.

        Raises:
            ValueError: If the batch starts anywhere but where the rows placed
                so far end, or leaves a gap before its last row.

        """
        if not placed.size:
            return
        first, last = int(placed[0]), int(placed[-1])
        if first == self.rows and last == self.rows + placed.size - 1:
            return
        message = (
            "The run promised its batches in the book's own order, and a batch "
            f"of {_counted(int(placed.size), 'row', 'rows')} was handed at "
            f"positions {first:,} to {last:,}, where the book's next rows are "
            f"{self.rows:,} to {self.rows + placed.size - 1:,}. {_A_DEFECT}"
        )
        raise ValueError(message)

    def covered(self) -> np.ndarray:
        """Return every row's position, in the order written, once they are the book's.

        A run that promised the book's order has had every batch checked as it
        came, so its rows are ``0`` to ``N - 1`` in the order written.

        Raises:
            ValueError: If the positions are not ``0`` to ``N - 1`` once each,
                ``N`` being the rows written. The message says how many
                positions are missing, how many rows repeat one already held,
                and how many stand past the end.

        """
        if self.in_order:
            return np.arange(self.rows, dtype=np.int64)
        written = (
            np.concatenate(self.positions)
            if self.positions
            else np.zeros(0, dtype=np.int64)
        )
        if self.form != _BY_POSITION:
            return written
        inside = written[written < written.size]
        held = np.bincount(inside, minlength=written.size)
        missing = int(np.count_nonzero(held == 0))
        if not missing:
            return written
        repeated = int(np.maximum(held - 1, 0).sum())
        past = int(written.size - inside.size)
        message = (
            f"The batches written hold {written.size:,} rows, and their "
            f"positions are not the book's rows 0 to {written.size - 1:,} "
            f"once each: {_counted(missing, 'position is', 'positions are')} "
            f"missing, {_counted(repeated, 'row repeats', 'rows repeat')} a "
            f"position already held, and "
            f"{_counted(past, 'row stands', 'rows stand')} past the end. "
            f"{_A_DEFECT}"
        )
        raise ValueError(message)


def _same_columns(first: pl.DataFrame, batch: pl.DataFrame) -> None:
    """Refuse a batch whose columns are not the first batch's, in Polars' words.

    With the vertical concatenation publication performs, over no rows, so
    both sinks refuse the same batch the same way -- a ``SchemaError`` for a
    column of another type, a ``ShapeError`` for another set of names -- and
    as it is written, rather than once a whole book has been staged behind
    it.
    """
    pl.concat([first.clear(), batch.clear()], how="vertical")


def _counted(count: int, one: str, many: str) -> str:
    """Return a count and its words, singular or plural as the count needs."""
    return f"{count:,} {one if count == 1 else many}"


def _positions_of(rows: ArrayLike, height: int) -> np.ndarray:
    """Return one batch's book positions, checked against the batch itself.

    A copy: an engine that reuses its own buffer for the next batch must not
    be able to move a batch already written.

    Raises:
        ValueError: If there is not one position per row, or they are not
            whole numbers from zero, ascending.

    """
    held = np.asarray(rows)
    if held.ndim != 1 or held.shape[0] != height:
        message = (
            f"A batch of {height:,} rows was handed positions of shape "
            f"{held.shape}: a batch says where each of its rows stands, one "
            f"position per row. {_A_DEFECT}"
        )
        raise ValueError(message)
    if height and held.dtype.kind not in "iu":
        message = (
            f"A batch's positions are whole numbers, and these are {held.dtype}. "
            f"{_A_DEFECT}"
        )
        raise ValueError(message)
    placed = held.astype(np.int64)
    if height and int(placed.min()) < 0:
        message = (
            "A batch's positions count the book's rows from zero, and these "
            f"reach below it. {_A_DEFECT}"
        )
        raise ValueError(message)
    if height > 1 and not bool(np.all(placed[1:] > placed[:-1])):
        message = (
            "A batch's positions ascend -- a batch is a run of the book's rows "
            "in the book's own order, however the batches themselves arrive -- "
            f"and these do not. {_A_DEFECT}"
        )
        raise ValueError(message)
    return placed


def _in_the_books_order(frame: pl.DataFrame, written: np.ndarray) -> pl.DataFrame:
    """Return one frame's rows back where their policies stood.

    ``written`` is each row's book position, and covers the frame's own row
    numbers once each. One gather -- and none at all where the rows already
    stand in the book's order, as they do for a book whose policies share one
    timeline and were computed in batches that follow it.
    """
    if written.size < _TWO or bool(np.all(written[1:] > written[:-1])):
        return frame
    back = np.empty(written.size, dtype=np.int64)
    back[written] = np.arange(written.size, dtype=np.int64)
    return frame[back]


# The fewest rows that can be out of order.
_TWO: Final = 2


class _Part:
    """One staged batch, read back front to back once, a few row groups at a time.

    Polars decodes the row groups of one read side by side, so a part reads
    :data:`_READ_AHEAD` of its groups at a time -- one at a time is five
    times slower -- and holds that read until its last row has been taken,
    then lets go of it. A part being read holds one read however many blocks
    it takes to use it up, and a part used up holds nothing.
    """

    def __init__(self, path: Path, group: int) -> None:
        """Name the part and the rows each of its row groups was written with."""
        self._path = path
        self._group = group
        self._read = 0
        self._held: pl.DataFrame | None = None
        self._at = 0

    def take(self, count: int) -> pl.DataFrame:
        """Return this part's next ``count`` rows.

        Read in whole row groups, aligned to the groups the part was written
        in, so each group is decoded once however the blocks of publication
        fall across it.

        Raises:
            RuntimeError: If the part ends before its rows do: something
                removed or changed it while the run was writing.

        """
        pieces: list[pl.DataFrame] = []
        while count:
            held = self._held if self._held is not None else self._next_read()
            piece = held.slice(self._at, count)
            self._at += piece.height
            count -= piece.height
            pieces.append(piece)
            self._held = None if self._at == held.height else held
        return pieces[0] if len(pieces) == 1 else pl.concat(pieces, how="vertical")

    def _next_read(self) -> pl.DataFrame:
        """Read this part's next few row groups, and start handing them out."""
        read = (
            pl.scan_parquet(self._path)
            .slice(self._read, self._group * _READ_AHEAD)
            .collect()
        )
        if not read.height:
            message = (
                f"The staged part {self._path} ended after {self._read:,} rows, "
                "and more were written to it: something removed or changed it "
                "while the run was writing."
            )
            raise RuntimeError(message)
        self._read += read.height
        self._at = 0
        return read


def _in_blocks(
    parts: Sequence[_Part], positions: Sequence[np.ndarray], block: int
) -> Iterator[pl.DataFrame]:
    """Yield every staged row in the book's order, one block of positions at a time.

    Each part's positions ascend, so the rows of one block are a contiguous
    run of every part that holds any of them, found by bisection. They are
    put in the book's order with one gather, and the block is handed on
    before the next one is read: what is held is one block, what each part
    being read has read ahead of it, and the positions.
    """
    total = sum(int(one.size) for one in positions)
    for low in range(0, total, block):
        high = min(low + block, total)
        pieces: list[pl.DataFrame] = []
        placed: list[np.ndarray] = []
        for part, rows in zip(parts, positions, strict=True):
            start, stop = (int(at) for at in np.searchsorted(rows, (low, high)))
            if start < stop:
                pieces.append(part.take(stop - start))
                placed.append(rows[start:stop])
        yield _in_the_books_order(
            pl.concat(pieces, how="vertical"), np.concatenate(placed) - low
        )


class _AbandonedError(Exception):
    """The run gave its result up, and the writer takes no more rows."""


class _Stream:
    """One result, written by Polars' own writer as its batches arrive.

    Polars writes one Parquet file from a source it pulls -- ``sink_parquet``
    over ``register_io_source`` -- which keeps the result file's format: the Polars
    writer, with the manifest in the file's footer. The writer therefore runs
    on a thread of its own, pulling pieces of the batch being written, and
    the engine's loop stays on the thread it runs on. Driving the loop from
    inside the source instead would move the whole run onto a thread of
    Polars' own pool, which is where Polars calls a source, and off the
    thread a key press interrupts.

    **One handoff.** :meth:`write` hands a batch over and waits until every
    row of it has been copied into a piece and taken by the writer, or until
    the writer has stopped. The source cuts one piece each time Polars asks
    for one, and Polars asks only when its pipeline has room, so a batch is
    taken as fast as the file is written. Once :meth:`write` returns nothing
    here refers to the batch: it goes as soon as the engine lets go of it,
    before the next batch is built.

    **What it holds.** A piece is one row group of the file, ``rows`` rows:
    a block of the first batch's rows, which is a block of every batch's
    wherever rows cannot widen -- and an engine promises the book's order
    only there (see :meth:`Sink.open`). Polars' writer holds up to its
    thread count plus four row groups being encoded or written, each beside
    its encoded pages, and a few pieces in the channels in front of them:
    about two row groups per thread, whatever the size of the book.

    **Why it cannot deadlock.** The two Python threads meet on one condition
    and nowhere else. The engine's thread waits for "the batch is taken, or
    the writer stopped", and the source for "a batch to cut, the end, or the
    stop". Each lets the condition go while it waits -- and the interpreter's
    lock with it, so the other can run -- and holds it only to read or set
    the fields below: never while a piece is cut, and never while Polars
    works. The writer's own thread waits inside Polars holding neither.
    Polars' pipeline needs nothing from any of them between one piece and
    the next -- it encodes and writes what it has, then asks for more -- so
    a batch handed over is taken in time, or the writer fails and wakes the
    engine's thread as it ends. A source waiting for a batch is woken by the
    next :meth:`write`, by :meth:`finish` or by :meth:`stop`, and the sink
    always calls one of the last two: publication finishes a result and
    abandoning stops it. Both wait for the writer to end, so nothing writes
    to the file once the sink has settled its fate.

    **Every wait ends, and a key pressed at either end of the writer's life
    stops it.** The sink holds the stream before its thread is started, so a
    key pressed while it starts finds a stream to stop. The sink tells the
    writer the run is abandoned with a plain store (:attr:`abandoned`), not
    a call, so a second key press cannot come between the two. Every wait
    looks up every tenth of a second as well as when woken -- the source for
    that store, the engine's thread for a writer that has ended -- so a
    wake-up that never came costs a tenth of a second rather than the run.
    The waits on the writer give up, and say so, once it has gone
    :data:`_PATIENCE` seconds without taking a row or writing a byte. And a
    writer given up removes its own file as it ends, so a result Polars
    opened after the sink removed its name does not outlive the run.
    """

    def __init__(
        self, schema: pl.Schema, manifest: ResultManifest, path: Path, *, rows: int
    ) -> None:
        """Take what the writer will write; nothing starts until :meth:`start`.

        ``rows`` is how many rows a row group of the file holds, and so how
        many a piece does.
        """
        self._schema = schema
        self._manifest = manifest
        self._path = path
        self._rows = rows
        self._changed = threading.Condition()
        # The batch being taken, how many of its rows are cut so far, and how
        # many rows of every batch.
        self._batch: pl.DataFrame | None = None
        self._taken = 0
        self._taken_in_all = 0
        # No batch follows; the thread was asked to start; it has returned.
        self._closing = False
        self._launched = False
        self._returned = False
        # The run gave the result up. Set by a plain store and read without
        # the condition as well as with it (see the class's own account).
        self.abandoned = False
        # What stopped the writer, as it was raised rather than as Polars
        # reports it; and what the source itself raised on Polars' thread.
        self._failure: BaseException | None = None
        self._met: list[BaseException] = []
        self._writer = threading.Thread(
            target=self._write,
            name=f"{_WRITER} for {path.name}",
            daemon=True,
        )

    def start(self) -> None:
        """Reserve the result's own name, and start Polars' writer on it."""
        # This run's own name, reserved at open: nothing stands there yet,
        # and a file that did would be another run's.
        self._path.touch(exist_ok=False)
        self._launched = True
        self._writer.start()

    def write(self, batch: pl.DataFrame) -> None:
        """Hand one batch to the writer, and wait until every row of it is taken.

        Raises:
            BaseException: What stopped the writer, where it stopped before
                taking the whole batch -- this one, or one before it whose
                last rows it failed to write.
            RuntimeError: If the writer has gone :data:`_PATIENCE` seconds
                without taking a row or writing a byte.

        """
        with self._changed:
            self._batch, self._taken = batch, 0
            self._changed.notify_all()
            stalled = self._patience("take the batch it was handed")
            # On the engine's own thread, so a key pressed while the batch is
            # taken interrupts this wait and the run is abandoned there.
            while not self._changed.wait_for(
                lambda: self._batch is None or self._returned, timeout=_LOOK_UP
            ):
                if not self._writer.is_alive():
                    break
                stalled()
            if self._batch is not None:
                # The writer stopped before it had taken the whole batch.
                self._batch = None
                raise self._what_stopped_it()

    def finish(self) -> None:
        """Say no batch follows, and wait for the file to be written.

        Raises:
            BaseException: What stopped the writer, if anything did.
            RuntimeError: If the writer has gone :data:`_PATIENCE` seconds
                without writing a byte, and has not ended.

        """
        with self._changed:
            self._closing = True
            self._changed.notify_all()
        self._joined("finish the file")
        if self._failure is not None:
            raise self._failure

    def stop(self) -> None:
        """Give the file up, and wait for the writer to give it up too.

        Whatever the writer met is not raised: the run is being abandoned for
        a reason of its own, and that reason is the one that propagates.

        Raises:
            RuntimeError: If the writer has gone :data:`_PATIENCE` seconds
                without ending.

        """
        self.abandoned = True
        with self._changed:
            self._batch = None
            self._changed.notify_all()
        self._joined("give the file up")

    def _joined(self, doing: str) -> None:
        """Wait for the writer's thread to end, if it was ever started.

        A key pressed inside ``Thread.start`` can land after the thread was
        made and before it has said it is running: it says so a moment later,
        and is waited for. If the key landed before the thread was made, it
        never will be, and there is nothing to wait for.

        Raises:
            RuntimeError: If the writer has gone :data:`_PATIENCE` seconds
                without taking a row or writing a byte, and has not ended.

        """
        if not self._launched:
            return
        began = time.monotonic()
        while not (self._writer.is_alive() or self._returned):
            if time.monotonic() - began >= _STARTING:
                return
            time.sleep(_STARTING / 1000)
        stalled = self._patience(doing)
        while True:
            self._writer.join(_LOOK_UP)
            if not self._writer.is_alive():
                return
            stalled()

    def _patience(self, doing: str) -> Callable[[], None]:
        """Return the check a wait makes each time it looks up, for a stalled writer.

        A writer at work takes rows or writes bytes many times a second; one
        that has done neither for :data:`_PATIENCE` seconds has stopped for a
        reason of its own, and a run waiting on it would wait for ever.
        """
        seen = self._progress()
        since = time.monotonic()

        def stalled() -> None:
            nonlocal seen, since
            now = self._progress()
            if now != seen:
                seen, since = now, time.monotonic()
                return
            if time.monotonic() - since >= _PATIENCE:
                message = (
                    f"Polars' writer for {self._path.name} has taken no row and "
                    f"written no byte for {_PATIENCE:.0f} s while the sink "
                    f"waited for it to {doing}, and has not ended: it has "
                    "stopped for a reason of its own. Nothing it wrote is "
                    "published."
                )
                raise RuntimeError(message)

        return stalled

    def _progress(self) -> tuple[int, int]:
        """Return what the writer has done so far: rows taken, and bytes on disk."""
        try:
            written = self._path.stat().st_size
        except OSError:
            written = -1
        return self._taken_in_all, written

    def _what_stopped_it(self) -> BaseException:
        """Return what stopped the writer before the run handed over its last batch."""
        if self._failure is None:  # pragma: no cover -- it ends early only by failing
            message = "Polars' writer ended before the run handed over its last batch."
            return RuntimeError(message)
        return self._failure

    def _write(self) -> None:
        """Run Polars' writer over the pieces, on the writer's own thread.

        Polars reports anything a source raises as its own ``ComputeError``.
        What the source raised is kept, and that is what the engine's thread
        raises -- a key pressed as ``KeyboardInterrupt`` -- rather than a
        wrapper naming neither. Only an error Polars' writer meets itself, a
        full disk say, comes out as Polars raised it.

        A writer given up before it began does not begin; one given up at any
        point removes its own file as it ends. Polars opens the file when it
        begins, so a writer that began after the sink removed the name would
        otherwise leave a fresh file behind it.
        """
        try:
            if not self.abandoned:
                register_io_source(
                    self._pieces, schema=self._schema, validate_schema=True
                ).sink_parquet(
                    self._path,
                    metadata=self._manifest.to_metadata(),
                    row_group_size=self._rows,
                    engine="streaming",
                )
        except BaseException as error:  # noqa: BLE001 -- carried to the engine's thread, which raises it
            with self._changed:
                self._failure = self._met[0] if self._met else error
        finally:
            if self.abandoned:
                with contextlib.suppress(OSError):
                    self._path.unlink(missing_ok=True)
            with self._changed:
                self._returned = True
                self._changed.notify_all()

    def _pieces(
        self,
        _with_columns: list[str] | None,
        _predicate: pl.Expr | None,
        _n_rows: int | None,
        _batch_size: int | None,
    ) -> Iterator[pl.DataFrame]:
        """Yield the result's rows a piece at a time, as Polars asks for them.

        On Polars' own thread. Its own sink asks for every column of every
        row, so no projection, predicate or row limit is ever passed. What
        this raises is kept for the engine's thread before Polars wraps it.
        """
        try:
            while (piece := self._next_piece()) is not None:
                yield piece
                # Not held while waiting for the next: Polars has it now.
                del piece
        except GeneratorExit:
            raise
        except BaseException as error:
            self._met.append(error)
            raise

    def _next_piece(self) -> pl.DataFrame | None:
        """Return the next piece of the batch being written, or None at the end.

        Waits for a batch where none is being taken, looking up every tenth
        of a second as well as when woken, so a stop the writer was never
        woken for is still seen. The piece is cut outside the condition, so
        the engine's thread is never kept from it by a copy.

        Raises:
            _AbandonedError: If the run was abandoned.

        """
        with self._changed:
            while not self._changed.wait_for(
                lambda: self._batch is not None or self._closing or self.abandoned,
                timeout=_LOOK_UP,
            ):
                pass
            if self.abandoned:
                raise _AbandonedError
            batch, at = self._batch, self._taken
            if batch is None:
                return None
        piece = _piece_of(batch, at, self._rows)
        with self._changed:
            if self._batch is batch:
                self._taken = at + piece.height
                self._taken_in_all += piece.height
                if self._taken == batch.height:
                    self._batch = None
                    self._changed.notify_all()
        return piece


def _piece_of(batch: pl.DataFrame, at: int, rows: int) -> pl.DataFrame:
    """Return up to ``rows`` of a batch's rows from ``at``, in memory of their own.

    A copy, not a slice, for two reasons measured on level 4. A slice shares
    its batch's buffers, so one piece still in Polars' writer keeps the whole
    batch in memory while the engine builds the next: two batches at the
    run's peak, the peak streaming exists to remove (writing three 2.6 GiB
    batches, 6.6 GiB against 4.1 GiB). And Polars' writer pages a sliced list
    column by its batch's cells rather than the slice's -- a per-period
    column of one 1,425-row group of a 20,000-policy batch in 13 pages, where
    a copy of the same rows makes one -- and zstd compresses the small pages
    so much less well that the file came out half as large again, 345
    against 227 MiB. The copy is one pass over the batch, on the writer's
    thread while Polars encodes the pieces before it.
    """
    return batch[np.arange(at, min(at + rows, batch.height), dtype=np.int64)]


def _as_frame(batch: ArrowStreamExportable) -> pl.DataFrame:
    """Read one batch as a Polars frame, borrowing rather than copying."""
    if isinstance(batch, pl.DataFrame):
        return batch
    return pl.DataFrame(batch)


def write_with_manifest(
    frame: pl.DataFrame,
    manifest: ResultManifest,
    path: Path,
    *,
    row_group_size: int | None = None,
) -> None:
    """Write one frame to Parquet with the manifest in its own metadata.

    The manifest is the half that makes the file a result rather than a
    table of numbers: a reader has to be able to say which graph, which book
    and which scope these columns are of without being told. It goes in the
    Parquet footer's key-value metadata, the one place every Parquet reader
    and writer has in common, so the file carries it whichever library reads
    it next -- :func:`read_manifest` looks nowhere else.

    ``row_group_size`` is how many rows each row group holds, where the
    writer's own choice will not do: a staged part is read back a slice at a
    time, and a row group is the least of a file a reader can decode.
    """
    frame.write_parquet(
        path, metadata=manifest.to_metadata(), row_group_size=row_group_size
    )


def read_manifest(path: Path) -> ResultManifest:
    """Return the manifest a result file carries, or say why it carries none.

    Read from the footer's key-value metadata, where any Parquet writer puts
    it -- Polars, pyarrow, DuckDB, arrow-rs -- so a result written by an
    engine in another language is read exactly as one written here.
    """
    return ResultManifest.from_metadata(pl.read_parquet_metadata(path))


def digest_of_inputs(frame: pl.DataFrame, columns: Iterable[str]) -> str:
    """Return the digest of the book these results were produced over.

    The specification's own content grammar (``spec/graph-artifact/
    v0-preview.md`` section 12.3) over the named columns in name order, rows
    as the book holds them -- the grammar every assumption table's stamp is
    taken under, so a consumer holding the book and nothing else reaches the
    same digest with no library in common with the producer. Name
    order rather than the frame's own, so two runs whose books differ only
    in column order digest alike. The grammar tags each column with its
    neutral type, so an i64 column of ones and an f64 column of ones are not
    the same bytes, while an Int32 and an Int64 holding the same numbers
    are.

    Not a hash of any writer's file: a Parquet encoding moves when its
    writer changes a default, and two runs of one book a library upgrade
    apart would then report different inputs with no data behind the
    difference.

    **A column held as categories is read as the text it holds.** A
    ``Categorical`` or an ``Enum`` is a string with a dictionary in front of
    it, and the dictionary is how an engine kept the column -- storage, as a
    width is -- so the book one pipeline extracts as categories and another
    as text is one book, and digests alike, at any depth of list. This is
    the one reading that meets such a column without naming its type: the
    book's values never travel, only its digest does, so no type is claimed
    for them.

    A column the frame does not hold is left out. The digest says what was
    read, not what was wanted, and what was wanted is refused elsewhere with
    the column named.
    """
    held = set(frame.columns)
    wanted = sorted(name for name in columns if name in held)
    selected = frame.select(wanted)
    as_text = [
        column.cast(read)
        for column in selected.get_columns()
        if (read := _read_as_text(column.dtype)) != column.dtype
    ]
    return content_sha_of(selected.with_columns(as_text) if as_text else selected)


def _read_as_text(dtype: pl.DataType) -> pl.DataType:
    """Return ``dtype`` with every category in it read as the text it stands for.

    A ``Categorical`` or an ``Enum`` becomes ``String``, and a list or a
    fixed-width array of them a list or array of ``String``, so the grammar
    reads the values the dictionary stood in front of. Any other type is
    returned as it is, for the grammar to name or refuse.
    """
    if isinstance(dtype, (pl.Categorical, pl.Enum)):
        return pl.String()
    inner = getattr(dtype, "inner", None)
    if isinstance(dtype, pl.List) and isinstance(inner, pl.DataType):
        return pl.List(_read_as_text(inner))
    if isinstance(dtype, pl.Array) and isinstance(inner, pl.DataType):
        return pl.Array(_read_as_text(inner), dtype.size)
    return dtype
