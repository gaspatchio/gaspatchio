# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A rollforward reads a book column wider than ``i64`` as arithmetic reads one.

The kernel reads its opening balances and its step amounts as doubles, so a
``UInt64`` input holding 2**64 - 1 entered the run as 1.8446744073709552e19
and every premium added after it was lost in the rounding, and a ``UInt128``
one stopped the plan with a panic. A rollforward step is arithmetic on the
column, so section 10's rule holds: an input whose values fit is the ``Int64``
it is, and one holding a value past that range refuses the run by name,
whichever door the book came in by.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.rollforward import compile_rollforward

_WIDE = [pl.UInt64, pl.Int128, pl.UInt128]
_PAST = {pl.UInt64: 2**64 - 1, pl.Int128: -(2**70), pl.UInt128: 2**64 - 1}


def _door(book: pl.DataFrame, door: str) -> ActuarialFrame:
    return ActuarialFrame(book if door == "DataFrame" else book.lazy())


def _rollforward(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        start_date=datetime.date(2025, 12, 31), n_periods=3, frequency="annual"
    )
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].add(af["premium"]).grow(af["rate"])
    af.av = compile_rollforward(b).expr_for("av")
    return af


def _rollforward_book(
    width: type[pl.DataType], init: list[int], premium: list[list[int]]
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "av_init": pl.Series(init, dtype=width),
            "premium": pl.Series(premium, dtype=pl.List(width)),
            "rate": [[0.0] * 3, [0.0] * 3],
        }
    )


@pytest.mark.parametrize("past_in", ["av_init", "premium"])
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_a_rollforward_reading_a_value_past_i64_is_refused_by_name(
    width: type[pl.DataType], door: str, past_in: str
) -> None:
    """It entered the run as its nearest double, and the premiums after it were lost."""
    past = _PAST[width]
    init = [100, past] if past_in == "av_init" else [100, 5]
    premium = (
        [[1, 2, 3], [past, 5, 6]] if past_in == "premium" else [[1, 2, 3], [4, 5, 6]]
    )
    af = _rollforward(_door(_rollforward_book(width, init, premium), door))

    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()

    assert str(caught.value).startswith(
        f"Column {past_in!r} holds a whole number outside the signed 64-bit range, "
        "and a rollforward reading it is refused."
    )


@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
@pytest.mark.parametrize("width", [*_WIDE, pl.Int64], ids=str)
def test_a_rollforward_over_a_wide_column_that_fits_runs_as_over_int64(
    width: type[pl.DataType], door: str
) -> None:
    """Hand values: 100 + 1, + 2, + 3 and 5 + 4, + 5, + 6, at a rate of nought."""
    book = _rollforward_book(width, [100, 5], [[1, 2, 3], [4, 5, 6]])
    out = _rollforward(_door(book, door)).collect()

    assert out["av"].to_list() == [[101.0, 103.0, 106.0], [9.0, 14.0, 20.0]]
