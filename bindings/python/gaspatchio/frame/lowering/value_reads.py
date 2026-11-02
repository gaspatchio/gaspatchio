# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A value-object read is its own node, never text inside an engine fragment.

A read of an assumption table, a mortality basis, a curve or a schedule
carries the identity of what it read on its node: the table's name and
content hash, the curve's, the schedule's. Chained into an engine fragment
-- ``table.lookup(age=af.age).cast(pl.Float32)``, ``pl.max_horizontal(lookup,
0.0)``, ``lookup.polars_native().cast(...)`` -- the read lowers into the
fragment's Polars plan, and the fragment is identified by Polars' display of
that plan, which prints the lookup plugin's name and not its arguments. Two
models reading two different tables then carried one fingerprint, which is a
false identity rather than a partial account (spec Annex A.2).

Each producer's lowered plan is registered here against the read it is
(:func:`register_value_read`, called from ``ProxyAwareExpr.wrap``, the door
every producer hands its expression back through). The one function that
mints every engine-native node, ``ingress.native_node``, asks
:func:`reads_inside` whether its plan holds a registered read and marks the
node where it does. Marking rather than refusing there: the same node is
built for an operand on a raw Polars frame, where a producer's expression
keeps Polars' own meaning and this rule does not reach. An ActuarialFrame
refuses a marked node at the door it records an assignment through
(:func:`refuse_a_value_read_inside_a_fragment`).

A compiled rollforward is not a value object in this sense and is not
registered: its fragment reads the hidden
``__rollforward_<run>`` column by name, so the fold reaches the rollforward's
own node and its identity moves with it. Its calls carry the ``schedule`` the
machine runs on, under the same key a schedule read does, and
are still not a read this module refuses: the schedule is the compilation's,
and the compilation's own node names it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import polars as pl

from gaspatchio._semantic.ir import Call, EngineNative, walk

if TYPE_CHECKING:
    from collections.abc import Iterator

    from gaspatchio._semantic.ir import OpNode

# The attribute that says a call reads a value object, each with the words a
# refusal names it in. A lookup and a mortality basis both carry
# ``table_fingerprint``; the basis is told apart by its own ``mortality``.
_READ_ATTRIBUTES: Final = ("mortality", "table_fingerprint", "curve", "schedule")


@dataclass(frozen=True, slots=True)
class ValueRead:
    """One registered read: the call that made it and the object it read.

    ``framed`` says whether the producer handed the read back bound to a
    frame -- a key read off ``af`` -- where gaspatchio's declared operations
    chained on it answer as a column's would. A read keyed by literals or by
    raw Polars expressions is not bound, and on it those operations are not
    gaspatchio's: a refusal must not name them as a move there.
    """

    call: str
    kind: str
    name: str | None
    identity: str
    framed: bool = True

    def described(self) -> str:
        """Return the read in the words a refusal names it in."""
        named = f" {self.name!r}" if self.name else ""
        return f"{self.call}(), which reads the {self.kind}{named} ({self.identity})"


# Plan key -> the read whose plan it is. Keyed by content, not by object
# identity: the plan inside a fragment is a copy Polars rebuilt, never the
# object the producer handed back.
_READS: dict[str, ValueRead] = {}

# id(EngineNative) -> the reads its plan holds. The node is kept alive by
# ``ingress.NATIVE_REFS`` for the life of the process, so its id is never
# reused while it is a key here -- the same reasoning as ``RAW_OPERANDS``.
_HIDDEN: dict[int, tuple[ValueRead, ...]] = {}


# The family whose calls name a schedule without being a schedule read: a
# compiled rollforward's own node and the calls reading it back out.
_COMPILATION_FAMILY: Final = "rollforward"


def value_read_of(node: OpNode, *, framed: bool = True) -> ValueRead | None:
    """Return the read ``node`` is, or ``None`` where it reads no value object."""
    if not isinstance(node, Call):
        return None
    if node.name == _COMPILATION_FAMILY or node.name.startswith(
        f"{_COMPILATION_FAMILY}."
    ):
        return None
    attrs = dict(node.attrs)
    for key in _READ_ATTRIBUTES:
        identity = attrs.get(key)
        if isinstance(identity, str):
            kind = {
                "mortality": "mortality basis over table",
                "table_fingerprint": "assumption table",
                "curve": "curve",
                "schedule": "schedule",
            }[key]
            name = attrs.get("table")
            return ValueRead(
                call=node.name,
                kind=kind,
                name=name if isinstance(name, str) else None,
                identity=identity,
                framed=framed,
            )
    return None


def _plan_key(expr: pl.Expr) -> str:
    """Return the key a plan is registered and looked up under.

    The serialized plan where Polars will write one; it carries a plugin's
    arguments, which the display leaves out. A plan holding a Python
    function -- a schedule's day count -- does not serialize without a
    pickler this package does not depend on, and is keyed on its rendering,
    which names the function's chain. The key only ever *finds* a read; it is
    never an identity, so a rendering that two reads share costs nothing
    worse than the refusal both would get.
    """
    try:
        payload = expr.meta.serialize(format="binary")
    except Exception:  # noqa: BLE001 -- Polars raises several kinds here
        return "text:" + hashlib.sha256(str(expr).encode()).hexdigest()
    return "plan:" + hashlib.sha256(payload).hexdigest()


def register_value_read(expr: pl.Expr, node: OpNode, *, framed: bool = True) -> None:
    """Remember ``expr`` as the plan of the value-object read ``node`` is.

    ``framed`` is whether the producer bound the read to a frame. One plan
    can be reached both ways -- ``lookup(age=af.age)`` and ``lookup(age=pl.col(
    "age"))`` lower alike -- and is then remembered as bound, so that a read
    written on the frame is answered the same whatever else the process
    wrote: a refusal's text never depends on which line ran first. A read
    keyed by values alone lowers to a plan no frame-keyed read shares, so it
    is always remembered as unbound.
    """
    read = value_read_of(node, framed=framed)
    if read is None:
        return
    key = _plan_key(expr)
    held = _READS.get(key)
    _READS[key] = held if held is not None and held.framed else read


def _gathered(found: dict[str, ValueRead], read: ValueRead) -> None:
    """Add ``read`` to ``found`` by identity, an unbound read winning a tie."""
    held = found.get(read.identity)
    if held is None or (held.framed and not read.framed):
        found[read.identity] = read


def _sub_plans(expr: pl.Expr) -> Iterator[pl.Expr]:
    """Yield ``expr`` and every expression inside it, outermost first."""
    yield expr
    try:
        inputs = expr.meta.pop()
    except Exception:  # noqa: BLE001 -- a plan Polars will not open is a leaf here
        return
    for inner in inputs:
        yield from _sub_plans(inner)


def reads_inside(expr: pl.Expr) -> tuple[ValueRead, ...]:
    """Return the registered reads ``expr``'s plan holds, first found first.

    A value that is not an expression -- the bare number a rollforward
    classifier hands over for an opening value -- holds none.
    """
    if not _READS or not isinstance(expr, pl.Expr):
        return ()
    if expr.meta.is_literal(allow_aliasing=True):
        return ()
    found: dict[str, ValueRead] = {}
    for inner in _sub_plans(expr):
        read = _READS.get(_plan_key(inner))
        if read is not None:
            _gathered(found, read)
    return tuple(found.values())


def value_read_held_by(value: object) -> ValueRead | None:
    """Return a value-object read ``value``'s own tree holds, or ``None``.

    Asks only a node the value already carries -- a producer's, or an
    expression proxy's built one -- and never builds one, so asking costs
    nothing and changes nothing. A refusal that would advise the explicit
    escape on such a value asks here first: through ``polars_native()`` the
    read would sit inside the very fragment
    :func:`refuse_a_value_read_inside_a_fragment` refuses.
    """
    held = getattr(value, "__dict__", None)
    if not isinstance(held, dict):
        return None
    node = held.get("_node") or held.get("_node_cached")
    if node is None:
        return None
    for leaf in walk(node):
        read = value_read_of(leaf)
        if read is not None:
            return read
    return None


def mark_hidden_reads(node: EngineNative, reads: tuple[ValueRead, ...]) -> None:
    """Record that the fragment ``node`` would hide ``reads`` from the tree."""
    if reads:
        _HIDDEN[id(node)] = reads


def hidden_reads(node: OpNode) -> tuple[ValueRead, ...]:
    """Return every value-object read hidden inside an engine fragment of ``node``."""
    found: dict[str, ValueRead] = {}
    for leaf in walk(node):
        if isinstance(leaf, EngineNative):
            for read in _HIDDEN.get(id(leaf), ()):
                _gathered(found, read)
    return tuple(found.values())


def refuse_a_value_read_inside_a_fragment(node: OpNode, *, column: str) -> None:
    """Refuse an assignment whose engine fragment would hide a value-object read.

    The moves the refusal names depend on how the read was written. Bound to
    the frame, a declared operation chained on the read keeps it a node, so
    that is the first move. Keyed by literals or by raw Polars expressions,
    the read is not yet a column the frame can type and no declared
    operation reaches it, so the one move is to store it first.

    Raises:
        ValueError: If an engine-native fragment of ``node`` holds a table,
            mortality, curve or schedule read, naming the read and the moves
            that work where it was written.

    """
    reads = hidden_reads(node)
    if not reads:
        return
    listed = "; ".join(read.described() for read in reads)
    msg = (
        f"Column {column!r} would read {listed} inside a Polars expression the "
        "framework cannot see into. That expression is recorded by Polars' own "
        "text, which does not name what was read or its content, so the model's "
        "fingerprint would not change when the table, curve or schedule did. "
        "A read like this has to be its own step. "
    )
    if all(read.framed for read in reads):
        msg += (
            "Either continue with a declared operation, which keeps the read -- "
            "a type conversion is to_float(), to_integer(), to_text() or "
            "to_list(); a NaN fill is fill_nan(0.0) -- or store the read as its "
            f"own column first and continue from that column: af.{column}_read = "
            f"<the read>, then af.{column} = af.{column}_read.polars_native()"
            ".<method>(...)."
        )
    else:
        msg += (
            "This read is keyed by values or raw Polars expressions rather than "
            "by a column of the frame, so gaspatchio's operations do not reach "
            "it where it is written: chained on it, a method is Polars' own. "
            f"Store the read as its own column first, af.{column}_read = <the "
            "read>, and continue from that column: a declared operation records "
            f"as itself -- af.{column} = af.{column}_read.fill_nan(0.0), or "
            "to_float(), to_integer(), to_text(), to_list() -- and any other "
            f"method is af.{column} = af.{column}_read.polars_native()"
            ".<method>(...)."
        )
    raise ValueError(msg)
