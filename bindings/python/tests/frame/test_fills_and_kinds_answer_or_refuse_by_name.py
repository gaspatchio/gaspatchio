# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A fill is one value at a time, and a value that is not a number is refused by name.

Three findings of one kind: lines the frame either answered wrongly or
refused in Polars' words.

- ``af.premium.fill_null(af.default_premium)`` over a per-period premium
  failed as ``SchemaError: failed to determine supertype of list[f64] and
  f64``, though 11.1.13 makes the fill an operand -- a scheme's own default
  -- and ``fill_nan`` answered the same line. And a per-period column fill
  replaced a policy whose whole run was missing while leaving a gap inside
  a run untouched, where 11.1.13 fills each period one value at a time.
- The numeric calls over text, a date, a date and time or a time of day
  failed in Polars' words (```cum_sum` operation not supported for dtype
  `str```) or were answered: ``af.code.exp()`` read "2.0" as a number,
  ``af.issue.log()`` took the logarithm of a day count and a run of text
  averaged to null.
- A ``UInt64`` value past ``i64`` in a conditional's branch failed as
  ``conversion from `u64` to `i64` failed``, and under ``log``, ``sqrt`` and
  the other maths calls was answered, where section 10 refuses every read
  that carries it into a double by name.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable

_ENGINES = ["in-memory", "streaming"]

# Premiums with a gap, a policy with a gap first, and a policy with no run.
_PREMIUMS = pl.DataFrame(
    [
        pl.Series(
            "premium",
            [[100.0, None, 100.0], [None, 50.0, 50.0], None],
            dtype=pl.List(pl.Float64),
        ),
        pl.Series("default_premium", [90.0, 45.0, 7.0]),
        pl.Series(
            "quoted",
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]],
            dtype=pl.List(pl.Float64),
        ),
        pl.Series("term", [[1, None, 3], None, [None, 2, 2]], dtype=pl.List(pl.Int64)),
        pl.Series("default_term", [10, 20, 30]),
    ]
)


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_per_policy_column_fills_every_missing_period_of_its_policy(
    engine: str,
) -> None:
    af = ActuarialFrame(_PREMIUMS)
    af.filled = af.premium.fill_null(af.default_premium)
    af.filled_by_expression = af.premium.fill_null(af.default_premium * 1.0)
    af.whole = af.term.fill_null(af.default_term)
    out = af.collect(engine=engine)  # type: ignore[arg-type]
    expected = [[100.0, 90.0, 100.0], [45.0, 50.0, 50.0], None]
    assert out["filled"].to_list() == expected
    assert out["filled_by_expression"].to_list() == expected
    assert out.schema["whole"] == pl.List(pl.Int64)
    assert out["whole"].to_list() == [[1, 10, 3], None, [30, 2, 2]]


@pytest.mark.parametrize("engine", _ENGINES)
def test_a_per_period_column_fills_the_same_period_and_leaves_no_run_alone(
    engine: str,
) -> None:
    """Was ``[[100.0, None, 100.0], [None, 50.0, 50.0], [7.0, 8.0, 9.0]]``."""
    af = ActuarialFrame(_PREMIUMS)
    af.filled = af.premium.fill_null(af.quoted)
    out = af.collect(engine=engine)  # type: ignore[arg-type]
    assert out["filled"].to_list() == [[100.0, 2.0, 100.0], [4.0, 50.0, 50.0], None]


def test_fill_null_and_fill_nan_answer_a_column_fill_alike() -> None:
    nan = math.nan
    book = _PREMIUMS.with_columns(
        pl.Series(
            "premium_nan",
            [[100.0, nan, 100.0], [nan, 50.0, 50.0], None],
            dtype=pl.List(pl.Float64),
        )
    )
    af = ActuarialFrame(book)
    af.by_null = af.premium.fill_null(af.default_premium)
    af.by_nan = af.premium_nan.fill_nan(af.default_premium)
    out = af.collect()
    assert out["by_null"].to_list() == out["by_nan"].to_list()


@pytest.mark.parametrize("fill", ["fill_null", "fill_nan"])
def test_a_run_filling_one_value_is_refused_by_name(fill: str) -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            [
                pl.Series("rate", [None, 0.5]),
                pl.Series(
                    "quoted", [[1.0, 2.0], [3.0, 4.0]], dtype=pl.List(pl.Float64)
                ),
            ]
        )
    )
    with pytest.raises(TypeError, match=rf"{fill}\(\): the value it fills .* one per"):
        af.r = getattr(af.rate, fill)(af.quoted)


_ODD = pl.DataFrame(
    [
        pl.Series("n", [3, 4]),
        pl.Series("periods", [[1, 2], [3, 4]], dtype=pl.List(pl.Int64)),
        pl.Series("code", ["A", "2.0"]),
        pl.Series("codes", [["1", "2"], ["a", "3"]], dtype=pl.List(pl.String)),
        pl.Series("issue", [date(1970, 1, 2), date(2024, 2, 29)]),
        pl.Series(
            "stamp",
            [datetime(2025, 1, 1, 1), datetime(2025, 1, 2)],  # noqa: DTZ001 -- zone-naive on purpose
        ),
        pl.Series(
            "rate_dec", [Decimal("1.0050"), Decimal("2.5000")], dtype=pl.Decimal(20, 4)
        ),
        pl.Series(
            "rates_dec",
            [[Decimal("1.5")], [Decimal("2.5")]],
            dtype=pl.List(pl.Decimal(20, 4)),
        ),
    ]
)
_REFUSED: dict[str, tuple[Callable[[ActuarialFrame], object], str]] = {
    "a running sum of text": (
        lambda af: af.codes.cum_sum(),
        r"cum_sum\(\): the value it reads",
    ),
    "a total of text": (lambda af: af.codes.list.sum(), r"sum\(\): the value it reads"),
    "an average of text": (
        lambda af: af.codes.list.mean(),
        r"mean\(\): the value it reads",
    ),
    "the exponential of text": (
        lambda af: af.code.exp(),
        r"exp\(\): the value it reads",
    ),
    "the logarithm of a date": (
        lambda af: af.issue.log(),
        r"log\(\): the value it reads",
    ),
    "the absolute value of a date": (
        lambda af: af.issue.abs(),
        r"abs\(\): the value it reads",
    ),
    "the sign of text": (lambda af: af.code.sign(), r"sign\(\): the value it reads"),
    "survival over text": (
        lambda af: af.codes.projection.cumulative_survival(),
        r"cumulative_survival\(\): the value it reads",
    ),
}


@pytest.mark.parametrize("line", list(_REFUSED))
def test_a_value_that_is_not_a_number_is_refused_where_it_is_written(line: str) -> None:
    make, words = _REFUSED[line]
    af = ActuarialFrame(_ODD)
    with pytest.raises(TypeError, match=words):
        af.r = make(af)


@pytest.mark.parametrize(
    "line",
    [
        lambda af: af.rate_dec + af.n,
        lambda af: af.rate_dec * 1.0,
        lambda af: af.rate_dec // 2.0,
        lambda af: af.rates_dec.cum_prod(),
        lambda af: af.n + 1,
    ],
    ids=[
        "a decimal plus a number",
        "a decimal times a double",
        "a decimal floor by a double",
        "a running product of decimals, read as doubles where they entered",
        "a control",
    ],
)
def test_the_arithmetic_an_engine_has_is_still_answered(
    line: Callable[[ActuarialFrame], object],
) -> None:
    af = ActuarialFrame(_ODD)
    af.r = line(af)
    assert af.collect()["r"].len() == 2


_WIDE = pl.DataFrame(
    [
        pl.Series("polno", [2**63, 5], dtype=pl.UInt64),
        pl.Series("n", [1, 2], dtype=pl.Int32),
        pl.Series("smoker", [True, False]),
    ]
)


@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
@pytest.mark.parametrize(
    "line",
    [
        lambda af: when(af.smoker).then(af.polno).otherwise(af.n),
        lambda af: when(af.smoker).then(af.n).otherwise(af.polno),
        lambda af: af.polno.log(),
        lambda af: af.polno.log10(),
        lambda af: af.polno.sqrt(),
        lambda af: af.polno.exp(),
        lambda af: af.polno.norm_cdf(),
    ],
    ids=["then", "otherwise", "log", "log10", "sqrt", "exp", "norm_cdf"],
)
def test_a_whole_number_past_i64_is_refused_by_name_where_it_is_carried(
    door: str, line: Callable[[ActuarialFrame], object]
) -> None:
    af = ActuarialFrame(_WIDE if door == "DataFrame" else _WIDE.lazy())
    af.r = line(af)
    with pytest.raises(
        pl.exceptions.InvalidOperationError,
        match=r"^Column 'polno' holds a whole number outside the signed 64-bit range",
    ):
        af.collect()


@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_a_wide_column_whose_values_fit_is_still_answered(door: str) -> None:
    book = _WIDE.with_columns(pl.Series("polno", [7, 5], dtype=pl.UInt64))
    af = ActuarialFrame(book if door == "DataFrame" else book.lazy())
    af.chosen = when(af.smoker).then(af.polno).otherwise(af.n)
    af.root = af.polno.sqrt()
    out = af.collect()
    assert out["chosen"].to_list() == [7, 2]
    assert out["root"].to_list() == [math.sqrt(7), math.sqrt(5)]
