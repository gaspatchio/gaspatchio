# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period comparison is never decided by the nearest double of an unread type.

The kernel a per-period comparison runs through reads both sides as doubles,
and a whole number past 2**53 is decided exactly only where the frame has
read both operands' types. Three places it had not:

- a sequence written into the formula -- ``af.k > (2**53, 2**53)``, one
  timeline every policy shares -- had no type, so ``2**53 + 1`` against it
  answered 0.0 in every period;
- a formula built on no frame (``ExpressionProxy(expr, parent=None)``) was
  lowered blind to its operands and reached Polars as a native comparison of
  a list, refused in Polars' own words when the frame ran;
- an operand the frame could not type at all was compared in doubles.

The first is now typed, the second is lowered against the frame it is
assigned to, and the third is refused by name.
"""

from __future__ import annotations

import datetime as dt
from unittest import mock

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, ExpressionProxy, when

_BIG = 2**53


def _frame() -> ActuarialFrame:
    book = pl.DataFrame(
        {
            "n": pl.Series([_BIG + 1, _BIG], dtype=pl.Int64),
            "k": pl.Series(
                [[_BIG + 1, _BIG + 1], [_BIG, _BIG]], dtype=pl.List(pl.Int64)
            ),
            "j": pl.Series([[_BIG, _BIG], [_BIG, _BIG]], dtype=pl.List(pl.Int64)),
        }
    )
    return ActuarialFrame(book).projection.set(
        start_date=dt.date(2025, 1, 1), n_periods=1, frequency="monthly"
    )


def _detached(name: str) -> ExpressionProxy:
    return ExpressionProxy(pl.col(name), parent=None)


def test_a_run_against_a_sequence_literal_compares_exactly() -> None:
    af = _frame()
    af.r = af.k > (_BIG, _BIG)
    assert af.collect()["r"].to_list() == [[1.0, 1.0], [0.0, 0.0]]


def test_a_run_against_a_list_literal_compares_exactly() -> None:
    af = _frame()
    af.r = af.k == [_BIG, _BIG]
    assert af.collect()["r"].to_list() == [[0.0, 0.0], [1.0, 1.0]]


def test_a_comparison_built_on_no_frame_is_decided_by_the_frame_it_joins() -> None:
    af = _frame()
    af.r = _detached("k") > _BIG
    assert af.collect()["r"].to_list() == [[1.0, 1.0], [0.0, 0.0]]


def test_two_runs_built_on_no_frame_are_compared_exactly() -> None:
    af = _frame()
    af.r = _detached("k") > _detached("j")
    assert af.collect()["r"].to_list() == [[1.0, 1.0], [0.0, 0.0]]


def test_a_conditional_over_a_comparison_built_on_no_frame_selects_exactly() -> None:
    af = _frame()
    af.r = when(_detached("k") > _BIG).then(1.0).otherwise(0.0)
    assert af.collect()["r"].to_list() == [[1.0, 1.0], [0.0, 0.0]]


def test_a_frameless_operand_beside_a_framed_one_is_compared_exactly() -> None:
    af = _frame()
    af.r = (_detached("k") + 0) > af.j
    assert af.collect()["r"].to_list() == [[1.0, 1.0], [0.0, 0.0]]


def test_an_operand_whose_type_cannot_be_read_is_refused_by_name() -> None:
    af = _frame()
    unread = "gaspatchio.frame.lowering.context.LoweringContext.dtype_of_expr"
    with (
        mock.patch(unread, return_value=None),
        pytest.raises(TypeError, match="could not be read before the run") as caught,
    ):
        af.r = af.k > (af.j + 0)
    assert "the column 'k'" in str(caught.value)
    assert "nearest doubles" in str(caught.value)


def test_a_per_policy_comparison_built_on_no_frame_answers_as_before() -> None:
    af = _frame()
    af.r = _detached("n") > _BIG
    assert af.collect()["r"].to_list() == [1.0, 0.0]


def test_a_raw_expression_on_no_frame_is_used_as_handed_over() -> None:
    af = _frame()
    af.r = ExpressionProxy(pl.col("n") - 1, parent=None)
    assert af.collect()["r"].to_list() == [_BIG, _BIG - 1]
