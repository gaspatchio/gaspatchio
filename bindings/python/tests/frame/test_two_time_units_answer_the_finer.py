# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A conditional of two time units answers the finer, losing no digit.

A conditional whose branches were a date and time in microseconds and one in
milliseconds -- or a Python ``datetime`` literal, held in microseconds, beside
a nanosecond column -- answered Polars' coarser unit on both routes, so the
finer branch lost its last digits without a word: 2025-01-01 00:00:00.627779
came back as .627. Two durations did the same. The pair now answers the
finer unit, losslessly, per policy and per period; a value the finer unit
cannot hold (a nanosecond count stops at 2262) refuses the run by name.

Hand values are counts of the finer unit.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_ZONE = "Pacific/Auckland"
# 2025-01-01T00:00:00Z in microseconds, in milliseconds and in nanoseconds.
_US = 1_735_689_600_000_000
_MS = _US // 1000
_NS = _US * 1000
# 2040-01-01T00:00:00.000007 as a Python literal, and its microsecond count;
# 9999-12-31, the open end date, which no nanosecond count reaches. Both are
# zone-naive, as the book's columns are.
_LITERAL = dt.datetime(2040, 1, 1, 0, 0, 0, 7)  # noqa: DTZ001
_LITERAL_US = 2_208_988_800_000_007
_OPEN_END = dt.datetime(9999, 12, 31)  # noqa: DTZ001


def _counts(values: list[Any], dtype: pl.DataType) -> pl.Series:
    """Build a column from whole-number counts read as ``dtype``."""
    inner = pl.List(pl.Int64) if isinstance(dtype, pl.List) else pl.Int64
    return pl.Series(values, dtype=inner).cast(dtype)


def _frame(**columns: pl.Series) -> ActuarialFrame:
    """Two policies: the first takes otherwise per policy, month 0 per period."""
    book = pl.DataFrame(
        {
            "pid": [1, 2],
            "x": [1.5, 3.5],
            "m": pl.Series([[0, 1, 2], [0, 1, 2]], dtype=pl.List(pl.Int64)),
            **columns,
        }
    )
    return ActuarialFrame(book)


def _answer(af: ActuarialFrame, line: Callable[[Any], Any]) -> pl.Series:
    af.r = line(af)
    return af.collect()["r"]


def _record_dtype(af: ActuarialFrame) -> str:
    document = json.loads(GraphExporter(af).export(profile="executable"))
    return next(node["dtype"] for node in document["nodes"] if node["column"] == "r")


# --- two time units ----------------------------------------------------------

_SCALARS = {
    "us": _counts([_US + 7, _US + 627_779], pl.Datetime("us")),
    "ms": _counts([_MS + 3, _MS + 5], pl.Datetime("ms")),
    "ns": _counts([_NS + 9, _NS + 11], pl.Datetime("ns")),
    "ns_zoned": _counts([_NS + 9, _NS + 11], pl.Datetime("ns", _ZONE)),
    "us_zoned": _counts([_US + 7, _US + 13], pl.Datetime("us", _ZONE)),
    "runs_us": _counts(
        [[_US + 1, _US + 2, _US + 3], [_US + 4, _US + 5, _US + 6]],
        pl.List(pl.Datetime("us")),
    ),
    "runs_ms": _counts(
        [[_MS + 1, _MS + 2, _MS + 3], [7, 8, 9]], pl.List(pl.Datetime("ms"))
    ),
    "runs_ns": _counts(
        [[_NS + 1, _NS + 2, _NS + 3], [2**62 + 1, -(2**62) - 3, 5]],
        pl.List(pl.Datetime("ns")),
    ),
}

# (what the author wrote, the line, the answer's type, the hand values as
# counts of the finer unit).
_TIME_PAIRS: list[tuple[str, Callable[[Any], Any], pl.DataType, list[Any]]] = [
    (
        "per policy, microseconds beside milliseconds",
        lambda af: when(af.x > 2).then(af.us).otherwise(af.ms),
        pl.Datetime("us"),
        [(_MS + 3) * 1000, _US + 627_779],
    ),
    (
        "per policy, milliseconds beside microseconds",
        lambda af: when(af.x > 2).then(af.ms).otherwise(af.us),
        pl.Datetime("us"),
        [_US + 7, (_MS + 5) * 1000],
    ),
    (
        "per policy, a datetime literal beside nanoseconds",
        lambda af: when(af.x > 2).then(_LITERAL).otherwise(af.ns),
        pl.Datetime("ns"),
        [_NS + 9, _LITERAL_US * 1000],
    ),
    (
        "per policy, two zoned units",
        lambda af: when(af.x > 2).then(af.ns_zoned).otherwise(af.us_zoned),
        pl.Datetime("ns", _ZONE),
        [(_US + 7) * 1000, _NS + 11],
    ),
    (
        "per policy, a chain of three units",
        lambda af: (
            when(af.x > 3).then(af.ms).when(af.x > 2).then(af.us).otherwise(af.ns)
        ),
        pl.Datetime("ns"),
        [_NS + 9, (_MS + 5) * 1_000_000],
    ),
    (
        "per period, microseconds beside milliseconds",
        lambda af: when(af.m > 0).then(af.runs_us).otherwise(af.runs_ms),
        pl.List(pl.Datetime("us")),
        [[(_MS + 1) * 1000, _US + 2, _US + 3], [7000, _US + 5, _US + 6]],
    ),
    (
        "per period, one policy's milliseconds beside a nanosecond run",
        lambda af: when(af.x > 2).then(af.runs_ms).otherwise(af.runs_ns),
        pl.List(pl.Datetime("ns")),
        [[_NS + 1, _NS + 2, _NS + 3], [7_000_000, 8_000_000, 9_000_000]],
    ),
    (
        "per period, a datetime literal beside a nanosecond run",
        lambda af: when(af.m > 0).then(_LITERAL).otherwise(af.runs_ns),
        pl.List(pl.Datetime("ns")),
        [
            [_NS + 1, _LITERAL_US * 1000, _LITERAL_US * 1000],
            [2**62 + 1, _LITERAL_US * 1000, _LITERAL_US * 1000],
        ],
    ),
    (
        "per period, a chain of three units",
        lambda af: (
            when(af.m > 1)
            .then(af.runs_ms)
            .when(af.m > 0)
            .then(af.runs_us)
            .otherwise(af.ns)
        ),
        pl.List(pl.Datetime("ns")),
        [
            [_NS + 9, (_US + 2) * 1000, (_MS + 3) * 1_000_000],
            [_NS + 11, (_US + 5) * 1000, 9_000_000],
        ],
    ),
]


@pytest.mark.parametrize(
    ("line", "dtype", "hand"),
    [pair[1:] for pair in _TIME_PAIRS],
    ids=[pair[0] for pair in _TIME_PAIRS],
)
def test_two_time_units_answer_the_finer_without_losing_a_digit(
    line: Callable[[Any], Any], dtype: pl.DataType, hand: list[Any]
) -> None:
    af = _frame(**_SCALARS)
    answer = _answer(af, line)
    assert answer.dtype == dtype
    assert answer.to_physical().to_list() == hand
    record = "list[datetime]" if isinstance(dtype, pl.List) else "datetime"
    assert _record_dtype(af) == record


def test_two_duration_units_answer_the_finer_on_both_routes() -> None:
    af = _frame(
        us=_counts([2**40 + 3, -5], pl.Duration("us")),
        ns=_counts([2**53 + 1, 7], pl.Duration("ns")),
        runs=_counts(
            [[2**62 + 1, 2, 3], [-(2**60) - 1, 0, 2**53 + 1]],
            pl.List(pl.Duration("ns")),
        ),
    )
    per_policy = _answer(af, lambda af: when(af.x > 2).then(af.us).otherwise(af.ns))
    per_period = _answer(
        af,
        lambda af: (
            when(af.m > 0).then(dt.timedelta(days=1, microseconds=3)).otherwise(af.runs)
        ),
    )
    day = (86_400 * 10**6 + 3) * 1000
    assert per_policy.dtype == pl.Duration("ns")
    assert per_policy.to_physical().to_list() == [2**53 + 1, -5000]
    assert per_period.dtype == pl.List(pl.Duration("ns"))
    assert per_period.to_physical().to_list() == [
        [2**62 + 1, day, day],
        [-(2**60) - 1, day, day],
    ]


@pytest.mark.parametrize(
    ("line", "named"),
    [
        (
            lambda af: when(af.x > 2).then(_OPEN_END).otherwise(af.ns),
            "A branch of this conditional",
        ),
        (
            lambda af: when(af.m > 0).then(_OPEN_END).otherwise(af.runs_ns),
            "A branch of this conditional",
        ),
        (lambda af: when(af.x > 2).then(af.ns).otherwise(af.far), "Column 'far'"),
    ],
    ids=["a literal per policy", "a literal per period", "a column per policy"],
)
def test_a_value_the_finer_unit_cannot_hold_is_refused_by_name(
    line: Callable[[Any], Any], named: str
) -> None:
    far = _counts([253_402_214_400_000_000, _US], pl.Datetime("us"))  # 9999-12-31
    af = _frame(**_SCALARS, far=far)
    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        _answer(af, line)
    headline = str(refused.value).splitlines()[0]
    assert headline.startswith(named)
    assert "the finer of the conditional's two time units cannot hold" in headline
