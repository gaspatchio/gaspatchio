# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What kind of dependency one read is, so an edge can say which it was.

"What does this reserve depend on?" and "what selected the row?" are
different questions. A graph whose edges are all one colour answers the
first with the second folded into it: an impact cone drawn through a
lookup key sweeps in every column that ever *found* a rate, and the
reviewer reading it cannot tell those from the columns whose values are
actually in the number.

So every read is classified in two words. The first is ``DIRECT`` or
``INDIRECT`` -- whether the value read flows into the result, or only
decided which values did -- and it is the one an edge itself carries, as
its ``relationship``. The second narrows it: ``IDENTITY``,
``TRANSFORMATION`` and ``AGGREGATION`` narrow ``DIRECT``; ``JOIN``,
``GROUP_BY``, ``FILTER``, ``SORT``, ``WINDOW`` and ``CONDITIONAL`` narrow
``INDIRECT``.

The two words are produced together here and are written apart. One
narrowing covers four edges in five, and a reader who has to tell an
impact cone from a lookup needs only the first word -- so the written
edge is the endpoints and the relationship, and the narrowing travels on
the reading node in the ``gaspatchio_column_transformation`` facet, where
a consumer that has never met it loses a narrowing rather than a graph.
Nothing in this module knows about that split: it classifies a read, and
``artifact.py`` decides which half goes where.

## The rules

- the whole formula is one reference to another column -- a rename, or a
  plain copy -- so the value arrives unchanged: ``DIRECT`` / ``IDENTITY``;
- an ordinary operand of an arithmetic, comparison or accessor formula:
  ``DIRECT`` / ``TRANSFORMATION``;
- an operand of an accumulating operation, whose result is a function of
  every period rather than of this one: ``DIRECT`` / ``AGGREGATION``;
- a column read **only** inside a conditional's test: ``INDIRECT`` /
  ``CONDITIONAL``;
- a lookup key, and the key a join matched an arriving column on:
  ``INDIRECT`` / ``JOIN``.
- a positional list index: ``INDIRECT`` / ``FILTER``; the selected list
  remains a direct operand unless an enclosing indirect context narrows it.
- the axis ``projection.broadcast_to_periods`` lays a per-policy value
  along -- ``like=``, or ``month`` where it was omitted: ``INDIRECT`` /
  ``WINDOW``. Only that list's length reaches the answer (section
  11.1.32), so its values are in no number; it is still a read, because a
  shorter axis is a shorter result. The value being repeated stays a
  direct operand.

``GROUP_BY`` and ``SORT`` are in the vocabulary
and nothing here emits one. They are defined so that a consumer meeting a
producer whose model shapes rows in those ways meets a name that has been
defined rather than one it has to guess at.

A rollforward state read is not a column read, and no rule here
classifies one: ``State`` names the compilation's own running value and
the frame supplies nothing for it. It still reaches the edge list, on the
one node that reads it. A compiled rollforward is one node in the graph,
and what that node reads is decided where it is minted
(``graph_builder.py``) rather than here, because its tree is the
compilation's identity rather than its recipe: there is nothing in it for
this walk to read. Two claims come out of that site, both of them rules
this module already states. A column the compilation consumes is an
operand of a linear recurrence, so it is ``DIRECT``/``AGGREGATION`` --
its value is in every later period's answer, not only in this one. A
running state read by the compilation that owns it is
``DIRECT``/``TRANSFORMATION``: it is the balance being carried at this
period. What a line pulling a state back out reads is the compilation
itself, claimed here under whatever context the extraction sits in --
ordinarily ``DIRECT``/``TRANSFORMATION``, and narrowed by a conditional's
test or a lookup's keys exactly as a column read would be.

## Which operations accumulate

An operation earns a place in :data:`AGGREGATING_CALLS` when its lowering
folds across the period axis, and not when it merely runs along one: a
cumulative product, a reverse-cumulative sum, a linear recurrence, a solve
that consumes a whole cashflow list to return one number. ``excel.pv`` and
``finance.present_value`` compute a closed form out of the values standing
at one period -- ``CF / (1 + rate)^period``, and Excel's annuity identity
-- so they are ordinary transformations of those values, whatever the
actuarial name suggests. Their operands are ``TRANSFORMATION``.

One operation is in the set without folding anything. ``list.reverse``
answers period ``t`` from the operand's period ``T - 1 - t``, where ``T``
is that policy's own length, so which period a value came from depends on
how long the policy is -- there is no single distance for an offset to
quote, and every period of the operand is in some period of the answer.
An impact cone drawn through it has to sweep the whole axis, which is
what ``AGGREGATION`` says (section 11.1.41); ``TRANSFORMATION`` would tell
a reviewer that this period's answer came from this period's value.

One operation falls on both sides of that line depending on how it was
called. ``finance.discount_factor`` under ``method="forward"`` takes the
per-period reciprocal and cumulates it, so every period's rate is inside
every later factor; under ``method="spot"`` it raises each period's own
rate to minus that period and folds nothing. The method travels on the
node as a typed attribute, so :data:`AGGREGATING_METHODS` classifies on it
rather than escalating the whole call name and reporting a spot factor as
an accumulation it is not.

A column read as the *time* into a curve -- ``curve.spot_rate(t)``,
``curve.discount_factor(t)`` -- is ``DIRECT``/``TRANSFORMATION``, and the
choice is deliberate rather than an omission. It is the nearest thing in
this vocabulary to a join key that is not one, and what settles it is that
interpolation puts ``t`` into the arithmetic: the curve reads between its
own knots, and the discount factor raises to minus ``t`` on top of that,
so the time's value is in the number rather than having only found it. A
lookup key is the other case exactly -- the table hands back the rate it
stored, unchanged by which key reached it.

## Nesting, and reading one column twice

Two questions, one ladder. :data:`_STRENGTH` ranks the six claims that
can fire, and it settles both of them.

A name read more than once in one formula gets the strongest claim any of
its reads supports: what the edge has to answer is "is this column's value
in the number?", and one read that puts it there settles that however many
others only consulted it.

A single read under nested contexts is settled by the same ladder, once
one prior rule has had its say: an indirect context absorbs a direct one
nested inside it. A value that only chose a branch did not stop choosing a
branch by being accumulated on the way, and a lookup key did not stop
being a key because the rate it found is then summed. Nothing absorbs in
the other direction -- entering a conditional's test, or a lookup's keys,
from an ordinary operand position is what makes a read indirect at all.
When indirect contexts nest, :data:`_STRENGTH` puts ``JOIN`` before
``FILTER`` before ``CONDITIONAL``. A lookup key inside a selection index
is still a ``JOIN``; an index inside a conditional test is a ``FILTER``.
Nesting order decides nothing.

## Which period a read came from

Three operations read their source somewhere other than the period being
computed, and until the read says which period it read, "this month's
reserve reads last month's -- show me which cell" is answered by a graph
pointing at the same cell. So a read made through one of them carries an
``offset``: the distance in periods, negative for a prior period and
positive for a later one, which is the sign ``projection.at_period``
already asks an actuary to write.

The distance is quoted rather than derived. ``projection.previous_period``
and ``projection.next_period`` carry no attribute because the identifier
fixes the distance -- one back, one ahead -- and ``projection.at_period``
states its own in ``relative_period``, the attribute the executable
profile's operation tree serialises. Nothing here reads a distance back
out of an expression's text.

Three kinds of read carry none. A read of the period being computed is
nearly every read, and it says so by carrying nothing rather than by
carrying a zero. A read whose narrowing is not ``TRANSFORMATION`` carries
none either: an offset says which period a *value* came from, and a lookup
key, a conditional's test or an operand folded across the whole run is not
a value narrowed by a distance. And a name read at two different periods
in one formula reaches the edge as one edge, so neither distance is the
read's -- it carries none, because stating one would be a narrower claim
than the formula supports.

## Which periods an aggregation reads

An offset says which period a value came from. An operand folded across
the run comes from many, and "does this reserve read the same periods as
the workbook's column?" is the timing half of a reconciliation -- which
modellers answered with regular expressions over the formula text until
the edge said it. So a direct read states its window (section 9):
``periods`` for an ``AGGREGATION`` read, each bound a whole number of
periods from the period being computed or the run's ``first`` or
``last``, and ``position`` for a read a literal ``list.get`` makes.

The window is quoted rather than derived, like the offset. Each
accumulating call's operands are read over a window the identifier and
its own attributes fix -- ``reverse`` on the two scans and the
recurrence, ``start_at`` on the survival fold, ``discount_kind`` on a
prospective value, ``method`` on a discount factor -- and
:func:`_operand_windows` is that table, one entry per identifier, with
nothing read out of an expression's text. The walk carries a *reach*
beside the context and the period: where in the run the subtree is read,
which a shift moves, an accumulation widens and a literal position pins.
A composition the two members cannot write exactly -- a fold of a value
read one period ahead, a position taken off a shifted list -- reaches
nothing, and the read states no window rather than an approximate one.

A window is a bound, not a promise that every period inside it moves the
answer: an operand moved outside it moves no period of the result, and
that is what the kit's perturbation vectors hold every engine to. Two
identifiers are wider than their reads on purpose, because the members
cannot write what they read: ``list.reverse``'s period ``t`` reads the
operand's ``T - 1 - t``, which is no fixed distance and no fixed end, so
it states the whole run; and a prospective value at the beginning of a
period never discounts by its last period's rate, which ``{0, last}``
still includes.

A name read through two windows in one formula writes one way per
window -- the facet's array is OpenLineage's, and one entry per way the
read was made is what it is for. The ladder still names the edge's own
narrowing and orders the ways, so a consumer reading the first entry
reads what it read before the windows were stated. An indirect read
states no window, and neither does a read of a column holding one value
per policy: it has no periods (``graph_builder.py`` drops the window
there, because the source's shape is known where the read is bound and
not here).

## What an edge alone does not say

``EngineNative`` is source text in one engine's own expression language,
and nothing here can read it. Its declared dependencies are therefore
claimed under whatever context the escape hatch itself sits in -- the only
defensible rule, since the walk cannot see which of them the text puts in
the answer and which only consulted. The consequence is worth stating
plainly rather than leaving to be discovered.

The escape hatch is reached by degradation as well as by choice. A lookup
multiplied by a number -- ``mortality.lookup(age=af.attained_age) * 2.0``
-- is emitted today as one opaque ``EngineNative``, and its key comes back
``DIRECT``/``TRANSFORMATION``: the read that only *found* the rate is
reported as a read whose value is in it. The reach of that matters more
than the example. The shipped tutorial models write their cumulative
products as raw Polars ``cum_prod()``, so the whole of the mini-VA
tutorial's edges carry no ``AGGREGATION`` at all -- the accumulation rule
is right wherever it fires, and fires on none of them.

A reader of the *node* can see the opacity: ``engines`` names the engine
the text needs, and ``period_reference`` says ``unknown``. A reader of the
edge alone cannot. That is the difference between reading a
``TRANSFORMATION`` as a claim about the read and reading it as the
strongest claim the framework was in a position to support.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, assert_never

from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    EngineNative,
    Lit,
    State,
    WhenThen,
)
from gaspatchio._semantic.join_keys import join_key_sides

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio._semantic.ir import OpNode

__all__ = [
    "AGGREGATING_CALLS",
    "AGGREGATING_METHODS",
    "EXTRACTIONS",
    "STATE_EXTRACTION",
    "Bound",
    "EdgeClass",
    "EdgeSubtype",
    "EdgeType",
    "Periods",
    "Position",
    "ReadClaim",
    "ReadWay",
    "Reference",
    "Window",
    "claim_over",
    "classify_reads",
    "extraction_of",
    "join_keys",
    "operand_windows",
    "stronger",
    "without_windows",
]

# Whether the value read flows into the result, or only decided which
# values did. Written on the edge as its ``relationship``; the name here
# stays ``type`` because that is what the vocabulary is called wherever it
# is written down verbatim, the facet included.
EdgeType = Literal["DIRECT", "INDIRECT"]

# The narrowing of the type. The first three go with DIRECT, the rest
# with INDIRECT, and the pairing is enforced by the published schema,
# where the narrowing is written: inside the facet rather than on the
# edge.
EdgeSubtype = Literal[
    "IDENTITY",
    "TRANSFORMATION",
    "AGGREGATION",
    "JOIN",
    "GROUP_BY",
    "FILTER",
    "SORT",
    "WINDOW",
    "CONDITIONAL",
]

# One read's classification: the pair an edge carries, kept together
# because neither half means anything without the other.
EdgeClass = tuple[EdgeType, EdgeSubtype]


# One end of a window: a whole number of periods from the period being
# computed, negative before it and positive after it, or one end of the run
# itself. Section 9 spells the two ends "first" and "last".
Bound = int | Literal["first", "last"]
FIRST: Final = "first"
LAST: Final = "last"


@dataclass(frozen=True, slots=True)
class Periods:
    """The periods of an operand one period of the answer can read.

    Written ``"periods": {"from": start, "to": end}`` (section 9). Each bound
    is a whole number of periods from the period being computed, or
    ``"first"`` / ``"last"`` for an end of the policy's own run: a cumulative
    sum reads ``{first, 0}``, a remaining sum ``{0, last}``, a total
    ``{first, last}``.

    Attributes:
        start: The earliest period read.
        end: The latest period read.

    """

    start: Bound
    end: Bound


@dataclass(frozen=True, slots=True)
class Position:
    """The one stored position a literal ``list.get`` reads.

    Written ``"position": k`` (section 9) and quoted as the call wrote it:
    ``0`` is the first period, ``-1`` the last (section 11.1.22). It is a
    position in the policy's own list, not a distance from the period being
    computed, which is why it is a member of its own.

    Attributes:
        index: The position the call selects.

    """

    index: int


# What a read states about where in the run it read, when it states it.
Window = Periods | Position


class ReadWay(NamedTuple):
    """One way a direct read was made: its narrowing and the window it read.

    A name read through two windows in one formula is two ways of reading
    it, and the facet writes one entry per way (section 9).

    Attributes:
        subtype: The narrowing this way of reading carries.
        window: The periods or the position it read, or ``None`` where it
            states none -- every read of the period being computed, and
            every read whose window the members cannot write.

    """

    subtype: EdgeSubtype
    window: Window | None = None


class ReadClaim(NamedTuple):
    """One read: what kind of read it was, and which periods it read.

    The three are produced by one walk and travel together, because an
    offset means nothing without the claim it sits beside: a value read at
    t-1 and a value only *consulted* at t-1 are different statements, and
    two containers is where a pair starts to drift.

    Attributes:
        edge: The two-word classification the edge and its facet carry
            between them.
        offset: The distance in periods from the row being computed --
            negative a prior period, positive a later one, the sign the
            ``projection`` accessor already uses. ``None`` wherever there
            is no distance to state, which an artifact writes as the
            field's absence rather than as a zero.
        ways: One entry per way a direct read was made, strongest
            narrowing first, wherever any of them states a window or there
            is more than one. Empty for the one-way read with no window,
            which is nearly every read: ``edge`` and ``offset`` say all of
            it, and the facet writes them as one entry.

    """

    edge: EdgeClass
    offset: int | None = None
    ways: tuple[ReadWay, ...] = ()


# What a formula can read: a column, by name, or one whole compiled
# rollforward, as the call that reads it back out. Two kinds because they
# are two kinds of thing -- a column is a name the frame answers to, and a
# compilation is a state machine no column holds -- and keeping them in one
# key space by spelling the second as a name would eventually put a
# compilation and a column of that name in the same slot.
Reference = str | Call

# The one of the three extractions below that names a running state. It
# carries the state and the point it is read at as typed attributes, so a
# column assigned one of these is a balance the compilation carries,
# materialised -- and the producer can say which balance without parsing
# anybody's formula text. The other two name a movement and a whole struct
# respectively, and neither of them names a state.
STATE_EXTRACTION: Final[str] = "rollforward.state"

# The three operations that read a compiled rollforward back out. The
# operands inside such a call are what the *compilation* reads, not what
# the node reading it does, so the walk claims the compilation and stops
# there rather than descending and claiming a growth rate on behalf of
# every line that ever pulled a state out.
EXTRACTIONS: Final[frozenset[str]] = frozenset(
    {STATE_EXTRACTION, "rollforward.increment", "rollforward.struct"}
)

IDENTITY: Final[EdgeClass] = ("DIRECT", "IDENTITY")
TRANSFORMATION: Final[EdgeClass] = ("DIRECT", "TRANSFORMATION")
AGGREGATION: Final[EdgeClass] = ("DIRECT", "AGGREGATION")
JOIN: Final[EdgeClass] = ("INDIRECT", "JOIN")
FILTER: Final[EdgeClass] = ("INDIRECT", "FILTER")
CONDITIONAL: Final[EdgeClass] = ("INDIRECT", "CONDITIONAL")
WINDOW: Final[EdgeClass] = ("INDIRECT", "WINDOW")

# The operation that repeats a per-policy value along a period axis it
# reads only the length of (section 11.1.32). Its second operand is that
# axis, and it is the only operand in this vocabulary whose values never
# reach the answer while its shape does.
_BROADCAST: Final[str] = "projection.broadcast_to_periods"

# The operations whose result is a function of every period rather than
# of the one being read, however they were called: a cumulative product,
# a prospective value, a remaining sum, a linear recurrence, and the
# internal-rate solve that consumes a whole cashflow list to return one
# number -- and a reversal, whose period t is the operand's period T-1-t.
# An operand of one of these is still in the answer -- so DIRECT
# -- but it is in every period's answer, which is what AGGREGATION says
# and TRANSFORMATION would not. See the module docstring for what each
# lowering had to do to earn its place, and which near neighbours are
# elementwise and so are not here.
AGGREGATING_CALLS: Final[frozenset[str]] = frozenset(
    {
        "cum_prod",
        "cum_sum",
        "sum",
        "mean",
        "min",
        "max",
        "projection.cumulative_survival",
        "projection.prospective_value",
        "projection.remaining_sum",
        "projection.accumulate",
        "excel.irr",
        "list.reverse",
    }
)

# The attribute a call's own choice of calculation travels on.
_METHOD: Final[str] = "method"

# The operations that accumulate under some of their methods and not
# others, with the methods that make them do it. Kept beside the set above
# rather than folded into it: a name in that set accumulates however it
# was called, a name here only sometimes does, and a reader checking why
# one edge says AGGREGATION and its neighbour says TRANSFORMATION has to
# be able to see which kind of rule answered.
AGGREGATING_METHODS: Final[dict[str, frozenset[str]]] = {
    "finance.discount_factor": frozenset({"forward"}),
}

# The call a join records for every column it brings in, and the attribute
# its keys travel in (section 11.1.2). How that attribute is spelled is
# ``gaspatchio._semantic.join_keys``'s alone: ``ActuarialFrame.join`` writes
# it there and :func:`join_keys` reads it back there, as every other reader
# of it does.
_JOIN_CALL: Final[str] = "join"
_JOIN_ON: Final[str] = "on"

# The operations an assumption-table read is recorded as: the lookup
# itself, and the convention-aware read of a mortality basis that stands
# for one. Every node argument of either is a key -- the table's identity,
# its miss policy and the mortality convention all travel as typed
# attributes, which are not nodes and are not read here.
_KEYED_READS: Final[frozenset[str]] = frozenset({"lookup", "mortality.at"})

# The attribute `projection.at_period` states its distance in. It is the
# one the executable profile's operation tree serialises, which is why the
# offset written into the artifact is quoted from here and never read back
# out of an expression's text.
_RELATIVE_PERIOD: Final[str] = "relative_period"

# The two operations whose distance is the identifier's rather than the
# call's: section 11.1.19 fixes `previous_period` at x[t-1] and
# `next_period` at x[t+1], so neither carries an attribute to quote and
# neither needs one.
_FIXED_PERIOD_SHIFTS: Final[dict[str, int]] = {
    "projection.previous_period": -1,
    "projection.next_period": 1,
}

# The one whose distance is written per call, in `relative_period`.
_STATED_PERIOD_SHIFT: Final[str] = "projection.at_period"

# Strongest claim about the value first. TRANSFORMATION beats AGGREGATION
# because a column multiplied into this period's number says more about
# this period than one folded into every period's; both beat IDENTITY,
# which is only ever the whole of a formula and so never contests
# anything; and every DIRECT claim beats all INDIRECT ones, because a
# value that is in the number is in the number however else it was also
# used.
#
# That last clause is about two *separate* reads of one name, which is
# what `_claim` settles. Within a single read the indirect/direct question
# is answered first and the other way round -- a value consulted only in a
# test does not join the answer by being accumulated on the way -- and
# only then does this ranking decide. `_narrowed` is where that order is
# written down.
#
# WINDOW is last: a column read only as the axis a value is repeated along
# contributed its length and nothing else, which is the least a read can
# say about the number -- a column that also chose a branch, or selected a
# position, said more.
_STRENGTH: Final[tuple[EdgeClass, ...]] = (
    TRANSFORMATION,
    AGGREGATION,
    IDENTITY,
    JOIN,
    FILTER,
    CONDITIONAL,
    WINDOW,
)
_RANK: Final[dict[EdgeClass, int]] = {
    claim: rank for rank, claim in enumerate(_STRENGTH)
}


def extraction_of(node: OpNode) -> Call | None:
    """Return the call reading a compiled rollforward, or None for anything else.

    One place answers this, because two places answering it would
    eventually disagree about which shape is a read of a compilation --
    and the walk that classifies reads and the fold that mints nodes for
    them have to agree exactly, or a node's edges and its ``reads`` come
    apart.

    Args:
        node: The op-tree node to test.

    Returns:
        The call, where ``node`` is one; None otherwise.

    """
    if isinstance(node, Call) and node.name in EXTRACTIONS:
        return node
    return None


def join_keys(node: OpNode) -> tuple[str, ...]:
    """Return the columns a join matched an arriving column on, in the order given.

    A column a join brought in holds whichever row of the other table its
    key matched, so the key decides its value: change a policy's product
    code and its expense loading is another row's. That makes the key a
    read of the arriving column -- ``INDIRECT``/``JOIN``, the pair a
    lookup key carries, because it selects the row rather than being
    arithmetic on it -- and it is what lets "what moves if this key is
    restated?" reach every column the join brought in, and everything
    downstream of them.

    The key travels on the record as the call's ``on`` attribute rather
    than as an operand, so it is read back out of that attribute here, in
    one place: the walk that binds a node's ``reads`` and the walk that
    classifies them both ask this, and the two have to agree exactly or a
    node's edges and its reads come apart.

    **The left side's keys, never the right side's.** Those are the
    columns on this frame, bound to the definitions they held when the
    join ran; the right side's names are the other table's, and it travels
    as an entry of its own. A cross join states no key -- every row is
    paired with every row -- so what it brings in reads nothing.

    The attribute is one flat string, so a key whose own name contains a
    comma or an equals sign could not be told from two keys; the frame
    refuses such a name before the join, and this reads the string exactly
    as section 11.1.2's grammar states it, trimming nothing.

    Args:
        node: The op-tree node to read.

    Returns:
        The key columns, where ``node`` is a join's record; empty for
        anything else, and for a join that states no key.

    Examples:
        >>> from gaspatchio._semantic.ir import Call
        >>> join_keys(Call("join", (), (("on", "product_code,issue_age"),)))
        ('product_code', 'issue_age')
        >>> join_keys(Call("join", (), (("on", "pol_num=policy_id"),)))
        ('pol_num',)
        >>> join_keys(Call("join", (), (("on", None),)))
        ()

    """
    if not isinstance(node, Call) or node.name != _JOIN_CALL:
        return ()
    return join_key_sides(dict(node.attrs).get(_JOIN_ON))[0]


def stronger(held: ReadClaim, candidate: ReadClaim) -> ReadClaim:
    """Return the stronger claim of two reads of one thing.

    The ladder :data:`_STRENGTH` states, offered to a caller that has
    resolved two of this module's references to one node and needs the
    same answer :func:`classify_reads` would have given had they been one
    reference: what the edge answers is "is this value in the number?",
    and one read that puts it there settles it.

    The offset is settled the other way round, and by agreement rather
    than by rank. Two reads of one node at one distance were both at that
    distance; two at different distances leave the edge standing for both,
    and it states no period rather than half of one. The windows are kept
    whole: each direct way either read was made is a way the node was read.
    """
    edge = held.edge if _RANK[held.edge] <= _RANK[candidate.edge] else candidate.edge
    agreed = held.offset if held.offset == candidate.offset else None
    return _finished(edge, agreed, (*_ways_of(held), *_ways_of(candidate)))


def claim_over(edge: EdgeClass, windows: tuple[Window | None, ...]) -> ReadClaim:
    """Return a direct read of ``edge`` made once over each of ``windows``.

    For a caller that knows the windows a read was made over without a
    formula to walk: a compiled rollforward's operand columns, each read
    over the run the recurrence has covered.

    Examples:
        >>> claim_over(AGGREGATION, (Periods("first", 0),)).ways
        (ReadWay(subtype='AGGREGATION', window=Periods(start='first', end=0)),)
        >>> claim_over(AGGREGATION, (None,)) == ReadClaim(AGGREGATION)
        True

    """
    return _finished(edge, None, tuple(ReadWay(edge[1], window) for window in windows))


def without_windows(claim: ReadClaim) -> ReadClaim:
    """Return ``claim`` stating no window, for a source with no periods.

    A column holding one value per policy is read the same whichever period
    of the answer reads it, so a window would state periods it does not
    have. The caller knows the source's shape, and this does not.
    """
    if not claim.ways:
        return claim
    bare = tuple(ReadWay(way.subtype) for way in claim.ways)
    return _finished(claim.edge, claim.offset, bare)


def classify_reads(node: OpNode) -> dict[Reference, ReadClaim]:
    """Return, per thing the tree reads, how it is read.

    One pre-order walk carrying the context it is in -- inside a
    conditional's test, inside a lookup's keys, inside an accumulating
    operation -- and one entry per distinct column name, holding the
    strongest claim any of that name's reads supports:
    ``DIRECT``/``TRANSFORMATION`` beats ``DIRECT``/``AGGREGATION`` beats
    ``DIRECT``/``IDENTITY`` beats ``INDIRECT``/``JOIN`` beats
    ``INDIRECT``/``FILTER`` beats ``INDIRECT``/``CONDITIONAL`` beats
    ``INDIRECT``/``WINDOW``. See the
    module docstring for why the strongest wins and how the contexts nest.

    A direct read also carries the window it read, and a name read through
    two windows carries both (see the module docstring).

    A tree that is one bare column reference is the identity case in
    full: a rename or a plain copy, where the value arrives unchanged.
    Nothing else produces ``IDENTITY``, because nothing else leaves the
    value alone.

    A read of a compiled rollforward is claimed as the extraction call
    itself rather than as the columns inside it, and the walk does not
    descend past one. Those columns are what the *compilation* reads;
    claiming them here would put a growth rate in the lineage of every
    line that ever pulled a state out of the same state machine.

    Args:
        node: The formula to classify, as the op-tree recorded for it.

    Returns:
        Each thing the tree reads, mapped to its classification: a column
        by name, and a compiled rollforward as the call that reads it.
        **This is not the set ``col_refs`` reports.** That function still
        descends into an extraction, because those columns are the ones
        the kernel needs the frame to supply; this one stops there,
        because they are not what the node reading the compilation read.

    Examples:
        >>> from gaspatchio._semantic.ir import Call, Col
        >>> survival = Call(
        ...     "projection.cumulative_survival",
        ...     (Col("qx"),),
        ...     (("start_at", 1.0), ("from_survival", False)),
        ... )
        >>> classify_reads(survival)["qx"].ways
        (ReadWay(subtype='AGGREGATION', window=Periods(start='first', end=-1)),)

    """
    if isinstance(node, Col):
        return {node.name: ReadClaim(IDENTITY)}
    found: dict[Reference, _Reading] = {}
    _classify(node, TRANSFORMATION, found, 0, _NOW)
    return {
        reference: _finished(reading.edge, reading.offset, tuple(reading.ways))
        for reference, reading in found.items()
    }


def operand_windows(operand: OpNode) -> dict[str, tuple[Window | None, ...]]:
    """Return the windows a compiled rollforward reads each column of one operand over.

    A rollforward is a linear recurrence run forward, so period ``t`` of
    every state reads its operands from the first period to ``t`` --
    ``{first, 0}``, the window ``projection.accumulate`` states -- and an
    operand built from other operations reads its columns through them, by
    the same walk a formula's reads take.

    Args:
        operand: One operand of the compilation, in the op-tree's
            vocabulary.

    Returns:
        Each column the operand names, with the windows it is read over:
        ``None`` among them where a read states none.

    Examples:
        >>> from gaspatchio._semantic.ir import Col
        >>> operand_windows(Col("growth"))
        {'growth': (Periods(start='first', end=0),)}

    """
    found: dict[Reference, _Reading] = {}
    _classify(operand, AGGREGATION, found, 0, _FIRST_TO_NOW)
    return {
        reference: tuple(way.window for way in reading.ways) or (None,)
        for reference, reading in found.items()
        if isinstance(reference, str)
    }


def _stated(claim: ReadClaim) -> ReadClaim:
    """Return ``claim`` carrying an offset only where stating one is a claim.

    Three reads in four are of the period being computed, and the absence
    is the statement: a zero would be a second spelling of the same fact,
    and a consumer would then have two shapes to recognise for one thing.

    The other two droppings are about what the claim underneath will
    hold. A read the walk could not pin to one period is not a read at
    one period. And an offset says which period a *value* came from, so
    it goes only with the narrowing that says a value came at all: a
    lookup key, a conditional's test and an operand folded across the
    whole run are none of them a value narrowed by a distance.
    """
    if claim.edge != TRANSFORMATION or claim.offset in {None, 0}:
        return ReadClaim(claim.edge, None, claim.ways)
    return claim


def _ways_of(claim: ReadClaim) -> tuple[ReadWay, ...]:
    """Return every direct way ``claim`` stands for, the one-way read included."""
    if claim.ways:
        return claim.ways
    if claim.edge[0] == "DIRECT":
        return (ReadWay(claim.edge[1]),)
    return ()


def _finished(
    edge: EdgeClass, offset: int | None, ways: tuple[ReadWay, ...]
) -> ReadClaim:
    """Return the claim one name's reads add up to, its ways in their order.

    The ways are the direct ones, each stated once in the order the formula
    first made it and then put in the ladder's order, so the strongest
    narrowing -- the edge's own -- comes first. A read whose only way is
    its edge's own narrowing with no window says everything in ``edge``
    and ``offset``, and carries no ways at all: that is the shape nearly
    every read has, and the shape it had before windows were stated.
    """
    if edge[0] != "DIRECT":
        return _stated(ReadClaim(edge, offset))
    distinct = tuple(dict.fromkeys(ways))
    ordered = tuple(sorted(distinct, key=lambda way: _RANK[("DIRECT", way.subtype)]))
    if ordered == (ReadWay(edge[1]),):
        ordered = ()
    return _stated(ReadClaim(edge, offset, ordered))


def _classify(
    node: OpNode,
    context: EdgeClass,
    found: dict[Reference, _Reading],
    period: int,
    reach: _Reach,
) -> None:
    """Walk ``node`` in pre-order, claiming each read under ``context``.

    ``period`` is how far from the row being computed this subtree is
    read, which only a period shift moves: it is carried down beside the
    context because both are facts about the position a read sits in
    rather than about the read itself. ``reach`` is the same fact widened
    to a window -- where in the run the subtree is read, which an
    accumulation and a literal position move as well -- and ``None`` once
    the two members could not write it exactly.

    The final ``case`` is unreachable for any real ``OpNode``; it exists
    so that adding an eighth node type to the union without teaching this
    walk what kind of read it makes fails the type checkers, rather than
    silently classifying the new node's operands as ordinary ones.
    """
    if (extraction := extraction_of(node)) is not None:
        # The compilation is the read; what is inside the call is what the
        # compilation reads, and belongs to its own node.
        _claim(found, extraction, context, period, reach)
        return
    match node:
        case Col(name=name):
            _claim(found, name, context, period, reach)
        case EngineNative(deps=deps):
            # The text is opaque, so its declared dependencies are read
            # under whatever context the escape hatch itself sits in -- and
            # over no window anyone can state.
            for dep in deps:
                _claim(found, dep, context, period, None)
        case BinOp(left=left, right=right):
            _classify(left, context, found, period, reach)
            _classify(right, context, found, period, reach)
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            _classify(cond, _narrowed(context, CONDITIONAL), found, period, reach)
            _classify(then, context, found, period, reach)
            _classify(otherwise, context, found, period, reach)
        case Call() as call:
            _classify_call(call, context, found, period, reach)
        case Lit() | State():
            pass
        case _ as unreachable:
            assert_never(unreachable)


def _classify_call(
    call: Call,
    context: EdgeClass,
    found: dict[Reference, _Reading],
    period: int,
    reach: _Reach,
) -> None:
    """Separate an operand from the one beside it that is read differently.

    Three operations hold operands that are not read the way their
    siblings are. A selection's position only chooses a value and is not
    part of it. A broadcast's axis gives the result its length and none of
    its values: ``rate.projection.broadcast_to_periods(like=af.policy_year)``
    holds the rate in every cell whatever the policy years were, so a
    ``DIRECT`` claim on ``policy_year`` would put it in the impact cone of
    every number the rate reaches. A period shift's value comes from
    another period and its fill does not: the fill is what stands at the
    boundary the shift runs off, in the period being computed, so carrying
    the distance into it would put a t-1 on a column nobody read at t-1.

    And one reads a column that is no operand at all: a join's key, named
    in its ``on`` attribute (:func:`join_keys`), which selected the row the
    arriving column holds.

    An accumulating operation reads each operand over the window its own
    identifier and attributes fix (:func:`_operand_windows`), and a literal
    ``list.get`` reads its list at the one position it names, whichever
    period of the answer is being computed.
    """
    for key in join_keys(call):
        _claim(found, key, _narrowed(context, JOIN), period, reach)
    match call:
        case Call(name="list.get", args=(values, index)):
            _classify(values, context, found, period, _selected(index))
            _classify(index, _narrowed(context, FILTER), found, period, reach)
            return
        case Call(name=name, args=(value, axis)) if name == _BROADCAST:
            _classify(value, context, found, period, reach)
            _classify(axis, _narrowed(context, WINDOW), found, period, reach)
            return
    shift = _period_shift(call)
    if shift is not None and call.args:
        value, *fill = call.args
        _classify(value, context, found, period + shift, _shifted(reach, shift))
        for operand in fill:
            _classify(operand, context, found, period, reach)
        return
    inner = _call_context(context, call)
    if not _accumulates(call):
        for arg in call.args:
            _classify(arg, inner, found, period, reach)
        return
    windows = _operand_windows(call)
    for at, arg in enumerate(call.args):
        window = windows[at] if at < len(windows) else None
        _classify(arg, inner, found, period, _through(reach, window))


# Where in the run a subtree is read, relative to the period being
# computed: a span of periods, a literal position, or None once the two
# members cannot write it exactly. A read of the period being computed is
# the span from 0 to 0.
_Reach = Periods | Position | None
_NOW: Final[Periods] = Periods(0, 0)
_FIRST_TO_NOW: Final[Periods] = Periods(FIRST, 0)
_BEFORE_NOW: Final[Periods] = Periods(FIRST, -1)
_NOW_TO_LAST: Final[Periods] = Periods(0, LAST)
_WHOLE_RUN: Final[Periods] = Periods(FIRST, LAST)

# The attributes the windows are quoted from. The four reductions of
# 11.1.14-11.1.17 need none -- they answer one number per policy -- and
# nor does a reversal, whose period t reads the operand's T-1-t, which no
# fixed distance and no fixed end can write (11.1.41), so it states the
# whole run, the bound the members can.
_REVERSE: Final[str] = "reverse"
_START_AT: Final[str] = "start_at"
_DISCOUNT_KIND: Final[str] = "discount_kind"


def _operand_windows(call: Call) -> tuple[Periods | None, ...]:
    """Return the window each operand of an accumulating ``call`` is read over.

    One entry per operand, quoted from the identifier and its own
    attributes (section 11) and never from an expression's text --
    :data:`_WINDOWS` is section 9's table, an identifier to the rule its
    clause fixes. ``None`` for an operand the call reads over no window the
    members can write: the opening value of a recurrence, the guess of a
    solve, the period operand a forward discount factor records and never
    reads -- and any call whose deciding attribute is missing or not one the
    clause states.
    """
    rule = _WINDOWS.get(call.name)
    if rule is None:
        return ()
    return rule(dict(call.attrs))


def _scan_windows(attrs: dict[str, object]) -> tuple[Periods | None, ...]:
    """11.1.9: period t is the fold of 0..t, or of t..n-1 under reverse.

    The direction is always on the record, so a tree without one is not
    guessed at.
    """
    return (_by_direction(attrs.get(_REVERSE)),)


def _survival_windows(attrs: dict[str, object]) -> tuple[Periods | None, ...]:
    """11.1.19: c[t] folds 0..t; under start_at period t is c[t-1], folding 0..t-1."""
    if _START_AT not in attrs:
        return (None,)
    return (_FIRST_TO_NOW if attrs[_START_AT] is None else _BEFORE_NOW,)


def _recurrence_windows(attrs: dict[str, object]) -> tuple[Periods | None, ...]:
    """11.1.20: s[t] = s[t-1] * m[t] + a[t], or run back from the last period.

    A document written before ``reverse`` was stated carries none, and its
    recurrence is the forward one. The opening value is where the run
    starts and is read over no window.
    """
    step = _by_direction(attrs.get(_REVERSE, False))
    return (None, step, step)


def _prospective_windows(attrs: dict[str, object]) -> tuple[Periods | None, ...]:
    """11.1.21: period t sums cashflows t..T-1 and discounts by rates t..T-1.

    The clause states the rate form; a factor form's discount is outside
    it, and states nothing.
    """
    rate = _NOW_TO_LAST if attrs.get(_DISCOUNT_KIND) == "rate" else None
    return (_NOW_TO_LAST, rate)


def _whole_run(_attrs: dict[str, object]) -> tuple[Periods | None, ...]:
    """11.1.14-11.1.17 and 11.1.41: one list operand, read over the whole run."""
    return (_WHOLE_RUN,)


def _irr_windows(_attrs: dict[str, object]) -> tuple[Periods | None, ...]:
    """11.1.36: one rate per policy, solved over the whole stream; a guess has none."""
    return (_WHOLE_RUN, None)


def _suffix_windows(_attrs: dict[str, object]) -> tuple[Periods | None, ...]:
    """11.1.20: the remaining sum at t is the sum of t..T-1."""
    return (_NOW_TO_LAST,)


def _forward_discount_windows(_attrs: dict[str, object]) -> tuple[Periods | None, ...]:
    """11.1.30 under forward: d[t] is the product of 1/(1+r[u]) over u=0..t-1.

    Only the forward method accumulates (:data:`AGGREGATING_METHODS`), and
    the period operand supplies nothing under it.
    """
    return (_BEFORE_NOW, None)


# Section 9's table: each accumulating identifier, and the rule that quotes
# the windows its operands are read over from its own attributes.
_WINDOWS: Final[
    dict[str, Callable[[dict[str, object]], tuple[Periods | None, ...]]]
] = {
    "cum_prod": _scan_windows,
    "cum_sum": _scan_windows,
    "sum": _whole_run,
    "mean": _whole_run,
    "min": _whole_run,
    "max": _whole_run,
    "list.reverse": _whole_run,
    "excel.irr": _irr_windows,
    "projection.cumulative_survival": _survival_windows,
    "projection.accumulate": _recurrence_windows,
    "projection.remaining_sum": _suffix_windows,
    "projection.prospective_value": _prospective_windows,
    "finance.discount_factor": _forward_discount_windows,
}


def _by_direction(reverse: object) -> Periods | None:
    """Return a fold's window for the direction it ran in, or None for no direction."""
    if reverse is False:
        return _FIRST_TO_NOW
    if reverse is True:
        return _NOW_TO_LAST
    return None


def _selected(index: OpNode) -> _Reach:
    """Return where a ``list.get`` reads its list: the literal position, or None.

    A position held in a column differs by policy, so it is no one
    position to state; the read is still a selection, and says nothing
    about where.
    """
    if isinstance(index, Lit):
        value = index.value
        if isinstance(value, int) and not isinstance(value, bool):
            return Position(value)
    return None


def _moved(bound: Bound, by: int) -> Bound | None:
    """Return ``bound`` moved ``by`` periods, or None where no bound writes it.

    An end of the run stays put only where moving it walks off the run --
    the first period moved back, the last moved on -- because there is no
    period there to read. Moved the other way it would name a period the
    two ends cannot, and stating the end anyway would claim a period the
    read never reached.
    """
    if not isinstance(bound, str):
        return bound + by
    if (bound == FIRST and by <= 0) or (bound == LAST and by >= 0):
        return bound
    return None


def _shifted(reach: _Reach, by: int) -> _Reach:
    """Return ``reach`` read ``by`` periods away, as a period shift reads it."""
    if not isinstance(reach, Periods):
        return None
    start = _moved(reach.start, by)
    end = _moved(reach.end, by)
    if start is None or end is None:
        return None
    return Periods(start, end)


def _through(reach: _Reach, window: Periods | None) -> _Reach:
    """Return where an operand is read, reached through ``window`` from ``reach``.

    Each period the accumulation's own answer is read at reads its operand
    over ``window``, so the operand's reach is the window laid over every
    period of ``reach``: an end of the run in the window is that end, and a
    distance moves the matching end of ``reach``. Under a literal position
    the window is laid over that one period, which is an end of the run
    only where it lands on one.
    """
    if reach is None or window is None:
        return None
    if isinstance(reach, Position):
        start = _bound_at(reach.index, window.start)
        end = _bound_at(reach.index, window.end)
    else:
        start = (
            window.start
            if isinstance(window.start, str)
            else _moved(reach.start, window.start)
        )
        end = (
            window.end if isinstance(window.end, str) else _moved(reach.end, window.end)
        )
    if start is None or end is None:
        return None
    return Periods(start, end)


def _bound_at(index: int, bound: Bound) -> Bound | None:
    """Return ``bound`` laid over the period position ``index`` names."""
    if isinstance(bound, str):
        return bound
    landed = index + bound
    if index >= 0 and landed <= 0:
        return FIRST
    if index < 0 and landed >= -1:
        return LAST
    return None


def _period_shift(call: Call) -> int | None:
    """Return how far from this period ``call`` reads its value, or None.

    None for every operation that reads the period being computed, which
    is all but the three. A ``relative_period`` that is not a whole number
    is not a distance this walk can quote, and it says nothing rather than
    inventing one -- the lowering refuses the same value, so an artifact
    reaching here with one is already a file that will not run.
    """
    fixed = _FIXED_PERIOD_SHIFTS.get(call.name)
    if fixed is not None:
        return fixed
    if call.name != _STATED_PERIOD_SHIFT:
        return None
    stated = dict(call.attrs).get(_RELATIVE_PERIOD)
    if isinstance(stated, bool) or not isinstance(stated, int):
        return None
    return stated


def _call_context(context: EdgeClass, call: Call) -> EdgeClass:
    """Return the context one operation's operands are read under.

    Two kinds of operation narrow it: a read of an assumption base, whose
    every node argument is a key, and an accumulating one, whose operands
    are folded across the period axis. Every other operation leaves the
    context alone -- an operand of an ordinary accessor call is an ordinary
    operand, and one buried inside a lookup key or a conditional's test is
    still part of the key or the test.
    """
    if call.name in _KEYED_READS:
        return _narrowed(context, JOIN)
    if _accumulates(call):
        return _narrowed(context, AGGREGATION)
    return context


def _accumulates(call: Call) -> bool:
    """Return whether ``call`` folds its operands across the period axis.

    The name answers it for an operation that accumulates however it was
    called. For the ones whose own method chooses between two different
    calculations, the method decides -- it is on the node as a typed
    attribute, so nothing here has to escalate the call name and report an
    elementwise result as an accumulation. A node carrying no method at all
    is not one of those calculations, and says so.
    """
    if call.name in AGGREGATING_CALLS:
        return True
    accumulating = AGGREGATING_METHODS.get(call.name)
    if accumulating is None:
        return False
    return dict(call.attrs).get(_METHOD) in accumulating


def _narrowed(context: EdgeClass, candidate: EdgeClass) -> EdgeClass:
    """Return the context to read a subtree under, entering ``candidate``.

    One ladder, and it is :data:`_STRENGTH`. An indirect context absorbs a
    direct one nested inside it: a column consulted only inside a
    conditional's test does not put its value into the answer by being
    accumulated on the way there, and a lookup key does not stop being a
    key because the rate it found is then summed. Nothing absorbs in the
    other direction -- entering a test, or a lookup's keys, from an
    ordinary operand position is what makes a read indirect at all. What is
    left is two indirect contexts, and the stronger of them wins, so
    nesting order decides nothing: a lookup key inside a conditional's test
    and a conditional's test inside a lookup key are both ``JOIN``.
    """
    if context[0] == "DIRECT":
        return candidate
    if candidate[0] == "DIRECT":
        return context
    return context if _RANK[context] < _RANK[candidate] else candidate


@dataclass(slots=True)
class _Reading:
    """What one walk has found about one name so far."""

    edge: EdgeClass
    offset: int | None
    ways: list[ReadWay]


def _claim(
    found: dict[Reference, _Reading],
    reference: Reference,
    candidate: EdgeClass,
    period: int,
    reach: _Reach,
) -> None:
    """Record ``candidate`` for ``reference``, keeping the stronger of the two.

    The period is kept only while every read of the name agrees on it. A
    column read at t-1 and again at t was read at both, and one edge
    stands for both reads: a file saying t-1 there would be a narrower
    claim than the formula supports, so it states no period at all.

    A direct read also records the way it was made, with its window, so
    that a name read through two windows states both.
    """
    way = _way(candidate, reach)
    held = found.get(reference)
    if held is None:
        found[reference] = _Reading(candidate, period, [] if way is None else [way])
        return
    if _RANK[candidate] < _RANK[held.edge]:
        held.edge = candidate
    if held.offset != period:
        held.offset = None
    if way is not None:
        held.ways.append(way)


def _way(candidate: EdgeClass, reach: _Reach) -> ReadWay | None:
    """Return the direct way one read was made, with the window it states.

    ``periods`` goes with ``AGGREGATION`` and ``position`` with either
    direct narrowing that reads a value: a literal ``list.get`` reads one
    stored position whether its answer is then multiplied in or folded. A
    read of the period being computed states neither, the offset being the
    only period fact such a read has. An indirect read states none.
    """
    if candidate[0] != "DIRECT":
        return None
    if isinstance(reach, Position):
        return ReadWay(candidate[1], reach)
    if candidate == AGGREGATION and isinstance(reach, Periods):
        return ReadWay(candidate[1], reach)
    return ReadWay(candidate[1])
