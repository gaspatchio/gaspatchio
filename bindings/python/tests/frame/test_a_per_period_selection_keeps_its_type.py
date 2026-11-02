# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period conditional answers the type its branches share, and every bit of it.

The per-period route selects through a kernel that works in doubles, and it
typed the answer back only for whole numbers, flags and calendar dates. Two
dates and times came back as ``list[f64]`` counts of microseconds (or
nanoseconds), so the record said ``list[f64]`` for a column the per-policy
form of the same line held as a date and time, and a nanosecond count lost
its last digits. A duration and a time of day did the same, a Categorical
or Enum pair came back as plain text, a decimal pair as doubles, and two
``None`` branches as ``list[f64]`` where the per-policy form is a null with
no type, which section 10 refuses at export. A 128-bit whole number selected
through two 32-bit halves kept its bits only while it stayed under 2**85,
and an unsigned one made the kernel panic.

Each pair now answers the type ``pl.when`` gives it on the per-policy route,
and every value is selected as the whole number it is held as, 32 bits at a
time. Two branches of one kind whose types have nothing in common -- a
zone-naive date and time opposite a zoned one, a Categorical opposite an
Enum -- are refused where the line is written, on both routes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_ZONE = "Pacific/Auckland"
# 2025-01-01T00:00:00Z in microseconds, and in nanoseconds.
_US = 1_735_689_600_000_000
_NS = _US * 1000

# The per-period condition: month 0 takes the otherwise branch, months 1 and
# 2 the then branch. The per-policy one: the first policy takes otherwise.
_MONTHS = [[0, 1, 2], [0, 1, 2]]
_X = [1.5, 3.5]


def _counts(values: list[Any], dtype: pl.DataType) -> pl.Series:
    """Build a column from whole-number counts read as ``dtype``."""
    inner = pl.List(pl.Int64) if isinstance(dtype, pl.List) else pl.Int64
    return pl.Series(values, dtype=inner).cast(dtype)


def _frame(**columns: pl.Series) -> ActuarialFrame:
    book = pl.DataFrame(
        {
            "pid": [1, 2],
            "x": _X,
            "m": pl.Series(_MONTHS, dtype=pl.List(pl.Int64)),
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


_NS_ZONED = pl.Datetime("ns", _ZONE)

# (what the author wrote, the then run, the otherwise run, the answer's type,
# the hand values as counts of the type's unit, the record's type).
_PAIRS: list[tuple[str, pl.Series, pl.Series, pl.DataType, list[list[Any]], str]] = [
    (
        "two microsecond dates and times",
        _counts(
            [[_US + 1, _US + 2, _US + 3], [7, 2**55 + 3, -(2**55) - 1]],
            pl.List(pl.Datetime("us")),
        ),
        _counts([[_US + 9] * 3, [_US + 11] * 3], pl.List(pl.Datetime("us"))),
        pl.List(pl.Datetime("us")),
        [[_US + 9, _US + 2, _US + 3], [_US + 11, 2**55 + 3, -(2**55) - 1]],
        "list[datetime]",
    ),
    (
        "two nanosecond dates and times in one zone",
        _counts(
            [[_NS + 1, _NS + 2, _NS + 3], [5, 2**62 + 1, -(2**62) - 3]],
            pl.List(_NS_ZONED),
        ),
        _counts([[_NS + 9] * 3, [_NS + 11] * 3], pl.List(_NS_ZONED)),
        pl.List(_NS_ZONED),
        [[_NS + 9, _NS + 2, _NS + 3], [_NS + 11, 2**62 + 1, -(2**62) - 3]],
        "list[datetime]",
    ),
]


@pytest.mark.parametrize(
    ("written", "then", "otherwise", "dtype", "expected", "recorded"),
    _PAIRS,
    ids=[pair[0] for pair in _PAIRS],
)
def test_two_dates_and_times_answer_a_date_and_time_in_their_unit_and_zone(  # noqa: PLR0913, PLR0917 -- one parameter per column of the table
    written: str,  # noqa: ARG001 -- the id
    then: pl.Series,
    otherwise: pl.Series,
    dtype: pl.DataType,
    expected: list[list[int]],
    recorded: str,
) -> None:
    af = _frame(t=then, o=otherwise)
    answer = _answer(af, lambda af: when(af.m > 0).then(af.t).otherwise(af.o))

    assert answer.dtype == dtype
    assert answer.to_physical().to_list() == expected
    assert _record_dtype(af) == recorded


_ROUTES: list[tuple[str, Callable[[Any], Any], list[list[int | None]]]] = [
    (
        "a None then branch",
        lambda af: when(af.m > 0).then(None).otherwise(af.t),
        [[_NS + 1, None, None], [5, None, None]],
    ),
    (
        "a None otherwise branch",
        lambda af: when(af.m > 0).then(af.t).otherwise(None),
        [[None, _NS + 2, _NS + 3], [None, 2**62 + 1, -(2**62) - 3]],
    ),
    (
        "one flag per policy",
        lambda af: when(af.x > 2).then(af.t).otherwise(af.o),
        [[_NS + 9] * 3, [5, 2**62 + 1, -(2**62) - 3]],
    ),
    (
        "a chain",
        lambda af: when(af.m > 1).then(af.t).when(af.m > 0).then(af.o).otherwise(af.t),
        [[_NS + 1, _NS + 9, _NS + 3], [5, _NS + 11, -(2**62) - 3]],
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "expected"), _ROUTES, ids=[route[0] for route in _ROUTES]
)
def test_a_date_and_time_keeps_its_type_on_every_per_period_route(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[list[int | None]],
) -> None:
    then = _counts(
        [[_NS + 1, _NS + 2, _NS + 3], [5, 2**62 + 1, -(2**62) - 3]], pl.List(_NS_ZONED)
    )
    otherwise = _counts([[_NS + 9] * 3, [_NS + 11] * 3], pl.List(_NS_ZONED))
    af = _frame(t=then, o=otherwise)

    answer = _answer(af, line)

    assert answer.dtype == pl.List(_NS_ZONED)
    assert answer.to_physical().to_list() == expected


def test_a_null_policy_and_an_empty_one_keep_their_shape() -> None:
    """A null run stays null and an empty run stays empty, as 11.1.28 states."""
    stamps = pl.List(pl.Datetime("us"))
    book = pl.DataFrame(
        {
            "m": pl.Series([[0, 1], None, []], dtype=pl.List(pl.Int64)),
            "t": _counts([[_US + 1, None], [1, 2], []], stamps),
            "o": _counts([[_US + 9, 2**55 + 1], [3, 4], []], stamps),
        }
    )
    af = ActuarialFrame(book)

    answer = _answer(af, lambda af: when(af.m > 0).then(af.t).otherwise(af.o))

    assert answer.dtype == stamps
    assert answer.to_physical().to_list() == [[_US + 9, None], None, []]


_OTHER_KINDS: list[tuple[str, pl.Series, pl.Series, pl.DataType, list[list[Any]]]] = [
    (
        "two nanosecond durations",
        _counts(
            [[2**62 + 1, 2, 3], [-(2**60) - 1, 0, 2**53 + 1]],
            pl.List(pl.Duration("ns")),
        ),
        _counts([[9] * 3, [11] * 3], pl.List(pl.Duration("ns"))),
        pl.List(pl.Duration("ns")),
        [[9, 2, 3], [11, 0, 2**53 + 1]],
    ),
    (
        "two times of day",
        _counts(
            [[86_399_999_999_999, 2, 3], [43_200_000_000_001, 0, 1]], pl.List(pl.Time)
        ),
        _counts([[9] * 3, [11] * 3], pl.List(pl.Time)),
        pl.List(pl.Time),
        [[9, 2, 3], [11, 0, 1]],
    ),
    (
        "two 128-bit whole numbers past 2**85",
        pl.Series(
            [[2**100 + 1, -(2**126) - 1, 2**86 + 3], [2**127 - 1, -(2**127), 7]],
            dtype=pl.List(pl.Int128),
        ),
        pl.Series(
            [[1, 2, 3], [2**90 + 1, -(2**90) - 1, 2**64]], dtype=pl.List(pl.Int128)
        ),
        pl.List(pl.Int128),
        [[1, -(2**126) - 1, 2**86 + 3], [2**90 + 1, -(2**127), 7]],
    ),
    (
        "two unsigned 128-bit whole numbers",
        pl.Series(
            [[2**128 - 1, 2**127 + 1, 2**86 + 5], [1, 2, 3]], dtype=pl.List(pl.UInt128)
        ),
        pl.Series([[4, 5, 6], [2**90 + 7, 8, 2**64]], dtype=pl.List(pl.UInt128)),
        pl.List(pl.UInt128),
        [[4, 2**127 + 1, 2**86 + 5], [2**90 + 7, 2, 3]],
    ),
    (
        "two Categorical labels",
        pl.Series([["a", "b", "c"], ["d", "e", "f"]]).cast(pl.List(pl.Categorical)),
        pl.Series([["u", "v", "w"], ["x", "y", "z"]]).cast(pl.List(pl.Categorical)),
        pl.List(pl.Categorical),
        [["u", "b", "c"], ["x", "e", "f"]],
    ),
    (
        "two Enum labels",
        pl.Series([["a", "b", "c"], ["a", "b", "c"]]).cast(
            pl.List(pl.Enum(["a", "b", "c", "z"]))
        ),
        pl.Series([["z"] * 3, ["z"] * 3]).cast(pl.List(pl.Enum(["a", "b", "c", "z"]))),
        pl.List(pl.Enum(["a", "b", "c", "z"])),
        [["z", "b", "c"], ["z", "b", "c"]],
    ),
]


@pytest.mark.parametrize(
    ("written", "then", "otherwise", "dtype", "expected"),
    _OTHER_KINDS,
    ids=[pair[0] for pair in _OTHER_KINDS],
)
def test_every_other_pair_of_one_kind_answers_its_own_type_exactly(
    written: str,  # noqa: ARG001 -- the id
    then: pl.Series,
    otherwise: pl.Series,
    dtype: pl.DataType,
    expected: list[list[Any]],
) -> None:
    af = _frame(t=then, o=otherwise)
    answer = _answer(af, lambda af: when(af.m > 0).then(af.t).otherwise(af.o))

    held = answer.to_physical() if dtype.inner.is_temporal() else answer  # type: ignore[union-attr]
    assert answer.dtype == dtype
    assert held.to_list() == expected


def test_two_null_branches_carry_no_type_and_are_refused_at_export() -> None:
    """Per period as per policy: nulls with no type, which section 10 refuses."""
    af = _frame()
    answer = _answer(af, lambda af: when(af.m > 0).then(None).otherwise(None))

    assert answer.dtype == pl.List(pl.Null)
    assert answer.to_list() == [[None] * 3, [None] * 3]
    with pytest.raises(UnmappedDtypeError, match="Null"):
        GraphExporter(af).export(profile="executable")


_APART: list[tuple[str, dict[str, pl.Series], Callable[[Any], Any]]] = [
    (
        "a zone-naive and a zoned date and time, per period",
        {
            "t": _counts([[1, 2, 3]] * 2, pl.List(pl.Datetime("ns"))),
            "o": _counts([[1, 2, 3]] * 2, pl.List(_NS_ZONED)),
        },
        lambda af: when(af.m > 0).then(af.t).otherwise(af.o),
    ),
    (
        "a zone-naive and a zoned date and time, per policy",
        {
            "t": _counts([1, 2], pl.Datetime("ns")),
            "o": _counts([1, 2], _NS_ZONED),
        },
        lambda af: when(af.x > 2).then(af.t).otherwise(af.o),
    ),
    (
        "a Categorical and an Enum, per period",
        {
            "t": pl.Series([["a"] * 3] * 2).cast(pl.List(pl.Categorical)),
            "o": pl.Series([["a"] * 3] * 2).cast(pl.List(pl.Enum(["a"]))),
        },
        lambda af: when(af.m > 0).then(af.t).otherwise(af.o),
    ),
    (
        "a Categorical and an Enum, per policy",
        {
            "t": pl.Series(["a", "a"]).cast(pl.Categorical),
            "o": pl.Series(["a", "a"]).cast(pl.Enum(["a"])),
        },
        lambda af: when(af.x > 2).then(af.t).otherwise(af.o),
    ),
]


@pytest.mark.parametrize(
    ("written", "columns", "line"), _APART, ids=[pair[0] for pair in _APART]
)
def test_one_kind_in_two_types_with_nothing_in_common_is_refused_by_name(
    written: str,  # noqa: ARG001 -- the id
    columns: dict[str, pl.Series],
    line: Callable[[Any], Any],
) -> None:
    af = _frame(**columns)

    with pytest.raises(TypeError, match="have nothing in common") as refused:
        af.r = line(af)

    assert "the column 'o'" in str(refused.value)


def test_an_unsigned_value_past_i64_beside_an_i64_run_fails_rather_than_null() -> None:
    """The per-period route answered a null; it is refused by name (section 10)."""
    af = _frame(
        t=pl.Series([[1, 2**64 - 1, 3]] * 2, dtype=pl.List(pl.UInt64)),
        o=pl.Series([[4, 5, 6]] * 2, dtype=pl.List(pl.Int64)),
    )
    af.r = when(af.m > 0).then(af.t).otherwise(af.o)

    with pytest.raises(
        pl.exceptions.InvalidOperationError,
        match=r"^Column 't' holds a whole number outside the signed 64-bit range",
    ):
        af.collect()


def test_a_date_and_time_per_policy_is_unchanged() -> None:
    """The guard: the per-policy route already answered the pair's own type."""
    af = _frame(
        t=_counts([_NS + 1, 2**62 + 1], _NS_ZONED), o=_counts([_NS + 9, 5], _NS_ZONED)
    )
    answer = _answer(af, lambda af: when(af.x > 2).then(af.t).otherwise(af.o))

    assert answer.dtype == _NS_ZONED
    assert answer.to_physical().to_list() == [_NS + 9, 2**62 + 1]
