# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period comparison of whole numbers, dates and times and durations is exact.

The per-period route compares through a kernel that reads both sides as
doubles. A double names every whole number only up to 2**53, so past it two
neighbouring values became one: ``2**53 + 1 > 2**53`` answered false in every
period, ``2**63 - 1 > 2**63 - 2`` false, a nanosecond date and time one unit
after another compared equal to it, and a duration likewise -- where the same
line written per policy, compared by Polars in the values' own type, answered
each one exactly. Section 11.1.26 now states the six comparisons exact over
the whole range of the type they compare, on both routes.

The guards at the end pass before and after: a whole number beside a decimal
keeps the mixed rule 11.1.26 states, and dates, narrow whole numbers and
in-range values answer as they always did.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable

_BIG = 2**53
_TOP = 2**63 - 1
_LEAST = -(2**63)
# 2025-01-01T00:00:00Z in nanoseconds.
_NS = 1_735_689_600_000_000_000
_ZONE = "Pacific/Auckland"


def _book(**columns: pl.Series) -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame({"pid": [1, 2], **columns}))


def _run(n: int) -> list[int]:
    return [n, n, n]


def _indicator_and_selection(
    af: ActuarialFrame, line: Callable[[Any], Any]
) -> tuple[list[Any], list[Any]]:
    """Return the comparison assigned as a column, and a conditional over it."""
    af.ind = line(af)
    af.sel = when(line(af)).then(1).otherwise(0)
    out = af.collect()
    return out["ind"].to_list(), out["sel"].to_list()


def _as(indicator: list[list[float]]) -> list[list[int]]:
    return [[int(value) for value in row] for row in indicator]


# The six comparisons of a run of 2**53 + 1 (first policy) or 2**53 (second)
# against the literal 2**53, and the per-period answer each owes.
_SIX: list[tuple[str, Callable[[Any], Any], list[float]]] = [
    ("gt", lambda af: af.k > _BIG, [1.0, 0.0]),
    ("ge", lambda af: af.k >= _BIG + 1, [1.0, 0.0]),
    ("lt", lambda af: af.k < _BIG + 1, [0.0, 1.0]),
    ("le", lambda af: af.k <= _BIG, [0.0, 1.0]),
    ("eq", lambda af: af.k == _BIG, [0.0, 1.0]),
    ("ne", lambda af: af.k != _BIG, [1.0, 0.0]),
]


@pytest.mark.parametrize(
    ("name", "line", "by_policy"), _SIX, ids=[case[0] for case in _SIX]
)
def test_a_whole_number_past_two_to_the_53_compares_exactly_in_every_period(
    name: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    by_policy: list[float],
) -> None:
    af = _book(k=pl.Series([_run(_BIG + 1), _run(_BIG)], dtype=pl.List(pl.Int64)))
    indicator, selection = _indicator_and_selection(af, line)
    expected = [[value] * 3 for value in by_policy]
    assert indicator == expected
    assert selection == _as(expected)


def test_the_answer_is_the_one_the_per_policy_route_gives() -> None:
    af = _book(
        n=pl.Series([_BIG + 1, _BIG], dtype=pl.Int64),
        k=pl.Series([_run(_BIG + 1), _run(_BIG)], dtype=pl.List(pl.Int64)),
    )
    af.by_policy = af.n > _BIG
    af.by_period = af.k > _BIG
    out = af.collect()
    assert out["by_policy"].to_list() == [1.0, 0.0]
    assert out["by_period"].to_list() == [[1.0] * 3, [0.0] * 3]


def test_a_literal_on_the_left_is_compared_exactly_too() -> None:
    af = _book(k=pl.Series([_run(_BIG + 1), _run(_BIG)], dtype=pl.List(pl.Int64)))
    indicator, selection = _indicator_and_selection(
        af,
        lambda af: _BIG < af.k,  # noqa: SIM300 -- the literal is written on the left
    )
    assert indicator == [[1.0] * 3, [0.0] * 3]
    assert selection == [[1] * 3, [0] * 3]


def test_a_run_against_a_per_policy_column_is_exact() -> None:
    af = _book(
        k=pl.Series([_run(_BIG + 1), _run(_BIG)], dtype=pl.List(pl.Int64)),
        m=pl.Series([_BIG, _BIG], dtype=pl.Int64),
    )
    indicator, selection = _indicator_and_selection(af, lambda af: af.k > af.m)
    assert indicator == [[1.0] * 3, [0.0] * 3]
    assert selection == [[1] * 3, [0] * 3]


def test_two_runs_at_the_ends_of_i64_are_compared_exactly() -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "k": pl.Series([[_TOP, _LEAST + 1, 0]], dtype=pl.List(pl.Int64)),
                "j": pl.Series([[_TOP - 1, _LEAST, 0]], dtype=pl.List(pl.Int64)),
            }
        )
    )
    af.gt = af.k > af.j
    af.eq = af.k == af.j
    af.top = af.k == _TOP - 1
    out = af.collect()
    assert out["gt"].to_list() == [[1.0, 1.0, 0.0]]
    assert out["eq"].to_list() == [[0.0, 0.0, 1.0]]
    assert out["top"].to_list() == [[0.0, 0.0, 0.0]]


def test_a_nanosecond_date_and_time_one_unit_later_is_later() -> None:
    stamps = pl.Series([_run(_NS + 1), _run(_NS)], dtype=pl.List(pl.Int64))
    af = _book(
        t=stamps.cast(pl.List(pl.Datetime("ns"))),
        o=pl.Series([_NS, _NS], dtype=pl.Int64).cast(pl.Datetime("ns")),
    )
    indicator, selection = _indicator_and_selection(af, lambda af: af.t > af.o)
    assert indicator == [[1.0] * 3, [0.0] * 3]
    assert selection == [[1] * 3, [0] * 3]


@pytest.mark.parametrize("unit", ["ns", "us", "ms"])
def test_a_zoned_date_and_time_compares_by_its_instant(unit: str) -> None:
    scale = {"ns": 1, "us": 1_000, "ms": 1_000_000}[unit]
    stamps = pl.Series(
        [_run(_NS // scale + 1), _run(_NS // scale)], dtype=pl.List(pl.Int64)
    )
    af = _book(
        t=stamps.cast(pl.List(pl.Datetime(unit, _ZONE))),
        o=pl.Series([_NS // scale] * 2, dtype=pl.Int64).cast(pl.Datetime(unit, _ZONE)),
    )
    af.eq = af.t == af.o
    af.ge = af.t >= af.o
    out = af.collect()
    assert out["eq"].to_list() == [[0.0] * 3, [1.0] * 3]
    assert out["ge"].to_list() == [[1.0] * 3, [1.0] * 3]


def test_a_date_and_time_in_another_unit_is_compared_in_the_finer_one() -> None:
    nanoseconds = pl.Series([_run(_NS + 1), _run(_NS)], dtype=pl.List(pl.Int64))
    af = _book(
        t=nanoseconds.cast(pl.List(pl.Datetime("ns"))),
        o=pl.Series([_NS // 1000] * 2, dtype=pl.Int64).cast(pl.Datetime("us")),
    )
    af.gt = af.t > af.o
    af.literal = af.t > dt.datetime(2025, 1, 1)  # noqa: DTZ001 -- zone-naive, as the column
    out = af.collect()
    assert out["gt"].to_list() == [[1.0] * 3, [0.0] * 3]
    assert out["literal"].to_list() == [[1.0] * 3, [0.0] * 3]


def test_a_duration_one_nanosecond_longer_is_longer() -> None:
    long = 2**60
    runs = pl.Series([_run(long + 1), _run(long)], dtype=pl.List(pl.Int64))
    af = _book(
        d=runs.cast(pl.List(pl.Duration("ns"))),
        e=pl.Series([long, long], dtype=pl.Int64).cast(pl.Duration("ns")),
    )
    indicator, selection = _indicator_and_selection(af, lambda af: af.d > af.e)
    assert indicator == [[1.0] * 3, [0.0] * 3]
    assert selection == [[1] * 3, [0] * 3]


def test_a_null_answers_null_value_by_value_and_policy_by_policy() -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "k": pl.Series(
                    [[_BIG + 1, None, _BIG], None, [_BIG + 1, _BIG]],
                    dtype=pl.List(pl.Int64),
                ),
                "m": pl.Series([_BIG, _BIG, None], dtype=pl.Int64),
            }
        )
    )
    af.gt = af.k > af.m
    assert af.collect()["gt"].to_list() == [[1.0, None, 0.0], None, [None, None]]


def test_two_runs_of_different_lengths_are_refused_by_the_kernel() -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "k": pl.Series([[_BIG + 1, _BIG, 1]], dtype=pl.List(pl.Int64)),
                "j": pl.Series([[_BIG, _BIG]], dtype=pl.List(pl.Int64)),
            }
        )
    )
    af.gt = af.k > af.j
    with pytest.raises(Exception, match="mismatched inner list lengths") as refused:
        af.collect()
    assert "right against left" in str(refused.value)


@pytest.mark.parametrize("zoned_first", [True, False])
def test_a_zoned_date_and_time_against_a_naive_one_is_refused_at_the_line(
    *, zoned_first: bool
) -> None:
    stamps = pl.Series([_NS, _NS], dtype=pl.Int64)
    af = _book(
        z=stamps.cast(pl.Datetime("ns", "UTC")),
        n=stamps.cast(pl.Datetime("ns")),
    )
    with pytest.raises(TypeError, match="no time zone") as refused:
        af.r = (af.z > af.n) if zoned_first else (af.n < af.z)
    assert "'UTC'" in str(refused.value)


# --- guards: these pass before and after ------------------------------------


def test_a_whole_number_beside_a_decimal_keeps_the_mixed_rule() -> None:
    af = _book(k=pl.Series([_run(3), _run(2)], dtype=pl.List(pl.Int64)))
    af.gt = af.k > 2.5
    assert af.collect()["gt"].to_list() == [[1.0] * 3, [0.0] * 3]


def test_dates_and_narrow_whole_numbers_answer_as_before() -> None:
    af = _book(
        d=pl.Series(
            [[dt.date(2025, 1, 2)], [dt.date(2025, 1, 1)]], dtype=pl.List(pl.Date)
        ),
        s=pl.Series([[5], [3]], dtype=pl.List(pl.Int32)),
    )
    af.late = af.d > dt.date(2025, 1, 1)
    af.big = af.s > 4
    out = af.collect()
    assert out["late"].to_list() == [[1.0], [0.0]]
    assert out["big"].to_list() == [[1.0], [0.0]]
