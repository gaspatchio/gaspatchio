# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A whole number kept to its significant figures is kept exactly.

Section 11.1.12 calls ``round_sig_figs`` exact. Polars rounds the figures
through a double and casts back, so a whole number came back wrong well
inside the range a double names: 781,098 to one figure was 799,999,
8.5e15 was 8,999,999,999,999,999, and 2**63 - 1 to two figures was
9,199,999,999,999,998,976. The figures are now counted and cut in
whole-number arithmetic, a tie away from zero; an answer that rounds past
``i64`` is refused by name, and so is a column still wider than ``i64``.
"""

from __future__ import annotations

import datetime
import importlib
import sys
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_I64_MAX = 2**63 - 1
_I64_MIN = -(2**63)

# (value, figures, the hand value).
_HAND: list[tuple[int, int, int]] = [
    (781098, 1, 800000),
    (427160, 1, 400000),
    (8_500_000_000_000_000, 1, 9_000_000_000_000_000),
    (-125000, 2, -130000),
    (125000, 2, 130000),
    (124999, 2, 120000),
    (2**53 + 1, 2, 9_000_000_000_000_000),
    (_I64_MAX, 2, 9_200_000_000_000_000_000),
    (_I64_MIN, 1, -9_000_000_000_000_000_000),
    (12345, 5, 12345),
    (-7, 3, -7),
    (0, 1, 0),
]


@pytest.mark.parametrize(
    ("value", "figures", "expected"), _HAND, ids=[f"{v}@{d}" for v, d, _ in _HAND]
)
def test_a_whole_number_keeps_its_figures_exactly(
    value: int, figures: int, expected: int
) -> None:
    af = ActuarialFrame(pl.DataFrame({"n": [value]}))
    af.r = af.n.round_sig_figs(figures)
    out = af.collect()

    assert out.schema["r"] == pl.Int64
    assert out["r"].to_list() == [expected]


def test_a_run_of_whole_numbers_keeps_its_figures_exactly() -> None:
    book = pl.DataFrame({"n": [781098, None]})
    af = ActuarialFrame(book).projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=1, frequency="monthly"
    )
    af.run = af.n * 1 + af.month * 100000
    af.r = af.run.round_sig_figs(1)
    out = af.collect()

    assert out["r"].to_list() == [[800000, 900000], [None, None]]


def test_a_whole_number_that_rounds_past_i64_is_refused() -> None:
    """2**63 - 1 to ten figures is 9,223,372,037 x 10**9, past the range."""
    af = ActuarialFrame(pl.DataFrame({"n": [_I64_MAX]}))
    af.r = af.n.round_sig_figs(10)

    with pytest.raises(Exception, match="rounds, to the significant figures") as caught:
        af.collect()

    assert str(caught.value).startswith("Column 'n' holds a whole number that rounds")


@pytest.mark.parametrize("lazy", [False, True], ids=["DataFrame", "LazyFrame"])
def test_a_column_still_wider_than_i64_is_refused(*, lazy: bool) -> None:
    """2**64 - 1 to two figures was 17,999,999,999,999,997,952 through a double."""
    book = pl.DataFrame({"n": pl.Series([2**64 - 1], dtype=pl.UInt64)})
    af = ActuarialFrame(book.lazy() if lazy else book)
    af.r = af.n.round_sig_figs(2)

    with pytest.raises(
        Exception, match="rounding it to significant figures is refused"
    ):
        af.collect()


def test_a_double_beside_the_whole_numbers_is_read_as_its_fifteen_digits() -> None:
    af = ActuarialFrame(pl.DataFrame({"x": [1234.567, 0.001234567]}))
    af.r = af.x.round_sig_figs(3)

    assert af.collect()["r"].to_list() == [1230.0, 0.00123]


def _reader_elementary() -> Any:  # noqa: ANN401 -- the reader is untyped
    conformance = (
        Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
    )
    sys.path.insert(0, str(conformance))
    try:
        return importlib.import_module("reader.elementary")
    finally:
        sys.path.remove(str(conformance))


@pytest.mark.parametrize(
    ("value", "figures", "expected"), _HAND, ids=[f"{v}@{d}" for v, d, _ in _HAND]
)
def test_the_reference_reader_keeps_the_same_figures(
    value: int, figures: int, expected: int
) -> None:
    elementary = _reader_elementary()

    rounded = elementary.rounding(
        value, name="round_sig_figs", attrs={"digits": figures}
    )

    assert rounded == expected
    assert type(rounded) is int
