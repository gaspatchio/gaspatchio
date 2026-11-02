# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Data models for calculation graph components.

This module provides Pydantic models for type-safe graph construction.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePath
from typing import Any, Final, Literal, Self

from pydantic import BaseModel, Field

from gaspatchio._beside import local_modules
from gaspatchio._semantic.ir import EngineName, OpNode
from gaspatchio._shape import Shape
from gaspatchio._source import SourceSpan
from gaspatchio.frame.calculations import SelectionKind
from gaspatchio.frame.graph._model_files import file_sha, revision_of, stamped_file
from gaspatchio.frame.graph.edges import EdgeSubtype, EdgeType, ReadWay
from gaspatchio.frame.graph.graph_utils import relative_to_root
from gaspatchio.frame.graph.policies import SelectedPolicy
from gaspatchio.frame.graph.portfolio import PortfolioFold

# What identifies one node in the calculation graph.
#
# A computed node is one *definition* of a column, so its id carries the
# ordinal that distinguishes it from the column's other definitions:
# ``"policies_in_force@2"`` is the second write of that name and a
# different node from ``"policies_in_force@1"``. An input node is the
# column as it arrived, which nothing on the frame defines, so it is
# unversioned and its id is the bare column name.
#
# Never split an id back apart to recover the column: a Polars column name
# may itself contain an ``@``. Read ``NodeData.column`` instead, which is
# what it is there for.
NodeId = str

# The two id namespaces the format reserves, and a column name may not be
# produced into either. ``state:account_value@eop`` is one running state of
# a rollforward and ``rollforward:7be2aa108f31`` is one whole compilation;
# neither is a column, which is why a node in one carries ``column: None``.
# Written here once so that whatever mints an id and whatever reads a name
# back out of one are looking at the same string.
STATE_NAMESPACE: str = "state:"
ROLLFORWARD_NAMESPACE: str = "rollforward:"

# The third reserved namespace: one step that chose which rows the model
# values, ``selection:1`` for the first. A selection step is not a node and
# defines no column; it is an entry of the document's ``selection`` list, and
# its id is what a change report and a refusal name it by. Positional within
# one artifact, as a node's ordinal is.
SELECTION_NAMESPACE: str = "selection:"

# The one call a compilation's operation tree is, and the attribute on it
# carrying the compiled artefact's own published identity. Written here for
# the same reason as the namespaces above: whatever mints the call and
# whatever reads the fingerprint back off it must be looking at the same two
# strings, and they are minted in one module and read in another.
ROLLFORWARD_CALL: str = "rollforward"
ROLLFORWARD_FINGERPRINT_ATTR: str = "fingerprint"

# The attribute beside it naming the schedule the machine runs on, by that
# schedule's own ``source_sha()``. The fingerprint is the machine alone and
# leaves the schedule out, so every rollforward call states the
# schedule as the data it is -- which is how a schedule change still moves
# ``graph_fingerprint`` -- and the pair is what a compilation is resolved by.
ROLLFORWARD_SCHEDULE_ATTR: str = "schedule"

# The two attributes a state extraction carries beside that fingerprint: which
# running state it pulls out, and the point in the period it reads it at.
# Together they spell the state reference -- ``fund`` and ``eop`` make
# ``fund@eop`` -- which is the name section 16 gives a running state
# everywhere it is not an id, an increment's ``target`` included.
ROLLFORWARD_STATE_ATTR: str = "state"
ROLLFORWARD_POINT_ATTR: str = "point"


@dataclass(frozen=True, slots=True)
class SelectionStep:
    """One row-selecting step, bound into the graph like a formula's reads.

    ``tree`` is the predicate's op-tree for a filter, and the ``join`` call
    (key, join type, right side's content identity) for a semi or anti join.
    ``reads`` are the nodes the step's column references bound to when it
    was taken -- the definition each column held at that point in the log --
    in the order the tree names them, as a node's ``reads`` are. ``id`` is
    ``selection:<k>``, counting from 1 in the order the model took the steps.
    """

    id: str
    kind: SelectionKind
    tree: OpNode
    reads: tuple[NodeId, ...]
    source: SourceSpan | None


class NodeType(str, Enum):
    """What kind of account a node gives of its column.

    ``COMPUTED`` is a calculation the frame recorded, ``INPUT`` a value
    that arrived rather than being derived -- a model-point field, or a
    column of values injected wholesale. ``HOLE`` is the absence of both,
    and it is minted at either of two places: a column that is on the
    frame with no account of itself anywhere in the log, or a name a
    record *reads* that no frame ever held -- not in the arriving data,
    not in the schema, defined by no calculation. It is a node type
    rather than a flag on the data so that a reader of the exported graph
    tells the three apart by the same field, without having to know which
    combination of absent fields means "unexplained".

    Two members are not accounts of a column at all, and they are here
    because a compiled rollforward is not one either. ``ROLLFORWARD`` is
    one whole compilation -- the state machine the framework escalates to
    when a within-period charge depends on the running balance -- standing
    as one node that every extraction from it reads. ``STATE`` is one of
    that compilation's running states: the account value the charge is
    struck against, which no column of the model holds and which the
    artifact could not otherwise point at. Both live in reserved id
    namespaces and carry ``column: None``, because neither is a column.
    """

    INPUT = "input"
    COMPUTED = "computed"
    HOLE = "hole"
    ROLLFORWARD = "rollforward"
    STATE = "state"


# What the frame saw of a column it cannot account for. Each value names
# evidence the frame met, never an inference about why: a reason it could
# not substantiate would be a guess wearing a type.
HoleReason = Literal["unrecorded", "overwritten", "rebuilt"]
"""What the frame saw of a column it cannot account for.

``"unrecorded"``: nothing accounts for the column, and the frame cannot
see why. A column a Polars step added outside the frame's own operations
and a gap in the framework's own logging leave the same evidence behind, so
the reason claims nothing more. A name a calculation reads that no frame
ever held is ``"unrecorded"`` too.

``"overwritten"``: a column the frame had accounted for -- a calculation
it logged, or a column the data arrived with -- that a write straight into
the query plan then replaced. The frame saw the write, and read off the
plan which columns it defined.

``"rebuilt"``: a column the frame arrived with whose values a calculation
on another frame produced. The frame was built over that frame's collected
values with ``ActuarialFrame(df)``, while the values were still held, rather
than with ``ActuarialFrame(df, continue_from=af)``, which keeps the
calculation. It is a hole while the frame holds the column with no account
of it, and behind any calculation that read it before the frame calculated
it again or dropped it; one nothing read stops being a hole once the frame
accounts for the column again or drops it, as any other hole does.

What each cannot see:

- ``"overwritten"`` sees writes to ``af._df``. A write that goes around
  even that, such as ``object.__setattr__`` on the frame's own storage, and
  an edit to the calculation log are not seen. A write that reorders,
  filters or moves whole rows defines no column and is not reported, and
  neither is one that hands a column back unchanged, only marks it sorted
  or casts it to the type it has. A plan rebuilt in the shape of the one it
  replaces is compared with it on its steps, its text, the memory of every
  table it scans and the values and parameters of every expression
  Polars' reader can show; a difference inside one it cannot show and the
  text does not print -- which table an assumption lookup reads, a cut's
  breaks, two Python functions printed alike -- is not seen. Where the
  frame cannot read which columns a write defined, it reports every column
  it accounted for that the plan still holds, rather than none.
- ``"rebuilt"`` sees only shared memory. Values that were filtered,
  sorted, joined, cast, rechunked, sliced, or written out and read back
  arrive as data, and so do values nobody held any longer when the frame
  was built -- the other frame had moved on and the DataFrame its collect
  handed back had been let go -- values from another process, and a
  one-row column, which Polars holds as a single value and copies whenever
  it is read. A column whose values are the data's own, because a
  calculation copied an input unchanged, is never reported, even where
  the model then dropped the input.
- ``"unrecorded"`` sees names the frame holds that nothing accounts for. A
  frame told which columns the policy data carried
  (``GraphExporter(af, data_columns=...)``, which ``gspio calc-graph``
  does, and every frame a batch runner or a scenario plan built while it
  ran the model) also reports a name the frame arrived holding that the
  data never had.

A hole the frame arrived holding -- a ``"rebuilt"`` one, and an
``"unrecorded"`` name the data never had -- carries a content stamp of the
column as it arrived (``HoleAccount.content``): the frame cannot say what
made those values, and it can say what they were, so an edit to a file the
setup joined moves the model's identity. An ``"overwritten"`` hole and a
name no frame held carry none, because no values of theirs are in hand.
"""


@dataclass(frozen=True, slots=True)
class HoleAccount:
    """What the fold saw of one hole: its reason, and what it can say beside it.

    Held beside the graph rather than on the node. The node is what the
    document writes for the column, and the reason reaches the document
    through its holes section, once per name; the rest is what the hint a
    reader is handed is made from.

    Attributes:
        reason: The evidence the frame met.
        replaced: For an overwritten hole, the node the write replaced: the
            definition the frame had logged, or the column as it arrived.
        readable: For an overwritten hole, False where the frame could not
            read which columns the write defined, and reported every column
            it accounted for that the plan still held.
        rescanned: For an overwritten hole, True where the plan written was
            nothing but a table in memory: values handed over in place of a
            plan.
        calculated_by: For a rebuilt hole, the definition on the other frame
            that produced the values, as that frame's own graph names it.
        calculated_at: Where that definition was written, as ``file:line``,
            or None where it could not be found.
        content: For a hole the frame arrived holding, the content stamp of
            the column as it arrived (``"sha256:..."``, the specification's
            content grammar over that one column, read as a book is read);
            None for every other hole, and where the values could not be
            read.

    """

    reason: HoleReason
    replaced: NodeId | None = None
    readable: bool = True
    rescanned: bool = False
    calculated_by: str | None = None
    calculated_at: str | None = None
    content: str | None = None


class Provenance(str, Enum):
    """Where one node's values came from, or which frame operation defined them.

    One field and one question. The first three members answer it for a
    column that arrived: the policy data, an assumption base, or a whole
    column handed to the frame at a known line
    (``af.simulated_deaths = pl.Series(...)``) -- data rather than a
    formula, but *located* data, which is strictly more than a
    spreadsheet's paste-as-values tells a reviewer. ``CONTINUATION`` is
    that same handing-over through an explicit re-entry, and it is a
    member of its own because where the values came back in is the
    distinction a reviewer is entitled to.

    The rest are the frame's own operations that record what they define,
    and they answer the question for a column the frame defined: a plain
    assignment, a column a single call
    minted as a batch whatever the number of columns it defined, a
    rename, the right side of a join, the projection timeline's own
    configuration, a date derivation, or a compiled rollforward's own
    within-period bookkeeping.

    Every member names a place the fold can point at, and there is
    deliberately no member for "somewhere, presumably". A column nothing
    accounts for is a hole, whose account of itself is that it has none;
    giving it a provenance would dress a guess as a positive claim about
    where a number came from.
    """

    MODEL_POINTS = "model_points"
    ASSUMPTIONS = "assumptions"
    INJECTED = "injected"
    CONTINUATION = "continuation"
    ASSIGNMENT = "assignment"
    BATCH = "batch"
    RENAME = "rename"
    JOIN = "join"
    PROJECTION = "projection"
    DATE = "date"
    ROLLFORWARD = "rollforward"


# The operations a compiled rollforward is built out of, closed at ten and
# spelled as the compiler spells them. The artifact publishes these names, so
# the list is a wire vocabulary rather than an implementation detail: renaming
# one in ``rollforward/_ops.py`` is a format change carrying a change-log
# line, which is the cost of not keeping a second vocabulary free to drift
# from the operations it would translate. Written out here rather than derived
# from that module, so that what the artifact promises is a list a reader can
# see, and so that a producer meeting an operation not on it says nothing
# rather than inventing an entry.
ROLLFORWARD_OPERATIONS: tuple[str, ...] = (
    "Add",
    "Subtract",
    "Charge",
    "Grow",
    "GrowCapped",
    "DeductNAR",
    "Ratchet",
    "Floor",
    "Round",
    "Apply",
)


class Increment(BaseModel):
    """One movement of one compiled rollforward's running balance.

    A summary and not the machine: what moved, in what order, under what
    name, and onto which balance. The expression behind a movement, its
    rounding, its stopping conditions and the opening value of any state are
    the compiled state machine, and they travel in the rollforward IR facet
    that the ``executable`` profile carries and the ``audit`` profile does
    not. The **amount** is neither: it is a value like any other value in the
    document, and it sits beside the rest of them in ``movements``, keyed by
    the kernel's own name for the step this entry's ``ordinal`` numbers.

    No per-increment digest is minted. An increment's identity is its
    position in its compilation -- the pair (the compilation's
    ``fingerprint``, this ``ordinal``) -- because the compiler already hashes
    the whole state machine once, and a second digest taken under the
    artifact's own grammar would be a second reading of one structure, free
    to disagree with the first.
    """

    ordinal: int = Field(
        description=(
            "Which movement this is, counting from 1 in the order the "
            "increments apply, which is the order the array holds them in. "
            "The array order is what is normative; this restates it so a "
            "reader can cite one movement, and the validator checks the "
            "restatement against the position it stands in."
        )
    )
    label: str | None = Field(
        description=(
            "The name the model's author gave this increment, or null where "
            "the operation carries no field for one. A label is an interface "
            "rather than a caption -- a model reads an increment back by "
            "name -- and it is inside the compilation's own identity, so two "
            "compilations differing only in a label are two compilations."
        )
    )
    operation: str = Field(
        description=(
            "What kind of movement this is, in the compiler's own operation "
            "vocabulary, closed at the ten names of ROLLFORWARD_OPERATIONS."
        )
    )
    target: str = Field(
        description=(
            "Which running balance the movement lands on, as the state "
            "reference ('av@eop') and not the reserved id built around it."
        )
    )
    reads_running_balance: bool | None = Field(
        description=(
            "Whether this increment's amount depends on the balance it is "
            "changing -- the framework's own escalation criterion, shown per "
            "movement rather than claimed of the whole. Null where the "
            "producer cannot classify the expression, carrying the meaning "
            "null carries everywhere else: the producer looked and cannot "
            "say, rather than a guess telling a reviewer a state machine was "
            "justified when nothing checked."
        )
    )


class Extraction(BaseModel):
    """One running balance of a compilation, as the column that materialises it.

    A line assigning ``compiled.expr_for("fund")`` writes the fund's running
    balance onto the frame. The two are one quantity asked about twice --
    the compilation carries the balance, the column is where the model reads
    it back out -- and until this record existed the only thing tying them
    together was the formula's own text, which no consumer may parse.

    It is the *column* that carries this and never the state. A state is not
    a column: nothing on the frame holds it, and a compilation's balance may
    be materialised by no column at all or by two, so a field on the state
    naming its column would have a cardinality the state cannot honour.
    """

    compilation: NodeId = Field(
        description=(
            "The id of the compiled rollforward node this column extracts "
            "from. It is also one of this node's `reads`, and the validator "
            "holds the two records to each other: a column naming a "
            "compilation it does not read has an account of itself that its "
            "own edges do not support."
        )
    )
    state: str = Field(
        description=(
            "Which running balance this column materialises, as the state "
            "reference ('fund@eop') and not the reserved id built around "
            "it -- the same spelling an increment's `target` carries, for "
            "the same reason. The state before the '@' is one the named "
            "compilation declares, which is the validator's second reading."
        )
    )


class NodeData(BaseModel):
    """Data associated with a graph node."""

    id: NodeId = Field(
        description="This node's own id: 'column@ordinal', or a bare column name"
    )
    column: str | None = Field(
        description=(
            "The column this node defines or supplies. None only in a "
            "reserved id namespace, where the node is not an account of a "
            "column at all: one compiled rollforward, or one of its running "
            "states."
        ),
    )
    version: int | None = Field(
        default=None,
        description=(
            "Which definition of `column` this node is, counting from 1 -- the "
            "same ordinal its id carries, stated as a number so a reader never "
            "has to split the id to reach it. None on a node nothing on the "
            "frame defined: an arriving column, or a column nothing accounts "
            "for."
        ),
    )
    reads: tuple[NodeId, ...] = Field(
        default=(),
        description=(
            "The node ids this node's column references bound to, in the order "
            "the formula names them. The graph's one account of what this node "
            "read: the column name behind each id is read off the node the id "
            "names, never restated here."
        ),
    )
    in_final_schema: bool = Field(
        default=False,
        description=(
            "Whether this node is what the frame's column actually holds at "
            "the end. Every other node -- a superseded definition, a column "
            "dropped before the model finished, a name renamed away -- is "
            "history rather than an answer."
        ),
    )
    retained: bool = Field(
        default=False,
        description=(
            "Whether the producer held this definition's own output to the "
            "export and read the value beside it off that, rather than off "
            "the column the frame ended up holding. Meaningful only where "
            "`in_final_schema` is false: a definition the frame holds is read "
            "off the finished frame like any other live column and has "
            "nothing to retain. False everywhere else, and absent from the "
            "wire record unless it is true -- the declaration is what lets a "
            "value hang off a superseded definition at all."
        ),
    )
    dtype: str = Field(default="unknown", description="Data type of the node")
    shape: Shape = Field(
        default="unknown",
        description="Column shape: scalar (one value per policy) or list (per period)",
    )
    provenance: Provenance | None = Field(
        default=None,
        description=(
            "Where this node's values came from, or which frame operation "
            "defined them -- one question, and the node has one answer to "
            "it. None on a node that has neither: a column nothing accounts "
            "for, a running rollforward state, and the two reserved payload "
            "kinds. A null here is a claim rather than a gap."
        ),
    )
    engines: tuple[EngineName, ...] = Field(
        default=(),
        description=(
            "The engines this node's formula reaches into through escape-hatch "
            "text, first mention first. Empty for a formula the framework built "
            "itself, which any engine holding the operations can run."
        ),
    )
    period_reference: Literal["unknown"] | None = Field(
        default=None,
        description=(
            "'unknown' when nothing can be said about which period this node "
            "reads from, because part of its formula is engine text the "
            "framework cannot read. Left unset otherwise: a period reference is "
            "derived from the node's own structure -- a previous_period call IS "
            "the period reference -- so storing one here would be a second, "
            "staler copy of something the node already says. Held for readers "
            "of the graph in memory and deliberately not exported: the "
            "artifact's node record has no such field, and the engines a node "
            "reaches into is what it states there instead."
        ),
    )
    local_fingerprint: str | None = Field(
        default=None,
        description=(
            "The framework's 'sha256:<hex>' stamp of what this node computes: "
            "its formula alone, with no source location, no rendered "
            "expression text and not its own column name. Two columns "
            "computed the same way share one. None until a fingerprinting "
            "pass stamps it -- folding does not, because the callers that "
            "only want the structure should not pay to hash it."
        ),
    )
    fingerprint: str | None = Field(
        default=None,
        description=(
            "The framework's 'sha256:<hex>' stamp of what this node computes "
            "together with everything it reads, in bind order. Moves when "
            "this node's own formula moves and also when anything upstream "
            "of it does, which is what makes it the answer to 'can this "
            "number still be what it was?'. None until a fingerprinting pass "
            "stamps it."
        ),
    )
    formula: str | None = Field(
        default=None,
        description=(
            "The as-written right-hand side of the statement that defined "
            "this column, as its author typed it -- the audit surface, and "
            "what a comparison between two quarters is a comparison of. None "
            "where no single written expression defines the column, and what "
            "decides that is the operation that defined it rather than the "
            "number of columns behind it: a column a batch call minted, "
            "whatever the number of columns "
            "that call defined, a rename, a join, the timeline's own "
            "configuration, a date derivation, or a statement whose source "
            "could not be resolved."
        ),
    )
    lowered: str | None = Field(
        default=None,
        description=(
            "The engine's own rendering of the same calculation, for a reader "
            "chasing what actually ran. It carries no authority against "
            "`formula`, which is the field the format calls normative, and it "
            "is deliberately not part of the wire form: it moves whenever the "
            "engine changes how it prints an expression, and a base artifact "
            "that churns on that is one nobody can compare quarter to "
            "quarter. A reader who wants it asks for it, and it arrives in "
            "the 'gaspatchio_lowered' facet instead. None for a column of "
            "values handed over wholesale, which no expression derives."
        ),
    )
    materialized_at: int | None = Field(
        default=None,
        description=(
            "The ordinal of the boundary at which this node's value was "
            "frozen, counting from 0, or None on a node no freeze ever "
            "settled. The audit reading is taken together with `kind`: a "
            "computed column that was frozen is wearing an input's clothes "
            "-- downstream of the freeze it behaves like data the model was "
            "handed -- and that is the case this field exists for, while on "
            "a leaf it records the freeze that settled the arriving value. "
            "Always None on a hole, which has no recorded history for a "
            "freeze to have settled. A node live at two freezes reports the "
            "later one: that is the freeze the value in front of the reader "
            "came out of."
        ),
    )
    extracts: tuple[Extraction, ...] | None = Field(
        default=None,
        description=(
            "What this column pulls out of a compiled rollforward, in the "
            "order its formula names them, or None on a column that pulls "
            "nothing out of one -- which is every column in a model that "
            "never escalated to a state machine. Held as a sequence "
            "however many there are, because a formula may materialise two "
            "balances at once and they may come from two compilations; the "
            "wire writes the single case as the object it is. "
            "None rather than an empty sequence, by the rule `states` and "
            "`increments` already follow: a column that extracts nothing "
            "says nothing here rather than claiming an extraction of no "
            "states."
        ),
    )
    states: tuple[str, ...] | None = Field(
        default=None,
        description=(
            "The running states one compiled rollforward declares, in "
            "declaration order. None on every node that is not a "
            "compilation, and None on a compilation this process cannot "
            "reach: which states a rollforward declares is a fact about the "
            "compiled artefact, and a node that has only the artefact's "
            "identity says nothing rather than an empty list, which would "
            "claim a state machine with no states in it."
        ),
    )
    increments: tuple[Increment, ...] | None = Field(
        default=None,
        description=(
            "The movements one compiled rollforward applies to its running "
            "balances, in the order they apply. None on every node that is "
            "not a compilation, and None on a compilation this producer "
            "cannot summarise: the compiled artefact is out of reach, an "
            "operation is not one of the ten this format names, two "
            "movements carry one label and the array would not be citable, "
            "or a movement's label is the empty string, which the record "
            "requires a present label not to be. "
            "The same conditional presence `states` has, and for the same "
            "reason -- a producer that cannot say omits the field rather "
            "than writing an empty array, which would claim a compilation "
            "that moves nothing."
        ),
    )
    movements: dict[str, Any] | None = Field(
        default=None,
        description=(
            "What each step of one compiled rollforward actually moved, "
            "keyed by the kernel's own name for the step -- the author's "
            "label where the step carries one, '{kind}@{ordinal}' where it "
            "is structural -- and each key holding the signed per-period "
            "amount under the envelope's evaluation context, in the shape "
            "`value_sample` takes. Every step of the chain is here, which is "
            "what lets a reader close 'closing = opening + sum of movements' "
            "without a residual for the steps nobody named. "
            "Enrichment, so absent from an artifact stating no context; None "
            "on every node that is not a compilation, and on a compilation "
            "whose movements this process could not read."
        ),
    )
    source_location: str | None = Field(
        default=None, description="Source code location"
    )
    value_sample: Any | None = Field(
        default=None,
        description=(
            "What this column held for the declared policy, read off the "
            "finished frame. Row zero unless a 'policy_id' pins one -- the "
            "first row of the file, which is where the data happened to put "
            "it rather than a policy chosen for standing for the book. A "
            "column holding one value per policy carries that value; a "
            "per-period column carries that policy's every period, in "
            "order, unless a 'period' or a year filter pins one, in which "
            "case it carries the one value that reading selected. Which of "
            "the two it is, the envelope's 'periods' states"
        ),
    )
    trace: list[dict[str, Any]] | None = Field(
        default=None, description="Calculation trace"
    )
    branches: dict[str, Any] | None = Field(
        default=None,
        description=(
            "What each branch of this node's conditional would have held "
            "for the declared policy, and which of the two the condition "
            "chose: 'then', 'otherwise' and 'fired'. Only where the "
            "producer was asked to evaluate them, and only on a node whose "
            "whole calculation is a conditional -- the outer one, since a "
            "conditional nested inside a branch is part of that branch's "
            "own value. None everywhere else, and on a node whose branches "
            "the producer could not evaluate"
        ),
    )


class GraphNode(BaseModel):
    """Represents a node in the calculation graph."""

    id: NodeId = Field(description="Unique identifier for the node")
    kind: NodeType = Field(description="What account this node gives of its column")
    data: NodeData = Field(description="Additional node data")


class GraphEdge(BaseModel):
    """One read: whose value, which node read it, and what kind of read it was.

    The two classification fields are what keep "what does this reserve
    depend on?" and "what selected the row?" apart. Drawn without them, an
    impact cone runs through every lookup key in the model and answers the
    first question with the second folded into it.

    They part company on the wire, and only there. ``relationship`` is what
    a written edge carries, because it is the distinction that changes an
    answer; ``subtype`` travels beside it on the reading node, in the
    ``gaspatchio_column_transformation`` facet. In memory they stay one
    record, because one walk produced them together and two containers is
    where a pair starts to drift.

    ``offset`` is the third thing that walk knows and goes to the same
    place, for the same reason: "this month's reserve reads last month's"
    is a claim about which period a value came from, and a read that does
    not say which cell it read answers the question by pointing at the
    same cell. ``ways`` is the fourth: which periods a direct read reached,
    one entry per way it was read, so a cumulative sum's edge says it read
    the run up to this period and a remaining sum's that it read the rest.
    """

    source: NodeId = Field(description="The node id whose value is read")
    target: NodeId = Field(description="The node id that reads it")
    relationship: EdgeType = Field(
        description=(
            "Whether the value read flows into the result (DIRECT) or only "
            "decided which values did (INDIRECT). Named for what an edge "
            "states rather than for the vocabulary the value comes from: "
            "the record already spends `type` on the type vocabulary"
        )
    )
    subtype: EdgeSubtype = Field(
        description=(
            "The narrowing of `relationship`: IDENTITY, TRANSFORMATION and "
            "AGGREGATION go with DIRECT, and JOIN, GROUP_BY, FILTER, SORT, "
            "WINDOW and CONDITIONAL with INDIRECT"
        )
    )
    offset: int | None = Field(
        default=None,
        description=(
            "Which period the value was read at, as a distance from the row "
            "being computed: negative a prior period, positive a later one. "
            "None wherever the read is of the period being computed, and the "
            "facet writes that absence rather than a zero. It travels beside "
            "`subtype`, for the same reason and to the same place"
        ),
    )
    ways: tuple[ReadWay, ...] = Field(
        default=(),
        description=(
            "One entry per way a direct read was made -- its narrowing and "
            "the periods or the literal position it read -- strongest "
            "narrowing first. Empty where the read is one way stating no "
            "window, which `subtype` and `offset` already say in full; the "
            "facet writes one transformation per entry"
        ),
    )


class ModelIdentity(BaseModel):
    """Which model an exported graph is an account of, and what it was run over.

    Every member may be null, and a null is the honest answer where the run
    could not determine one: a version block that invented a label or guessed
    a revision would be worse than one that says it does not know. What it
    carries is what makes an artifact placeable a quarter later -- the file
    the model was read from and its content hash, the revision that file was
    at, the file the policy data was read from, and the output file it wrote.

    Which policy data the model was built over does not depend on this block.
    Every export records a content digest of that data in the document's
    ``book``, so two artifacts can be compared on it whether or not anybody
    named a file here; ``model_points`` adds where the data was read from.

    ``results`` is the one member whose absence is not a null. Every other
    field answers a question the run could fail to answer; that one answers
    a question the run may not have asked at all, and the two readings are
    not the same statement.

    :meth:`of` reads every member off the files themselves, which is how both
    ``gspio calc-graph`` and a Python export fill the block in: the same
    helper on both routes, so the two write the same account of one model.
    """

    label: str | None = Field(
        default=None, description="The name the run gave the model, or None"
    )
    source_path: str | None = Field(
        default=None, description="Where the model file was read from, or None"
    )
    source_sha: str | None = Field(
        default=None,
        description="'sha256:<hex>' over the model source's bytes, or None",
    )
    modules: list[dict[str, str | None]] | None = Field(
        default=None,
        description=(
            "Every local module the model imports -- each file beside the "
            "model, or in a package beside it, that its import statements "
            "resolve to, and those files' own in turn -- as 'path' and "
            "'fingerprint', the sha256 over the file's bytes taken as "
            "'source_sha' is, ordered by path. An empty list where the model "
            "imports nothing from beside itself; None where no model file was "
            "named, and then the member is absent from the document. An "
            "installed package and the standard library are never listed: a "
            "name is resolved against the model's own directory, as running "
            "the model resolves it. A helper is as much the model as the file "
            "is -- an edited accessor moves every figure it computes and no "
            "byte of the model file -- so 'gspio verify --model' holds each "
            "one against the file beside the model it is given. 'fingerprint' "
            "is None only for a file that could not be read"
        ),
    )
    git: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The revision the model source was at -- 'commit' and 'dirty' -- or "
            "None where git ran beside the model and found no working tree, or "
            "{'omitted': 'unavailable', 'detail': ...} where git could not "
            "answer: no git on PATH, git refusing the directory, no commit "
            "yet, or no answer in time, the detail saying which in git's own "
            "first line. None has that one meaning and no other. "
            "'dirty' describes the whole working tree, not the model file "
            "alone: it is true where anything beside the model was uncommitted "
            "at that revision, which is the conservative reading and the only "
            "one a reader should take from it. It is true as well where the "
            "commit does not hold the model file itself -- untracked, or in an "
            "ignored directory -- because the commit then does not hold the "
            "model as it ran"
        ),
    )
    model_points: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The file the policy data was read from -- 'path' and the file's "
            "own 'fingerprint' -- or None where the run named none. The data's "
            "own content digest is recorded in the document's book either way"
        ),
    )
    results: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The output file this run wrote -- 'path' and 'fingerprint', on "
            "exactly the shape 'model_points' carries -- or None where the "
            "run wrote none. None is written out as the field being absent "
            "rather than null, because the two would be different claims: a "
            "null says there were results the producer could not identify, "
            "and what is true is that there were no results to identify. "
            "It is what lets a reader holding the artifact and a Parquet "
            "beside it check that the numbers came out of the run this "
            "document is an account of, rather than trusting two file names "
            "to agree"
        ),
    )
    audit: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The run's own audit record -- 'path' and 'fingerprint', on the "
            "shape 'model_points' and 'results' carry -- or None where the "
            "run wrote none. Absent rather than null for the reason "
            "'results' is. A scenario run keeps two records of itself: this "
            "document, which says how each number was made, and the "
            "sidecar, which says which plan was run and what each scenario "
            "folded. This is the member that ties the two together by "
            "content, rather than by two file names sitting in one directory"
        ),
    )
    scenarios: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The scenario plan's run script the export ran -- 'path' and "
            "'fingerprint', on the shape 'model_points' carries -- or None "
            "where the run was no scenario plan. Absent rather than null for "
            "the reason 'results' is. The plan is as much the run as the "
            "model is: a shock factor edited in it moves every scenario it "
            "shocks and no byte of the model, so a reviewer holds it as the "
            "model file is held"
        ),
    )

    @classmethod
    def of(  # noqa: PLR0913 -- one keyword per file the block can name
        cls,
        model_file: Path | str,
        *,
        model_points: Path | str | None = None,
        results: Path | str | None = None,
        audit: Path | str | None = None,
        scenarios: Path | str | None = None,
        label: str | None = None,
    ) -> Self:
        """Return the version block for a model file: which model, at which commit.

        A reviewer holding an audit file a quarter later asks which model
        produced it: which file, with what in it, at which commit, over which
        policy data. This reads each answer off the files themselves -- the
        model source's path and the sha256 of its bytes, the same two for
        every local module it imports, the git commit it sits at and whether
        the working tree was clean, and a path and a sha256 for each other
        file named -- so an audit file exported from
        Python carries the block ``gspio calc-graph`` writes, and each member
        of it can be checked with ``gspio verify``.

        The model file is named by the caller and never inferred from the
        code that called the export: a notebook, a test and a scheduled job
        all run from somewhere other than the model, and a block naming the
        wrong file is worse than one naming none.

        Every path is written relative to one root -- the repository the
        model sits in, or the model file's own directory outside one -- and
        the export writes each node's location against the same root, so the
        document names no directory on the machine that wrote it. The root
        itself is not written: ``git`` says which of the two applied.

        A member the files cannot answer stays null: a model outside revision
        control has no ``git``, and a named file that cannot be read has no
        stamp. Where git is there and cannot answer -- no git on ``PATH``, a
        refusal such as git's "dubious ownership" of a shared drive, no reply
        in time -- ``git`` is ``{"omitted": "unavailable", "detail": ...}``,
        saying why, so "not under revision control" and "git could not be
        read" are two answers rather than one null. ``git.dirty`` describes
        the whole working tree, not the model file alone, so anything
        uncommitted anywhere in the checkout makes it true -- and so does a
        model file the commit does not hold, untracked or in an ignored
        directory.

        The root is kept beside the fields and is not one of them: two
        identities are equal when their fields are, and a block rebuilt from
        its fields, or read back from JSON, carries no root. An export of
        such a block whose ``source_path`` is relative is refused rather than
        written with absolute locations beside it; ``model_copy`` keeps the
        root, and ``label=`` here is the way to name the model without
        rebuilding the block.

        Args:
            model_file: The model source the run executed.
            model_points: The policy data file the model was run over.
            results: The results file the run wrote.
            audit: The run's own record, such as a scenario run's sidecar.
            scenarios: The scenario plan's run script, where the run was one.
            label: The name the run gives the model, the one member no file
                answers.

        Returns:
            The version block, each member determined or null.

        Raises:
            FileNotFoundError: If ``model_file``, or any file named beside it,
                names no file -- a typo is not a run that wrote no file, and
                the block must not say it was.
            OSError: If a named file is there and cannot be read.

        Examples:
            The line a Python export adds is the config's ``model``:

            >>> import shutil
            >>> import tempfile
            >>> from pathlib import Path
            >>> from gaspatchio.frame.graph import GraphExportConfig, ModelIdentity
            >>> folder = Path(tempfile.mkdtemp())
            >>> model_file = folder / "model.py"
            >>> _ = model_file.write_text("RATE = 0.00123")
            >>> config = GraphExportConfig(model=ModelIdentity.of(model_file))
            >>> config.model.source_path
            'model.py'
            >>> config.model.source_sha.startswith("sha256:")
            True

            A helper the model imports from beside it is stamped the same
            way, so an edited helper is caught as an edited model is:

            >>> _ = (folder / "helpers.py").write_text("LOADING = 1.1")
            >>> _ = model_file.write_text("import helpers")
            >>> [module["path"] for module in ModelIdentity.of(model_file).modules]
            ['helpers.py']
            >>> shutil.rmtree(folder)

            ``GraphExporter(af).export(result, config)`` then writes the block,
            and every node's location against the same directory.

        """
        path = Path(model_file).resolve()
        if not path.is_file():
            msg = (
                f"{model_file} names no model file, so there is no source to "
                "say which model this is an account of. Pass the path of the "
                ".py file the model was run from."
            )
            raise FileNotFoundError(msg)
        # Every named file is checked before git is asked anything: a typo is
        # refused having cost nothing.
        named = {
            member: _named_file(member, given)
            for member, given in (
                ("model_points", model_points),
                ("results", results),
                ("audit", audit),
                ("scenarios", scenarios),
            )
        }
        source_sha = file_sha(path)
        if source_sha is None:
            msg = (
                f"{model_file} could not be read, so its bytes cannot be "
                "stamped. Pass a model file this process can read."
            )
            raise OSError(msg)
        revision = revision_of(path)
        identity = cls(
            label=label,
            source_path=relative_to_root(path, revision.root),
            source_sha=source_sha,
            modules=[
                {
                    "path": relative_to_root(module, revision.root),
                    "fingerprint": file_sha(module),
                }
                for module in local_modules(path)
            ],
            git=revision.git,
            model_points=stamped_file(named["model_points"], revision.root),
            results=stamped_file(named["results"], revision.root),
            audit=stamped_file(named["audit"], revision.root),
            scenarios=stamped_file(named["scenarios"], revision.root),
        )
        # Kept in the instance's own dict, beside the fields and outside the
        # model's own machinery (see _ROOT_KEY), so a copy keeps it while
        # equality and every dump pass it by.
        object.__setattr__(identity, _ROOT_KEY, revision.root)
        return identity


# Where :meth:`ModelIdentity.of` keeps the directory every path in the block
# was written against. Not a field and never on the wire: the format writes
# no root, because a reader holding the document holds the model file and
# ``git`` says which of the two bases applied. It sits in the instance's own
# dict rather than as a declared attribute, because the model's equality
# compares its fields and passes over such an entry -- a declared private
# attribute would take part, and an identity would stop equalling itself read
# back from its own fields. ``model_copy`` copies the dict, so it keeps the
# root; a block rebuilt from its fields or read back from JSON has none, and
# the export then refuses a relative ``source_path`` (:func:`_document_root`).
_ROOT_KEY: Final[str] = "_paths_root"


def _root_of(model: ModelIdentity) -> Path | None:
    """Return the root :meth:`ModelIdentity.of` kept, or None where it kept none."""
    kept = vars(model).get(_ROOT_KEY)
    return kept if isinstance(kept, Path) else None


# What each file the helper can name is, in the words its refusal uses: what
# the block would claim if the file were quietly left out.
_WHAT_A_MISSING_FILE_WOULD_CLAIM: Final[dict[str, str]] = {
    "model_points": "that the run named no policy data file",
    "results": "that the run wrote no results file",
    "audit": "that the run kept no record of itself",
    "scenarios": "that the run was no scenario plan",
}


def _named_file(member: str, given: Path | str | None) -> Path | None:
    """Return a file the caller named, or refuse one that is not there to stamp.

    A named file that is missing, is a directory, or cannot be read is
    refused rather than left out: left out, the block would say the run
    named or wrote no such file, which is a different claim and a false one.
    """
    if given is None:
        return None
    path = Path(given)
    if not path.is_file():
        msg = (
            f"{member}={given} names no file, and leaving it out would say "
            f"{_WHAT_A_MISSING_FILE_WOULD_CLAIM[member]}. Pass the path of the "
            "file itself."
        )
        raise FileNotFoundError(msg)
    if file_sha(path) is None:
        msg = (
            f"{member}={given} could not be read, so its bytes cannot be "
            "stamped. Pass a file this process can read."
        )
        raise OSError(msg)
    return path


def root_of_the_files_read(locations: Iterable[str | None]) -> Path | None:
    """Return the root a document with no other root writes its paths against.

    The first location that names a file on this disk decides it, with the
    two bases :meth:`ModelIdentity.of` uses: the checkout the file sits in,
    or the file's own directory outside one. A frame exported from
    Python with no model identity and no ``source_root`` would otherwise
    write each node's location as the absolute path the interpreter
    recorded, which names the exporting machine (section 7). None where no
    location names a file -- every node written in a notebook cell, or none
    written anywhere -- and then there is no absolute path to write either.
    """
    for location in locations:
        if not location:
            continue
        written = Path(location.rpartition(":")[0])
        if written.is_absolute() and written.is_file():
            return _checkout_holding(written.parent)
    return None


# The checkout each directory sits in, found once per directory a process asks about.
_CHECKOUTS: dict[Path, Path] = {}


def _checkout_holding(directory: Path) -> Path:
    """Return the top of the git checkout ``directory`` sits in, else ``directory``.

    Read off the filesystem -- the nearest directory holding ``.git``, a
    directory or a worktree's file -- rather than by asking git: an export
    with no model identity states no revision, so it needs only the root,
    and three git calls per export cost seconds on a large checkout.
    """
    found = _CHECKOUTS.get(directory)
    if found is None:
        found = next(
            (
                candidate
                for candidate in (directory, *directory.parents)
                if (candidate / ".git").exists()
            ),
            directory,
        )
        _CHECKOUTS[directory] = found
    return found


def _document_root(
    model: ModelIdentity | None, source_root: Path | str | None
) -> Path | None:
    """Return the directory every path in a document is written against.

    An identity made by :meth:`ModelIdentity.of` wrote its own paths against
    a root, and a document holds one root or its paths cannot all be
    resolved from one place. So where the caller names none, the identity's
    root is the document's: each node's location and each entry of the
    sources section is written against the directory ``source_path`` was.

    A ``source_root`` naming that same directory changes nothing, however it
    is spelled -- two spellings of one directory on a filesystem that ignores
    case are one directory. One naming another directory is refused rather
    than preferred, whichever way the preference would run: locations written
    against somewhere other than the checkout the block names a commit of
    resolve for no reader, and a block rewritten to follow the caller is no
    longer the account the helper read off the files.

    **A relative ``source_path`` with no root is refused too.** The root is
    not a field, so an identity rebuilt from its fields or read back from
    JSON carries none, and exported as it stands its node locations would be
    absolute beside a ``source_path`` that is not: two bases in one document,
    and a directory of the exporting machine named in it.

    Args:
        model: The identity the document carries, or None.
        source_root: The root the caller named, or None.

    Returns:
        The root, resolved, or None where neither the caller nor the identity
        names one -- the document then carries each location as the
        interpreter recorded it.

    Raises:
        ValueError: If ``source_root`` names a directory other than the one
            the identity's paths were written against, or if the identity's
            ``source_path`` is relative and no root is known.

    """
    stated = None if model is None else _root_of(model)
    if source_root is None:
        if stated is None and model is not None:
            _refuse_a_relative_source_path_with_no_root(model.source_path)
        return stated
    named = Path(source_root).resolve()
    if stated is None:
        return named
    if _one_directory(named, stated):
        return stated
    msg = (
        f"source_root names {named}, and the model identity's paths were "
        f"written against {stated}. One document writes every path against "
        "one root, and an identity from ModelIdentity.of has already taken "
        "its own: the repository the model sits in, or the model file's "
        "directory outside one. Leave source_root out and the export writes "
        "every location against that root, or name the root the identity "
        "already carries."
    )
    raise ValueError(msg)


def _one_directory(one: Path, other: Path) -> bool:
    """Return whether two resolved paths name one directory on this machine."""
    if one == other:
        return True
    try:
        return one.samefile(other)
    except OSError:
        return False


def _refuse_a_relative_source_path_with_no_root(source_path: str | None) -> None:
    """Refuse an export that would write absolute locations beside a relative path."""
    if source_path is None or PurePath(source_path).is_absolute():
        return
    msg = (
        f"The model identity names its source by the relative path "
        f"{source_path}, and this export knows no root to write node "
        "locations against, so they would be absolute beside it. Build the "
        "identity with ModelIdentity.of(model_file), which keeps the root its "
        "own paths were written against -- label= names the model there -- or "
        f"pass source_root, the directory {source_path} is relative to."
    )
    raise ValueError(msg)


class GraphExportConfig(BaseModel):
    """Configuration for graph export operations."""

    model: ModelIdentity | None = Field(
        default=None,
        description=(
            "Which model the export is an account of. ModelIdentity.of(model_file) "
            "fills it in from the files, as gspio calc-graph does. None where "
            "the caller knows nothing about it, which exports a version block "
            "of nulls."
        ),
    )
    policy_id: str | None = Field(
        default=None,
        description=(
            "Which model point every sample value and trace is read from. "
            "None reads the first row of the file: unpinned you always get "
            "the first thing, not a representative policy"
        ),
    )
    policies: tuple[SelectedPolicy, ...] = Field(
        default=(),
        description=(
            "The axis of model points this artifact carries values for, in "
            "the order the selector produced it, each entry carrying the row "
            "it sits at, the id it holds and the sentence saying how it came "
            "to be in the file. Empty is what every caller that predates the "
            "axis asks for: one policy, the one `policy_id` above names, and "
            "every enrichment field written as the value itself"
        ),
    )
    folds: tuple[PortfolioFold, ...] = Field(
        default=(),
        description=(
            "The book's own folds, which sit at the head of the axis above "
            "-- before the policies, because a total of the book is the "
            "thing a reader of a portfolio document opened it for. Each "
            "carries the name of the fold, the cut it was taken over, the "
            "sentence saying what it is an account of, and what each "
            "column it covers came to. Empty is every export nobody asked "
            "for a fold"
        ),
    )
    row_pin: tuple[tuple[str, Any], ...] | None = Field(
        default=None,
        description=(
            "Which row of the finished frame every sample and trace is read "
            "off, as the column-and-value pairs that name it. It is the "
            "export's own row stamp, put on the book before the model ran "
            "and found again afterwards, and it outranks `policy_id`: a "
            "model that reordered its rows reordered the ids with them, so "
            "the stamp is the only statement that survives the run. None "
            "where nothing was pinned, which is every caller that predates "
            "the policy axis"
        ),
    )
    policy_id_column: str = Field(
        default="Policy number", description="Name of policy ID column"
    )
    period: int | None = Field(
        default=None,
        description=(
            "The projection period every per-period value is read at, or "
            "None to read every period. It is to the time axis what "
            "`policy_id` is to the model points: one narrowing, stated on "
            "the document rather than left for a reader to infer from the "
            "numbers. A period past the end of every timeline in the frame "
            "is refused, naming the length the projection actually reaches."
        ),
    )
    filter_expr: str | None = Field(
        default=None, description="Polars filter expression"
    )
    include_traces: bool = Field(default=True, description="Whether to generate traces")
    branches: bool = Field(
        default=False,
        description=(
            "Whether a conditional states what its dead branch would have "
            "held. Off, nothing is evaluated and no node carries the "
            "member: the answer to 'what would this have been if the "
            "condition had gone the other way?' is not in the finished "
            "frame, so stating it costs one evaluation of each branch per "
            "conditional and a reader who did not ask should not pay it"
        ),
    )
