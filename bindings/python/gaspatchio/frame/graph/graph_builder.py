# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Folding the durable calculation log into the model's calculation graph.

The log is an append-only sequence of what a model *did*, in the order it
did it. The graph is what a reviewer reads: which calculation fed which,
all the way back to the columns the data arrived in. ``fold`` is the one
function that turns the first into the second, and it does so with a
single rule.

## One node per definition

A model reassigns. ``af.policies_in_force`` gets written once before the
maturity test and once after it, and those two lines are two different
worksheet columns wearing one Python name -- which is exactly why the
Excel version of the same model has two columns and Trace Precedents works
on it. So every record in the log mints its own node, identified as
``column@ordinal``, and a column written twice has two nodes. The columns
the frame arrived with mint one unversioned node each: nothing on the
frame defines them, so there is no ordinal to give them.

## Bind first, advance after

Records store column *names* -- ``Col("policies_in_force")`` -- never
versions. Position in the log is what carries the version, so the fold
walks the log in order holding a map from each live column name to the
node that currently defines it:

1. bind every column reference in the record's formula against that map;
2. mint the record's own node;
3. only then point the map at the new node.

That ordering is the whole mechanism. It is what makes ``x = f(x)`` read
the version it is about to replace rather than itself -- a plain edge
between two nodes instead of a cycle -- and what makes the claim column
written between the two writes read the first version while the payout
column written after them reads the second. There are no phi nodes and no
dominance frontiers here: ``when``/``then``/``otherwise`` is an expression
*inside* one assignment, so there is no control flow between assignments
to merge. It is the naming discipline, not the transformation.

## One call is one step

Every column a single ``with_columns`` call defines shares one operation
id, and the fold binds all of them against the map as it stood *before*
the call, then advances all of them together. That is what Polars does --
a sibling naming another sibling is handed the value from before the call
-- so it is what the graph has to say. Membership in such a group is
decided by the shared operation id the records carry and by nothing else:
two consecutive single-expression calls are two groups and see sequential
state, however adjacent they look in the log.

A boundary record marks a materialization. It defines no column, so it
mints no node; the record is kept so a reader can still see where the plan
was frozen, and every definition that was live when the walk met it is
stamped with that freeze. Being live at a freeze is the whole of what the
stamp means: those are the definitions the freeze turned into values, and
downstream of it each of them behaves like data the model was handed.

## Holes: the columns nothing accounts for

Every column a finished model holds should be a recorded calculation, a
column the data arrived with, or a located injection. A column that is
none of the three -- present in the frame's schema, absent from the log
and from the arriving set -- is a **hole**, and the frame is reachable in
that state by writing its query plan directly (``af._df =
af._df.with_columns(...)``), behind every door that records.

The fold mints a node for each one, before it walks the log, so that a
calculation reading such a column binds to a hole the schema gave a type
to rather than to one minted blind on first reference. A hole reads
nothing: it is where this model's account of itself ends, and a dependency
walk that arrives at one stops there. Marking is deliberately all it does
-- a wrong composition is refused, but incomplete knowledge is reported,
loudly, in the one artifact whose job is to say how each number was made.

A reference the walk cannot resolve at all -- a record naming a column no
frame ever held -- becomes a hole too, behind a warning. There is no
fourth kind of node for it and deliberately no "inferred" source to give
it: the fold can see that nothing accounts for the name and can see
nothing else, and an input node would tell a reviewer the policy data
supplied a column the model never had.

Two holes say more than that, because the frame saw more. A write to the
query plan that defined a column the frame had accounted for is in the
log as an overwrite, and the walk mints it where it falls: a hole that is
one of the column's definitions, versioned and located at the write, which
a later calculation reads and which leaves the definition it replaced as
history. And a column the frame arrived holding that another frame
calculated is seeded with the definition its values came from. Each hole's
account -- its reason, and what the hint a reader is handed is made from --
is kept in ``CalcGraph.hole_accounts``.

## A compiled rollforward is one node, and its states are visible

The framework escalates from a closed form to a state machine exactly
when a within-period charge depends on the running balance -- a cost of
insurance struck on the net amount at risk, a floor and cap on a credited
rate, a benefit base that ratchets to a fund's high-water mark. That
escalation is the whole justification for the machinery, so the graph
shows it as structure rather than flattening it back into the columns
that happen to read it.

One compiled rollforward is **one node**, in the reserved
``rollforward:`` namespace and identified by the compilation's own
published fingerprint. Every extraction from it -- ``af.fund =
compiled.expr_for("fund")``, and the sibling line reading the GMDB out of
the same compilation -- is an ordinary computed node whose whole read is
that one parent. The columns the compilation consumes hang off the
parent, once, where they belong: read twice they were being reported
twice, and read by a wrapper expression they were not being reported at
all.

Each running state the compilation reads mints a leaf of its own, in the
reserved ``state:`` namespace. It is not a column -- nothing on the frame
holds it and nothing can be asked to supply it -- and before it existed
the artifact had nowhere to point when a charge read the balance it was
about to change. A COI on the net amount at risk said it read a rate and
a death benefit and nothing else: true of the arguments, false of the
calculation.

Neither namespace is shared. A column whose name begins ``state:`` or
``rollforward:`` is refused by name at the door that would mint it --
whether it arrived with the data, was assigned, or was written straight
into the query plan -- and the refusal is categorical rather than a
response to a collision. A consumer reading ids by namespace has to be
able to trust what it finds there, and a column sitting in one is a wrong
answer to a question the format says can be asked.

A model reaches the compilation through either of two doors, and both
arrive at the same node. The first is a record whose formula *is* the
extraction, which carries the compilation's fingerprint on the call. The
second is a record that wrapped the extraction in an expression of its
own, where all the record keeps is a reference to the hidden struct
column the frame materialises for the kernel; that name embeds the
fingerprint, so it resolves to the same compilation rather than being
dropped as it used to be. Only the first door survives a process the
compilation is not registered in -- the scratch name carries sixteen hex
characters of a sixty-four character identity, which is enough to
recognise the door and not enough to stand for what came through it. See
:meth:`CalcGraph._resolve`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final, assert_never

import polars as pl
from loguru import logger

from gaspatchio._canonical import short_fingerprint
from gaspatchio._dtypes import (
    UNKNOWN,
    UnmappedDtypeError,
    neutral_dtype,
    wider_than_i64_at,
    with_integers_as_i64,
)
from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    State,
    WhenThen,
    walk,
)
from gaspatchio._shape import shape_from_dtype
from gaspatchio._warning import warn
from gaspatchio.engines.protocol import digest_of_inputs
from gaspatchio.frame.calculations import (
    BoundaryRecord,
    CalculationRecord,
    OverwriteRecord,
)
from gaspatchio.frame.lowering._polars.rendering import conditional_comparisons

from .edges import (
    AGGREGATION,
    STATE_EXTRACTION,
    TRANSFORMATION,
    ReadClaim,
    claim_over,
    classify_reads,
    extraction_of,
    join_keys,
    operand_windows,
    stronger,
    without_windows,
)
from .graph_models import (
    ROLLFORWARD_CALL,
    ROLLFORWARD_FINGERPRINT_ATTR,
    ROLLFORWARD_NAMESPACE,
    ROLLFORWARD_OPERATIONS,
    ROLLFORWARD_POINT_ATTR,
    ROLLFORWARD_SCHEDULE_ATTR,
    ROLLFORWARD_STATE_ATTR,
    SELECTION_NAMESPACE,
    STATE_NAMESPACE,
    Extraction,
    GraphEdge,
    GraphNode,
    HoleAccount,
    Increment,
    NodeData,
    NodeId,
    NodeType,
    Provenance,
    SelectionStep,
)
from .graph_utils import clean_expression_string, source_location
from .row_identity import ROW_STAMP

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from gaspatchio._semantic.ir import AttrValue, EngineName, OpNode
    from gaspatchio.frame.calculations import LogEntry, SelectionRecord
    from gaspatchio.frame.graph.frame_view import GraphSource
    from gaspatchio.frame.plan_writes import Origin

    from .edges import Reference

# column name -> the node that currently defines it. Rebuilt as the fold
# walks the log; never part of the finished graph, which records the
# bindings it produced instead.
_LiveMap = dict[str, NodeId]

# The frame's resolved schema, or an empty mapping when it has no plan to
# resolve one from.
SchemaMap = dict[str, "pl.DataType"]

# node id -> the values that node's own output holds, where the caller
# collected them. Only the type vocabulary reads it, and only for the
# integer widths it judges on values rather than on the width
# (:func:`~.dtypes.neutral_dtype`). Empty for every fold that is not an
# export against a collected frame: what nobody collected, nobody can
# measure, and a fold that measured nothing names nothing.
ValuesInReach = Mapping[NodeId, "pl.Series"]

# The op-tree call a whole column of values handed to the frame is recorded
# under (``frame/base.py`` mints it at every assignment door). The fold
# reads the record's own node for this rather than carrying a second flag
# beside it.
_INJECTION = "injected"

# The one recording door behind which a column's own right-hand side was
# written: a plain ``af.column = ...`` or ``af["column"] = ...`` statement.
# Every other door mints columns from something that is not a written
# expression, which is why ``_as_written`` reads from this one alone.
_WRITTEN_ASSIGNMENT = "assignment"

# The recording door a compiled rollforward's own node comes through. It
# is the compilation's within-period bookkeeping, which is neither a
# statement the model's author wrote nor a column arriving from anywhere.
_ROLLFORWARD_DOOR: Final[Provenance] = Provenance.ROLLFORWARD

# The door a column of values comes back through when an explicit re-entry
# hands it over, against the one a line inside the model hands it over at.
# Both are values rather than formulas and the node says which: where the
# data came back in is the distinction a reviewer is entitled to, and it is
# the only thing the merged field keeps of an injection's own door.
_RE_ENTRY: Final[str] = "continuation"

# The operation the compilation's own node stands for, and the attribute
# carrying the identity that says which compilation it is. The node's
# whole formula is this one call: a compiled rollforward's fingerprint is
# already an identity over every state and every operation in it, so
# restating the machine inside the node would hash the same structure
# twice under two different grammars. Both strings are read back out by
# whatever asks the graph which compilations it holds, so they are named
# where the two id namespaces are.
_COMPILATION = ROLLFORWARD_CALL
_FINGERPRINT_ATTR = ROLLFORWARD_FINGERPRINT_ATTR
_SCHEDULE_ATTR = ROLLFORWARD_SCHEDULE_ATTR

# A compilation is reached by its run: the pair (fingerprint, schedule) a
# rollforward call carries. The fingerprint is the machine alone and leaves
# the schedule out, so it names the machine and the pair names the kernel
# run -- which is what the process files a compilation under.

# What each reserved id namespace names, said once. Both phrases go into
# refusals -- the one that keeps a column out of a namespace and the one
# that keeps two things out of a single id -- and a namespace whose purpose
# is worded two ways in two refusals is one a reader has to reconcile.
_STATE_IS = "one running rollforward state"
_COMPILATION_IS = "one compiled rollforward"
_SELECTION_IS = "one step that chose which rows the model values"

# The reserved namespaces, paired with what each one names, for the check
# that walks them. A pair rather than two branches so that adding a third
# namespace is adding a line here rather than finding every place two were
# spelled out.
_RESERVED_NAMESPACES: tuple[tuple[str, str], ...] = (
    (STATE_NAMESPACE, _STATE_IS),
    (ROLLFORWARD_NAMESPACE, _COMPILATION_IS),
    (SELECTION_NAMESPACE, _SELECTION_IS),
)


def _refuse_reserved(column: str) -> None:
    """Refuse a column named into a reserved id namespace.

    Section 8.1 of the format says a column name may not be produced into
    either namespace, and it is a rule about the *name* rather than about a
    collision: the point of a reserved namespace is that a consumer reading
    ids by namespace can trust what it finds there. A column called
    ``state:premium@bop`` that no compilation happens to contend with is
    still a node in the ``state:`` namespace giving an account of a column,
    which is the one thing a node there is defined not to be -- and a
    consumer that read it as a running balance would be reading the
    artifact correctly and getting the wrong answer.

    So the refusal is categorical, not conditional on the id being taken.
    It fires at the two doors that mint a node from a column name
    (:meth:`CalcGraph._add_leaf` and :meth:`CalcGraph._add_definition`), so
    that an arriving column, an assigned column and a column written
    straight into the plan are each refused the same way and by name.

    Raises:
        ValueError: If ``column`` begins with a reserved namespace prefix.

    """
    for prefix, names in _RESERVED_NAMESPACES:
        if not column.startswith(prefix):
            continue
        msg = (
            f"The column {column!r} is named into the calculation graph's "
            f"reserved {prefix!r} namespace, which names {names}. A reserved "
            "namespace names something that is not a column of the model at "
            "all, so no column may be produced into one: a reader taking the "
            f"id {column!r} for {names} would be reading the artifact "
            "correctly and getting the wrong answer. Rename the column."
        )
        raise ValueError(msg)


def _nameable(
    dtype: pl.DataType | None, column: str, values: pl.Series | None = None
) -> pl.DataType | None:
    """Return an arrival type this vocabulary can name, or None.

    An arriving column the model renamed or dropped is history by the time
    the graph is folded: the frame still remembers the type it came in
    under, and nothing else does. Where section 10 has a name for that
    type, the leaf states it -- which is the whole point of keeping the
    record.

    Where it has none -- a vendor ``Categorical``, an ``Array``, a
    ``Duration``, an integer wider than ``i64`` with no values left in
    reach to judge it on -- this returns None and the leaf stays
    ``unknown``, which is the permission section 10 writes for exactly this
    case: a column defined and then dropped, where the value is history
    rather than the answer. Refusing instead would refuse the whole export
    over a column the model had already carried into the vocabulary and
    let go of -- ``af.product = af["Product Code"].to_text()`` followed by
    a drop, which is the move ``.to_text()`` exists for.

    ``values`` are the column as the book arrived with it, where the fold
    read them, so an integer wider than ``i64`` whose every value fits is
    named ``i64`` as it would be at a DataFrame's door.

    A column the frame still holds never reaches here: the collected
    schema answers for it first, and a type with no name there refuses the
    export as it always has.
    """
    if dtype is None:
        return None
    try:
        neutral_dtype(dtype, column=column, values=values)
    except UnmappedDtypeError:
        logger.debug(
            f"The type {column!r} arrived under has no name in the "
            "calculation graph's vocabulary and the column is no longer on "
            "the frame; its input leaf stays untyped."
        )
        return None
    return dtype


def _still_as_arrived(af: GraphSource) -> frozenset[str]:
    """Return the names that still hold the values the frame arrived with.

    An arriving name the model renamed away or dropped is out of the
    frame's arriving set (``_initial_columns`` follows both), and one a
    line of the log defined -- a rename into it, an assignment over it, a
    write straight into the plan -- holds that line's values from then on.
    Every other arriving name holds the book's own column.
    """
    written = {
        entry.column
        for entry in af._calculations  # noqa: SLF001 -- the frame's own log
        if isinstance(entry, (CalculationRecord, OverwriteRecord))
    }
    return af._initial_columns - written  # noqa: SLF001 -- the frame's own


def _is_injection(node: OpNode) -> bool:
    """Return whether ``node`` is a column of values rather than a formula."""
    return isinstance(node, Call) and node.name == _INJECTION


def _rebuilt_account(origin: Origin | None) -> HoleAccount | None:
    """Return the account of a hole another frame's calculation made, or None.

    None where nothing says another frame made it, which leaves the hole
    unrecorded: the fold saw its name and nothing else.
    """
    if origin is None:
        return None
    return HoleAccount(
        "rebuilt",
        calculated_by=origin.node_id,
        calculated_at=origin.source_location,
    )


def _provenance_of(record: CalculationRecord, *, injected: bool) -> Provenance:
    """Return where one recorded definition's values came from.

    A definition the model calculated answers with the door it came
    through, and each door is a provenance of its own: nothing is
    translated here, the vocabularies were built to meet.

    A definition that is a whole column of values answers with the values
    instead. ``injected`` is a column handed over at a line inside the
    model; ``continuation`` is one that came back through an explicit
    re-entry. The door such a column was *recorded* under is dropped, and
    it is the only thing this mapping does not carry: which statement
    wrote the values down is not a fact about where they came from, which
    is the question the field asks. The distinction that is load-bearing
    on a column of values -- handed over at a line, against returned from
    outside the frame's own calculations -- is exactly these two members.
    """
    if not injected:
        return Provenance(record.origin)
    return (
        Provenance.CONTINUATION if record.origin == _RE_ENTRY else Provenance.INJECTED
    )


def _references(node: OpNode) -> Iterator[Reference]:
    """Yield what a formula reads, in the order it names them.

    Two kinds, and the walk stops at the second. A column is yielded by
    name. A compiled rollforward is yielded as the call that reads it back
    out, and nothing inside that call is descended into: the operands
    there are what the *compilation* reads, and they belong to its own
    node rather than to every line that pulls a state out of it.

    The same shape as ``col_refs``, which this deliberately does not reuse:
    that function answers "which columns must the frame supply", which is a
    different question from "what did this formula read" the moment one of
    the answers is not a column. It still descends into an extraction, and
    it must, because those columns are the ones the kernel needs.

    Duplicates are yielded; the caller de-duplicates once it has resolved
    each reference to a node, since two references can resolve to one node.

    A join's key is yielded too, though the record names it in an
    attribute rather than as an operand: every column a join brings in
    holds the row its key matched, so it reads that key (:func:`join_keys`
    says why, and is the one reader of the attribute). Bound like any other
    name, to the definition the key held when the join ran.
    """
    extraction = extraction_of(node)
    if extraction is not None:
        yield extraction
        return
    yield from join_keys(node)
    match node:
        case Col(name=name):
            yield name
        case EngineNative(deps=deps):
            yield from deps
        case BinOp(left=left, right=right):
            yield from _references(left)
            yield from _references(right)
        case Call(args=args):
            for arg in args:
                yield from _references(arg)
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            yield from _references(cond)
            yield from _references(then)
            yield from _references(otherwise)
        case Lit() | State():
            pass
        case _ as unreachable:
            assert_never(unreachable)


def _string_attr(node: Call, key: str) -> str:
    """Return one of a call's typed attributes, refusing anything but text.

    Raises:
        TypeError: If the attribute is absent or is not text. Every
            rollforward call carries its compilation's fingerprint as a
            string; one that does not is an emission bug, and a graph that
            went on to build an id out of the wrong sort of value would be
            wrong quietly.

    """
    value: AttrValue = dict(node.attrs).get(key)
    if not isinstance(value, str):  # pragma: no cover - emission always sets it
        msg = f"{node.name}: {key!r} must be a string, got {value!r}"
        raise TypeError(msg)
    return value


def _run_of(node: Call) -> tuple[str, str]:
    """Return the run one rollforward call names: its fingerprint and schedule."""
    return _string_attr(node, _FINGERPRINT_ATTR), _string_attr(node, _SCHEDULE_ATTR)


def _declared_states(run: tuple[str, str]) -> tuple[str, ...] | None:
    """Return the states one compilation declares, in declaration order, or None.

    None where this process cannot reach the compiled artefact -- a graph
    folded from a log that travelled, or one folded in a worker that never
    ran the compiler. The node still carries the compilation's identity
    and everything the record said it reads; what it stops claiming is the
    state list, because that is a fact about the compiled artefact and
    nothing else in the record holds it. An empty list would say the state
    machine has no states in it, which is not something any compilation is.
    """
    # The lowering package imports the op-tree, so importing it at module
    # scope here would close a cycle.
    from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415 — import cycle
        rollforward_for,
    )

    try:
        compiled = rollforward_for(*run)
    except KeyError:
        logger.debug(
            f"No compiled rollforward is registered for {run[0]!r} in this "
            "process, so its node carries its identity and what the record "
            "said it reads, and states nothing about which states it declares."
        )
        return None
    return tuple(state.name for state in compiled.ir.states)


def _declared_increments(run: tuple[str, str]) -> tuple[Increment, ...] | None:
    """Return one compilation's movements in the order they apply, or None.

    The summary section 16 carries: what moved, under what name, onto which
    balance, and whether the amount depended on the balance it changed. Not
    the machine -- no amount, no expression, no rounding, no stopping
    condition, no opening value -- which travels in the rollforward IR facet
    the ``executable`` profile carries.

    None in the four cases a producer cannot write a citable summary, and
    an omitted field rather than an empty array in every one of them, exactly
    as ``states`` is omitted:

    * the compiled artefact is out of reach, which is ``states``' own case;
    * an operation this format does not name, where inventing an entry would
      put a movement in front of a reader under a name the vocabulary never
      promised;
    * two movements carrying one label, which would leave the array
      uncitable -- the requirement is on the document rather than on the
      compiler, so a model whose labels collide still compiles and still
      runs, and only its summary goes unwritten;
    * a movement whose label is the empty string. A label is a name a model
      reads an increment back by, ``""`` is not one, and the record requires
      a present label to be non-empty. It is its own case rather than the
      collision's other half: the compiler refuses a *missing* label under
      ``track_increments`` and says nothing about an empty one, so ``""``
      compiles, and a producer following a rule that named only the other
      three would write a document its own validator refuses.
    """
    # The lowering package imports the op-tree, so importing it at module
    # scope here would close a cycle.
    from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415 — import cycle
        rollforward_for,
    )
    from gaspatchio.frame.lowering.rules.rollforward import (  # noqa: PLC0415 — rules load lazily
        increments_of,
    )

    fingerprint = run[0]
    try:
        compiled = rollforward_for(*run)
    except KeyError:
        logger.debug(
            f"No compiled rollforward is registered for {fingerprint!r} in this "
            "process, so its node says nothing about which movements it "
            "applies, for the same reason it says nothing about its states."
        )
        return None

    labels: set[str] = set()
    for ordinal, op in enumerate(compiled.ir.transitions, start=1):
        operation = type(op).__name__
        if operation not in ROLLFORWARD_OPERATIONS:
            logger.debug(
                f"Compilation {fingerprint!r} applies a {operation!r}, which is "
                "not one of the ten operations this format names, so its node "
                "carries no increments summary rather than an invented entry."
            )
            return None
        label = getattr(op, "label", None)
        if label is not None and (label == "" or label in labels):
            logger.debug(
                f"Compilation {fingerprint!r} carries the label {label!r} at "
                f"increment {ordinal}, which is empty or already used, so its "
                "node carries no increments summary rather than an array a "
                "reader could not cite one movement of."
            )
            return None
        if label is not None:
            labels.add(label)
    return tuple(
        Increment(
            ordinal=ordinal,
            label=increment.label,
            operation=increment.operation,
            target=increment.target.name,
            reads_running_balance=increment.reads_running_balance,
        )
        for ordinal, increment in enumerate(increments_of(compiled.ir), start=1)
    )


def _operands_of(run: tuple[str, str]) -> tuple[OpNode, ...]:
    """Return what a compilation reads, when only its kernel column is to hand.

    The door a wrapped extraction comes through: the record kept the
    kernel's column name and nothing else, so what the compilation
    consumes has to come from the compiled artefact. A record whose whole
    formula is the extraction already carries exactly this tuple as the
    call's arguments, and is read from there rather than looked up.
    """
    # ``rules.rollforward`` loads with its siblings the first time anything
    # reads the lowering registry; importing one rule module at module
    # scope would populate that registry before the loader has run.
    from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415 — import cycle
        rollforward_for,
    )
    from gaspatchio.frame.lowering.rules.rollforward import (  # noqa: PLC0415 — rules load lazily
        operand_nodes,
    )

    return operand_nodes(rollforward_for(*run).ir)


def _as_written(record: CalculationRecord) -> str | None:
    """Return the right-hand side the model's author typed, or None.

    This is the field a reviewer and a supervisor read, so it carries the
    statement's own text rather than the engine's rendering of what that
    text meant. The two say the same thing about the model, and only one of
    them stays the same when a dependency changes how it prints an
    expression -- which is the difference between an artifact two quarters
    apart that can be compared and one that cannot.

    Null is a claim here, not a gap, and there are two ways to earn it.

    The first is that no single written expression defines the column. The
    door is the test here, not the number of columns behind it: a column a
    batch call minted has a statement, but that statement's right-hand side
    is the whole call, sibling or no sibling, and reporting it against one
    column would show a reviewer text that does not compute the number
    beside it. A call that happened to define exactly one column is the same
    call through the same door, and earns the same null. A rename moves a
    name and writes no expression at all; a join brings a column in from
    another table; the projection timeline and a date derivation each stamp
    columns from one configuration rather than from a formula. Each of those
    is a record the log holds honestly and none of them has an as-written
    right-hand side, so the ``assignment`` door is the only one this reads
    from. One statement comes through that door and still writes several
    columns at once -- ``af.a, af.b = x, y`` -- and it earns the same null
    for the same reason, one step earlier: capture records no right-hand
    side for a tuple target, so there is none here to read.

    The second is that the statement could not be resolved: source read
    from stdin, an ``exec``-compiled snippet, a ``compile(..., '<string>')``
    fragment and a bare REPL each leave the interpreter with no retrievable
    text, and an augmented assignment (``af.reserve += ...``) is neither of
    the two shapes a right-hand side is taken from -- a ``target = value``
    assignment writing one column, and the ``setattr(af, name, value)`` call
    a column whose name is only known at run time is written through. Both
    leave the span without one, and a null says so rather than inventing
    text.

    A notebook cell is not one of those, tempting as it is to assume:
    IPython registers each cell's source in ``linecache``, which is where
    ``executing`` reads from, so an ordinary cell resolves its right-hand
    side and reports a ``Jupyter Cell N:M`` location like any other
    statement.

    A reader who needs to see what actually ran reaches for the engine's
    rendering, which every one of these nodes still carries: it travels in
    the ``gaspatchio_lowered`` facet, and the export writes it when it is
    asked for.

    Args:
        record: The log entry whose defining statement to read.

    Returns:
        The right-hand side's own text, or None where there is none.

    """
    if record.origin != _WRITTEN_ASSIGNMENT:
        return None
    if record.source is None:
        return None
    return record.source.rhs


def _kernel_column(name: str) -> bool:
    """Return whether ``name`` is a column the rollforward kernel minted for itself.

    A compiled rollforward is read through a struct-field reference into a
    hidden column named ``__rollforward_<fingerprint>``, which the frame
    materialises for the kernel to work in. Assigning that reference
    straight to a column keeps the hidden name out of the record, but any
    expression built around it -- prepending a period, combining two
    states -- carries the name through into it.

    It is the kernel's scratch space rather than a column of the model,
    and the frame already treats it that way:
    ``ActuarialFrame._unaccounted_columns`` leaves it out of what the model
    failed to explain, and ``collect()`` strips it from the output. What
    the fold does with it is resolve it to the compilation it names, which
    is the thing the record was actually reading.

    What matches is the name the kernel mints and not everything that
    begins like it. The minted shape is the prefix and sixteen hex
    characters of a fingerprint, exactly, and the registry that mints it is
    asked (``rollforward/_registry.py``). A column of the author's own that
    happens to start with those letters is a column of the model, and
    treating it as the kernel's would leave the node reading it saying it
    read nothing while its own formula still names the column -- a lineage
    claim the artifact cannot support, unannounced, in the one document
    whose whole purpose is that it can be checked.
    """
    # The rollforward package imports the frame; imported on call to keep
    # that edge one-way at import time.
    from gaspatchio.rollforward._registry import (  # noqa: PLC0415 — import cycle
        _is_minted_name,
    )

    return _is_minted_name(name)


def _engines_reached(node: OpNode) -> tuple[EngineName, ...]:
    """Return the engines ``node``'s escape-hatch text needs, first mention first.

    Empty for a formula the framework built itself, whatever its depth: a
    node needs a named engine only where it carries text written in that
    engine's own language. The walk is what makes one opaque operand
    enough -- a mortality rate multiplied by a raw Polars cumulative sum
    is a calculation whose value nothing but Polars can produce, however
    ordinary the multiplication around it looks.
    """
    engines: list[EngineName] = []
    for current in walk(node):
        if isinstance(current, EngineNative) and current.engine not in engines:
            engines.append(current.engine)
    return tuple(engines)


class CalcGraph:
    """One node per definition, plus the columns the model's data arrived in.

    Built by :func:`fold` and read by everything downstream of it. Nodes
    are keyed by :data:`~.graph_models.NodeId` and held in the order the
    log defined them, which is already a topological order: a node is
    added only after every node it reads.
    """

    def __init__(
        self, values: ValuesInReach | None = None, *, refuse_unnamed: bool = True
    ) -> None:
        """Start an empty graph with no inputs, definitions or boundaries.

        ``values`` is what a caller holding the collected frame passes so
        that a wide integer column can be named on its numbers rather than
        on its storage width; see :data:`ValuesInReach`. It is construction
        state and nothing else, and :func:`fold` lets go of it as soon as
        the last node is minted -- a finished graph that kept a reference
        to the frame's columns would hold the whole run's data alive for as
        long as anybody held the graph.

        ``refuse_unnamed`` says whether a calculation whose type has no
        name stops the fold; see :func:`fold`.
        """
        self.nodes: dict[NodeId, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._values: ValuesInReach = values if values is not None else {}
        # The values a bare read moved under a new name, so a rename of a
        # rename is named on them too. Construction state, released with
        # ``_values``.
        self._moved: dict[NodeId, pl.Series] = {}
        self._refuse_unnamed = refuse_unnamed
        # definition node id -> the refusal its type would meet at export,
        # for each calculation a fold that does not refuse let through. Its
        # node says ``unknown`` meanwhile, so this is what tells it apart
        # from a definition whose type was never resolved at all -- which
        # :func:`~.holes.holes_in` reads as the mark of a failed batch.
        self.unnamed_types: dict[NodeId, UnmappedDtypeError] = {}
        # node id -> the op-tree the record held, for the nodes a record
        # minted. A reference rather than a copy, so the fold pays nothing
        # for keeping it, and it is what lets a later pass fingerprint the
        # graph without re-reading the log. Absent for a column the data
        # arrived with and for a column nothing accounts for: neither has a
        # record, which is what makes them the leaves they are.
        self.op_trees: dict[NodeId, OpNode] = {}
        # The materializations the log recorded, in the order they
        # happened. A boundary defines no column and so contributes no node
        # -- but where the plan was frozen is still part of what happened,
        # and a node's ``materialized_at`` is an index into this tuple. The
        # records themselves rather than their positions, because a reader
        # asking where a value was frozen needs the statement as well as
        # the step it fell after.
        self.boundaries: tuple[BoundaryRecord, ...] = ()
        # Every step that chose which rows the model values, in the order the
        # model took them, each bound to the definitions its predicate read
        # when it was taken. Not nodes: a selection defines no column. It is
        # what the document's ``selection`` list carries, and it enters both
        # fingerprints and the book's columns from here.
        self.selection: tuple[SelectionStep, ...] = ()
        # hole node id -> what the fold saw of it: the reason, and what the
        # hint a reader is handed is made from. Every hole has one. Kept here
        # rather than on the node, which is what the document writes: the
        # reason reaches the document once per name, through its holes
        # section, and the rest stays in this process.
        self.hole_accounts: dict[NodeId, HoleAccount] = {}
        # column name -> its definition node ids, oldest first. Only
        # columns something on the frame actually defined appear here; an
        # arriving column has no definitions, which is what makes it input.
        self._definitions: dict[str, list[NodeId]] = {}
        # compiled-rollforward run (fingerprint, schedule) -> the one node
        # standing for it. A model may read one compilation from a dozen
        # lines and each of them reads the same node, which is the whole
        # point of the node. Keyed on the run rather than the fingerprint,
        # which leaves the schedule out, so that one machine on two
        # schedules is two compilations here and is refused by name in
        # :meth:`_compilation` rather than merged into one node.
        self._compilations: dict[tuple[str, str], NodeId] = {}
        # running-state node id -> the compilation that minted it. A state
        # is named by the compilation that carries it, and two
        # compilations in one model declaring a state of the same name
        # would otherwise share one leaf and be reported as sharing one
        # running balance. See :meth:`_state`.
        self._state_owners: dict[NodeId, str] = {}
        # column name -> its arrival type and where its values were made, for
        # each column the frame arrived holding that another frame
        # calculated and that no longer stands on it unaccounted for.
        # Construction state: a record that reads one binds to a hole minted
        # then, and the fold lets go of the rest when it ends.
        self._rebuilt_elsewhere: dict[str, tuple[pl.DataType | None, Origin]] = {}

    def versions(self, column: str) -> tuple[NodeId, ...]:
        """Return every definition of ``column``, oldest first.

        Empty for a column nothing on the frame defined -- an arriving
        model-point field, a column nothing accounts for, or a name this
        model never mentions. The last of those is told apart from the
        other two by :meth:`latest`, which does not answer for it.
        """
        return tuple(self._definitions.get(column, ()))

    def latest(self, column: str) -> NodeId | None:
        """Return the node holding ``column``'s value at the end of the log.

        The column's last definition if it has one; the unversioned node if
        nothing defined it -- the input the data arrived with, or the hole
        standing for a column nothing accounts for; and ``None`` if the
        model never mentions the name at all. The node's own type is what
        says which of those the answer is.
        """
        defined = self._definitions.get(column)
        if defined:
            return defined[-1]
        return column if column in self.nodes else None

    def get_node_stats(self) -> dict[str, Any]:
        """Get statistics about the graph."""
        input_nodes = sum(1 for n in self.nodes.values() if n.kind == NodeType.INPUT)
        computed_nodes = sum(
            1 for n in self.nodes.values() if n.kind == NodeType.COMPUTED
        )
        # Counted alongside the other two rather than left to be inferred
        # from the total: a graph with holes in it is the one fact about a
        # model's calculations nobody should have to subtract to notice.
        hole_nodes = sum(1 for n in self.nodes.values() if n.kind == NodeType.HOLE)
        # Every kind is counted, so the parts add up to the total. A count
        # that left two kinds out would have a reader subtracting to find
        # out whether the difference was a rollforward or a bug.
        rollforward_nodes = sum(
            1 for n in self.nodes.values() if n.kind == NodeType.ROLLFORWARD
        )
        state_nodes = sum(1 for n in self.nodes.values() if n.kind == NodeType.STATE)

        return {
            "total_nodes": len(self.nodes),
            "input_nodes": input_nodes,
            "computed_nodes": computed_nodes,
            "hole_nodes": hole_nodes,
            "rollforward_nodes": rollforward_nodes,
            "state_nodes": state_nodes,
            "total_edges": len(self.edges),
            "node_names": list(self.nodes.keys()),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert the graph to a dictionary representation.

        **This is the in-memory structure, not the wire form.** It is the
        nodes and edges exactly as this class holds them -- nested, and
        carrying the fields the fold keeps for itself -- for a caller that
        wants to compare two graphs or walk one without pulling it through a
        serialiser. The artifact a reader outside this package is given is
        built by ``build_artifact``, which is flat, carries an envelope, and
        is what conforms to the published schema.

        Returns:
            Dictionary with "nodes" and "edges" keys

        """
        return {
            "nodes": [node.model_dump() for node in self.nodes.values()],
            "edges": [edge.model_dump() for edge in self.edges],
        }

    # -- how fold() builds it ------------------------------------------------

    def _seed_inputs(
        self, af: GraphSource, schema: SchemaMap, unaccounted: frozenset[str]
    ) -> _LiveMap:
        """Add one node per column the frame arrived with, and start the live map.

        Under the names the data arrived with, not the names the model
        renamed them to. A rename on the way in is a name-move the log already
        records, so the input it moved is still the vendor field it was --
        ``Issue Age``, with ``issue_age`` reading it -- and the graph can
        still say which field of the source each number came from.

        Minus the columns the frame cannot account for, because one name
        can be both. Rename or drop an arriving column, write a new one
        straight into the plan under the name it left behind, and that name
        belongs to the new column: the hole ``_seed_holes`` is about to
        mint, not the input that used to answer to it. Seeding both would
        claim one node id twice, and the graph would far rather say a
        column is unexplained than hand a stranger an arriving column's
        provenance. That set is ``unaccounted``, worked out once by
        :func:`_columns_with_no_account` and handed to both seeds, so the
        two can never disagree about which names they are dividing.

        Typed by the arrival type too, for the names the collected schema
        can no longer be asked about. A renamed column is under its new
        name in that schema and a dropped one is not in it at all, so the
        leaf naming the vendor field used to state ``unknown`` -- a
        producer writing that for a type it did meet, which section 10
        forbids. The frame's own arrival record answers instead
        (``_arrival_schema``), and the leaf's ``value_sample`` stays null
        because the values really are gone from the collected frame. So it
        does for a name a later line took over -- ``af.pid = af.x * 2``
        after the arriving ``pid`` was renamed or dropped, or
        ``af.n = af.n * 1.5`` over it -- where the collected schema's type
        under that name is the new column's, which the leaf took: an
        ``i64`` field stated as ``f64``. Only a name that still holds the
        values it arrived with (:func:`_still_as_arrived`) is typed off
        that schema. A wide arrival is named on the values read off the book
        (:func:`_with_wide_arrivals_read`), so a lazily handed one that
        fits is ``i64`` whether or not the model kept it.

        Ordered by the frame's own column order where it still knows the
        name, then anything else alphabetically. A set's iteration order is
        not stable across processes, and an exported graph that reorders
        its own inputs between two runs of the same model is not one
        anybody can diff.
        """
        arrived: frozenset[str] = af._arrival_names  # noqa: SLF001 -- the frame's own
        initial = arrived - unaccounted
        order = {name: index for index, name in enumerate(af._column_order)}  # noqa: SLF001
        ranked = sorted(initial, key=lambda name: (order.get(name, len(order)), name))
        arrival = af._arrival_schema  # noqa: SLF001 -- the frame's own
        held = _still_as_arrived(af)
        return {
            column: self._add_input(
                column,
                schema[column]
                if column in held and column in schema
                else _nameable(arrival.get(column), column, self._values.get(column)),
                Provenance.MODEL_POINTS,
            )
            for column in ranked
        }

    def _seed_holes(
        self,
        af: GraphSource,
        schema: SchemaMap,
        live: _LiveMap,
        unaccounted: frozenset[str],
    ) -> None:
        """Add one node per column of the schema nothing accounts for.

        The set is handed in rather than taken here: which columns a model
        cannot account for is decided in one place
        (:func:`_columns_with_no_account`, over the frame's own answer),
        because the frame reads that same answer when it hands its log to a
        successor and the input seed reads it just above. A second
        subtraction here would eventually disagree with those.

        Seeded in the frame's own schema order, and done before the log
        walk, so that a calculation reading one of these columns binds to
        a hole the schema has already given a type to. Left until
        afterwards, the first read would reach ``_bind``, whose hole is
        minted blind: it knows the name and nothing else, so the column
        would come off the wire typed ``unknown`` -- and behind a warning
        that nothing in this model accounts for the name, which is not
        what a plan written directly is.

        A column the frame arrived holding that another frame calculated is
        seeded here only while it stands on the frame unaccounted for, as
        every other hole is. Once the frame accounts for the column again,
        or drops it, it is a hole only for a calculation that read it before
        then: :meth:`_bind` mints it when that record is folded, under the
        name it arrived with and typed as it arrived, so the record reads
        the hole rather than a name the fold cannot place. Each such hole
        says which definition made its values; every other one is
        unrecorded, because nothing more than its name was seen.
        """
        rebuilt: Mapping[str, Origin] = af._rebuilt  # noqa: SLF001 -- the frame's own
        for column, dtype in schema.items():
            if column in unaccounted:
                live[column] = self._add_hole(
                    column, dtype, _rebuilt_account(rebuilt.get(column))
                )
        arrival = af._arrival_schema  # noqa: SLF001 -- the frame's own
        self._rebuilt_elsewhere = {
            column: (arrival.get(column), origin)
            for column, origin in rebuilt.items()
            if column not in live
        }

    def _fold_operation(self, records: list[CalculationRecord], live: _LiveMap) -> None:
        """Fold every record one call produced: bind them all, then advance them all."""
        bound: list[tuple[str, NodeId]] = []
        for record in records:
            reads, read_as = self._reads_of(record, live)
            bound.append((record.column, self._add_definition(record, reads, read_as)))
        for column, node_id in bound:
            live[column] = node_id

    def _fold_selections(
        self, records: tuple[SelectionRecord, ...], live: _LiveMap
    ) -> None:
        """Bind each selection step's reads to the definitions live when it was taken.

        A predicate reads columns exactly as a formula does, so it binds the
        way a formula's references bind: to whatever each name held at that
        point in the log. A filter on ``status`` taken before a line rewrote
        ``status`` reads the arriving column, and one taken after reads the
        rewrite. A semi or anti join reads its left key, as a join does.
        """
        for record in records:
            reads: list[NodeId] = []
            for reference in _references(record.node):
                node_id = self._resolve(reference, live)
                if node_id is not None and node_id not in reads:
                    reads.append(node_id)
            self.selection = (
                *self.selection,
                SelectionStep(
                    id=f"{SELECTION_NAMESPACE}{len(self.selection) + 1}",
                    kind=record.kind,
                    tree=record.node,
                    reads=tuple(reads),
                    source=record.source,
                ),
            )

    def _reads_of(
        self, record: CalculationRecord, live: _LiveMap
    ) -> tuple[tuple[NodeId, ...], tuple[ReadClaim, ...]]:
        """Return what one record reads, and what kind of read each one is.

        A read of a compiled rollforward is a read of the compilation, not
        of the columns it consumes. That is the difference the node exists
        to make: those columns are the compilation's reads, stated once on
        its own node, rather than restated on every line that pulls a state
        back out of it -- which reported one growth rate twice in a model
        reading two states, and reported the compilation's own running
        balance nowhere.

        Everything else binds the way any column reference binds. Two of
        them can land on one node -- two states of one compilation read in
        one formula -- and the stronger claim wins there, for the reason
        the classifier gives when two reads of one column meet: what an
        edge answers is whether the value is in the number.

        A source holding one value per policy states no window: it has no
        periods to read, and this is where its shape is known.
        """
        read_as = classify_reads(record.node)
        reads: list[NodeId] = []
        claims: dict[NodeId, ReadClaim] = {}
        for reference in _references(record.node):
            node_id = self._resolve(reference, live)
            if node_id is None:
                continue
            held = claims.get(node_id)
            claim = read_as[reference]
            claims[node_id] = claim if held is None else stronger(held, claim)
            if held is None:
                reads.append(node_id)
        return tuple(reads), tuple(
            self._periodic(node_id, claims[node_id]) for node_id in reads
        )

    def _periodic(self, node_id: NodeId, claim: ReadClaim) -> ReadClaim:
        """Return ``claim`` stating its window only where the source has periods."""
        source = self.nodes.get(node_id)
        if source is not None and source.data.shape == "scalar":
            return without_windows(claim)
        return claim

    def _resolve(self, reference: Reference, live: _LiveMap) -> NodeId | None:
        """Return the node one reference names, or None where nothing answers it.

        A compilation is named either by the call that reads it, which
        carries the fingerprint, or by the kernel's own column, whose name
        embeds it. The one reference that answers to nothing is that
        kernel column in a process where the compiler never ran -- a graph
        folded somewhere the compilation does not exist. Binding it would
        mint a hole: the model reported as unable to account for a column
        its author never wrote, behind a warning that nothing in the model
        accounts for the name. Saying nothing about it is the honest
        answer there.
        """
        if isinstance(reference, Call):
            return self._compilation(_run_of(reference), reference.args, live)
        if _kernel_column(reference) and self._compilation_named_by(reference) is None:
            return None
        return self._bind(live, reference)

    def _compilation_named_by(self, name: str) -> tuple[str, str] | None:
        """Return the run of the compilation whose kernel column is ``name``."""
        # The lowering package imports the op-tree, so importing it at
        # module scope here would close a cycle.
        from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415 — import cycle
            rollforward_named_by,
        )

        return rollforward_named_by(name)

    def _compilation(
        self, run: tuple[str, str], operands: tuple[OpNode, ...], live: _LiveMap
    ) -> NodeId:
        """Add the node standing for one compiled rollforward, or return the one held.

        Minted once per compilation however many lines read it, because
        one compilation is one kernel run and one state machine: a model
        extracting a fund and a benefit base from the same compilation is
        reading one thing twice, not two things.

        **The operation id is not what identifies it.** Two extractions
        written as two assignments each mint their own operation id
        (``frame/base.py``), and that id is the fold's transaction
        boundary -- what decides which version of a column a sibling binds
        to. Forcing several assignments to share one to make them share a
        parent would change the answer to a different question, so the
        parent is keyed on the compilation's own published fingerprint
        instead. Do not "fix" this by touching the operation id.

        The id is claimed like any other, so a column that genuinely
        collides with the reserved namespace is refused rather than
        silently merged into the compilation's node.

        **The id is the machine's and the node states the schedule.** The
        published fingerprint leaves the schedule out, so the
        id does too and a re-sourced schedule leaves it where it was; the
        node's one call carries the schedule's ``source_sha()`` beside the
        fingerprint, which is how a schedule change still moves the node's
        digests and ``graph_fingerprint``. One model holding one machine on
        two schedules would put two kernel runs under one id, so that is
        refused by name (:meth:`_refuse_one_machine_on_two_schedules`).

        Args:
            run: The compilation's own published fingerprint and the
                ``source_sha()`` of the schedule it runs on.
            operands: What the compilation reads, in the op-tree's
                vocabulary.
            live: The bindings as they stand, for the columns it consumes.

        Returns:
            The id of the node standing for that compilation.

        Raises:
            ValueError: If this model already holds the same machine on a
                different schedule.

        """
        held = self._compilations.get(run)
        if held is not None:
            return held
        fingerprint, schedule = run
        self._refuse_one_machine_on_two_schedules(run)
        node_id = f"{ROLLFORWARD_NAMESPACE}{short_fingerprint(fingerprint)}"
        self._claim_reserved(node_id, _COMPILATION_IS)
        # Bound before the node is added, so that everything it reads is
        # already in the graph when the node itself arrives: the graph is
        # held in the order the calculations ran, and fingerprinting reads
        # it in that order.
        reads, read_as = self._compilation_reads(operands, fingerprint, live)
        self.nodes[node_id] = GraphNode(
            id=node_id,
            kind=NodeType.ROLLFORWARD,
            data=NodeData(
                id=node_id,
                column=None,
                version=None,
                provenance=_ROLLFORWARD_DOOR,
                reads=reads,
                dtype=neutral_dtype(None, column=node_id),
                shape=shape_from_dtype(None),
                states=_declared_states(run),
                increments=_declared_increments(run),
            ),
        )
        self.op_trees[node_id] = Call(
            _COMPILATION,
            args=(),
            attrs=((_FINGERPRINT_ATTR, fingerprint), (_SCHEDULE_ATTR, schedule)),
        )
        self.edges.extend(
            GraphEdge(
                source=read,
                target=node_id,
                relationship=claim.edge[0],
                subtype=claim.edge[1],
                offset=claim.offset,
                ways=claim.ways,
            )
            for read, claim in zip(reads, read_as, strict=True)
        )
        self._compilations[run] = node_id
        logger.trace(f"Compiled rollforward node: {node_id} reads {reads}")
        return node_id

    def _refuse_one_machine_on_two_schedules(self, run: tuple[str, str]) -> None:
        """Refuse a second schedule under a machine this model already holds.

        The node id is the machine's (its fingerprint leaves the schedule
        out), so the same machine compiled on two schedules in one model is
        two kernel runs claiming one id. Merging them would report the
        second run's reads and movements as the first one's, and minting a
        second id would need a spelling the namespace does not have -- the
        refusal ``_state`` gives two compilations sharing a state name, for
        the same reason. A model's rollforwards run on its own projection,
        so this is reached only by a machine compiled on a schedule handed
        to ``RollforwardBuilder`` directly.

        Raises:
            ValueError: If a compilation of the same machine on another
                schedule is already held.

        """
        fingerprint, schedule = run
        other = next(
            (held for held in self._compilations if held[0] == fingerprint), None
        )
        if other is None:
            return
        msg = (
            f"This model runs one compiled rollforward "
            f"({short_fingerprint(fingerprint)}) on two schedules, "
            f"{short_fingerprint(other[1])} and {short_fingerprint(schedule)}. "
            "A compilation's identity is its machine and leaves the schedule "
            "out, so both runs would claim the calculation-graph node id "
            f"{ROLLFORWARD_NAMESPACE}{short_fingerprint(fingerprint)!s} and the "
            "graph could not say whose reads and movements were whose. Compile "
            "both on the frame's own projection -- af.projection.rollforward(...) "
            "after af.projection.set(...) -- or keep the second model in a "
            "frame of its own."
        )
        raise ValueError(msg)

    def _compilation_reads(
        self, operands: tuple[OpNode, ...], fingerprint: str, live: _LiveMap
    ) -> tuple[tuple[NodeId, ...], tuple[ReadClaim, ...]]:
        """Return what one compilation reads, first mention first, and how.

        Two kinds of thing, and they are classified differently because
        they are different reads. A column the compilation consumes -- a
        growth rate, a charge rate, an anniversary mask -- is an operand
        of a linear recurrence, so its value is in every later period's
        answer rather than only in this one, which is what ``AGGREGATION``
        says and ``TRANSFORMATION`` would not. A running state is the
        balance the compilation is carrying at this period, read by the
        compilation that owns it, and that is ``TRANSFORMATION``.

        De-duplicated, like every other node's reads: two operations
        charging the same rate column read one column, and the graph
        states what a node reads rather than how many times it mentioned
        it.
        """
        reads: dict[NodeId, ReadClaim] = {}
        for operand in operands:
            for node_id, claim in self._compilation_operand_reads(
                operand, fingerprint, live
            ):
                held = reads.get(node_id)
                reads[node_id] = claim if held is None else stronger(held, claim)
        return tuple(reads), tuple(
            self._periodic(node_id, claim) for node_id, claim in reads.items()
        )

    def _compilation_operand_reads(
        self, operand: OpNode, fingerprint: str, live: _LiveMap
    ) -> Iterator[tuple[NodeId, ReadClaim]]:
        """Bind one operand's leaves, distinguishing state reads from column reads.

        No claim here carries an offset. A compilation's operand run is the
        machine's own order rather than a formula's, and a linear
        recurrence reads every period of what it consumes up to the one it
        is at -- which is what ``AGGREGATION`` says, and a single distance
        would contradict. That run is the window a column read states,
        ``{first, 0}``, quoted from the recurrence's own direction
        (:func:`operand_windows`); an engine fragment's dependencies state
        none, because nothing here can read the text.
        """
        windows = operand_windows(operand)
        for current in walk(operand):
            if isinstance(current, State):
                yield self._state(current.name, fingerprint), ReadClaim(TRANSFORMATION)
            elif isinstance(current, Col):
                yield (
                    self._bind(live, current.name),
                    claim_over(AGGREGATION, windows.get(current.name, (None,))),
                )
            elif isinstance(current, EngineNative):
                for dependency in current.deps:
                    yield self._bind(live, dependency), ReadClaim(AGGREGATION)

    def _state(self, name: str, fingerprint: str) -> NodeId:
        """Add the leaf standing for one running state, or return the one held.

        A running state is not a column: nothing on the frame holds it,
        nothing can be asked to supply it, and it reads nothing itself --
        it is where a compilation's account of its own balance begins.

        Two compilations in one model may each carry a running state of the
        same reference, and the id namespace has no room to tell them
        apart. Sharing the leaf would say the two compilations carry one
        running balance, which is a lineage claim the artifact cannot
        support, so the second one is refused instead and the message says
        which rename fixes it.

        The refusal names the state the way its author did. ``name`` is the
        reference the compilation carries -- ``fund@eop``, a state and the
        point it is read at -- and what the author wrote is
        ``states={"fund": ...}``. Asking them to rename ``'fund@eop'``
        sends them looking for a string their model does not contain, so
        the state is named on its own and the reference follows it in
        parentheses. Reading the state back out is the same partition
        ``classify_operand_expression`` makes on the way in, which is the
        one place the framework parses this spelling.

        Raises:
            ValueError: If a second compilation claims a state id already
                minted for another one.

        """
        node_id = f"{STATE_NAMESPACE}{name}"
        owner = self._state_owners.get(node_id)
        if owner == fingerprint:
            return node_id
        if owner is not None:
            declared, _, _ = name.partition("@")
            msg = (
                f"Two compiled rollforwards in this model both carry a running "
                f"state {declared!r} (read as {name!r}), so both claim the "
                f"calculation-graph node id {node_id!r}: the compilations "
                f"{short_fingerprint(owner)} and "
                f"{short_fingerprint(fingerprint)}. A running state is named by "
                "the state and not by the compilation carrying it, so the graph "
                "cannot say whose balance this one is. Rename one of the states."
            )
            raise ValueError(msg)
        self._claim_reserved(node_id, _STATE_IS)
        self.nodes[node_id] = GraphNode(
            id=node_id,
            kind=NodeType.STATE,
            data=NodeData(
                id=node_id,
                column=None,
                version=None,
                provenance=None,
                reads=(),
                dtype=neutral_dtype(None, column=node_id),
                shape=shape_from_dtype(None),
            ),
        )
        self._state_owners[node_id] = fingerprint
        logger.trace(f"Running-state node: {node_id}")
        return node_id

    def _bind(self, live: _LiveMap, name: str) -> NodeId:
        """Resolve one column reference to the node that defines it.

        A name with no live binding is one nothing accounts for: no
        calculation defined it, no column arrived under it, and it is not
        in the schema for a hole to have been seeded from. Two shapes
        reach here -- a record naming a column that never existed
        anywhere, a bug in whatever minted it, and a ``with_columns``
        call that failed on the caller's own expression, which the door
        records because the query plan already carried it -- so the fold
        binds the reference to a hole and says loudly that it did. Which
        of the two this is cannot be told from a name, so the warning
        does not try: the hole's own hint decides it in ``holes.py``,
        off the marked record, and would contradict this line if this
        line named a culprit.

        A hole rather than an input, because an input is a positive claim
        about where a number came from, and that claim is exactly what
        nothing here supports. Calling it an input put a name the model
        never held in front of a reviewer as a field the policy data
        supplied; a typo exported as data is the kind of thing nobody
        notices until someone asks where a number came from. The hole
        states what the fold actually observed and nothing beyond it.

        The live map is keyed by name, and one name can have belonged to
        two columns: an arriving column renamed or dropped away, and a
        later column written straight into the plan under the name it left
        behind. A record reading that name binds to whatever the frame
        holds under it now, which is the hole ``_seed_holes`` minted.
        Nothing keyed by name can tell the two apart, and the hole is the
        safer of them to point at -- it is the one that says the model
        cannot account for what is there.

        One name has no live binding and is not unaccounted for either:
        the column the rollforward kernel minted for itself. It is never
        in the live map -- the frame leaves it out of what the model
        failed to explain -- and what it names is a compilation rather
        than a column, so it binds to that compilation's node.

        Nor is a column the frame arrived holding that another frame
        calculated, read before the frame accounted for it again or dropped
        it. The fold knows exactly what that one is, so it binds to the
        hole that says so, minted now, and says nothing louder.
        """
        node_id = live.get(name)
        if node_id is not None:
            return node_id
        arrived = self._rebuilt_elsewhere.pop(name, None)
        if arrived is not None:
            dtype, origin = arrived
            live[name] = self._add_hole(name, dtype, _rebuilt_account(origin))
            return live[name]
        if _kernel_column(name):
            run = self._compilation_named_by(name)
            if run is not None:
                return self._compilation(run, _operands_of(run), live)
        warn(
            f"Nothing accounts for {name!r}: no calculation defines it and no "
            "input column has that name, so the calculation graph marks it as "
            "unexplained. Either the record of the calculation that reads it "
            "is wrong, or a with_columns() call failed on this name and was "
            "recorded as written, which is usually a misspelling. "
            "af.graph.holes() lists the column with what to check: the "
            "spelling where the failed call's record shows the failure, and "
            "the record itself where it does not."
        )
        live[name] = self._add_hole(name, None)
        return live[name]

    def _claim(self, node_id: NodeId, column: str) -> None:
        """Refuse to let one node id stand for two different things.

        An id is ``column@ordinal`` for a definition and the bare column
        name for an input -- and a Polars column name may itself contain an
        ``@``, so a column literally called ``policies_in_force@1`` claims
        the id the first write of ``policies_in_force`` needs. Taking the
        id anyway would drop one node and hand its edges to the survivor,
        in the one artifact whose whole job is to say truthfully which
        calculation fed which. Naming the clash is the smaller loss.

        Raises:
            ValueError: If ``node_id`` is already taken.

        """
        if node_id not in self.nodes:
            return
        msg = (
            f"Two columns both claim the calculation-graph node id "
            f"{node_id!r}: {self.nodes[node_id].data.column!r} and "
            f"{column!r}. A node id is the column name plus '@' plus which "
            "assignment it was, so a column whose own name contains '@' can "
            "collide with another column's version. Rename one of them."
        )
        raise ValueError(msg)

    def _claim_reserved(self, node_id: NodeId, what: str) -> None:
        """Refuse to let one reserved id stand for two different things.

        No column reaches here. A name in either namespace is refused at
        the door that would mint it (:func:`_refuse_reserved`), so nothing
        under ``state:`` or ``rollforward:`` is ever an account of a
        column, and this guard is not what keeps the namespaces reserved.

        What it does keep out is one reserved id claimed twice by two
        reserved things: two compiled rollforwards whose published
        identities agree across the twelve hex characters the id carries.
        They are two kernel runs and two state machines, and merging them
        into one node would report the second one's reads as the first
        one's, in the one artifact whose job is to say truthfully which
        calculation fed which.

        Raises:
            ValueError: If ``node_id`` is already taken.

        """
        if node_id not in self.nodes:
            return
        msg = (
            f"Two different things both claim the calculation-graph node id "
            f"{node_id!r}, which is reserved for {what}. A reserved id names "
            "one of them and the graph cannot say which, so it says neither. "
            "Two compiled rollforwards whose published fingerprints agree "
            "across the first twelve hex characters is the way this happens; "
            "changing either compilation moves its fingerprint and its id "
            "with it."
        )
        raise ValueError(msg)

    def _add_input(
        self, column: str, dtype: pl.DataType | None, provenance: Provenance
    ) -> NodeId:
        """Add the node standing for a column as the frame received it."""
        node_id = self._add_leaf(column, dtype, NodeType.INPUT, provenance)
        logger.trace(f"Input node: {column}")
        return node_id

    def _add_hole(
        self,
        column: str,
        dtype: pl.DataType | None,
        account: HoleAccount | None = None,
    ) -> NodeId:
        """Add the node standing for a column nothing on the frame explains.

        Unversioned, like an input, because nothing defined it -- and
        carrying no provenance, unlike an input, because that absence is
        the whole content of the node. The column's dtype is still known:
        what is missing is any account of how the values got there.
        ``account`` says what the fold saw of it; None is a column it saw
        nothing of but the name.
        """
        node_id = self._add_leaf(column, dtype, NodeType.HOLE, None)
        self.hole_accounts[node_id] = account or HoleAccount("unrecorded")
        logger.debug(
            f"No calculation and no arriving column accounts for {column!r}; "
            "recording it in the calculation graph as a hole."
        )
        return node_id

    def _add_overwrite(self, entry: OverwriteRecord, live: _LiveMap) -> None:
        """Add the hole one write past the frame's doors left, and make it live.

        The write defined the column, so the hole is one of the column's
        definitions: it takes the version the frame logged, as an assignment
        would, and the line of the write. It has no formula and no
        provenance, because the frame saw a plan and not a calculation, and
        a calculation written after it binds to it, which is where the
        values it reads came from. The node it replaced stays as history,
        named on the hole's account so the hint can quote it.
        """
        _refuse_reserved(entry.column)
        node_id = f"{entry.column}@{entry.ordinal}"
        self._claim(node_id, entry.column)
        self.nodes[node_id] = GraphNode(
            id=node_id,
            kind=NodeType.HOLE,
            data=NodeData(
                id=node_id,
                column=entry.column,
                version=entry.ordinal,
                reads=(),
                dtype=neutral_dtype(
                    entry.dtype, column=entry.column, values=self._values.get(node_id)
                ),
                shape=shape_from_dtype(entry.dtype),
                provenance=None,
                source_location=source_location(entry.source),
            ),
        )
        self.hole_accounts[node_id] = HoleAccount(
            "overwritten",
            replaced=live.get(entry.column),
            readable=entry.readable,
            rescanned=entry.rescanned,
        )
        self._definitions.setdefault(entry.column, []).append(node_id)
        live[entry.column] = node_id
        logger.debug(
            f"{entry.column!r} was written straight into the query plan over "
            "the frame's own account of it; recording that definition in the "
            f"calculation graph as the hole {node_id!r}."
        )

    def _add_leaf(
        self,
        column: str,
        dtype: pl.DataType | None,
        node_type: NodeType,
        provenance: Provenance | None,
    ) -> NodeId:
        """Add one unversioned node: a column nothing on this frame defines.

        Its id is the bare column name -- there is no ordinal to give it,
        which is exactly what distinguishes it from a definition. Nothing
        defined it, so it carries no version, and that is null rather than
        a number invented for it. Its provenance is where the values came
        from -- which for a column nothing accounts for is null, the whole
        content of that node.

        One of the two doors a column name reaches the graph through, so
        it is one of the two that refuses a name in a reserved namespace
        (:func:`_refuse_reserved`). An arriving column, and a column
        written straight into the query plan, both arrive here.

        A leaf's id is its column name, which is the key its values are
        held under too, so a wide integer column reaching here with the
        frame collected is named on its numbers.
        """
        _refuse_reserved(column)
        self._claim(column, column)
        self.nodes[column] = GraphNode(
            id=column,
            kind=node_type,
            data=NodeData(
                id=column,
                column=column,
                version=None,
                reads=(),
                dtype=neutral_dtype(
                    dtype, column=column, values=self._values.get(column)
                ),
                shape=shape_from_dtype(dtype),
                provenance=provenance,
            ),
        )
        return column

    def _add_definition(
        self,
        record: CalculationRecord,
        reads: tuple[NodeId, ...],
        read_as: tuple[ReadClaim, ...],
    ) -> NodeId:
        """Add the node standing for one record, already bound to what it reads.

        Two of these records are not calculations, and the node says so
        rather than dressing them as one.

        A record whose node is an injection is a whole column of values
        handed over at a known line, so it becomes an input -- and one
        shaped like every other input, with neither a formula nor an engine
        rendering. An input that reported either would show a reviewer
        something that reads as a derivation for a column that has none, and
        would leave "is this derived?" to be inferred from which fields
        happen to be filled in. What it carries that a model-point field
        cannot is where it arrived: the line, from the record's own source
        span.

        Every other record carries two accounts of what it computes, and
        they are not interchangeable. ``formula`` is the right-hand side as
        the author wrote it (see :func:`_as_written`), and it is the one a
        reviewer reads. ``lowered`` is the engine's rendering of the same
        calculation, cleaned of the file paths the engine prints into it,
        for a reader chasing what actually ran; it stays off the wire unless
        the export is asked for it, because it moves whenever the engine
        changes how it prints an expression and the artifact's own identity
        should not move with it.

        A record reaching into an engine's own expression language carries
        the engines that text needs, and says its period reference is
        unknown: every other node's timing can be read off its structure,
        and that text is the one thing the framework cannot read.

        The version and the recording door both come straight off the
        record. Which assignment this was is the same ordinal the node id
        carries, and restating it as a number is what saves a reader
        splitting an id that may contain an ``@`` of the column's own.

        Each edge says what kind of read it stands for, and the claim
        arrives already made: the classifier answers by column name and
        knows nothing of versions, so the caller that bound the names is
        the one place holding both halves at once. That is what tells a
        rate multiplied in and an age that only found it apart, without
        either of them having to be looked up twice.

        Args:
            record: The log entry this node stands for.
            reads: The node ids this record's formula bound to, in the
                order it names them.
            read_as: What kind of read each entry of ``reads`` is, one per
                entry.

        Returns:
            The id of the node minted for the record.

        Raises:
            ValueError: If the record's column is named into a reserved id
                namespace. This is the other door a column name reaches the
                graph through (:func:`_refuse_reserved`), and an ordinal on
                the end of the name does not take it back out of the
                namespace it begins in.

        """
        _refuse_reserved(record.column)
        node_id = f"{record.column}@{record.ordinal}"
        self._claim(node_id, record.column)
        injected = _is_injection(record.node)
        lowered = (
            None
            if injected
            else clean_expression_string(
                str(record.expr), comparisons=conditional_comparisons(record.expr)
            )
        )
        formula = None if injected else _as_written(record)
        # A record whose source span could not be resolved (stdin, an
        # exec-compiled snippet, a bare REPL) reports no location rather
        # than a made-up one; NodeData.source_location is optional for
        # exactly this.
        location = source_location(record.source)
        dtype = record.dtype
        engines = _engines_reached(record.node)
        self.nodes[node_id] = GraphNode(
            id=node_id,
            kind=NodeType.INPUT if injected else NodeType.COMPUTED,
            data=NodeData(
                id=node_id,
                column=record.column,
                version=record.ordinal,
                provenance=_provenance_of(record, injected=injected),
                reads=reads,
                formula=formula,
                lowered=lowered,
                source_location=location,
                # Keyed on the node rather than on the column: two
                # definitions of one name are two sets of values, and the
                # caller says which of them it is holding for each.
                dtype=self._definition_dtype(
                    dtype,
                    record.column,
                    node_id,
                    self._values_of(node_id, record, reads),
                ),
                shape=shape_from_dtype(dtype),
                engines=engines,
                period_reference="unknown" if engines else None,
                extracts=self._extracts(record.node),
            ),
        )
        self.op_trees[node_id] = record.node
        self.edges.extend(
            GraphEdge(
                source=read,
                target=node_id,
                relationship=claim.edge[0],
                subtype=claim.edge[1],
                offset=claim.offset,
                ways=claim.ways,
            )
            for read, claim in zip(reads, read_as, strict=True)
        )
        self._definitions.setdefault(record.column, []).append(node_id)
        logger.trace(f"Definition node: {node_id} reads {reads}")
        return node_id

    def _values_of(
        self, node_id: NodeId, record: CalculationRecord, reads: tuple[NodeId, ...]
    ) -> pl.Series | None:
        """Return the values one definition holds, where the fold has them.

        Its own, where the caller collected them. A definition that is a
        bare read of one other node -- a rename, which moves a column to a
        new name -- holds that node's values, so a wide arriving column
        renamed on the way in is named on the numbers read off the book, as
        the leaf it moved is, rather than refused on its width.
        """
        held = self._values.get(node_id)
        if held is not None or not isinstance(record.node, Col) or len(reads) != 1:
            return held
        moved = self._values.get(reads[0], self._moved.get(reads[0]))
        if moved is not None:
            self._moved[node_id] = moved
        return moved

    def _definition_dtype(
        self,
        dtype: pl.DataType | None,
        column: str,
        node_id: NodeId,
        values: pl.Series | None,
    ) -> str:
        """Return the name of one calculation's type, or what the fold does instead.

        A calculation is identified by what it computes, never by its type
        -- its fingerprint is taken over its operation tree -- so the type
        is a fact the exported document states about it and nothing that
        says whether the model accounts for it. A fold that answers the
        graph's questions therefore lets a type with no name through: the
        node says ``unknown`` and the refusal is kept in
        :attr:`unnamed_types`, for the export to meet again when it folds
        with ``refuse_unnamed`` on. A fold for the export refuses here, as
        it always has.

        Only a definition: a leaf is identified by its name *and* its type,
        so a leaf whose type has no name has no identity to answer with.
        """
        try:
            return neutral_dtype(dtype, column=column, values=values)
        except UnmappedDtypeError as refusal:
            if self._refuse_unnamed:
                raise
            self.unnamed_types[node_id] = refusal
            logger.debug(
                f"{node_id!r} has a type the calculation graph has no name "
                "for; the graph's questions answer without it, and the "
                "export refuses it by name."
            )
            return UNKNOWN

    def _extracts(self, node: OpNode) -> tuple[Extraction, ...] | None:
        """Return the running balances one record materialises, or None.

        A column assigned ``compiled.expr_for("fund")`` **is** the fund's
        running balance, written onto the frame. Nothing but the formula's
        text said so before this, and a consumer may not parse that text --
        so the column states what it extracts, and the forward audit
        questions in :mod:`calc_graph` read the statement rather than
        inferring it from a name.

        Read off the same walk that binds the record's reads
        (:func:`_references`), which is why the compilation an extraction
        names is always one of them: the two cannot come apart, because one
        walk produced both. The compilation node is already minted by the
        time this runs -- the caller binds the reads first -- so the
        fingerprint on the call resolves to an id the graph holds.

        **Only the state door is an extraction of a balance.** Of the three
        calls that read a compilation back out, ``rollforward.state`` is the
        one carrying a state and a point, and it is the one whose result is
        a balance. ``rollforward.increment`` reads back a signed *movement*,
        which is not a balance and which names no state on the call;
        ``rollforward.struct`` is refused at export with every other Struct
        (section 16.3), so no node ever carries one. Deriving the increment's
        target from the compilation's own summary was rejected: the movement
        the column holds is not the balance it landed on, and writing one as
        the other would put a wrong claim in the record that exists to be
        checked.

        De-duplicated on the pair, in first-mention order, for the reason
        ``reads`` is: a formula naming one balance twice materialised one
        balance.
        """
        found: dict[tuple[NodeId, str], Extraction] = {}
        for reference in _references(node):
            if not isinstance(reference, Call) or reference.name != STATE_EXTRACTION:
                continue
            compilation = self._compilations[_run_of(reference)]
            # StateRef.canonical_name() spells this on the way in and
            # classify_operand_expression parses it back out; the two typed
            # attributes are read here rather than any third reading of the
            # name, so the reference cannot drift by a character.
            state = (
                f"{_string_attr(reference, ROLLFORWARD_STATE_ATTR)}"
                f"@{_string_attr(reference, ROLLFORWARD_POINT_ATTR)}"
            )
            found.setdefault(
                (compilation, state),
                Extraction(compilation=compilation, state=state),
            )
        return tuple(found.values()) or None

    def _mark_materialized(self, boundary: BoundaryRecord, live: _LiveMap) -> None:
        """Keep one freeze, and record it on every definition it settled.

        The live map is exactly the set of definitions that were the frame's
        answer when the plan was frozen, so it is exactly the set the freeze
        turned into values -- a column the data arrived with as much as one
        the model computed. A definition written after the freeze was never
        frozen and says nothing; a definition already superseded keeps
        whichever earlier freeze it did live through.

        The stamp overwrites, and that is the rule rather than an accident
        of the loop. A column live at two freezes was frozen at both, and
        the later one is the one a reader needs: it is the freeze the value
        in front of them came out of.

        A hole is passed over, and reports null however early it was
        punched. ``_seed_holes`` puts every one of them in the live map
        before the walk begins, so a column written straight into the plan
        long after the freeze sits in that map at the freeze and would
        otherwise come off the wire claiming the freeze settled it. The
        producer cannot tell that column from one the plan already held:
        not seeing where a value came from is what makes a column a hole,
        and not seeing when it arrived is the same blindness asked about
        time. A null here says the producer looked and had nothing to go
        on, which is the truthful answer in both cases; a stamp would be
        seeding order reported as history.
        """
        ordinal = len(self.boundaries)
        self.boundaries = (*self.boundaries, boundary)
        for node_id in live.values():
            node = self.nodes[node_id]
            if node.kind is NodeType.HOLE:
                continue
            node.data.materialized_at = ordinal

    def _mark_final_schema(self, live: _LiveMap, schema: SchemaMap) -> None:
        """Flag the nodes that are what the frame's columns actually hold.

        One node per surviving column: the last thing that defined it, or
        the arriving value if nothing did. Every other node -- a superseded
        definition, a column dropped before the model finished, a name
        renamed away -- is history rather than an answer, and says so.
        """
        for column, node_id in live.items():
            if column in schema:
                self.nodes[node_id].data.in_final_schema = True


def _with_wide_arrivals_read(
    af: GraphSource, values: ValuesInReach | None
) -> ValuesInReach | None:
    """Return ``values`` with the book's wide columns read by their values.

    A book handed over as a DataFrame has its ``UInt64``, ``Int128`` and
    ``UInt128`` columns judged on their values where the frame is built:
    read as ``Int64`` where every value fits (section 10). A LazyFrame's are
    judged when its values are first read, and a fold with no values in
    reach read none, so the input leaf of a fitting identifier was refused
    on its width alone: the one book exported, fingerprinted and ran on an
    engine from one door and not the other. A wide column the book arrived
    with is read here off the book as it arrived -- as the book's digest
    already reads it -- so its leaf is named on its numbers: ``i64`` where
    every value fits, and refused naming the value where one does not, by
    either door. A computed column has no book to be read from, and is
    named on the values the caller holds or refused on its width.
    """
    book = af._arrival_data  # noqa: SLF001 -- the frame's own
    held = values or {}
    unread = [
        name
        for name, dtype in af._arrival_schema.items()  # noqa: SLF001 -- the frame's own
        if name not in held and wider_than_i64_at(dtype) is not None
    ]
    if book is None or not unread:
        return values
    read = book.select(unread).collect()
    return {**held, **{name: read.get_column(name) for name in unread}}


def fold(
    af: GraphSource,
    *,
    values: ValuesInReach | None = None,
    data_columns: Iterable[str] | None = None,
    refuse_unnamed: bool = True,
) -> CalcGraph:
    """Fold a frame's durable calculation log into its calculation graph.

    Seeds the graph with the columns the frame arrived with and the columns
    nothing accounts for, then walks the log once, minting one node per
    record and binding each record's column references to whichever
    definition was live when that record landed. See the module docstring
    for why the binding happens before the advance, why one multi-column
    call binds all of its records against the state that predates it, and
    what an unaccounted-for column is.

    Args:
        af: The frame whose log to fold. Its whole history is used, so a
            frame that carries a log forward from an earlier step (a
            renamed frame, a scenario axis) folds into the whole model's
            graph rather than only the part after that step.
        values: Each node's own output, where the caller collected it; see
            :data:`ValuesInReach`. A fold with nothing here still answers
            every structural question -- it is only the integer widths
            wider than ``i64`` that need the numbers, and without them they
            are refused rather than guessed at.
        data_columns: Which columns the policy data the model ran over
            actually carried, from a caller that watched the run start and
            therefore knows. None takes the frame's own word where it has
            one: a frame built while a batch runner or a scenario plan ran
            the model was told the book's columns by that runner
            (``_book_columns``). Where nobody watched, the frame's own
            arriving set is the only account there is of what arrived --
            see :func:`_columns_with_no_account` for what each of the two
            answers lets this fold say.
        refuse_unnamed: Whether a calculation whose type the vocabulary has
            no name for stops the fold. On, the default, for the fold an
            export writes from: the document states every type it names,
            so it refuses the one it cannot name, by column and with the
            cast that carries it. Off for a fold that only answers the
            graph's questions -- what is a hole, what reads what, which
            tier, what fingerprint -- none of which a calculation's type
            answers: its node says ``unknown`` and the refusal waits in
            :attr:`CalcGraph.unnamed_types`. A leaf is refused either way,
            because a leaf's type is half of what identifies it.

    Returns:
        The graph, its nodes in log order -- which is already a topological
        order.

    """
    told = _the_book_s_columns(af, data_columns)
    graph = CalcGraph(
        _with_wide_arrivals_read(af, values), refuse_unnamed=refuse_unnamed
    )
    # The frame's own schema, less the export's own scaffolding. The row
    # stamp is a column an export puts on the book so that a selected row
    # can be found again in the frame the model hands back
    # (:mod:`~gaspatchio.frame.graph.row_identity`): it is not a field of
    # the model points and it is not a calculation, so it is neither an
    # input nor a hole, and no node is minted for it. Taken out here rather
    # than at each seed, because the two seeds divide one set of names
    # between them and a name only one of them knew to skip would be minted
    # by the other -- which would put the scaffolding in every
    # ``graph_fingerprint`` this producer has ever written.
    schema: SchemaMap = {
        column: dtype
        for column, dtype in (af._schema or {}).items()  # noqa: SLF001 -- the frame's own schema
        if column != ROW_STAMP
    }
    unaccounted = _columns_with_no_account(af, told) | {ROW_STAMP}
    live = graph._seed_inputs(af, schema, unaccounted)  # noqa: SLF001 -- construction

    entries = list(af._calculations)  # noqa: SLF001 -- the frame's own log
    graph._seed_holes(af, schema, live, unaccounted)  # noqa: SLF001 -- construction
    groups = _operation_groups(entries)
    folded: set[int] = set()
    selections = _selections_by_position(af)
    for position, entry in enumerate(entries):
        graph._fold_selections(selections.pop(position, ()), live)  # noqa: SLF001
        if isinstance(entry, BoundaryRecord):
            graph._mark_materialized(entry, live)  # noqa: SLF001 -- construction
            continue
        if isinstance(entry, OverwriteRecord):
            graph._add_overwrite(entry, live)  # noqa: SLF001 -- construction
            continue
        if entry.operation_id in folded:
            continue  # already folded with the rest of the call it came from
        folded.add(entry.operation_id)
        graph._fold_operation(groups[entry.operation_id], live)  # noqa: SLF001
    # A step taken after the last entry of the log -- the ordinary place for a
    # filter written at the end of a model -- binds against the log's final
    # state, and so does one a frame positioned past an entry it no longer
    # holds.
    for position in sorted(selections):
        graph._fold_selections(selections[position], live)  # noqa: SLF001
    graph._mark_final_schema(live, schema)  # noqa: SLF001
    _stamp_the_holes_it_arrived_holding(graph, af, told)
    # Every node is minted, so nothing is left to measure. Dropped here
    # rather than kept as a field of the finished graph: a caller holding
    # the graph would otherwise hold the run's columns alive with it.
    graph._values = {}  # noqa: SLF001 -- construction state, released
    graph._moved = {}  # noqa: SLF001 -- as above
    graph._rebuilt_elsewhere = {}  # noqa: SLF001 -- as above
    logger.trace(
        f"Folded {len(entries)} log entries into {len(graph.nodes)} nodes "
        f"and {len(graph.edges)} edges"
    )
    return graph


def _the_book_s_columns(
    af: GraphSource, data_columns: Iterable[str] | None
) -> frozenset[str] | None:
    """Return the columns the policy data carried, from the caller or the frame.

    The caller's word wins: ``gspio calc-graph`` read the file and then
    started the run. Failing that, the frame's own: a frame built while a
    batch runner or a scenario plan ran the model was told the book's
    columns by it, and carries them through every step after (a frame
    the setup rebuilt with ``ActuarialFrame(df)`` included, which is the
    frame that needs telling). None where nobody watched the run begin.
    """
    if data_columns is not None:
        return frozenset(data_columns)
    held: frozenset[str] | None = getattr(af, "_book_columns", None)
    return held


def _stamp_the_holes_it_arrived_holding(
    graph: CalcGraph, af: GraphSource, data_columns: frozenset[str] | None
) -> None:
    """Stamp each hole the frame arrived holding with its values' content digest.

    Two kinds of hole stand for a column the frame was handed: a
    ``rebuilt`` one, whose values another frame calculated, and an
    ``unrecorded`` name the policy data never had -- a column the setup
    made in Polars and handed to a fresh frame. The frame cannot say what
    made either, and it holds what each held when it arrived (the data
    the frame was built over, ``_arrival_data``). The stamp is section
    12.3's content grammar over that one column, read as the book is read,
    so the model's identity moves when the file the setup joined is edited
    and stays where it was when the file is not.

    An ``overwritten`` hole and a name no frame held are not stamped: the
    values of the first are a write's that the frame never held as an
    arrival, and the second has none. A hole whose values cannot be read
    keeps its name alone, as every hole did before, and says so in the log.
    """
    never_had = (
        af._bare_arrivals - data_columns  # noqa: SLF001 -- the frame's own
        if data_columns is not None
        else frozenset()
    )
    arrived: dict[NodeId, str] = {}
    for node_id, account in graph.hole_accounts.items():
        column = graph.nodes[node_id].data.column
        if column is None:
            continue
        if account.reason == "rebuilt" or (
            account.reason == "unrecorded" and column in never_had
        ):
            arrived[node_id] = column
    book = af._arrival_data  # noqa: SLF001 -- the frame's own
    if not arrived or book is None:
        return
    held = set(book.collect_schema().names())
    wanted = sorted({column for column in arrived.values() if column in held})
    if not wanted:
        return
    try:
        values = with_integers_as_i64(book.select(wanted).collect())
        stamps = {
            column: digest_of_inputs(values.select(column), [column])
            for column in wanted
        }
    except (pl.exceptions.PolarsError, OSError, ValueError) as unread:
        logger.warning(
            f"The values of {wanted} as the frame arrived holding them could not "
            f"be read ({unread}); each is recorded as a hole by name alone."
        )
        return
    for node_id, column in arrived.items():
        stamp = stamps.get(column)
        if stamp is not None:
            graph.hole_accounts[node_id] = replace(
                graph.hole_accounts[node_id], content=stamp
            )


def _selections_by_position(
    af: GraphSource,
) -> dict[int, tuple[SelectionRecord, ...]]:
    """Return the frame's selection steps, grouped by where in the log each was taken.

    A frame built before selections were recorded, or a structural view that
    does not carry them, has none.
    """
    grouped: dict[int, list[SelectionRecord]] = {}
    for record in getattr(af, "_selections", ()):
        grouped.setdefault(record.position, []).append(record)
    return {position: tuple(records) for position, records in grouped.items()}


def _columns_with_no_account(
    af: GraphSource, data_columns: Iterable[str] | None
) -> frozenset[str]:
    """Return every column this graph can give no account of.

    Three parts. The frame's own answer is the first and the settled one:
    a column in its schema that no record defines and that did not arrive
    with its data has no account of itself, and ``_unaccounted_columns`` is
    the one place that difference is taken.

    The second is a column the frame arrived holding that another frame
    calculated, which the frame found by memory when it was built
    (``_rebuilt``). It is a hole for the frame's own reason -- it did not
    come from the data -- and the frame's own answer already holds it for
    as long as it stands on the frame unaccounted for, as it holds any
    other column. Once the frame accounts for it again or drops it, it is
    a hole only where a calculation read it first, which the fold decides
    as it meets that read (``CalcGraph._bind``).

    The third is the rebuild the frame could not see, and it needs a
    caller who watched the run begin. The setup step every model author is
    taught -- collect, rename the columns in Polars, hand the DataFrame to
    ``ActuarialFrame(mp)`` -- produces a frame with an empty log whose
    arriving set is everything that DataFrame held: the columns of the
    file, plus whatever the model calculated before the rebuild, plus
    whatever the Polars statement created. Memory tells the frame about
    the second of those while the earlier values are still held; it
    cannot tell it about the third, and once the memory is gone, not
    about the second either.

    So the fact that closes the gap comes from outside: ``data_columns``
    is what the policy data carried, from a caller that read the file and
    then started the run over it. A name in the frame's bare arriving set
    that the data never carried did not come from the data, and no record
    accounts for it either -- which is section 7.1's first hole exactly, "a
    column that is on the frame with no account of itself anywhere in what
    the model logged". It is reported as ``unrecorded``: from its name
    alone, a column a Polars statement made and one an earlier frame
    calculated look the same, and a reason code that guessed would be
    worse than the one it can defend.

    **Only the bare arriving set is compared**, never the whole of
    ``_arrival_names``. A derivation step widens that -- a cross-joined
    scenario axis brings a ``scenario_id`` the file never carried -- and
    those arrivals are steps the log watched and can vouch for. Measuring
    them against the file would report an honest input as a hole.

    None for ``data_columns`` is a caller who cannot say, and then nothing
    is added: the frame's arriving set stands as the account of what
    arrived, which for a frame built straight from a table is exactly what
    it is.
    """
    own = af._unaccounted_columns()  # noqa: SLF001 -- its own
    if data_columns is None:
        return own
    return own | (af._bare_arrivals - frozenset(data_columns))  # noqa: SLF001


def _operation_groups(
    entries: list[LogEntry],
) -> dict[int, list[CalculationRecord]]:
    """Group the log's records by the call each one came from.

    Membership is the operation id the records themselves carry -- the
    transaction boundary recorded as data at assignment time -- and never
    how close together two records happen to sit in the log.
    """
    groups: dict[int, list[CalculationRecord]] = {}
    for entry in entries:
        if isinstance(entry, CalculationRecord):
            groups.setdefault(entry.operation_id, []).append(entry)
    return groups
