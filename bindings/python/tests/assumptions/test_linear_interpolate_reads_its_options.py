# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``LinearInterpolate(extrapolate=..., fill_gaps=...)`` do what they say.

Both fields were declared and never read: ``extrapolate=True`` left a
trailing blank blank (a lookup then refused it as "missing keys", or, with
``on_missing`` set, answered NaN or the fill instead of 0.05), and
``fill_gaps=False`` still filled the interior. ``extrapolate`` now extends the
line through the two nearest values past the first and last, ``fill_gaps``
fills between values only when asked, and a fill asked to fill nothing is
refused.
"""

from __future__ import annotations

import math
from fractions import Fraction

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import LinearInterpolate, MeltDimension, Table

# age 40: durations 2 and 4 hold values; 1, 3 and 5 are blank.
# age 41: durations 1, 3 and 4 hold values; 2 and 5 are blank.
SRC = pl.DataFrame(
    {
        "age": [40, 41],
        "1": [None, 0.02],
        "2": [0.010, None],
        "3": [None, 0.04],
        "4": [0.030, 0.05],
        "5": [None, None],
    },
    schema_overrides=dict.fromkeys("12345", pl.Float64),
)


def _rates(fill: LinearInterpolate, name: str) -> list[float | None]:
    table = Table(
        name=name,
        source=SRC,
        dimensions={
            "age": "age",
            "dur": MeltDimension(list("12345"), name="dur", fill=fill),
        },
        value="rate",
        on_missing="nan",
    )
    af = ActuarialFrame(
        pl.DataFrame({"age": [40] * 5 + [41] * 5, "dur": [1, 2, 3, 4, 5] * 2})
    )
    af.r = table.lookup(age=af.age, dur=af.dur)
    return [None if math.isnan(v) else v for v in af.collect()["r"].to_list()]


def _f(*values: str | None) -> list[float | None]:
    return [None if v is None else float(Fraction(v)) for v in values]


def test_extrapolate_extends_the_line_past_the_first_and_last_value() -> None:
    got = _rates(LinearInterpolate(extrapolate=True), "lio_extrapolate")
    hand = _f(
        "0",
        "1/100",
        "2/100",
        "3/100",
        "4/100",
        "2/100",
        "3/100",
        "4/100",
        "5/100",
        "6/100",
    )
    assert got == pytest.approx(hand, abs=1e-15)


def test_fill_gaps_false_leaves_the_interior_blank() -> None:
    got = _rates(LinearInterpolate(fill_gaps=False, extrapolate=True), "lio_ends_only")
    hand = _f(
        "0", "1/100", None, "3/100", "4/100", "2/100", None, "4/100", "5/100", "6/100"
    )
    assert got == pytest.approx(hand, abs=1e-15)


def test_the_default_fills_between_values_and_not_past_them() -> None:
    got = _rates(LinearInterpolate(), "lio_default")
    hand = _f(
        None, "1/100", "2/100", "3/100", None, "2/100", "3/100", "4/100", "5/100", None
    )
    assert got == pytest.approx(hand, abs=1e-15)


def test_log_linear_extrapolates_in_log_space() -> None:
    got = _rates(LinearInterpolate(method="log-linear", extrapolate=True), "lio_log")
    trailing_41 = math.exp(math.log(0.05) + (math.log(0.05) - math.log(0.04)))
    assert got[9] == pytest.approx(trailing_41, rel=1e-12)
    assert got[0] == pytest.approx(0.01 * math.sqrt(0.01 / 0.03), rel=1e-12)


def test_a_fill_asked_to_fill_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match=r"fills no blank"):
        LinearInterpolate(fill_gaps=False)


def test_one_value_has_no_line_to_extend() -> None:
    lone = pl.DataFrame(
        {"age": [40], "1": [None], "2": [0.01], "3": [None]},
        schema_overrides=dict.fromkeys("123", pl.Float64),
    )
    table = Table(
        name="lio_lone",
        source=lone,
        dimensions={
            "age": "age",
            "dur": MeltDimension(
                list("123"), name="dur", fill=LinearInterpolate(extrapolate=True)
            ),
        },
        value="rate",
        on_missing="nan",
    )
    af = ActuarialFrame(pl.DataFrame({"age": [40, 40, 40], "dur": [1, 2, 3]}))
    af.r = table.lookup(age=af.age, dur=af.dur)
    got = af.collect()["r"].to_list()
    assert got[1] == 0.01
    assert math.isnan(got[0])
    assert math.isnan(got[2])
