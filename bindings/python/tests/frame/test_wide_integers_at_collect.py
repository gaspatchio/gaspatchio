# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A book handed over as a plan has its wide columns judged when it is collected.

A ``UInt64``, ``Int128`` or ``UInt128`` book column whose values fit is read as
``Int64`` where a DataFrame enters the frame (section 10). A LazyFrame's values
are not in hand there, so the same column kept its width through the run, and
a column no line read -- a policy number carried to the results -- came back
``UInt64`` from the one door and ``Int64`` from the other. Its values are in
hand when the frame is collected, so the rule is applied there, and the two
doors hand back one schema. A plan's own schema, before the run, still shows
the width it arrived in: no value had been read to say otherwise.
"""

from __future__ import annotations

import datetime

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_WIDE = [pl.UInt64, pl.Int128, pl.UInt128]
_PAST = {pl.UInt64: 2**64 - 1, pl.Int128: -(2**70), pl.UInt128: 2**64 - 1}


def _passenger(af: ActuarialFrame) -> ActuarialFrame:
    af.r = af.amt * 2
    return af


@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_a_lazily_handed_passenger_that_fits_comes_back_int64(
    width: type[pl.DataType],
) -> None:
    """The eager door made it Int64; the lazy one returned it in its width."""
    book = pl.DataFrame({"pid": pl.Series([7, 8], dtype=width), "amt": [2.0, 3.0]})
    eager = _passenger(ActuarialFrame(book)).collect()
    lazy_frame = _passenger(ActuarialFrame(book.lazy()))
    lazy = lazy_frame.collect()

    assert lazy.schema == eager.schema
    assert lazy.schema["pid"] == pl.Int64
    assert lazy["pid"].to_list() == [7, 8]


def test_a_lazily_handed_passenger_is_judged_after_a_projection_too() -> None:
    book = pl.DataFrame({"pid": pl.Series([7, 8], dtype=pl.UInt64), "amt": [2.0, 3.0]})
    af = _passenger(ActuarialFrame(book.lazy())).projection.set(
        start_date=datetime.date(2025, 1, 1), n_periods=1, frequency="monthly"
    )

    assert af.collect().schema["pid"] == pl.Int64


@pytest.mark.parametrize("width", _WIDE, ids=str)
def test_a_lazily_handed_passenger_past_i64_keeps_its_width_and_digits(
    width: type[pl.DataType],
) -> None:
    past = _PAST[width]
    book = pl.DataFrame({"pid": pl.Series([7, past], dtype=width), "amt": [2.0, 3.0]})
    lazy = _passenger(ActuarialFrame(book.lazy())).collect()

    assert lazy.schema["pid"] == width
    assert lazy["pid"].to_list() == [7, past]


def test_a_plan_s_schema_before_the_run_still_shows_the_width_it_arrived_in() -> None:
    """What the two doors cannot share: no value has been read to judge by."""
    book = pl.DataFrame({"pid": pl.Series([7, 8], dtype=pl.UInt64)})

    assert ActuarialFrame(book.lazy()).schema["pid"] == pl.UInt64
    assert ActuarialFrame(book).schema["pid"] == pl.Int64
