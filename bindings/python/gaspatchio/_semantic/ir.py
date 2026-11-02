# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The semantic op-tree: a closed, engine-free intermediate representation.

Every formula gaspatchio evaluates -- ``af.claims = af.sum_assured *
af.pols_death``, a ``when/then/otherwise`` conditional, a rollforward
state read, an escape-hatch call into one engine's own expression
language -- reduces to one of the seven node types defined here: ``Col``,
``Lit``, ``BinOp``, ``Call``, ``WhenThen``, ``State``, and
``EngineNative``. ``OpNode`` is the closed union of exactly those seven;
nothing outside this module adds an eighth.

This module knows nothing about how a node gets evaluated. It has no
Polars import and no dependency on the rest of the framework beyond the
standard library: node construction, structural equality, and the two
traversal functions below (``walk``, ``col_refs``) are the entire
surface. Lowering a node to a Polars expression, a JAX trace, or plain
Python is separate machinery that reads this vocabulary -- it does not
belong to it, and the Polars lowering lives in
``gaspatchio.frame.lowering``. Keeping that split sharp is what makes
the tree auditable: the op-tree is *what* a formula means, independent
of *how* any one engine computes it.

Every node type is a frozen dataclass, so equality and hashing are
structural (two nodes built from the same values are the same node),
and every node works as a dict key or a set member with no extra code.

``Lit`` carries either one scalar or a sequence of them. A band of age
boundaries, a schedule of loadings, a set of product codes -- an actuary
writes those into a formula the same way they write a number into one,
and the tree holds the values rather than handing the whole sequence to
an engine to keep. What it holds is what identifies it, which is the
point: the engine's own display of a long sequence abbreviates the
middle away, so two bands differing only there were indistinguishable
while the tree could not see inside them.

``Lit`` additionally rejects a non-finite float (NaN, +infinity,
-infinity) at construction -- inside a sequence as well as on its own,
naming the position: a non-finite number baked into a formula is a bug
in whatever upstream calculation produced it, not a value the op-tree
should carry forward silently.

Three modules in this repository are named for an intermediate
representation; ``spec/graph-artifact/README.md``, under "Three modules
named for an intermediate representation", tells them apart, and the
question answered here is what a formula means, before any engine has been
chosen to compute it.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, assert_never

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True)
class Col:
    """A reference to a column on the frame, by name."""

    name: str


# What a literal may hold, one value at a time. Named so that the
# sequence form below states the same vocabulary rather than respelling
# it, and so a caller building a literal can annotate what it is passing.
#
# A date is a literal's whole payload and never a member of a sequence, so
# the two types are separate rather than one type used twice. The boundary
# is real and it is one the byte grammar cannot state for itself: the moment
# the scalar encoder learns the date tag, a tuple of dates becomes hashable
# as a sequence of them -- while the wire has no way to spell one, since a
# literal carries its date under its own key and a sequence has no such key
# to give a member. Left as one type, the tree would accept a shape the wire
# cannot write, and the inconsistency would surface only when some producer
# path minted one.
LitScalar = float | int | bool | str | datetime.date
LitSequenceMember = float | int | bool | str


def non_finite_literal_message(value: float, where: str) -> str:
    """Explain that a literal is not finite, and where in a sequence it sits.

    ``where`` is empty for a literal that is one value on its own, and
    names the position for one buried in a sequence. The value is named
    bare rather than dressed as a node: a member of a sequence is not a
    node in its own right, and ``Lit(nan)`` would name one the tree never
    built.
    """
    return (
        f"{value!r} is not finite{where}: NaN and infinite "
        "floats are not valid formula literals -- this is a bug, "
        "not a value. Fix the upstream calculation that produced it."
    )


def _an_instant_is_not_a_date(value: datetime.datetime) -> str:
    """Explain that a datetime is not a date in this grammar.

    ``datetime.datetime`` is a subclass of ``datetime.date`` in Python, so a
    producer testing for a date first would encode an instant as its calendar
    day and lose the time without a word. The refusal is what stops that, and
    it says which of the two the author is holding.
    """
    return (
        f"{value!r} is an instant and not a calendar date: this grammar has a "
        "tag for a date -- a count of whole days -- and none for a time of "
        "day, so encoding this would silently drop everything below the day "
        "and hash as a different value than it holds. Write the instant onto "
        "the frame as a column of its own and compare against the column, or "
        "pass the calendar date with .date() if the day is what the "
        "calculation means."
    )


def _a_date_is_not_a_member(value: datetime.date, position: int) -> str:
    """Explain that a date may be a literal but not a member of a sequence."""
    return (
        f"{value!r} is not a valid member of a sequence literal at position "
        f"{position}: a date is a literal on its own in this grammar and not "
        "a member of a band. A membership test against a set of dates stays "
        "an engine fragment and the node says so; write the dates onto the "
        "frame as a column and test against the column if the calculation "
        "should be in the record."
    )


@dataclass(frozen=True)
class Lit:
    """A literal embedded directly in a formula: one scalar, or a sequence.

    The sequence form is held as a tuple so the node stays frozen and
    hashable, and so two literals written with the same values are one
    node however the author spelled the container.

    Raises:
        ValueError: If ``value`` is a non-finite float (NaN, +infinity,
            or -infinity), or holds one -- see the module docstring.
        TypeError: If ``value`` is an instant, or is a sequence holding a
            date. A date is a calendar day in this grammar and an instant
            is not one; a date is a literal's whole payload and not a
            member of a band.

    """

    value: LitScalar | tuple[LitSequenceMember, ...]

    def __post_init__(self) -> None:
        """Reject a non-finite float payload; every other value is valid.

        A sequence is checked member by member and the refusal names the
        position: a boundary that arrived as NaN is the same upstream bug
        wherever in the band it sits, and finding it by eye is not work
        the message should leave to the reader.

        ``Lit`` has no column context to name here -- that context lives
        in the traceback at the assignment site that constructed this
        node, not in this exception.
        """
        if isinstance(self.value, datetime.datetime):
            raise TypeError(_an_instant_is_not_a_date(self.value))
        if isinstance(self.value, tuple):
            for position, member in enumerate(self.value):
                if isinstance(member, float) and not math.isfinite(member):
                    msg = non_finite_literal_message(member, f" at position {position}")
                    raise ValueError(msg)
                if isinstance(member, datetime.date):
                    raise TypeError(_a_date_is_not_a_member(member, position))
        elif isinstance(self.value, float) and not math.isfinite(self.value):
            msg = non_finite_literal_message(self.value, "")
            raise ValueError(msg)


# The closed operator vocabulary a BinOp may carry: seven arithmetic, six
# comparison, two logical. Named so that emission and lowering can annotate
# an operator argument precisely instead of widening it to ``str``.
BinOpKind = Literal[
    "add",
    "sub",
    "mul",
    "div",
    "floordiv",
    "mod",
    "pow",
    "lt",
    "le",
    "gt",
    "ge",
    "eq",
    "ne",
    "and",
    "or",
]


@dataclass(frozen=True)
class BinOp:
    """A binary operation over two child nodes."""

    op: BinOpKind
    left: OpNode
    right: OpNode


# A Call attribute's value stays typed -- an offset of -1 is stored as
# the int -1, never stringified to "-1". Lowering code reading attrs
# back out relies on this: it is what lets a Polars kwarg or a JAX
# static argument round-trip without a parsing step.
#
# A date is deliberately NOT admitted here, though the byte grammar encodes
# one in this position perfectly well: an attribute and a literal share one
# scalar block and one encoder, so section 12.1's tag reaches both. What
# stops a date arriving is that no identifier's signature puts one here --
# a projection's valuation_date is text, an ISO date, and stays text, since
# the signature says so and moving it would move every projection's digest
# to say what the schedule already says. Widening the alias ahead of a
# signature that wants one would put a date in front of every site that
# reads an attribute back as a number, and there are four of those. A
# signature that wants a real date widens this and fixes them together.
AttrValue = str | int | float | bool | None


@dataclass(frozen=True)
class Call:
    """A named operation applied to one or more child-node arguments.

    ``attrs`` carries the call's non-node keyword configuration (e.g. an
    ``at_period`` offset, a rounding precision) as typed values, not
    node children -- they play no part in ``walk`` or ``col_refs``.

    **Unlike ``Lit``, this validates nothing at construction**, and a
    non-finite attribute is refused one step earlier, at the emission door
    in ``_authoring/emit.py``. The two places are not interchangeable:
    the canonical encoding has to stay total over everything ``AttrValue``
    admits, including the NaN and the two infinities, because an encoder
    that raised on a node somebody had already built would turn a
    fingerprint into a second validator with its own opinion. Refusing the
    value where the author wrote it, and encoding whatever a node
    nonetheless holds, is one rule kept in the right place rather than two
    rules in two.
    """

    name: str
    args: tuple[OpNode, ...]
    attrs: tuple[tuple[str, AttrValue], ...] = ()


@dataclass(frozen=True)
class WhenThen:
    """A conditional: ``cond`` selects between ``then`` and ``otherwise``."""

    cond: OpNode
    then: OpNode
    otherwise: OpNode


@dataclass(frozen=True)
class State:
    """A reference to a named rollforward state, not a column on the frame."""

    name: str


# The engines a fragment of escape-hatch text can be written for. Named
# rather than spelled inline so that anything annotating a node with the
# engines it needs -- the calculation graph does -- states the same closed
# vocabulary instead of widening it to ``str`` and drifting from it.
EngineName = Literal["polars", "jax", "python"]


@dataclass(frozen=True)
class EngineNative:
    """An escape hatch: source text in one engine's own expression language.

    ``deps`` declares the column names ``text`` reads. ``text`` is
    opaque outside the named ``engine``, so ``col_refs`` cannot parse it
    and relies on this declaration instead.
    """

    engine: EngineName
    text: str
    deps: tuple[str, ...]


# The closed node vocabulary: every OpNode is exactly one of these seven
# types -- never a subclass of one, and never an eighth kind defined
# elsewhere.
OpNode = Col | Lit | BinOp | Call | WhenThen | State | EngineNative


def walk(node: OpNode) -> Iterator[OpNode]:
    """Yield ``node`` and every descendant, in pre-order.

    The node comes first, then its children in field order: ``BinOp``
    yields ``left`` before ``right``; ``Call`` yields each of ``args``
    in call order; ``WhenThen`` yields ``cond``, then ``then``, then
    ``otherwise``. ``Col``, ``Lit``, ``State``, and ``EngineNative`` are
    leaves -- they have no ``OpNode`` children to descend into.

    The final ``case`` is unreachable for any real ``OpNode``; it exists
    so that adding an eighth node type to the union without teaching
    this function how to walk it fails mypy/pyright, rather than
    silently under-walking the new node at runtime.
    """
    yield node
    match node:
        case BinOp(left=left, right=right):
            yield from walk(left)
            yield from walk(right)
        case Call(args=args):
            for arg in args:
                yield from walk(arg)
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            yield from walk(cond)
            yield from walk(then)
            yield from walk(otherwise)
        case Col() | Lit() | State() | EngineNative():
            pass
        case _ as unreachable:
            assert_never(unreachable)


def col_refs(node: OpNode) -> tuple[str, ...]:
    """Return every column name ``node`` reads, first occurrence first.

    Collects ``Col.name`` and each entry of ``EngineNative.deps`` while
    walking ``node`` in pre-order, de-duplicating so a name that recurs
    keeps only its first position. ``State`` names are excluded: a
    rollforward state reference is not a column the frame needs to
    supply.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for current in walk(node):
        match current:
            case Col(name=name):
                candidates: tuple[str, ...] = (name,)
            case EngineNative(deps=deps):
                candidates = deps
            case _:
                continue
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                ordered.append(candidate)
    return tuple(ordered)
