# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Content-addressed identity for every calculation in a model.

Run a model this quarter, run it again next quarter with one mortality
basis replaced, and the question a reviewer has to answer is not "did
anything change?" but "which numbers can no longer be the same, and which
ones had no business moving at all?" Two hashes per node answer it:

- a **local fingerprint** over the node's own formula -- what it computes,
  and nothing else;
- a **Merkle fingerprint** over that local fingerprint followed by the
  fingerprints of everything the node reads, in bind order.

A node whose local fingerprint moved was edited. A node whose local
fingerprint held but whose Merkle fingerprint moved was not edited -- its
answer simply cannot be what it was, because something upstream changed.
That distinction is the whole point, and it is why a horizon extended from
99 to 100 shows up as one changed timeline and a tail of inherited
movement rather than as a model rewritten end to end.

## What the bytes cover, and what they deliberately do not

The bytes hashed for a node are the op-tree: node type, fields in
declaration order, child nodes recursively, typed attribute values sorted
by key. They carry **no source span, no rendered formula text, and not the
name of the column being defined**. Reformatting a model, moving a
function, or renaming a column is therefore not a model change -- which is
what lets a rename be reported as a rename instead of one calculation
deleted and an identical one invented.

Encoding rules, so that a fingerprint taken on one machine means the same
thing as one taken on another:

- one tag byte per node type, and a separate tag per scalar type, so a
  whole number, its own text, and a true/false flag are three things;
- text as UTF-8 behind its byte length;
- decimals as their eight IEEE-754 bytes, most significant first, a
  negative zero's sign bit included: the two zeros are one number in the
  arithmetic, and ``to_text`` and every sign-reading operation tell them
  apart, so an identity that equated them would report no drift on a model
  that changed;
- whole numbers zigzag-encoded, so a period offset of -1 costs one byte
  rather than eight;
- every variable-length run (arguments, attributes, declared reads, the
  members of a sequence literal) behind its own count, so one argument
  called ``ab`` can never flatten to the same bytes as two called ``a``
  and ``b``;
- a literal holding a sequence -- the age boundaries of a banded lookup,
  a schedule of loadings -- behind a tag of its own, so a band of one
  boundary is never the boundary on its own. It is the values that are
  hashed, member by member: an engine's own display of a long sequence
  abbreviates the middle away, and two bands differing only there would
  otherwise be one calculation.

Three kinds of node have no formula to hash: columns the data arrived
with, columns nothing accounts for, and the running states of a compiled
rollforward. They hash their name and their neutral type instead, under
three different tags -- "the data supplied this", "nothing here can
explain this" and "this is not a column at all" are different claims
about a model and must not collide.

A compiled rollforward itself does have something to hash, and it is one
call carrying the compilation's own published fingerprint and the schedule
it runs on. That fingerprint is already an identity over the whole state
machine -- every state, every operation, in order -- so restating the
machine inside these bytes would hash the same structure twice under two
grammars, and the second one would be this module's rather than the
compiler's. It leaves the schedule out, which is why the
schedule's own ``source_sha()`` sits beside it: data, as a curve's or a
table's digest on the call that reads it is.

A column of values injected at a line is identified by its contents. The
injection record carries the same ``sha256:`` content stamp an assumption
table and a join's right side carry, taken over the values, their type and
their count, so two models handed different data under one column name
hash differently. It has to be the values: an injection reads nothing, so
nothing upstream of it can move on its behalf. Both containers a whole
column arrives in are covered — a ``pl.Series`` and the NumPy array a
simulation hands back — and over the same bytes, so the same values stamp
alike whichever one they came in.

## The graph digest

One digest for the whole model hashes the **pairs** of node id and Merkle
fingerprint, sorted, then the assumption tables the model reads, then the
columns it cannot account for. Pairs rather than a bag of hashes, because
two columns computed the same way share a fingerprint by design: swapping
which formula binds to which column name leaves the bag identical and must
still move the digest.

## The formulas-only digest

``graph_fingerprint`` is the model *as run*: a lookup carries its table's
content hash, so re-sourcing a basis moves it exactly as editing a formula
does. A reviewer signing off a quarter asks the two questions apart -- "did
the logic change, or only the data?" -- and wants one figure for the first.
:func:`formulas_fingerprint` is that figure: the same fold, taken over trees
in which every attribute naming a value object's *content* is replaced by one
fixed marker, with the tables section left out. Everything a modeller types
stays in -- literals, table names, keys, a miss policy, a valuation date.

Nothing here is stamped by the fold. Folding is the cheap structural pass
that hole detection and graph export both run today; hashing every
op-tree on those paths would be work neither caller asked for. Ask for a
fingerprint explicitly with :func:`stamp_fingerprints`.
"""

from __future__ import annotations

import datetime
import hashlib
import math
import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, NoReturn, assert_never

from gaspatchio._canonical import DISPLAY_WIDTH, SHA256_PREFIX, short_fingerprint
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

from .graph_models import STATE_NAMESPACE, NodeType

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from gaspatchio._semantic.ir import (
        AttrValue,
        LitScalar,
        LitSequenceMember,
        OpNode,
    )

    from .graph_builder import CalcGraph
    from .graph_models import GraphNode, NodeId, SelectionStep

# HEX_WIDTH is the width of a digest's own hex representation -- sixty-four
# lowercase hex digits -- not the length of the "sha256:<hex>" string a
# node is actually stamped with; :func:`stamp_fingerprints` adds that
# prefix on top. A display surface abbreviates to the first twelve hex
# digits of the digest, which is the width a reviewer can hold in their
# head and still far beyond accidental collision for one model's node
# count.
HEX_WIDTH: Final[int] = 64

# One tag per node type. A node's bytes start with its tag so that two
# different kinds of node can never encode alike, however similar their
# payloads look.
_TAG_COL: Final[bytes] = b"\x01"
_TAG_LIT: Final[bytes] = b"\x02"
_TAG_BINOP: Final[bytes] = b"\x03"
_TAG_CALL: Final[bytes] = b"\x04"
_TAG_WHEN_THEN: Final[bytes] = b"\x05"
_TAG_STATE: Final[bytes] = b"\x06"
_TAG_ENGINE_NATIVE: Final[bytes] = b"\x07"

# One tag per scalar type, for a literal's payload and for an attribute
# value. A term of thirty years and the text "30" are different things to
# every lowering that reads them back, so they are different bytes here.
_TAG_NONE: Final[bytes] = b"\x10"
_TAG_BOOL: Final[bytes] = b"\x11"
_TAG_INT: Final[bytes] = b"\x12"
_TAG_FLOAT: Final[bytes] = b"\x13"
_TAG_STR: Final[bytes] = b"\x14"

# A literal holding a sequence of scalars -- the age boundaries of a
# banded lookup, a schedule of loadings. Its own tag, sitting where a
# scalar's tag would, so that a band of one boundary can never encode as
# the boundary on its own.
_TAG_SEQUENCE: Final[bytes] = b"\x15"

# A calendar date, as a count of whole days from the epoch below, zigzagged
# and written as a varint. The number and the layout are the content
# grammar's (section 12.3), deliberately: that section took its date tag
# from the block this one occupies so that a reader holding both grammars
# meets one number and one layout per type rather than two. A date is a
# calendar day and nothing below it -- no time zone, no offset, no leap
# second -- counted on the proleptic Gregorian calendar, extended backwards
# without limit.
_TAG_DATE: Final[bytes] = b"\x16"
_EPOCH: Final[datetime.date] = datetime.date(1970, 1, 1)

# The three leaves that have no formula. Separate tags because the three
# make different claims about a model -- "the data supplied this",
# "nothing here can explain this", and "this is not a column at all" --
# and a comparison between two quarters has to be able to see one become
# another.
_TAG_INPUT_LEAF: Final[bytes] = b"\x20"
_TAG_HOLE_LEAF: Final[bytes] = b"\x21"
_TAG_STATE_LEAF: Final[bytes] = b"\x22"

# Which tag stands for a leaf of each kind. A leaf is a node with no
# operation tree to hash, and the three kinds that can be one are here;
# every other kind reaches :func:`canonical_bytes` instead.
_LEAF_TAGS: Final[dict[NodeType, bytes]] = {
    NodeType.INPUT: _TAG_INPUT_LEAF,
    NodeType.HOLE: _TAG_HOLE_LEAF,
    NodeType.STATE: _TAG_STATE_LEAF,
}

# Every NaN encodes as this one quiet-NaN payload. A literal cannot be
# NaN -- the op-tree refuses one at construction -- but a call attribute
# has no such gate, and two runs that both produced a NaN have not
# drifted. Reading their differing bit patterns as different models would
# be a false positive in the one report whose value is its silence.
_QUIET_NAN: Final[bytes] = b"\x7f\xf8\x00\x00\x00\x00\x00\x00"

# The attribute an assumption-table lookup carries its table's content hash
# under. Named here so the graph digest can restate the model's assumption
# dependencies as a section of their own.
_TABLE_FINGERPRINT_ATTR: Final[str] = "table_fingerprint"


@dataclass(frozen=True, slots=True)
class NodeFingerprints:
    """One node's two hashes: what it computes, and what its answer rests on."""

    local: bytes
    merkle: bytes


# --- primitive encodings ----------------------------------------------------


def _uvarint(value: int) -> bytes:
    """Encode a count or a byte length, seven bits at a time, low group first."""
    out = bytearray()
    while True:
        group = value & 0x7F
        value >>= 7
        if value:
            out.append(group | 0x80)
        else:
            out.append(group)
            return bytes(out)


def _zigzag(value: int) -> bytes:
    """Encode a whole number that may be negative, small magnitudes stay short.

    -1 becomes 1, 1 becomes 2, -2 becomes 3. Two's complement would spell
    every negative number at full width; an ``at_period`` offset is
    routinely -1 and deserves its one byte.
    """
    return _uvarint((value << 1) ^ (-1 if value < 0 else 0))


def _text(value: str) -> bytes:
    """Encode text as UTF-8 behind its byte length."""
    raw = value.encode("utf-8")
    return _uvarint(len(raw)) + raw


def _decimal(value: float) -> bytes:
    """Encode a decimal as its eight IEEE-754 bytes, most significant first.

    **A negative zero keeps its own sign bit**, and so hashes apart from a
    positive one. Until ``gspv0-preview-3`` the two were written alike, on
    the ground that they are one number in the arithmetic; the vocabulary
    this identity is published beside can tell them apart -- ``to_text``
    spells them differently and 11.1.25 gives a signed zero observable
    division semantics -- so a model could print 0.0 one quarter and 100.0
    the next under one fingerprint, with the change report reporting no
    drift. An identity must not equate what an admitted operation can
    distinguish.

    Every NaN is still written as one quiet NaN, and that reason stands
    untouched: two runs that both produced a NaN have not drifted, and
    reading their differing bit patterns as two models would be a false
    positive in the one report whose value is its silence. The infinities
    keep their own distinct bits.
    """
    if math.isnan(value):
        return _QUIET_NAN
    return struct.pack(">d", value)


def _scalar(value: AttrValue | datetime.date) -> bytes:
    """Encode one value -- an attribute, or a literal's single payload.

    True/false is checked before whole numbers on purpose: Python makes
    ``True`` an integer, and a flag that fingerprinted as 1 would let a
    boolean attribute and a numeric one collide.

    The parameter is one type wider than ``AttrValue``, and the width is the
    literal's. Both positions share one scalar block in this grammar, so the
    date tag reaches an attribute too the moment a signature carries one --
    the encoder is ready and ``AttrValue`` is what is not, deliberately, for
    the reason stated where it is declared.
    """
    if value is None:
        return _TAG_NONE
    if isinstance(value, bool):
        return _TAG_BOOL + (b"\x01" if value else b"\x00")
    if isinstance(value, int):
        return _TAG_INT + _zigzag(value)
    if isinstance(value, float):
        return _TAG_FLOAT + _decimal(value)
    if isinstance(value, str):
        return _TAG_STR + _text(value)
    # The instant is tested before the date, and the order is the whole of
    # this pair. ``datetime.datetime`` is a SUBCLASS of ``datetime.date`` in
    # Python, so a producer testing for the date first would encode an
    # instant as its calendar day and lose the time in silence -- the same
    # shape of mistake as encoding a flag as the whole number 1, which the
    # first branch of this function is arranged against. ``Lit`` refuses an
    # instant at its own door too; this is the second of the three, and it
    # is here because an attribute reaches this function without passing
    # that one.
    if isinstance(value, datetime.datetime):
        msg = (
            f"A calculation-graph fingerprint cannot encode {value!r}: this "
            "grammar has a tag for a calendar date and none for a time of "
            "day, so an instant would encode as its own day and hash as a "
            "value it does not hold. Write it onto the frame as a column and "
            "compare against the column."
        )
        raise TypeError(msg)
    if isinstance(value, datetime.date):
        return _TAG_DATE + _zigzag((value - _EPOCH).days)
    # Unreachable while the op-tree's own literal and attribute types hold.
    # Named rather than left to fail somewhere further down, because a
    # fingerprint that quietly encoded an unexpected value as something
    # else would be wrong in the one artifact whose value is being right.
    msg = (
        f"A calculation-graph fingerprint cannot encode {value!r}: a formula's "
        "literals and configuration must each be text, a whole number, a "
        "decimal, a true/false flag, a calendar date, or absent."
    )
    raise TypeError(msg)


def _literal(value: LitScalar | tuple[LitSequenceMember, ...]) -> bytes:
    """Encode a literal's payload: one scalar, or a counted run of them.

    Kept apart from :func:`_scalar` because a call attribute is always one
    value (see ``ir.AttrValue``) and widening the attribute encoder to
    accept a sequence would say otherwise. The sequence tag sits where a
    scalar's tag would, so a band of one boundary and that boundary on
    its own are two encodings, not one.
    """
    if isinstance(value, tuple):
        return _TAG_SEQUENCE + _sequence([_scalar(member) for member in value])
    return _scalar(value)


def _attributes(attrs: tuple[tuple[str, AttrValue], ...]) -> bytes:
    """Encode a call's configuration, ordered by key text and behind its own count.

    Sorted rather than left in the order the call happened to build them,
    so two records configured identically fingerprint identically. The
    encoded value breaks a tie between repeated keys, which keeps the
    order total rather than merely stable.

    By the key's own text, and the difference is not academic: a key is
    written as its byte length in front of its UTF-8, so sorting the
    encodings would put a short key before a longer one that precedes it
    alphabetically. ``content`` and ``origin`` on an injection record are
    exactly that pair, and the two readings hash it differently.
    """
    ordered = sorted((key, _scalar(value)) for key, value in attrs)
    return _sequence([_text(key) + encoded for key, encoded in ordered])


def _sequence(items: Sequence[bytes]) -> bytes:
    """Encode a variable-length run behind its own count.

    Every other piece of this encoding is already self-delimiting -- text
    carries its length, a scalar its tag, a node its tag -- so the count is
    belt as well as braces. It is cheap, and it means the run's boundaries
    are stated outright rather than inferred from an argument about which
    tag bytes happen not to look like which length bytes. That argument is
    how tree hashes end up accepting something they never hashed.
    """
    return _uvarint(len(items)) + b"".join(items)


# --- the canonical bytes ----------------------------------------------------


def canonical_bytes(node: OpNode) -> bytes:
    """Return the bytes that stand for ``node`` and nothing else.

    Type tag, then the node's own fields in declaration order, with child
    nodes encoded in place. Carries no source span, no rendered formula
    text, and not the name of the column the node defines.

    The final ``case`` is unreachable for any real node; it exists so that
    an eighth node type added to the op-tree without teaching this function
    how to encode it fails type checking, rather than silently
    fingerprinting as something else at run time.

    See also :func:`gaspatchio._identity.canonical_bytes`, the audit
    chain's byte grammar for ``Schedule``/``Curve``/``Table`` canonical
    forms, which raises on NaN rather than normalizing it as this one does.
    """
    match node:
        case Col(name=name):
            encoded = _TAG_COL + _text(name)
        case Lit(value=value):
            encoded = _TAG_LIT + _literal(value)
        case BinOp(op=op, left=left, right=right):
            encoded = (
                _TAG_BINOP + _text(op) + canonical_bytes(left) + canonical_bytes(right)
            )
        case Call(name=name, args=args, attrs=attrs):
            encoded = (
                _TAG_CALL
                + _text(name)
                + _sequence([canonical_bytes(arg) for arg in args])
                + _attributes(attrs)
            )
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            encoded = (
                _TAG_WHEN_THEN
                + canonical_bytes(cond)
                + canonical_bytes(then)
                + canonical_bytes(otherwise)
            )
        case State(name=name):
            encoded = _TAG_STATE + _text(name)
        case EngineNative(engine=engine, text=text, deps=deps):
            encoded = (
                _TAG_ENGINE_NATIVE
                + _text(engine)
                + _text(text)
                + _sequence([_text(dep) for dep in deps])
            )
        case _ as unreachable:
            assert_never(unreachable)
    return encoded


def _leaf_bytes(node: GraphNode) -> bytes:
    """Return the bytes that stand for a node with no formula to hash.

    A column the data arrived with, a column nothing in the model accounts
    for, and one running state of a compiled rollforward. All three are a
    name and a neutral type; the tag is what keeps them from colliding, so
    that a column which stops being explained between two quarters is
    visible as a change rather than as nothing, and so that a column and a
    running state that happen to share a name are never one leaf.

    The name is the leaf's own, and for a running state that is the state
    reference the compilation carries -- ``account_value@eop``, the same
    string a ``State`` node inside any operation tree holds -- rather than
    the reserved id built around it. What identifies a state is what the
    compilation calls it; the ``state:`` namespace is how one artifact
    keeps its ids apart, and section 8.1 of the format says an id is
    positional within one artifact and means nothing across two.

    Raises:
        ValueError: If ``node`` is not one of the three kinds a leaf can
            be. Every other kind was folded from an operation tree and is
            hashed from that tree; reaching here with one is a fold that
            went wrong, and a leaf's bytes taken over a node that has a
            formula would identify it by its name instead of by what it
            computes.

    """
    tag = _LEAF_TAGS.get(node.kind)
    if tag is None:
        msg = (
            f"{node.id!r} is a {node.kind.value!r} node with no operation "
            "tree behind it. Only a column the data arrived with, a column "
            "nothing accounts for and a running rollforward state are "
            "identified by their name and their type; everything else is "
            "identified by what it computes, and a node of that kind "
            "reaching here is a fold that lost its tree."
        )
        raise ValueError(msg)
    return tag + _text(_leaf_name(node)) + _text(node.data.dtype)


def _leaf_name(node: GraphNode) -> str:
    """Return the name a leaf is identified by, which is not always its column.

    A running state has no column -- it is the compilation's own carried
    value, and nothing on the frame holds it -- so its name comes off its
    reserved id, which is that namespace followed by the state reference
    and nothing else. Taking the prefix off is exact, and it is not the
    id-splitting the format forbids: that rule is about recovering a
    *column* name from an id, which a column containing an ``@`` defeats.
    No column is in this namespace to be recovered -- the fold refuses one
    by name at the doors that mint nodes from column names
    (``graph_builder._refuse_reserved``) -- so every id here was built by
    the one place that builds them, out of the state reference and the
    prefix and nothing else.
    """
    if node.kind is NodeType.STATE:
        return node.id.removeprefix(STATE_NAMESPACE)
    # Every other leaf is a column, and the fold gives it its own name.
    return node.data.column if node.data.column is not None else node.id


# --- the two hashes ---------------------------------------------------------


def local_fingerprint(node: OpNode) -> bytes:
    """Return the hash of what ``node`` computes, ignoring what it reads."""
    return hashlib.sha256(canonical_bytes(node)).digest()


def _merkle(local: bytes, dep_fps: Sequence[bytes]) -> bytes:
    """Fold dependency fingerprints into a local one.

    The digests are fixed width, so concatenating them is unambiguous
    without a count in front. Order is bind order: a node that reads two
    columns the other way round is a different calculation.
    """
    return hashlib.sha256(local + b"".join(dep_fps)).digest()


def fingerprint(node: OpNode, dep_fps: Sequence[bytes]) -> bytes:
    """Return the hash of what ``node`` computes and what its answer rests on."""
    return _merkle(local_fingerprint(node), dep_fps)


def fingerprints_for(graph: CalcGraph) -> dict[NodeId, NodeFingerprints]:
    """Return both fingerprints for every node, keyed by node id.

    Pure: nothing on the graph is written. Walks the nodes in the order the
    graph holds them, which is the order the calculations ran, so
    everything a node reads is already fingerprinted by the time the node
    itself is.

    Args:
        graph: The folded graph to fingerprint.

    Returns:
        One :class:`NodeFingerprints` per node, in graph order.

    Raises:
        ValueError: If a node reads something the graph does not hold
            before it -- see :func:`_dependency_fingerprint`.

    """
    computed: dict[NodeId, NodeFingerprints] = {}
    for node_id, node in graph.nodes.items():
        op_tree = graph.op_trees.get(node_id)
        raw = canonical_bytes(op_tree) if op_tree is not None else _leaf_bytes(node)
        local = hashlib.sha256(raw).digest()
        deps = [
            _dependency_fingerprint(computed, node_id, read) for read in node.data.reads
        ]
        computed[node_id] = NodeFingerprints(local=local, merkle=_merkle(local, deps))
    return computed


def _dependency_fingerprint(
    computed: dict[NodeId, NodeFingerprints], node_id: NodeId, read: NodeId
) -> bytes:
    """Return the fingerprint of something a node reads, or refuse to guess.

    Reachable only for a graph rearranged after folding: the fold hands its
    nodes over in the order the calculations ran, and a node is added only
    after everything it reads. A hash taken with an upstream dependency
    quietly dropped would still be sixty-four characters long and would
    still compare equal to itself, which is exactly the kind of wrong
    answer nobody catches.

    Raises:
        ValueError: Always, when ``read`` has not been fingerprinted yet.

    """
    known = computed.get(read)
    if known is not None:
        return known.merkle
    msg = (
        f"Cannot fingerprint {node_id!r}: it reads {read!r}, which this graph "
        "does not hold before it. A calculation graph is held in the order its "
        "calculations ran, so a graph rearranged after folding cannot be "
        "fingerprinted -- fold it again rather than reordering it."
    )
    raise ValueError(msg)


def graph_fingerprint(
    graph: CalcGraph, *, prints: Mapping[NodeId, NodeFingerprints] | None = None
) -> bytes:
    """Return one hash standing for the whole model.

    Three sections, each behind its own count: the node id and Merkle
    fingerprint of every node, sorted by id; the assumption tables the
    model reads, sorted; and the columns it cannot account for, sorted,
    each with the content stamp of its values where the frame arrived
    holding it (:func:`hole_entries`).

    The first section hashes *pairs* rather than a bag of fingerprints. Two
    columns computed the same way share a fingerprint by design, so
    swapping which formula binds to which column name leaves a bag
    identical -- and must still move this digest.

    An assumption table's content hash already rides on the lookup node
    that reads it, so the second section restates something the first
    already covers. That is deliberate: it makes "which assumption bases
    was this model run against" a section of the digest rather than a fact
    buried inside one node's bytes.

    Args:
        graph: The folded graph to take one identity over.
        prints: The fingerprints already taken over this same graph, where
            the caller is holding them. Every caller that stamps the nodes
            is: :func:`stamp_fingerprints` hands back exactly what it
            wrote, and hashing every op-tree a second time to reach a
            digest the first pass already held is work no export needs to
            do. None takes them here.

    Returns:
        The digest, raw. A caller writing it onto a document puts it in
        the framework's ``"sha256:<hex>"`` shape first.

    Raises:
        ValueError: If ``prints`` does not cover exactly this graph's
            nodes. A digest taken over a mapping that has drifted from the
            graph would still be sixty-four characters long and would
            still compare equal to itself, which is the kind of wrong
            answer nobody catches.

    """
    if prints is not None and prints.keys() != graph.nodes.keys():
        _refuse_foreign_prints(graph, prints)
    taken = fingerprints_for(graph) if prints is None else prints
    pairs = [_text(node_id) + taken[node_id].merkle for node_id in sorted(taken)]
    tables = [_text(table) for table in sorted(_assumption_fingerprints(graph))]
    holes = hole_entries(_hole_stamps(graph))
    selected = [
        step.merkle
        for step in selection_fingerprints(
            graph.selection, {node_id: fps.merkle for node_id, fps in taken.items()}
        )
    ]
    return hashlib.sha256(
        _sequence(pairs)
        + _sequence(tables)
        + _sequence(holes)
        + selection_section(selected)
    ).digest()


def selection_local(kind: str, tree: OpNode) -> bytes:
    """Return one selection step's own digest: its kind, then its predicate's bytes.

    The kind is text behind its length, as every text in this grammar is,
    and the tree's canonical bytes follow it with nothing between: a filter
    and a semi join are different steps over the same tree shape only in
    principle, and a step that changed from keeping the rows a key matches to
    dropping them has to move the digest whatever its tree says.
    """
    return hashlib.sha256(_text(kind) + canonical_bytes(tree)).digest()


def selection_fingerprints(
    steps: Sequence[SelectionStep], reads: Mapping[NodeId, bytes]
) -> list[NodeFingerprints]:
    """Return each selection step's two digests, in the order the model took them.

    The local digest is :func:`selection_local`; the step's fingerprint folds
    it over the fingerprints of what the predicate reads, in the order it
    reads them -- section 12's fold, exactly as a node's is -- so a step whose
    predicate stood still while a column it reads was redefined has moved in
    identity and not in itself.

    Args:
        steps: The graph's selection steps.
        reads: Every node's fingerprint, raw, by id: the node digests for
            ``graph_fingerprint``, the masked ones for the formulas figure.

    Raises:
        ValueError: If a step reads a node ``reads`` does not hold.

    """
    stamped: list[NodeFingerprints] = []
    for step in steps:
        local = selection_local(step.kind, step.tree)
        stamped.append(
            NodeFingerprints(
                local=local, merkle=_merkle(local, _step_reads(step, reads))
            )
        )
    return stamped


def _step_reads(step: SelectionStep, reads: Mapping[NodeId, bytes]) -> list[bytes]:
    """Return the fingerprints one step reads, or refuse to fold over a gap."""
    missing = [read for read in step.reads if read not in reads]
    if missing:
        msg = (
            f"Cannot fingerprint {step.id!r}: its predicate reads {missing}, which "
            "this graph does not hold. Fold the frame again rather than exporting "
            "from this graph."
        )
        raise ValueError(msg)
    return [reads[read] for read in step.reads]


def selection_section(fingerprints: Sequence[bytes]) -> bytes:
    """Return the selection section both model digests end with, or nothing.

    The steps' fingerprints, raw and in the order the model took them --
    not sorted, because the list is ordered and the order is the model's --
    behind their count. **Absent rather than empty** where the model selects
    no rows, so a model that never selects keeps the digest it had before
    selection entered the record: no published digest moves for a model that
    does not select.
    """
    return _sequence(fingerprints) if fingerprints else b""


def hole_entries(stamps: Mapping[str, str | None]) -> list[bytes]:
    """Return the third section's entries: each hole once, by name, stamped where it is.

    One entry per name, sorted by name: the name as text, and where the
    hole carries a content stamp -- the frame arrived holding the column --
    that stamp as text straight after it, in the same entry. A hole with no
    stamp is its name alone, exactly as every hole was before the stamp
    existed, so a document whose holes are all overwritten writes, or that
    has none, keeps the digest it had.

    Args:
        stamps: Each hole's name and its stamp, or None, as the holes section
            lists them: one per name.

    Returns:
        The entries, in name order, for :func:`_sequence`.

    """
    return [
        _text(name) + (_text(stamp) if stamp is not None else b"")
        for name, stamp in sorted(stamps.items())
    ]


def _hole_stamps(graph: CalcGraph) -> dict[str, str | None]:
    """Return each hole's name with the stamp of its first node in the graph's order.

    The holes section lists one entry per name, carrying what the first
    hole node standing for it says (section 7.1); the digest reads the same
    node, so the two cannot disagree about which stamp a name carries.
    """
    found: dict[str, str | None] = {}
    for node in _hole_nodes(graph):
        name = _leaf_name(node)
        if name not in found:
            account = graph.hole_accounts.get(node.id)
            found[name] = account.content if account is not None else None
    return found


def _hole_names(graph: CalcGraph) -> list[str]:
    """Return every column the model cannot account for, once each and sorted.

    By the hole's own name, which is its column: a hole is always an account
    of one, so :func:`_leaf_name` answers with that column here and the two
    readings can never come apart. Once each, as the holes section lists
    them: a column written over past the frame's doors, calculated again and
    written over again has two hole nodes and is one unaccounted name.
    De-duplicated first and sorted second, as the tables are.
    """
    return sorted(set(map(_leaf_name, _hole_nodes(graph))))


def _refuse_foreign_prints(
    graph: CalcGraph, prints: Mapping[NodeId, NodeFingerprints]
) -> NoReturn:
    """Refuse a mapping of fingerprints that is not this graph's, and say how.

    Reached when a mapping does not cover exactly this graph's nodes: a
    node with no fingerprint offered, or a fingerprint offered for a node
    the graph does not hold. Both node sets are named rather than counted,
    because "which nodes" is what tells the caller whether they are holding
    a stale mapping or the wrong model's.

    Drift under an unchanged set of node ids -- the same nodes, digests
    taken before one of their formulas moved -- is the caller's contract
    and is checked nowhere, because checking it would mean recomputing
    every digest, which is the whole pass handing the mapping over exists
    to avoid.

    Raises:
        ValueError: Always.

    """
    unhashed = sorted(graph.nodes.keys() - prints.keys())
    unknown = sorted(prints.keys() - graph.nodes.keys())
    msg = (
        "Cannot take one identity for this model from fingerprints that were "
        "not taken over it. Nodes in the graph with no fingerprint offered: "
        f"{unhashed or 'none'}. Fingerprints offered for nodes the graph does "
        f"not hold: {unknown or 'none'}. Hand over what stamp_fingerprints "
        "returned for this graph, or hand over nothing and let this take them."
    )
    raise ValueError(msg)


def _hole_nodes(graph: CalcGraph) -> list[GraphNode]:
    """Return every node standing for a column the model cannot account for."""
    return [node for node in graph.nodes.values() if node.kind is NodeType.HOLE]


def _assumption_fingerprints(graph: CalcGraph) -> set[str]:
    """Return the content hash of every assumption table the model looks up in."""
    found: set[str] = set()
    trees = [*graph.op_trees.values(), *(step.tree for step in graph.selection)]
    for op_tree in trees:
        for current in walk(op_tree):
            if not isinstance(current, Call):
                continue
            found.update(
                value
                for key, value in current.attrs
                if key == _TABLE_FINGERPRINT_ATTR and isinstance(value, str)
            )
    return found


# --- the formulas-only identity ---------------------------------------------

# The one text every content digest is replaced by in the formulas form. Not
# a digest's shape, so a reader meeting it in a printed tree cannot take it
# for one, and the same text in every masked position, so two models reading
# two different bases through one formula encode alike.
FORMULAS_MASK: Final[str] = "masked"

# Which attributes name a value object's content, by the identifier that
# carries them. A table's content hash, a join's right side, a mortality
# wrapper's recipe and its base, a projection's schedule, and the two halves
# of a column of values handed over at a line: what the values were, and the
# container they came in. Each is data rather than something a modeller
# typed into a formula. The key a value sits under, and whether it is
# present at all, stay -- those are the call's own shape.
_CONTENT_ATTRIBUTES: Final[dict[str, frozenset[str]]] = {
    "lookup": frozenset({"table_fingerprint"}),
    "join": frozenset({"right_fingerprint"}),
    "mortality.at": frozenset({"mortality", "table_fingerprint"}),
    "projection_set": frozenset({"schedule_source_sha"}),
    "injected": frozenset({"content", "origin"}),
}

# A projection built from a schedule object restates two of that schedule's
# own parameters beside its digest -- where the timeline starts and how often
# it steps -- so a re-sourced schedule would move those copies even with the
# digest masked. They are masked with it, in that form and no other: a
# projection set from a start and a frequency typed into ``projection.set``
# itself carries no schedule digest, and there they are the model's own.
_SCHEDULE_FORM: Final[str] = "schedule_source_sha"
_SCHEDULE_RESTATES: Final[frozenset[str]] = frozenset({"start", "frequency"})

# The families that name their value object under one key on every member:
# every ``curve.*`` call carries its curve's ``source_sha`` as ``curve``, and
# every ``schedule.*`` and ``projection_frame.*`` call its schedule's as
# ``schedule``. By prefix, so a member the vocabulary grows later is masked
# with its family rather than left to move the digest on a data change.
_CONTENT_FAMILIES: Final[tuple[tuple[str, str], ...]] = (
    ("curve.", "curve"),
    ("schedule.", "schedule"),
    ("projection_frame.", "schedule"),
    # A compiled rollforward's own call and the three that read it back out
    # carry the schedule the machine runs on, beside the machine's
    # fingerprint, which leaves it out. The prefix has no dot:
    # the bare ``rollforward`` call is a member of its own family.
    ("rollforward", "schedule"),
)


def content_attributes(name: str) -> frozenset[str]:
    """Return the attribute keys of ``name`` whose value names a value object's content.

    These are the positions the formulas-only digest masks. A call reading a
    table, a curve or a schedule carries that object's digest as one flat
    text attribute (section 12.1), so a model re-run on a re-sourced basis
    differs from last quarter's in exactly these values and nowhere else in
    its trees. A compiled rollforward's ``fingerprint`` is not among them:
    it is the compiler's identity for the whole state machine, which is
    logic, and it is kept. The ``schedule`` beside it is: the fingerprint
    leaves the schedule out, and the call states it as data.

    Args:
        name: An operation identifier, as a call node carries it.

    Returns:
        The keys to mask; empty for an identifier that reads no value object.

    Examples:
        >>> from gaspatchio.frame.graph.fingerprint import content_attributes
        >>> sorted(content_attributes("mortality.at"))
        ['mortality', 'table_fingerprint']
        >>> sorted(content_attributes("curve.spot_rate"))
        ['curve']
        >>> sorted(content_attributes("rollforward.state"))
        ['schedule']
        >>> sorted(content_attributes("projection.at_period"))
        []

    """
    named = _CONTENT_ATTRIBUTES.get(name, frozenset())
    family = frozenset(
        key for prefix, key in _CONTENT_FAMILIES if name.startswith(prefix)
    )
    return named | family


def formulas_tree(node: OpNode) -> OpNode:
    """Return ``node`` with every content digest replaced by :data:`FORMULAS_MASK`.

    The tree keeps its shape: every node, every operand and every attribute
    key is where it was, and only the value of an attribute
    :func:`content_attributes` names is replaced -- whatever that value was,
    a null included, because whether a base could be hashed is a fact about
    the base. A projection built from a schedule object also has the
    ``start`` and ``frequency`` it restates from that schedule masked, since
    they are the schedule's content written out again. An engine-native
    fragment's text is kept as written.

    Args:
        node: An operation tree, as the fold records it.

    Returns:
        The masked tree. Its canonical bytes are what the formulas-only
        digest takes each node's identity over.

    Examples:
        >>> from gaspatchio._semantic.ir import Call, Col
        >>> from gaspatchio.frame.graph.fingerprint import formulas_tree
        >>> read = Call(
        ...     "lookup",
        ...     (Col("age"),),
        ...     (
        ...         ("table", "mortality"),
        ...         ("table_fingerprint", "sha256:" + "ab" * 32),
        ...         ("on_missing", "raise"),
        ...         ("fill_value", None),
        ...     ),
        ... )
        >>> dict(formulas_tree(read).attrs)["table_fingerprint"]
        'masked'
        >>> dict(formulas_tree(read).attrs)["table"]
        'mortality'

    """
    match node:
        case Call(name=name, args=args, attrs=attrs):
            masked = content_attributes(name)
            if _SCHEDULE_FORM in masked and any(
                key == _SCHEDULE_FORM for key, _ in attrs
            ):
                masked |= _SCHEDULE_RESTATES
            return Call(
                name,
                tuple(formulas_tree(arg) for arg in args),
                tuple(
                    (key, FORMULAS_MASK if key in masked else value)
                    for key, value in attrs
                ),
            )
        case BinOp(op=op, left=left, right=right):
            return BinOp(op, formulas_tree(left), formulas_tree(right))
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            return WhenThen(
                formulas_tree(cond), formulas_tree(then), formulas_tree(otherwise)
            )
        case Col() | Lit() | State() | EngineNative():
            return node
        case _ as unreachable:
            assert_never(unreachable)


# A column of values handed over at a line has no tree on the wire in either
# profile, so a reader recomputing the formulas-only digest from a document
# cannot mask one. Both of its attributes are masked, which makes its masked
# bytes one constant every such node shares -- and a reader holding nothing
# but the node's ``provenance`` can take them.
HANDED_OVER_FORMULAS_LOCAL: Final[bytes] = hashlib.sha256(
    canonical_bytes(
        Call("injected", (), (("content", FORMULAS_MASK), ("origin", FORMULAS_MASK)))
    )
).digest()


def formulas_digest(
    pairs: Mapping[str, bytes],
    hole_names: Iterable[str],
    selection: Sequence[bytes] = (),
) -> bytes:
    """Return the formulas-only digest over its sections.

    The first and third of :func:`graph_fingerprint`'s sections, behind
    their own counts and nothing else: every (node id, masked fingerprint)
    pair sorted by id, then every unaccounted column name once and sorted.
    The tables section is left out rather than masked, because a list of
    masked entries would still count the bases a model reads, and how many
    tables a basis is split across is data too. Where the model selects
    rows, the selection section follows, over the steps' masked fingerprints
    (:func:`selection_section`).

    Args:
        pairs: Every node's fingerprint folded over masked trees, raw, by id.
        hole_names: The columns the model cannot account for; repeats are
            taken once.
        selection: Each selection step's fingerprint folded over its masked
            tree and the masked fingerprints of what it reads, raw, in the
            order the model took the steps.

    Returns:
        The digest, raw.

    """
    section_one = [_text(node_id) + pairs[node_id] for node_id in sorted(pairs)]
    section_three = [_text(name) for name in sorted(set(hole_names))]
    return hashlib.sha256(
        _sequence(section_one) + _sequence(section_three) + selection_section(selection)
    ).digest()


def formulas_fingerprint(graph: CalcGraph) -> bytes:
    """Return one hash standing for the model's formulas, its data left out.

    The fold of :func:`graph_fingerprint`, taken again with every node's
    local digest over its masked tree (:func:`formulas_tree`): a re-sourced
    table, a shocked curve, a new schedule, or a different column of values
    handed over at a line leaves it where it was, and an edited formula, a
    lookup pointed at a different table name, or a changed literal moves it.
    Leaves -- arriving columns, unaccounted columns, running states -- carry
    no content digest and hash as they always do.

    **A compiled rollforward's machine is logic and its schedule is data.**
    The compiler's own fingerprint is taken over the machine alone -- every
    state, operation, operand, rounding and stopping rule -- and is kept;
    the schedule it runs on travels beside it as the ``schedule`` attribute
    and is masked. So under a rollforward a re-sourced schedule
    moves ``graph_fingerprint`` and leaves this digest where it was, and an
    edited machine moves both.

    Args:
        graph: The folded graph to take the formulas-only identity over.

    Returns:
        The digest, raw. A caller writing it onto a document puts it in the
        framework's ``"sha256:<hex>"`` shape first.

    Examples:
        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> from gaspatchio.assumptions import Table
        >>> from gaspatchio.frame.graph import (
        ...     fold,
        ...     formulas_fingerprint,
        ...     graph_fingerprint,
        ... )
        >>> def quarter(rate: float) -> tuple[bytes, bytes]:
        ...     table = Table(
        ...         name="lapse",
        ...         source=pl.DataFrame({"duration": [0, 1], "rate": [rate, 0.05]}),
        ...         dimensions={"duration": "duration"},
        ...         value="rate",
        ...     )
        ...     af = ActuarialFrame(pl.DataFrame({"duration": [0, 1]}))
        ...     af.lapse_rate = table.lookup(duration=af.duration)
        ...     graph = fold(af)
        ...     return graph_fingerprint(graph), formulas_fingerprint(graph)
        >>> (graph_q1, formulas_q1), (graph_q2, formulas_q2) = (
        ...     quarter(0.10),
        ...     quarter(0.12),
        ... )
        >>> graph_q1 == graph_q2
        False
        >>> formulas_q1 == formulas_q2
        True

    """
    masked: dict[NodeId, NodeFingerprints] = {}
    for node_id, node in graph.nodes.items():
        op_tree = graph.op_trees.get(node_id)
        raw = (
            canonical_bytes(formulas_tree(op_tree))
            if op_tree is not None
            else _leaf_bytes(node)
        )
        local = hashlib.sha256(raw).digest()
        deps = [
            _dependency_fingerprint(masked, node_id, read) for read in node.data.reads
        ]
        masked[node_id] = NodeFingerprints(local=local, merkle=_merkle(local, deps))
    folded = {node_id: fps.merkle for node_id, fps in masked.items()}
    selected = [
        _merkle(
            selection_local(step.kind, formulas_tree(step.tree)),
            _step_reads(step, folded),
        )
        for step in graph.selection
    ]
    return formulas_digest(folded, _hole_names(graph), selected)


# --- storing and showing ----------------------------------------------------


def stamp_fingerprints(graph: CalcGraph) -> dict[NodeId, NodeFingerprints]:
    """Write both fingerprints onto every node of ``graph``, as a stamp.

    Each stamp is ``SHA256_PREFIX`` followed by sixty-four lowercase hex
    digits -- the same shape every other content hash in the framework
    takes (:func:`gaspatchio._identity.source_sha_of`, ``content_sha_of``,
    the ``table_fingerprint`` attribute a lookup node already carries),
    built from the one constant those share rather than a second literal
    written here.

    The fold does not do this. Its two callers today -- reporting the
    columns a model cannot account for, and exporting the graph -- have
    never asked for a content hash, and hashing every op-tree on their
    paths would be work neither wants. A caller that wants
    content-addressed identity asks for it here.

    Args:
        graph: The folded graph to stamp. Mutated in place.

    Returns:
        The same fingerprints that were stamped, so a caller needing both
        the stamped graph and the raw digests pays for one pass. The
        returned :class:`NodeFingerprints` still hold raw bytes -- the
        scheme prefix is the stamped string's form only.

    """
    computed = fingerprints_for(graph)
    for node_id, fps in computed.items():
        data = graph.nodes[node_id].data
        data.local_fingerprint = f"{SHA256_PREFIX}{fps.local.hex()}"
        data.fingerprint = f"{SHA256_PREFIX}{fps.merkle.hex()}"
    return computed


__all__ = [
    "DISPLAY_WIDTH",
    "FORMULAS_MASK",
    "HANDED_OVER_FORMULAS_LOCAL",
    "NodeFingerprints",
    "canonical_bytes",
    "content_attributes",
    "fingerprint",
    "fingerprints_for",
    "formulas_digest",
    "formulas_fingerprint",
    "formulas_tree",
    "graph_fingerprint",
    "local_fingerprint",
    "selection_fingerprints",
    "selection_local",
    "selection_section",
    "short_fingerprint",
    "stamp_fingerprints",
]
