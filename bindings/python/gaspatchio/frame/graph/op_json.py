# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The operation tree in JSON: the seven nodes written out, and read back.

``ir.py`` holds the closed vocabulary a formula reduces to. ``fingerprint.py``
turns one of those trees into the bytes its identity is taken over. This
module is the third reading of the same vocabulary: the tree as a JSON
document, so that what a model computes can travel in a file rather than only
be hashed there.

The two are deliberately different jobs and the difference is worth stating.
The canonical bytes are for **comparing**: they are compact, they are ordered
so that two records configured identically hash identically, and nothing reads
them back -- a digest is not meant to be reversible. This encoding is for
**reading and re-executing**: every field is named, the order is the tree's own
rather than a sorted one, and :func:`op_node_from_json` reconstructs the node
the writer held. A consumer that parses a tree written here and hashes what it
got reaches the digest the artifact already carries, which is what makes the
file check itself rather than ask to be trusted (*No vendor lock-in, by
construction*).

The seven names -- ``col``, ``lit``, ``binop``, ``call``, ``when_then``,
``state``, ``engine_native`` -- are the ones the published schema enumerates,
not a second spelling invented here.

A literal is the one node with two forms, because it holds two things: one
scalar under ``value``, or a sequence of them under ``values``. Naming them
apart rather than writing a bare JSON array under one key is what keeps a band
of one boundary and that boundary on its own two documents, which is the
distinction ``Lit`` exists to hold.

**On the way in this module is liberal, and on the way out it is complete.**
A run this encoder always writes -- a call's arguments, a call's attributes,
an engine-native fragment's declared reads -- may be absent from a document
written by hand or by another producer, and absence is read as the empty run:
"no arguments" is not an ambiguous sentence. What is refused is a meaning that
would have to be guessed: an unknown node name, a literal carrying both forms
or neither, an operator outside the closed vocabulary, a child that is not an
object.
"""

from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING, Any, Final, assert_never, cast, get_args

from gaspatchio._semantic.ir import (
    BinOp,
    BinOpKind,
    Call,
    Col,
    EngineName,
    EngineNative,
    Lit,
    State,
    WhenThen,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio._semantic.ir import AttrValue, LitScalar, LitSequenceMember, OpNode

__all__ = ["op_node_from_json", "op_node_to_json"]

# The seven node names, exactly as the published schema enumerates them.
_COL: Final[str] = "col"
_LIT: Final[str] = "lit"

# The key a date literal is written under. Structural rather than a
# spelling, because JSON has a number token and no date token: a date under
# ``value`` would be the TEXT "2024-01-01", which encodes as the string tag
# and its eleven bytes and reaches a well-formed digest matching nothing.
# Exactly one of ``value``, ``values`` and ``date`` is present on a literal.
_LIT_DATE: Final[str] = "date"

# Four digits, a hyphen, two digits, a hyphen, two digits. No time, no
# offset, no ``Z``, no compact form, and no year outside 0000-9999: the
# value hashed is the day count, so two spellings of one day would be one
# digest under two documents and a consumer could not say which the
# producer wrote.
_ISO_DATE: Final[re.Pattern[str]] = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_BINOP: Final[str] = "binop"
_CALL: Final[str] = "call"
_WHEN_THEN: Final[str] = "when_then"
_STATE: Final[str] = "state"
_ENGINE_NATIVE: Final[str] = "engine_native"

_NODE_NAMES: Final[tuple[str, ...]] = (
    _COL,
    _LIT,
    _BINOP,
    _CALL,
    _WHEN_THEN,
    _STATE,
    _ENGINE_NATIVE,
)

# The two closed vocabularies a document can get wrong in a way no amount of
# well-formed JSON would catch. Read off the type aliases themselves, so that
# widening one of them never leaves this module refusing what the tree accepts.
_BINOP_KINDS: Final[frozenset[str]] = frozenset(get_args(BinOpKind))
_ENGINE_NAMES: Final[frozenset[str]] = frozenset(get_args(EngineName))


def op_node_to_json(node: OpNode) -> dict[str, Any]:
    """Return ``node`` as a JSON-encodable object naming every field it carries.

    The final ``case`` is unreachable for any real node; it exists so that
    an eighth node type added to the op-tree without teaching this function
    how to write it fails the type checkers, rather than being written out
    as something else at run time.

    Args:
        node: The operation-tree node to write out.

    Returns:
        The node as an object: ``op`` naming which of the seven it is, then
        that node's own fields, with child nodes written in place.

    Raises:
        ValueError: If a call carries the same attribute key twice. A JSON
            object holds a key once, so the second would silently displace
            the first -- and a call configured twice over is a producer bug
            rather than a document to write.

    Examples:
        >>> from gaspatchio._semantic.ir import BinOp, Col
        >>> from gaspatchio.frame.graph.op_json import op_node_to_json
        >>> op_node_to_json(BinOp("mul", Col("sum_assured"), Col("death_rate")))
        {'op': 'binop', 'kind': 'mul', 'left': {'op': 'col', 'name': 'sum_assured'}, 'right': {'op': 'col', 'name': 'death_rate'}}

    """  # noqa: E501 — the example's one-line dict output is what doctest compares against
    written: dict[str, Any]
    match node:
        case Col(name=name):
            written = {"op": _COL, "name": name}
        case Lit(value=value):
            written = _lit_to_json(value)
        case BinOp(op=op, left=left, right=right):
            written = {
                "op": _BINOP,
                "kind": op,
                "left": op_node_to_json(left),
                "right": op_node_to_json(right),
            }
        case Call(name=name, args=args, attrs=attrs):
            written = {
                "op": _CALL,
                "name": name,
                "args": [op_node_to_json(arg) for arg in args],
                "attrs": _attrs_to_json(name, attrs),
            }
        case WhenThen(cond=cond, then=then, otherwise=otherwise):
            written = {
                "op": _WHEN_THEN,
                "cond": op_node_to_json(cond),
                "then": op_node_to_json(then),
                "otherwise": op_node_to_json(otherwise),
            }
        case State(name=name):
            written = {"op": _STATE, "name": name}
        case EngineNative(engine=engine, text=text, deps=deps):
            written = {
                "op": _ENGINE_NATIVE,
                "engine": engine,
                "text": text,
                "deps": list(deps),
            }
        case _ as unreachable:
            assert_never(unreachable)
    return written


def op_node_from_json(payload: Mapping[str, Any]) -> OpNode:
    """Return the operation-tree node ``payload`` stands for.

    The inverse of :func:`op_node_to_json` for everything that function
    writes: parsing a tree back and writing it out again returns the same
    object, and hashing it reaches the digest the artifact carries.

    Args:
        payload: One node of an operation tree, as
            :func:`op_node_to_json` writes it.

    Returns:
        The node itself.

    Raises:
        ValueError: If ``payload`` names no node type, names one this
            vocabulary does not hold, or is missing something whose meaning
            would otherwise have to be guessed.
        TypeError: If a field carries a value of the wrong shape -- a child
            that is not an object, a name that is not text, a literal
            holding something the tree cannot spell.

    """
    kind = payload.get("op")
    parsed: OpNode
    match kind:
        case "col":
            parsed = Col(name=_named_text(payload, "name", kind))
        case "lit":
            parsed = _lit_from_json(payload)
        case "binop":
            parsed = BinOp(
                op=_binop_kind(payload),
                left=_child(payload, "left", kind),
                right=_child(payload, "right", kind),
            )
        case "call":
            parsed = Call(
                name=_named_text(payload, "name", kind),
                args=tuple(_children(payload, "args", kind)),
                attrs=_attrs_from_json(payload),
            )
        case "when_then":
            parsed = WhenThen(
                cond=_child(payload, "cond", kind),
                then=_child(payload, "then", kind),
                otherwise=_child(payload, "otherwise", kind),
            )
        case "state":
            parsed = State(name=_named_text(payload, "name", kind))
        case "engine_native":
            parsed = EngineNative(
                engine=_engine_name(payload),
                text=_named_text(payload, "text", kind),
                deps=tuple(_dep_names(payload)),
            )
        case _:
            raise ValueError(_unknown_node_message(kind))
    return parsed


def _unknown_node_message(kind: object) -> str:
    """Explain that a document names a node type this vocabulary does not hold."""
    named = "names no node type at all" if kind is None else f"names {kind!r}"
    return (
        f"An operation tree {named}. Every node carries an 'op' naming one "
        f"of {list(_NODE_NAMES)} -- the seven the format's own byte grammar "
        "tags -- and nothing else is a node. A document using another name "
        "was written against a different vocabulary; read it under the "
        "schema its producer published."
    )


def _attrs_to_json(
    name: str, attrs: tuple[tuple[str, AttrValue], ...]
) -> dict[str, AttrValue]:
    """Return a call's configuration as an object, refusing a repeated key.

    Kept in the order the call carries rather than sorted. Sorting is what
    the byte grammar does, and for the reason it does it -- two records
    configured identically must hash identically -- but this document is
    read rather than compared, and the order a call was configured in is a
    fact about it that costs nothing to keep.
    """
    written: dict[str, AttrValue] = {}
    for key, value in attrs:
        if key in written:
            msg = (
                f"The call {name!r} carries the attribute {key!r} twice. A "
                "JSON object holds a key once, so writing it would keep the "
                "second and lose the first. Emit the call with one value per "
                "attribute."
            )
            raise ValueError(msg)
        written[key] = value
    return written


def _attrs_from_json(
    payload: Mapping[str, Any],
) -> tuple[tuple[str, AttrValue], ...]:
    """Return a call's configuration, in the order the document writes it."""
    attrs = payload.get("attrs", {})
    if not isinstance(attrs, dict):
        msg = (
            f"A call's 'attrs' must be an object of typed values, got "
            f"{attrs!r}. Each key is the name of one piece of the call's "
            "configuration and each value is text, a whole number, a "
            "decimal, a true/false flag, or null."
        )
        raise TypeError(msg)
    return tuple(
        (str(key), _attr_value(str(key), value)) for key, value in attrs.items()
    )


def _attr_value(key: str, value: object) -> AttrValue:
    """Return one call attribute, refusing a value the tree cannot carry."""
    # Spelled out rather than read off a tuple constant: the four are what
    # ``AttrValue`` says, and writing them here is what lets a type checker
    # see that the value handed back is one of them.
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    msg = (
        f"The call attribute {key!r} carries {value!r}, which an operation "
        "tree cannot hold: an attribute is text, a whole number, a decimal, "
        "a true/false flag, or null. A structure belongs in the call's "
        "arguments, where it is a node of its own."
    )
    raise TypeError(msg)


def _lit_to_json(value: LitScalar | tuple[LitSequenceMember, ...]) -> dict[str, Any]:
    """Return the wire form of one literal's payload.

    A date takes its own key. ``datetime.date`` is tested before the tuple
    only for readability -- the two cannot both be true -- but it must be
    tested before nothing else, because ``Lit`` has already refused a date
    inside a tuple and an instant anywhere.
    """
    if isinstance(value, datetime.date):
        return {"op": _LIT, _LIT_DATE: value.isoformat()}
    if isinstance(value, tuple):
        return {"op": _LIT, "values": list(value)}
    return {"op": _LIT, "value": value}


def _lit_date(text: object) -> datetime.date:
    """Return the date ``text`` spells, refusing anything but ISO 8601's day form.

    Raises:
        TypeError: If the value under ``date`` is not text.
        ValueError: If the text is not a plain calendar date.

    """
    if not isinstance(text, str):
        msg = (
            f"A literal's 'date' must be text spelling a calendar date, got "
            f"{text!r}. JSON has no date token, which is why the key carries "
            "one rather than the value doing so."
        )
        raise TypeError(msg)
    if not _ISO_DATE.match(text):
        msg = (
            f"A literal's 'date' is {text!r}, which is not a calendar date in "
            "ISO 8601 extended form: four digits, a hyphen, two digits, a "
            "hyphen, two digits, with no time, no offset and no compact form. "
            "The value hashed is the day count, so two spellings of one day "
            "would be one digest under two documents."
        )
        raise ValueError(msg)
    return datetime.date.fromisoformat(text)


def _lit_from_json(payload: Mapping[str, Any]) -> Lit:
    """Return the literal ``payload`` stands for: one scalar, or a sequence.

    The two forms are named apart on purpose, so this refuses a document
    carrying both -- which would be two literals under one node -- and one
    carrying neither, which names no value at all.
    """
    named = [key for key in ("value", "values", _LIT_DATE) if key in payload]
    if len(named) > 1:
        msg = (
            "A literal carries exactly one of 'value', 'values' and 'date': "
            "one is a single value, one a sequence of them and one a calendar "
            f"day, and {payload!r} would be several literals written as one "
            "node."
        )
        raise ValueError(msg)
    if _LIT_DATE in payload:
        return Lit(_lit_date(payload[_LIT_DATE]))
    has_scalar = "value" in payload
    has_sequence = "values" in payload
    if has_sequence:
        members = payload["values"]
        if not isinstance(members, (list, tuple)):
            msg = (
                f"A literal's 'values' must be a sequence, got {members!r}. "
                "One value on its own is written under 'value'."
            )
            raise TypeError(msg)
        return Lit(
            tuple(_lit_scalar(member, len(tuple(members))) for member in members)
        )
    if has_scalar:
        return Lit(_lit_scalar(payload["value"], None))
    msg = (
        f"A literal names no value: {payload!r} carries none of 'value', "
        "'values' and 'date'. A literal is one scalar under 'value', a "
        "sequence of them under 'values', or a calendar day under 'date'."
    )
    raise ValueError(msg)


def _lit_scalar(value: object, in_sequence: int | None) -> LitSequenceMember:
    """Return one literal payload, refusing a value the tree cannot spell.

    A date is not among the types accepted here, in either position. In the
    scalar position it never reaches this function, because it arrives under
    its own key; in a sequence it is refused, which is the boundary this
    grammar draws and the third of the three doors that draw it.
    """
    if isinstance(value, (bool, int, float, str)):
        return value
    where = "" if in_sequence is None else f" inside a sequence of {in_sequence} values"
    msg = (
        f"A literal cannot hold {value!r}{where}: a formula's literals are "
        "text, whole numbers, decimals, and true/false flags, and a calendar "
        "day written under 'date' rather than here. A value the tree could "
        "only half hold would identify the formula by half its contents, so "
        "it is refused rather than abbreviated."
    )
    raise TypeError(msg)


def _binop_kind(payload: Mapping[str, Any]) -> BinOpKind:
    """Return the operator a binary operation applies, refusing an unknown one."""
    kind = payload.get("kind")
    if isinstance(kind, str) and kind in _BINOP_KINDS:
        # The membership test is the check the annotation states; the set was
        # read off the alias itself, so the narrowing is sound and only the
        # type checker needs telling.
        return cast("BinOpKind", kind)
    msg = (
        f"A binary operation applies {kind!r}, which is not one of the "
        f"operators an operation tree carries: {sorted(_BINOP_KINDS)}. Seven "
        "arithmetic, six comparison, two logical, and the vocabulary is "
        "closed."
    )
    raise ValueError(msg)


def _engine_name(payload: Mapping[str, Any]) -> EngineName:
    """Return the engine an escape-hatch fragment is written for."""
    engine = payload.get("engine")
    if isinstance(engine, str) and engine in _ENGINE_NAMES:
        return cast("EngineName", engine)
    msg = (
        f"An engine-native fragment names the engine {engine!r}, which is "
        f"not one this format knows: {sorted(_ENGINE_NAMES)}. The fragment's "
        "text is opaque outside the engine it was written for, so the engine "
        "is the one thing about it that has to be a name a reader knows."
    )
    raise ValueError(msg)


def _named_text(payload: Mapping[str, Any], key: str, kind: object) -> str:
    """Return one required text field off a node, refusing anything else."""
    value = payload.get(key)
    if isinstance(value, str):
        return value
    msg = (
        f"A {kind!r} node's {key!r} must be text, got {value!r}. It names "
        "something -- a column, a state, an operation, a fragment's source "
        "-- and a name that is not text names nothing."
    )
    raise TypeError(msg)


def _child(payload: Mapping[str, Any], key: str, kind: object) -> OpNode:
    """Return one required child node, parsed in place."""
    value = payload.get(key)
    if not isinstance(value, dict):
        msg = (
            f"A {kind!r} node's {key!r} must be an operation tree of its "
            f"own, got {value!r}. Children are written in place, as objects "
            "carrying their own 'op'."
        )
        raise TypeError(msg)
    return op_node_from_json(value)


def _children(payload: Mapping[str, Any], key: str, kind: object) -> list[OpNode]:
    """Return a run of child nodes, reading an absent run as the empty one."""
    values = payload.get(key, [])
    if not isinstance(values, (list, tuple)):
        msg = (
            f"A {kind!r} node's {key!r} must be a sequence of operation "
            f"trees, got {values!r}."
        )
        raise TypeError(msg)
    return [_child({key: value}, key, kind) for value in values]


def _dep_names(payload: Mapping[str, Any]) -> list[str]:
    """Return the column names an engine-native fragment declares it reads."""
    deps = payload.get("deps", [])
    if not isinstance(deps, (list, tuple)):
        msg = (
            f"An engine-native fragment's 'deps' must be a sequence of "
            f"column names, got {deps!r}. The text is opaque, so this "
            "declaration is the only account of what it reads."
        )
        raise TypeError(msg)
    return [_dep_name(dep) for dep in deps]


def _dep_name(dep: object) -> str:
    """Return one name out of ``deps``, refusing an entry that is not text.

    Named apart from :func:`_named_text` rather than borrowing it: the field
    a reader has to go and fix is ``deps``, and a message naming ``name``
    would send them looking for a field the node does not carry.
    """
    if isinstance(dep, str):
        return dep
    msg = (
        f"An engine-native fragment's 'deps' carries {dep!r}, which is not a "
        "column name. Every entry names one column the fragment reads, and "
        "the text is opaque, so an entry that is not text accounts for "
        "nothing."
    )
    raise TypeError(msg)
