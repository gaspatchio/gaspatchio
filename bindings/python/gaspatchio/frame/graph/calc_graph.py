# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Reading a model's calculation graph: the query surface and the export.

The fold turns a frame's durable calculation log into one node per
definition. This module is what reads those nodes back:

- ``af.graph`` -- :class:`GraphFrameAccessor` -- is the surface an actuary
  or an assistant touches. Its questions are all structural: what did this
  column read, who read it, what is the whole cone behind it, what would
  move with it, which versions of the name exist, which one is live, what
  can the model not account for, which of its lines are written outside the
  format's own vocabulary, and what is this model's content-addressed
  identity.
- :class:`GraphExporter` writes the same graph out as JSON, enriched with
  sample values and per-node traces from a collected frame, for the
  ``gspio calc-graph`` command and anything that visualizes a model.

Nothing on the accessor runs the model. Every answer comes from the log
and the frame's schema, so asking how a number was made never costs
computing one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

import polars as pl
from loguru import logger

from gaspatchio._dtypes import neutral_dtype
from gaspatchio._identity import SHA256_PREFIX
from gaspatchio._semantic.ir import BinOp, WhenThen
from gaspatchio._semantic.operations import BINARY_OPERATIONS
from gaspatchio._shape import shape_from_dtype
from gaspatchio._source import SourceSpan
from gaspatchio.frame.calculation_log import _RETAINED_PREFIX, _retained_column_name
from gaspatchio.frame.calculations import CalculationRecord, OverwriteRecord

from ._model_files import revision_notice
from .artifact import (
    _DOCUMENT_INDENT,
    ARTIFACT_FILE_NAME,
    PAYLOAD_DIRECTORY,
    SEAL_BY_DEFAULT,
    SOURCE_DIRECTORY,
    TABLE_PAYLOAD_LIMIT,
    _tier_of,
    _tree_of,
    build_artifact,
    payload_bytes,
    payload_file_name,
    refusal_for_a_number_json_cannot_hold,
    source_payload_of,
)
from .assumptions import ArtefactReference, payload_of
from .filter_handler import DataFrameFilter
from .fingerprint import graph_fingerprint, stamp_fingerprints
from .graph_builder import CalcGraph, ValuesInReach, fold
from .graph_models import (
    GraphExportConfig,
    GraphNode,
    ModelIdentity,
    NodeId,
    NodeType,
    _document_root,
    root_of_the_files_read,
)
from .holes import Hole, holes_in
from .lineage import Lineage, Unused
from .rollforward_movements import MOVEMENT_PREFIX, Readings, read_the_movements
from .row_identity import ROW_STAMP, LocatedRow, locate_the_selection
from .tiers import _census_of
from .trace_generator import NOTHING_FOLDED, FoldReading, TraceGenerator
from .value_extractor import SampleValueExtractor, one_value_on_the_wire
from .xlsx_export import render_xlsx

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.engines.report import RunSummary
    from gaspatchio.frame.graph.frame_view import GraphSource
    from gaspatchio.frame.lowering.context import LoweringContext

    from .portfolio import PortfolioFold
    from .tiers import TierCensus

# The one fold a per-period movement has a meaning under, as the framework
# spells the aggregator: the book's movement at each period. Every other
# aggregation on the axis either reduces a timeline away or is a fold the
# waterfall identity does not survive.
_THE_FOLD_A_MOVEMENT_HAS: Final[str] = "period_sum"

# The two working names the book's fold builds a period index under. They
# live for the length of one lazy frame and reach no document.
_ROW: Final[str] = "__rf_fold_row"
_PERIOD: Final[str] = "__rf_fold_period"

# How many sub-expressions the fold probe looks at before it gives up. A
# model's line is a handful of operations deep; a tree deeper than this is
# one nothing here could characterise anyway, and the cap is what stops a
# pathological expression from turning an export into a walk of its own
# query plan.
_SUBEXPRESSIONS_PROBED = 64

# What the engine calls a window in its own account of an expression. An
# aggregate under one of these folded a group's rows rather than the
# export's, which is a different population and a different sentence.
_A_WINDOW = "Over"

# The expression the control question below is asked of. Written here, by
# this build, out of the operations a window is made of, so that what it
# means is not in doubt: it is a window, and an account of it that does not
# name one is an account this build cannot read.
_A_KNOWN_WINDOW = pl.col("x").sum().over("g")

# The window spellings this build has proved the engine still writes.
# **Positive answers only, and deliberately.** A build that has once read
# its own control has an engine whose spelling is what this module says it
# is, and that does not change under it; a negative answer can come from a
# refusal that is not about the spelling at all, and freezing one would
# silence every window reading for the life of the process on the strength
# of a single failed serialization. Re-asking costs one small expression's
# account -- microseconds -- so the asymmetry is free.
_WINDOWS_THIS_BUILD_CAN_READ: Final[set[str]] = set()

# Whose rows an aggregate found inside a line folded, as far down the
# expression as the descent has got. **Three answers, not two.** "This build
# could not read the engine's account of the expression" is not the same
# answer as "there is no window here", and the difference matters because
# the second one is spent naming the export's whole population -- a claim
# about which policies a total ran over. A probe that answers the widest
# population where it read nothing at all is not failing safe; it is
# printing the falsehood the probe exists to prevent.
_Scope = Literal["model_points", "a_group", "unnamed"]
_MODEL_POINTS: _Scope = "model_points"
_A_GROUP: _Scope = "a_group"
_UNNAMED: _Scope = "unnamed"

# The two words a conditional's ``fired`` is written in, spelled once so
# that the producer, the schema and the refusal that reads them cannot
# spell one branch two ways. They are the names the formula itself uses --
# ``when(...).then(...).otherwise(...)`` -- rather than "true" and "false",
# because what a reader is looking for is the line they wrote.
_THEN: Final[str] = "then"
_OTHERWISE: Final[str] = "otherwise"

# The operators that make a comparison, off the same table the lowering
# reads them from. A branch that is one of these is an indicator in value
# position, and stating it any other way would put a boolean in the record
# where the column would have held 1.0.
_COMPARISONS: Final[frozenset[str]] = frozenset(
    operation.identifier
    for operation in BINARY_OPERATIONS
    if operation.family == "comparison"
)


def _could_fold_down_the_model_points(node: GraphNode) -> bool:
    """Whether this node is even the kind of line that could fold the rows.

    **Nothing the format names folds down the model points.** Its two
    accumulations are along one policy's own period axis and along nothing
    else (specification 11.1.9), and every other operation in the
    vocabulary works one value at a time. So a line that reduces the
    population to one number reaches an artifact as an engine fragment --
    there is no identifier for it to be recorded under -- and a node whose
    formula reaches into no engine at all cannot be one.

    That is a fact about the vocabulary rather than a shortcut, and it is
    also what keeps the probe below off the ordinary node: a hundred-column
    projection asks the engine about the handful of lines that could
    possibly answer yes, not about every multiplication in it.
    """
    return bool(node.data.engines)


def _the_engine_names_its_windows(spelling: str) -> bool:
    """Whether an account of a known window carries ``spelling`` as its key.

    The control question, and the whole of what makes the reading below
    fail safe. Finding the key in a real expression's account is evidence of
    a window only while the key is the one the engine writes: an engine that
    renamed it answers every windowed expression exactly the way it answers
    one with no window in it, and *that* answer is spent handing the descent
    the export's whole population. The probe would then print a total over
    one product as a fold over every model point in the file -- the
    falsehood it exists to remove, arriving through its own recognition
    step, silently, with nothing in the document to say so.

    Asking of a real expression cannot tell those two apart. Asking of one
    this build wrote itself can: :data:`_A_KNOWN_WINDOW` *is* a window, so
    an account of it that does not carry the key means the key has moved.
    Where it has, this build cannot read windows at all, and every window
    answer degrades to the population this export cannot name -- saying
    less, never the whole book.

    Cheap enough to be unconditional: one small expression serialized once
    per spelling per process, and the answer is a set membership after that.
    """
    if spelling in _WINDOWS_THIS_BUILD_CAN_READ:
        return True
    try:
        control = json.loads(_A_KNOWN_WINDOW.meta.serialize(format="json"))
    except Exception as e:  # noqa: BLE001 -- a control that cannot be read is a no
        logger.trace(f"Could not read the engine's account of a known window: {e}")
        return False
    if not (isinstance(control, dict) and spelling in control):
        logger.trace(
            f"This build's window key {spelling!r} is not one the engine writes"
        )
        return False
    _WINDOWS_THIS_BUILD_CAN_READ.add(spelling)
    return True


def _rows_below(expr: pl.Expr, above: _Scope) -> _Scope:
    """Return whose rows an aggregate underneath ``expr`` folded.

    ``af.claims.polars_native().sum().polars_native().over("product")`` totals the
    policies of one product
    and still answers once per policy, so it is not a fold down the model
    points and must not be announced as one. The height test says so at the
    outermost level all by itself -- a grouped select over no rows yields no
    rows -- but the descent below walks *into* that expression, where the
    aggregate it is scoped by looks exactly like a whole-book total.

    So the window is recognised where the engine itself names it, in its own
    account of the expression, rather than in the text a rendering happens
    to print.

    **A serialization this build cannot read narrows the sentence rather
    than widening it.** Answering "no window" there is not neutral: it hands
    the descent the export's whole population, and the walk-through then
    prints a group total as a fold over every model point in the file --
    which is the falsehood this probe was written to remove, restored by its
    own failure route. So an unreadable account is its own answer, and what
    it reaches says the operand folded without saying whose rows it folded
    over.

    **And a readable account is only evidence while the key is current.**
    An engine that renamed its window key answers a windowed expression the
    way it answers one with no window in it, so the absence of the key is
    two different facts with one spelling. :func:`_the_engine_names_its_windows`
    is what separates them: it asks the same question of an expression this
    build wrote and knows to be a window, and where *that* comes back
    without the key the reading below is not made at all -- every answer
    degrades to the population this export cannot name, which is the same
    discipline the unreadable-account route already follows.

    A window found under an unreadable parent still scopes what is inside
    it: the engine named that one, whatever could not be read above it. And
    a window already passed through stands -- an aggregate inside a group is
    inside that group however deep the descent goes.
    """
    if above == _A_GROUP:
        return above
    if not _the_engine_names_its_windows(_A_WINDOW):
        return _UNNAMED
    try:
        rendered = json.loads(expr.meta.serialize(format="json"))
    except Exception as e:  # noqa: BLE001 -- a probe that fails names no population
        logger.trace(f"Could not read the engine's account of an expression: {e}")
        return _UNNAMED
    if isinstance(rendered, dict) and _A_WINDOW in rendered:
        return _A_GROUP
    return above


def _folds_the_frame_away(expr: pl.Expr, empty: pl.DataFrame) -> bool:
    """Whether this one expression turns the frame's rows into a single value.

    The test is the definition rather than a reading of the expression's
    text: an operation that turns a column into one value for the frame
    yields one row from a frame that has none, and an operation that works
    a row at a time yields none. So the probe is a select against the
    frame's own schema with its rows taken away, which computes nothing
    over any real data and stays true for a release that renames a method.

    An expression naming no column is never a fold, whatever its height:
    ``pl.lit(0)`` yields one row from an empty frame because a literal is
    one value, not because it summed anything.

    A fragment the engine refuses over no data says nothing either way, and
    False is what says nothing here: the caller keeps the walk-through it
    would otherwise have withheld.
    """
    try:
        return bool(expr.meta.root_names()) and empty.select(expr).height == 1
    except Exception as e:  # noqa: BLE001 -- a probe that fails makes no claim
        logger.trace(f"Could not probe a sub-expression for a fold: {e}")
        return False


def _fold_reading(expr: pl.Expr, empty: pl.DataFrame) -> FoldReading:
    """Return what folds in this expression, and whether the line is one.

    The question a walk-through has to answer before it substitutes
    anything. A trace replaces each column name with the value that column
    held *for the sampled policy*, and that statement is true exactly where
    the sampled policy's own values are what the calculation ran over. A
    fold down the model-point file -- a portfolio total, a mean the whole
    book is measured against -- ran over every row, so one row's number put
    inside it is arithmetic that does not produce its own stated result.

    **A fold inside a line is not the line being a fold.**
    ``af.share = af.claims / af.claims.polars_native().sum()`` answers once per policy:
    the
    sampled policy's own share is what it reached, and a step announcing a
    fold would contradict the result printed under it. So the line's own
    reading is the outermost expression alone, and what the descent finds
    inside is used for the other job -- naming the operands no number may
    stand for.

    The descent is the engine's own account of an expression's inputs
    (``meta.pop()``), which is how ``claims - claims.mean()`` is caught at
    depth. It stops at a folding sub-expression, since everything under one
    is inside it, and it carries whose rows it has passed under: an
    aggregate scoped to a group folded the group's rows and not the
    export's, and an aggregate under an account this build could not read
    folded rows this export cannot name.

    Args:
        expr: The engine expression the column was computed with.
        empty: The finished frame with its rows taken away, carrying the
            schema every column in ``expr`` resolves against.

    Returns:
        The reading. Empty tuples and a False outermost where every part of
        the expression works a row at a time.

    """
    outermost = _folds_the_frame_away(expr, empty)
    folded: dict[_Scope, list[str]] = {_MODEL_POINTS: [], _A_GROUP: [], _UNNAMED: []}
    pending: list[tuple[pl.Expr, _Scope]] = [(expr, _MODEL_POINTS)]
    probed = 0
    while pending and probed < _SUBEXPRESSIONS_PROBED:
        current, scope = pending.pop()
        probed += 1
        if _folds_the_frame_away(current, empty):
            folded[scope].extend(_names_read(current))
            continue
        below = _rows_below(current, scope)
        try:
            pending.extend((child, below) for child in current.meta.pop())
        except Exception as e:  # noqa: BLE001 -- a probe that fails makes no claim
            logger.trace(f"Could not read a sub-expression's own inputs: {e}")
    return FoldReading(
        outermost=outermost,
        over_the_model_points=tuple(dict.fromkeys(folded[_MODEL_POINTS])),
        over_a_group=tuple(dict.fromkeys(folded[_A_GROUP])),
        over_an_unnamed_population=tuple(dict.fromkeys(folded[_UNNAMED])),
    )


def _names_read(expr: pl.Expr) -> list[str]:
    """Return the columns one expression reads, or nothing where it cannot say."""
    try:
        return list(expr.meta.root_names())
    except Exception as e:  # noqa: BLE001 -- a probe that fails makes no claim
        logger.trace(f"Could not read the columns a sub-expression names: {e}")
        return []


def _reads_a_replaced_value(graph: CalcGraph, node: GraphNode) -> bool:
    """Whether ``node`` read a value the finished frame no longer holds.

    Sample values are read out of the collected frame, one per column, so
    they can only speak for the node each column actually ended up holding.
    A node that read a version something later replaced -- death claims
    taken on the inforce *before* the maturity zeroing, say -- has no value
    in that frame for what it actually read, and substituting the column's
    surviving value would put the replacement into the trace: arithmetic
    that does not produce its own stated result, against a formula and a
    ``reads`` list that both say otherwise.

    So the numeric walk-through is withheld for those nodes. The formula,
    the reads and the source location all stay -- what the node computed is
    still fully stated; only the numbers that would have to be invented are
    absent.
    """
    return any(not graph.nodes[read].data.in_final_schema for read in node.data.reads)


def _columns_read(graph: CalcGraph, node: GraphNode) -> list[str]:
    """Return the column names ``node`` read, in the order its formula names them.

    A trace substitutes sample values into a formula, and a formula names
    columns rather than node ids -- so the names are read back off the nodes
    the bindings point at, rather than kept a second time beside them. Two
    lists of the same references, one by id and one by name, are two lists
    that can disagree, and the one that says which *definition* was read is
    the one worth keeping.

    A read of something that is not a column -- a compiled rollforward --
    names nothing for a trace to substitute, and is left out rather than
    given a name it does not have.
    """
    return [
        name
        for read in node.data.reads
        if (name := graph.nodes[read].data.column) is not None
    ]


def _branches_of(
    graph: CalcGraph,
    node: GraphNode,
    *,
    context: LoweringContext,
    extractor: SampleValueExtractor,
) -> dict[str, Any] | None:
    """Return what each branch of ``node``'s conditional held, or None.

    None on every node whose whole calculation is not a conditional, which
    is most of them, and the absence is the statement: a node with one
    answer has no second one to show.

    **The outer conditional only.** A conditional nested inside a branch is
    part of what that branch evaluates to, and states nothing of its own:
    ``when(a).then(0).otherwise(when(b).then(c).otherwise(d))`` states two
    branches -- the ``0`` and whatever the inner conditional came to --
    because two is what the reader is choosing between at this line.

    **Only where the frame still holds the answer.** A superseded
    definition's inputs may have been written over between its line and
    the collect, so a branch of one evaluated here would be evaluated
    against the values that replaced them: the right formula over the
    wrong numbers, which is the failure retention exists to avoid. Those
    nodes state nothing.

    None again where the engine cannot evaluate a branch at all -- a
    column the finished frame no longer holds, a lowering that refuses, an
    engine-native fragment in a language this producer does not run. The
    reason goes to the log at trace level and the node carries no
    ``branches``, because a node that states one branch and not the other
    states nothing a reader can compare.
    """
    if not node.data.in_final_schema:
        return None
    tree = _tree_of(graph, node)
    if not isinstance(tree, WhenThen):
        return None
    try:
        then = extractor.extract_expression(_branch_expression(tree.then, context))
        otherwise = extractor.extract_expression(
            _branch_expression(tree.otherwise, context)
        )
        chosen = extractor.extract_expression(_condition_expression(tree.cond, context))
    except Exception as error:  # noqa: BLE001 — a branch that cannot be evaluated is unstated
        logger.trace(f"Could not evaluate the branches of {node.data.id}: {error}")
        return None
    sample = node.data.value_sample
    periods = len(sample) if isinstance(sample, list) else None
    return {
        "then": _over_the_same_periods(then, periods),
        "otherwise": _over_the_same_periods(otherwise, periods),
        "fired": _which_branch_fired(chosen, periods),
    }


def _branch_expression(branch: OpNode, context: LoweringContext) -> pl.Expr:
    """Lower one branch of a conditional the way the conditional lowered it.

    A branch that is itself a comparison is an actuarial indicator in this
    position -- "1.0 in the months this policy is in force" -- and lowers
    to the Float64 mask the frame would have stored, not to a boolean. Any
    other branch lowers plainly. The split is the one
    ``frame/lowering/polars.py`` makes between a value position and a
    predicate one, made here for the same reason: what goes in the record
    has to be what the column would have held.
    """
    from gaspatchio.frame.lowering.polars import (  # noqa: PLC0415 — import cycle
        lower_mask,
        lower_polars,
    )

    if isinstance(branch, BinOp) and branch.op in _COMPARISONS:
        return lower_mask(branch, context)
    return lower_polars(branch, context)


def _condition_expression(cond: OpNode, context: LoweringContext) -> pl.Expr:
    """Lower a conditional's condition to the mask the conditional selects on.

    The 0/1 form rather than the boolean one, and for a reason a boolean
    cannot meet: a per-period condition is a comparison the engine refuses
    to make natively -- a list against a scalar -- so the framework's own
    conditional routes it through the same kernel this does. One reading
    for both shapes, and it is the reading the model ran under.
    """
    from gaspatchio.frame.lowering.polars import (  # noqa: PLC0415 — import cycle
        lower_mask,
    )

    return lower_mask(cond, context)


def _over_the_same_periods(value: Any, periods: int | None) -> Any:  # noqa: ANN401 — one evaluated value, of whatever type it holds
    """Return ``value`` shaped like the sample it stands beside.

    A branch may be one value where the column is a run of them --
    ``.otherwise(0.0)`` on a per-period column is the literal zero, not a
    timeline of zeros -- and a reader comparing period 37's answer with
    period 37's alternative should index both the same way. So a single
    value on a per-period node is written across the periods it would have
    held for. ``periods`` is None wherever the sample is one value, which
    is a per-policy column, and a pinned period, which narrowed the sample
    to one already.
    """
    if periods is None or isinstance(value, list):
        return value
    return [value] * periods


def _which_branch_fired(chosen: Any, periods: int | None) -> Any:  # noqa: ANN401 — a mask, of one period or of every period
    """Name the branch the condition chose, per period where there are periods.

    The condition lowers to the same 0/1 mask the conditional selects on,
    so 1.0 is the ``then`` branch and everything else -- 0.0, and the null
    a comparison against a missing value comes to -- is the ``otherwise``
    one, which is what the engine itself does with each.

    A condition that does not vary by period on a column that does is
    written across the periods anyway: the word beside period 37's value
    is the word that decided period 37.
    """
    if isinstance(chosen, list):
        return [_the_branch(one) for one in chosen]
    word = _the_branch(chosen)
    return [word] * periods if periods is not None else word


def _the_branch(mask: Any) -> str:  # noqa: ANN401 — one value of the condition's mask
    """Return the branch one value of the condition's mask selects."""
    return _THEN if mask == 1.0 else _OTHERWISE


@dataclass(slots=True)
class _TraceBatch:
    """Hold the values and successful trace count shared by one export.

    The exporter owns setup and the count of computed nodes. This object owns
    the state passed to ``_attach_trace``, which owns each node's eligibility,
    substitution, fold context and attachment under the existing error boundary.
    """

    graph: CalcGraph
    generator: TraceGenerator
    node_values: dict[str, Any]
    # The run each retained superseded definition produced, by node id rather
    # than by column: two definitions of one column share a name, so the
    # column-keyed map above can only ever hold the live one's values.
    retained_values: dict[NodeId, Any]
    expressions: dict[NodeId, pl.Expr]
    empty: pl.DataFrame
    trace_count: int = 0


def _attach_trace(batch: _TraceBatch, node_id: NodeId, node: GraphNode) -> None:
    """Attach a truthful trace to ``node`` when its values support one.

    A trace is a walk-through written beside a value the node already holds,
    so one the renderer cannot write never fails the export: the node keeps
    its value, carries no ``trace``, and a warning names it.
    """
    if node.data.value_sample is None:
        logger.trace(f"Skipping trace for {node_id}: no sample value")
        return
    if _reads_a_replaced_value(batch.graph, node):
        logger.trace(
            f"Skipping trace for {node_id}: it read a value the "
            "finished frame no longer holds"
        )
        return
    rendered = node.data.lowered
    if rendered is None:
        logger.trace(f"Skipping trace for {node_id}: no expression")
        return

    expr = batch.expressions.get(node_id)
    # A retained definition's own run first: the column-keyed map below holds
    # the live definition's values under the same name, and substituting
    # those here would end the walk-through at the number that replaced this
    # node's rather than at the number this node produced. Then the whole run
    # where this node is a column and the frame still holds it; the sample
    # otherwise, which is what a node that is not an account of a column has.
    column = node.data.column
    whole = batch.retained_values.get(node_id)
    if whole is None:
        whole = (
            batch.node_values.get(column, node.data.value_sample)
            if column is not None
            else node.data.value_sample
        )
    folds = (
        _fold_reading(expr, batch.empty)
        if expr is not None and _could_fold_down_the_model_points(node)
        else NOTHING_FOLDED
    )
    try:
        trace = batch.generator.generate_trace(
            rendered,
            _columns_read(batch.graph, node),
            whole,
            folds=folds,
            tree=batch.graph.op_trees.get(node_id),
        )
        node.data.trace = trace
        batch.trace_count += 1
        logger.trace(f"Generated trace for {node_id} with {len(trace)} steps")
    except Exception as e:  # noqa: BLE001 -- a trace never fails the export (docstring above): the renderer formats arbitrary written formulas, the node keeps its value, and this warning names the node
        logger.warning(f"Failed to generate trace for {node_id}: {e}")


def _what_each_node_held(graph: CalcGraph) -> dict[NodeId, dict[str, Any]]:
    """Return one policy's enrichment, lifted off the graph before the next pass.

    ``value_sample`` and ``trace`` are taken from every node, including the
    nodes holding neither: a null at a position of the axis says this policy
    had nothing there, and a field present in one policy's mapping and
    missing from another's would leave the two arrays a different length
    from the axis they are read against.

    ``branches`` is taken only where the node states them. Absent says one
    of the three things section 8 lists -- nobody asked, the node is not a
    conditional, the producer could not evaluate a branch -- and a null
    written for every node of a document nobody asked branches of would
    claim the third of those about every calculation in the model.
    """
    held: dict[NodeId, dict[str, Any]] = {}
    for node_id, node in graph.nodes.items():
        one: dict[str, Any] = {
            "value_sample": node.data.value_sample,
            "trace": node.data.trace,
        }
        if node.data.branches is not None:
            one["branches"] = node.data.branches
        # Only where there are any. ``movements`` is a member of one kind of
        # node, and a null written for every column of the model would read
        # as a producer that looked for a state machine's movements in a
        # multiplication and found none.
        if node.data.movements is not None:
            one["movements"] = node.data.movements
        held[node_id] = one
    return held


def _enhance_with_movements(
    graph: CalcGraph,
    df: pl.DataFrame,
    config: GraphExportConfig,
    readings: Readings,
) -> None:
    """Put one policy's movements and closing balances on the graph.

    Read through the same extractor the columns are read through, so the
    export's own period narrowing reaches them: a document pinned to one
    period carries that period's movement beside that period's balance,
    and one that is not carries the whole timeline of each.

    A running state's closing balance goes where every other value goes --
    ``value_sample`` -- because it is one, and its ``shape`` stops being
    ``unknown`` in the same breath. Its ``dtype`` does not move, and that
    is deliberate rather than an omission: a leaf's type is inside its
    canonical bytes (section 12.1), so naming it here would move the
    state's two digests, the compilation's, and the ``graph_fingerprint``
    of every model that ever compiled a rollforward -- for a reading the
    format does not hash and did not change.
    """
    if not readings.carries_anything():
        return
    extractor = SampleValueExtractor(
        df, config.policy_id, config.policy_id_column, config.period, config.row_pin
    )
    for node_id, keyed in readings.movements.items():
        node = graph.nodes.get(node_id)
        if node is None:
            continue
        moved = {key: extractor.extract(column) for key, column in keyed.items()}
        node.data.movements = {
            key: amount for key, amount in moved.items() if amount is not None
        } or None
    for node_id, column in readings.closing.items():
        node = graph.nodes.get(node_id)
        if node is None:
            continue
        balance = extractor.extract(column)
        if balance is None:
            continue
        node.data.value_sample = balance
        node.data.shape = shape_from_dtype(df.schema[column])


def _what_the_book_came_to(
    graph: CalcGraph, fold: PortfolioFold, readings: Readings, book: pl.DataFrame
) -> dict[NodeId, dict[str, Any]]:
    """Return one fold's entry of the axis, keyed by the nodes it covers.

    Only ``value_sample``, and only on the nodes whose column the fold
    covered. Everything else is absent, and the wire writes a null at this
    entry's position for it -- which is the honest thing and the only
    honest thing. There is no portfolio value of a monthly mortality rate,
    so the file states none rather than a figure it made up by summing a
    thousand rates.

    ``trace`` is absent throughout, on the covered nodes as much as on the
    rest. A walk-through is one policy's arithmetic replayed step by step
    against the row its sample came off, and no such row exists for the
    book: nothing ran once over a thousand policies that a reader could be
    walked through. The page therefore shows no "expression that ran" on a
    fold entry, which is absent rather than empty.

    **The definition the frame holds is the one the fold belongs to.** A
    column this model wrote twice has a node per definition, and the
    number the driver folded came out of the finished frame -- so it goes
    against the definition that produced it and the superseded ones carry
    a null, exactly as they would for a policy.

    **A rollforward's movements are folded here and nowhere else**, because
    no accumulator can name them: they are not columns of the model, so a
    model declaring ``AGGREGATIONS`` cannot ask for them and the driver's
    result does not carry them. They are read off ``book`` -- every row of
    the finished run, never the handful this document samples -- under the
    entry's own aggregation, which for a per-period movement is a fold
    across the book at each period. The identity that makes this honest is
    that a movement is additive: the book's movement at a period is the sum
    of its policies', measured rather than assumed. A fold whose
    aggregation is not one that identity holds under carries null here,
    which is the null section 7 already defines for a column no accumulator
    covers.
    """
    held: dict[NodeId, dict[str, Any]] = {}
    for node_id, node in graph.nodes.items():
        column = node.data.column
        if column is None or not node.data.in_final_schema:
            continue
        if column in fold.values:
            held[node_id] = {"value_sample": fold.values[column]}
    held |= _what_the_book_moved(fold, readings, book)
    return held


def _what_the_book_moved(
    fold: PortfolioFold, readings: Readings, book: pl.DataFrame
) -> dict[NodeId, dict[str, Any]]:
    """Return the book's own movements and closing balances under one fold.

    Empty for every fold but the one a per-period amount has a meaning
    under. ``period_sum`` folds a per-period column across the book at each
    period, which is what a movement schedule for the book is; ``sum``
    reduces a scalar column over the book and has no per-period answer to
    give, and ``min``, ``max``, ``variance`` and the rest are folds the
    waterfall identity does not survive -- the minimum closing balance is
    not the minimum opening plus the minimum of each movement, and a
    producer writing one would publish four numbers that do not add up and
    invite a reader to reconcile them.
    """
    if fold.aggregation != _THE_FOLD_A_MOVEMENT_HAS:
        return {}
    held: dict[NodeId, dict[str, Any]] = {}
    for node_id, keyed in readings.movements.items():
        moved = {key: _down_the_book(book, column) for key, column in keyed.items()}
        held[node_id] = {"movements": moved}
    for node_id, column in readings.closing.items():
        held[node_id] = {"value_sample": _down_the_book(book, column)}
    return held


def _down_the_book(book: pl.DataFrame, column: str) -> list[Any]:
    """Return one per-period column summed across every row of the book.

    Per period rather than per policy, and the period index is taken off
    each row's own timeline rather than assumed shared: a book of per-policy
    timelines is jagged, and a fold that read position 40 of a
    thirty-period policy would be summing a value that does not exist.
    """
    folded = (
        book.lazy()
        .select(pl.col(column))
        .with_row_index(_ROW)
        # Stated rather than defaulted, and stated as False: a policy whose
        # timeline is empty contributes no period to the book's fold, where
        # the null the other reading produces would contribute one the book
        # does not have.
        .explode(column, empty_as_null=False)
        .with_columns(pl.int_range(pl.len()).over(_ROW).alias(_PERIOD))
        .group_by(_PERIOD)
        .agg(pl.col(column).sum())
        .sort(_PERIOD)
        .collect()
    )
    return [one_value_on_the_wire(value) for value in folded.get_column(column)]


def _release_the_enrichment(graph: CalcGraph) -> None:
    """Empty the four enrichment fields before the next policy is read.

    Only those four. ``retained``, and the ``dtype`` and ``shape`` a
    retained definition or a running state earns, are facts about the
    definition rather than about any policy -- the producer read them off
    the column it held aside, which is the same column whichever row is
    being sampled -- so a pass that reset them would have the second policy
    re-establish what the first already did and, on any node where that
    failed, quietly withdraw it.
    """
    for node in graph.nodes.values():
        node.data.value_sample = None
        node.data.trace = None
        node.data.branches = None
        node.data.movements = None


def _restore_the_enrichment(
    graph: CalcGraph, held: dict[NodeId, dict[str, Any]]
) -> None:
    """Put the first policy's enrichment back on the graph.

    The graph is what a one-policy document is written from, and it is what
    the wire form falls back to for every field the axis does not override.
    Leaving the last policy's values on it would put the axis's final entry
    where its first belongs, for any reader that did not follow the arrays.
    """
    for node_id, node in graph.nodes.items():
        one = held.get(node_id, {})
        node.data.value_sample = one.get("value_sample")
        node.data.trace = one.get("trace")
        node.data.branches = one.get("branches")
        node.data.movements = one.get("movements")


def _a_plan_no_type_names(failure: Exception) -> ValueError:
    """Return the refusal for an export over a plan whose schema cannot be resolved."""
    lines = [line for line in str(failure).strip().splitlines() if line.strip()]
    said = lines[0] if lines else type(failure).__name__
    msg = (
        "The calculation graph cannot be exported: the frame cannot state the "
        "type of its plan, so the record would carry no type for any column "
        "the model holds, and an engine reading it would compute none of them "
        "and say nothing (section 10 of the specification). The engine's "
        f"own words: {said} Run af.collect() to see the line that fails, "
        "correct it, and export again."
    )
    return ValueError(msg)


class GraphExporter:
    """Write a model's calculation graph as a document a reviewer can file.

    The document is the model's own account of every column: what each one
    reads, how it was computed, which assumption tables and which book of
    policies it rests on, and a content identity for each calculation and for
    the model as a whole. It is JSON that validates against the published
    schema, and it can be read, checked and compared by someone who never
    runs the model.

    :meth:`export` writes the document, and :meth:`export_with_sidecar`
    files it with each assumption table in a file of its own beside it.
    :meth:`node_values` hands back the values each calculation produced,
    keyed the way the document names them -- for reconciling the document's
    figures against a run, or for comparing two runs of one model
    calculation by calculation.
    """

    def __init__(
        self, af: GraphSource, *, data_columns: Iterable[str] | None = None
    ) -> None:
        """
        Initialize the exporter with an ActuarialFrame.

        ``data_columns`` is the one fact about the run that the finished
        frame cannot supply: which columns the policy data the model ran
        over actually carried. A caller that read the file and then started
        the run knows it, and passing it is what lets this export tell a
        column that arrived with that data from a column that merely turned
        up on a frame rebuilt half way through the model. Where they differ,
        the difference is written as a hole rather than as an arrival the
        file never made -- see
        :func:`~gaspatchio.frame.graph.graph_builder._columns_with_no_account`.

        Left out, nothing is claimed and nothing changes: the frame's own
        arriving set is the whole account of what arrived, which for a frame
        built straight from a table is exactly what it is.

        Args:
            af: GraphSource whose calculation log holds the model's columns
            data_columns: The columns of the policy data the model was run
                over, from a caller that watched the run start, or None from
                one that cannot say.

        """
        self.af = af
        # Held as a tuple, because one exporter may fold the same frame more
        # than once -- a results manifest and then the document -- and an
        # iterator read by the first fold would leave the second with none.
        self._data_columns = None if data_columns is None else tuple(data_columns)
        # Set only while :meth:`_executable_for_an_engine` writes the one
        # document this exporter hands to an engine rather than files.
        self._book_left_to_the_engine = False
        # Set while an ``executable`` document is written: an engine runs one,
        # so a plan whose schema cannot be resolved is refused rather than
        # written with no type on any column (:meth:`_backfill_unresolved_dtypes`).
        self._refusing_an_untyped_plan = False
        # The book an export here last digested, and the member it wrote: a
        # second document over the same book reuses the digest rather than
        # taking another pass over every column the model reads.
        self._book_taken: tuple[object, dict[str, Any]] | None = None
        self._records = self._calculation_records()
        self._validate_calculation_log()

    def _executable_for_an_engine(self) -> dict[str, Any]:
        """Return the document the frame's engine door hands a second engine.

        The executable profile, values-free and without the model's text, as
        ``collect(engine=...)`` and ``run_aggregated(engine=...)`` hand it
        over. The book's digest is left to the engine: it digests the inputs
        it is handed into its own result manifest, which is the record of
        what it ran over, and a digest taken here -- a pass over every
        required column of the book -- would be paid for on every run and
        read by nothing.
        """
        self._book_left_to_the_engine = True
        try:
            document: dict[str, Any] = json.loads(
                self.export(profile="executable", include_source=False)
            )
        finally:
            self._book_left_to_the_engine = False
        return document

    def _document_root(
        self, model: ModelIdentity | None, source_root: Path | str | None
    ) -> Path | None:
        """Return the root every path is written against, never none where one is found.

        The identity's root or the one the caller named; and where neither
        names one, the root of the files the nodes were written in, so a
        frame exported with no identity writes no absolute path (section 7).
        """
        root = _document_root(model, source_root)
        if root is not None:
            return root
        entries = [
            *(getattr(self.af, "_calculations", None) or []),
            *(getattr(self.af, "_selections", None) or []),
        ]
        spans = (getattr(entry, "source", None) for entry in entries)
        return root_of_the_files_read(
            f"{span.file}:{span.line}" for span in spans if isinstance(span, SourceSpan)
        )

    def _versions_to_state(
        self, versions: str, *, carries_values: bool
    ) -> Mapping[str, str] | Literal["withheld"] | None:
        """Return what the document states produced its values, or refuse the setting.

        The run the values came from, where the document carries values and
        the frame knows that run: a frame computed in a worker and pickled
        back states the worker's versions, and one computed on a second
        engine states what that engine's manifest says produced it. None,
        where there is no such run, states this process's.
        """
        if versions == "withheld":
            return "withheld"
        if versions != "recorded":
            msg = (
                f"versions={versions!r} is not a setting. 'recorded' states what "
                "produced the values; 'withheld' records them as withheld, for a "
                "document committed as a golden."
            )
            raise ValueError(msg)
        run = self.af._last_run  # noqa: SLF001 -- the frame owns completion
        if carries_values and run is not None:
            return run.versions
        return None

    def _calculation_records(self) -> list[CalculationRecord]:
        """Return the frame's calculations, boundary markers dropped.

        A boundary marks a materialization, which defines no column, so it
        has no node to contribute.
        """
        entries = getattr(self.af, "_calculations", None) or []
        return [entry for entry in entries if isinstance(entry, CalculationRecord)]

    def _definitions_logged(self) -> list[tuple[str, int]]:
        """Return every definition the log holds, as (column, ordinal), in order.

        A calculation, and a write over a column outside the frame's own
        operations: the second is a definition too -- the graph mints a hole
        under its ordinal -- and a column it was the last word on holds its
        values, while one a later definition replaced may have had them
        carried aside like any other.
        """
        entries = getattr(self.af, "_calculations", None) or []
        return [
            (entry.column, entry.ordinal)
            for entry in entries
            if isinstance(entry, CalculationRecord | OverwriteRecord)
        ]

    def _expressions_by_node(self) -> dict[NodeId, pl.Expr]:
        """Return the engine expression behind each node, by node id.

        A node id is a column and the ordinal of the definition, which is
        what a record already carries, so the two are matched on the pair
        rather than on anything either of them has to be told.

        The expression is what the fold probe asks its question of. The
        node's own operation tree cannot answer it: an engine fragment is
        opaque by construction -- that is what makes it a fragment -- and
        a fold down the model points is exactly the shape that reaches an
        artifact as one, since the format has no identifier for it
        (specification 11.1.9). The record kept the live expression, so
        the question can be put to the thing that actually ran.
        """
        return {
            f"{record.column}@{record.ordinal}": record.expr for record in self._records
        }

    def _validate_calculation_log(self) -> None:
        """Validate that the ActuarialFrame recorded something to export.

        A model that chose which policies it values and calculated nothing is
        still a model: its record is the selection (section 7.6), the book
        columns the selection reads and the digests over both. Only a frame
        that neither calculated nor selected has nothing to account for.
        """
        if not self._records and not getattr(self.af, "_selections", None):
            message = (
                "No calculations found. The model did not compute any columns "
                "on this frame, so there is no calculation graph to export."
            )
            raise ValueError(message)

    def export(  # noqa: PLR0913 — one parameter per thing the caller may say about the document; this is the list build_artifact takes, passed through, and folding them into a config object here would rename the list rather than shorten it
        self,
        result_df: pl.DataFrame | None = None,
        config: GraphExportConfig | None = None,
        *,
        profile: Literal["audit", "executable"] = "audit",
        include_lowered: bool = False,
        include_tables: bool | Literal["all"] = True,
        include_source: bool = True,
        table_payload_limit: int | None = TABLE_PAYLOAD_LIMIT,
        source_root: Path | str | None = None,
        seal: bool = SEAL_BY_DEFAULT,
        retain_superseded: bool = True,
        versions: Literal["recorded", "withheld"] = "recorded",
    ) -> str:
        """
        Export the calculation graph as a conforming artifact.

        The graph is written into the envelope that says which schema it
        conforms to, which model it is an account of, which book of policies
        it was built over, and what the identity of the whole model is -- so
        a reader a quarter later can place it and check it rather than take
        it on trust.

        The book is identified by its content, with nothing to pass in: the
        document records a digest of the input columns the model reads or
        hands back, taken over the data the frame was handed. Two filings of
        one model over two in-force files therefore say so when they are
        compared, and a filing can be matched to a set of results by the data
        behind both -- where the engine that wrote the results was handed the
        book itself, since an engine records a digest of what it was handed,
        and a book crossed with a scenario axis or filtered first is other
        rows.

        Every computed node states the right-hand side its author wrote. The
        engine's own rendering of the same calculation is not in the base
        artifact and has to be asked for: it moves whenever the engine
        changes how it prints an expression, and two exports of a model that
        never changed would stop comparing.

        Two conformance profiles, and the default is the one a reviewer
        reads::

            exporter.export()  # audit: the account of the model
            exporter.export(profile="executable")  # and the calculation itself

        The ``executable`` profile writes the operation tree of every node
        that has one onto the node, under ``expr`` -- a column that arrived,
        a hole and a running state have none -- and a compiled rollforward's
        own state machine into the envelope's facets. A consumer parses a
        tree, hashes it under the format's byte grammar, and reaches the
        ``local_fingerprint`` the same node already carries, which is what
        lets the file check itself rather than ask to be trusted.

        **What is stable.** The operation trees are what another engine runs
        the model from, and they are not yet a stable interface. The JAX
        engine runs the operations its coverage table lists and refuses the
        rest by name, and no engine yet covers every operation the format
        names. The format is still a pre-release version, as the schema
        identifier every document states -- ``gaspatchio-graph/v0-preview.3``
        -- says: until its first stable version the trees' shape may change
        between releases without a compatibility path, and every change is
        recorded in the specification's change log.

        Every assumption base the model read carries its own values, so that
        the reader who asks "which mortality basis was this run against?"
        gets the basis rather than a digest of a file they now have to find.
        Three settings say how much of that travels::

            exporter.export()  # the values, up to 1 MiB each
            exporter.export(include_tables="all")  # the values, whatever they weigh
            exporter.export(include_tables=False)  # identities only, no values

        The slim form is for a repository where the assumption bases are
        versioned separately: the fingerprints still say exactly which
        revision of each base was read, and committing a copy of a mortality
        table beside every run would be committing the same file twice.
        :meth:`export_with_sidecar` is that form with its other half written
        -- the identities in ``artifact.json``, each base's values in a file
        beside it named after the fingerprint the document already states.

        **The trade runs both ways, and neither side is the safe answer.**
        Inline, the file handed over *contains* the basis: a supervisor
        holding it and nothing else re-hashes the mortality table the
        reserves were struck on without fetching anything. Beside, *did
        the basis move?* becomes a comparison of two file names rather than
        a diff of two payloads, and wherever the store keeps one file per
        name -- filings sharing a directory, or a content-addressed store
        above this writer -- ten quarters of an unchanged basis stop being
        ten copies of one table. Ten filings into ten directories are still
        ten copies: the name is what makes them one file, and which files a
        store keeps under it is not this writer's to decide. Both are *Audit
        by default*; which one a filing wants depends on whether it is
        handed over once or kept for a decade.

        **Inline is the default for now**, and it is a default that may
        change: which way a producer should file by default will be settled
        before the format's first stable version, on what filings actually
        look like by then.

        Args:
            result_df: The frame ``collect()`` returned, where the document
                should carry each calculation's values for the policies it
                samples; None writes the calculations without values.
            config: What the export is told beyond the frame: which model
                this is an account of, which policies to carry values for,
                and the period and filter the values are read at.
            profile: Which conformance profile the artifact claims. ``audit``
                is the envelope, the node record, the edges and the identity
                fields; ``executable`` is that same document with every
                node's operation tree written onto it. An ``executable``
                artifact is a conforming ``audit`` artifact, so a consumer
                that reads only the audit fields reads either correctly.
            include_lowered: Whether every node that has one also carries the
                engine's rendering of its calculation, in the
                ``gaspatchio_lowered`` facet. Off by default; the as-written
                formula beside it is authoritative either way.
            include_tables: Whether each assumption entry carries the base's
                own values. True inlines everything at or under
                ``table_payload_limit`` and, above it, writes an entry saying
                a value exists, was left out for its size, and how many bytes
                it weighs. ``"all"`` inlines regardless of weight. False
                writes that same stand-in for every base, keeping every
                identity and carrying no values at all. **Both settings
                govern all three kinds of entry**: a schedule and a curve are
                inlined, weighed and stood in for on the same terms a table
                is, and the name says "tables" only because a table is the
                entry whose values run to megabytes. **It governs the sources
                section on the same terms**: a model's own text is a value
                this document carries inline, weighed and stood in for under
                one rule rather than two.
            include_source: Whether the model's own text travels in the
                document, one entry per file its nodes were written in. On by
                default: a reader who has followed a node to ``model.py:520``
                can then read line 520, and a document that names the line and
                cannot show it answers half the question it was asked. Off
                writes every entry as withheld, keeping the path and the
                fingerprint so a reader knows what was left out and can check
                a copy they hold against it::

                    exporter.export()  # the model's source travels
                    exporter.export(include_source=False)  # paths and digests only

                Leaving the text out is a decision the file records rather
                than a silence, which is what makes carrying it the default
                a producer opts out of instead of a favour it asks for.
            table_payload_limit: How many bytes one inlined payload may
                weigh, measured in the serialisation this document is written
                in, or None for no guard -- which for these entries is what
                ``"all"`` says. The default keeps an artifact something a
                repository can hold a copy of per run.
            source_root: The directory every ``source_location`` is written
                relative to, or None to write the absolute path the model was
                read from. A document other people read wants the first:
                where in a repository the model is written is a fact about the
                model, and whose disk it was read off is not::

                    exporter.export(source_root=repository_root)

                A ``config.model`` made by :meth:`ModelIdentity.of` already
                carries that root -- the repository the model sits in, or the
                model file's directory -- and None then takes it, so a Python
                export writes its locations against the directory its version
                block's paths were written against. A ``source_root`` naming
                another directory is refused: one document has one root.

                A location outside the root is written with ``..``
                segments rather than left absolute, so that a root named at
                all leaves no absolute path in the document. A file under the
                producer's temporary directory, where the root is not -- a
                notebook kernel's cell file -- is written by its name in
                angle brackets, ``<cell.py>:7``, since a climb to it would
                name the machine; a location that names no file, such as a
                notebook cell's ``Jupyter Cell 3``, is written as it was
                recorded. The rewrite
                happens inside the export and therefore under the seal, which
                is why it is a setting here and not something a publishing
                script does to the file afterwards.
            seal: Whether the document carries ``document_digest``, the hash
                over its own canonical serialization. The fingerprints answer
                whether this is the same calculation; the seal answers whether
                this is the file the producer wrote, which is a different
                question and the one an edited quotation escapes. On by
                default, because the format requires it: a document written
                without a seal does not validate until it is sealed::

                    exporter.export(seal=False)  # no seal on the wire

            retain_superseded: Whether a definition the model wrote over
                carries its own values. On, every superseded definition is
                written with ``retained: true``, its own ``value_sample`` and
                its own walk-through, read from the output that definition
                produced rather than from the column that replaced it -- the
                artifact answers "what did this column hold before the
                override?" for a reviewer who has the file and cannot ask the
                frame. Off, those nodes are written as history with no values
                and a ``dtype`` of ``unknown``, which is what the format has
                always permitted for them::

                    exporter.export(retain_superseded=False)  # history only

                **This switch governs the document; the frame's own
                ``retain_superseded`` governs the memory.** The values an
                export writes were carried through the model's collect, which
                is over by the time an exporter exists: off here, the values
                are released from the frame -- their residency after the run
                ends here -- but nothing reached from an exporter can unspend
                the collect that produced them. Declining the cost itself is
                ``ActuarialFrame(..., retain_superseded=False)``, which keeps
                nothing of a replaced definition's values in the first place.

                The two settle in one direction. With the frame's lever off
                there is nothing to write, so superseded definitions are
                history with no values here whatever this is set to. With it
                on and this off, the values exist and this export declines
                them. With both on, each superseded definition carries its
                own number and says it was retained.

            versions: Whether the document states what produced its values,
                as ``producer.versions``. ``"recorded"``, the default, writes
                the result manifest's own six keys -- the core's version and
                its compiled extension's, the extension's sha256, Polars,
                Python and the platform -- taken from the run the values came
                from (``af.graph.last_run``) where the document carries values
                and that run is known, and from this process otherwise; and,
                where ``config.model`` names a model file, ``imports``: each
                installed distribution the model imports, with its version.
                ``"withheld"`` writes section 6.1's withheld form in their
                place, for a document committed as a golden, which must not
                carry one machine's build strings::

                    exporter.export(versions="withheld")  # no library versions

                It is never the default: the versions are the record's answer
                to "would this library give the same number?".

        Returns:
            JSON string carrying the artifact

        Raises:
            ValueError: If ``source_root`` names another directory than the
                one ``config.model``'s paths were written against, or if
                ``versions`` is neither ``"recorded"`` nor ``"withheld"``.

        """
        stated_versions = self._versions_to_state(
            versions, carries_values=result_df is not None
        )
        if config is None:
            config = GraphExportConfig()
        # The root, settled before the frame is read: a document with two
        # roots is refused, and a refusal after every value was sampled is
        # the same answer paid for twice.
        root = self._document_root(config.model, source_root)

        logger.info(f"Building calculation graph from {len(self._records)} operations")

        self._refusing_an_untyped_plan = profile == "executable"
        # Prepare DataFrame if provided. The superseded definitions the frame
        # carried through its collect join it BEFORE the filter, so that every
        # value in this document was read off the same rows: a retained column
        # filtered differently from the frame beside it would put one policy's
        # history next to another policy's answer.
        carried: dict[str, pl.Series] = {}
        values_read_from = result_df
        # Every node's own output, for the one question a type cannot answer
        # about itself. Taken BEFORE the filter, because the question is
        # whether the column holds a value the record cannot carry and the
        # column is all of its rows: a filter that happened to select the
        # rows that fit would otherwise certify a width on a sample.
        in_reach: dict[NodeId, pl.Series] = {}
        # The whole book as the model finished with it, held back from the
        # filter. A fold is over the book and a sample is over the rows the
        # export narrowed to, so the two are read off two frames rather than
        # one narrowed frame doing both jobs.
        book: pl.DataFrame | None = None
        readings = Readings((), {}, {})
        graph: CalcGraph | None = None
        # Where on the finished frame each entry of the axis is. Worked out
        # once, against the frame the model handed back and before this
        # export's own filter narrows it, because what is being measured
        # here is what the MODEL did to the selected row -- moved it, folded
        # it away, duplicated it -- and a cut this export was asked for is
        # a cut the envelope already records on every entry.
        located: tuple[LocatedRow, ...] = ()
        if result_df is not None:
            if retain_superseded:
                carried = self._carried_definitions(result_df)
            else:
                self._release_carried_definitions()
            collected = (
                result_df.hstack(list(carried.values())) if carried else result_df
            )
            in_reach = self._values_by_node(collected)
            # Built here rather than below, because what a compiled
            # rollforward moved is read off the graph's own compilations and
            # the readings have to join the frame before it is filtered: a
            # movement and the balance beside it are sampled off one row under
            # one context, like every other per-period value.
            graph = self._build_graph_structure(in_reach)
            book, readings = read_the_movements(graph, collected)
            if config.policies:
                located = locate_the_selection(
                    book, config.policies, id_column=config.policy_id_column
                )
                # The sentences travel amended where the model moved a row,
                # so the ``why`` on the wire and the row the values came off
                # are one statement rather than two a reader has to
                # reconcile.
                config = config.model_copy(
                    update={"policies": tuple(one.entry for one in located)}
                )
            values_read_from = self._prepare_dataframe(book, config)
            # What the envelope says the values were read from is the model's
            # own frame. The carried columns are how this producer reached a
            # superseded definition's numbers, the readings are how it
            # reached a state machine's, and the row stamp is how it found
            # the selected row again; none of the three is a column of the
            # model, and nothing downstream of here should be able to
            # mistake one for a column that is.
            taken_off = [*carried, *readings.columns]
            if ROW_STAMP in values_read_from.columns:
                taken_off.append(ROW_STAMP)
            result_df = (
                values_read_from.drop(taken_off) if taken_off else values_read_from
            )

        # Build the graph structure, where the values did not already need it.
        if graph is None:
            graph = self._build_graph_structure(in_reach)

        # Enhance with sample values if DataFrame provided, once per policy
        # the export carries. The graph is left holding the first policy's
        # values, so everything downstream of here reads exactly what it
        # read before there was an axis.
        samples: list[dict[NodeId, dict[str, Any]]] = []
        if values_read_from is not None and book is not None:
            samples = self._along_the_policy_axis(
                graph,
                values_read_from,
                config,
                in_reach,
                readings=readings,
                book=book,
                located=located,
            )

        # Log statistics
        self._log_statistics(graph, result_df)

        # The filtered frame goes with the graph: the envelope has to say
        # which policy the samples were read from, and that is a fact about
        # the rows that survived the filter rather than about the config.
        #
        # The book the frame was built over, as it was handed in: the
        # document digests the columns of it the model reads, so two
        # documents say whether they were built over the same book -- unless
        # it is being handed to an engine, which digests what it runs over
        # itself. A digest an earlier export here took over the same book is
        # reused rather than taken again. Not ``book`` above, which is the
        # book as the model finished with it.
        arrived = self.af._arrival_data  # noqa: SLF001 -- the frame's own
        document = build_artifact(
            graph,
            config=config,
            profile=profile,
            values_from=result_df,
            include_lowered=include_lowered,
            include_tables=include_tables,
            include_source=include_source,
            table_payload_limit=table_payload_limit,
            source_root=root,
            seal=seal,
            samples=samples,
            book=arrived,
            book_left_to_the_engine=self._book_left_to_the_engine,
            book_taken=self._book_already_taken(arrived),
            versions=stated_versions,
        )
        self._remember_the_book(arrived, document)
        # Said as the file is written rather than found at audit: a model
        # whose revision the document cannot state is told so once, in the
        # sentence the document's own git member carries.
        notice = revision_notice(document.get("model"))
        if notice is not None:
            logger.info(notice)
        # allow_nan=False is the backstop, and it is deliberately here rather
        # than in the one path known to need it. Python's encoder will happily
        # write the bare tokens NaN and Infinity, which are not JSON: a strict
        # parser -- serde_json, Go, JSON.parse -- refuses the whole document,
        # and the schema validator, which runs on an object somebody already
        # parsed, never sees them. So an unparseable file would leave this
        # process looking like a valid one. Every value that could carry a
        # non-finite float states it on the wire instead; a refusal here is
        # therefore a path that has not, surfacing loudly at the producer
        # rather than quietly at whoever tries to read the file next quarter.
        try:
            return json.dumps(document, indent=_DOCUMENT_INDENT, allow_nan=False)
        except ValueError as refused:
            raise refusal_for_a_number_json_cannot_hold(document, refused) from refused

    def _book_already_taken(self, book: object) -> dict[str, Any] | None:
        """Return the book member an earlier export here wrote over ``book``, if any.

        The same object, not an equal one: the digest is reused only for the
        very book it was taken over.
        """
        if self._book_taken is None or self._book_taken[0] is not book:
            return None
        return self._book_taken[1]

    def _remember_the_book(self, book: object, document: dict[str, Any]) -> None:
        """Keep the book member a document wrote, where it states a digest."""
        member = document.get("book")
        if isinstance(member, dict) and isinstance(member.get("digest"), str):
            self._book_taken = (book, member)

    def _along_the_policy_axis(  # noqa: PLR0913 — one parameter per frame or map a pass reads; folding them into an object would rename the list rather than shorten it
        self,
        graph: CalcGraph,
        values_read_from: pl.DataFrame,
        config: GraphExportConfig,
        in_reach: ValuesInReach,
        *,
        readings: Readings,
        book: pl.DataFrame,
        located: tuple[LocatedRow, ...],
    ) -> list[dict[NodeId, dict[str, Any]]]:
        """Read every node's values once per policy the export carries.

        One pass of the three enrichment steps per entry of the axis, each
        against the same finished frame and each pinned to that entry's own
        model point. The model is run **once**, over the rows the selection
        named, and what varies between passes is which row is read -- which
        is what makes a second policy cost its own values and nothing else:
        no second fold, no second compilation, and every fingerprint in the
        document identical because none of them was ever a fact about a
        policy.

        The three steps are one pass rather than three loops because they
        are not independent. A walk-through is built from the sample beside
        it, and a conditional's two branches are evaluated against the row
        the sample came off, so a pass that mixed one policy's sample with
        another's walk-through would produce exactly the disagreement the
        enrichment layer exists to catch.

        **The book's folds come first, and they are read from nowhere.**
        A fold is already a number -- the driver computed it over the whole
        book -- so its entry is assembled rather than sampled, and the
        frame the policies are read off is never touched for it. Every
        column the fold does not cover is absent from its mapping, which is
        the null the wire then writes at that position. A rollforward's
        movements are the exception the format's own rule makes room for:
        no accumulator names them, because they are not columns of the
        model, so the producer folds them itself over ``book`` -- every row
        of it -- under the entry's own aggregation.

        The graph is left holding the **first policy's** values, and the
        first policy is not the first entry once there are folds above it.
        A document carrying one policy is built from the graph alone and
        writes every enrichment field as the value itself, which is byte
        for byte what it was before this axis existed; a document carrying
        more gets the arrays out of what this returns.
        """
        folded = [
            _what_the_book_came_to(graph, fold, readings, book) for fold in config.folds
        ]
        axis: tuple[LocatedRow | None, ...] = located or (None,)
        read: list[dict[NodeId, dict[str, Any]]] = []
        width = len(folded) + len(axis)
        for entry in axis:
            pinned = self._pinned_to(config, entry)
            self._enhance_with_values(graph, values_read_from, pinned, in_reach)
            _enhance_with_movements(graph, values_read_from, pinned, readings)
            if config.include_traces:
                self._add_traces(graph, values_read_from, pinned)
            # And, where the caller asked for it, what each branch of a
            # conditional would have held. Only where they asked: the
            # default path evaluates nothing here at all.
            if config.branches:
                self._enhance_with_branches(graph, values_read_from, pinned)
            read.append(_what_each_node_held(graph))
            if width > 1:
                _release_the_enrichment(graph)
        if width > 1:
            _restore_the_enrichment(graph, read[0])
        return [*folded, *read]

    @staticmethod
    def _pinned_to(
        config: GraphExportConfig, entry: LocatedRow | None
    ) -> GraphExportConfig:
        """Return the context one policy's values are read under.

        **A row position never crosses the run.** It used to: an entry
        reached by counting rows of the book was read back at that position
        of the finished frame, on the assumption that running the model
        preserves them. ``af.sort(...)`` disproves it, and the document that
        came out carried the selected policy's id over another policy's
        numbers. So the row the selector counted is found again before this
        is reached (:func:`~.row_identity.locate_the_selection`) and what
        arrives here is a row of the frame the values come off, named by the
        stamp this export put on the book or -- where the model did not hand
        that stamp back -- by the policy id, which is the pin
        ``--policies 7`` has always used.

        None where there is no axis, which is every caller that predates
        one: the context is the config as it stands and the values come off
        the policy it names, or off the frame's first row.
        """
        if entry is None:
            return config
        return config.model_copy(
            update={"policy_id": entry.policy_id, "row_pin": entry.pin}
        )

    def export_with_sidecar(  # noqa: PLR0913 — the list :meth:`export` takes, less the two this filing shape settles; a config object here would rename it rather than shorten it
        self,
        directory: Path | str,
        result_df: pl.DataFrame | None = None,
        config: GraphExportConfig | None = None,
        *,
        profile: Literal["audit", "executable"] = "audit",
        include_lowered: bool = False,
        include_source: bool = True,
        source_root: Path | str | None = None,
        seal: bool = SEAL_BY_DEFAULT,
        retain_superseded: bool = True,
        versions: Literal["recorded", "withheld"] = "recorded",
    ) -> str:
        """Write the artifact into ``directory``, with the values it names beside it.

        The same account of the model :meth:`export` writes, filed the other
        way round. ``artifact.json`` is the identities-only document -- every
        base named, every fingerprint stated, no values carried -- and each
        base's values sit under ``assumptions/`` in a file named after the
        very fingerprint the document states for it.

        **Nothing in the document points at a file, and nothing needs to.**
        An entry publishes the fingerprint its values hash to, so the name is
        derived rather than recorded (:func:`payload_file_name`): a consumer
        fetches that name, re-hashes what comes back under the grammar its
        kind is stamped by, and either reaches the fingerprint the document
        declared or has been handed the wrong file. That is why this writes a
        conforming artifact and moves nothing on the wire -- the location is
        a consequence of the identity, not a new field beside it.

        **The document is the index.** An entry that carries a weight is one
        whose values this process held, weighed and put in a file; an entry
        reading ``omitted: unavailable`` is one whose values this process
        could not reach, and there is no file for it because there was
        nothing to write. A reader never has to guess which entries have a
        file, and no field was added to tell them.

        **What the shape buys, and what it costs.** An inline artifact is a
        filing that *contains* its basis: hand the file to a supervisor and
        the mortality table the reserves were struck on is in it, re-hashable
        without leaving the page. This form gives that up in exchange for the
        thing a repository wants -- *did the basis move?* becomes a
        comparison of two file names rather than a diff of two payloads,
        and where the store keeps one file per name, ten quarters of an
        unchanged basis stop being ten copies of one table. This call
        writes every payload it names into the directory it was handed, so
        ten filings into ten directories are ten copies; one directory, or
        a content-addressed store above it, is what collapses them. Both
        halves are *Audit by default*; which one a filing wants depends on
        whether it is handed over once or stored for a decade.

        **The seal covers the document.** Where ``seal`` is asked for, the
        digest is over ``artifact.json`` and over nothing else: a payload
        file's identity is its own content hash, which the document already
        states and the file is already named after, so a second digest over
        the same bytes would say nothing the first does not.

        ``include_tables`` and ``table_payload_limit`` are not parameters
        here. This filing shape *is* the identities-only setting, and a guard
        on an inlined payload has nothing to guard.

        **The model's own source is filed the same way, in a folder of its
        own.** Every entry of the sources section states its weight and its
        text goes into ``sources/``, in a file named after the entry's own
        fingerprint -- the bases' rule, applied to the model's text, in the
        folder named after the section that accounts for it. A model's code
        filed among the rate tables would be exactly the confusion the format
        keeps the model's text out of the assumptions directory to avoid.
        ``include_source`` is still a parameter, because it is not a question
        about where the text is put but whether it is disclosed at all, and
        off there means no file is written for it and no folder either.

        Args:
            directory: Where the filing goes. Created if it does not exist,
                and so is the ``assumptions/`` folder inside it -- which is
                written even for a model that read no base at all, so that
                "this model rests on nothing" and "the folder was never
                written" are not one answer to a consumer's fetch. Pointing
                two filings at one directory is the shape that realises the
                saving above, and it is not a merge: the second
                ``artifact.json`` replaces the first without a word, and a
                payload the first document named and the second does not is
                left where it lies. Under content addressing an accumulating
                ``assumptions/`` is the store working -- a reader fetching
                by name is unaffected -- but the document at the root is the
                part that cannot accumulate, so two filings kept side by
                side want two directories.
            result_df: The frame ``collect()`` returned, as :meth:`export`
                takes it; None writes the calculations without values.
            config: What the export is told beyond the frame, as
                :meth:`export` takes it.
            profile: Which conformance profile the artifact claims, as
                :meth:`export` defines the two.
            include_lowered: Whether every node that has one also carries the
                engine's rendering of its calculation.
            include_source: Whether the model's own text is disclosed at all,
                as :meth:`export` defines it. On, each source's text goes in a
                file beside the document; off, every entry reads withheld and
                no file is written for it.
            source_root: The directory every ``source_location`` is written
                relative to, as :meth:`export` defines it -- taken from a
                ``config.model`` made by :meth:`ModelIdentity.of` where it is
                None. Each source file is read back against the same root
                before it is filed.
            seal: Whether ``artifact.json`` carries ``document_digest``.
            retain_superseded: Whether a definition the model wrote over
                carries its own values, as :meth:`export` defines it. It
                governs the document, which is the half of this filing the
                node records live in; an assumption payload is unaffected
                either way.
            versions: Whether ``artifact.json`` states what produced its
                values, as :meth:`export` defines it.

        Returns:
            The document, as the text written to ``artifact.json`` -- the
            same string :meth:`export` would have returned for the same call
            with ``include_tables=False``, byte for byte.

        Raises:
            ValueError: If a base the document weighed cannot be read back
                when the file comes to be written, or if a source file the
                document weighed no longer hashes to the fingerprint beside
                it. Either means the thing moved between the two readings,
                and writing the current bytes under the recorded digest would
                put a file in the store that hashes to a name it does not
                carry. Every payload is read before any of them is written,
                so this refusal leaves nothing behind -- not a payload, not
                the ``assumptions/`` folder, not the directory itself. Also
                if ``source_root`` names another directory than the one
                ``config.model``'s paths were written against, before
                anything is read.
            OSError: If the directory or a file cannot be written. Payload
                files already written stay where they are, and because
                ``artifact.json`` goes down last, a failure part way through
                leaves a directory holding payloads and no document. The
                absent ``artifact.json`` is what says it is not a filing;
                nothing here removes the payloads that did land.

        """
        where = Path(directory)
        # One root for both halves of the filing: the document's paths are
        # written against it, and each source file is read back against it.
        root = self._document_root(
            None if config is None else config.model, source_root
        )
        document_text = self.export(
            result_df,
            config,
            profile=profile,
            include_lowered=include_lowered,
            include_tables=False,
            include_source=include_source,
            source_root=root,
            seal=seal,
            retain_superseded=retain_superseded,
            versions=versions,
        )
        document: dict[str, Any] = json.loads(document_text)
        payloads = self._payload_files(document)
        sources = self._source_files(document, root=root)

        beside = where / PAYLOAD_DIRECTORY
        beside.mkdir(parents=True, exist_ok=True)
        for name, content in payloads.items():
            (beside / name).write_bytes(content)
        if sources:
            code = where / SOURCE_DIRECTORY
            code.mkdir(parents=True, exist_ok=True)
            for name, content in sources.items():
                (code / name).write_bytes(content)
        # The document last, so that a directory holding it holds every
        # payload it accounts for rather than an index of files still
        # arriving.
        (where / ARTIFACT_FILE_NAME).write_text(document_text, "utf-8")
        logger.info(
            f"Filed the artifact, {len(payloads)} assumption payload(s) and "
            f"{len(sources)} model source(s) under {where}"
        )
        return document_text

    @staticmethod
    def _payload_files(document: dict[str, Any]) -> dict[str, bytes]:
        """Return the file each weighed entry's values are written into.

        Read off the document rather than off a second walk of the graph.
        The section is the producer's own statement of which bases it holds
        the values of, so taking the list from anywhere else would be
        building a directory that could disagree with the index published
        beside it -- and the disagreement would be invisible until somebody
        fetched a name nothing wrote.

        Every payload is read before any of them is written, so a base that
        moved under the export stops the filing rather than leaving a
        directory half written.
        """
        files: dict[str, bytes] = {}
        for entry in document["assumptions"]:
            if "bytes" not in entry["payload"]:
                continue
            values = payload_of(
                ArtefactReference(
                    kind=entry["kind"],
                    name=entry["name"],
                    fingerprint=entry["fingerprint"],
                )
            )
            if values is None:
                msg = (
                    f"The {entry['kind']} {entry['name']!r} was weighed for this "
                    f"artifact and cannot be read back under "
                    f"{entry['fingerprint']}, so the values the document names "
                    "are no longer here to be filed beside it. The base moved "
                    "while the export was being written. Export again from a "
                    "process that is not extending its assumption bases."
                )
                raise ValueError(msg)
            files[payload_file_name(entry["fingerprint"])] = payload_bytes(values)
        return files

    @staticmethod
    def _source_files(
        document: dict[str, Any], *, root: Path | None
    ) -> dict[str, bytes]:
        """Return the file each weighed source entry's text is written into.

        The bases' rule, applied to the model's own text: the document is the
        index, an entry that states a weight is one whose text goes in a file,
        and the file is named after the fingerprint the entry publishes, so no
        pointer is needed and none is written. The folder is ``sources/``
        rather than the bases' own, because the folder is named after the
        section it answers for.

        The path is read back against the same root the document's paths were
        written against, which is the only way a relative path in a document
        becomes a file on a disk again. And the bytes are re-hashed before
        they are filed: a source that moved between the weighing and the
        writing would otherwise be stored under a name it no longer hashes to,
        which is the one failure a content-addressed store cannot detect for
        itself.
        """
        files: dict[str, bytes] = {}
        for entry in document.get("sources", []):
            if "bytes" not in entry["payload"]:
                continue
            where = Path(entry["path"])
            found = source_payload_of(where if root is None else root / where)
            if found is None or found[0] != entry["fingerprint"]:
                msg = (
                    f"The model source {entry['path']!r} was weighed for this "
                    f"artifact and no longer reads back under "
                    f"{entry['fingerprint']}, so the text the document names "
                    "is not the text that would be filed beside it. The file "
                    "moved or was edited while the export was being written. "
                    "Export again from a tree nobody is editing."
                )
                raise ValueError(msg)
            files[payload_file_name(entry["fingerprint"])] = payload_bytes(found[1])
        return files

    def node_values(self, result_df: pl.DataFrame) -> dict[NodeId, pl.Series]:
        """Return each node's own values off the frame this model finished on.

        The finished frame names its columns the way the model does, and the
        document names calculations by node id. The two part company the
        moment a model writes one column twice -- ``policies_in_force@1`` and
        ``policies_in_force@2`` share one column name -- and again wherever a
        compiled rollforward carries a balance no column of the model holds.
        This is the pairing the document's own figures are read from, for a
        caller reconciling those figures against the run, or comparing two
        runs of one model calculation by calculation. It reaches the values
        by three routes:

        - a column no calculation defines, under its own name;
        - a definition the frame still holds, and one the model replaced,
          from the values the run set aside for it;
        - a running state's closing balance, re-tracked over the finished
          frame the way :meth:`export` reads one.

        A node whose values are not in reach earns no entry rather than an
        approximate one, which is the same answer :meth:`export` gives: a
        definition renamed away or a column dropped before the model finished
        has no values anywhere, and inventing some would be worse than saying
        nothing.

        Args:
            result_df: The frame ``collect()`` handed back -- that object,
                not a copy of the same shape. A definition the model replaced
                is read from values the collect set aside for exactly that
                frame, so a copy reaches none of them.

        Returns:
            Node id to that node's values.

        """
        carried = self._carried_definitions(result_df)
        collected = result_df.hstack(list(carried.values())) if carried else result_df
        values = self._values_by_node(collected)
        book, readings = read_the_movements(
            self._build_graph_structure(values), collected
        )
        for node_id, column in readings.closing.items():
            if column in book.columns:
                values[node_id] = book.get_column(column)
        return values

    def _carried_definitions(self, result_df: pl.DataFrame) -> dict[str, pl.Series]:
        """Return each superseded definition's own output, by the name it rode under.

        The frame carried these through the same collect that produced
        ``result_df`` (``ActuarialFrame.collect``), which is what makes one
        execution answer for every definition the model wrote rather than one
        replay per definition it replaced. Nothing is recomputed here.

        Empty on every model that never wrote a column twice, which is most
        of them, and empty where the values in hand are not the ones that
        collect handed back. **The test is identity, not shape.** The frame
        records the object its last collect produced, and only that object
        carries the rows this history belongs to: two frames of equal height
        are a thing that happens constantly -- two runs of one model, a
        re-collect, a frame sliced to the same length -- and putting one
        run's history beside another run's answers is exactly the untruth
        this whole mechanism exists to prevent. A caller who hands over
        anything else gets the superseded definitions written as history,
        which is the safe direction to fail in.

        The cost is named before it is paid, because it is memory a model
        pays for the whole life of its last collect: one carried column per
        superseded definition, sized here from the values themselves rather
        than assumed.
        """
        held = getattr(self.af, "_retained_values", None)
        if held is None:
            return {}
        tie = getattr(self.af, "_retained_for", None)
        # The defensive container is the same completion's values too. Its
        # identity is owned by the frame and cleared whenever the plan moves;
        # accepting it does not accept arbitrary caller copies or row counts.
        snapshot = self.af._collected_values  # noqa: SLF001 -- completion's own witness
        if snapshot is not result_df and (tie is None or tie() is not result_df):
            logger.debug(
                "Not retaining superseded definitions: the values handed to "
                "this export are not the frame this model's last collect "
                "produced, so there is nothing tying one to the other."
            )
            return {}
        definitions = {
            _retained_column_name(column, ordinal): f"{column}@{ordinal}"
            for column, ordinal in self._definitions_logged()
        }
        carried = {
            name: held[name]
            for name in held.columns
            if name in definitions and name not in result_df.columns
        }
        if carried:
            weight = sum(series.estimated_size() for series in carried.values())
            named = ", ".join(sorted(definitions[name] for name in carried))
            logger.info(
                f"Retaining {len(carried)} superseded definition(s) with their "
                f"own values: {named} -- about {weight / 1e6:.1f} MB held for "
                "this export. Pass retain_superseded=False to write them as "
                "history with no values."
            )
        return carried

    def _release_carried_definitions(self) -> None:
        """Drop the superseded definitions the frame is holding for an export.

        An export that declines to write those values is the last thing that
        was going to read them, so the frame stops holding them here. What
        this releases is their residency AFTER the run -- the collect that
        produced them has already been paid for, and no switch reached from
        here can unspend it.
        """
        if getattr(self.af, "_retained_values", None) is None:
            return
        logger.debug(
            "Releasing the superseded definitions this frame was holding: "
            "this export was asked not to write them."
        )
        self.af._retained_values = None  # noqa: SLF001 -- the frame's own
        self.af._retained_for = None  # noqa: SLF001 -- and the tie to them

    def _prepare_dataframe(
        self, df: pl.DataFrame, config: GraphExportConfig
    ) -> pl.DataFrame:
        """Prepare DataFrame by applying filters if specified."""
        # The model's own columns. A frame reaching here may be carrying a
        # superseded definition under a hidden name, or a reading of what a
        # compiled rollforward moved, and a log line naming either beside the
        # model's columns reads as though the model had one.
        named = [
            column
            for column in df.columns
            if column != ROW_STAMP
            and not column.startswith((_RETAINED_PREFIX, MOVEMENT_PREFIX))
        ]
        logger.debug(f"Result DataFrame has {len(df)} rows and columns: {named}")

        if config.filter_expr:
            filter_handler = DataFrameFilter(df)
            df = filter_handler.apply_filter(config.filter_expr)

        return df

    def _values_by_node(self, frame: pl.DataFrame) -> dict[NodeId, pl.Series]:
        """Return, per node, the column of ``frame`` whose values are that node's own.

        The type vocabulary names an integer width wider than ``i64`` on
        the numbers a column actually holds, and this is where an export
        says which numbers those are. Getting the pairing wrong would be
        worse than not answering: certifying one definition's width from
        another definition's values is exactly the inference the refusal
        exists to prevent, so the rule is that a node earns an entry only
        where the frame demonstrably holds *its* output.

        Three ways a node does:

        - **A column no calculation defines** is the values it arrived
          with, under its own name. A name something later wrote is not,
          which is why the defined names are taken out first.
        - **A column's live definition** is the column itself: that
          definition is what the frame ended up holding.
        - **A superseded definition** is the column the frame carried aside
          for it (:meth:`_carried_definitions`), and nothing else. Without
          retention there is no such column, so it earns no entry and its
          width is refused rather than read off its replacement.

        Everything else -- a definition renamed away, a column dropped
        before the model finished -- is absent, which is the same answer as
        a lazy export: no values in reach.

        The export's own row stamp earns no entry either. It is not a
        column of the model, no node is minted for it
        (:func:`~.graph_builder.fold`), and a width certified off it would
        be this export certifying its own scaffolding.
        """
        held = set(frame.columns)
        # The last definition of a column is the one the frame holds; every
        # earlier one was replaced. A write over the column outside the
        # frame's own operations is a definition here too: where it is the
        # last word, the column holds its values and not the calculation's.
        logged = self._definitions_logged()
        last = dict(logged)
        values: dict[NodeId, pl.Series] = {
            name: frame.get_column(name)
            for name in frame.columns
            if name not in last
            and name != ROW_STAMP
            and not name.startswith(_RETAINED_PREFIX)
        }
        for column, ordinal in logged:
            source = (
                column
                if last[column] == ordinal
                else _retained_column_name(column, ordinal)
            )
            if source in held:
                values[f"{column}@{ordinal}"] = frame.get_column(source)
        return values

    def _build_graph_structure(self, in_reach: ValuesInReach) -> CalcGraph:
        """Fold the frame's log into the graph, then fill in what it could not know."""
        graph = fold(self.af, values=in_reach, data_columns=self._data_columns)
        self._backfill_unresolved_dtypes(graph, in_reach)
        return graph

    def _backfill_unresolved_dtypes(
        self, graph: CalcGraph, in_reach: ValuesInReach
    ) -> None:
        """Resolve dtype and shape from the final schema where recording could not.

        A record's dtype comes from a cheap per-assignment probe and can be
        None (a probe failure also cascades to downstream assignments). The
        collected schema holds the authoritative dtype for every column that
        survived to the frame — prefer it over exporting "unknown".

        Only for the nodes the frame's columns actually hold: the schema
        describes the final frame, so borrowing a dtype from it for a
        superseded definition or a dropped column would state the surviving
        column's type as that node's own.

        The schema is a type and nothing else, which is why the values go
        with it: a wide integer resolved here is judged on the numbers the
        node's own column holds, exactly as one resolved in the fold is.

        A plan whose schema cannot be resolved at all is refused where the
        document is ``executable``. Its record typed every column ``unknown``
        and held none of them in the final schema, and an engine reading it
        computed nothing and said nothing: the JAX engine handed back the
        book's own columns and no answer (section 10: ``unknown`` is history,
        never a column the model holds). An ``audit`` record, which no engine
        runs, is still written, untyped, for the reader looking at the line
        that broke it.
        """
        lazy_frame = self.af._df  # noqa: SLF001
        if lazy_frame is None:
            logger.warning("Could not collect schema for dtype backfill: no frame")
            return

        try:
            schema = lazy_frame.collect_schema()
        except Exception as e:
            if self._refusing_an_untyped_plan:
                raise _a_plan_no_type_names(e) from e
            logger.warning(f"Could not collect schema for dtype backfill: {e}")
            return

        for node in graph.nodes.values():
            data = node.data
            # Nothing to backfill on a node the frame does not hold, and
            # nothing to look up for one that is not an account of a column
            # at all: a compiled rollforward and its running states have no
            # name here and no type the frame's schema could give them.
            if not data.in_final_schema or data.column is None:
                continue
            if "unknown" not in (data.dtype, data.shape):
                continue
            dtype = schema.get(data.column)
            if dtype is None:
                continue
            if data.dtype == "unknown":
                data.dtype = neutral_dtype(
                    dtype, column=data.column, values=in_reach.get(data.id)
                )
            if data.shape == "unknown":
                data.shape = shape_from_dtype(dtype)

    def _enhance_with_values(
        self,
        graph: CalcGraph,
        df: pl.DataFrame,
        config: GraphExportConfig,
        in_reach: ValuesInReach,
    ) -> None:
        """Add sample values to graph nodes.

        A value read off the column a frame ends up holding can only speak
        for the definition that column holds. A superseded definition given
        one that way would be shown carrying the value that replaced it — the
        wrong number against the right formula, which is worse than no number
        at all.

        So a superseded definition is read off its OWN output instead, where
        ``df`` carries it: the frame held that definition's column aside
        through the collect (:meth:`_carried_definitions`), and the node then
        declares ``retained`` so that a reader knows which frame the number in
        front of them came out of. Where nothing was carried — retention
        switched off, a freeze that settled the column before the export, a
        door that does not carry — the node stays as it always was: the
        formula, the reads and the source location, and no number.
        """
        extractor = SampleValueExtractor(
            df,
            config.policy_id,
            config.policy_id_column,
            config.period,
            config.row_pin,
        )

        for node_id, node in graph.nodes.items():
            # Nothing to read a value out of for a node that is not a
            # column: a compiled rollforward's own values live in a
            # scratch column the finished frame no longer holds, and a
            # running state was never a column of the frame at all.
            column = node.data.column
            if column is None:
                continue
            if not node.data.in_final_schema:
                self._enhance_a_superseded_definition(
                    node, column, df, extractor, in_reach.get(node_id)
                )
                continue
            sample_value = extractor.extract(column)
            if sample_value is not None:
                node.data.value_sample = sample_value
                logger.trace(f"Added sample value for {node_id}: {sample_value}")

    @staticmethod
    def _enhance_a_superseded_definition(
        node: GraphNode,
        column: str,
        df: pl.DataFrame,
        extractor: SampleValueExtractor,
        values: pl.Series | None,
    ) -> None:
        """Read one superseded definition's value off the output it produced.

        The type comes off the same column, and this is the one place a
        superseded definition earns a stated ``dtype`` and ``shape``: the
        format lets it carry ``unknown`` because the finished frame holds
        nothing to read them from, and here the producer did read one. Left
        ``unknown`` where nothing was carried, which is the case that
        permission was written for.

        ``values`` is that same carried column taken before the export's
        own filter, for the width question the type cannot answer; the
        sample beside it is read through the filter, because a sample is
        about one policy and a width is about every row.
        """
        if node.data.version is None:
            return
        held = _retained_column_name(column, node.data.version)
        if held not in df.columns:
            return
        sample_value = extractor.extract(held)
        if sample_value is None:
            return
        node.data.value_sample = sample_value
        node.data.retained = True
        dtype = df.schema[held]
        if node.data.dtype == "unknown":
            node.data.dtype = neutral_dtype(dtype, column=column, values=values)
        if node.data.shape == "unknown":
            node.data.shape = shape_from_dtype(dtype)
        logger.trace(f"Retained {node.data.id}: {sample_value}")

    def _enhance_with_branches(
        self,
        graph: CalcGraph,
        df: pl.DataFrame,
        config: GraphExportConfig,
    ) -> None:
        """State both branches of every conditional, and which one fired.

        A conditional's walk-through names the branch that fired and says
        nothing about the other one, and the other one is in no column of
        the finished frame: "what would this have been if the condition had
        gone the other way?" is a question the document could not answer at
        all. So each branch is evaluated -- through the same lowering the
        model ran under, against the same row every sample was read off --
        and the answer is written beside the sample it would have replaced.

        **Evaluated, never invented.** The subtree the branch is gets
        lowered by :mod:`gaspatchio.frame.lowering.polars` with this
        frame's own context, so the number in the record is the number the
        engine would have produced. Nothing here reads the formula text and
        nothing here guesses from the fired value.

        Only the nodes the frame still holds: a superseded definition's
        inputs may have been written over since, so evaluating its branches
        against the finished frame would answer with the values that
        replaced them. A node whose branches cannot be evaluated states
        none at all, which is why every failure below is a trace line and a
        skip rather than a null.
        """
        from gaspatchio.frame.lowering.context import (  # noqa: PLC0415 — import cycle
            LoweringContext,
        )

        context = LoweringContext(frame=self.af)
        extractor = SampleValueExtractor(
            df,
            config.policy_id,
            config.policy_id_column,
            config.period,
            config.row_pin,
        )
        stated = 0
        for node in graph.nodes.values():
            branches = _branches_of(graph, node, context=context, extractor=extractor)
            if branches is None:
                continue
            node.data.branches = branches
            stated += 1
            logger.trace(f"Stated both branches of {node.data.id}: {branches}")
        logger.info(f"Stated both branches on {stated} conditional nodes")

    def _add_traces(
        self,
        graph: CalcGraph,
        df: pl.DataFrame,
        config: GraphExportConfig,
    ) -> None:
        """Add calculation traces to computed nodes.

        Built over the engine's rendering rather than over the as-written
        formula, because a trace is a substitution: it replaces each column
        name with the number that column held, and the engine's rendering
        names its columns bare where a written line names them through the
        frame (``af.sum_assured``). Substituting into the written line would
        leave the frame's name stranded in front of every value and produce
        arithmetic nobody could read. The written line is what the node
        itself states; this is the walk-through beside it.

        **A line that folds down the model points gets no substitution.**
        The sampled policy's own number does not stand for a column that
        was summed over the whole population, and a walk-through that put
        it there would read as arithmetic a reader could check and could
        not. Those nodes say what was folded and over how many model
        points instead, which is the true statement the false one was
        standing in for.

        **A line with a fold inside it keeps its walk-through.**
        ``af.share = af.claims / af.claims.polars_native().sum()`` answers once per
        policy,
        so the sampled policy's own values stand for the operands outside
        the fold; only the ones inside it are left standing as their names,
        with the step saying which and over what they were folded.

        **A retained superseded definition walks through its own run.** Its
        reads all survive into the final schema -- a node that read something
        replaced is still refused a walk-through, for the reason
        :func:`_reads_a_replaced_value` states -- so the substitution is the
        same one every live node gets, and only the result it ends at is
        read from the column the frame held aside for it.
        """
        logger.info("Generating calculation traces for computed nodes")

        # Keyed by column name, because a trace substitutes values into a
        # rendered expression and that names columns, not node ids.
        #
        # Read whole rather than taken off the node's own sample: a sample
        # is a window on a per-period column and the walk-through has
        # things to say about the run behind that window -- how long it is,
        # where it ends, whether it ever turns negative -- which the window
        # has already thrown away.
        # Keyed by column, so only the definition the column HOLDS may enter
        # it: substituting a name means substituting what that name stood for
        # when the formula ran, and a superseded definition's values under
        # the shared column name would be a walk-through of arithmetic
        # nobody wrote.
        whole = SampleValueExtractor(
            df,
            config.policy_id,
            config.policy_id_column,
            None,
            config.row_pin,
        )
        node_values = {
            node.data.column: value
            for node in graph.nodes.values()
            if node.data.in_final_schema
            and node.data.value_sample is not None
            and node.data.column is not None
            and (value := whole.extract_whole(node.data.column)) is not None
        }
        # And, by node id, the run each retained superseded definition
        # produced -- what its own walk-through has to end at.
        retained_values: dict[NodeId, Any] = {}
        for node_id, node in graph.nodes.items():
            column, version = node.data.column, node.data.version
            if not node.data.retained or column is None or version is None:
                continue
            held = _retained_column_name(column, version)
            run = whole.extract_whole(held) if held in df.columns else None
            if run is not None:
                retained_values[node_id] = run

        # The population every fold in this export ran over: the rows the
        # frame holds *after* any filter, since a filtered export folded
        # fewer of them and a sentence naming the whole book would be
        # naming rows this run never saw. The period is the other narrowing
        # a reader may have asked for, and every line that prints one period
        # of a run says which period it is.
        batch = _TraceBatch(
            graph=graph,
            generator=TraceGenerator(
                node_values, population=df.height, period=config.period
            ),
            node_values=node_values,
            retained_values=retained_values,
            expressions=self._expressions_by_node(),
            # The frame's own schema with its rows taken away, built once: the
            # fold probe resolves every expression against it and computes
            # nothing over any real data.
            empty=df.head(0),
        )

        # Process computed nodes
        computed_count = 0

        for node_id, node in graph.nodes.items():
            if node.kind.value == "computed":
                computed_count += 1
                _attach_trace(batch, node_id, node)

        logger.info(
            f"Generated traces for {batch.trace_count}/{computed_count} computed nodes"
        )

    def _log_statistics(self, graph: CalcGraph, df: pl.DataFrame | None) -> None:
        """Log graph statistics."""
        stats = graph.get_node_stats()
        # Every kind the graph holds, so the parts add up to the total. A
        # line whose numbers do not reconcile sends a reader looking for
        # the nodes it left out rather than reading the model.
        logger.info(
            f"Graph built: {stats['total_nodes']} nodes "
            f"({stats['input_nodes']} inputs, {stats['computed_nodes']} computed, "
            f"{stats['hole_nodes']} unaccounted for, "
            f"{stats['rollforward_nodes']} compiled rollforwards, "
            f"{stats['state_nodes']} running states), "
            f"{stats['total_edges']} edges"
        )

        if df is not None:
            nodes_with_values = sum(
                1 for node in graph.nodes.values() if node.data.value_sample is not None
            )
            logger.info(
                f"Added sample values to "
                f"{nodes_with_values}/{stats['total_nodes']} nodes"
            )


# How the node line names each kind of node an exported document carries, in
# the order it states them: the kind, its singular and its plural, and whether
# the line states it when the model holds none. A compiled rollforward and its
# running states are not accounts of a column, and a model that never
# escalated to a state machine holds neither, so they are named only where
# there are any and that model's line reads as it always did. A column nothing
# accounts for is always stated, because "0 unaccounted for" is the claim.
_NODE_LINE: Final[tuple[tuple[NodeType, str, str, bool], ...]] = (
    (NodeType.INPUT, "input", "inputs", True),
    (NodeType.COMPUTED, "computed", "computed", True),
    (NodeType.ROLLFORWARD, "compiled rollforward", "compiled rollforwards", False),
    (NodeType.STATE, "running state", "running states", False),
    (NodeType.HOLE, "unaccounted for", "unaccounted for", True),
)


def node_accounting(nodes: list[dict[str, Any]]) -> str:
    """Return the one-line node census of an exported graph.

    Every node is one of five kinds -- a column the data arrived with, a
    calculation, a compiled rollforward, one of its running states, or a
    column nothing accounts for -- and every node is counted under its kind,
    so the parts add up to the total. A breakdown that silently left a kind
    out would send a reader subtracting to find what it omitted, and a model
    holding columns it cannot account for is the one fact nobody should have
    to work out for themselves.

    The two kinds that are not an account of a column are named only where
    the model holds one, so the line for a model that never escalated to a
    state machine is the line it always was.

    Args:
        nodes: The ``"nodes"`` list of an exported artifact, each entry
            carrying the node's ``"kind"`` -- the account it gives of its
            column.

    Returns:
        A line of the form ``"5 nodes: 2 inputs, 2 computed, 1 unaccounted
        for"``, or on a model with a state machine ``"11 nodes: 4 inputs,
        5 computed, 1 compiled rollforward, 1 running state, 0 unaccounted
        for"``. The count of columns nothing accounts for is always stated
        -- ``0 unaccounted for`` is a claim about the model, not an absence
        worth hiding.

    Raises:
        ValueError: If a node's kind is none of the five, which would leave
            the parts short of the total.

    Examples:
        >>> from gaspatchio.frame.graph import node_accounting
        >>> node_accounting([{"kind": "input"}, {"kind": "computed"}, {"kind": "hole"}])
        '3 nodes: 1 input, 1 computed, 1 unaccounted for'

    """
    counts: dict[str, int] = {kind.value: 0 for kind, *_ in _NODE_LINE}
    for node in nodes:
        kind = node.get("kind")
        if not isinstance(kind, str) or kind not in counts:
            msg = (
                f"{node.get('id')!r} is of kind {kind!r}, which is none of the "
                f"kinds a node can be: {', '.join(counts)}. Counting it under "
                "none of them would leave the parts short of the total. Check "
                "the document with gspio validate, which names every field "
                "that departs from the format."
            )
            raise ValueError(msg)
        counts[kind] += 1
    stated = ", ".join(
        f"{counts[kind.value]} {one if counts[kind.value] == 1 else many}"
        for kind, one, many, always in _NODE_LINE
        if always or counts[kind.value]
    )
    total = len(nodes)
    return f"{total} {'node' if total == 1 else 'nodes'}: {stated}"


class GraphFrameAccessor:
    """The model's own account of how each of its columns was made.

    ``af.graph`` answers the questions a reviewer asks of a calculation:
    what did this column read, who read it, what is behind it all the way
    down, what would move all the way forward if it changed, which
    versions of the name exist, which one is live, what can the model not
    account for, which lines are written outside the format's own
    vocabulary, and has any of it moved since last quarter.

    **A column name means the definition the frame holds now.** A model
    reassigns -- ``policies_in_force`` is written once before the lapse
    decrement and once after -- and those are two worksheet columns
    wearing one Python name. Every query here takes either the name, which
    answers for the live definition, or an explicit ``"column@ordinal"``,
    which answers for that one. A name the graph has never held is
    refused, by name: an empty tuple would read as "nothing depends on
    it", which is a different and much more comfortable answer than "you
    asked about a column that does not exist".

    **Answers are node ids, not column names.** ``precedents("death_claims")``
    naming ``policies_in_force@1`` is the whole point: it says which
    version the claims were taken on, which a column name cannot.

    **Nothing here runs the model.** The graph is folded from the
    calculation log and the frame's schema, cached, and re-folded the
    moment either moves -- a new assignment, a ``drop``, a plan written
    directly. Asking how a number was made never costs computing one.

    **``graph`` is a reserved attribute name on the frame**, as ``date``,
    ``excel``, ``finance`` and ``projection`` are. A model whose data really
    does carry a column called ``graph`` still has it -- reach it as
    ``af["graph"]`` -- but ``af.graph`` is always this accessor.

    Examples:
        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> model_points = pl.DataFrame(
        ...     {
        ...         "sum_assured": [100_000.0],
        ...         "mortality_rate": [0.01],
        ...         "lapse_rate": [0.05],
        ...     }
        ... )
        >>> af = ActuarialFrame(model_points)
        >>> af.policies_in_force = 1.0 - af.mortality_rate
        >>> af.death_claims = af.sum_assured * af.mortality_rate
        >>> af.policies_in_force = af.policies_in_force * (1.0 - af.lapse_rate)

        The inforce after lapses is a second definition, and the graph
        says which one anything read:

        >>> af.graph.versions("policies_in_force")
        ('policies_in_force@1', 'policies_in_force@2')
        >>> af.graph.latest("policies_in_force")
        'policies_in_force@2'
        >>> af.graph.precedents("policies_in_force")
        ('policies_in_force@1', 'lapse_rate')

    """

    def __init__(self, frame: GraphSource) -> None:
        """Bind the query surface to ``frame``, with nothing folded yet.

        The fold is deferred to the first question. An accessor is built
        on the first ``af.graph`` and kept, so a model that never asks
        one pays nothing for it.
        """
        self._frame = frame
        self._cached_graph: CalcGraph | None = None
        self._cached_state: tuple[int, int, frozenset[str]] | None = None
        self._cached_fingerprint: str | None = None
        self._cached_lineage: Lineage | None = None

    @property
    def last_run(self) -> RunSummary | None:
        """Read the current plan's last successful collection without executing.

        The summary names the engine, requested Polars execution mode where
        applicable, profiling, result shape and the engine's own report.
        Successful engine notes are available in ``last_run.report.notes``.
        None means this plan has not completed a collection, its plan changed,
        or a new attempt has started without completing successfully.

        ``materialize()`` changes the plan to frozen values and clears this
        reading. A returned summary is immutable and may be kept by the caller.
        No device is inferred from an engine name.

        ``last_run.versions`` answers the question a reviewer puts to any
        number: same model, same data -- would the library this ran on give
        the same answer? A Polars run names the core package's version, the
        version its compiled extension was built as, the Polars version, the
        platform, Python and the extension's digest; a run on a second engine
        names what that engine's own result manifest states.
        It is read when asked for, so a collect never pays for it. The model
        half of the question is :meth:`fingerprint`. For a model that rebuilds
        its frame from bare values in setup, as the three-phase template
        teaches, the fingerprint a results file or an audit file states is
        not this one -- the commands are told the model points file's
        columns and state the rebuilt ones as holes -- and building the frame
        with ``ActuarialFrame(df, continue_from=af)`` keeps the two one model.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> af = ActuarialFrame(pl.DataFrame({"premium": [1200.0, 900.0]}))
            >>> af.commission = af.premium * 0.05
            >>> af.graph.last_run is None
            True
            >>> _ = af.collect()
            >>> run = af.graph.last_run
            >>> run.engine, run.rows, run.columns
            ('polars', 2, 2)
            >>> run.versions["polars_version"] == pl.__version__
            True
            >>> run.versions["extension_sha256"].startswith("sha256:")
            True

        """
        return self._frame._last_run  # noqa: SLF001 -- the frame owns completion

    # --- the cached fold ----------------------------------------------------

    @property
    def _state(self) -> tuple[int, int, frozenset[str]]:
        """Return everything the fold's answer depends on, as one key.

        Three parts, because there are three ways the answer moves and
        only one of them is an append:

        1. **How long the log is.** Every assignment appends a record, so
           a longer log is a graph with more nodes in it.
        2. **Which generation the query plan is on.** ``drop``, ``select``,
           ``filter`` and a plan written straight into ``_df`` all change
           the schema without appending anything -- and the schema is what
           decides which nodes are what the frame actually holds and which
           columns nothing accounts for. The frame bumps this counter on
           every plan swap, which is exactly the event to key on.
        3. **Which columns arrived with the data.** Two sets answer that
           between them. ``_initial_columns`` holds the arriving columns
           under the names the frame calls them by now, and through
           ``_unaccounted_columns`` it is the difference between calling a
           column an input and calling it a hole; a frame derived from
           another works it out for itself, and a rename or a drop moves
           it. ``_arrival_names`` holds the names those columns arrived
           under and ``_arrival_schema`` the types, and the graph seeds the
           inputs from both. Only the first is keyed on, because only the
           first can move: the arrival record is fixed when the frame is
           built and a derived frame is a different frame with a cache of
           its own.

        Cheap enough to take on every question: two integers and a
        frozenset the frame already holds.
        """
        frame = self._frame
        return (
            len(frame._calculations),  # noqa: SLF001 -- the frame's own log
            frame._schema_generation,  # noqa: SLF001 -- the frame's own plan
            frame._initial_columns,  # noqa: SLF001 -- the frame's own inputs
        )

    @property
    def _graph(self) -> CalcGraph:
        """Return the folded graph, folding again only when the frame moved.

        Folded without refusing a calculation whose type has no name: no
        question asked here is about a calculation's type. The export is,
        and it folds again and refuses that type by name (see :func:`fold`).
        """
        state = self._state
        if self._cached_graph is None or self._cached_state != state:
            self._cached_graph = fold(self._frame, refuse_unnamed=False)
            self._cached_state = state
            self._cached_fingerprint = None
            self._cached_lineage = None
        return self._cached_graph

    @property
    def _lineage(self) -> Lineage:
        """Return the folded graph's lineage, the structure every walk reads.

        The same :class:`~.lineage.Lineage` an exported document is read into
        (:func:`gaspatchio.graph.read_artifact`), so a question asked here and
        the same question asked of the file are answered by one walk.
        """
        graph = self._graph
        if self._cached_lineage is None:
            self._cached_lineage = Lineage.of_graph(graph)
        return self._cached_lineage

    # --- resolving what the caller named ------------------------------------

    def _resolve(self, column: str) -> NodeId:
        """Return the node ``column`` names: a live definition, or an exact one.

        A column name resolves to whichever definition is live at the end
        of the log -- the last one written, or the arriving value if
        nothing on the frame defined it. An explicit ``"column@ordinal"``
        resolves to that definition. The column name is tried first, so a
        column whose own name contains an ``@`` still answers for itself.
        Asking for a version that does not exist is answered with the
        versions that do; any other name the graph has never held, with the
        nearest columns it does hold.

        Raises:
            ValueError: If the graph holds no such column and no such node.

        """
        return self._lineage.resolve(column)

    def _column_of(self, column: str) -> str:
        """Return the column a name or a versioned node id belongs to.

        Raises:
            ValueError: If the name resolves to a node that is not an
                account of a column at all -- a compiled rollforward or one
                of its running states, both of which live in a reserved id
                namespace. A question about a column has no answer there,
                and the refusal says so rather than handing back a null.

        """
        return self._lineage.column_of(column)

    # --- the questions ------------------------------------------------------

    def precedents(self, column: str) -> tuple[NodeId, ...]:
        """Return the definitions ``column``'s own formula read.

        The worksheet's backward audit arrow, and the other half of the
        pair :meth:`dependents` completes. Direct reads only, in the order
        the formula names them: the operands of one line of the model,
        bound to the versions that were live when it ran.

        Empty for a leaf -- a column the data arrived with, and a column
        nothing accounts for. A **joined** column is not a leaf: it reads
        the key the join matched it on, because the key decides which row
        of the other table it holds. Move a policy's product code and its
        commission rate is another product's. The key selects the row
        rather than being arithmetic on it, so the read is recorded as a
        key read, the same kind of read a table lookup's key is.

        The other table is not a precedent: it is data the join was
        handed, identified by its content. That identity is part of the
        joined column's own, so a revised table moves :meth:`fingerprint`,
        and the exported document carries the table itself beside the
        model.

        Args:
            column: A column name, answering for the definition the frame
                holds now, or an explicit ``"column@ordinal"``.

        Returns:
            The node ids the formula read, first mention first.

        Raises:
            ValueError: If the graph holds no such column and no such node.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {
            ...         "sum_assured": [100_000.0],
            ...         "mortality_rate": [0.01],
            ...         "lapse_rate": [0.05],
            ...     }
            ... )
            >>> af = ActuarialFrame(model_points)
            >>> af.policies_in_force = 1.0 - af.mortality_rate
            >>> af.death_claims = af.sum_assured * af.mortality_rate
            >>> af.policies_in_force = af.policies_in_force * (1.0 - af.lapse_rate)
            >>> af.graph.precedents("death_claims")
            ('sum_assured', 'mortality_rate')

            The name answers for the live definition; the ordinal answers
            for the one it replaced:

            >>> af.graph.precedents("policies_in_force")
            ('policies_in_force@1', 'lapse_rate')
            >>> af.graph.precedents("policies_in_force@1")
            ('mortality_rate',)

            A commission rate joined in from a product table reads the
            product code it was matched on:

            >>> products = pl.DataFrame(
            ...     {"product": ["term", "whole_life"], "commission_rate": [0.05, 0.03]}
            ... )
            >>> af = ActuarialFrame(
            ...     pl.DataFrame({"product": ["term"], "premium": [1_200.0]})
            ... )
            >>> af = af.join(products, on="product")
            >>> af.graph.precedents("commission_rate")
            ('product',)

        """
        return self._lineage.precedents(column)

    def dependents(self, column: str) -> tuple[NodeId, ...]:
        """Return the definitions that read ``column`` directly.

        The worksheet's forward audit arrow: :meth:`precedents` reads one
        way along an edge, this one reads the same edge the other way, in
        the order the model defined them. Asked of a column name this
        answers for the live definition, so a version something later
        replaced reports the readers *it* has -- which is usually none,
        and is the honest answer: what reads the replacement is not what
        read this.

        **Pointed at a column that is a running balance materialised, the
        arrow follows the balance.** A line assigning
        ``compiled.expr_for("fund")`` writes a state machine's own fund out
        onto the frame, and the node says so in ``extracts``. The state
        machine reads the *state*, never that column, so an arrow drawn
        from the column alone stops where it starts -- and says nothing
        reads a fund the guarantee beside it is struck against. So the
        readers of the running state join the answer, in the order the
        model built them. Asked of a state id, or of a column that
        materialises nothing, this is what it always was.

        Args:
            column: A column name, answering for the definition the frame
                holds now, or an explicit ``"column@ordinal"``.

        Returns:
            The node ids whose formulas read it, in the order the model
            defined them.

        Raises:
            ValueError: If the graph holds no such column and no such node.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {
            ...         "sum_assured": [100_000.0],
            ...         "mortality_rate": [0.01],
            ...         "lapse_rate": [0.05],
            ...     }
            ... )
            >>> af = ActuarialFrame(model_points)
            >>> af.policies_in_force = 1.0 - af.mortality_rate
            >>> af.death_claims = af.sum_assured * af.mortality_rate
            >>> af.policies_in_force = af.policies_in_force * (1.0 - af.lapse_rate)
            >>> af.graph.dependents("mortality_rate")
            ('policies_in_force@1', 'death_claims@1')

            A separate-account fund whose charge is struck on the running
            balance. Nothing on the frame reads ``account_value``; what
            reads the balance that column materialises is the state
            machine, and the arrow finds it one hop out:

            >>> import datetime
            >>> from gaspatchio.rollforward import compile_rollforward
            >>> af = ActuarialFrame({"av_init": [100.0], "me": [[0.001] * 2]})
            >>> af = af.projection.set(
            ...     start_date=datetime.date(2025, 1, 31),
            ...     n_periods=2,
            ...     frequency="monthly",
            ... )
            >>> builder = af.projection.rollforward(states={"av": af["av_init"]})
            >>> _ = builder["av"].charge(af["me"], label="me_charge")
            >>> af.account_value = compile_rollforward(builder).expr_for("av")
            >>> af.graph.dependents("account_value")
            ('rollforward:...',)

        """
        return self._lineage.dependents(column)

    def trace(self, column: str, *, depth: int | None = None) -> tuple[NodeId, ...]:
        """Return everything behind ``column``, all the way down to the leaves.

        The transitive closure over what each node read, ending with the
        node asked about. Ordered as the model built it, so every node
        appears after everything it reads and the last entry is the answer
        the rest of the cone produces -- read it top to bottom and you
        have the derivation.

        The walk stops at leaves: a column the data arrived with, and a
        column nothing accounts for. It runs on through a **joined** column
        to the key the join matched it on, since the key chose the row the
        column holds. The other table the join read is not a node: it is
        data, identified by its content, and that identity is part of the
        joined column's own fingerprint, so a revised table still moves it.
        Reaching a hole means something else, and more bluntly: this is
        where the model's account of itself ends.

        The cone runs all the way down unless ``depth`` cuts it: ``depth=1``
        is the column and what it read, ``depth=2`` adds what those read,
        and so on -- the same cut ``gspio graph trace --depth`` makes on an
        exported file, answered by the same walk.

        Args:
            column: A column name, answering for the definition the frame
                holds now, or an explicit ``"column@ordinal"``.
            depth: How many reads back to follow, ``0`` for the column
                alone. ``None``, the default, follows every read. A depth
                that is not a whole number of reads is refused with a
                ``ValueError``.

        Returns:
            Every node in the cone, each once however many paths reach it,
            in the order the model defined them, ending with ``column``'s
            own node.

        Raises:
            ValueError: If the graph holds no such column and no such node.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {
            ...         "sum_assured": [100_000.0],
            ...         "mortality_rate": [0.01],
            ...         "lapse_rate": [0.05],
            ...     }
            ... )
            >>> af = ActuarialFrame(model_points)
            >>> af.policies_in_force = 1.0 - af.mortality_rate
            >>> af.death_claims = af.sum_assured * af.mortality_rate
            >>> af.policies_in_force = af.policies_in_force * (1.0 - af.lapse_rate)
            >>> af.graph.trace("policies_in_force")  # doctest: +NORMALIZE_WHITESPACE
            ('mortality_rate', 'lapse_rate',
             'policies_in_force@1', 'policies_in_force@2')

            One read back is the formula's own operands and the column:

            >>> af.graph.trace("policies_in_force", depth=1)
            ('lapse_rate', 'policies_in_force@1', 'policies_in_force@2')

            A column the data arrived with is its own whole cone:

            >>> af.graph.trace("sum_assured")
            ('sum_assured',)

        """
        return self._lineage.trace(column, depth=depth)

    def affected(
        self,
        column: str | None = None,
        *,
        assumption: str | None = None,
        depth: int | None = None,
    ) -> tuple[NodeId, ...]:
        """Return everything ahead of ``column``, all the way to the outputs.

        The question a reviewer asks of an assumption: if this moves, what
        moves with it? :meth:`dependents` answers one hop of it; this
        answers all of them. The transitive closure over what read each
        node, starting with the node asked about. Ordered as the model
        built it, so every node appears after everything that reaches it
        and the first entry is the change the rest of the cone is the
        consequence of -- read it top to bottom and you have the
        propagation, as :meth:`trace` read top to bottom is the derivation.

        The four questions are two axes crossed. ``precedents`` and
        ``dependents`` are the worksheet's one-hop audit arrows, one each
        way along an edge. ``trace`` is the whole derivation *behind* a
        column; ``affected`` is the whole consequence *ahead* of it.

        The two forward questions are paired the same way on a column that
        is a running balance materialised: the cone opens at the running
        state as well as at the column, so that moving a fund reaches the
        guarantee struck against it. :meth:`dependents` says why, and the
        two backward questions need none of it -- they already reach the
        state, because the column reads the compilation and the
        compilation reads the state.

        The walk stops where nothing reads: a column the model computed
        and nothing else used, and a definition no later line reads, even
        where the name it wrote lives on. A superseded definition answers
        with the readers *it* has and everything past them; what the
        replacement decided is whether *it* reads the old definition, not
        whether the cone reaches it. That is the whole rule, and it is a
        closure over reads rather than a walk along the versions of a
        name: one name holds as many definitions as the model wrote, and
        the cone holds the ones a reads path runs through. Every claim
        about a shape below is an example that runs.

        **Ask it of an assumption table by name** with ``assumption=``:
        "if the mortality table moves, what moves?" The cone opens at every
        calculation whose own formula looked the table up -- the node's
        ``reads_assumptions`` in the exported file -- and runs forward from
        all of them at once. A table a join brought in is not looked up by
        any formula; the column it was matched on is what selected its rows,
        so ask what that key affects.

        ``depth`` cuts the cone after that many reads forward, as it cuts
        :meth:`trace` backward.

        Args:
            column: A column name, answering for the definition the frame
                holds now, or an explicit ``"column@ordinal"``. Name this or
                ``assumption``, not both: a ``ValueError`` says so.
            assumption: The name of an assumption entry -- a table's own
                name -- to start from every calculation that read it, so the
                answer starts with the first of them. A name no calculation
                reads is refused with a ``ValueError`` naming the nearest ones
                that are read.
            depth: How many reads forward to follow, ``0`` for the start
                alone. ``None``, the default, follows every read. A depth
                that is not a whole number of reads is refused with a
                ``ValueError``.

        Returns:
            Every node the change would reach, each once however many
            paths reach it, in the order the model defined them, starting
            with ``column``'s own node.

        Raises:
            ValueError: If the graph holds no such column and no such node.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {
            ...         "sum_assured": [100_000.0],
            ...         "mortality_rate": [0.01],
            ...         "lapse_rate": [0.05],
            ...     }
            ... )
            >>> af = ActuarialFrame(model_points)
            >>> af.policies_in_force = 1.0 - af.mortality_rate
            >>> af.death_claims = af.sum_assured * af.mortality_rate
            >>> af.policies_in_force = af.policies_in_force * (1.0 - af.lapse_rate)
            >>> af.graph.affected("mortality_rate")  # doctest: +NORMALIZE_WHITESPACE
            ('mortality_rate', 'policies_in_force@1',
             'death_claims@1', 'policies_in_force@2')

            A column nothing has read yet is its own whole cone:

            >>> af.graph.affected("death_claims")
            ('death_claims@1',)

            The third line rewrote ``policies_in_force`` in terms of the
            definition it replaces -- the reassignment ordinary models are
            full of -- so the replacement reads it and the cone holds both:

            >>> af.graph.affected("policies_in_force@1")
            ('policies_in_force@1', 'policies_in_force@2')

            Naming a working column and rebinding the balance onto it is
            how a charge gets deducted. The rebind names no version of
            ``account_value`` at all, and the cone crosses into the
            definition it writes anyway -- and on to the surrender value
            past that -- because the intermediate it reads was itself
            derived from the opening balance:

            >>> policy = pl.DataFrame(
            ...     {
            ...         "opening_av": [1000.0],
            ...         "coi_rate": [0.002],
            ...         "statutory_floor": [900.0],
            ...     }
            ... )
            >>> af = ActuarialFrame(policy)
            >>> af.account_value = af.opening_av * 1.0
            >>> af.coi_charge = af.account_value * af.coi_rate
            >>> af.av_after_charges = af.account_value - af.coi_charge
            >>> af.account_value = af.av_after_charges
            >>> af.surrender_value = af.account_value * 0.95
            >>> af.graph.affected("account_value@1")  # doctest: +NORMALIZE_WHITESPACE
            ('account_value@1', 'coi_charge@1', 'av_after_charges@1',
             'account_value@2', 'surrender_value@1')

            It reaches the definition the rebind wrote and runs on from
            there as far as reads carry it -- and no further. Write the
            balance again from an independent source and the cone is
            unmoved, while the bare name answers for a third definition
            the opening balance had no part in:

            >>> af.account_value = af.statutory_floor * 1.0
            >>> af.graph.affected("account_value@1")  # doctest: +NORMALIZE_WHITESPACE
            ('account_value@1', 'coi_charge@1', 'av_after_charges@1',
             'account_value@2', 'surrender_value@1')
            >>> af.graph.affected("account_value")
            ('account_value@3',)

            Now write the working column afresh from the statutory-floor
            column, which in this model is a column the data arrived
            with. What decides whether the cone crosses a replacement is
            not the one read at its head but whether anything behind it
            reads back to the definition you asked about, so walk the
            whole way down: what the rebind reads, what that definition
            reads, and where the reading stops.

            >>> af = ActuarialFrame(policy)
            >>> af.account_value = af.opening_av * 1.0
            >>> af.coi_charge = af.account_value * af.coi_rate
            >>> af.av_after_charges = af.account_value - af.coi_charge
            >>> af.av_after_charges = af.statutory_floor * 1.0
            >>> af.account_value = af.av_after_charges
            >>> af.surrender_value = af.account_value * 0.95
            >>> af.graph.precedents("account_value@2")
            ('av_after_charges@2',)
            >>> af.graph.precedents("av_after_charges@2")
            ('statutory_floor',)
            >>> af.graph.precedents("statutory_floor")
            ()

            Each answer but the last names one node, and each name is
            asked about in turn, so the walk exhausts the frontier
            rather than taking a first step: the two nodes behind the
            rebind are the working column's new definition and a floor
            that reads nothing, and neither of them is the opening
            balance. So the cone stops here at the definition the
            rewrite replaced, severing the path that carried the opening
            balance out to the surrender value above:

            >>> af.graph.affected("account_value@1")
            ('account_value@1', 'coi_charge@1', 'av_after_charges@1')

            The severing was in the reading, not in the shape of the
            line. Put a real floor in that same position -- one that
            keeps the balance where it already clears the minimum -- and
            the floor as written below names among its own operands the
            definition it replaces:

            >>> from gaspatchio import when
            >>> af = ActuarialFrame(policy)
            >>> af.account_value = af.opening_av * 1.0
            >>> af.coi_charge = af.account_value * af.coi_rate
            >>> af.av_after_charges = af.account_value - af.coi_charge
            >>> af.av_after_charges = (
            ...     when(af.av_after_charges < af.statutory_floor)
            ...     .then(af.statutory_floor)
            ...     .otherwise(af.av_after_charges)
            ... )
            >>> af.account_value = af.av_after_charges
            >>> af.surrender_value = af.account_value * 0.95
            >>> af.graph.precedents("av_after_charges@2")
            ('av_after_charges@1', 'statutory_floor')

            That read is the path, whole again, and in this model the
            cone runs on through the floor's own definition, into the
            rebind, and out to the surrender value:

            >>> af.graph.affected("account_value@1")  # doctest: +NORMALIZE_WHITESPACE
            ('account_value@1', 'coi_charge@1', 'av_after_charges@1',
             'av_after_charges@2', 'account_value@2', 'surrender_value@1')

            Back to the rewrite: that path, and no more than that path.
            Let the rebind subtract a charge struck off the opening
            balance as well, and one severed read decides nothing: the
            opening balance reaches the surrender value after all:

            >>> af = ActuarialFrame(policy)
            >>> af.account_value = af.opening_av * 1.0
            >>> af.coi_charge = af.account_value * af.coi_rate
            >>> af.av_after_charges = af.account_value - af.coi_charge
            >>> af.av_after_charges = af.statutory_floor * 1.0
            >>> af.account_value = af.av_after_charges - af.coi_charge
            >>> af.surrender_value = af.account_value * 0.95
            >>> af.graph.affected("account_value@1")  # doctest: +NORMALIZE_WHITESPACE
            ('account_value@1', 'coi_charge@1', 'av_after_charges@1',
             'account_value@2', 'surrender_value@1')

            Move a fund that a benefit base ratchets to, and the guarantee
            moves with it. Nothing on the frame reads the ``fund`` column;
            what reads the fund is the state machine, through the running
            balance the column materialises, and the cone opens there too:

            >>> import datetime
            >>> from gaspatchio.rollforward import compile_rollforward
            >>> af = ActuarialFrame(
            ...     {
            ...         "fund_init": [100.0],
            ...         "gmdb_init": [100.0],
            ...         "rate": [[0.01, 0.01]],
            ...         "anniv": [[False, True]],
            ...     }
            ... )
            >>> af = af.projection.set(
            ...     start_date=datetime.date(2025, 1, 31),
            ...     n_periods=2,
            ...     frequency="monthly",
            ... )
            >>> builder = af.projection.rollforward(
            ...     states={"fund": af["fund_init"], "gmdb": af["gmdb_init"]}
            ... )
            >>> _ = builder["fund"].grow(af["rate"], label="growth")
            >>> _ = builder["gmdb"].ratchet(
            ...     to=pl.col("fund@eop"), when=af["anniv"], label="ratchet"
            ... )
            >>> compiled = compile_rollforward(builder)
            >>> af.fund = compiled.expr_for("fund")
            >>> af.gmdb = compiled.expr_for("gmdb")
            >>> af.graph.affected("fund")  # doctest: +NORMALIZE_WHITESPACE
            ('state:fund@eop', 'rollforward:...',
             'fund@1', 'gmdb@1')

            Restate the product a policy is written under, and the rate a
            join brought in on that code moves, and so does everything
            struck on the rate. The cone crosses the join because the
            joined column reads the key it was matched on:

            >>> products = pl.DataFrame(
            ...     {"product": ["term", "whole_life"], "commission_rate": [0.05, 0.03]}
            ... )
            >>> af = ActuarialFrame(
            ...     pl.DataFrame({"product": ["term"], "premium": [1_200.0]})
            ... )
            >>> af = af.join(products, on="product")
            >>> af.commission = af.premium * af.commission_rate
            >>> af.graph.dependents("product")
            ('commission_rate@1',)
            >>> af.graph.affected("product")
            ('product', 'commission_rate@1', 'commission@1')

            Move the mortality table and the rate looked up from it moves,
            and the claims struck on that rate; the premium, which never
            read the table, does not:

            >>> from gaspatchio.assumptions import Table
            >>> mortality = Table(
            ...     name="mortality",
            ...     source=pl.DataFrame({"age": [40, 41], "rate": [0.001, 0.0012]}),
            ...     dimensions={"age": "age"},
            ...     value="rate",
            ... )
            >>> af = ActuarialFrame(
            ...     pl.DataFrame({"age": [40], "sum_assured": [100_000.0]})
            ... )
            >>> af.q = mortality.lookup(age=af.age)
            >>> af.claims = af.sum_assured * af.q
            >>> af.premium = af.sum_assured * 0.002
            >>> af.graph.affected(assumption="mortality")
            ('q@1', 'claims@1')

        """
        return self._lineage.affected(column, assumption=assumption, depth=depth)

    def versions(self, column: str) -> tuple[NodeId, ...]:
        """Return every definition of ``column``, oldest first.

        The model's own history of one name: one entry per assignment that
        wrote it. Empty for a column nothing on the frame defined -- a
        model-point field or a column nothing accounts for -- which is
        what makes those columns leaves rather than calculations.

        History of the *name*, not of the schema. A column the model
        computed and then dropped keeps every definition it ever had:
        dropping a column does not unmake the calculation, and a graph
        that forgot it could not answer where a number in an earlier
        output came from. Whether the frame still holds the value is a
        different question, and the node answers it -- ``in_final_schema``
        is ``False`` for exactly that case.

        Args:
            column: A column name, or an explicit ``"column@ordinal"``,
                which answers for the column that node defines.

        Returns:
            The column's definition node ids, oldest first.

        Raises:
            ValueError: If the graph holds no such column and no such node.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {
            ...         "sum_assured": [100_000.0],
            ...         "mortality_rate": [0.01],
            ...         "lapse_rate": [0.05],
            ...     }
            ... )
            >>> af = ActuarialFrame(model_points)
            >>> af.policies_in_force = 1.0 - af.mortality_rate
            >>> af.policies_in_force = af.policies_in_force * (1.0 - af.lapse_rate)
            >>> af.graph.versions("policies_in_force")
            ('policies_in_force@1', 'policies_in_force@2')
            >>> af.graph.versions("sum_assured")
            ()

        """
        return self._lineage.versions_of(self._column_of(column))

    def latest(self, column: str) -> NodeId:
        """Return the node holding ``column``'s value at the end of the log.

        The column's last definition, or the arriving node if nothing on
        the frame defined it. Asked with an explicit ``"column@ordinal"``
        it still answers with the last definition of that column, not the
        ordinal handed in: the question is which node the value came from.

        "Last" is about the log, not the schema. A column the model
        computed and then dropped still has a last definition and this
        still names it, because the graph is the model's history and the
        calculation did happen. Read the node's ``in_final_schema`` to ask
        the other question -- whether the frame still holds the value --
        which is ``False`` for a dropped column and for every definition a
        later one superseded.

        Args:
            column: A column name, or an explicit ``"column@ordinal"``.

        Returns:
            The node id the column's value comes from.

        Raises:
            ValueError: If the graph holds no such column and no such node.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {
            ...         "sum_assured": [100_000.0],
            ...         "mortality_rate": [0.01],
            ...         "lapse_rate": [0.05],
            ...     }
            ... )
            >>> af = ActuarialFrame(model_points)
            >>> af.policies_in_force = 1.0 - af.mortality_rate
            >>> af.policies_in_force = af.policies_in_force * (1.0 - af.lapse_rate)
            >>> af.graph.latest("policies_in_force")
            'policies_in_force@2'
            >>> af.graph.latest("sum_assured")
            'sum_assured'

        """
        return self._lineage.resolve(self._column_of(column))

    def unused(self, keep: Iterable[str] = ()) -> Unused:
        """Return every calculation nothing reads, each under the one class it is.

        The question a reviewer asks before trusting a model: which of these
        lines does nothing use? A node nothing reads is one of five things,
        and the record says which without a guess:

        - ``superseded`` -- a definition a later line of the same column
          replaced, read by nothing before it was. Dead code.
        - ``data`` -- a column that arrived, with the model points, from a
          table, handed over at a line or brought in by a join, that nothing
          reads.
        - ``stamp`` -- a column the projection timeline set up that nothing
          reads.
        - ``length_only`` -- a column read only for its length, as the
          ``like=`` of a broadcast: the model uses how long it is, never
          its values.
        - ``terminal`` -- a live calculation nothing reads. A result, or dead
          code. The model does not say which, so neither does this.

        **Name your results in ``keep``** and they move to ``kept``, so what
        is left under ``terminal`` is what nobody has vouched for.

        A column assigned a running balance is unused when no line reads the
        column: the state machine reads the balance, not the column, and
        nothing would change if the line were deleted. (:meth:`affected`
        answers a different question -- what moves when the balance moves --
        and follows the balance.) A column nothing accounts for has no
        account to classify; :meth:`holes` names it.

        Args:
            keep: Column names, or explicit ``"column@ordinal"`` ids, to set
                aside as kept. A name answers for its live definition: a
                result is what the frame holds now, and an earlier definition
                nothing read is still dead code.

        Returns:
            An :class:`~gaspatchio.frame.graph.lineage.Unused` with one tuple
            of node ids per class, each in the order the model defined them,
            and the ``counts``.

        Raises:
            ValueError: If a name in ``keep`` is not in the graph.

        Examples:
            >>> import datetime
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {
            ...         "policy_id": ["A"],
            ...         "sum_assured": [100_000.0],
            ...         "q": [0.01],
            ...         "smoker": ["N"],
            ...     }
            ... )
            >>> af = ActuarialFrame(model_points).projection.set(
            ...     start_date=datetime.date(2025, 1, 31),
            ...     n_periods=3,
            ...     frequency="monthly",
            ... )
            >>> af.claims = af.sum_assured * af.q
            >>> af.claims = af.sum_assured * af.q * 1.05
            >>> af.smoker_by_period = af.smoker.projection.broadcast_to_periods(
            ...     like=af.month
            ... )
            >>> unused = af.graph.unused()
            >>> unused.superseded, unused.data, unused.length_only
            (('claims@1',), ('policy_id',), ('month@1',))
            >>> unused.terminal
            ('claims@2', 'smoker_by_period@1')

            The claims are the result; say so, and one terminal is left:

            >>> kept = af.graph.unused(keep=["claims"])
            >>> kept.kept, kept.terminal
            (('claims@2',), ('smoker_by_period@1',))
            >>> kept.counts["stamp"]
            3

        """
        return self._lineage.unused(keep)

    def holes(self) -> list[Hole]:
        """Return what this model cannot explain, on the frame or in a record.

        Every column a finished model holds should be one of three things:
        a calculation the frame recorded, a field the data arrived with,
        or a column of values injected at a known line. A hole is the
        fourth case, and the empty list is the claim worth making -- not a
        default, but a positive statement that this model can account for
        every column it carries and every name its records read.

        Each hole carries the column's name, the reason -- what the frame
        saw of it -- and a hint naming the next move:

        - ``"overwritten"``: a column the frame had accounted for that a
          write straight into ``af._df`` replaced. Make the change through
          the frame, so the calculation is recorded.
        - ``"rebuilt"``: a column the frame was built holding whose values a
          calculation on another frame made. Build the frame with
          ``continue_from=`` to keep that calculation.
        - ``"unrecorded"``: anything else. For a column sitting on the
          frame, assign it through the frame so the calculation is
          recorded, or load it with the model points so it arrives as an
          input. For a name a record reads that no frame ever held, the
          opposite -- there is no column to record, and the record naming
          it is what needs fixing.

        **What it cannot see.** The claim is exactly as wide as the
        evidence behind each reason. A write that goes around even
        ``af._df`` -- ``object.__setattr__`` on the frame's own storage, an
        edit to the calculation log -- is not seen, and neither is one that
        only reorders, filters or moves whole rows or hands a column back
        unchanged, or a plan rebuilt in the old one's shape whose difference
        lies inside an expression Polars' reader cannot show and the plan's
        text does not print, such as which table an assumption lookup reads,
        a cut's breaks or two Python functions printed alike. A
        rebuild is seen by memory, so values that were copied on the way
        -- filtered, sorted, joined, cast, rechunked, sliced, or written out
        and read back -- arrive as data, as do values nobody held any
        longer when the new frame was built, values from another process,
        and a one-row column. See
        :data:`~gaspatchio.frame.graph.graph_models.HoleReason`.

        **An empty list does not mean every line is ``core``.** A line
        written in an engine's own expression language -- ``.polars_native()``,
        or a Polars expression handed to ``with_columns`` -- is recorded, so
        it is accounted for and is no hole, and it is still ``engine_native``:
        a calculation only that engine can run. A line reaching an operation
        nothing has classified -- one an extension registered under a name
        of its own -- is recorded too, and is ``opaque``. :meth:`tiers` says
        which lines those are.

        Returns:
            One :class:`~gaspatchio.frame.graph.holes.Hole` per
            unaccounted-for column, in the order the calculation graph holds
            them: the columns seeded from the frame in its schema order,
            then each overwrite where the log met it, and any name the
            records read that no frame ever held where it was first read.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {"sum_assured": [100_000.0], "mortality_rate": [0.01]}
            ... )
            >>> af = ActuarialFrame(model_points)
            >>> af.death_claims = af.sum_assured * af.mortality_rate
            >>> af.graph.holes()
            []

            Write over the claims straight in the query plan and the frame
            says so, naming the line of the write in the hint:

            >>> overwritten = ActuarialFrame(model_points)
            >>> overwritten.death_claims = (
            ...     overwritten.sum_assured * overwritten.mortality_rate
            ... )
            >>> overwritten._df = overwritten._df.with_columns(
            ...     pl.lit(0.0).alias("death_claims")
            ... )
            >>> [(hole.column, hole.reason) for hole in overwritten.graph.holes()]
            [('death_claims', 'overwritten')]

            Discount the claims in Polars' own language and there is still
            nothing unaccounted for, though the new line is not ``core``:

            >>> af = af.with_columns(
            ...     (pl.col("death_claims") * 0.95).alias("discounted_claims")
            ... )
            >>> af.graph.holes()
            []
            >>> af.graph.tiers().engine_native
            ('discounted_claims@1',)

        """
        return holes_in(self._graph)

    def tiers(self) -> TierCensus:
        """Return which of the model's calculations sit at each tier.

        Is every line of this model written in something the format's own
        vocabulary accounts for? :meth:`holes` cannot say. A line written in
        an engine's own expression language -- ``.polars_native()``, or a
        Polars expression handed to ``with_columns`` -- is recorded, so it is
        accounted for and is no hole, and it is still a line only that
        engine can run. This names those lines.

        Every calculation the model recorded is counted at its tier, named
        by its node id: ``core`` where the whole line is in the format's own
        vocabulary, ``engine_native`` where it reaches into one engine's own
        expression language, and ``opaque`` where it reaches an operation
        nothing has classified. A calculation is every node the exported
        document records as computed, and every compiled rollforward: a
        column assigned on the frame, and equally a column a join brought
        in, a renamed column, the columns a projection timeline sets up and
        a date the frame derived. A definition a later line replaced is
        counted too, because it was a line of the model and the lines after
        it were computed from what it produced. A column the data arrived
        with, a column of values handed over, a column nothing accounts for
        and a running rollforward state compute nothing and are not counted.

        Each tier is the one the same node carries in the exported document,
        read off the same operation tree, so the census and the file agree
        node for node. Nothing here runs the model.

        Returns:
            A :class:`~gaspatchio.frame.graph.tiers.TierCensus` holding the
            node ids at each of the three tiers, in the order the model
            defined them, and their ``counts`` -- every tier stated, a zero
            included.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {
            ...         "sum_assured": [100_000.0],
            ...         "mortality_rate": [0.01],
            ...         "discount_factor": [0.95],
            ...     }
            ... )
            >>> af = ActuarialFrame(model_points)
            >>> af.death_claims = af.sum_assured * af.mortality_rate
            >>> af.present_value = af.death_claims * af.discount_factor
            >>> af.graph.tiers().counts
            {'core': 2, 'engine_native': 0, 'opaque': 0}

            Discount the claims with a Polars expression instead, and the
            model still accounts for every column -- but one of its lines
            is now written in Polars' own language:

            >>> af = ActuarialFrame(model_points)
            >>> af.death_claims = af.sum_assured * af.mortality_rate
            >>> af = af.with_columns(
            ...     (pl.col("death_claims") * pl.col("discount_factor")).alias(
            ...         "present_value"
            ...     )
            ... )
            >>> af.graph.holes()
            []
            >>> tiers = af.graph.tiers()
            >>> tiers.counts
            {'core': 1, 'engine_native': 1, 'opaque': 0}
            >>> tiers.engine_native
            ('present_value@1',)

        """
        graph = self._graph
        return _census_of(
            (node.id, tier)
            for node in graph.nodes.values()
            if (tier := _tier_of(graph, node)) is not None
        )

    def fingerprint(self) -> str:
        """Return one content-addressed stamp standing for the whole model.

        The framework's ``"sha256:<hex>"`` shape, over every node's own
        Merkle fingerprint paired with the node it belongs to, the
        assumption tables the model reads, and the columns it cannot
        account for. It moves when any formula moves, when anything
        upstream of one does, and when an assumption base changes
        underneath -- which is what makes it the answer to "can this
        number still be what it was?".

        Stamping is the side effect worth knowing about: every node of the
        cached graph carries ``local_fingerprint`` and ``fingerprint``
        afterwards, and neither before. Folding deliberately does not
        hash, so the callers that only want the structure do not pay for
        it; this is where a caller asks for content-addressed identity and
        gets both the graph-level answer and the per-node ones. One pass
        answers both: the graph-level digest is taken from the very
        fingerprints the stamp wrote rather than from a second hashing of
        every operation tree, and the answer is kept until the frame moves
        under it.

        **It is an identity of the model, not of the policies.** The same
        model run over a new in-force file keeps its fingerprint; what says
        the data moved is the exported document's ``book``, a digest of the
        input columns the model reads.

        Structure only, like everything else here: the model is not run.
        A column of values injected at a line is the one thing hashed by
        what it holds rather than by what derives it. Its record carries a
        content stamp of its own -- the same ``sha256:`` content stamp an
        assumption table and a join's right side carry, taken over the
        values, their type and their count -- so two models handed
        different data under one column name fingerprint differently. That
        covers both containers a whole column arrives in, a ``pl.Series``
        and the NumPy array a simulation hands back, over the same bytes.

        Returns:
            ``"sha256:"`` followed by sixty-four lowercase hex digits.

        Examples:
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> model_points = pl.DataFrame(
            ...     {"sum_assured": [100_000.0], "mortality_rate": [0.01]}
            ... )
            >>> af = ActuarialFrame(model_points)
            >>> af.death_claims = af.sum_assured * af.mortality_rate
            >>> af.graph.fingerprint()  # doctest: +ELLIPSIS
            'sha256:...'

            Two runs of the same model agree; a changed formula does not:

            >>> unchanged = af.graph.fingerprint()
            >>> unchanged == af.graph.fingerprint()
            True

        """
        graph = self._graph
        if self._cached_fingerprint is None:
            prints = stamp_fingerprints(graph)
            self._cached_fingerprint = (
                f"{SHA256_PREFIX}{graph_fingerprint(graph, prints=prints).hex()}"
            )
        return self._cached_fingerprint

    def to_excel(
        self,
        path: Path | str,
        result_df: pl.DataFrame | None = None,
        config: GraphExportConfig | None = None,
    ) -> Path:
        """Write the model's audit record as a workbook a reviewer opens in Excel.

        The record is exported exactly as :meth:`GraphExporter.export` writes
        it, and laid out by :func:`~gaspatchio.frame.graph.render_xlsx`: a
        README naming the record by its digests, the policy's timeline with
        periods as rows and every per-period column in calculation order,
        headed by its formula and tier, then its single values, its nodes,
        its edges and its assumption bases. Every number is the double the
        run produced, written with every digit, and no cell recalculates.

        Nothing here runs the model: the values are the ones in
        ``result_df``, the frame ``collect()`` returned. Without it the
        workbook carries the calculations and no values.

        Args:
            path: Where to write the ``.xlsx`` file.
            result_df: The frame ``collect()`` returned, whose values the
                workbook lays out; None writes the calculations alone.
            config: Which policies to lay out and which model the record is
                an account of, as :meth:`GraphExporter.export` takes it. None
                lays out the first row of the frame.

        Returns:
            The path written.

        Examples:
            >>> import shutil
            >>> import tempfile
            >>> import zipfile
            >>> from pathlib import Path
            >>> import polars as pl
            >>> from gaspatchio import ActuarialFrame
            >>> af = ActuarialFrame(
            ...     pl.DataFrame({"sum_assured": [100_000.0], "q": [0.00123]})
            ... )
            >>> af.death_claims = af.sum_assured * af.q
            >>> folder = Path(tempfile.mkdtemp())
            >>> written = af.graph.to_excel(folder / "policy.xlsx", af.collect())
            >>> zipfile.ZipFile(written).namelist()[0]
            '[Content_Types].xml'
            >>> shutil.rmtree(folder)

        """
        target = Path(path)
        record = GraphExporter(self._frame).export(result_df, config)
        target.write_bytes(render_xlsx(record))
        return target
