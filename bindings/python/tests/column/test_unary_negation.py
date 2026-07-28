# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Unary negation on scalar and list columns.

Regression test for the missing ``__neg__`` overload: ``-col`` raised
``InvalidOperationError: neg operation not supported for dtype list[f64]``
while the equivalent ``0.0 - col`` and ``col * -1.0`` both worked. Both proxies
define the full arithmetic dunder set but omitted ``__neg__``, so Python fell
through to Polars' native ``neg``, which has no list kernel.
"""

import polars as pl

from gaspatchio_core import ActuarialFrame, when


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "policy_id": [1, 2],
                "scalar_col": [1.5, -2.5],
                "list_col": [[1.0, -2.0, 3.0], [4.0, 5.0, -6.0]],
            }
        )
    )


def test_negation_on_list_column_matches_zero_minus() -> None:
    af = _frame()
    af.negated = -af.list_col
    af.reference = 0.0 - af.list_col
    out = af.collect()
    assert out["negated"].to_list() == out["reference"].to_list()
    assert out["negated"].to_list() == [[-1.0, 2.0, -3.0], [-4.0, -5.0, 6.0]]


def test_negation_on_scalar_column_matches_zero_minus() -> None:
    af = _frame()
    af.negated = -af.scalar_col
    out = af.collect()
    assert out["negated"].to_list() == [-1.5, 2.5]


def test_negation_inside_when_then_otherwise() -> None:
    af = _frame()
    af.result = when(af.list_col > 0.0).then(-af.list_col).otherwise(0.0)
    out = af.collect()
    assert out["result"].to_list() == [[-1.0, 0.0, -3.0], [-4.0, -5.0, 0.0]]


def test_negation_on_an_expression_not_just_a_column() -> None:
    """``-`` must work on an ExpressionProxy, not only a ColumnProxy."""
    af = _frame()
    af.negated = -(af.list_col * 2.0)
    out = af.collect()
    assert out["negated"].to_list() == [[-2.0, 4.0, -6.0], [-8.0, -10.0, 12.0]]
