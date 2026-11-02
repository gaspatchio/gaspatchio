# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A sampled date or timestamp the calendar cannot hold refuses by column, never panics.

The export reads the sampled row's values to write them, and a date or a
timestamp is read as the host language's own: from the year 10000 up to about
262,000 years from 1970 that raised ``year N is out of range`` (named by
column since D1-P10), and past that the engine's conversion panicked inside
Rust -- ``PanicException: NaiveDateTime + TimeDelta overflowed`` -- before
any value reached Python, an exception no ``except Exception`` catches. A
millisecond or microsecond timestamp, naive or zoned, or a date, in the row
the record samples was enough, including values the content grammar accepts. A zoned
instant inside the years whose wall clock is not raised a bare
``OverflowError``.

The count is now judged before it is read: anything outside the years 1 to
9999 -- per policy, or in any period of a per-period column -- refuses the
export naming the column, on every path that samples a row.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from pathlib import Path

_YEAR_S = 31_556_952
_Y272000_MS = 270_000 * _YEAR_S * 1000  # past chrono's calendar, inside i64 us
_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
_Y20000_MS = (
    int((dt.datetime(9999, 12, 31, tzinfo=dt.UTC) - _EPOCH).total_seconds()) * 2000
)
_I64_MAX = 2**63 - 1
_LATE_ON_THE_LAST_DAY_MS = int(
    (dt.datetime(9999, 12, 31, 23, tzinfo=dt.UTC) - _EPOCH).total_seconds() * 1000
)


def _instants(count: int, unit: str, zone: str | None = None) -> pl.Series:
    return pl.Series("ts", [count, 0], dtype=pl.Int64).cast(pl.Datetime(unit, zone))


def _days(count: int) -> pl.Series:
    return pl.Series("ts", [count, 0], dtype=pl.Int32).cast(pl.Date)


PAST = {
    "ms year 272000": _instants(_Y272000_MS, "ms"),
    "ms year 20000": _instants(_Y20000_MS, "ms"),
    "ms past i64 us": _instants(9_223_372_036_854_776, "ms"),
    "ms before past i64 us": _instants(-9_223_372_036_854_776, "ms"),
    "ms i64 max": _instants(_I64_MAX, "ms"),
    "us year 272000": _instants(_Y272000_MS * 1000, "us"),
    "us i64 min": _instants(-_I64_MAX - 1, "us"),
    "ms UTC year 272000": _instants(_Y272000_MS, "ms", "UTC"),
    "ms Auckland year 272000": _instants(_Y272000_MS, "ms", "Pacific/Auckland"),
    "us Auckland year 20000": _instants(_Y20000_MS * 1000, "us", "Pacific/Auckland"),
    "9999-12-31T23:00Z in Auckland": _instants(
        _LATE_ON_THE_LAST_DAY_MS, "ms", "Pacific/Auckland"
    ),
    "date i32 max": _days(2**31 - 1),
    "date i32 min": _days(-(2**31)),
    "date year 20000": _days(3_650_000),
    "a period of list[ms] at year 272000": pl.Series(
        "ts", [[0, _Y272000_MS], [0]], dtype=pl.List(pl.Int64)
    ).cast(pl.List(pl.Datetime("ms"))),
}

INSIDE = {
    "ns i64 max (year 2262)": _instants(_I64_MAX, "ns"),
    "9999-12-31T23:00Z naive": _instants(_LATE_ON_THE_LAST_DAY_MS, "ms"),
    "9999-12-31T23:00Z in New York": _instants(
        _LATE_ON_THE_LAST_DAY_MS, "ms", "America/New_York"
    ),
    "0001-01-01 as a date": _days(-719_162),
}


def _frame(ts: pl.Series) -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"pid": [1, 2], "ts": ts, "x": [1.0, 2.0]}))
    af.y = af.x * 2.0
    return af


@pytest.mark.parametrize("profile", ["executable", "audit"])
@pytest.mark.parametrize("held", list(PAST))
def test_the_export_refuses_by_column(held: str, profile: str) -> None:
    af = _frame(PAST[held])

    with pytest.raises(
        ValueError, match="Column 'ts' holds a date outside the years 1"
    ):
        GraphExporter(af).export(af.collect(), profile=profile, include_source=False)


@pytest.mark.parametrize("held", list(INSIDE))
def test_a_value_the_calendar_holds_still_exports(held: str) -> None:
    af = _frame(INSIDE[held])

    exported = GraphExporter(af).export(
        af.collect(), profile="audit", include_source=False
    )

    assert exported


@pytest.mark.parametrize("html", [False, True])
def test_calc_graph_exits_with_the_refusal_not_a_rust_traceback(
    tmp_path: Path, *, html: bool
) -> None:
    (tmp_path / "model.py").write_text(
        "def main(af, params=None):\n    af.y = af.x * 2.0\n    return af\n"
    )
    pl.DataFrame(
        {"pid": [1, 2], "ts": PAST["ms year 272000"], "x": [1.0, 2.0]}
    ).write_parquet(tmp_path / "book.parquet")
    arguments = [
        "calc-graph",
        str(tmp_path / "model.py"),
        str(tmp_path / "book.parquet"),
        "-o",
        str(tmp_path / "g.json"),
        *(["--html", str(tmp_path / "g.html")] if html else []),
    ]

    result = CliRunner().invoke(app, arguments, env={"COLUMNS": "200"})

    assert result.exit_code == 1
    assert isinstance(result.exception, (ValueError, SystemExit))
    assert "holds a date outside the years 1" in (result.output + str(result.exception))
