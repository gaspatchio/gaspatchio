# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Boolean-mask combinators and predicate-to-bool conversion (Polars backend).

The frontend (column/condition_expression.py) declares that AND/OR/NOT of
conditions produces an ExpressionProxy. The arithmetic-as-logic
implementation (left * right for AND, 1 - (1-a)*(1-b) for OR, 1 - bool for
NOT) lives here as an implementation detail of the Polars backend.

Layering note: this module is the one place in polars_backend/ that
imports from column/. The _to_*_expr coercion helpers need to dispatch on
the proxy type (ColumnProxy / ConditionExpression / ExpressionProxy) to
emit the correct Polars expression, and duck-typing all three is messier
than three function-local imports. The imports are deferred to break the
masks <-> condition_expression cycle. Keep the exception bounded — only
the type-dispatch helpers below import from column/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio_core.polars_backend.plugins import list_conditional

if TYPE_CHECKING:
    from gaspatchio_core.column.condition_expression import ConditionExpression


def to_boolean_expr(condition: ConditionExpression) -> pl.Expr:
    """Convert a ConditionExpression to a Float64 0/1 expression.

    Uses list_conditional for list-shaped conditions; native Polars cast
    for scalar.
    """
    # Read the shape from the condition's resolved shape (PR 2's SOT) —
    # not by re-probing the schema or duck-typing the operands.
    if condition.shape == "list":
        # Normalize operand order so the list-typed side is on the plugin's
        # `left` (required by list_conditional). Handles commuted predicates
        # like (scalar) == af.list_col by swapping + inverting the operator.
        left, right, operator = condition.normalize_for_list_path()
        return list_conditional(left, right, pl.lit(1.0), pl.lit(0.0), operator)
    return condition._expr.cast(pl.Float64)  # noqa: SLF001


def boolean_and(
    left: ConditionExpression,
    right: Any,  # noqa: ANN401
) -> tuple[pl.Expr, bool]:
    """Combine two predicates with element-wise AND.

    Returns (combined_expr, is_list_path). The caller (frontend operator
    overload) uses is_list_path to decide whether to stamp
    kind="boolean_mask" on the resulting ExpressionProxy — list path
    always does, scalar path preserves the existing behavior of NOT
    setting kind (a quirk in condition_expression.py:212).
    """
    has_list = left.shape == "list" or _other_has_list(right)
    if has_list:
        left_bool = to_boolean_expr(left)
        right_bool = _other_to_boolean_expr(right)
        return left_bool * right_bool, True
    # Scalar path: native Polars boolean AND
    return left._expr & _other_to_native_expr(right), False  # noqa: SLF001


def boolean_or(
    left: ConditionExpression,
    right: Any,  # noqa: ANN401
) -> pl.Expr:
    """Combine two predicates with element-wise OR.

    Scalar path uses native ``|`` returning Boolean — required because the
    result is later fed to ``pl.when()`` which rejects Float64. List path
    uses the ``1 - (1-a)(1-b)`` arithmetic identity over Float64 0/1 masks
    because native ``|`` doesn't broadcast inside ``list[bool]``.
    """
    has_list = left.shape == "list" or _other_has_list(right)
    if has_list:
        left_bool = to_boolean_expr(left)
        right_bool = _other_to_boolean_expr(right)
        return pl.lit(1.0) - ((pl.lit(1.0) - left_bool) * (pl.lit(1.0) - right_bool))
    return left._expr | _other_to_native_expr(right)  # noqa: SLF001


def boolean_not(condition: ConditionExpression) -> pl.Expr:
    """Negate a predicate.

    Scalar path uses native ``~`` returning Boolean — required because the
    result is later fed to ``pl.when()`` which rejects Float64. List path
    uses ``1.0 - bool`` over the Float64 0/1 mask because ``~`` doesn't
    apply inside ``list[bool]`` element-wise.
    """
    if condition.shape == "list":
        return pl.lit(1.0) - to_boolean_expr(condition)
    return ~condition._expr  # noqa: SLF001


# === Type-dispatch helpers (the controlled column/ exception) ===


def _other_to_boolean_expr(other: Any) -> pl.Expr:  # noqa: ANN401
    """Convert the second operand of AND/OR to a Float64 0/1 expression."""
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(other, ConditionExpression):
        return to_boolean_expr(other)
    if isinstance(other, ColumnProxy):
        return other._to_expr().cast(pl.Float64)  # noqa: SLF001
    if isinstance(other, ExpressionProxy):
        return other._expr  # noqa: SLF001
    return other


def _other_to_native_expr(other: Any) -> pl.Expr:  # noqa: ANN401
    """Coerce the second AND operand to a native pl.Expr (scalar path)."""
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(other, ConditionExpression):
        return other._expr  # noqa: SLF001
    if isinstance(other, ColumnProxy):
        return other._to_expr()  # noqa: SLF001
    if isinstance(other, ExpressionProxy):
        return other._expr  # noqa: SLF001
    return other


def _other_has_list(other: Any) -> bool:  # noqa: ANN401
    """Return True iff the operand resolves to a list-shaped value."""
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(other, (ConditionExpression, ColumnProxy, ExpressionProxy)):
        return other.shape == "list"
    return False
