# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A column still wider than ``i64`` is compared exactly, in its own width.

A ``UInt64``, ``Int128`` or ``UInt128`` column holding a value no ``i64``
holds keeps the width it arrived in, and is outside the portable domain: the
record refuses it. The frame still compares it, exactly. Two things stood in
the way. The literal check refused any whole number past ``i64`` wherever it
was written, so ``af.pid == 2**64 - 1`` -- exact before that check -- could no
longer be written at all; and Polars compared such a column with a whole
number of another type in a type that does not hold both, so ``pid > 7``
answered null for the policy holding ``2**64 - 1``. A literal past ``i64`` is
now admitted in a comparison, or a membership test, against such a column,
and refused everywhere else; and the comparison is made in a type holding
both sides.

``replace`` and ``cut`` are not comparisons: ``replace`` answers in the
column's own type and ``cut`` places a value against decimal breakpoints. So
they read a wide column as arithmetic does -- as the ``Int64`` it fits, from
either door -- and are refused by name where a value does not fit. A
membership test answers a truth value and never carries the value, so
``is_in`` is a comparison: it is exact in the column's own width.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.lowering.ingress import IntegerLiteralPastI64Error

_PAST = 2**64 - 1


def _past(*, lazy: bool = False) -> ActuarialFrame:
    book = pl.DataFrame({"pid": pl.Series([7, _PAST], dtype=pl.UInt64)})
    return ActuarialFrame(book.lazy() if lazy else book)


def _fits(*, lazy: bool) -> ActuarialFrame:
    book = pl.DataFrame({"pid": pl.Series([7, 8], dtype=pl.UInt64)})
    return ActuarialFrame(book.lazy() if lazy else book)


@pytest.mark.parametrize("lazy", [False, True], ids=["DataFrame", "LazyFrame"])
def test_an_identifier_past_i64_is_compared_with_its_own_digits(*, lazy: bool) -> None:
    af = _past(lazy=lazy)
    af.is_it = af.pid == _PAST
    af.not_it = af.pid != 2**64 - 2
    af.above = af.pid > 2**63
    af.flag = when(af.pid == _PAST).then(1).otherwise(0)
    out = af.collect()
    assert out["is_it"].to_list() == [0.0, 1.0]
    assert out["not_it"].to_list() == [1.0, 1.0]
    assert out["above"].to_list() == [0.0, 1.0]
    assert out["flag"].to_list() == [0, 1]


def test_a_literal_on_the_left_of_a_wide_column_is_admitted_too() -> None:
    af = _past()
    af.r = _PAST == af.pid  # noqa: SIM300 -- the literal is written on the left
    af.s = 2**63 < af.pid  # noqa: SIM300 -- the literal is written on the left
    out = af.collect()
    assert out["r"].to_list() == [0.0, 1.0]
    assert out["s"].to_list() == [0.0, 1.0]


def test_a_wide_column_against_a_small_whole_number_is_not_null() -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "pid": pl.Series([7, _PAST], dtype=pl.UInt64),
                "i": pl.Series([-1, -1], dtype=pl.Int64),
            }
        )
    )
    af.gt = af.pid > 7
    af.over_i = af.pid > af.i
    out = af.collect()
    assert out["gt"].to_list() == [0.0, 1.0]
    assert out["over_i"].to_list() == [1.0, 1.0]


def test_a_per_period_run_of_a_wide_column_is_compared_exactly() -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "ids": pl.Series(
                    [[7, _PAST], [2**63, 2**63 + 1]], dtype=pl.List(pl.UInt64)
                )
            }
        )
    )
    af.top = af.ids == _PAST
    af.big = af.ids > 2**63
    af.small = af.ids > 7
    out = af.collect()
    assert out["top"].to_list() == [[0.0, 1.0], [0.0, 0.0]]
    assert out["big"].to_list() == [[0.0, 1.0], [0.0, 1.0]]
    assert out["small"].to_list() == [[0.0, 1.0], [1.0, 1.0]]


def test_a_128_bit_column_is_compared_exactly_on_both_routes() -> None:
    values = [2**100 + 1, -(2**126) - 1]
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "n": pl.Series(values, dtype=pl.Int128),
                "u": pl.Series([2**128 - 1, 3], dtype=pl.UInt128),
                "ns": pl.Series([[v, v] for v in values], dtype=pl.List(pl.Int128)),
                "s": pl.Series([-1, 4], dtype=pl.Int64),
            }
        )
    )
    af.by_policy = af.n > 2**100
    af.by_period = af.ns > 2**100
    af.unsigned = af.u > af.s
    out = af.collect()
    assert out["by_policy"].to_list() == [1.0, 0.0]
    assert out["by_period"].to_list() == [[1.0, 1.0], [0.0, 0.0]]
    assert out["unsigned"].to_list() == [1.0, 0.0]


def test_a_literal_past_i64_is_refused_everywhere_else() -> None:
    narrow = ActuarialFrame(pl.DataFrame({"pid": pl.Series([7, 8], dtype=pl.Int64)}))
    with pytest.raises(IntegerLiteralPastI64Error):
        narrow.r = narrow.pid == _PAST
    wide = _past()
    with pytest.raises(IntegerLiteralPastI64Error):
        wide.r = wide.pid + _PAST
    with pytest.raises(IntegerLiteralPastI64Error):
        wide.r = when(wide.pid == 7).then(_PAST).otherwise(0)


def test_a_membership_test_is_a_comparison() -> None:
    af = _past()
    af.member = af.pid.is_in([_PAST, 7])
    af.only_seven = af.pid.is_in([7])
    out = af.collect()
    assert out["member"].to_list() == [True, True]
    assert out["only_seven"].to_list() == [True, False]
    narrow = ActuarialFrame(pl.DataFrame({"pid": pl.Series([7, 8], dtype=pl.Int64)}))
    with pytest.raises(IntegerLiteralPastI64Error):
        narrow.r = narrow.pid.is_in([_PAST])


@pytest.mark.parametrize("lazy", [False, True], ids=["DataFrame", "LazyFrame"])
def test_a_substitution_over_a_fitting_wide_column_answers_int64(*, lazy: bool) -> None:
    af = _fits(lazy=lazy)
    af.r = af.pid.replace({7: 9})
    out = af.collect()
    assert out.schema["r"] == pl.Int64
    assert out["r"].to_list() == [9, 8]


@pytest.mark.parametrize("lazy", [False, True], ids=["DataFrame", "LazyFrame"])
def test_a_substitution_over_a_value_past_i64_is_refused_by_name(*, lazy: bool) -> None:
    af = _past(lazy=lazy)
    af.r = af.pid.replace({7: 9})
    with pytest.raises(Exception, match="outside the signed 64-bit range") as refused:
        af.collect()
    assert "an operation carrying it is refused" in str(refused.value)
    assert "Column 'pid'" in str(refused.value)


@pytest.mark.parametrize("lazy", [False, True], ids=["DataFrame", "LazyFrame"])
def test_a_band_over_a_fitting_wide_column_places_its_values(*, lazy: bool) -> None:
    af = _fits(lazy=lazy)
    af.band = af.pid.cut([7.5])
    assert af.collect()["band"].to_list() == ["(-inf, 7.5]", "(7.5, inf]"]


@pytest.mark.parametrize("lazy", [False, True], ids=["DataFrame", "LazyFrame"])
def test_a_band_over_a_value_past_i64_is_refused_by_name(*, lazy: bool) -> None:
    af = _past(lazy=lazy)
    af.band = af.pid.cut([10.0])
    with pytest.raises(Exception, match="placing it in a band is refused") as refused:
        af.collect()
    assert "to_text()" in str(refused.value)
