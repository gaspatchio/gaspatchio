# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The walks every lineage question is answered by, on a frame or on a file.

``af.graph`` asks what a column read, what read it, everything behind it,
everything ahead of it and what nothing reads. An audit file holds the same
account of the same model: one node per definition, what each read, and which
running balance a column materialises. A reviewer holding only the file asks
the same questions of it, and a second implementation of the answers is a
second thing that can be wrong in its own way -- a version bound one way here
and another way there, a balance's readers found on the frame and missed in
the file.

So both are answered here, once, over one structure: :class:`Lineage`, built
either from a folded graph (:meth:`Lineage.of_graph`) or from a document's
``nodes`` (:meth:`Lineage.of_document`). Each node carries exactly what the
walks read -- its id, its column and ordinal, its kind and provenance, what it
read, the balances it materialises (section 16), the assumption entries its
formula read, and which of its reads only took a length. The two builders sit
side by side so a field one of them reads and the other does not is visible
in one place, and the parity tests hold every answer on every shipped model to
equality.

Nothing here runs a model. Every answer is node ids in the order the model
defined them, which is a topological order: a node is defined only after
everything it reads.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any, Final

from .assumptions import assumptions_read_by_node
from .graph_models import STATE_NAMESPACE

if TYPE_CHECKING:
    from .graph_builder import CalcGraph
    from .graph_models import NodeId

# How many column names a refusal lists before it stops naming them and
# says how many more there are. Long enough to be a menu on a small model,
# short enough not to bury the message on a production one.
_NAMES_IN_REFUSAL: Final = 10

# The narrowing that says a read took only the other column's length: a
# per-period timeline laid out to match it, its values never read.
_LENGTH_ONLY: Final = "WINDOW"

# The kinds and the provenance the classes of an unread node are read from.
_ARRIVED: Final = "input"
_HOLE: Final = "hole"
_JOINED: Final = "join"
_STAMPED: Final = "projection"
_TRANSFORMATION_FACET: Final = "gaspatchio_column_transformation"

# The classes of a node nothing reads, in the order a report states them.
UNUSED_CLASSES: Final[tuple[str, ...]] = (
    "superseded",
    "data",
    "stamp",
    "length_only",
    "terminal",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class LineageNode:
    """One node, as much of it as a lineage question reads.

    Attributes:
        id: The node id.
        column: The column it is an account of, or ``None`` in a reserved
            namespace (a compiled rollforward, a running state).
        version: Which definition of ``column`` it is, or ``None`` for a node
            nothing defined.
        kind: The node's kind, in the words the document writes it in.
        provenance: Where its values came from, or ``None``.
        reads: What its formula read, first mention first.
        extracts: The running balances it materialises, as state references
            (``"fund@eop"``) -- empty for nearly every node.
        assumptions: The assumption entries its own formula read.
        length_reads: The reads that took only a length, never a value.

    """

    id: NodeId
    column: str | None
    version: int | None
    kind: str
    provenance: str | None
    reads: tuple[NodeId, ...]
    extracts: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    length_reads: frozenset[NodeId] = frozenset()


@dataclass(frozen=True, slots=True, kw_only=True)
class Unused:
    """The calculations nothing reads, each under the one class the record supports.

    "Which of these does nothing use?" is the question a reviewer asks of a
    model before trusting it, and the honest answer is not one list. A
    definition a later line replaced and nobody read is dead code; a column
    the data arrived with that nothing reads is unused data; a live
    calculation nothing reads is either a result or dead code, and the model
    does not say which. Each node nothing reads is put under exactly one
    class, read off what the record states and never guessed:

    - ``superseded``: a definition a later one of the same column replaced,
      and that nothing read before it was replaced. Dead code.
    - ``data``: a column that arrived -- with the model points, from a table,
      handed over at a line, or brought in by a join -- that nothing reads.
    - ``stamp``: a column the projection timeline set up that nothing reads.
    - ``length_only``: a column read, but only for its length -- a timeline
      laid out to match it. The model uses how long it is, not its values.
    - ``terminal``: a live calculation nothing reads. A result, or dead code;
      only the person who wrote the model can say which.
    - ``kept``: any of the above the caller named as kept -- the results it
      knows about -- so what remains under ``terminal`` is what nobody has
      vouched for yet.

    A column nothing accounts for is not listed here: it has no account to
    classify, and :meth:`~GraphFrameAccessor.holes` names it.

    Every tuple holds node ids in the order the model defined them.
    """

    superseded: tuple[NodeId, ...]
    data: tuple[NodeId, ...]
    stamp: tuple[NodeId, ...]
    length_only: tuple[NodeId, ...]
    terminal: tuple[NodeId, ...]
    kept: tuple[NodeId, ...]

    @property
    def counts(self) -> dict[str, int]:
        """Return how many nodes each class holds, a zero included."""
        return {name: len(self.of(name)) for name in (*UNUSED_CLASSES, "kept")}

    def of(self, name: str) -> tuple[NodeId, ...]:
        """Return the node ids under one class, named as :attr:`counts` names it.

        Raises:
            ValueError: If ``name`` is not one of the classes.

        """
        found: dict[str, tuple[NodeId, ...]] = {
            "superseded": self.superseded,
            "data": self.data,
            "stamp": self.stamp,
            "length_only": self.length_only,
            "terminal": self.terminal,
            "kept": self.kept,
        }
        if name not in found:
            msg = (
                f"{name!r} is not a class of unused node. The classes are "
                f"{', '.join(found)}."
            )
            raise ValueError(msg)
        return found[name]


class Lineage:
    """One model's nodes and reads, and every lineage question asked of them."""

    __slots__ = ("_definitions", "_nodes", "_readers")

    def __init__(self, nodes: Iterable[LineageNode]) -> None:
        """Hold ``nodes`` in the order given: the order the model defined them."""
        self._nodes: dict[NodeId, LineageNode] = {node.id: node for node in nodes}
        self._definitions: dict[str, list[NodeId]] = {}
        self._readers: dict[NodeId, list[NodeId]] = {}
        for node in self._nodes.values():
            if node.column is not None and node.version is not None:
                self._definitions.setdefault(node.column, []).append(node.id)
            for read in node.reads:
                self._readers.setdefault(read, []).append(node.id)

    # --- building one -------------------------------------------------------

    @classmethod
    def of_graph(cls, graph: CalcGraph) -> Lineage:
        """Return the lineage of a folded graph, read off its nodes and edges."""
        assumptions = assumptions_read_by_node(graph)
        length_reads: dict[NodeId, set[NodeId]] = {}
        for edge in graph.edges:
            if edge.subtype == _LENGTH_ONLY and all(
                way.subtype == _LENGTH_ONLY for way in edge.ways
            ):
                length_reads.setdefault(edge.target, set()).add(edge.source)
        return cls(
            LineageNode(
                id=node.id,
                column=node.data.column,
                version=node.data.version,
                kind=node.kind.value,
                provenance=(
                    None if node.data.provenance is None else node.data.provenance.value
                ),
                reads=node.data.reads,
                extracts=tuple(one.state for one in node.data.extracts or ()),
                assumptions=assumptions.get(node.id, ()),
                length_reads=frozenset(length_reads.get(node.id, ())),
            )
            for node in graph.nodes.values()
        )

    @classmethod
    def of_document(cls, nodes: Sequence[Mapping[str, Any]]) -> Lineage:
        """Return the lineage of an exported document's ``nodes``, in its order.

        ``extracts`` is an object or an array of them (section 8); a read
        takes only a length where every narrowing the reading node's facet
        states for it is ``WINDOW``. A node whose facet is absent states no
        narrowing, and none of its reads is taken for a length.
        """
        return cls(
            LineageNode(
                id=node["id"],
                column=node.get("column"),
                version=node.get("version"),
                kind=node.get("kind", ""),
                provenance=node.get("provenance"),
                reads=tuple(node.get("reads") or ()),
                extracts=_extracted_states(node.get("extracts")),
                assumptions=tuple(node.get("reads_assumptions") or ()),
                length_reads=_length_reads(node),
            )
            for node in nodes
        )

    # --- resolving a name ---------------------------------------------------

    @property
    def order(self) -> tuple[NodeId, ...]:
        """Return every node id, in the order the model defined them."""
        return tuple(self._nodes)

    def node(self, node_id: NodeId) -> LineageNode:
        """Return one node by its id."""
        return self._nodes[node_id]

    def versions_of(self, column: str) -> tuple[NodeId, ...]:
        """Return every definition of ``column``, oldest first; empty for none."""
        return tuple(self._definitions.get(column, ()))

    def resolve(self, column: str) -> NodeId:
        """Return the node ``column`` names: its live definition, or an exact id.

        A column name resolves to its last definition, or to the arriving node
        where nothing defined it. An explicit ``"column@ordinal"`` resolves to
        that definition. The column name is tried first, so a column whose own
        name contains an ``@`` still answers for itself.

        Raises:
            ValueError: If no such column and no such node is here.

        """
        defined = self._definitions.get(column)
        if defined:
            return defined[-1]
        if column in self._nodes:
            return column
        raise ValueError(self.refusal(column))

    def column_of(self, column: str) -> str:
        """Return the column a name or a node id is an account of.

        Raises:
            ValueError: If the name resolves to a node that is no column's
                account -- a compiled rollforward or one of its states.

        """
        found = self._nodes[self.resolve(column)].column
        if found is None:
            raise ValueError(self.refusal(column))
        return found

    def refusal(self, column: str) -> str:
        """Return the message for a name this model's graph does not hold.

        A version that does not exist is answered with the versions that do;
        anything else with the nearest columns the graph does hold.
        """
        base = column.rsplit("@", 1)[0]
        defined = self._definitions.get(base)
        if defined:
            times = "once" if len(defined) == 1 else f"{len(defined)} times"
            return (
                f"{column!r} is not one of this model's calculations. "
                f"{base!r} is defined {times}: {', '.join(defined)}. "
                f"Ask for {base!r} itself for whichever definition the "
                "frame holds now."
            )
        # The columns and only the columns: a reserved id names something
        # that is not one, and offering it as a near miss for a column name
        # would answer the question with a different kind of thing.
        known = sorted(
            {node.column for node in self._nodes.values() if node.column is not None}
        )
        return (
            f"No column named {column!r} is in this model's calculation "
            f"graph. {_suggestion(column, known, noun='columns')}"
        )

    # --- the questions ------------------------------------------------------

    def precedents(self, column: str) -> tuple[NodeId, ...]:
        """Return what ``column``'s own formula read, first mention first."""
        return self._nodes[self.resolve(column)].reads

    def dependents(self, column: str) -> tuple[NodeId, ...]:
        """Return the nodes that read ``column``, or a balance it materialises."""
        seeds = set(self._forward_seeds((self.resolve(column),)))
        return tuple(
            node.id for node in self._nodes.values() if not seeds.isdisjoint(node.reads)
        )

    def trace(self, column: str, *, depth: int | None = None) -> tuple[NodeId, ...]:
        """Return everything behind ``column`` within ``depth`` reads, itself last."""
        return self._cone(
            (self.resolve(column),),
            lambda node_id: self._nodes[node_id].reads,
            depth=depth,
        )

    def affected(
        self,
        column: str | None = None,
        *,
        assumption: str | None = None,
        depth: int | None = None,
    ) -> tuple[NodeId, ...]:
        """Return everything ahead of ``column``, or of every reader of ``assumption``.

        Raises:
            ValueError: If both or neither of ``column`` and ``assumption`` are
                named, or if the one named is not in this graph.

        """
        if (column is None) == (assumption is None):
            msg = (
                "Name a column, or an assumption with assumption=, to ask what "
                "it reaches -- one of the two, not both."
            )
            raise ValueError(msg)
        if assumption is not None:
            starts = self._readers_of_assumption(assumption)
        else:
            starts = (self.resolve(str(column)),)
        return self._cone(
            self._forward_seeds(starts),
            lambda node_id: self._readers.get(node_id, ()),
            depth=depth,
        )

    def unused(self, keep: Iterable[str] = ()) -> Unused:
        """Return every node nothing reads, each under its class.

        Raises:
            ValueError: If a name in ``keep`` is not in this graph.

        """
        kept_ids = {self.resolve(name) for name in keep}
        classes: dict[str, list[NodeId]] = {
            name: [] for name in (*UNUSED_CLASSES, "kept")
        }
        for node in self._nodes.values():
            found = self._unused_class(node)
            if found is None:
                continue
            classes["kept" if node.id in kept_ids else found].append(node.id)
        return Unused(**{name: tuple(ids) for name, ids in classes.items()})

    # --- the walks ------------------------------------------------------------

    def _forward_seeds(self, starts: Iterable[NodeId]) -> tuple[NodeId, ...]:
        """Return ``starts`` and the running state of each balance one materialises.

        A column assigned an extraction is that running balance written onto
        the frame. What reads the balance is the state machine, through the
        state, and never the column -- so a forward question asked of the
        column is asked of the state as well (section 16). A state that has
        no node is a balance nothing consulted, and is dropped.
        """
        seeds: list[NodeId] = []
        for start in starts:
            seeds.append(start)
            seeds.extend(
                state_id
                for state_id in (
                    f"{STATE_NAMESPACE}{state}" for state in self._nodes[start].extracts
                )
                if state_id in self._nodes
            )
        return tuple(seeds)

    def _cone(
        self,
        starts: Iterable[NodeId],
        step: Callable[[NodeId], Iterable[NodeId]],
        *,
        depth: int | None,
    ) -> tuple[NodeId, ...]:
        """Return every node ``step`` reaches from ``starts``, in model order.

        Breadth first, so ``depth`` counts reads from the nearest start: zero
        is the starts alone, and ``None`` runs until nothing new is reached.
        """
        limit = _checked_depth(depth)
        cone: set[NodeId] = set()
        frontier = list(dict.fromkeys(starts))
        hops = 0
        while frontier:
            cone.update(frontier)
            if limit is not None and hops >= limit:
                break
            frontier = list(
                dict.fromkeys(
                    nxt
                    for node_id in frontier
                    for nxt in step(node_id)
                    if nxt not in cone
                )
            )
            hops += 1
        return tuple(node_id for node_id in self._nodes if node_id in cone)

    def _readers_of_assumption(self, name: str) -> tuple[NodeId, ...]:
        """Return every node whose own formula read the assumption entry ``name``.

        Raises:
            ValueError: If no node reads an entry of that name.

        """
        starts = tuple(
            node.id for node in self._nodes.values() if name in node.assumptions
        )
        if starts:
            return starts
        known = sorted(
            {one for node in self._nodes.values() for one in node.assumptions}
        )
        msg = (
            f"No calculation in this model's graph reads an assumption named "
            f"{name!r}. {_suggestion(name, known, noun='assumptions')}"
        )
        if not get_close_matches(name, known, n=1, cutoff=0.6):
            msg += (
                " A table a join brought in is reached through the key it was "
                "matched on: ask what that column affects."
            )
        raise ValueError(msg)

    def _unused_class(self, node: LineageNode) -> str | None:
        """Return the class of a node nothing reads, or ``None`` for one read.

        Read off the record and never guessed. A node read only for its length
        is ``length_only``; a node read for a value is not unused at all, and
        a column nothing accounts for has no account to classify.
        """
        if node.kind == _HOLE:
            return None
        readers = self._readers.get(node.id, ())
        if not readers:
            return self._unread_class(node)
        if all(node.id in self._nodes[one].length_reads for one in readers):
            return "length_only"
        return None

    def _unread_class(self, node: LineageNode) -> str:
        """Return the class of a node no other node reads.

        In this order: a definition a later one of its column replaced is
        ``superseded``, an arriving or joined column is ``data``, a column the
        projection set up is a ``stamp``, and anything else is ``terminal``.
        """
        if (
            node.column is not None
            and node.version is not None
            and self._definitions[node.column][-1] != node.id
        ):
            return "superseded"
        if node.kind == _ARRIVED or node.provenance == _JOINED:
            return "data"
        if node.provenance == _STAMPED:
            return "stamp"
        return "terminal"


def _checked_depth(depth: int | None) -> int | None:
    """Return ``depth`` when it is a whole number of reads, or refuse it.

    Raises:
        ValueError: If ``depth`` is negative, or not a whole number.

    """
    if depth is None:
        return None
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
        msg = (
            f"depth={depth!r} is not a number of reads. Pass a whole number, 0 "
            "for the column alone, or None to follow every read."
        )
        raise ValueError(msg)
    return depth


def _suggestion(name: str, known: Sequence[str], *, noun: str) -> str:
    """Return the sentence naming what the reader may have meant instead."""
    near = get_close_matches(name, known, n=3, cutoff=0.6)
    if near:
        return f"Did you mean {', '.join(repr(one) for one in near)}?"
    if not known:
        return f"It holds no {noun}."
    if len(known) <= _NAMES_IN_REFUSAL:
        return f"It holds: {', '.join(known)}."
    listed = ", ".join(known[:_NAMES_IN_REFUSAL])
    return (
        f"It holds {len(known)} {noun}, among them: {listed}, "
        f"and {len(known) - _NAMES_IN_REFUSAL} more."
    )


def _extracted_states(extracts: object) -> tuple[str, ...]:
    """Return the state references a document node's ``extracts`` names."""
    if isinstance(extracts, Mapping):
        extracts = [extracts]
    if not isinstance(extracts, list):
        return ()
    return tuple(
        one["state"]
        for one in extracts
        if isinstance(one, Mapping) and isinstance(one.get("state"), str)
    )


def _length_reads(node: Mapping[str, Any]) -> frozenset[NodeId]:
    """Return the reads a document node's facet narrows to a length alone."""
    facet = (node.get("facets") or {}).get(_TRANSFORMATION_FACET) or {}
    found: set[NodeId] = set()
    for read in facet.get("reads") or ():
        ways = read.get("transformations") or ()
        if ways and all(way.get("subtype") == _LENGTH_ONLY for way in ways):
            found.add(read["source"])
    return frozenset(found)
