# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A comparison of two times held in different units answers in the finer unit.

Per policy, Polars compared a nanosecond date and time with a microsecond one
in the coarser unit, cutting the nanoseconds off first: ``N + 1`` nanoseconds
past an instant compared equal to that instant held in microseconds, and so
not later than it. The per-period route already read both as counts of the
finer unit, so the same line answered two ways depending on whether the
column was laid along periods. Both now read the finer unit, and a value no
nanosecond count holds -- the open-ended 9999-12-31 beside a nanosecond
column -- is compared exactly too, as it was on both routes before.

Hand values: ``N`` is 2025-01-01T00:00:00 as a count of nanoseconds, the
nanosecond column holds ``N + 1``, ``N`` and ``N - 1``, and the coarser
column holds ``N`` in its own unit for every policy.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable

_N = 1_735_689_600_000_000_000


def _frame(**columns: pl.Series) -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame(columns)).projection.set(
        start_date=dt.date(2025, 1, 1), n_periods=1, frequency="monthly"
    )


def _times(unit: str, counts: list[int], zone: str | None = None) -> pl.Series:
    return pl.Series(counts, dtype=pl.Int64).cast(pl.Datetime(unit, zone))  # type: ignore[arg-type]


def _both_routes(
    af: ActuarialFrame, line: Callable[[Any, Any], Any], left: str, right: str
) -> tuple[list[float], list[list[float]]]:
    """Return the comparison per policy, and with its left side laid along periods."""
    af.pol = line(af[left], af[right])
    af.run = when(af.month >= 0).then(af[left]).otherwise(af[left])
    af.per = line(af.run, af[right])
    out = af.collect()
    return out["pol"].to_list(), out["per"].to_list()


_SIX: list[tuple[str, Callable[[Any, Any], Any], list[float]]] = [
    ("gt", lambda a, b: a > b, [1.0, 0.0, 0.0]),
    ("ge", lambda a, b: a >= b, [1.0, 1.0, 0.0]),
    ("lt", lambda a, b: a < b, [0.0, 0.0, 1.0]),
    ("le", lambda a, b: a <= b, [0.0, 1.0, 1.0]),
    ("eq", lambda a, b: a == b, [0.0, 1.0, 0.0]),
    ("ne", lambda a, b: a != b, [1.0, 0.0, 1.0]),
]


@pytest.mark.parametrize(("name", "line", "hand"), _SIX, ids=[c[0] for c in _SIX])
def test_a_nanosecond_against_a_microsecond_column_compares_in_nanoseconds(
    name: str,  # noqa: ARG001 -- the id
    line: Callable[[Any, Any], Any],
    hand: list[float],
) -> None:
    af = _frame(
        ns=_times("ns", [_N + 1, _N, _N - 1]), us=_times("us", [_N // 1000] * 3)
    )
    per_policy, per_period = _both_routes(af, line, "ns", "us")
    assert per_policy == hand
    assert per_period == [[value, value] for value in hand]


def test_the_coarser_column_on_the_left_is_compared_in_the_finer_unit() -> None:
    af = _frame(
        ns=_times("ns", [_N + 1, _N, _N - 1]), us=_times("us", [_N // 1000] * 3)
    )
    per_policy, per_period = _both_routes(af, lambda a, b: a < b, "us", "ns")
    assert per_policy == [1.0, 0.0, 0.0]
    assert per_period == [[1.0, 1.0], [0.0, 0.0], [0.0, 0.0]]


def test_a_microsecond_against_a_millisecond_column_compares_in_microseconds() -> None:
    micro = _N // 1000
    af = _frame(
        us=_times("us", [micro + 1, micro, micro - 1]),
        ms=_times("ms", [_N // 1_000_000] * 3),
    )
    assert _both_routes(af, lambda a, b: a > b, "us", "ms")[0] == [1.0, 0.0, 0.0]
    assert _both_routes(af, lambda a, b: a == b, "us", "ms")[0] == [0.0, 1.0, 0.0]


def test_two_durations_in_different_units_compare_in_the_finer() -> None:
    af = _frame(
        dns=pl.Series([1001, 1000, 999], dtype=pl.Int64).cast(pl.Duration("ns")),
        dus=pl.Series([1, 1, 1], dtype=pl.Int64).cast(pl.Duration("us")),
    )
    per_policy, per_period = _both_routes(af, lambda a, b: a > b, "dns", "dus")
    assert per_policy == [1.0, 0.0, 0.0]
    assert per_period == [[1.0, 1.0], [0.0, 0.0], [0.0, 0.0]]


def test_two_zoned_times_in_different_units_compare_by_their_instants() -> None:
    af = _frame(
        a=_times("ns", [_N + 1, _N, _N - 1], "UTC"),
        b=_times("us", [_N // 1000] * 3, "Pacific/Auckland"),
    )
    per_policy, per_period = _both_routes(af, lambda a, b: a > b, "a", "b")
    assert per_policy == [1.0, 0.0, 0.0]
    assert per_period == [[1.0, 1.0], [0.0, 0.0], [0.0, 0.0]]


def test_a_conditional_over_the_comparison_selects_by_the_finer_unit() -> None:
    af = _frame(
        ns=_times("ns", [_N + 1, _N, _N - 1]), us=_times("us", [_N // 1000] * 3)
    )
    af.picked = when(af.ns > af.us).then(1.0).otherwise(0.0)
    assert af.collect()["picked"].to_list() == [1.0, 0.0, 0.0]


def test_a_value_the_finer_unit_cannot_hold_is_compared_exactly() -> None:
    """9999-12-31 in microseconds is past every nanosecond count, and is later."""
    af = _frame(
        end=pl.Series(
            [dt.datetime(9999, 12, 31), dt.datetime(2024, 1, 1)],  # noqa: DTZ001 -- zone-naive on purpose
            dtype=pl.Datetime("us"),
        ),
        ns=_times("ns", [_N, _N]),
    )
    per_policy, per_period = _both_routes(af, lambda a, b: a > b, "end", "ns")
    assert per_policy == [1.0, 0.0]
    assert per_period == [[1.0, 1.0], [0.0, 0.0]]


def test_one_unit_on_both_sides_answers_as_before() -> None:
    af = _frame(
        a=_times("us", [_N // 1000 + 1, _N // 1000]),
        b=_times("us", [_N // 1000] * 2),
    )
    assert _both_routes(af, lambda a, b: a > b, "a", "b")[0] == [1.0, 0.0]
