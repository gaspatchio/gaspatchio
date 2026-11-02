# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed-walk derivation of engine_binding for an IR.

Closed-subset whitelist — operators safe to lower to portable backends
(JAX, future engines) without semantic divergence:

  - Polars Expr basics: pl.col, pl.lit, arithmetic (+, -, *, /, **)
  - Comparisons: ==, !=, <, <=, >, >=
  - Boolean: &, |, ~
  - when().then().otherwise()
  - Already-typed inputs: Schedule.year_fractions_expr,
    Curve.spot_rate / discount_factor. Not Curve.forward_rate: it takes two
    floats and returns one, so there is no Expr for a body to hold.
  - MortalityTable.at, Table.lookup

**The walk accepts that list and refuses everything else.** Each Expr is
serialised to the engine's own tree (``Expr.meta.serialize(format="json")``)
and every node in it is reduced to an identity: the node kind, plus the
operator for a ``BinaryExpr``, plus the named payload for a ``Function``,
plus the symbol for a call into this package's extension. An Expr is
closed-subset when every one of its identities is in ``_CLOSED_SUBSET``, and
the IR is ``'portable'`` when every Expr it holds is.

**It fails closed.** A kind the walk has never seen, a payload outside the
set, a plugin call into a library that is not this package's own extension,
and an Expr the engine cannot serialise at all each read as ``'polars'``. So
a ``'portable'`` stamp says the whole tree was recognised and a ``'polars'``
stamp is a refusal — a hit and a miss both mean something, which is what the
substring denylist this replaced could not say.

Three admissions the bare list above does not spell, each measured rather
than assumed:

  - ``Clip`` is in the set because ``MortalityTable.at`` on a select-ultimate
    table emits one — the duration clamp at ``select_period``. It is an
    elementwise three-argument min/max, which every portable backend holds,
    so admitting it does not widen what ``'portable'`` promises.
  - ``Pow`` is admitted only under its ``Generic`` payload, which is what
    ``**`` produces. ``.sqrt()`` and ``.cbrt()`` are the same payload family
    under other variants, are not in the list above, and refuse.
  - A plugin call is admitted by symbol — ``curve_eval``, ``list_pow``,
    ``lookup_by_table_and_hash``, and ``ieee_div``/``ieee_floordiv``/
    ``ieee_mod`` — and only where the library it names is the extension this
    process loaded. The first three are what the typed inputs above
    serialise to; the quotients are the division the framework lowers ``/``,
    ``//`` and ``%`` over numbers to. Any other symbol, or one of those in
    somebody else's library, refuses.

**The stamp is folded into the compilation's canonical form and so into its
``spec_fingerprint``**, which means a Polars release that renames a node kind
would refuse every rollforward that used to pass and move every compiled
fingerprint with it, silently and all at once. The census in
``tests/rollforward/test_engine_binding.py`` exists to make that loud: it
pins, construct by construct, the identities the closed subset serialises to,
and the Polars version they were measured on — ``MEASURED_POLARS_VERSION``
below.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from gaspatchio.rollforward._ir import IR, EngineBinding
    from gaspatchio.rollforward._ops import Op

#: The Polars release the identities below were measured on. The census test
#: asserts the installed version still matches; where it does not, re-measure
#: every construct before moving this string, because a changed identity moves
#: every compiled rollforward's fingerprint.
MEASURED_POLARS_VERSION = "1.42.1"

# `+ - * /`, the six comparisons, and `&` / `|`. `**` is not a BinaryExpr —
# Polars renders it as a `Pow` function payload — and neither is `~`.
_PORTABLE_BINARY_OPS: frozenset[str] = frozenset(
    {
        "Plus",
        "Minus",
        "Multiply",
        "TrueDivide",
        "Eq",
        "NotEq",
        "Lt",
        "LtEq",
        "Gt",
        "GtEq",
        "And",
        "Or",
    }
)

# Symbols in this package's own extension that a typed input serialises to:
# `Curve.spot_rate` and `Curve.discount_factor` call `curve_eval`, the second
# raising the result through `list_pow`; `Table.lookup` and
# `MortalityTable.at` call `lookup_by_table_and_hash`. `ieee_div`,
# `ieee_floordiv` and `ieee_mod` are what `/`, `//` and `%` over numbers lower
# to -- the division the `TrueDivide` entry above already admits, computed one
# IEEE operation per element -- so a framework-lowered quotient is as portable
# as a hand-written one.
_PORTABLE_PLUGIN_SYMBOLS: frozenset[str] = frozenset(
    {
        "curve_eval",
        "ieee_div",
        "ieee_floordiv",
        "ieee_mod",
        "list_pow",
        "lookup_by_table_and_hash",
    }
)

#: Every node identity the closed subset produces. Anything else is 'polars'.
_CLOSED_SUBSET: frozenset[tuple[str, ...]] = frozenset(
    {
        ("Column",),
        ("Literal",),
        ("Ternary",),
        ("Function", "Pow", "Generic"),
        ("Function", "Boolean", "Not"),
        ("Function", "Clip"),
        *(("BinaryExpr", op) for op in _PORTABLE_BINARY_OPS),
        *(("Function", "FfiPlugin", symbol) for symbol in _PORTABLE_PLUGIN_SYMBOLS),
    }
)


def _own_extension() -> str:
    """Return the resolved path of the extension module this process loaded.

    Read on demand rather than at import: this module is reached while
    ``gaspatchio`` itself is still initialising.
    """
    from gaspatchio._internal import __file__ as native_path  # noqa: PLC0415

    return str(Path(str(native_path)).resolve())


def _plugin_identity(payload: dict[str, Any]) -> tuple[str, ...]:
    """Reduce an ``FfiPlugin`` payload to ``('Function', 'FfiPlugin', symbol)``.

    A call into any library but this process's own extension gets a
    ``'foreign'`` identity instead, which no closed-subset entry matches: the
    three admitted symbols name what this package's kernels compute, and the
    same name in another library is another calculation.
    """
    symbol = str(payload.get("symbol"))
    try:
        resolved = str(Path(str(payload.get("lib"))).resolve())
    except (OSError, ValueError):
        resolved = ""
    if resolved != _own_extension():
        return ("Function", "FfiPlugin", "foreign", symbol)
    return ("Function", "FfiPlugin", symbol)


def _function_identity(payload: object) -> tuple[str, ...]:
    """Reduce a ``Function`` node's payload to its identity.

    A payload is either a bare name (``"MaxHorizontal"``) or a single-key
    mapping whose value is either a variant name (``{"Pow": "Generic"}``) or
    that variant's own options (``{"Clip": {...}}``), which the identity
    drops — options configure an operation, they do not decide which one it
    is.
    """
    if isinstance(payload, str):
        return ("Function", payload)
    if isinstance(payload, dict) and len(payload) == 1:
        name, variant = next(iter(payload.items()))
        if name == "FfiPlugin" and isinstance(variant, dict):
            return _plugin_identity(variant)
        if isinstance(variant, str):
            return ("Function", str(name), variant)
        return ("Function", str(name))
    return ("Function", "malformed")


def _collect(node: object, found: set[tuple[str, ...]]) -> None:
    """Add every node identity in ``node`` to ``found``, descending by kind."""
    if not isinstance(node, dict) or len(node) != 1:
        found.add(("malformed",))
        return
    kind, body = next(iter(node.items()))
    if kind == "Column":
        found.add(("Column",))
    elif kind == "Literal":
        # A literal is data, not an operation: every payload shape it carries
        # — an inline scalar, a dtype-tagged number, an embedded series — is a
        # constant any backend can materialise.
        found.add(("Literal",))
    elif kind == "BinaryExpr" and isinstance(body, dict):
        operator = body.get("op")
        found.add(
            ("BinaryExpr", operator if isinstance(operator, str) else "malformed")
        )
        _collect(body.get("left"), found)
        _collect(body.get("right"), found)
    elif kind == "Ternary" and isinstance(body, dict):
        found.add(("Ternary",))
        _collect(body.get("predicate"), found)
        _collect(body.get("truthy"), found)
        _collect(body.get("falsy"), found)
    elif kind == "Function" and isinstance(body, dict):
        found.add(_function_identity(body.get("function")))
        operands = body.get("input")
        for operand in operands if isinstance(operands, list) else ():
            _collect(operand, found)
    else:
        found.add((str(kind),))


def node_identities(expr: pl.Expr) -> frozenset[tuple[str, ...]]:
    """Return the identity of every node in ``expr``'s own tree.

    An Expr the engine refuses to serialise yields a single
    ``('unserialisable', ...)`` identity, which no closed-subset entry
    matches. The case that arises is a Python callable inside the Expr:
    writing one into the tree needs a pickler this package does not depend
    on, so the walk cannot read such an Expr and does not pass it.
    """
    try:
        tree = json.loads(expr.meta.serialize(format="json"))
    except Exception as exc:  # noqa: BLE001 — any refusal reads as "not recognised"
        return frozenset({("unserialisable", type(exc).__name__)})
    found: set[tuple[str, ...]] = set()
    _collect(tree, found)
    return frozenset(found)


def _expr_is_closed_subset(expr: pl.Expr | None) -> bool:
    """Return True when every node in ``expr`` is in the closed subset."""
    if expr is None:
        return True
    return node_identities(expr) <= _CLOSED_SUBSET


def _op_is_closed_subset(op: Op) -> bool:
    """Return True when every Expr-typed field of ``op`` is closed-subset."""
    for f in fields(op):  # type: ignore[arg-type]
        value = getattr(op, f.name)
        if isinstance(value, pl.Expr) and not _expr_is_closed_subset(value):
            return False
    return True


def derive_engine_binding(ir: IR) -> EngineBinding:
    """Return ``'portable'`` iff every Expr in the IR is closed-subset.

    Inspects:
      - Each transition Op's Expr-typed fields
      - The contract_boundary mask (if any)
      - Each State's init Expr

    Anything the walk does not recognise stamps ``'polars'``.
    """
    for state in ir.states:
        if not _expr_is_closed_subset(state.init):
            return "polars"
    for op in ir.transitions:
        if not _op_is_closed_subset(op):
            return "polars"
    if not _expr_is_closed_subset(ir.contract_boundary):
        return "polars"
    return "portable"


__all__ = ["MEASURED_POLARS_VERSION", "derive_engine_binding", "node_identities"]
