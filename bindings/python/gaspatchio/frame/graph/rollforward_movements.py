# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What a compiled rollforward moved, read back off the run that was performed.

A rollforward's audit artefact is a movement schedule: an opening balance,
each signed movement under the name the step was declared by, and a closing
balance, per period. Every other calculation in the model publishes that much
already -- a column carries its formula and its values, and a reader follows
one to the other. A compiled rollforward published its identity, what it read
and the movements it applies **in the abstract**, and then stopped: the
amounts were inside the kernel and nowhere on the file, which is the one
question a rollforward is audited by.

This module is what reads them back. The kernel has always been able to emit
them -- ``track_increments`` is the flag, section 16.2 the contract -- and
what was missing was a producer willing to ask for them without changing the
model.

**It re-tracks; it does not re-run the model differently.** The compilation
the model registered is reached by its own published fingerprint, its IR is
re-compiled with tracking on, and that expression is evaluated over the frame
the model finished with. Three things follow, and each is the reason this is
the path rather than the obvious one of asking the modeller to switch tracking
on:

- **The model is untouched.** Nobody edits a model to be audited, and a
  document whose values came off a second, differently-configured run would be
  quoting a run nobody performed.
- **No identity moves.** ``track_increments`` is inside a compiled
  rollforward's fingerprint, so the tracked compilation is a *different*
  compilation with a different fingerprint. That identity is never written
  anywhere: the node keeps the fingerprint the model ran under, and the tracked
  compilation exists for the length of one expression. A producer that
  registered it, or stamped it on the node, would publish a document
  identifying a compilation the model never compiled.
- **The answer does not move.** Tracking changes what the kernel *reports*,
  never what it computes. Every closing value of three shipped patterns was
  measured tracked against untracked, as binary64 bit patterns, and 300 of
  300 were identical; that measurement is what licenses quoting a tracked
  run's movements beside an untracked run's balances.

**The readings ride the frame as scratch columns**, on the precedent a
superseded definition's carried output already set (``_carried_definitions``):
they are how this producer reached numbers the finished frame does not hold,
not columns of the model, and nothing downstream may mistake one for the
other. They are added under the reserved prefix below, sampled exactly as
every other per-period column is sampled -- through the export's own filter
and period narrowing, so a movement and the balance beside it are read off one
row under one context -- and never written to the document under these names.

**A movement on the file is a movement of the run the state came from**, and
that is what decides which values the tracked expression is evaluated against.
The kernel call names its operands by column name, and a column name is not a
value: a model that reassigns an input *after* pulling its state back out --
``af.av = compiled.expr_for("av")`` and then ``af.fund_return =
af.fund_return * 2.0`` -- leaves the finished frame holding a ``fund_return``
the compilation never saw. Re-tracking by name there produces a whole
movement schedule, a closing balance and a check line that all agree with each
other and none of which happened; the document validates and states a run
nobody performed, which is the worst failure this format has. So each operand
is rebound to the **version the compilation read**: the graph's own account of
what a compilation binds (``reads``, one node id per column, §16.1's versioned
reads) says which definition of each name the machine was handed, and the
frame holds that definition either under its own name -- where it is still
what the column means at the end -- or under the hidden name the assignment
door carried it aside to when a later line replaced it.

**Where a bound version is not on the frame, the enrichment is declined.**
An arriving column written over by the model's first assignment to that name
is carried nowhere: the retention at the assignment door is for a *definition*
a later definition replaced, and an arrival was never one. There is then no
honest re-track, and the reading stops rather than quoting the replacement --
no ``movements`` on the compilation, and the running state's closing balance
read instead off the column the model materialised it into, which is the run's
own number by construction. The validator says in words why a compilation
that could be reached carries no movements, so the absence is a statement
rather than a gap; and a reader meeting a waterfall may rely on it being this
run's.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from loguru import logger

from gaspatchio._semantic.ir import Call
from gaspatchio.frame.calculation_log import _retained_column_name

from .edges import STATE_EXTRACTION
from .graph_models import STATE_NAMESPACE, NodeId
from .rollforward_ir import compilations_in

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio.rollforward._data import CompiledData

    from .graph_builder import CalcGraph
    from .graph_models import GraphNode

__all__ = ["MOVEMENT_PREFIX", "Readings", "read_the_movements"]

# The prefix every scratch column this module adds is named under. It never
# reaches the document: a reader meeting one would be reading the producer's
# working rather than the model's.
MOVEMENT_PREFIX: Final[str] = "__rf_reading_"

# The point a running state's closing balance is read at. One spelling, here
# and in the extraction a model writes that balance onto the frame with, so
# the two cannot come apart by a character.
_CLOSE: Final[str] = "eop"


@dataclass(frozen=True, slots=True)
class Readings:
    """Where one export's rollforward readings sit on the frame it sampled.

    Attributes:
        columns: Every scratch column added, so the caller can take them off
            again. A frame that kept them would publish the producer's
            working as columns of the model.
        movements: Per compilation node, the scratch column each of its
            movements was read into, keyed by the kernel's own key for that
            step -- a label where the model's author gave one, ``floor@3``
            where the step is structural.
        closing: Per running-state node, the column that state's closing
            balance is read from -- a scratch column of this module's where
            the re-track bound, and the model's own extraction column where
            it declined and the model wrote that balance onto the frame.

    """

    columns: tuple[str, ...]
    movements: dict[NodeId, dict[str, str]]
    closing: dict[NodeId, str]

    def carries_anything(self) -> bool:
        """Return whether any reading was taken at all.

        The closing balances are asked about as well as the scratch columns,
        because a compilation whose re-track was declined still has a balance
        to quote -- off the column the model materialised it into -- and a
        reading that tested only its own working would drop it.
        """
        return bool(self.columns or self.closing)


def read_the_movements(
    graph: CalcGraph, frame: pl.DataFrame
) -> tuple[pl.DataFrame, Readings]:
    """Return ``frame`` with one scratch column per reading, and where they are.

    Args:
        graph: The folded calculation graph, for the compilations it holds
            and the running-state nodes those compilations declare.
        frame: The frame the model finished with. Every input the kernel
            reads is on it, which is what lets the tracked expression run
            over it without re-running the model.

    Returns:
        The frame with the readings added, and the map from node to column.
        The frame unchanged and an empty map where the model compiled no
        rollforward, which is every model that never escalated to a state
        machine -- and the frame unchanged with a closing balance or two
        where every compilation's re-track was declined and the balances
        came off the model's own columns.

    """
    held = frozenset(frame.columns)
    movements: dict[NodeId, dict[str, str]] = {}
    closing: dict[NodeId, str] = {}
    # One group per rebinding, because a rebinding is a substitution over the
    # frame rather than a rewrite of the expression: the engine has no door
    # for renaming the columns a plugin call reads, so the columns are put
    # under the names the call asks for and the call is evaluated there. Every
    # compilation that needs no substitution shares the empty group, which is
    # every compilation of every model that does not write over what a state
    # machine read -- one pass, as before this reading learned to rebind.
    groups: dict[tuple[tuple[str, str], ...], list[pl.Expr]] = {}
    for node_id, fingerprint, compiled in compilations_in(graph):
        reading = _one_compilation(graph, node_id, fingerprint, compiled, held)
        if reading is None:
            closing.update(_balances_the_model_wrote(graph, node_id, compiled, held))
            continue
        groups.setdefault(reading.bound, []).extend(reading.exprs)
        movements[node_id] = reading.keys
        closing.update(reading.states)
    if not groups:
        return frame, Readings((), movements, closing)
    read, columns = _taken_off_the_frame(frame, groups)
    logger.debug(
        f"Read {len(columns)} rollforward reading(s) off "
        f"{len(movements)} compilation(s): the movements each step applied "
        "and each state's closing balance, re-tracked over the finished frame "
        "against the versions each compilation bound."
    )
    return read, Readings(columns, movements, closing)


def _taken_off_the_frame(
    frame: pl.DataFrame,
    groups: dict[tuple[tuple[str, str], ...], list[pl.Expr]],
) -> tuple[pl.DataFrame, tuple[str, ...]]:
    """Return ``frame`` with every group's readings beside it, and their names.

    Each group is evaluated on its own substitution of the frame and the
    readings are stacked back on, rather than the substitution being written
    into the frame the export goes on to sample: putting one version of a
    column under another version's name is how the readings are reached, and
    it must not be how any other value in the document is.

    The substitution is built through the lowering's own column door rather
    than out of raw engine vocabulary, which is where every other column
    reference in this package comes from.
    """
    # The lowering package imports the op-tree; see ``_one_compilation``.
    from gaspatchio.frame.lowering.columns import (  # noqa: PLC0415 — import cycle
        column_reference,
    )

    read = frame
    columns: list[str] = []
    for bound, exprs in groups.items():
        lazy = frame.lazy()
        if bound:
            lazy = lazy.with_columns(
                [column_reference(version).alias(name) for name, version in bound]
            )
        taken = lazy.select(exprs).collect()
        columns.extend(taken.columns)
        read = read.hstack(taken.get_columns())
    return read, tuple(columns)


@dataclass(frozen=True, slots=True)
class _OneCompilation:
    """What one compilation contributes to an export's readings.

    Attributes:
        exprs: The expressions reading it, to be evaluated under ``bound``.
        keys: The scratch column each of its movements is read into.
        states: The scratch column each of its running states is read into.
        bound: The substitution the expressions are evaluated under --
            each operand name against the frame column holding the version
            the compilation read. Empty where every operand still means at
            the end of the run what it meant when the machine was compiled,
            which is every model that does not write over a machine's input.

    """

    exprs: list[pl.Expr]
    keys: dict[str, str]
    states: dict[NodeId, str]
    bound: tuple[tuple[str, str], ...]


def _one_compilation(
    graph: CalcGraph,
    node_id: NodeId,
    fingerprint: str,
    compiled: CompiledData,
    held: frozenset[str],
) -> _OneCompilation | None:
    """Return the reading of one compilation, or None where it cannot be taken.

    None in two cases, and they are the same answer for two reasons. The
    tracked compilation cannot be built at all; or one of the versions the
    compilation bound is not on the finished frame, so the expression could
    only be evaluated against values the machine never saw. Either is a
    producer that has less to say rather than an export that fails: the node,
    its identity, what it reads and the movements it declares are all still
    written, and what is missing is their amounts -- the same absence a
    compilation out of this process's reach already carries, taken for the
    same reason.
    """
    # The compiler reaches the op-tree through the lowering package, and this
    # module is inside it; a module-scope import here would close the cycle.
    from gaspatchio.rollforward._data import CompiledData  # noqa: PLC0415
    from gaspatchio.rollforward._ops import (  # noqa: PLC0415 — import cycle
        increment_keys,
    )
    from gaspatchio.rollforward._passes import (  # noqa: PLC0415 — compiler is used on demand
        _compile_ir,
    )

    ir = compiled.ir
    try:
        tracked = _compile_ir(
            dataclasses.replace(ir, track_increments=True), CompiledData
        )
    except (ValueError, KeyError, TypeError) as error:
        logger.debug(
            f"No movements for {node_id!r}: re-compiling its own IR with "
            f"tracking on was refused ({error}), so the artifact carries "
            "what the compilation declares and not what it moved."
        )
        return None

    # Built here rather than through ``CompiledRollforward.expr_for`` and
    # ``increment_for``: those two emit an op-node and register the tracked
    # compilation's identity against it, and the tracked compilation is not
    # the one the model ran. Nothing this reading touches may reach the
    # graph the document is written from.
    from gaspatchio.rollforward._data import (  # noqa: PLC0415 — import cycle
        _raw_plugin_expr,
    )

    struct = _raw_plugin_expr(tracked)
    bound = _the_versions_it_bound(graph, node_id, struct, held)
    if bound is None:
        return None
    short = fingerprint.split(":", 1)[-1][:16]
    exprs: list[pl.Expr] = []

    keys: dict[str, str] = {}
    for key in increment_keys(ir.transitions):
        column = f"{MOVEMENT_PREFIX}{short}__m__{key}"
        exprs.append(struct.struct.field(f"increment_{key}").alias(column))
        keys[key] = column

    states: dict[NodeId, str] = {}
    for state in ir.states:
        reference = f"{state.name}@{_CLOSE}"
        state_id = f"{STATE_NAMESPACE}{reference}"
        # Only a state the graph holds a node for. A state no operation
        # consults has no node to carry a balance, and minting one here
        # would put a node in the graph after it was fingerprinted.
        if state_id not in graph.nodes:
            continue
        column = f"{MOVEMENT_PREFIX}{short}__s__{state.name}"
        exprs.append(struct.struct.field(reference).alias(column))
        states[state_id] = column

    return _OneCompilation(exprs=exprs, keys=keys, states=states, bound=bound)


def _the_versions_it_bound(
    graph: CalcGraph, node_id: NodeId, struct: pl.Expr, held: frozenset[str]
) -> tuple[tuple[str, str], ...] | None:
    """Return where each operand's bound version is, or None where one is gone.

    The compilation's node states what it read, one node id per column, and a
    node id carries the version: ``fund_return`` is the column as it arrived,
    ``fund_return@1`` the first definition the model wrote of that name. That
    is the record §16.1 means by a versioned read, and it is the only account
    of which values the machine was handed -- the kernel call itself carries
    names, and a name at the end of a run is whatever the last line to write
    it meant by it.

    Three answers per read, and they are the same three the export's own
    ``_values_by_node`` takes for a node's values:

    - the version is what the column holds at the end, and the operand needs
      no substitution;
    - it was replaced by a later definition and the assignment door carried
      it aside, so the substitution names the hidden column holding it;
    - it was replaced and nothing carried it -- an arriving column written
      over by the model's first assignment to that name, which the door does
      not retain because retention is for a definition and an arrival is not
      one -- and there is nothing honest to evaluate against.

    **The expression's own roots are read back and checked against this**,
    because the compilation's ``reads`` is built from the operations and the
    state initialisers, and the kernel binds two things that are neither: a
    contract-boundary mask, and a per-policy period count on a jagged
    schedule. A root the graph gives this compilation no account of is
    accepted only where nothing on the model ever wrote that name, so the
    frame's column is what the data arrived with and the binding by name is
    the binding that happened. Where the model did write it, this reading
    cannot say which definition the machine got, and it says so by declining.
    """
    bound: dict[str, str] = {}
    accounted: set[str] = set()
    for read in graph.nodes[node_id].data.reads:
        node = graph.nodes.get(read)
        if node is None or node.data.column is None:
            # A running state: the kernel carries it, and nothing on the
            # frame ever held it for a substitution to reach.
            continue
        accounted.add(node.data.column)
        version = _where_that_version_is(node, held)
        if version is None:
            logger.info(
                f"No movements for {node_id!r}: it read "
                f"{node.data.column!r} as {read!r}, and the finished frame "
                "no longer holds that version -- a later line wrote over the "
                "column and nothing carried the values the machine was "
                "handed. The artifact carries what this compilation declares "
                "and what its balance came to, and not a movement schedule "
                "re-tracked against values it never saw."
            )
            return None
        if version != node.data.column:
            bound[node.data.column] = version
    written = {
        node.data.column
        for node in graph.nodes.values()
        if node.data.version is not None and node.data.column is not None
    }
    try:
        roots = set(struct.meta.root_names())
    except Exception:  # noqa: BLE001 - meta inspection is best-effort
        logger.info(
            f"No movements for {node_id!r}: the engine would not say which "
            "columns its kernel call reads, so this reading cannot certify "
            "that each of them is the version the compilation bound."
        )
        return None
    for root in sorted(roots - accounted):
        if root in written:
            logger.info(
                f"No movements for {node_id!r}: its kernel call reads the "
                f"column {root!r}, which this model writes and which the "
                "compilation's own reads do not account for, so which "
                "definition of it the machine was handed cannot be read off "
                "the graph. The artifact carries what this compilation "
                "declares and not what it moved."
            )
            return None
    return tuple(sorted(bound.items()))


def _where_that_version_is(node: GraphNode, held: frozenset[str]) -> str | None:
    """Return the frame column holding one node's own values, or None."""
    column = node.data.column
    if column is None:  # pragma: no cover - callers filter these out
        return None
    if node.data.in_final_schema:
        return column if column in held else None
    if node.data.version is None:
        # An arriving column a later line wrote over. Nothing carried it:
        # the assignment door retains a definition being replaced, and the
        # values a column arrived with were never one.
        return None
    carried = _retained_column_name(column, node.data.version)
    return carried if carried in held else None


def _balances_the_model_wrote(
    graph: CalcGraph,
    node_id: NodeId,
    compiled: CompiledData,
    held: frozenset[str],
) -> dict[NodeId, str]:
    """Return where the model itself put each of one compilation's balances.

    The fallback for a compilation this reading declined: its movements are
    off the file, and its closing balances need not be. A line reading
    ``compiled.expr_for("av")`` **is** that balance written onto the frame,
    so the column holds the run's own closing values whatever happened to the
    machine's inputs afterwards, and the state node quotes it rather than
    carrying nothing.

    **Only a line that is the extraction and nothing else.** A column stating
    that it extracts a balance may have wrapped it -- ``expr_for("av") + 1``,
    or two balances added together -- and those state the extraction as
    honestly as a bare one does, because what the record says is which
    compilation the formula reached. So the operation tree is the test: the
    whole of it is the state call, or this is not the balance and is not read
    as one.
    """
    found: dict[NodeId, str] = {}
    for state in compiled.ir.states:
        reference = f"{state.name}@{_CLOSE}"
        state_id = f"{STATE_NAMESPACE}{reference}"
        if state_id not in graph.nodes:
            continue
        column = _the_column_that_is_this_balance(graph, node_id, reference, held)
        if column is None:
            continue
        found[state_id] = column
        logger.debug(
            f"The closing balance of {state_id!r} is read off {column!r}, the "
            "column the model materialised it into: this compilation's "
            "movements could not be re-tracked against the versions it bound."
        )
    return found


def _the_column_that_is_this_balance(
    graph: CalcGraph, node_id: NodeId, reference: str, held: frozenset[str]
) -> str | None:
    """Return the frame column one bare extraction of ``reference`` holds."""
    for other in graph.nodes.values():
        extracts = other.data.extracts or ()
        if not any(
            one.compilation == node_id and one.state == reference for one in extracts
        ):
            continue
        tree = graph.op_trees.get(other.data.id)
        if not isinstance(tree, Call) or tree.name != STATE_EXTRACTION:
            continue
        column = _where_that_version_is(other, held)
        if column is not None:
            return column
    return None
