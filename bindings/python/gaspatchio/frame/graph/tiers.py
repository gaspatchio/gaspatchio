# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How much of an operation the artifact format can account for.

An exported graph says how every column was computed. Whether anything
other than this package could *run* that account is a separate question,
and this module answers it one operation at a time.

Three answers. ``core`` is an operation the format names in its own
vocabulary, which any implementation holding that vocabulary can execute.
``engine_native`` is a fragment written in one engine's own expression
language -- declared rather than hidden, so a reader is told what the
portability costs instead of finding out when the port fails.
``opaque`` is an identifier this package carries and nobody has
classified: the artifact still records it, and the tier is what stops the
record from implying more than it knows.

**A node's tier is the weakest tier reached anywhere in its tree.** A
mortality rate multiplied by a raw cumulative sum is a calculation nothing
but that engine can produce, however ordinary the multiplication around it
looks, and reporting the strongest thing found would tell a reader the
node was more portable than it is.

:data:`TIERS` is its own registry, over the identifier space the Polars
lowering registry uses and wider than it in two directions -- the closed
binary-operator vocabulary, which a formula writes rather than calls, and
the two recording doors, whose identifiers name a column's provenance and
lower to nothing at all -- and deliberately not folded into that registry:
one maps an operation to the expression that computes it, the other says
what a second implementation would need to hold, and a dictionary
answering two questions is one nobody can read as a table. The
classification is still a plain literal, reviewable at a glance and in one
place rather than assembled at import out of whatever happened to declare
itself -- and that one place is
:data:`~gaspatchio._semantic.vocabulary.VOCABULARY`, where an
operation's tier stands in the row beside its specification clause and the
sentence a walk-through speaks for it. This table is the column of that
one a tier lookup reads.

An identifier with no entry is ``opaque``. The weaker tiers are reached
through a node's tree and never through this table, which is why every
entry in it is ``core``.

**A whole model is counted as well as each node.** :class:`TierCensus`
says which of a model's calculations sit at each tier, and
``af.graph.tiers()`` takes it for a frame. It exists because a model with
no holes reads as more than it says: a line written in an engine's own
expression language is recorded, so it is accounted for, and it is still a
line only that engine can run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, assert_never

from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    OpNode,
    State,
    WhenThen,
    walk,
)
from gaspatchio._semantic.vocabulary import VOCABULARY, OpTier

from .graph_models import NodeType

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from .graph_models import NodeId

__all__ = ["TIERS", "OpTier", "TierCensus", "tier_of"]

# How much of an operation this format can account for, written from the
# strongest claim to the weakest.

# Every operation identifier this format owns, with the tier it carries,
# read out of the one row per identifier that holds it, and therefore in
# the order the specification tabulates them: the closed binary-operator
# vocabulary -- the operators a formula is written with rather than called
# -- and then every other identifier alphabetically, those that take no
# domain among them. An identifier absent from here is either in an
# extension domain or is not an operation, and either way a node reaching
# it is opaque.
TIERS: Final[dict[str, OpTier]] = {entry.identifier: entry.tier for entry in VOCABULARY}

# How strong a claim each tier is, so that "the weakest reached" is a
# comparison rather than a chain of special cases. The numbers are private
# and mean nothing outside this module: only their order is a fact.
_STRENGTH: Final[dict[OpTier, int]] = {"core": 2, "engine_native": 1, "opaque": 0}

# The order a census states the tiers in, strongest claim first. Read off
# the strengths above rather than written out again, so a census states
# exactly the tiers a node can reach.
_CENSUS_ORDER: Final[tuple[OpTier, ...]] = tuple(
    sorted(_STRENGTH, key=_STRENGTH.__getitem__, reverse=True)
)

# The kinds of node a document writes a tier on, because they are the kinds
# that compute: every kind section 8 does not call a leaf. A calculation the
# frame recorded and a compiled rollforward are the two this package writes.
# A state graph and a nested valuation are the two payload sections section
# 17 reserves, which no producer here writes and a document may still carry,
# each with a tree of its own and a tier stated over it. A leaf -- an
# arriving column, a column nothing accounts for, a running state -- has
# nothing to execute, and the document says so with a null tier.
_KINDS_THAT_COMPUTE: Final[frozenset[str]] = frozenset(
    {
        NodeType.COMPUTED.value,
        NodeType.ROLLFORWARD.value,
        "state_graph",
        "nested_valuation",
    }
)


def tier_of(node: OpNode) -> OpTier:
    """Return the weakest tier reached anywhere in ``node``'s tree.

    Args:
        node: The operation tree to account for. A leaf is a tree of one.

    Returns:
        ``core`` where every operation in the tree is in the format's own
        vocabulary, ``engine_native`` where the tree reaches into an
        engine's own expression language, and ``opaque`` where it reaches
        an identifier nothing has classified. One unclassifiable leaf
        makes the whole node opaque, which is the point: a node is only as
        portable as the least portable thing in it.

    """
    weakest: OpTier = "core"
    for current in walk(node):
        reached = _tier_reached(current)
        if _STRENGTH[reached] < _STRENGTH[weakest]:
            weakest = reached
    return weakest


@dataclass(frozen=True, slots=True, kw_only=True)
class TierCensus:
    """Which of a model's calculations sit at each tier, in the order it wrote them.

    Is every line of this model written in something the format's own
    vocabulary accounts for? An empty list of holes does not say so: a
    line written in an engine's own expression language is recorded, and so
    accounted for, and it is still a line only that engine can run. The
    census answers line by line -- which calculations are ``core``, which
    reach into one engine's own language, and which reach an operation
    nothing has classified.

    Each calculation is named by its node id, ``present_value@1``, which says
    which definition of the column it is. What counts as a calculation is
    every node the exported document records as computed, and every compiled
    rollforward: a column assigned on the frame, and equally a column a join
    brought in, a renamed column, the columns a projection timeline sets up
    and a date the frame derived. A document read from a file counts the two
    payload sections the specification reserves as well, a state graph and a
    nested valuation, which compute and which no frame of this package
    holds. A definition a later line replaced
    is counted like any other: it was a line of the model, and the lines
    after it were computed from what it produced. A column the data arrived
    with, a column of values handed over at a line, a column nothing
    accounts for and a running rollforward state compute nothing, carry no
    tier, and are not counted.

    ``af.graph.tiers()`` takes the census of a frame. The three tuples are
    given by name, since three tuples of node ids in the wrong order would be
    three wrong answers that all look right.

    Attributes:
        core: The calculations written wholly in the format's own vocabulary.
        engine_native: The calculations whose tree reaches a fragment of one
            engine's own expression language.
        opaque: The calculations whose tree reaches an operation nothing has
            classified.

    Examples:
        >>> from gaspatchio.frame.graph import TierCensus
        >>> census = TierCensus(core=("claims@1",), engine_native=("pv@1",), opaque=())
        >>> census.counts
        {'core': 1, 'engine_native': 1, 'opaque': 0}
        >>> census == TierCensus(core=("claims@1",), engine_native=("pv@1",), opaque=())
        True

    """

    core: tuple[NodeId, ...]
    engine_native: tuple[NodeId, ...]
    opaque: tuple[NodeId, ...]

    @property
    def counts(self) -> dict[OpTier, int]:
        """Return how many calculations sit at each tier, a zero included.

        Every tier is always stated, strongest claim first: ``0 opaque`` is
        a claim about the model -- nothing in it reaches an operation the
        format cannot name -- and a count that left it out would leave the
        reader to work that out for themselves.
        """
        return {tier: len(self._at(tier)) for tier in _CENSUS_ORDER}

    def _at(self, tier: OpTier) -> tuple[NodeId, ...]:
        """Return the node ids at ``tier``."""
        match tier:
            case "core":
                return self.core
            case "engine_native":
                return self.engine_native
            case "opaque":
                return self.opaque
            case _ as unreachable:
                assert_never(unreachable)


def _census_of(tiered: Iterable[tuple[NodeId, object]]) -> TierCensus:
    """Return the census of calculations, each paired with the tier it carries.

    Every pair is a calculation -- the caller has already left out what
    computes nothing -- and is counted at its tier, in the order the pairs
    arrive, which for a frame's graph and an exported document alike is the
    order the model defined them.

    Raises:
        ValueError: If a calculation carries no tier, or one the format does
            not define. Counting it nowhere would understate the model -- a
            document whose tiers were all stripped would report the all-zero
            census, a claim about a model that computes -- and counting it
            anywhere would be a guess.

    """
    at: dict[str, list[NodeId]] = {tier: [] for tier in _CENSUS_ORDER}
    for node_id, tier in tiered:
        if not isinstance(tier, str) or tier not in at:
            carried = "no tier" if tier is None else f"the tier {tier!r}"
            msg = (
                f"{node_id!r} is a calculation and carries {carried}, where "
                f"every calculation carries one of {', '.join(_CENSUS_ORDER)}. "
                "Counting it nowhere would understate the model, and counting "
                "it anywhere would be a guess. Check the document with gspio "
                "validate, which names every field that departs from the format."
            )
            raise ValueError(msg)
        at[tier].append(node_id)
    return TierCensus(
        core=tuple(at["core"]),
        engine_native=tuple(at["engine_native"]),
        opaque=tuple(at["opaque"]),
    )


def _census_of_document(nodes: Iterable[Mapping[str, Any]]) -> TierCensus:
    """Return the census of the calculations an exported document's nodes hold.

    Keyed on each node's kind rather than on whether a tier was written. A
    calculation that arrives with no tier is then refused by name instead of
    being counted as nothing, and a node of a kind that computes nothing is
    left out whatever its tier field holds.

    Raises:
        ValueError: If a calculation carries no tier, or one the format does
            not define; see :func:`_census_of`.

    """
    return _census_of(
        (node["id"], node.get("tier"))
        for node in nodes
        if node.get("kind") in _KINDS_THAT_COMPUTE
    )


def _tier_reached(node: OpNode) -> OpTier:
    """Return the tier this one node reaches, its children left to the walk.

    A conditional and the three leaves that name no operation -- a column
    reference, a literal, a running rollforward state -- are ``core``: each
    is a node the byte grammar tags in its own right rather than an
    operation an implementation would have to be told about separately.

    The final case is unreachable for any real node; it exists so that an
    eighth node type added to the union without a decision about what it
    costs to execute fails the type checkers rather than silently
    defaulting to the strongest claim.
    """
    match node:
        case EngineNative():
            return "engine_native"
        case BinOp(op=op):
            return TIERS.get(op, "opaque")
        case Call(name=name):
            return TIERS.get(name, "opaque")
        case Col() | Lit() | State() | WhenThen():
            return "core"
        case _ as unreachable:
            assert_never(unreachable)
