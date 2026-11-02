# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One execution plan, six stages, and the same plan behind both doors.

The stages are these six, in the order a finding becomes knowable in:

1. **Inspection.** The document through the validator the producer uses and
   through ``inspect_execution``; the nodes this run needs; and, per node, what
   this engine can do with it. Nothing has been read from the book yet, so a
   refusal here costs a reader nothing but the sentence.
2. **Input and payload validation.** The arriving columns against the
   artifact's input nodes -- name, type, shape -- and every check whose
   operands already exist. The null rule lives here: a null in a column
   something reads as a value refuses, with its row count, because this
   engine cannot hold one.
3. **Shape and host preparation.** The interning dictionary; the host
   operations whose operands arrived rather than were computed; the
   ancestry of every column a per-period array's width is read from; how many
   cells each axis-sizing operation lays down per policy; and the key
   questions the book alone settles, so a read whose keys all arrived is
   answered before anything is compiled.
4. **The numerical regions, batch by batch.** The policies are grouped by
   the widths their axes take, each group is cut into batches under the
   temporaries budget, and each (width, batch) shape is one compiled program
   the batches of that group share. Every check that needed a computed operand
   is carried through as a bounded flag, and what comes back of it is what a
   finding reports -- how many cells it caught and the first of them, counted
   on the card; a coarse check's cells come back only where it caught
   one, for the host's exact judgement. On a
   card the host settles and dispatches the next batch before it reads this
   one back, so the card is never waiting on the host's settling;
   on the CPU, which is the host's own cores, each batch runs after the one
   before it. Each batch's
   columns go to the sink the moment the batch is read back, with the book
   positions of its rows, and its values are dropped before any batch after
   the one on the card is dispatched.
5. **Further host boundaries.** Where host stages that make text from a
   calculation would stand; this engine refuses that for now, and nothing
   stands here today.
6. **Completion.** Every batch's flags read together, the coarse ones judged
   exactly, and -- only if nothing refused -- the result the sink has been
   holding published, in the book's own order.

**Publication is the last thing that happens and the only thing that is
visible.** Every batch is written away as it finishes, into a result nobody
can see until the sink publishes it. A run that refuses at completion has done
all the work and published none of it, which is a different fact from a run
that never started; the report's closing sentence is where the two are told
apart.

**A width is not an argument.** Everything a compiled program is built around
-- how wide a rectangle is, whether two per-period operands are the same
timeline -- is settled on the host before the program exists, and everything
else goes in as an argument. That division is why a second batch of one group
is the same executable over different numbers, and it is why the operations
that read the width of their own answer are lowered in stage 3 rather than
inside the program that reads them.

**The fold's cost is the frame door's, not this module's.** ``collect(engine=)``
folds the executable document before anything here runs, and what that costs
is measured on the door's own path in ``tests/test_doors.py``.
"""

from __future__ import annotations

import datetime
import platform
import traceback
from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import partial
from typing import TYPE_CHECKING, Any, Final

import jax
import jax.numpy as jnp
import numpy as np
import polars as pl
import pyarrow as pa

from gaspatchio.engines.format import (
    SHA256_PREFIX,
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    SelectionRefusedError,
    State,
    WhenThen,
    apply_selection,
    inspect_execution,
    join_key_sides,
    op_node_from_json,
)
from gaspatchio.engines.protocol import (
    VALUE_BEARING,
    EngineResult,
    NodeStatus,
    ResultManifest,
    digest_of_inputs,
)
from gaspatchio.engines.report import EngineRefusal, Refusal, RunReport

from .batching import (
    BATCH_GRID,
    BUDGET_BYTES,
    batch_size,
    bytes_per_policy,
    chunks,
    grouped,
    in_the_books_order,
    one_timeline,
)
from .cache import CacheOutcome, report_key, unusable, watching
from .capability import NodeRecord
from .checks import (
    FlagBook,
    Flagged,
    about,
    flag,
    recording,
    tallied,
    to_the_horizon,
)
from .domains import check_inputs
from .horizon import BUCKETS, Horizon, bucket_of, periods_of, trim
from .interning import Dictionary
from .lowerings import LOWERINGS, SIZINGS, STEPS, load, refused_by_name
from .lowerings.rollforward import (
    FACET,
    MACHINE,
    MACHINE_DOORS,
    ROLLFORWARD_KIND,
    STATE_KIND,
    body_of,
    declares,
    fingerprint_of,
    inspect_machine,
    machine_tree,
    outside_the_subset,
    outside_the_types,
)
from .lowerings.tables import KEYED_READS, inspect_payload, keys_all_arrived
from .preflight import (
    Finding,
    document_refusals,
    domain_refusal,
    findings_of,
    findings_tallied,
    input_mismatch,
    input_missing,
    merged_findings,
    read_as_i64,
)
from .typed import (
    INT64_MAX,
    INT64_MIN,
    JNP_OF,
    PAST_I64_LITERAL_MOVE,
    DomainRefused,
    Shape,
    Value,
    arithmetic_carrier,
    carried_to,
    cell_of,
    written_exponent,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator, Sequence

    from gaspatchio.engines.format import (
        ExecutionInspection,
        LitScalar,
        LitSequenceMember,
        OpNode,
    )
    from gaspatchio.engines.protocol import Sink

    from .checks import Carried
    from .lowerings import Steps
    from .tables import Storage
    from .typed import Carrier

__all__ = [
    "Batched",
    "Computed",
    "Dispatched",
    "ExecutionPlan",
    "LoweringContext",
    "Prepared",
    "PreparedInputs",
    "Program",
    "Settled",
    "Streamed",
    "checked_depth",
    "depth_on",
]

# A date is held as a count of days from this epoch, in int64.
_EPOCH = datetime.date(1970, 1, 1)

# What a refusal says when a node's own record and its own tree disagree about
# the type of the answer. Named because it is the one refusal that is about the
# *document* rather than about the model -- a producer wrote a record its own
# formula does not produce -- and a test sweeping the operand domains has to be
# able to tell it apart from a domain refusal without matching on prose.
RECORD_DISAGREES = "is recorded as"

# What the manifest says produced a result.
ENGINE_NAME = "jax"


def depth_on(backend: str) -> int:
    """Return how many batches to hand to their programs ahead of the one read back.

    **One on a card.** A card runs a program by itself once it has
    its batch, so the host settles and dispatches the next batch while the
    card computes this one, and reading a batch back waits for that batch's
    program alone.

    **Nought on the CPU.** There the device is the host's own cores. XLA runs
    a CPU program's work in order and stops taking new work at about
    thirty-two computations in flight, so a settlement dispatched behind a
    running program waits for it to end; and a batch written while the next
    one computes builds and compresses its columns on the very cores the
    program is using. On the Intel laptop on 2026-09-24, 140,000 level-4
    policies every node through the file sink took 61 and 62 s one batch at a
    time against 79 and 86 s one ahead, peaking 0.8 GiB higher. So the CPU
    runs each batch after the one before it, as it always did.

    Neither is a knob on either door: the bench passes a depth to measure
    what the overlap is worth, and nothing else does.
    """
    return 0 if backend == "cpu" else 1


def checked_depth(depth: int | None) -> int:
    """Return the depth a run takes: the one a caller named, or the device's own.

    **Nought or one, and nothing else.** One batch ahead is the whole of the
    overlap: while the card computes one batch the host has one batch to
    settle, so a second batch in flight hides no more of the host's work. It
    would keep three batches alive at once rather than two -- three batches'
    answers on the card, where the batch budget counts one program's
    temporaries and none of any batch's answers -- and the stream's and the
    fold's promise that at most two are alive would not hold.

    Raises:
        ValueError: If ``depth`` is named and is neither 0 nor 1.

    """
    if depth is None:
        return depth_on(jax.default_backend())
    if depth not in (0, 1):
        message = (
            "depth is 0, each batch after the one before it, or 1, one batch "
            f"ahead; got {depth}"
        )
        raise ValueError(message)
    return depth


@dataclass(frozen=True, slots=True)
class PreparedInputs:
    """The book, checked against the artifact's input nodes and carried in.

    Attributes:
        frame: The arriving columns of the policies the run values -- the
            book as handed in, through the document's recorded selection
            (section 7.6) -- kept for the host stage.
        columns: Column name to the value the trace sees.
        rows: How many policies. One number, because every column of a book
            is as long as the book.
        dictionary: The interning table the text columns were carried through,
            which the host stage and the publication both read.
        handed: The book as it was handed in -- its narrow integers read as
            ``i64``, which moves no digest -- before the selection, where
            the document records one: the result manifest digests the book
            the engine was handed, so a document and its result are matched
            by content. None where nothing was selected and ``frame`` is it.

    """

    frame: pl.DataFrame
    columns: dict[str, Value]
    rows: int
    dictionary: Dictionary
    handed: pl.DataFrame | None = None


@dataclass(frozen=True, slots=True)
class Prepared:
    """What the host settled before the trace began.

    Attributes:
        inputs: The book, checked and carried in.
        dictionary: The interning table the text columns went through.
        host: The operations that produce text, done here off the trace.
        flags: What the host stage's own checks caught. A check is a check
            wherever it was raised: ``str.to_date`` parses on the host and
            still owes 11.1.7's strictness, and a flag raised there has to
            reach completion with the trace's own.
        axis: The pre-axis subgraph's values -- the ancestry of the column a
            projection's horizon is named by, settled before the main pass so
            that every per-period array has a length before the first one is
            built.
        widths: Per axis-sizing operation, how many cells it lays down for
            each policy. Read before any array is allocated, and what the
            policies are grouped by: two policies whose axes round up to the
            same widths are two rows of one rectangle and one program.

    """

    inputs: PreparedInputs
    dictionary: Dictionary
    host: dict[str, Value]
    flags: FlagBook = field(default_factory=FlagBook)
    axis: dict[str, Value] = field(default_factory=dict)
    widths: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Computed:
    """What the numerical regions produced, and what they flagged doing it."""

    values: dict[str, Value]
    rows: int
    dictionary: Dictionary
    flags: FlagBook


@dataclass(frozen=True, slots=True)
class Settled:
    """One batch of policies, and every value its program is handed.

    Attributes:
        rows: The book rows this batch holds, in the book's own order.
        values: Node id to the value, on the host: the columns that arrived,
            the host settlement, the pre-axis subgraph and the operations
            that read the width of their own answer.
        dictionary: The run's interning table.
        flags: What the axis-sizing operations flagged, which reaches
            completion with the program's own.

    """

    rows: np.ndarray
    values: dict[str, Value]
    dictionary: Dictionary
    flags: FlagBook

    @property
    def count(self) -> int:
        """Return how many policies this batch holds."""
        return int(self.rows.size)


@dataclass(frozen=True, slots=True)
class Program:
    """One compiled region pass, and what each of its outputs means.

    Attributes:
        compiled: The executable, one per (bucket, batch).
        names: The order the value arrays go in.
        axes: How many per-period axes' period counts go in beside them.
        columns: Node id to the column name the result carries it under.
        shapes: Per published node, the carrier, the shape, the declared type
            and which returned axis its periods stand on.
        buckets: The width of each returned axis.
        sources: Per returned axis, which of the axes the batch was handed in
            on it is -- so its period counts are the batch's own, already on
            the host -- or None for an axis the program laid itself, whose
            counts are read back with the rest of its answers.
        longest: The returned axes the final schema's per-period doubles
            stand on, whether or not those columns are returned: the longest
            timeline among them is what ``run_aggregated`` reports as its
            period count.
        flags: Per check the trace carried, in the order it raised them: its
            name, what it is about, the shape of its mask, the exact judgement
            a coarse one defers, and the sentence a noted one reports instead
            of refusing -- what the program's counts mean.

    """

    compiled: Any
    names: tuple[str, ...]
    axes: int
    columns: dict[str, str]
    shapes: dict[str, tuple[str, str, str, int | None]]
    buckets: tuple[int, ...]
    sources: tuple[int | None, ...]
    longest: tuple[int, ...]
    flags: tuple[Carried, ...]


@dataclass(frozen=True, slots=True)
class Dispatched:
    """One batch handed to its compiled program, and not yet read back.

    What a program returns is arrays the device is still computing, and this
    holds them unread: the host is free to settle the next batch while the
    card works on this one. Nothing of the batch's own inputs is kept -- the
    runtime holds a program's arguments for as long as it runs -- only what
    reading the answers back needs.

    Attributes:
        rows: The book positions this batch holds, ascending.
        program: The program it was handed to, and what its outputs mean.
        columns: Node id to the array the program is computing for it.
        counts: Each returned axis's period counts, on the device.
        tallies: Every check's count of caught cells and its first caught
            cell, in one array on the device.
        coarse_masks: Each coarse check's mask, on the device, and nothing
            else's: read back only where the card counted a caught cell for
            that check.
        coarse_operands: What each coarse check's exact judgement reads,
            read back with its mask.
        lengths: The period counts of each axis the batch was handed in on,
            on the host -- where a returned axis's own counts are read from.
        flags: What settling the batch flagged, read with the program's own.
        dictionary: The run's interning table.

    """

    rows: np.ndarray
    program: Program
    columns: dict[str, jax.Array]
    counts: tuple[jax.Array, ...]
    tallies: jax.Array
    coarse_masks: tuple[jax.Array, ...]
    coarse_operands: tuple[tuple[jax.Array, ...], ...]
    lengths: tuple[np.ndarray, ...]
    flags: FlagBook
    dictionary: Dictionary

    def per_period(self, node_id: str) -> tuple[jax.Array, jax.Array]:
        """Return one per-period answer and each policy's period count, unread.

        What a reader queues beside the program reads: both are still being
        computed, and work queued on them waits for this program and no
        other.

        Raises:
            AssertionError: If the answer holds one value per policy.

        """
        at = self.program.shapes[node_id][3]
        if at is None:  # pragma: no cover -- a defect, not a refusal
            message = f"{node_id} holds one value per policy, not one per period"
            raise AssertionError(message)
        return self.columns[node_id], self.counts[at]


@dataclass(frozen=True, slots=True)
class Batched:
    """What one batch produced: its rows, its values, and what it flagged.

    Handed on the moment its program has run, and let go of as soon as it has
    been read. The stream builds its columns, writes them to the sink with the
    book positions of its rows, and drops its values before the next batch is
    computed -- so a book is never held whole, on the device or in memory. What
    outlives a batch is its findings, which are small and which completion
    reads with every other batch's.

    The values and not a frame, because building columns is the reader's
    business: the stream builds them, and a fold would reduce the values
    without building any. And a fault met building them is not raised where it
    happens -- a later batch may yet refuse, and a refusal is the run's real
    answer (see :meth:`ExecutionPlan.stage_stream`).

    Attributes:
        rows: The book positions this batch holds, ascending: a run of one
            group's policies, in the book's own order.
        values: Node id to the value the program returned for it, taken out
            one at a time as the stream builds the batch's columns.
        dictionary: The run's interning table, which text is read back
            through.
        columns: Node id to the column the result carries it under.
        findings: What its checks caught, each position named in the book
            rather than in the batch.
        longest: The most periods any per-period double of the final schema
            holds for a policy of this batch -- counted off the batch's own
            timelines, whether or not its program returned those columns.
        queued: Whatever the reader queued on the device beside this batch's
            program the moment it was dispatched, handed back with it; None
            where nothing was (see :meth:`ExecutionPlan.stage_batches`).

    """

    rows: np.ndarray
    values: dict[str, Value]
    dictionary: Dictionary
    columns: dict[str, str]
    findings: tuple[Finding, ...]
    longest: int
    queued: object


@dataclass(frozen=True, slots=True)
class Streamed:
    """What running every batch leaves for completion to read.

    Attributes:
        findings: Every batch's findings, in the order the batches ran.
        fault: The first fault met building or writing a batch's columns,
            held so that a refusal can still be the run's answer. None where
            every batch that was to be written was written.

    """

    findings: tuple[Finding, ...]
    fault: Exception | None = None


class _ValueNeeded(Exception):  # noqa: N818 -- a signal, never a refusal
    """A check read from the record alone reached a value it does not have."""


class _NoValueYet(Mapping[str, "Value"]):
    """The values of an inspection, which has read no book: every one is to come.

    Asked whether it holds a value, or for one, it stops the check that asked
    (:class:`_ValueNeeded`), so a check that needs the book is left to the run
    rather than refused for a column it was never handed.
    """

    def __contains__(self, key: object) -> bool:
        raise _ValueNeeded(key)

    def __getitem__(self, key: str) -> Value:
        raise _ValueNeeded(key)

    def __iter__(self) -> Iterator[str]:
        raise _ValueNeeded(None)

    def __len__(self) -> int:
        raise _ValueNeeded(None)


class LoweringContext:
    """What a lowering can ask about the node it is inside.

    A lowering never reaches the plan directly. It asks for an operand's
    value, for the record of the node it stands in, or for the type the
    operation contract gives a nested call -- and each of those is a question
    with one answer rather than a door onto the run's state.
    """

    def __init__(  # noqa: PLR0913 -- one argument per thing a context is
        self,
        plan: ExecutionPlan,
        record: NodeRecord,
        values: Mapping[str, Value],
        dictionary: Dictionary,
        rows: int,
        *,
        on_the_host: bool = False,
        machines: dict[str, dict[str, Value]] | None = None,
        widths: Mapping[str, np.ndarray] | None = None,
    ) -> None:
        """Bind one node's lowering to the run it is part of.

        ``on_the_host`` says that the values this context carries are the
        book's own numbers rather than a program's arguments, so a finding
        about them can be read now and reported as what it is: something
        knowable before anything was compiled. Everywhere else it is False
        and a finding travels as a flag.

        ``machines`` is the state map each compiled rollforward this pass has
        run, shared by every node of the pass: 16.1 evaluates a compilation
        once, and a model extracting a fund and a benefit base from one
        machine is one kernel run. It belongs to the *pass* rather than to
        the run, because a balance is an array of one batch's policies.

        ``widths`` is how many cells each axis-sizing call lays down for each
        policy of this batch, as preparation already counted them on the host
        (:attr:`Prepared.widths`, cut to the batch's rows). A lowering that
        lays an axis asks for its own count here rather than reading it back
        off the device: settling a batch then waits on nothing the card is
        still computing, which is what lets the host settle the next batch
        while the card runs this one.
        """
        self.on_the_host = on_the_host
        self._plan = plan
        self._record = record
        self._values = values
        self.dictionary = dictionary
        self.rows = rows
        self.machines = {} if machines is None else machines
        self._widths: Mapping[str, np.ndarray] = {} if widths is None else widths
        self._by_column = {
            plan.records[read].column: read
            for read in record.reads
            if read in plan.records and plan.records[read].column is not None
        }
        # Where this node's own answer has no value -- a left join's policy
        # whose key reached no row, kept under ``on_missing="null"`` (11.1.2).
        # Set by the lowering that keeps it; the run stores it beside the
        # node's value under :func:`absence_of`.
        self.absent: jax.Array | None = None

    @property
    def node(self) -> NodeRecord:
        """Return the record of the node this lowering is inside."""
        return self._record

    def cells_of(self, call: Call) -> np.ndarray | None:
        """Return how many cells one axis-sizing call lays down per policy, if known.

        The count preparation took for this node's call, cut to this batch's
        policies: the same number the call's own sizing answers, read on the
        host before anything was dispatched. None where the host has no count
        to offer -- outside a batch's settlement, or for a sizing that refused
        and so was never counted -- and the lowering then reads its count
        back off the device as it always could.
        """
        return self._widths.get(f"{self._record.node_id}/{call.name}")

    def record(self, node_id: str) -> NodeRecord:
        """Return one graph node's record -- its declared type and shape."""
        return self._plan.records[node_id]

    def column(self, name: str) -> Value:
        """Return the value standing under one column name, as this node reads it.

        The name is resolved through the node's own ``reads``, which carry the
        *version* the node was written against. Resolving it against whatever
        the frame ended up holding would read a later account of the column
        than the one the formula was written over.
        """
        value, absent = self.column_with_its_absences(name)
        if absent is not None:
            # A null this engine cannot hold, read by a formula that does not
            # fill it: refused for the policies it stands in, the rule for
            # a null read as a value.
            flag("join.unmatched", absent, where=self._record.node_id)
        return value

    def column_with_its_absences(self, name: str) -> tuple[Value, jax.Array | None]:
        """Return a column's value, and where it has none, for a fill to read.

        ``fill_null`` is the one operation that reads an absence as what it
        is; every other read goes through :meth:`column`, which refuses the
        policies it stands in.
        """
        node_id = self._by_column.get(name)
        if node_id is None or node_id not in self._values:
            raise DomainRefused(
                what=(
                    f"the formula reads column {name!r} and this run holds no "
                    "value for it"
                ),
                move=(
                    "run the engine on the document this frame exports, so "
                    "every column a formula reads is a node the run computed"
                ),
                clause="8.2",
            )
        absent = self._values.get(absence_of(node_id))
        return self._values[node_id], None if absent is None else absent.array

    def key_column(self, name: str, *, role: str) -> Value:
        """Return the value standing under one column name at this point in the run.

        For a column a call names in an *attribute* and its node does not
        read: a schedule's inception and end-date columns (11.1.37) are named
        in its recipe, so there is no versioned read to resolve the name
        through the way :meth:`column` does. What stands under the name is
        the last account of it this run has computed. A join's key is not
        one of these -- its node reads it (11.1.2), and it resolves through
        :meth:`column`.

        Args:
            name: The column the schedule names.
            role: What the schedule names it as -- ``"its inception date"``,
                ``"its end date"`` -- for a refusal to say which column of
                the schedule's the run could not find.

        Raises:
            DomainRefused: If this run holds no value under that name.

        """
        node_id = self._standing_under(name)
        if node_id is not None:
            return self._values[node_id]
        raise DomainRefused(
            what=(
                f"the schedule names {name!r} as {role}, and this run holds no "
                "column of that name"
            ),
            move=(
                "run the engine on the document this frame exports, so the "
                "column the schedule names is a node the run computed"
            ),
            clause="11.1.37",
        )

    def _standing_under(self, name: str) -> str | None:
        """Return the node whose value stands under one column name, or None.

        The last account of it this run has computed. Used where a name is
        not resolved through the node's own ``reads`` -- which is a column a
        schedule names in its recipe (11.1.37).
        """
        for node_id in reversed(self._plan.order):
            record = self._plan.records.get(node_id)
            if record is not None and record.column == name and node_id in self._values:
                return node_id
        return None

    def resolves_to_an_input(self, name: str) -> bool:
        """Return whether the value standing under one name is one that arrived.

        What decides *when* a finding about values became knowable, and so
        which group of the report it belongs in: a key every one of whose
        operands arrived with the book was checkable before anything was
        compiled, and one a calculation produced was not.

        **Asked of the node, never of the name.** A model that writes over an
        arriving column -- ``duration = duration + 10``, an ordinary line --
        leaves a document carrying an input node *and* a computed node under
        that one name, and a formula written after it reads the computed one.
        A test on the name alone answered "arrived" there, which put the
        refusal in the inputs group, named a key the book never carried, and
        closed "Nothing was computed." about a run that had computed the very
        key it was refusing over.

        Resolved the way the *value* is: through this node's own ``reads``
        where it reads one -- a lookup's key operand and a join's key alike
        (11.1.2) -- and otherwise through the last account the run has
        computed, which is what a schedule's column attribute names.
        """
        node_id = self._by_column.get(name) or self._standing_under(name)
        record = self._plan.records.get(node_id) if node_id is not None else None
        return record is not None and record.kind == "input"

    def bound_columns(self, fingerprint: str) -> dict[str, Value]:
        """Return the columns one compiled rollforward's own reads bind.

        Section 16.1 binds every operand of a machine -- its openings, its
        rates, its masks -- through **the compilation node's** versioned
        reads, not through the line that extracts a balance: a line reading a
        compilation reads the node and never the columns behind it (§16), so
        its own reads name one node and no columns at all.

        Where the document carries no such node the binding is the extracting
        node's own reads, which is the same rule read at the only other place
        it can be: a producer that cannot reach the compiled artefact emits
        neither the compilation's node nor the reference to it (§16), and a
        one-node document -- a published vector case -- carries the machine in
        the facet and the columns on the line that reads it.
        """
        for record in self._plan.records.values():
            if record.kind != ROLLFORWARD_KIND:
                continue
            if fingerprint_of(record.expr) != fingerprint:
                continue
            return {
                str(self._plan.records[read].column): self._values[read]
                for read in record.reads
                if read in self._values and self._plan.records[read].column is not None
            }
        return {
            str(name): self._values[read]
            for name, read in self._by_column.items()
            if read in self._values
        }

    def assumption(
        self, kind: str, name: str | None, fingerprint: str
    ) -> dict[str, Any]:
        """Return the payload one call's identity attributes name.

        Resolved by kind and the **whole** digest, with the name where the
        entry has one: section 15 says a short label is not an identity, and
        11.1.24 says a same-name entry carrying another fingerprint is not
        the basis this call names and must not be read as a fallback.

        Raises:
            DomainRefused: If the directory does not resolve the identity to
                exactly one entry carrying its values.

        """
        entries = [
            entry
            for entry in self.document.get("assumptions") or []
            if isinstance(entry, dict)
            and entry.get("kind") == kind
            and entry.get("fingerprint") == fingerprint
            and (name is None or entry.get("name") == name)
        ]
        payload = entries[0].get("payload") if len(entries) == 1 else None
        if not isinstance(payload, dict) or "omitted" in payload:
            raise DomainRefused(
                what=(
                    f"the {kind} this call names ({fingerprint}) resolves to "
                    f"{len(entries)} entries carrying their values"
                ),
                move=(
                    "export the artifact again from the run that read the "
                    "basis, so its values travel with the record"
                ),
                clause="15",
            )
        return payload

    def note(self, sentence: str) -> None:
        """Report something the run should say without refusing over it."""
        if sentence not in self._plan.notes:
            self._plan.notes.append(sentence)

    @property
    def document(self) -> dict[str, Any]:
        """Return the document this run is of."""
        return self._plan.document

    @property
    def bases(self) -> dict[str, tuple[Storage, str | None]]:
        """Return the bases this run has built, so a basis is built once."""
        return self._plan.bases

    def lower(self, node: OpNode) -> Value:
        """Return the value one operand tree stands for.

        A test with no truth value in some cells (a NaN reached a comparison
        in it, 11.1.26) is read here by an operation that states no answer
        over one -- the chained operators that do take it receive it from the
        plan's own stack -- so those cells are refused by name rather than
        read as whatever truth value the array happens to hold there.
        """
        value = self._plan.lower(node, self)
        if value.unknown is None:
            return value
        flag("comparison.unknown", value.unknown)
        return Value(
            value.array, value.carrier, value.shape, value.dtype, value.horizon
        )

    def sequence(self, node: OpNode) -> tuple[LitSequenceMember, ...]:
        """Return the members a sequence literal holds, refusing anything else.

        Section 11.1.5 and 11.1.6 put the members in the tree rather than in a
        configuration, exactly so that what identifies the operation travels
        with it. An operand that computed the members is a different operation
        and the clause says so.
        """
        if isinstance(node, Lit) and isinstance(node.value, tuple):
            return node.value
        raise DomainRefused(
            what=(
                "this operation takes its members written into the formula, "
                "and here they are the answer of an expression"
            ),
            move=(
                "write the members out, or leave the line where it is: a set "
                "an expression produced is not this operation"
            ),
            clause="11.1.5",
        )

    def infer(self, call: Call, operands: Sequence[Value]) -> tuple[str, Shape]:
        """Return the type and shape 11.1.25's numeric clause gives a call.

        The shared rule, not a second dispatch table: ``div`` answers ``f64``,
        a double on either side promotes, and two integers stay integers for
        the five operations the clause names. A family whose answer is not a
        number -- a comparison, a test for absence -- states its own type on
        the value it returns and does not come here.

        **A Boolean operand is a stored indicator and counts as a double.**
        11.1.25's own domain is ``i64`` and ``f64``, so the only way a Boolean
        reaches an arithmetic operand at all is 11.1.26's other half: a
        comparison used as an arithmetic operand supplies ``f64`` 1.0 and 0.0.
        Reading the pair ``{bool, bool}`` as ``i64`` -- which is what "no f64
        here" would say -- makes ``(a < b) + (a <= b)`` answer 1.0 where the
        clause answers 2.0, and makes ``(a < b) - (a > b)`` an operation with
        no integer subtraction behind it at all.
        """
        shape: Shape = (
            "list" if any(one.shape == "list" for one in operands) else "scalar"
        )
        carrier = arithmetic_carrier(
            call.name,
            tuple(one.carrier for one in operands),
            per_period=shape == "list",
            exponent=written_exponent(call.name, call.args),
        )
        # The arithmetic family validates its carriers before asking this rule.
        if carrier is None:  # pragma: no cover -- validated numeric operands
            message = "validated arithmetic operands have no numeric carrier"
            raise AssertionError(message)
        return carrier, shape

    def literal_code(self, text: str) -> int:
        """Return the interned code one text literal stands for in this run."""
        return self.dictionary.code_for(text)


@dataclass(slots=True)
class ExecutionPlan:
    """One document, read once, and everything the run needs to know about it."""

    document: dict[str, Any]
    inspection: ExecutionInspection
    order: tuple[str, ...]
    statuses: tuple[NodeStatus, ...]
    pre_axis: tuple[str, ...]
    records: dict[str, NodeRecord]
    tree_refusals: tuple[Refusal, ...]
    scope: str
    notes: list[str] = field(default_factory=list)
    # Every basis this run has built, by kind, digest and answer column. One
    # per run and never one across runs: a grid holds interned codes, and
    # the codes are this run's (see :mod:`gaspatchio_jax.interning`).
    bases: dict[str, tuple[Storage, str | None]] = field(default_factory=dict)
    # Every program this run has compiled, by the shape it was built for. One
    # per run and never one across runs: a program holds this run's interned
    # codes and this run's bases.
    programs: dict[tuple[object, ...], Program] = field(default_factory=dict)
    # What one policy cost in temporaries, as the last group's program
    # reported it. Read by the scaling report; the run says it in a note.
    per_policy: int = 0

    @staticmethod
    def stage_inspect(
        document: dict[str, Any], *, every_node: bool = False
    ) -> ExecutionPlan:
        """Read the document, and say per node what this engine can do with it.

        The validator runs first, through ``inspect_execution``, which itself
        validates deeply before it inspects anything -- one pass rather than
        two over the same digests, and the same report either way.

        ``every_node`` decides which nodes the run *needs*, and therefore
        which refusals are this run's: a superseded definition the final
        schema never reads should not refuse a run that never asked for it.
        """
        load()
        roots = _roots(document) if every_node else None
        inspection = inspect_execution(document, roots=roots)
        records = _records(document)
        scope = "every-node" if every_node else "final-schema"
        refusals = [
            one
            for one in document_refusals(document, inspection)
            if not _read_here(one, document)
        ]
        if refusals:
            return ExecutionPlan(
                document,
                inspection,
                (),
                tuple(
                    NodeStatus(one.where, "refused", one.what, one.clause)
                    for one in refusals
                ),
                (),
                records,
                tuple(refusals),
                scope,
            )
        order = _execution_order(
            document, records, inspection.reachable, every_node=every_node
        )
        statuses = tuple(
            _status_of(records[node_id], records, document) for node_id in order
        )
        pre_axis = _pre_axis(document, records, order)
        refused = tuple(
            _refusal_from(status, records[status.node_id])
            for status in statuses
            if status.status == "refused"
        )
        plan = ExecutionPlan(
            document=document,
            inspection=inspection,
            order=order,
            statuses=statuses,
            pre_axis=pre_axis,
            records=records,
            tree_refusals=refused,
            scope=scope,
        )
        plan._inspect_payloads()
        return plan

    def _inspect_payloads(self) -> None:
        """Validate each reachable table invocation and machine from its payload alone.

        A keyed read against its basis, and a compiled rollforward against
        its body and schedule (:func:`inspect_machine`) -- for each node that
        reads one, and for each running state, whose machine is its owner's.
        And each call that lays its own axis -- a projection declaration, a
        schedule reading -- through the sizing the run takes its width with,
        as far as the record carries it (:meth:`_inspect_sizing`): an anchor
        this engine has no boundaries for, or a horizon the record does not
        fix, is refused there before any value is read. Those are the
        refusals the run meets before it reads a value, so the inspection a
        ``validate`` prints names them on the same nodes, in the same
        sentence and under the same clause.
        """
        refusals = list(self.tree_refusals)
        statuses = list(self.statuses)
        dictionary = Dictionary()
        for index, status in enumerate(statuses):
            record = self.records[status.node_id]
            if status.status == "refused":
                continue
            context = LoweringContext(self, record, {}, dictionary, 0)
            try:
                for fingerprint in self._machines_read(record):
                    inspect_machine(fingerprint, context)
                calls = (
                    []
                    if record.expr is None
                    else _calls_inside(op_node_from_json(record.expr))
                )
                for call in calls:
                    if call.name in KEYED_READS:
                        inspect_payload(call, context)
                    if call.name in SIZINGS:
                        self._inspect_sizing(record, call, dictionary)
            except DomainRefused as refused:
                one = domain_refusal(record.node_id, refused)
                refusals.append(one)
                statuses[index] = NodeStatus(one.where, "refused", one.what, one.clause)
        self.statuses = tuple(statuses)
        self.tree_refusals = tuple(refusals)

    def _inspect_sizing(
        self, record: NodeRecord, call: Call, dictionary: Dictionary
    ) -> None:
        """Run one axis-laying call's sizing from the record alone, as the run sizes it.

        The sizing the run calls in preparation (:meth:`_stage_widths`), over
        a context that holds no value: where the count follows from the
        attributes and the payload, the sizing answers or refuses exactly as
        it will over the book, and where it needs an operand's values --
        a column horizon, an inception date -- it stops there and the run
        decides. Every flag it raises is dropped, as preparation drops them.

        Raises:
            DomainRefused: If the sizing refuses before it reads a value.

        """
        context = LoweringContext(self, record, _NoValueYet(), dictionary, 1)
        try:
            with (
                about(record.node_id),
                recording(),
                jax.ensure_compile_time_eval(),
            ):
                SIZINGS[call.name](call, context)
        except _ValueNeeded:
            return

    def _machines_read(self, record: NodeRecord) -> list[str]:
        """Return the compilations one node's value is run out of, by identity.

        A running state's is its owner's. Any other node's are those its tree
        names at a door onto a compilation. The compilation's own node is
        none: it is the machine, never lowered as a column (§16), and the run
        refuses on the nodes that ask it for a balance.
        """
        if record.kind == ROLLFORWARD_KIND:
            return []
        if record.kind == STATE_KIND:
            owner = _state_owner(record, self.records, self.document)
            return [] if owner is None else [owner]
        if record.expr is None:
            return []
        return [
            str(dict(call.attrs)["fingerprint"])
            for call in _calls_inside(op_node_from_json(record.expr))
            if (call.name == MACHINE or call.name in MACHINE_DOORS)
            and isinstance(dict(call.attrs).get("fingerprint"), str)
        ]

    def stage_validate_inputs(self, inputs: pl.DataFrame) -> PreparedInputs:
        """Check the book against the artifact's input nodes, and carry it in.

        Raises:
            EngineRefusal: If anything the tree needs is missing, mistyped,
                misshapen or carries a null.

        """
        # An integer an i64 holds is read as i64, as the producer reads it
        # where the book enters the frame: one book for both engines. A wide
        # one holding a value past i64 keeps its width and is refused by
        # that value where the tree reads it (`input_mismatch`).
        handed = read_as_i64(inputs)
        inputs = self._selected(handed)
        refusals: list[Refusal] = []
        columns: dict[str, Value] = {}
        held = dict(zip(inputs.columns, inputs.dtypes, strict=True))
        dictionary = Dictionary()
        key_only = _key_only_columns(self.document, self.records, self.order)
        for requirement in self.inspection.required_inputs:
            if requirement.node_id not in self.records:
                continue
            column = requirement.column
            if column not in held:
                refusals.append(input_missing(requirement.node_id, column))
                continue
            refusal = input_mismatch(
                requirement, inputs[column], keys_only=column in key_only
            )
            if refusal is not None:
                refusals.append(refusal)
                continue
            missing = int(inputs[column].null_count())
            if missing:
                self.notes.append(
                    f"{column!r} carries {missing} keys that are not there, "
                    "and every read of it is a key: each one is a miss under "
                    "the read's own policy"
                )
            columns[column] = _carried(inputs[column], requirement.dtype, dictionary)
        if refusals:
            raise EngineRefusal(RunReport(refusals=tuple(refusals), notes=()))
        self.notes.extend(_nulls_nothing_reads(inputs, set(columns)))
        return PreparedInputs(
            frame=inputs,
            columns=columns,
            rows=inputs.height,
            dictionary=dictionary,
            handed=handed if handed is not inputs else None,
        )

    def _selected(self, inputs: pl.DataFrame) -> pl.DataFrame:
        """Return the policies the model valued: the book through its selection.

        The document says which policies the model chose to value -- a filter,
        a semi or an anti join -- and a replay that valued every row it was
        handed would publish a total over policies the model left out, under
        the model's own stamps. So the book goes through each step first, on
        the host, as the producer's own core lowering reads the step (section
        7.6). A step no replay can apply is refused by name.

        Raises:
            EngineRefusal: If a step cannot be applied to this book.

        """
        try:
            return apply_selection(self.document, inputs)
        except SelectionRefusedError as refused:
            raise EngineRefusal(
                RunReport(
                    refusals=(
                        Refusal(
                            group="inputs",
                            where=refused.step,
                            count=None,
                            what=str(refused),
                            move=(
                                "export the model again with a selection the "
                                "book can answer, or select the model points "
                                "before the run"
                            ),
                            clause="7.6",
                        ),
                    ),
                    notes=tuple(self.notes),
                )
            ) from refused

    def stage_prepare(self, prepared: PreparedInputs) -> Prepared:
        """Settle on the host everything the trace should not have to carry.

        Two things today: the interning dictionary, built while the columns
        were carried in, and the operations that produce text, which the
        trace does not carry. Both are done from values that arrived, never
        from a calculation -- which is the condition the capability states
        and the status publishes.

        A host operation can refuse, and it refuses the same way a lowered one
        does: every finding into one report, the run over. This stage is as
        much a place a refusal is met as the trace is, and a refusal that left
        here as something other than one report would be the one finding a
        reader met in a different shape from all the others.

        Raises:
            EngineRefusal: If a host operation is outside the domain its
                clause states.

        """
        host: dict[str, Value] = {}
        refusals: list[Refusal] = []
        self._stage_domains(prepared, refusals)
        with recording() as flags:
            # The host settlement first, and the axis after it. A pre-axis
            # subgraph can read a column an off-trace operation produced --
            # level 4's horizon stands on a parsed entry date -- and an axis
            # stage that ran first would meet that operation in the trace,
            # where it has no answer, and refuse a model that is perfectly
            # ordinary.
            for node_id in self.order:
                record = self.records[node_id]
                name = _call_name(record)
                if name is None or name not in LOWERINGS:
                    continue
                if not LOWERINGS[name][1].off_trace:
                    continue
                try:
                    host[node_id] = _host_value(record, prepared, prepared.dictionary)
                except DomainRefused as refused:
                    refusals.append(domain_refusal(node_id, refused))
            axis = self._stage_axis(prepared, host, refusals, flags)
            widths = self._stage_widths(prepared, host, axis)
            self._stage_keys(prepared, host, axis, refusals)
        if refusals:
            raise EngineRefusal(
                RunReport(refusals=tuple(refusals), notes=tuple(self.notes))
            )
        return Prepared(
            inputs=prepared,
            dictionary=prepared.dictionary,
            host=host,
            flags=flags,
            axis=axis,
            widths=widths,
        )

    def _stage_domains(self, prepared: PreparedInputs, refusals: list[Refusal]) -> None:
        """Check arriving operands without computing or retaining derived values."""
        values = {
            node_id: prepared.columns[record.column or ""]
            for node_id, record in self.records.items()
            if record.kind == "input" and (record.column or "") in prepared.columns
        }
        for node_id in self.order:
            record = self.records[node_id]
            if record.expr is None:
                continue
            context = LoweringContext(
                self,
                record,
                values,
                prepared.dictionary,
                prepared.rows,
                on_the_host=True,
            )
            try:
                self._domains_of(node_id, record.expr, context, refusals)
            except RecursionError:
                # The operand checks read each call's operands one level inside
                # the next; a tree past the call depth is refused here by name,
                # as the lowering refuses it, rather than as a traceback.
                refusals.append(domain_refusal(node_id, _too_deep(record.expr)))

    def _domains_of(
        self,
        node_id: str,
        tree: Mapping[str, Any],
        context: LoweringContext,
        refusals: list[Refusal],
    ) -> None:
        """Check the arriving operands of every call one node's tree makes."""
        for call in _calls_inside(op_node_from_json(tree)):
            with about(node_id), recording() as flags:
                try:
                    check_inputs(call, context)
                except DomainRefused as refused:
                    refusals.append(
                        replace(domain_refusal(node_id, refused), group="inputs")
                    )
            refusals.extend(
                one.refusal(operand_is_computed=False)
                for one in findings_of(flags)
                if one.refuses
            )

    def _stage_keys(
        self,
        prepared: PreparedInputs,
        host: Mapping[str, Value],
        axis: Mapping[str, Value],
        refusals: list[Refusal],
    ) -> None:
        """Answer here every key question the book alone settles.

        A read that selects a row on keys which all arrived with the book is
        a read whose misses are knowable before anything is compiled. The
        run has cost nothing at that point, so the refusal says so -- and the
        report names the first key tuple the basis could not answer rather
        than a count out of a program that has already run.

        The same read is met again when the program is built, where the same
        two checks travel as flags. They catch nothing, because a book that
        would have tripped them never reached the program: this stage
        refused it. What this stage buys is *when* a reader is told, which is
        the whole distinction between the two closing sentences.
        """
        settled: dict[str, Value] = {
            **{
                node_id: prepared.columns[self.records[node_id].column or ""]
                for node_id in self.order
                if self.records[node_id].kind == "input"
                and (self.records[node_id].column or "") in prepared.columns
            },
            **dict(host),
            **dict(axis),
        }
        for node_id, call in self._reads_on_arriving_keys(settled):
            context = LoweringContext(
                self,
                self.records[node_id],
                settled,
                prepared.dictionary,
                prepared.rows,
                on_the_host=True,
            )
            try:
                with about(node_id), recording():
                    _dispatch(call, context)
            except DomainRefused as refused:
                refusals.append(domain_refusal(node_id, refused))

    def _reads_on_arriving_keys(
        self, settled: Mapping[str, Value]
    ) -> list[tuple[str, Call]]:
        """Return every row-selecting call whose keys all came with the book."""
        found: list[tuple[str, Call]] = []
        for node_id in self.order:
            tree = self.records[node_id].expr
            if tree is None:
                continue
            context = LoweringContext(
                self, self.records[node_id], settled, Dictionary(), 0
            )
            found.extend(
                (node_id, call)
                for call in _calls_inside(op_node_from_json(tree))
                if call.name in KEYED_READS and keys_all_arrived(call, context)
            )
        return found

    def _stage_widths(
        self,
        prepared: PreparedInputs,
        host: Mapping[str, Value],
        axis: Mapping[str, Value],
    ) -> dict[str, np.ndarray]:
        """Return how many cells each axis-sizing operation lays down per policy.

        The count on its own, and before any array is allocated. It is the
        one number that decides a *shape* -- how wide the rectangle is, and
        therefore which policies are rows of one rectangle and one compiled
        program -- and a shape cannot be an argument to a program built
        around it.

        A sizing that refuses is left out rather than refused here: the
        operation itself refuses when it is lowered, with its own sentence
        and in its own group, and refusing twice for one cause is one finding
        a reader meets in two shapes.

        **And every flag it raises is thrown away, in a book of its own.** A
        sizing lowers whatever its operands stand on -- ``date.date_ranges``
        lowers both of its endpoint trees to find out how far they reach --
        and a check raised in there is a check the same cell will raise again
        when the whole node is lowered for real. Left in the run's book it
        would be counted twice and the report would say two cells where the
        book has one. So this stage records into a book nobody reads, exactly
        as :meth:`_stage_keys` does, and the flags that reach completion are
        the ones raised where the value was actually built.
        """
        settled: dict[str, Value] = {
            **{
                node_id: prepared.columns[self.records[node_id].column or ""]
                for node_id in self.order
                if self.records[node_id].kind == "input"
            },
            **dict(host),
            **dict(axis),
        }
        found: dict[str, np.ndarray] = {
            f"{name}/carried": np.asarray(value.horizon.lengths, dtype=np.int64)
            for name, value in prepared.columns.items()
            if value.horizon is not None
        }
        for node_id, call in self._axis_sizing_calls():
            record = self.records[node_id]
            context = LoweringContext(
                self, record, settled, prepared.dictionary, prepared.rows
            )
            try:
                with (
                    about(node_id),
                    recording() as flags,
                    jax.ensure_compile_time_eval(),
                ):
                    counts = SIZINGS[call.name](call, context)
                    # Held to the node's own periods exactly as every other
                    # stage holds its flags, so that what this book carries
                    # is what a kept book would have carried. It is then
                    # dropped, for the reason the docstring gives.
                    to_the_horizon(
                        flags,
                        0,
                        _axes_of(
                            record, settled, Value(counts, "i64", "scalar", "i64")
                        ),
                    )
                    found[f"{node_id}/{call.name}"] = np.asarray(counts, dtype=np.int64)
            except DomainRefused:
                # And only this. A sizing that refuses is left out because the
                # operation refuses again when it is lowered, with its own
                # sentence and in its own group. Anything else -- a type
                # error, a shape error -- is a defect in this engine, and
                # swallowing it would turn it into a book grouped on one axis
                # fewer, which is a wrong answer arrived at quietly.
                continue
        return found

    def _axis_sizing_calls(self) -> list[tuple[str, Call]]:
        """Return every call in this run that reads the width of its own answer."""
        found: list[tuple[str, Call]] = []
        for node_id in self.order:
            tree = self.records[node_id].expr
            if tree is None:
                continue
            found.extend(
                (node_id, call)
                for call in _calls_inside(op_node_from_json(tree))
                if call.name in SIZINGS
            )
        return found

    def _stage_axis(
        self,
        prepared: PreparedInputs,
        host: Mapping[str, Value],
        refusals: list[Refusal],
        flags: FlagBook,
    ) -> dict[str, Value]:
        """Return the pre-axis subgraph's values, settled before the main pass.

        **Two-stage tracing.** The period count depends on data: a
        ``projection_set`` names a column as its horizon and a schedule names
        one as its term, and in levels 4 and 5 five scalar nodes stand between
        the book and that column. A trace over rectangular arrays needs the
        width before it builds one, so the ancestry of the horizon column is
        run first, on its own, and the main pass begins with those values in
        hand rather than discovering the axis half way through itself.

        **A refusal here is a refusal.** It is met before anything the main
        pass would compute and it stops the run with the rest of this stage's
        findings, in one report -- which is what it was doing before it was
        swallowed, and the swallowing is what made the stage a no-op nobody
        noticed.

        The flags this stage raises go into the book the caller opened, so a
        check on a node the axis stands on reaches completion with the trace's
        own; the main pass then reads these values rather than recomputing the
        nodes, so no flag is raised twice. **And they are held to their own
        node's horizon here exactly as the main pass holds its own**: a
        horizon column is an ordinary calculation and may stand on a
        per-period one -- ``max(a // b)`` is a term in months -- so a check
        raised in this stage sees the same padding every other check does.
        """
        values: dict[str, Value] = {}
        for node_id in self.pre_axis:
            record = self.records[node_id]
            if record.kind == "input":
                values[node_id] = prepared.columns[record.column or ""]
                continue
            if node_id in host:
                values[node_id] = host[node_id]
                continue
            tree = record.expr
            if tree is None:
                continue
            context = LoweringContext(
                self, record, values, prepared.dictionary, prepared.rows
            )
            raised = len(flags.entries)
            try:
                with about(node_id):
                    produced = self.lowered(tree, context)
                values[node_id] = _settled(produced, record)
                _keep_absences(values, node_id, context)
                to_the_horizon(flags, raised, _axes_of(record, values, produced))
            except DomainRefused as refused:
                refusals.append(domain_refusal(node_id, refused))
        return values

    def stage_settle(self, prepared: Prepared, rows: np.ndarray) -> Settled:
        """Return everything one batch's compiled pass reads, settled on the host.

        The book's columns, the host settlement and the pre-axis subgraph,
        each cut to this batch's policies -- and then the operations that read
        the width of their own answer, lowered here rather than in the
        program. A width is not a number a program can be handed: it is the
        shape of the program's own arrays, fixed while the program is being
        built. So those operations answer first, on the host, and their
        answers go in as arguments like every other column.

        **Nothing is read back off the device here.** Every width an axis
        takes was counted on the host when the book was prepared, and each
        lowering that lays an axis is handed its batch's own counts rather
        than reading them back. A read-back queues behind whatever the card
        is already computing, so a settlement that read would wait for the
        previous batch's program to finish -- and the host could never
        settle one batch while the card computes another.

        Raises:
            EngineRefusal: If an axis-sizing operation is outside the domain
                its clause states.

        """
        arriving: dict[str, Value] = {}
        for node_id in self.order:
            record = self.records[node_id]
            if record.kind == "input":
                arriving[node_id] = prepared.inputs.columns[record.column or ""]
            elif node_id in prepared.host:
                arriving[node_id] = prepared.host[node_id]
            elif node_id in prepared.axis:
                arriving[node_id] = prepared.axis[node_id]
        settled = _rows_of(arriving, rows)
        sizing = self._axis_sizing_calls()
        generated = {node_id for node_id, _ in sizing}
        counted = _host_widths(sizing, prepared.widths, rows)
        refusals: list[Refusal] = []
        with recording() as flags:
            for node_id in self.order:
                record = self.records[node_id]
                tree = record.expr
                if node_id not in generated or node_id in settled or tree is None:
                    continue
                context = LoweringContext(
                    self,
                    record,
                    settled,
                    prepared.dictionary,
                    int(rows.size),
                    widths=counted,
                )
                raised = len(flags.entries)
                try:
                    with about(node_id):
                        produced = self.lowered(tree, context)
                    settled[node_id] = _settled(produced, record)
                    _keep_absences(settled, node_id, context)
                    to_the_horizon(flags, raised, _axes_of(record, settled, produced))
                except DomainRefused as refused:
                    refusals.append(domain_refusal(node_id, refused))
        if refusals:
            raise EngineRefusal(
                RunReport(refusals=tuple(refusals), notes=tuple(self.notes))
            )
        return Settled(
            rows=rows,
            values=settled,
            dictionary=prepared.dictionary,
            flags=flags,
        )

    def compile_for(
        self, settled: Settled, returns: frozenset[str] | None = None
    ) -> tuple[Program, CacheOutcome]:
        """Trace the region pass once for this batch's shape, and compile it.

        One program per (bucket, batch): the arrays go in as arguments and
        the widths are fixed in the program, so a second batch of the same
        widths and the same size is the same executable over different
        numbers -- which is what makes a book of a million policies a
        compilation and not a thousand of them.

        **What the program hands back is what its reader reads.** Every node
        the run publishes, by default: the stream writes each of them. A
        fold names the handful of columns it folds (``returns``), and its
        program hands back those and nothing else -- every node is still
        traced and every check still carried, so a refusal is the same
        refusal, but a column nobody reads never leaves the card: folding a
        total and a term structure of level 4 returns two columns of the
        final schema's hundred and twenty-eight.

        **And of every check, what a finding reports**: how many
        cells it caught and the first of them, reduced on the card and
        handed back in one array for every check (:func:`~gaspatchio_jax.
        checks.tallied`). A coarse check's mask and operands are handed back
        besides, and read only where the card caught a cell of it: its count
        is of what the in-trace test caught, and only the host's exact
        judgement says which of those are wrong.

        Returns:
            The program, and what its compilation cost and came from.

        Raises:
            EngineRefusal: If anything the tree holds is outside the domain
                its clause states. A refusal here is met while the program is
                being built, before any of it has run.

        """
        names = tuple(settled.values)
        axes = _axes_in(settled.values)
        read: dict[str, object] = {}

        def region(
            arrays: tuple[jax.Array, ...], counts: tuple[jax.Array, ...]
        ) -> tuple[
            dict[str, jax.Array],
            tuple[jax.Array, ...],
            jax.Array,
            tuple[jax.Array, ...],
            tuple[tuple[jax.Array, ...], ...],
        ]:
            standing, computed = self._traced(settled, arrays, counts)
            carried = self.returned_nodes(computed.values, returns)
            counted = self._per_period_doubles(computed.values)
            out = _axes_in(
                {node_id: computed.values[node_id] for node_id in (*carried, *counted)}
            )
            read["columns"] = carried
            # A published node's absences come back beside it, so the column
            # is written with a null where the node has no value (11.1.2).
            kept = [
                absence_of(node_id)
                for node_id in carried
                if absence_of(node_id) in computed.values
            ]
            if returns is not None:
                # A fold reads the column as numbers, and an absence it cannot
                # skip is a null it would have summed: refused, as a formula
                # reading the column unfilled is.
                computed.flags.entries.extend(
                    Flagged(
                        name="join.unmatched",
                        where=node_id,
                        mask=computed.values[absence_of(node_id)].array,
                    )
                    for node_id in carried
                    if absence_of(node_id) in computed.values
                )
                kept = []
            read["shapes"] = {
                node_id: (
                    computed.values[node_id].carrier,
                    computed.values[node_id].shape,
                    computed.values[node_id].dtype,
                    _axis_index(computed.values[node_id], out),
                )
                for node_id in (*carried, *kept)
            }
            read["buckets"] = tuple(axis.bucket for axis in out)
            read["sources"] = tuple(_source_of(axis, standing) for axis in out)
            read["longest"] = tuple(
                sorted(
                    {
                        at
                        for node_id in counted
                        if (at := _axis_index(computed.values[node_id], out))
                        is not None
                    }
                )
            )
            entries = computed.flags.entries
            coarse = [entry for entry in entries if entry.judgement is not None]
            read["flags"] = tuple(entry.carried() for entry in entries)
            return (
                {
                    node_id: computed.values[node_id].array
                    for node_id in (*carried, *kept)
                },
                tuple(axis.t for axis in out),
                # Every mask as its node's horizon held it, which is exactly
                # the mask the host used to scan.
                tallied([entry.mask for entry in entries]),
                tuple(entry.mask for entry in coarse),
                tuple(entry.operands for entry in coarse),
            )

        arrays = tuple(settled.values[name].array for name in names)
        counts = tuple(axis.t for axis in axes)
        # Tracing first, and outside the measurement. A trace builds this
        # run's bases on the host, and building one is itself a handful of
        # small compilations -- so a window around both would report the
        # basis's cache and call it the program's.
        lowered = jax.jit(region).lower(arrays, counts)
        with watching() as held:
            compiled = lowered.compile()
        return Program(
            compiled=compiled,
            names=names,
            axes=len(axes),
            columns=read["columns"],  # type: ignore[arg-type]
            shapes=read["shapes"],  # type: ignore[arg-type]
            buckets=read["buckets"],  # type: ignore[arg-type]
            sources=read["sources"],  # type: ignore[arg-type]
            longest=read["longest"],  # type: ignore[arg-type]
            flags=read["flags"],  # type: ignore[arg-type]
        ), held.outcome

    def _traced(
        self,
        settled: Settled,
        arrays: tuple[jax.Array, ...],
        counts: tuple[jax.Array, ...],
    ) -> tuple[list[Horizon], Computed]:
        """Return one batch's region pass over the arrays a program is handed.

        The body of every program :meth:`compile_for` builds, before anything
        is chosen to hand back, and called inside its trace: each value the
        batch was settled with, standing on the axis it was settled on with
        the period counts handed in, and every node lowered over them with
        every check carried and held to its node's own periods.

        Returns:
            The axes the batch was handed in on, as the trace holds them, and
            what the region pass computed and flagged over them.

        """
        axes = _axes_in(settled.values)
        standing = [
            Horizon.over(count, bucket=axis.bucket, host=axis.lengths)
            for count, axis in zip(counts, axes, strict=True)
        ]
        held = {
            name: replace(
                value, array=array, horizon=_on(standing, _axis_index(value, axes))
            )
            for (name, value), array in zip(settled.values.items(), arrays, strict=True)
        }
        return standing, self._regions(held, settled.count, settled.dictionary)

    def _regions(
        self, settled: Mapping[str, Value], rows: int, dictionary: Dictionary
    ) -> Computed:
        """Lower every node the run needs, carrying each check as a bounded flag.

        Every node is attempted, and every refusal met while lowering travels
        in one report -- the same shape the two pre-flight groups have, and
        for the same reason: an engine that stopped on the first one sends the
        reader back round the edit-run loop once per column. A node standing
        on one that refused is passed over in silence: "no value for this"
        would be one finding per column downstream of the one finding that
        matters.

        Raises:
            EngineRefusal: If anything the tree holds is outside the domain
                its clause states.

        """
        values: dict[str, Value] = dict(settled)
        refusals: list[Refusal] = []
        withheld: set[str] = set()
        machines: dict[str, dict[str, Value]] = {}
        with recording() as flags:
            for node_id in self.order:
                record = self.records[node_id]
                if any(read in withheld for read in record.reads):
                    withheld.add(node_id)
                    continue
                if node_id in values:
                    continue
                if record.kind == ROLLFORWARD_KIND:
                    # The machine is not a column (§16) and nothing publishes
                    # it: every balance it carries is a running state's own
                    # node, and each of those asks the machine for it. Run
                    # here it would be run twice.
                    continue
                tree = self.tree_of(record)
                if tree is None:
                    continue
                context = LoweringContext(
                    self, record, values, dictionary, rows, machines=machines
                )
                raised = len(flags.entries)
                try:
                    with about(node_id):
                        produced = self.lowered(tree, context)
                    values[node_id] = _settled(produced, record)
                    _keep_absences(values, node_id, context)
                    # Every check this node raised is about this node's own
                    # periods. Held here rather than at each raise because a
                    # check can be raised before the horizon that governs it
                    # is known -- an operand widened to a double flags at
                    # ±2^53 inside ``carried_to``, frames before the
                    # operation that will align it has run.
                    to_the_horizon(flags, raised, _axes_of(record, values, produced))
                except DomainRefused as refused:
                    refusals.append(domain_refusal(node_id, refused))
                    withheld.add(node_id)
        if refusals:
            raise EngineRefusal(
                RunReport(refusals=tuple(refusals), notes=tuple(self.notes))
            )
        return Computed(values=values, rows=rows, dictionary=dictionary, flags=flags)

    def stage_dispatch(self, settled: Settled, program: Program) -> Dispatched:
        """Hand one batch to its compiled program, and return without waiting.

        A compiled program runs asynchronously: the call queues it on the
        device and hands back arrays the card is still computing. Nothing is
        read back here, so the host is free to settle the next batch while
        the card works on this one; :meth:`stage_finish` reads the answers
        when they are wanted.
        """
        axes = _axes_in(settled.values)
        if len(axes) != program.axes:  # pragma: no cover -- a defect, not a refusal
            message = (
                f"this batch stands on {len(axes)} axes and its program was "
                f"built around {program.axes}"
            )
            raise AssertionError(message)
        columns, counts, tallies, masks, operands = program.compiled(
            tuple(settled.values[name].array for name in program.names),
            tuple(axis.t for axis in axes),
        )
        return Dispatched(
            rows=settled.rows,
            program=program,
            columns=columns,
            counts=tuple(counts),
            tallies=tallies,
            coarse_masks=tuple(masks),
            coarse_operands=tuple(tuple(one) for one in operands),
            lengths=tuple(axis.lengths for axis in axes),
            flags=settled.flags,
            dictionary=settled.dictionary,
        )

    def stage_finish(self, dispatched: Dispatched, queued: object = None) -> Batched:
        """Read one dispatched batch's answers back, and put them into values.

        What comes back is arrays: the columns the manifest names, the axis
        each per-period one stands on, and every check's count and first
        caught cell, counted on the card. They are put back into values
        here, on the host, because the horizon a column is cut to is *this*
        batch's period counts and the program was built around another
        batch's. Those counts are the ones the batch was settled with,
        already on the host, wherever an answer stands on an axis the batch
        was handed in on; only an axis the program laid itself has its counts
        read back.

        Reading the checks' counts is what waits for the program to end, and
        only for this batch's: a program dispatched after it is not waited
        for. A coarse check's mask and operands are read only where the card
        counted a caught cell of it. ``queued`` is what the reader queued
        beside the batch's program when it was dispatched, handed back with
        the batch.
        """
        program = dispatched.program
        standing = [
            Horizon.over(count, bucket=bucket, host=_counts_of(dispatched, at, count))
            for at, (count, bucket) in enumerate(
                zip(dispatched.counts, program.buckets, strict=True)
            )
        ]
        values = {
            node_id: Value(
                dispatched.columns[node_id],
                carrier,  # type: ignore[arg-type]
                shape,  # type: ignore[arg-type]
                dtype,
                None if at is None else standing[at],
            )
            for node_id, (carrier, shape, dtype, at) in program.shapes.items()
        }
        return Batched(
            rows=dispatched.rows,
            values=values,
            dictionary=dispatched.dictionary,
            columns=program.columns,
            # The host stage's findings in front of the trace's: they were
            # knowable first and a reader reads a report in the order things
            # became knowable.
            findings=(
                *findings_of(dispatched.flags, dispatched.rows),
                *findings_tallied(
                    program.flags,
                    dispatched.tallies,
                    dispatched.coarse_masks,
                    dispatched.coarse_operands,
                    dispatched.rows,
                ),
            ),
            longest=max(
                (
                    int(standing[at].lengths.max())
                    for at in program.longest
                    if standing[at].lengths.size
                ),
                default=0,
            ),
            queued=queued,
        )

    def stage_batches(  # noqa: PLR0913 -- one argument per thing the loop is shaped by
        self,
        prepared: Prepared,
        *,
        groups: Sequence[np.ndarray] | None = None,
        budget_bytes: int = BUDGET_BYTES,
        batch: int | None = None,
        depth: int | None = None,
        returns: frozenset[str] | None = None,
        on_dispatch: Callable[[Dispatched], object] | None = None,
    ) -> Iterator[Batched]:
        """Run the whole book batch by batch, handing each on as it finishes.

        The groups come first, because two policies whose timelines round up
        to different widths are not rows of one rectangle. Inside a group the
        size of a batch is read off the compiled program's own temporaries
        against the budget, and every batch of that group and that size is the
        same executable over different numbers.

        **The host and the card work at once.** A batch handed to
        its program runs on the card by itself, and the host settles and
        dispatches the next batch before it reads this one's answers back --
        so the host's settling overlaps the card's computing instead of
        waiting its turn, and reading a batch back waits for that batch's
        program alone. ``depth`` is how many batches are dispatched ahead of
        the one being handed over: the device's own by default -- one on a
        card, nought on the CPU, where there is no second device to overlap
        with (:func:`depth_on`) -- and the bench passes either to measure
        what the overlap is worth.

        **Work the reader wants on the device beside a batch** is queued
        straight behind that batch's own program, through ``on_dispatch``:
        queued when the batch is handed over, it would wait for the next
        batch's program as well. What it returns rides with the batch
        (:attr:`Batched.queued`). It is called before the batch is handed
        over, so a fault it meets is its to hold for the batch's own turn,
        not to raise.

        **Nothing moves but the timing.** Batches are handed over in the
        order they were dispatched, so findings arrive in batch order. A
        refusal met settling a batch or building its program is raised only
        once every batch dispatched before it has been handed over, as when
        the batches ran one at a time. And nothing is kept here: whoever
        takes a batch decides what outlives it -- the stream writes its rows
        away and keeps its findings (:meth:`stage_stream`) -- so the batches
        alive at once are the ``depth`` in flight and the one being handed
        over. That is what lets a book larger than memory run at all.

        Args:
            prepared: The book, settled once on the host.
            groups: The book's rows grouped by the shape their program takes
                (:func:`~gaspatchio_jax.batching.grouped`), where the caller
                settled them first -- the stream does, to tell its sink
                before the first batch whether the book will arrive in its
                own order. Grouped here where None.
            budget_bytes: What the temporaries of one batch may reach.
            batch: How many policies to a batch, where the caller is pinning
                it rather than reading it off the program. The scaling report
                sweeps it; the invariance properties hold the answer against
                batches of one, of seven and of the whole book, and a size
                that can only be reached through the budget could not say
                *seven*.
            depth: How many batches are dispatched ahead of the one handed
                over; the device's own where None.
            returns: The nodes each program hands back, where the reader
                reads fewer than every node the run publishes -- a fold's
                columns (:meth:`compile_for`).
            on_dispatch: What the reader queues on the device beside each
                batch's program, the moment the batch is dispatched.

        Yields:
            Each batch's rows, values and findings, group by group.

        Raises:
            EngineRefusal: If a batch refuses while its axis is settled or its
                program built. Nothing has been published -- publication is
                :meth:`stage_complete`'s, reached only when every batch has
                run.
            ValueError: If ``depth`` is named and is neither 0 nor 1.

        """
        depth = checked_depth(depth)
        count = 0
        without_a_cache = unusable()
        if without_a_cache is not None:
            self.notes.append(f"compile cache: {without_a_cache}")
        if groups is None:
            groups = grouped(prepared.widths, prepared.inputs.rows)
        ahead: deque[tuple[Dispatched, object]] = deque()
        try:
            for group in groups:
                size, per_policy = (
                    (min(batch, max(int(group.size), 1)), 0)
                    if batch is not None
                    else self._batch_for(prepared, group, budget_bytes, returns)
                )
                self.per_policy = per_policy
                self.notes.append(
                    f"temporaries: {per_policy} bytes a policy, batches of {size}"
                    if per_policy
                    else f"batches of {size}, as the caller asked for"
                )
                for rows in chunks(group, size):
                    settled = self.stage_settle(prepared, rows)
                    program, _outcome = self._program_for(settled, returns)
                    dispatched = self.stage_dispatch(settled, program)
                    # The batch's inputs are let go of here: the runtime keeps
                    # a program's arguments for as long as the program runs.
                    del settled
                    queued = None if on_dispatch is None else on_dispatch(dispatched)
                    ahead.append((dispatched, queued))
                    del dispatched, queued
                    count += 1
                    while len(ahead) > depth:
                        # Yielded without a name: a local here would hold this
                        # batch's values while the next batch is computed.
                        yield self.stage_finish(*ahead.popleft())
        except EngineRefusal:
            # Met sizing a group, settling a batch or building its program --
            # the only steps here that refuse -- and raised after every batch
            # already dispatched has been handed over, as when each ran after
            # the one before it.
            yield from self._handed_over(ahead)
            raise
        yield from self._handed_over(ahead)
        self.notes.append(
            f"batching: {count} batches in {len(groups)} horizon "
            f"groups, {len(self.programs)} compilations"
        )

    def _handed_over(
        self, ahead: deque[tuple[Dispatched, object]]
    ) -> Iterator[Batched]:
        """Read back and hand over every batch still in flight, in dispatch order."""
        while ahead:
            yield self.stage_finish(*ahead.popleft())

    def stage_stream(
        self,
        prepared: Prepared,
        sink: Sink,
        *,
        budget_bytes: int = BUDGET_BYTES,
        batch: int | None = None,
        depth: int | None = None,
    ) -> Streamed:
        """Run every batch, and write each one's rows away the moment it finishes.

        Publication is all or nothing: each completed batch goes into an
        unpublished result beside the destination, and nothing is visible
        until completion publishes it. The sink is opened once the manifest is
        known -- after the first program is built, which is what says which
        columns there are -- and every batch is handed over with the book
        positions of its rows, so the sink, not this stage, puts the book back
        in its own order. A batch's values are let go of once it is written,
        before any batch after the next is dispatched: on a card, the next
        batch computes while this one is written (:meth:`stage_batches`).

        **The sink is told first whether the book will arrive in its own
        order.** The batching plan is settled before anything is computed:
        which policies share a program, and that the batches run group by
        group, each group front to back. Where that plan hands the book over
        in its own order and every policy has the same timeline on every
        axis -- levels 4 and 5 -- the sink is opened with that promise, and a
        file sink writes each batch straight into the result instead of
        staging it, to be read back and written a second time in the book's
        order at publication. Every other book is staged as before: one whose
        widths interleave, the jagged one, because it does not arrive in its
        own order, and one sorted by term because its rows widen batch by
        batch, and the row groups of a file written straight through are
        sized from the first batch's (:func:`~gaspatchio_jax.batching.one_timeline`).

        **A run already refused writes nothing more.** Once the findings so
        far refuse -- read exactly as completion will read them -- no result
        can be published, so the remaining batches run for their findings
        only. The report is still whole, and nothing is built or staged for a
        publication that cannot happen.

        **A fault building or writing a batch's columns is held, not raised.**
        A later batch may still refuse, and a refusal is the run's real
        answer. So the fault is kept, the remaining batches run for their
        findings only, and completion raises it only where nothing refused.

        Args:
            prepared: The book, settled once on the host.
            sink: Where each batch's rows go, and what publishes them.
            budget_bytes: What the temporaries of one batch may reach.
            batch: How many policies to a batch, where the caller pins it.
            depth: How many batches are dispatched ahead of the one written;
                the device's own where None.

        Returns:
            Every batch's findings, and the fault held, if there was one.

        Raises:
            EngineRefusal: If a batch refuses while its axis is settled or its
                program built. ``run`` abandons the sink, as it opened it.

        """
        host = findings_of(prepared.flags)
        groups = grouped(prepared.widths, prepared.inputs.rows)
        in_order = in_the_books_order(groups) and one_timeline(prepared.widths)
        found: list[Finding] = []
        fault: Exception | None = None
        refused = False
        opened = False
        for batched in self.stage_batches(
            prepared,
            groups=groups,
            budget_bytes=budget_bytes,
            batch=batch,
            depth=depth,
        ):
            found.extend(batched.findings)
            refused = refused or _refuses([*host, *found])
            if not refused and fault is None:
                try:
                    if not opened:
                        sink.open(
                            self.manifest_of(prepared.inputs, batched.columns),
                            in_order=in_order,
                        )
                        opened = True
                    sink.write_batch(
                        _published(batched.values, batched.dictionary, batched.columns),
                        rows=batched.rows,
                    )
                except Exception as error:  # noqa: BLE001 -- held for completion, which raises it unless a refusal is the answer
                    # Held without the batch it was building: the frames the
                    # fault passed through would otherwise keep that batch's
                    # values alive while every later batch runs.
                    traceback.clear_frames(error.__traceback__)
                    fault = error
            # Let go of this batch before the one after the next is
            # dispatched; the loop's own name would otherwise hold its values
            # through it.
            del batched
        return Streamed(findings=tuple(found), fault=fault)

    def _batch_for(
        self,
        prepared: Prepared,
        group: np.ndarray,
        budget_bytes: int,
        returns: frozenset[str] | None = None,
    ) -> tuple[int, int]:
        """Return the batch size one group takes, and what a policy costs in it.

        Measured rather than assumed: the program is built at the widest size
        the group could use, its own temporaries are read, and the size is
        taken from that. Where the two disagree the program is built again at
        the size that fits, which is one extra compilation per group and the
        only honest way to know a number the compiler decides. It is the
        program the batches will run -- returning what they return -- because
        a column that stays on the card is a buffer the compiler places.
        """
        if not group.size:
            return BATCH_GRID[0], 0
        widest = min(BATCH_GRID[-1], int(group.size))
        settled = self.stage_settle(prepared, group[:widest])
        program, _outcome = self._program_for(settled, returns)
        per_policy = bytes_per_policy(program.compiled, settled.count)
        return min(batch_size(per_policy, budget_bytes), int(group.size)), per_policy

    def _program_for(
        self, settled: Settled, returns: frozenset[str] | None = None
    ) -> tuple[Program, CacheOutcome]:
        """Return the compiled program for one batch's shape, building it once.

        Twice over: in this process, keyed by the shape, so a second batch of
        one group is handed the program the first batch built; and on disk,
        through jax's persistent cache, so a second *run* of a model in a new
        process is handed the executable the first run compiled. The two are
        reported apart, because a warm process says nothing about a cold
        cache. What the program returns is part of the shape: a fold's
        program and a publishing one over the same batch are two programs.
        """
        key = _shape_key(settled, returns)
        standing = self.programs.get(key)
        if standing is not None:
            reused = CacheOutcome(
                process_local=True, persistent=False, compile_seconds=0.0
            )
            self._note_compilation(settled, standing, reused, returns)
            return standing, reused
        built, outcome = self.compile_for(settled, returns)
        self.programs[key] = built
        self._note_compilation(settled, built, outcome, returns)
        return built, outcome

    def _note_compilation(
        self,
        settled: Settled,
        program: Program,
        outcome: CacheOutcome,
        returns: frozenset[str] | None = None,
    ) -> None:
        """Say what one batch's program cost and where it came from.

        **Three outcomes and three sentences**, because a reader cannot act
        on "cached". *Compiled* is the one that cost a compiler's seconds and
        will not again. *Reused in this process* is a second batch of one
        group and says nothing about whether anything was written down.
        *Loaded from the persistent cache* is the one that survived closing
        the laptop, and is the one an actuary feels on the second run of the
        morning. Told apart by what the sentence says, not by whether there
        is one.

        One line per distinct sentence: a hundred batches of one shape are one
        reuse, said once.
        """
        if outcome.process_local:
            reuse, cost = "reused in this process", ""
        elif outcome.persistent:
            reuse = "loaded from the persistent cache"
            cost = f", {outcome.compile_seconds:.2f}s"
        else:
            reuse, cost = "compiled", f", {outcome.compile_seconds:.2f}s"
        key = report_key(self.document, program.buckets, settled.count, returns)
        returning = (
            ""
            if returns is None
            else f", returning the {len(program.columns)} columns folded"
        )
        sentence = (
            f"compile cache: {reuse} for {key} ({settled.count} policies, "
            f"widths {list(program.buckets)}{returning}{cost})"
        )
        if sentence not in self.notes:
            self.notes.append(sentence)

    def stage_complete(
        self,
        streamed: Streamed,
        sink: Sink,
        prepared: Prepared | None = None,
    ) -> EngineResult:
        """Read every batch's findings together, and publish only if none refused.

        **Publication is the last thing that happens.** Every batch has run and
        been written away by the time this is reached, so a refusal here is a
        run that did all the work and published none of it -- which the
        closing sentence says. The sink puts the rows back in the book's own
        order as it publishes: a reader is owed the policies in the order they
        were handed in, and the order this engine computed them in is the
        order of the widths it grouped them by.

        Raises:
            EngineRefusal: If any check the trace carried caught a cell that
                is genuinely outside its domain.
            Exception: The fault held while a batch's columns were built or
                written, where nothing refused.

        """
        # The host stage's own findings in front of every batch's: they were
        # knowable first, over the whole book at once, and a reader reads a
        # report in the order things became knowable.
        found = merged_findings(
            [
                *(() if prepared is None else findings_of(prepared.flags)),
                *streamed.findings,
            ]
        )
        refusals = [one.refusal() for one in found if one.refuses]
        if refusals:
            # The sink is settled by ``run``'s own finally, once: a second
            # abandon here would be this stage undoing a decision the caller
            # owns, and a sink that counted them would see two.
            raise EngineRefusal(RunReport(refusals=tuple(refusals), notes=()))
        if streamed.fault is not None:
            raise streamed.fault
        notes = (*self.notes, *(one.sentence() for one in found if not one.refuses))
        return sink.publish(RunReport(refusals=(), notes=notes))

    def tree_of(self, record: NodeRecord) -> Mapping[str, Any] | None:
        """Return the operation tree one node's value comes out of, or None.

        Its own, for every node that has one. A **running state** has none:
        nothing in the model's source defines it and it reads nothing (§8.1),
        because it is where a compilation's account of its own balance begins.
        What answers it is the compilation that declares it -- the machine's
        own one-call tree -- so that is what comes back here, and the state's
        value is that call answered inside the state's own node.
        """
        if record.expr is not None or record.kind != STATE_KIND:
            return record.expr
        fingerprint = _state_owner(record, self.records, self.document)
        return machine_tree(fingerprint) if fingerprint is not None else None

    def lowered(self, tree: Mapping[str, Any], context: LoweringContext) -> Value:
        """Return the value one node's operation tree stands for, as its JSON.

        The door every node is lowered through. A tree is read and lowered one
        operation inside the next wherever it is not a chain of the operators
        written in steps (:meth:`lower`), so a tree nested deep enough in some
        other operation still reaches the end of Python's call depth. That is
        refused here, naming the node and how deep its tree goes, rather than
        handed to the reader as a traceback.

        Raises:
            DomainRefused: If the tree holds something this engine refuses,
                or nests deeper than this engine can lower it.

        """
        try:
            return self.lower(op_node_from_json(tree), context)
        except RecursionError:
            refused = _too_deep(tree)
        raise refused

    def lower(self, node: OpNode, context: LoweringContext) -> Value:
        """Return the value one operation tree stands for, under this run.

        **A chain of operators written in steps is lowered from one stack.**
        Where the operation at the root is one whose lowering is written in
        steps (``gaspatchio_jax.lowerings``), that lowering and every one of
        the same kind beneath it is driven by :meth:`_in_steps`, so a sum of
        any number of terms, a ``when`` nested in its ``otherwise`` any number
        of times or a long conjunction is lowered without one Python call per
        level. Anything else is lowered as its lowering asks.

        Raises:
            DomainRefused: If the tree holds something this engine refuses --
                which ``stage_inspect`` has already reported on, so reaching
                this is a defect in the agreement between the two.

        """
        stepped = _in_steps_at(node)
        if stepped is not None:
            return self._in_steps(*stepped, context)
        match node:
            case Col(name=name):
                return context.column(name)
            case Lit(value=value):
                return _literal(value, context)
            case BinOp(op=operator, left=left, right=right):
                return _dispatch(Call(operator, (left, right)), context)
            case Call():
                return _dispatch(node, context)
            case WhenThen(cond=condition, then=then, otherwise=otherwise):
                return _dispatch(
                    Call("when_then", (condition, then, otherwise)), context
                )
            case State(name=name):  # pragma: no cover -- refused at inspection
                raise DomainRefused(
                    what=f"the rollforward state {name!r} is not lowered here",
                    move="run this model on Polars until the scan lands",
                    clause="16.1",
                )
            case EngineNative(engine=engine):  # pragma: no cover -- as above
                raise DomainRefused(
                    what=f"a fragment of {engine}'s own expression language",
                    move=f"run this model on {engine}",
                    clause="8.2",
                )
        raise AssertionError(node)  # pragma: no cover -- the union above is closed

    def _in_steps(self, call: Call, steps: Steps, context: LoweringContext) -> Value:
        """Return one call's value, driving its steps and its operands' from a stack.

        Each lowering on the stack yields the operand it needs next. An operand
        that is itself a call written in steps goes on the stack; any other is
        lowered at once, as :meth:`lower` lowers it, and its value is sent
        back. So the operands are lowered, and every check raised, in exactly
        the order the lowerings would have lowered and raised them calling
        back into the plan one inside the next.
        """
        walks: list[Generator[OpNode, Value, Value]] = [steps(call, context)]
        sent: Value | None = None
        while True:
            walk = walks[-1]
            try:
                tree = next(walk) if sent is None else walk.send(sent)
            except StopIteration as done:
                walks.pop()
                answer: Value = done.value
                if not walks:
                    return answer
                sent = answer
                continue
            nested = _in_steps_at(tree)
            if nested is None:
                sent = self.lower(tree, context)
            else:
                walks.append(nested[1](nested[0], context))
                sent = None

    def returned_nodes(
        self, values: Mapping[str, Value], returns: frozenset[str] | None
    ) -> dict[str, str]:
        """Return the nodes a program hands back, and the column each stands under.

        Every node this run publishes where ``returns`` is None; otherwise
        exactly the nodes named, in the run's own order -- the columns a fold
        reads, and no others.

        Raises:
            AssertionError: If execution omitted a requested value.

        """
        if returns is None:
            return self.published_nodes(values)
        chosen = {
            node_id: self.records[node_id].column or node_id
            for node_id in self.order
            if node_id in returns and node_id in values
        }
        missing = sorted(returns - set(chosen))
        if missing:
            message = f"requested nodes were not computed: {missing}"
            raise AssertionError(message)
        return chosen

    def _per_period_doubles(self, values: Mapping[str, Value]) -> list[str]:
        """Return the final schema's per-period doubles, which a fold counts periods by.

        ``run_aggregated`` reports as its period count the longest timeline
        among the final frame's per-period doubles. A fold's program returns
        few of those columns, so the timelines are read off the axes they
        stand on instead, and these are the nodes whose axes those are.
        """
        return [
            node_id
            for node_id in self.order
            if self.records[node_id].kind in VALUE_BEARING
            and self.records[node_id].in_final_schema
            and node_id in values
            and values[node_id].shape == "list"
            and values[node_id].carrier == "f64"
        ]

    def published_nodes(self, values: Mapping[str, Value]) -> dict[str, str]:
        """Return every requested value node and its output column.

        Raises:
            AssertionError: If execution omitted a requested value.

        """
        every = self.scope == "every-node"
        requested = {
            node_id: (node_id if every else (self.records[node_id].column or node_id))
            for node_id in (self.records if every else self.order)
            if self.records[node_id].kind in VALUE_BEARING
            and (every or self.records[node_id].in_final_schema)
        }
        missing = sorted(set(requested) - set(values))
        if missing:
            message = f"requested value-bearing nodes were not computed: {missing}"
            raise AssertionError(message)
        return requested

    def manifest_of(
        self, inputs: PreparedInputs, carried: Mapping[str, str]
    ) -> ResultManifest:
        """Return what these columns are, for whoever compares them later."""
        return ResultManifest(
            scope="every-node" if self.scope == "every-node" else "final-schema",
            columns=dict(carried),
            dtypes={node_id: self.records[node_id].dtype for node_id in carried},
            row_identity=None,
            graph_fingerprint=str(self.document.get("graph_fingerprint") or ""),
            # The artifact's own input columns, in name order -- not the
            # book's columns. A digest over whatever the caller happened to
            # hand in says "two books" for two runs over one book that differ
            # only in a column nothing reads, and the whole point of the
            # digest is that a comparison can say whether two results are of
            # one book.
            inputs_digest=digest_of_inputs(
                inputs.frame if inputs.handed is None else inputs.handed,
                [requirement.column for requirement in self.inspection.required_inputs],
            ),
            producer=ENGINE_NAME,
            versions=engine_versions(),
        )


def engine_versions() -> dict[str, str]:
    """Return what produced a result, so a result that moves can be placed."""
    import hashlib  # noqa: PLC0415 -- only the manifest needs it
    from importlib.metadata import version  # noqa: PLC0415 -- as above
    from pathlib import Path  # noqa: PLC0415 -- as above

    import jax  # noqa: PLC0415 -- as above

    from gaspatchio import _internal  # noqa: PLC0415 -- as above

    extension = Path(_internal.__file__)
    return {
        "engine_version": version("gaspatchio-jax"),
        "jax_version": jax.__version__,
        "jaxlib_version": version("jaxlib"),
        "platform": platform.platform(),
        # The core package's version as installed, and the version its
        # extension was compiled as, under the keys the core's own manifests
        # use: one number in a release wheel, and two to be told apart in an
        # editable install over an extension built before the last bump.
        "core_version": version("gaspatchio"),
        "extension_version": _internal.__version__,
        # In the core's own form, "sha256:" and the digits, so this engine's
        # statement and the core's about one binary are one string.
        "extension_sha256": (
            f"{SHA256_PREFIX}{hashlib.sha256(extension.read_bytes()).hexdigest()}"
        ),
        # Which device computed the values. A fold on the laptop's CPU and one
        # on a card are this engine at these versions either way, and a total
        # that moved between the two moved with the device's arithmetic -- so
        # the record says which rather than leaving a reader to guess.
        "backend": jax.default_backend(),
        "device": ", ".join(sorted({one.device_kind for one in jax.devices()})),
    }


def _in_steps_at(node: OpNode) -> tuple[Call, Steps] | None:
    """Return the call one tree node is and the steps its lowering is written in.

    None for a node whose lowering is not written in steps, or whose table
    entry has been replaced by a lowering that is not -- which is then lowered
    as that entry says (:func:`_dispatch`).
    """
    match node:
        case BinOp(op=operator, left=left, right=right):
            call = Call(operator, (left, right))
        case WhenThen(cond=condition, then=then, otherwise=otherwise):
            call = Call("when_then", (condition, then, otherwise))
        case Call():
            call = node
        case _:
            return None
    found = LOWERINGS.get(call.name)
    steps = STEPS.get(found[0]) if found is not None else None
    return None if steps is None else (call, steps)


def _too_deep(tree: Mapping[str, Any]) -> DomainRefused:
    """Return the refusal of a tree nested past what this engine walks.

    One sentence wherever a walk over the tree runs out of Python's call
    depth -- the lowering, or the host's checks of arriving operands -- so a
    reader meets the same refusal on the same node whichever stage met it.
    """
    return DomainRefused(
        what=(
            f"this line's operation tree nests {_depth_of(tree)} operations "
            "deep, deeper than this engine lowers one operation inside another"
        ),
        move=(
            "split the line into named intermediate columns, or run this "
            "model on Polars"
        ),
        clause="11.1",
    )


def _depth_of(tree: Mapping[str, Any]) -> int:
    """Return how many operations deep one operation tree's JSON nests, by a stack.

    Every object carrying an ``op`` is one operation, wherever it sits among
    its parent's members, so the count needs no list of which member holds a
    child: it is the deepest path of operations from the root.
    """
    deepest = 0
    pending: list[tuple[object, int]] = [(tree, 0)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, dict):
            depth += 1 if "op" in item else 0
            deepest = max(deepest, depth)
            pending.extend((member, depth) for member in item.values())
        elif isinstance(item, list):
            pending.extend((member, depth) for member in item)
    return deepest


def _dispatch(call: Call, context: LoweringContext) -> Value:
    """Send one call to the lowering registered for its identifier."""
    found = LOWERINGS.get(call.name)
    if found is None:
        stated = refused_by_name(call.name)
        raise DomainRefused(
            what=(
                stated[0]
                if stated is not None
                else f"{call.name!r} has no lowering in this engine yet"
            ),
            move=(
                "run this model on Polars: this engine refuses this operation "
                "by name rather than answering a contract nobody has written"
                if stated is not None
                else "run this model on Polars until the identifier lands here"
            ),
            clause=stated[1] if stated is not None else "11.1",
        )
    return found[0](call, context)


# Where the producer's own inspector reports on the compiled rollforward
# facet, and under which check. A finding of that check about that facet is
# the same bytes this engine reads for itself.
_COMPILATIONS: Final = f"/facets/{FACET}/compilations/"
_STRUCTURE: Final = "portable_structure"


def _read_here(refusal: Refusal, document: Mapping[str, Any]) -> bool:
    """Return whether this engine takes its own reading of what a finding is about.

    One place and one facet. The producer's inspector reports on a compiled
    rollforward's body, and so does this engine: :func:`outside_the_subset`
    is 16.1's own list of conditions and it is the stricter of the two
    readings -- it requires the body's fields to be exactly the nine the
    subsection names, the points, the binding and the axes it fixes, and
    every increment's operation, arity, settings and target. So a structural
    finding about the same bytes is not a second fact about the model; it is
    the weaker reading of the one this engine has already taken, and passing
    it on would hand a reader a refusal whose next move -- export the
    artifact again -- produces the identical document.

    **What a reader is told instead** is this engine's own sentence, from the
    compilation node's status, naming what about the machine is outside the
    subset. Nothing goes unsaid: a body the producer would call incomplete
    and 16.1 admits runs, and one that 16.1 does not admit refuses here with
    the clause.
    """
    return (
        refusal.clause == _STRUCTURE
        and refusal.where.startswith(_COMPILATIONS)
        and body_of(document, refusal.where.removeprefix(_COMPILATIONS)) is not None
    )


def _state_owner(
    state: NodeRecord, records: Mapping[str, NodeRecord], document: Mapping[str, Any]
) -> str | None:
    """Resolve the unique declaring compilation, never the first name match.

    Section 16 forbids two compilations sharing a state reference because
    the state namespace cannot express which balance they mean.
    """
    owners = {
        fingerprint_of(record.expr)
        for record in records.values()
        if record.kind == ROLLFORWARD_KIND
        and declares(
            document, fingerprint_of(record.expr), state.node_id.partition(":")[2]
        )
    }
    return next(iter(owners)) if len(owners) == 1 else None


def _roots(document: Mapping[str, Any]) -> list[str]:
    """Select value nodes and state owners; never offer a state as a root."""
    records = _records(document)
    owners = {
        _state_owner(record, records, document)
        for record in records.values()
        if record.kind == STATE_KIND
    } - {None}
    return [
        record.node_id
        for record in records.values()
        if (record.kind in VALUE_BEARING and record.kind != STATE_KIND)
        or (record.kind == ROLLFORWARD_KIND and fingerprint_of(record.expr) in owners)
    ]


def _execution_order(
    document: Mapping[str, Any],
    records: Mapping[str, NodeRecord],
    reachable: Sequence[str],
    *,
    every_node: bool,
) -> tuple[str, ...]:
    """Place internal balances after their owner's external dependencies.

    The artifact's state leaves can precede any inputs. Their execution
    belongs at the compilation, including unconsulted states in every-node.
    """
    states = {
        record.node_id: _state_owner(record, records, document)
        for record in records.values()
        if record.kind == STATE_KIND and (every_node or record.node_id in reachable)
    }
    order = []
    for node_id in reachable:
        record = records[node_id]
        if record.kind == STATE_KIND:
            continue
        order.append(node_id)
        if record.kind == ROLLFORWARD_KIND:
            owner = fingerprint_of(record.expr)
            order.extend(
                state for state, fingerprint in states.items() if fingerprint == owner
            )
    # Unowned or ambiguous states must reach inspection and refuse, not vanish.
    order.extend(state for state in states if state not in order)
    return tuple(order)


def _records(document: Mapping[str, Any]) -> dict[str, NodeRecord]:
    """Return one record per node, with the document's arriving columns on each."""
    nodes = [node for node in document.get("nodes") or [] if isinstance(node, dict)]
    arriving = frozenset(
        str(node["column"])
        for node in nodes
        if node.get("kind") == "input" and isinstance(node.get("column"), str)
    )
    declared = {
        str(node["id"]): str(node.get("dtype"))
        for node in nodes
        if node.get("id") is not None
    }
    kinds = {
        str(node["id"]): str(node.get("kind"))
        for node in nodes
        if node.get("id") is not None
    }
    named = {
        str(node["id"]): node.get("column")
        for node in nodes
        if node.get("id") is not None
    }
    return {
        str(node["id"]): NodeRecord(
            node_id=str(node["id"]),
            column=node.get("column") if isinstance(node.get("column"), str) else None,
            version=node.get("version")
            if isinstance(node.get("version"), int)
            else None,
            kind=str(node.get("kind")),
            dtype=str(node.get("dtype")),
            shape=str(node.get("shape")),
            reads=tuple(str(read) for read in node.get("reads") or ()),
            expr=node.get("expr") if isinstance(node.get("expr"), dict) else None,
            in_final_schema=bool(node.get("in_final_schema")),
            arriving_columns=arriving,
            # The declared type of everything this node reads, keyed by the
            # name its formula reads it under. A capability's operand domain
            # is evaluated against these, which is what lets a status be a
            # statement about an invocation without a book and without
            # lowering anything.
            read_dtypes={
                str(named[read]): declared[read]
                for read in (str(one) for one in node.get("reads") or ())
                if read in declared and isinstance(named.get(read), str)
            },
            # And what kind of node each of those is, which is what the operand
            # condition is actually about: a column that arrived, or one a
            # calculation produced under the same name.
            read_kinds={
                str(named[read]): kinds[read]
                for read in (str(one) for one in node.get("reads") or ())
                if read in kinds and isinstance(named.get(read), str)
            },
        )
        for node in nodes
        if node.get("id") is not None
    }


# Where a key is named rather than written as an operand: 11.1.2's join states
# its key in the ``on`` attribute (its node reads the key all the same), and the
# two table reads carry theirs as operands.
_KEYED_BY_OPERAND: Final = ("lookup", "mortality.at")


def _key_only_columns(
    document: Mapping[str, Any],
    records: Mapping[str, NodeRecord],
    order: Sequence[str],
) -> frozenset[str]:
    """Return the columns this run reads **only** to select a row with.

    The door's null refusal is narrowed here, and only here. A null in a
    column something reads as a value has no representation in the trace and
    refuses with its row count. A null in a column every read of which is a *key*
    is different: 11.1.24 makes it a miss, answered by the read's own policy --
    the canonical NaN, a stated fill, or a refusal naming the key where the
    policy is raise. Level 4's guarded surrender-charge read is the case: the
    identifier is null on the plans that have no schedule, the read is behind
    a ``when_then`` that never selects it there, and a door that refused the
    book would refuse an ordinary model for a column it never used.

    A column read as a key *and* as a value is not in this set: one value use
    is enough for the null to need a representation the trace has not got.
    """
    keys: set[str] = set()
    values: set[str] = set()
    for node_id in order:
        tree = records[node_id].expr
        if isinstance(tree, dict):
            _reads_inside(tree, keys, values)
    del document
    return frozenset(keys - values)


def _reads_inside(tree: Mapping[str, Any], keys: set[str], values: set[str]) -> None:
    """Collect the columns one tree reads, keeping key reads apart from value ones."""
    kind = tree.get("op")
    name = str(tree.get("name") or "")
    if kind == "col":
        values.add(name)
        return
    written = [one for one in (tree.get("args") or ()) if isinstance(one, dict)]
    if kind == "call" and name in _KEYED_BY_OPERAND:
        for argument in written:
            if argument.get("op") == "col":
                keys.add(str(argument.get("name")))
            else:
                _reads_inside(argument, keys, values)
        return
    if kind == "call" and name == "join":
        keys |= set(join_key_sides((tree.get("attrs") or {}).get("on"))[0])
        return
    for argument in written:
        _reads_inside(argument, keys, values)
    for key in ("left", "right", "cond", "then", "otherwise"):
        child = tree.get(key)
        if isinstance(child, dict):
            _reads_inside(child, keys, values)


def _calls_inside(node: OpNode) -> list[Call]:
    """Return every call one operation tree names, outermost first."""
    found: list[Call] = []
    match node:
        case Call(args=args):
            found.append(node)
            for argument in args:
                found.extend(_calls_inside(argument))
        case BinOp(left=left, right=right):
            found.append(Call(node.op, (left, right)))
            found.extend(_calls_inside(left))
            found.extend(_calls_inside(right))
        case WhenThen(cond=condition, then=then, otherwise=otherwise):
            found.append(Call("when_then", (condition, then, otherwise)))
            for child in (condition, then, otherwise):
                found.extend(_calls_inside(child))
        case _:
            pass
    return found


def _axes_of(
    record: NodeRecord, values: Mapping[str, Value], produced: Value
) -> tuple[jax.Array, ...]:
    """Return every per-period axis one node stood on, as its active masks.

    Its operands' and its answer's. A node can stand on more than one -- a
    boundary sequence is one cell longer than the period values beside it --
    and a flag is held to the union of every axis whose rectangle it is the
    shape of, so all of them are offered and none is dropped on the way.
    """
    standing = [produced, *(values[read] for read in record.reads if read in values)]
    active: dict[int, jax.Array] = {}
    for value in standing:
        if value.shape == "list" and value.horizon is not None:
            # Keyed by the mask's own identity: two axes of one rectangle and
            # different period counts are two axes, and a key that was the
            # shape would keep one of them.
            active[id(value.horizon.active)] = value.horizon.active
    return tuple(active.values())


def _pre_axis(
    document: Mapping[str, Any],
    records: Mapping[str, NodeRecord],
    order: Sequence[str],
) -> tuple[str, ...]:
    """Return the ancestry of everything a per-period array's width is read from.

    Three sources, and all three are read. A ``projection_set``'s
    ``until_value`` where it is a column name, and a schedule recipe's
    ``until_value_column`` or ``inception_column`` -- the columns a horizon is
    *named* by. And, for every operation that reads the width of its own
    answer (``sizes_its_own_axis`` on its registration), everything that
    operation's node stands on: a calendar range is sized from its two
    endpoints, which are nowhere in a recipe.

    What comes back is those nodes and everything they stand on, in the run's
    own order. They are settled before the main pass because a width is not a
    number a compiled program can be handed.
    """
    named: set[str] = set()
    for entry in document.get("assumptions") or ():
        payload = entry.get("payload") if isinstance(entry, dict) else None
        if not isinstance(payload, dict):
            continue
        named |= {
            str(payload[key])
            for key in ("until_value_column", "inception_column")
            if isinstance(payload.get(key), str)
        }
    for record in records.values():
        tree = record.expr
        if not isinstance(tree, dict) or tree.get("name") != "projection_set":
            continue
        attrs = tree.get("attrs")
        stated = attrs.get("until_value") if isinstance(attrs, dict) else None
        if isinstance(stated, str):
            named.add(stated)
    wanted = _sizing_operands(records, order)
    for node_id in reversed(order):
        record = records[node_id]
        if record.column in named or node_id in wanted:
            wanted.add(node_id)
            wanted |= {read for read in record.reads if read in records}
    return tuple(node_id for node_id in order if node_id in wanted)


def _sizing_operands(
    records: Mapping[str, NodeRecord], order: Sequence[str]
) -> set[str]:
    """Return what every axis-sizing operation in this run stands on.

    The node's own reads rather than the operation's operands: an operand is
    an expression inside the node and what settles it is everything the node
    stands on, which is what the ancestry walk is given.
    """
    found: set[str] = set()
    for node_id in order:
        tree = records[node_id].expr
        if tree is None:
            continue
        if any(call.name in SIZINGS for call in _calls_inside(op_node_from_json(tree))):
            found |= {read for read in records[node_id].reads if read in records}
    return found


def _nulls_nothing_reads(inputs: pl.DataFrame, read: set[str]) -> list[str]:
    """Return a note per book column that carries nulls and that nothing reads.

    A null in a column a lowered node reads as a value refuses at the door. A
    null in a column nothing reads costs the run nothing and is reported
    rather than refused -- but it is reported, because a book carrying gaps in
    a column the model was meant to read under another name is a mistake
    worth seeing.
    """
    return [
        f"{name!r} carries {int(inputs[name].null_count())} values that are "
        "not there, and no node this run computed reads it"
        for name in inputs.columns
        if name not in read and inputs[name].null_count()
    ]


def _call_name(record: NodeRecord) -> str | None:
    """Return the identifier of a node whose whole tree is one call, or None."""
    tree = record.expr
    if tree is None or tree.get("op") != "call":
        return None
    name = tree.get("name")
    return str(name) if isinstance(name, str) else None


# The two kinds section 17 designs and does not emit, each with what a reader
# porting a model needs to hear rather than the bare word. Neither carries an
# operation tree at all -- what a second engine would have to run is the
# payload, and this preview states no portable semantics for either.
_REFUSED_KINDS: Final[dict[str, str]] = {
    "state_graph": (
        "a product whose states are the product, whose transitions are "
        "declared and simultaneous rather than ordered and applied; section "
        "17 designs the payload and nothing emits one, so there is no "
        "portable calculation here to run"
    ),
    "nested_valuation": (
        "a valuation struck inside the projection by an inner model; section "
        "17 designs the payload and nothing emits one, so there is no "
        "portable calculation here to run"
    ),
}


def _status_of(  # noqa: PLR0911 -- one return per kind of node this engine meets
    record: NodeRecord,
    records: Mapping[str, NodeRecord],
    document: Mapping[str, Any],
) -> NodeStatus:
    """Return what this engine does with one node, worst finding first."""
    if record.kind == "input":
        return NodeStatus(record.node_id, "lowered", None, "8.2")
    if record.kind == ROLLFORWARD_KIND:
        return _machine_status(record, document)
    if record.kind == STATE_KIND:
        # A running state is not a column and section 10 resolves no type for
        # it; what answers it is the machine that declares it, and 16.1 states
        # the type of the balance that machine carries. So the status is the
        # compilation's, read where the state's own record says nothing.
        if _state_owner(record, records, document) is None:
            return NodeStatus(
                record.node_id,
                "refused",
                (
                    "this state has no unique declaring compilation; "
                    "give each machine distinct state names"
                ),
                "16.1",
            )
        return NodeStatus(
            record.node_id,
            "lowered",
            "the internal balance of a compilation at its declared point",
            "16.1",
        )
    if record.kind in _REFUSED_KINDS:
        # Before the type, because neither of these is a column and section
        # 10 was never asked to resolve one: what a reader needs to hear is
        # that the payload behind the node is designed and not emitted, not
        # that its type is unknown.
        return NodeStatus(record.node_id, "refused", _REFUSED_KINDS[record.kind], "17")
    if record.dtype == "unknown":
        return NodeStatus(
            record.node_id,
            "refused",
            (
                "the producer resolved no type for this column, so there is "
                "nothing to hold its values in"
            ),
            "10",
        )
    if record.kind not in VALUE_BEARING:
        return NodeStatus(
            record.node_id,
            "refused",
            f"a node of kind {record.kind!r} is not lowered in this edition",
            "8.2",
        )
    tree = record.expr
    if tree is None:
        return NodeStatus(
            record.node_id,
            "refused",
            "a computed node carrying no operation tree",
            "8.2",
        )
    return _worst(_statuses_inside(tree, record, records), record)


def _machine_status(record: NodeRecord, document: Mapping[str, Any]) -> NodeStatus:
    """Return what this engine does with one compiled rollforward's own node.

    Read from the *body* and not from the call: the node's whole tree is the
    identifier and a fingerprint (§12.1), and everything that decides whether
    a machine is inside 16.1's executable subset travels in the facet. Asked
    here, so a machine this engine will not run refuses before the book is
    opened rather than half way through a trace.
    """
    tree = record.expr
    fingerprint = fingerprint_of(tree)
    body = body_of(document, fingerprint)
    if body is None:
        return NodeStatus(
            record.node_id,
            "refused",
            (
                f"this artifact carries no machine under {fingerprint}, and a "
                "fingerprint is an identity rather than a recipe"
            ),
            "16.1",
        )
    outside = outside_the_subset(body) or outside_the_types(body, record.read_dtypes)
    if outside is not None:
        return NodeStatus(record.node_id, "refused", outside, "16.1")
    return LOWERINGS[MACHINE][1].status_of(tree or {}, record)


def _statuses_inside(
    tree: Mapping[str, Any], record: NodeRecord, records: Mapping[str, NodeRecord]
) -> list[NodeStatus]:
    """Return one status per operation the tree names, in the tree's own order."""
    found: list[NodeStatus] = []
    kind = tree.get("op")
    if kind in ("call", "binop", "when_then"):
        name = str(tree.get("name") or tree.get("kind") or "when_then")
        registered = LOWERINGS.get(name)
        if registered is None:
            stated = refused_by_name(name)
            found.append(
                NodeStatus(
                    record.node_id,
                    "refused",
                    stated[0]
                    if stated is not None
                    else f"{name} has no lowering in this engine yet",
                    stated[1] if stated is not None else "11.1",
                )
            )
        else:
            found.append(registered[1].status_of(tree, record))
    elif kind in ("state", "engine_native"):
        found.append(
            NodeStatus(
                record.node_id,
                "refused",
                (
                    "a state reference"
                    if kind == "state"
                    else "one engine's own expression text"
                )
                + ", which this engine does not read",
                "8.2",
            )
        )
    for key in ("left", "right", "cond", "then", "otherwise"):
        child = tree.get(key)
        if isinstance(child, dict):
            found.extend(_statuses_inside(child, record, records))
    if str(tree.get("name") or "") in MACHINE_DOORS:
        # **A rollforward door's arguments are not its operands.** Section
        # 12.1 says outright that the three doors carry the *compilation's*
        # own operand run rather than a call's argument list -- which is why
        # a running state stands among them, and why nothing here lowers one.
        # What such a call can do is a fact about the machine in the facet,
        # and the status above is read from there.
        return found
    for argument in tree.get("args") or ():
        if isinstance(argument, dict):
            found.extend(_statuses_inside(argument, record, records))
    return found


# Worst first: a refusal beats an off-trace lowering beats a lowering.
_SEVERITY = {"refused": 2, "lowered-off-trace": 1, "lowered": 0}


def _worst(statuses: Sequence[NodeStatus], record: NodeRecord) -> NodeStatus:
    """Return the status a node takes from every operation inside it.

    A tree that names no operation at all -- one column standing for another
    -- is lowered: there is nothing in it this engine could fail to do.
    """
    if not statuses:
        return NodeStatus(record.node_id, "lowered", None, "8.2")
    return max(statuses, key=lambda status: _SEVERITY[status.status])


# What a tree refusal names where the reference producer answers the form:
# Polars has a lowering this engine has not.
_ON_POLARS: Final = "run this model on Polars, or keep the column out of the artifact"


def _refusal_from(status: NodeStatus, record: NodeRecord) -> Refusal:
    """Return the tree-group refusal one refused node's status stands for.

    **Polars is named only where Polars answers.** A declaration that refuses
    a form the reference producer refuses too -- an operand of a shape the
    clause does not state, a flag where a count is read -- names the move its
    registration states instead (:attr:`Capability.refused_alike`), because
    sending a reader to an engine that refuses the same line is no move at all.
    """
    return Refusal(
        group="tree",
        where=status.node_id,
        count=None,
        what=status.condition or "this engine has no lowering for it",
        move=_move_alike(status, record, record.expr) or _ON_POLARS,
        clause=status.clause,
    )


def _move_alike(
    status: NodeStatus, record: NodeRecord, tree: Mapping[str, Any] | None
) -> str | None:
    """Return the move the operation that refused names, where Polars refuses it too.

    Walks the tree in the order :func:`_statuses_inside` read it and asks the
    registration whose status is the refusal's own; None where no registration
    holds one, which leaves the Polars move standing.
    """
    if tree is None:
        return None
    kind = tree.get("op")
    name = str(tree.get("name") or tree.get("kind") or "when_then")
    if kind in ("call", "binop", "when_then"):
        registered = LOWERINGS.get(name)
        if registered is not None and registered[1].status_of(tree, record) == status:
            return registered[1].move_of(tree, record)
    children = [tree.get(key) for key in ("left", "right", "cond", "then", "otherwise")]
    if name not in MACHINE_DOORS:
        children.extend(tree.get("args") or ())
    for child in children:
        if isinstance(child, dict):
            found = _move_alike(status, record, child)
            if found is not None:
                return found
    return None


def _carried(series: pl.Series, dtype: str, dictionary: Dictionary) -> Value:
    """Return one arriving column as the trace sees it.

    A per-period column arrives jagged -- one list per policy, each its own
    length -- and leaves here rectangular: every row padded up to one bucket,
    with that policy's own count beside it. What fills the padding is the
    carrier's zero, and nothing reads it: every operation that could is masked
    to its own neutral element first (:mod:`gaspatchio_jax.horizon`).
    """
    carrier = cell_of(dtype)
    if carrier is None:  # pragma: no cover -- the validator refuses first
        message = f"no carrier for {dtype}"
        raise AssertionError(message)
    if not dtype.startswith("list["):
        return Value(_cells(series, carrier, dictionary), carrier, "scalar", dtype)
    written = series.to_list()
    lengths = [0 if row is None else len(row) for row in written]
    horizon = Horizon.over(jnp.asarray(lengths, dtype=np.int64))
    inner = series.dtype.inner if isinstance(series.dtype, pl.List) else series.dtype
    flat = _cells(
        pl.Series(
            series.name,
            [cell for row in written if row is not None for cell in row],
            dtype=inner,
        ),
        carrier,
        dictionary,
    )
    held = np.asarray(flat)
    rows = np.zeros((len(written), horizon.bucket), dtype=held.dtype)
    at = 0
    for row, length in enumerate(lengths):
        rows[row, :length] = held[at : at + length]
        at += length
    return Value(jnp.asarray(rows), carrier, "list", dtype, horizon)


def _cells(series: pl.Series, carrier: Carrier, dictionary: Dictionary) -> jax.Array:
    """Return one flat column of cells as the trace holds them."""
    if carrier == "code":
        return jnp.asarray(dictionary.codes_for_series(series))
    if carrier == "date":
        return jnp.asarray(np.asarray(series.to_physical().to_numpy(), dtype=np.int64))
    return jnp.asarray(series.to_numpy(), dtype=JNP_OF[carrier])


def _literal(
    value: LitScalar | tuple[LitSequenceMember, ...], context: LoweringContext
) -> Value:
    """Return one literal as a column of the run's own width."""
    if isinstance(value, tuple):
        raise DomainRefused(
            what="a sequence literal is not a value on its own",
            move="it belongs to the operation that names it, as its members",
            clause="12.1",
        )
    if isinstance(value, str):
        code = context.literal_code(value)
        return Value(
            jnp.full((context.rows,), code, dtype=JNP_OF["code"]),
            "code",
            "scalar",
            "str",
        )
    if isinstance(value, datetime.date):
        days = (value - _EPOCH).days
        return Value(
            jnp.full((context.rows,), days, dtype=JNP_OF["date"]),
            "date",
            "scalar",
            "date",
        )
    if isinstance(value, bool):
        return Value(
            jnp.full((context.rows,), value, dtype=JNP_OF["bool"]),
            "bool",
            "scalar",
            "bool",
        )
    if isinstance(value, int):
        if not INT64_MIN <= value <= INT64_MAX:
            raise DomainRefused(
                what=(
                    f"the integer literal {value} is outside the signed 64-bit "
                    "range a whole number is carried in"
                ),
                move=PAST_I64_LITERAL_MOVE,
                clause="10",
            )
        return Value(
            jnp.full((context.rows,), value, dtype=JNP_OF["i64"]),
            "i64",
            "scalar",
            "i64",
        )
    return Value(
        jnp.full((context.rows,), float(value), dtype=JNP_OF["f64"]),
        "f64",
        "scalar",
        "f64",
    )


# The suffix a node's absences are kept under, beside its value. Not a node
# id any document can carry: an id is the node's column and its version.
_ABSENT: Final = "\x00absent"


def absence_of(node_id: str) -> str:
    """Return the key a node's absences are kept under beside its value."""
    return f"{node_id}{_ABSENT}"


def _keep_absences(
    values: dict[str, Value], node_id: str, context: LoweringContext
) -> None:
    """Keep where a node's answer has no value beside it, as one more value.

    One per-policy truth value, so every stage that cuts, gathers or hands a
    batch's values to a program carries it as it carries any other.
    """
    if context.absent is not None:
        values[absence_of(node_id)] = Value(context.absent, "bool", "scalar", "bool")


def _settled(value: Value, record: NodeRecord) -> Value:
    """Return a node's value in the type its record declares, or refuse.

    The record is the authority and the arithmetic is not: section 11.1.26's
    stored indicator is the ordinary case -- a comparison assigned to a column
    is ``f64`` 1.0 and 0.0, the same truth value in a different representation
    -- and everything else has to agree outright.
    """
    wanted = cell_of(record.dtype)
    if wanted is None and record.kind == STATE_KIND and record.dtype == "unknown":
        # A running state is not a column of the model, so section 10 resolved
        # no type for it and the record says ``unknown`` -- which it is
        # entitled to. 16.1 states the type where 10 left it open: one
        # ``list[f64]`` of length T per policy, which is what the machine
        # handed back. The record is still the authority; it just has nothing
        # to say here.
        return value
    if wanted is None:
        raise DomainRefused(
            what=(
                f"{record.node_id} {RECORD_DISAGREES} {record.dtype}, which this "
                "engine holds no carrier for"
            ),
            move="run this model on Polars",
            clause="10",
        )
    if value.carrier == wanted:
        if value.unknown is not None:
            # A stored truth value holds no NaN: where a NaN left it unknown
            # (11.1.26) the producer stores a null, which this engine does not
            # carry. Named by the node, as every refusal raised while its
            # formula was lowered is: settling runs after that block closes.
            flag("comparison.unknown", value.unknown, where=record.node_id)
        return Value(value.array, wanted, value.shape, record.dtype, value.horizon)
    if value.carrier in ("bool", "i64") and wanted in ("f64", "i64"):
        # The node record is the authority on a node's type, not
        # what the arithmetic produced. The two cases that reach here are
        # 11.1.26's stored indicator -- a comparison assigned to a column is
        # 1.0 and 0.0, the same truth value in another representation -- and an
        # integer calculation the producer recorded as a double, which is the
        # widening ``carried_to`` checks at ±2^53.
        with about(record.node_id):
            carried = carried_to(value, wanted, clause="11.1.26")
        return Value(carried.array, wanted, value.shape, record.dtype, value.horizon)
    raise DomainRefused(
        what=(
            f"{record.node_id} {RECORD_DISAGREES} {record.dtype} and this "
            f"engine's lowering produced a {value.carrier} value"
        ),
        move=_who_to_tell(value.carrier, wanted),
        clause="8.2",
    )


# The carriers a widening runs between, in the direction it widens. Where the
# engine's answer is the *wider* of the two, the engine is what moved and the
# engine's package is who to tell; where it is not, the two disagree about
# what the operation answers at all and neither side can be named alone.
_WIDER_THAN: Final[dict[str, frozenset[str]]] = {
    "f64": frozenset({"i64", "bool"}),
    "i64": frozenset({"bool"}),
}


def _who_to_tell(produced: str, declared: str) -> str:
    """Return the next move for a record disagreement, naming the side it knows.

    An engine that widened a whole number into a double is the side that
    moved, and saying "report it against the record" there sends a reader to
    argue with the producer about the engine's own arithmetic. Where neither
    carrier is a widening of the other, the two disagree about what the
    operation answers at all, and which of them is wrong is not something
    either side can settle from here -- so both are named.
    """
    if declared in _WIDER_THAN.get(produced, frozenset()):
        return (
            "report it against this engine's package: the record carries the "
            "narrower type and this engine widened it, so what moved is here"
        )
    return (
        "report the disagreement against this engine's package and against "
        "the producer that wrote the record: one of the two is wrong about "
        "what this operation answers, and the record is what a second reader "
        "goes by"
    )


def _host_value(
    record: NodeRecord, prepared: PreparedInputs, dictionary: Dictionary
) -> Value:
    """Return the value one off-trace operation produces, computed on the host."""
    from .lowerings import conversion  # noqa: PLC0415 -- only the host stage needs it

    return conversion.on_the_host(record, prepared, dictionary)


def _published(
    values: dict[str, Value], dictionary: Dictionary, columns: Mapping[str, str]
) -> pl.DataFrame:
    """Return the values as one frame, in the columns the manifest names.

    Each value is taken out of ``values`` as its column is built, so the
    buffer it stood in is let go of the moment it has been copied out. A batch
    is then never held twice over -- once as the program's values and once as
    the frame built from them -- which on a laptop is half of a batch's peak.
    """
    series = [
        _with_absences(
            _as_series(column, values.pop(node_id), dictionary),
            values.pop(absence_of(node_id), None),
        )
        for node_id, column in columns.items()
    ]
    return pl.DataFrame(series) if series else pl.DataFrame(schema={})


def _with_absences(series: pl.Series, absent: Value | None) -> pl.Series:
    """Return a published column with a null wherever its node has no value."""
    if absent is None:
        return series
    rows = np.flatnonzero(np.asarray(absent.array))
    if rows.size == 0:
        return series
    return series.scatter(rows, None)


def _refuses(found: Sequence[Finding]) -> bool:
    """Return whether these findings refuse the run, read as completion reads them.

    Merged first, exactly as :meth:`ExecutionPlan.stage_complete` merges them:
    whether a check refuses is settled by its first finding, so a verdict on
    the findings so far is the verdict completion will reach.
    """
    return any(one.refuses for one in merged_findings(found))


def _rows_of(values: Mapping[str, Value], rows: np.ndarray) -> dict[str, Value]:
    """Return every settled value cut to the policies of one batch.

    A per-period value is cut twice: to the rows, and back to the width those
    rows need. The policies of a batch are the policies whose timelines round
    up to one width, so the second cut takes the padding the rest of the book
    put there and nothing a policy of this batch wrote.

    **One compiled gather for the whole batch, not one per column.** Cut a
    column at a time, every column paid a dispatch, a fresh copy of the row
    positions onto the device and the bounds arithmetic on those positions:
    32 ms of a 53 ms settle per batch on the T4 (measured 2026-09-24), for nothing
    but moving cells. The cells are the same either way; only the number of
    trips differs. The widths are settled on the host first, because a width
    is the shape of an answer and a compiled program is built for one shape.
    """
    lengths = {
        node_id: value.horizon.lengths[rows]
        for node_id, value in values.items()
        if value.shape == "list" and value.horizon is not None
    }
    widths = tuple(
        _width_of(lengths[node_id]) if node_id in lengths else None
        for node_id in values
    )
    arrays = _gathered(tuple(value.array for value in values.values()), rows, widths)
    cut: dict[str, Value] = {}
    for (node_id, value), array, width in zip(
        values.items(), arrays, widths, strict=True
    ):
        if width is None:
            cut[node_id] = replace(value, array=array)
            continue
        counts = lengths[node_id]
        cut[node_id] = replace(
            value,
            array=array,
            horizon=Horizon.over(
                jnp.asarray(counts, dtype=np.int64), bucket=width, host=counts
            ),
        )
    return cut


def _host_widths(
    sizing: Sequence[tuple[str, Call]],
    widths: Mapping[str, np.ndarray],
    rows: np.ndarray,
) -> dict[str, np.ndarray]:
    """Return each axis-sizing call's cell counts for one batch, as the host holds them.

    Cut from what preparation counted over the whole book, and keyed as it
    keys them: by the node and the operation's name. **A key two calls of one
    node share is left out.** Preparation keeps one count under such a key,
    so it would stand for either call; handed to the wrong one it would be a
    timeline the model never laid. A call left out reads its count back off
    the device, which is slower and right. So does a sizing that refused,
    which preparation never counted.
    """
    keys = Counter(f"{node_id}/{call.name}" for node_id, call in sizing)
    return {
        key: widths[key][rows]
        for key, many in keys.items()
        if many == 1 and key in widths
    }


def _width_of(counts: np.ndarray) -> int:
    """Return the width one batch's own period counts round up to."""
    return bucket_of(int(counts.max())) if counts.size else BUCKETS[0]


@partial(jax.jit, static_argnums=2)
def _gathered(
    arrays: tuple[jax.Array, ...], rows: np.ndarray, widths: tuple[int | None, ...]
) -> tuple[jax.Array, ...]:
    """Return each array's rows, a per-period one cut back to its width."""
    return tuple(
        array[rows] if width is None else array[rows, :width]
        for array, width in zip(arrays, widths, strict=True)
    )


def _shape_key(
    settled: Settled, returns: frozenset[str] | None = None
) -> tuple[object, ...]:
    """Return what makes two batches one compilation.

    How many policies, every axis's width and period counts' agreement
    pattern, and what the program hands back. Not the counts themselves:
    they are arguments, which is the whole point of compiling once for a
    group.
    """
    axes = _axes_in(settled.values)
    return (
        None if returns is None else tuple(sorted(returns)),
        settled.count,
        tuple(axis.bucket for axis in axes),
        tuple(
            bool(np.array_equal(axes[left].lengths, axes[right].lengths))
            for left in range(len(axes))
            for right in range(left + 1, len(axes))
        ),
    )


def _axes_in(values: Mapping[str, Value]) -> list[Horizon]:
    """Return every distinct per-period axis these values stand on.

    By the identity of the axis object, not by its contents: two axes of one
    rectangle carrying different period counts are two axes, and keying on
    the shape would keep one of them.
    """
    found: dict[int, Horizon] = {}
    for value in values.values():
        if value.horizon is not None:
            found.setdefault(id(value.horizon), value.horizon)
    return list(found.values())


def _counts_of(dispatched: Dispatched, at: int, count: jax.Array) -> np.ndarray:
    """Return one returned axis's period counts, on the host.

    The batch's own, as it was settled, where the axis is one it was handed
    in on; read back off the device only where the program laid the axis
    itself. That read waits for this batch's program and nothing after it.
    """
    source = dispatched.program.sources[at]
    if source is not None:
        return dispatched.lengths[source]
    return np.asarray(count, dtype=np.int64)


def _source_of(axis: Horizon, standing: Sequence[Horizon]) -> int | None:
    """Return which axis a program was handed one of its answers' axes as, if any.

    By identity: an answer standing on an axis the batch was handed in on
    has that batch's own period counts, which the host already holds. An
    axis the program laid itself -- a compiled rollforward's, sized from the
    schedule -- is none of them.
    """
    return next((at for at, one in enumerate(standing) if one is axis), None)


def _on(axes: Sequence[Horizon], at: int | None) -> Horizon | None:
    """Return the axis one value stands on, or None where it is per-policy."""
    return None if at is None else axes[at]


def _axis_index(value: Value, axes: Sequence[Horizon]) -> int | None:
    """Return which of these axes one value stands on, or None for per-policy."""
    if value.horizon is None:
        return None
    for at, axis in enumerate(axes):
        if axis is value.horizon:
            return at
    message = f"a per-period {value.dtype} value stands on no axis of this run"
    raise AssertionError(message)  # pragma: no cover -- a defect, not a refusal


def _as_series(name: str, value: Value, dictionary: Dictionary) -> pl.Series:
    """Return one traced column as the Polars column its record declares.

    A per-period column is cut back to each policy's own periods on the way
    out: the bucket is this engine's business and a reader is owed the
    timeline the model projected, not the width one compilation was padded
    to.
    """
    if value.carrier in {"f64", "i64", "bool", "date"}:
        # This is the existing device-to-host boundary, after computation.
        # Keep the cells in arrays: rebuilding them through Python rows
        # dominates publication and helps neither CPU nor GPU execution. A
        # date is its count of days, which is what Polars keeps a date as, so
        # it takes the same road and is named a date only at the end -- by a
        # strict cast, which refuses a count no date can hold rather than
        # wrapping it.
        cells = np.asarray(value.array)
        dtype = _POLARS_OF[value.carrier]
        if value.shape == "scalar":
            return pl.Series(name, cells).cast(dtype)
        return _per_period(name, cells, periods_of(value).lengths).cast(pl.List(dtype))
    if value.shape == "list":
        horizon = periods_of(value)
        rows = [
            _cells_out(row, value.carrier, dictionary) for row in trim(value, horizon)
        ]
        return pl.Series(name, rows, dtype=pl.List(_POLARS_OF[value.carrier]))
    return pl.Series(
        name,
        _cells_out(np.asarray(value.array), value.carrier, dictionary),
        dtype=_POLARS_OF[value.carrier],
    )


def _per_period(name: str, cells: np.ndarray, lengths: np.ndarray) -> pl.Series:
    """Return a padded rectangle as the list column of each policy's own periods.

    One pass takes the cells inside each policy's horizon, in row order; the
    offsets their lengths give then make them an Arrow list, which Polars
    takes without copying. Through a fixed-width array, a list and a slice
    by each row's length, it was three passes over every cell of the batch,
    for a column that is most of what a batch publishes (level 4: 63 of its
    128 columns are per-period doubles).
    """
    inside = np.arange(cells.shape[1])[None, :] < lengths[:, None]
    offsets = np.concatenate(([0], np.cumsum(lengths, dtype=np.int64)))
    listed = pa.LargeListArray.from_arrays(pa.array(offsets), pa.array(cells[inside]))
    return pl.Series(name, listed)


# What each carrier is published as, in section 10's own five types.
_POLARS_OF: dict[str, pl.DataType] = {
    "code": pl.String(),
    "date": pl.Date(),
    "bool": pl.Boolean(),
    "i64": pl.Int64(),
    "f64": pl.Float64(),
}


def _cells_out(cells: np.ndarray, carrier: str, dictionary: Dictionary) -> list[object]:
    """Return one row of cells as the values a reader gets back."""
    if carrier == "code":
        return list(dictionary.texts_of(cells))
    if carrier == "date":
        # Through numpy's own object form, which is ``datetime.date``: a
        # ``datetime64`` inside a list column is not a cell Polars builds a
        # date out of, and the scalar path would take it only by accident.
        return list(cells.astype("datetime64[D]").astype(object))
    return list(cells)
