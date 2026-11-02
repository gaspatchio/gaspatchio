# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The columns a model cannot account for, on its frame or in its records.

Every column a finished model holds should be one of three things: a
calculation the frame recorded, a field the data arrived with, or a
column of values injected at a known line. A **hole** is the fourth
case, and it is punched at two different places.

The first is a column that is on the frame with no account of itself
anywhere in the log, and a hole says what the frame saw of it:

- ``"overwritten"`` -- a column the frame had accounted for, a
  calculation it logged or a column the data arrived with, that a write
  straight into the query plan then replaced::

      af._df = af._df.with_columns(...)  # behind every door that records

  The frame reads that write as it takes it, and logs each column the
  write defined over its own account. The fold mints the write where it
  falls in the log: a hole that is one of the column's definitions,
  versioned and located at the write, which a later calculation reads and
  which leaves the definition it replaced as history. Reading a write
  costs in proportion to the plan underneath it -- about 12 ms a write on
  the level-4 tutorial model -- so a loop of such writes grows with its
  length. Many columns written in one ``with_columns`` are one write.
- ``"rebuilt"`` -- a column the frame arrived with whose values a
  calculation on another frame produced. ``ActuarialFrame(df)`` over a
  DataFrame that came out of another frame's ``collect()`` starts a new
  log, and every column arrives as if the data had supplied it; the frame
  recognises the ones the other frame calculated by their memory, while
  those values are still held, and does not take them for data.
  ``continue_from=`` is the door that carries their calculations across.
- ``"unrecorded"`` -- anything else nothing accounts for: a column a
  write added under a new name, and a column whose values the frame could
  not place. A write past the doors and a gap in the framework's own
  logging leave the same evidence, and a reason code that guessed would
  be worse than the one it can defend. Told which columns the policy data
  carried, the fold also reports a name the frame arrived holding that the
  data never had -- the template's setup step, collect and rename in
  Polars, makes such names, and from the name alone a column a Polars
  statement made and one an earlier frame calculated look the same.

The second is the mirror of the first: a name a record *reads* that no
frame ever held -- not in the arriving data, not in the schema, defined
by no calculation. There is no column on the frame to explain; what is
wrong is either the record and whatever minted it, or -- where the
record came from a ``with_columns`` call that failed -- the caller's own
expression, transcribed faithfully. The reference still binds to a hole
rather than to an invented input, because an input is a positive claim
about where a number came from, and that claim is exactly what nothing
here supports. It is ``"unrecorded"``.

Who decides differs with the site. The first is the frame's own answer:
it is the one place that holds the log, the arriving columns and the
schema at once. The second is the fold's alone, because no frame was
ever asked -- none ever held the name to be asked about. The graph
already carries the difference, in whether the hole node is what one of
the frame's columns actually holds, and that is what decides which next
move is honest: record the column, or fix the record.

What each reason cannot see is stated on
:data:`~gaspatchio.frame.graph.graph_models.HoleReason`.

**Holes mark, they do not crash.** A composition the framework knows to
be wrong is refused at the line that wrote it; a hole is incomplete
knowledge, and the honest response to incomplete knowledge is to say so
where the model's account of itself is read -- not to refuse a run whose
numbers are fine.

The holes are read back off the calculation graph, which mints a typed
leaf node at either site when it folds the log, and keeps beside each
what it saw of it (``CalcGraph.hole_accounts``). Counting either set a
second time here would mean two places that could disagree about what
this model failed to explain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from gaspatchio._dtypes import UNKNOWN

from .graph_builder import fold
from .graph_models import HoleAccount, HoleReason, NodeType, Provenance

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio.frame.graph.frame_view import GraphSource

    from .graph_builder import CalcGraph
    from .graph_models import GraphNode, NodeId

# A hole the fold has no account of: one it saw nothing of but the name.
_UNRECORDED = HoleAccount("unrecorded")


@dataclass(frozen=True, slots=True)
class Hole:
    """One column a model cannot account for -- on its frame, or in a record.

    ``content`` is the stamp of the column's values as the frame arrived
    holding them, where it did: a ``rebuilt`` column, and an ``unrecorded``
    name the policy data never had. The stamp says what the column held,
    never what made it, and it is what moves the model's identity when a
    file the setup read is edited.
    """

    column: str
    reason: HoleReason = "unrecorded"
    hint: str = ""
    content: str | None = None


def find_holes(af: GraphSource) -> list[Hole]:
    """Return everything ``af`` holds or reads that nothing in its log explains.

    Empty for a model built entirely through the frame's own operations,
    which is the claim worth making: every column is a formula, a named source or
    a located injection, and every name the records read is one of those.

    Args:
        af: The frame to report on. Its whole history is used, so a frame
            that carries a log forward from an earlier step answers for
            the whole model rather than only the part after that step.

    Returns:
        One :class:`Hole` per unaccounted-for column -- the frame's own in
        its schema order, and then any name the records read that no
        frame ever held.

    """
    return holes_in(fold(af, refuse_unnamed=False))


def holes_in(graph: CalcGraph) -> list[Hole]:
    """Return the holes ``graph`` already carries, one per column, in its order.

    Which of a frame's columns are unaccounted for is the frame's own
    decision -- it is the one place that has the log, the arriving columns
    and the schema in front of it at once, and it answers the same
    question for itself when it hands its log to a frame derived from it.
    A name the records read that no frame ever held is the fold's
    decision alone, because there was never a frame holding that name to
    put the question to. The fold records both as nodes, with what it saw
    of each; this reads those back rather than deciding either again.

    One entry per column, however many hole nodes stand for it: a column
    written over outside the frame's own operations, calculated again
    through them and written over again has two. (Written over twice in a
    row, it has one: the frame already said it could not account for the
    column, and the second write changes nothing it was vouching for.) The
    entry is the first of them in the graph's order, which is the order the
    log met them in, so the line it names is the first one to fix.
    """
    # A hole is always an account of a column -- that is what distinguishes
    # it from the nodes a graph holds that are not columns at all, a
    # compiled rollforward and its running states. Reading the name out
    # first is what says so: this section names columns, and a node with
    # no column name to give has nothing to say in it.
    read_by_a_failed_batch = _names_a_failed_batch_read(graph)
    found: dict[str, Hole] = {}
    for node in graph.nodes.values():
        column = node.data.column
        if node.kind is not NodeType.HOLE or column is None or column in found:
            continue
        account = graph.hole_accounts.get(node.id, _UNRECORDED)
        found[column] = Hole(
            column=column,
            reason=account.reason,
            hint=_hint(
                graph,
                node,
                account,
                defined_by=read_by_a_failed_batch.get(node.data.id),
            ),
            content=account.content,
        )
    return list(found.values())


def _names_a_failed_batch_read(graph: CalcGraph) -> Mapping[NodeId, str]:
    """Return each node id a failed ``with_columns`` call read, with the alias.

    The door records the batch its query plan already carries even when
    the call throws, and it takes each alias's dtype from the
    ``self._schema or {}`` read in ``_record_batch_calculations`` -- the
    last schema that *did* resolve. A successful call has just advanced
    that schema past its own aliases, so each of them comes back typed;
    a failed one never got there, so a new alias comes back with no
    dtype at all. That pair, the batch provenance and the missing type, is
    the graph's own evidence that the reference under it was read by a
    statement the user watched fail.

    **Read in one direction only.** A record marked here is always a
    failed batch's record; a failed batch's record is not always marked.
    Each alias records whatever that last resolved schema holds for its
    name, which may be ``None`` for a name the frame itself holds -- what
    resolves that schema is enumerated in ``base.py``'s
    ``_record_batch_calculations`` docstring, and is not restated here.
    So inside a *single* failed batch one alias can come back typed and
    another not, which is why the hint an actuary is handed can turn on
    which alias in their statement carried the typo. A false negative,
    never a false positive: the general wording stands where the marker
    misses.

    Where that costs most is on a real model, and there it is the
    default rather than the edge: a typo riding a reused alias is typed
    off the schema resolved before the failing batch, so the marker
    misses and the actuary is handed the general wording for their own
    spelling. Closing it needs a marker that does not key on the dtype,
    which is a change to the evidence the graph carries rather than to
    this reader of it.

    A calculation whose type the fold let through without a name is
    untyped on the node too, and is not this: its record held a type,
    which is exactly what a failed batch's did not, and
    ``unnamed_types`` is where the fold says so.

    The alias comes back with the id so the hint can name the statement
    instead of gesturing at it -- a batch record always defines a column.
    Where two failed batches read the same name, the first is kept: the
    earlier call is the one to fix first.
    """
    named: dict[NodeId, str] = {}
    for node in graph.nodes.values():
        alias = node.data.column
        came_through_a_batch = node.data.provenance is Provenance.BATCH
        untyped = node.data.dtype == UNKNOWN and node.id not in graph.unnamed_types
        if not came_through_a_batch or not untyped or alias is None:
            continue
        for read in node.data.reads:
            named.setdefault(read, alias)
    return named


def _hint(
    graph: CalcGraph,
    node: GraphNode,
    account: HoleAccount,
    *,
    defined_by: str | None,
) -> str:
    """Return the next move for one hole, in plain English.

    A hole whose reason says what the frame saw gets the move that answers
    it: an overwrite is written through the frame instead, and a rebuild is
    built with ``continue_from=``. Every other hole is unrecorded, and the
    two mint sites need opposite advice there. The node already knows which
    one it came from: a hole punched for a column of the frame is what
    that column holds, so it is in the final schema; a hole punched for a
    reference nothing resolves is in no frame's schema at all. Giving the
    second the first's remedy would tell a reader to assign the column or
    to load it with the model points -- which would resolve the reference
    and leave the bug that wrote the record in place.

    The second site has two readings of its own, and the graph tells
    those apart too: a record that no door of the frame would write is a
    producer's mistake, while a record a failing ``with_columns`` call
    minted is a faithful transcript of the caller's own expression. Only
    the first is a record to fix.
    """
    column = node.data.column or node.id
    if account.reason == "overwritten":
        return _hint_for_an_overwritten_column(graph, node, account)
    if account.reason == "rebuilt":
        return _hint_for_a_rebuilt_column(column, account)
    if node.data.in_final_schema:
        return _hint_for_a_column_on_the_frame(column)
    if defined_by is not None:
        return _hint_for_a_name_a_failed_batch_read(column, defined_by)
    return _hint_for_a_name_no_frame_held(column)


def _hint_for_an_overwritten_column(
    graph: CalcGraph, node: GraphNode, account: HoleAccount
) -> str:
    """Return the next move for a column a write past the frame's doors replaced.

    Names the line of the write and what it replaced, so the reader can see
    both statements at once: the calculation the frame recorded, with its
    formula where it has one, or the column as the data supplied it. Where
    the frame could not read which columns the write defined, it says so,
    because then the column is reported for being held, not for being seen
    written. Where the plan written was values in memory, it names the two
    doors that freeze or bring back values with their account kept.
    """
    column = node.data.column or node.id
    at = _at(node.data.source_location)
    move = (
        f"Write the change through the frame ({_assignment_form(column)}...) "
        "so the calculation is recorded."
    )
    if account.rescanned:
        return (
            f"The query plan was replaced{at} by values in memory -- a collect "
            "handed back as the plan, such as af._df.collect().lazy() -- so the "
            f"frame cannot say what made {column!r}. To freeze the work so far "
            "and keep its account, call af.materialize(); to bring back values "
            "that had to leave the model, build ActuarialFrame(df, "
            "continue_from=af)."
        )
    if not account.readable:
        return (
            f"The write to the query plan{at} changed it in a way the frame "
            "could not read, so the frame cannot say which columns it defined; "
            f"{column!r} is reported because the frame accounted for it and "
            "the plan still holds it. Make the change through the frame's own "
            "operations, so each column it defines is recorded."
        )
    replaced = graph.nodes.get(account.replaced) if account.replaced else None
    if replaced is None or replaced.kind is NodeType.INPUT:
        return (
            f"{column!r} arrived as an input and was then written straight into "
            f"the query plan{at}, outside the frame's own operations, so the "
            f"frame cannot say what it holds. {move}"
        )
    formula = f", {replaced.data.formula}," if replaced.data.formula else ""
    return (
        f"{column!r} was written straight into the query plan{at}, outside the "
        "frame's own operations, so the calculation the frame recorded for it "
        f"-- {replaced.id}{formula}{_at(replaced.data.source_location)} -- is "
        f"not what it holds. {move}"
    )


def _hint_for_a_rebuilt_column(column: str, account: HoleAccount) -> str:
    """Return the next move for a column whose values another frame calculated.

    The calculation is not lost, only left behind on the frame that made
    it, so the move is the door that brings it across rather than a new
    assignment.
    """
    made = account.calculated_by or "a calculation"
    return (
        f"{column!r} arrived holding values that {made} calculated on another "
        f"frame{_at(account.calculated_at)}, and ActuarialFrame(df) starts a "
        "new calculation log, so this frame holds them as data with no "
        "account of how they were made. Build the frame with "
        "ActuarialFrame(df, continue_from=af), where af is the frame that "
        "calculated them, to keep the calculation -- or keep modelling on "
        "that frame and freeze it with af.materialize() rather than "
        "collecting."
    )


def _at(location: str | None) -> str:
    """Return ``" at file:line"``, or nothing where the line was not found."""
    return f" at {location}" if location else ""


def _hint_for_a_column_on_the_frame(column: str) -> str:
    """Return the next move for a column the model holds and cannot explain."""
    return (
        f"{column!r} is on the frame but nothing recorded it: the framework "
        "never saw it assigned, so the calculation graph has no formula and "
        f"no source to show for it. Assign it through the frame "
        f"({_assignment_form(column)}...) so the calculation is recorded, or "
        "load it with the model points so it arrives as an input."
    )


def _hint_for_a_name_no_frame_held(column: str) -> str:
    """Return the next move for a name the records read and no frame held.

    Not a column to record, because there is no column: nothing arrived
    under the name, no calculation defined it, and it is in no schema --
    so what is wrong is the record naming it. Adding a column under that
    name would make the reference resolve and leave whatever minted the
    record still minting it.
    """
    return (
        f"{column!r} is read by a recorded calculation, but no frame in this "
        "model ever held a column by that name: nothing arrived under it, no "
        "calculation defined it, and it is in no schema. If this model never "
        "had a column by that name, the record naming it is wrong -- fix "
        "whatever wrote that record rather than adding a column to make the "
        "reference resolve."
    )


def _hint_for_a_name_a_failed_batch_read(column: str, defined_by: str) -> str:
    """Return the next move for a name a failing ``with_columns`` call read.

    The record is not the thing to fix here: it says exactly what the
    call said, and the framework recorded it because the batch had
    already reached the query plan. What is wrong is in the caller's own
    expression, and a name nothing supplies is the usual reason such a
    call throws -- so the reader is sent to the spelling, not to the
    record and not to the framework that wrote it down.

    ``defined_by`` is the alias that read the name, which the marked
    record carries: it turns "go and find the call" into the line to
    open.
    """
    return (
        f"{column!r} is read by a calculation recorded from a with_columns() "
        f"call that then failed -- the one defining {defined_by!r} -- and no "
        "frame in this model ever held a column by that name: nothing arrived "
        "under it, no calculation defined it, and it is in no schema. A name "
        "nothing supplies is the usual reason such a call fails. Check how "
        f"{column!r} is spelled in the expression for {defined_by!r} against "
        "the columns the frame holds -- fixing the expression clears the "
        "failure and this hole with it."
    )


def _assignment_form(column: str) -> str:
    """Return the assignment a reader can actually type for ``column``.

    Attribute assignment is the taught form, but it cannot spell a column
    whose name has a space in it or starts with an underscore -- and
    vendor extracts are full of both. Pointing an actuary at
    ``af.Policy Number = ...`` would be a next move that does not run.
    """
    if column.isidentifier() and not column.startswith("_"):
        return f"af.{column} = "
    return f"af[{column!r}] = "
