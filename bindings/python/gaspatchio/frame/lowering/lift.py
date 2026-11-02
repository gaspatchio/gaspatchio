# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Read a raw Polars predicate back into the op-tree, where the tree can spell it.

``af.filter(pl.col("status") == "IF")`` is how the filter's own docstring
teaches in-force selection, and an author who wrote it has written a
comparison of a column with a literal -- the same calculation as
``af.status == "IF"``, spelled in the engine's own words. A selecting step
enters the record as a predicate op-tree (section 7.6), so this module reads
that spelling back into the tree the frame's own operators build, and the
two spellings of one predicate are one record with one fingerprint.

**The grammar is closed and small, and anything outside it is not guessed
at.** A column, a literal, the comparisons, ``&``, ``|``, ``~``, the
arithmetic operators, the null and NaN tests and membership in a literal
set: the forms a row predicate is written in. Every other form -- a string
method, a window, a cast, a user function -- answers None, and the caller
records the predicate as the engine fragment it is, exactly as a raw Polars
operand to a formula is recorded. Nothing is approximated: a form this
module cannot transcribe whole is not transcribed in part.

The engine's own account of an expression (``meta.serialize(format="json")``)
is what is read, never its display text, and a control expression this
build writes itself is read first: an engine whose account of a known
comparison no longer has the shape below lifts nothing at all, so a format
change narrows the record to engine fragments rather than mistranscribing
it.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any, Final

import polars as pl
from loguru import logger

from gaspatchio._semantic.ir import BinOp, Call, Col, Lit
from gaspatchio.frame.lowering.ingress import (
    IntegerLiteralPastI64Error,
    recordable_node,
)

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import BinOpKind, OpNode

__all__ = ["lift_predicate"]

# The engine's operator names, and the op-tree's own for each.
_BINARY: Final[dict[str, BinOpKind]] = {
    "Eq": "eq",
    "NotEq": "ne",
    "Lt": "lt",
    "LtEq": "le",
    "Gt": "gt",
    "GtEq": "ge",
    "And": "and",
    "LogicalAnd": "and",
    "Or": "or",
    "LogicalOr": "or",
    "Plus": "add",
    "Minus": "sub",
    "Multiply": "mul",
    "TrueDivide": "div",
    "FloorDivide": "floordiv",
    "Modulus": "mod",
}

# The engine's one-operand Boolean functions, and the vocabulary's call for each.
_TESTS: Final[dict[str, str]] = {
    "Not": "not_",
    "IsNull": "is_null",
    "IsNotNull": "is_not_null",
    "IsNan": "is_nan",
    "IsNotNan": "is_not_nan",
    "IsFinite": "is_finite",
    "IsInfinite": "is_infinite",
}

# A comparison this build writes itself, and the account it must have for
# any account to be read. See the module docstring.
_CONTROL: Final[pl.Expr] = pl.col("a") == 1
_CONTROL_ACCOUNT: Final[dict[str, Any]] = {
    "BinaryExpr": {
        "left": {"Column": "a"},
        "op": "Eq",
        "right": {"Literal": {"Dyn": {"Int": 1}}},
    }
}
_readable: list[bool] = []


def _engine_accounts_are_readable() -> bool:
    """Whether this engine still writes the account the lifter reads, asked once."""
    if not _readable:
        try:
            account = json.loads(_CONTROL.meta.serialize(format="json"))
        except Exception as error:  # noqa: BLE001 -- an unreadable control is a no
            logger.trace(
                f"Could not read the engine's account of a comparison: {error}"
            )
            account = None
        _readable.append(account == _CONTROL_ACCOUNT)
    return _readable[0]


def lift_predicate(expr: pl.Expr) -> OpNode | None:
    """Return the op-tree a raw Polars predicate stands for, or None.

    None wherever any part of the expression is outside the closed grammar
    the module docstring lists, and wherever this engine's account of an
    expression cannot be read -- the caller then records the predicate as
    an engine fragment.

    Examples:
        >>> import polars as pl
        >>> lift_predicate(pl.col("status") == "IF")
        BinOp(op='eq', left=Col(name='status'), right=Lit(value='IF'))
        >>> lift_predicate(pl.col("status").str.starts_with("I")) is None
        True

    """
    if not _engine_accounts_are_readable():
        return None
    try:
        account = json.loads(expr.meta.serialize(format="json"))
    except Exception as error:  # noqa: BLE001 -- an expression that will not say is not lifted
        logger.trace(f"Could not read the engine's account of a predicate: {error}")
        return None
    return _lifted(account)


def _lifted(account: object) -> OpNode | None:  # noqa: PLR0911 -- one return per form of the closed grammar
    """Return the op-tree one piece of the engine's account stands for, or None."""
    if not isinstance(account, dict) or len(account) != 1:
        return None
    ((form, body),) = account.items()
    if form == "Column" and isinstance(body, str):
        return Col(body)
    if form == "Literal":
        return _literal(account)
    if form == "BinaryExpr" and isinstance(body, dict):
        op = _BINARY.get(str(body.get("op")))
        left, right = _lifted(body.get("left")), _lifted(body.get("right"))
        if op is None or left is None or right is None:
            return None
        return BinOp(op, left, right)
    if form == "Function" and isinstance(body, dict):
        return _function(body)
    return None


def _function(body: dict[str, Any]) -> OpNode | None:
    """Return a one-operand test, or membership in a literal set, or None."""
    inputs = body.get("input")
    function = body.get("function")
    if not isinstance(inputs, list) or not isinstance(function, dict):
        return None
    test = function.get("Boolean")
    operands = [_lifted(one) for one in inputs]
    if any(operand is None for operand in operands):
        return None
    if isinstance(test, str) and test in _TESTS and len(operands) == 1:
        return Call(_TESTS[test], (operands[0],))  # type: ignore[arg-type]
    if isinstance(test, dict) and set(test) == {"IsIn"} and len(operands) == 2:  # noqa: PLR2004 -- a value and its set
        options = test["IsIn"]
        members = operands[1]
        nulls_equal = options.get("nulls_equal") if isinstance(options, dict) else None
        if not isinstance(nulls_equal, bool) or not (
            isinstance(members, Lit) and isinstance(members.value, tuple)
        ):
            return None
        return Call("is_in", (operands[0], members), (("nulls_equal", nulls_equal),))  # type: ignore[arg-type]
    return None


def _literal(account: dict[str, Any]) -> OpNode | None:
    """Return the literal one account holds, read by the engine itself, or None.

    The account of a literal is the engine's own encoding of the value -- a
    list arrives as Arrow bytes -- so it is not parsed here. The literal is
    handed back to the engine as an expression and evaluated, and the value
    it yields is recorded through the same door an operand of a formula
    takes, so a literal the tree has no form for is refused there as it is
    everywhere else.
    """
    try:
        literal = pl.Expr.deserialize(io.StringIO(json.dumps(account)), format="json")
        values = pl.select(literal.alias("value")).to_series()
    except Exception as error:  # noqa: BLE001 -- a literal the engine will not hand back is not lifted
        logger.trace(f"Could not read a literal back out of a predicate: {error}")
        return None
    if values.len() != 1:
        return None
    value = values.to_list()[0]
    if value is None:
        return None
    try:
        node = recordable_node(value)
    except IntegerLiteralPastI64Error:
        # A whole number no i64 holds, written in the author's own Polars:
        # the predicate stays the engine fragment it was written as, with
        # the engine's meaning, rather than being lifted into a record that
        # cannot hold it.
        return None
    return node if isinstance(node, Lit) else None
