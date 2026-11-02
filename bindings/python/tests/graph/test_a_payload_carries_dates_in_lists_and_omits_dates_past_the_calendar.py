# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An audit payload carries dates in lists, and omits dates past the calendar.

Section 13 says a producer inlining a payload MUST inline exactly the frame
its fingerprint was taken over, and section 10 writes a ``date`` or
``datetime`` as ISO-8601 text wherever one appears, a ``list[date]`` column
of an assumption payload included. A join's right side holding a list of
dates went out as Python objects, and the export died on
``Object of type date is not JSON serializable``. Its elements are now
written as their text and read back by ``gspio validate``, so the payload
re-hashes to the fingerprint beside it.

A date or timestamp outside the years 1 to 9999 has no such text -- the
form's year is four digits -- and the producer wrote ``+10183-...``, which
no reader of that form reads, or panicked inside the engine past about
262,000 years from 1970. Such a payload, in a table or a join, is now the
existing ``unavailable`` omission, with a warning naming the column.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from loguru import logger

from gaspatchio import ActuarialFrame
from gaspatchio._identity import content_sha_of
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.validate import payload_frame, validate_artifact

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_NAMES = itertools.count()


@pytest.fixture
def warnings_said() -> Iterator[list[str]]:
    said: list[str] = []
    sink = logger.add(lambda message: said.append(str(message)), level="WARNING")
    yield said
    logger.remove(sink)


def _counts(kind: str, values: list[int]) -> pl.Series:
    if kind == "date":
        return pl.Series("c", values, dtype=pl.Int32).cast(pl.Date)
    unit, _, zone = kind.partition(" ")
    return pl.Series("c", values, dtype=pl.Int64).cast(pl.Datetime(unit, zone or None))  # type: ignore[arg-type]


def _listed(kind: str, *rows: list[int]) -> pl.Series:
    return pl.concat([_counts(kind, row).implode() for row in rows])


def _join_document(column: pl.Series) -> dict[str, Any]:
    right = pl.DataFrame({"k": [1, 2], "c": column})
    af = ActuarialFrame(pl.DataFrame({"pid": [1, 2], "k": [1, 2]})).join(right, on="k")
    af.out = af.k * 2
    exported = GraphExporter(af).export(
        af.collect(), profile="audit", include_source=False
    )
    return json.loads(exported)  # type: ignore[arg-type]


def _table_document(column: pl.Series) -> tuple[dict[str, Any], Table]:
    table = Table(
        name=f"l1_payload_{next(_NAMES)}",
        source=pl.DataFrame({"c": column, "v": [0.1, 0.2]}),
        dimensions={"c": "c"},
        value="v",
    )
    af = ActuarialFrame(pl.DataFrame({"pid": [1], "q": column[:1]}))
    af.r = table.lookup(c=af.q)
    exported = GraphExporter(af).export(
        af.collect(), profile="audit", include_source=False
    )
    return json.loads(exported), table  # type: ignore[arg-type]


def _entry(document: dict[str, Any], kind: str) -> dict[str, Any]:
    (entry,) = [one for one in document["assumptions"] if one["kind"] == kind]
    return entry


_LISTS: dict[str, Callable[[], pl.Series]] = {
    "list[date]": lambda: pl.Series(
        "c", [[dt.date(2025, 1, 1), dt.date(2025, 6, 30)], [dt.date(2026, 1, 1)]]
    ),
    "list[date] with a null": lambda: pl.Series(
        "c", [[dt.date(2025, 1, 1), None], None], dtype=pl.List(pl.Date)
    ),
    "list[list[date]]": lambda: pl.Series(
        "c", [[[dt.date(2025, 1, 1)]], [[dt.date(2026, 1, 1)], []]]
    ),
    "list[datetime us]": lambda: pl.Series(
        "c",
        [[dt.datetime(2025, 1, 1, 1, 2, 3, 4)], [dt.datetime(2026, 1, 1)]],  # noqa: DTZ001
    ),
    "list[datetime ns]": lambda: _listed("ns", [1_700_000_000_000_000_001], [5]),
    "list[datetime ms UTC]": lambda: _listed("ms UTC", [5], [6]),
    "list[date] at 9999-12-31": lambda: _listed("date", [0], [2_932_896]),
}


@pytest.mark.parametrize("what", list(_LISTS))
def test_a_join_payload_of_dates_in_lists_rehashes_to_its_fingerprint(
    what: str,
) -> None:
    document = _join_document(_LISTS[what]())
    entry = _entry(document, "join")

    declared = {
        column["name"]: column["dtype"] for column in entry["payload"]["columns"]
    }
    assert declared["c"].startswith("list[")
    rebuilt, unreadable = payload_frame(entry["payload"])
    assert unreadable is None
    assert rebuilt is not None
    assert content_sha_of(rebuilt) == entry["fingerprint"]


@pytest.mark.parametrize("what", ["list[date]", "list[datetime ns]"])
def test_validate_deep_rehashes_a_list_of_dates_and_finds_nothing(what: str) -> None:
    document = _join_document(_LISTS[what]())
    report = validate_artifact(document, deep=True)
    assert not [
        finding
        for finding in report.findings
        if finding.where.startswith("/assumptions") or finding.severity == "error"
    ]

    entry = _entry(document, "join")
    entry["payload"]["rows"][0][-1] = None
    broken = validate_artifact(document, deep=True)
    assert any(
        finding.where == "/assumptions/0" and "hash to" in finding.message
        for finding in broken.findings
    )


# A count past the calendar in row 1, which the export never samples.
_PAST: dict[str, Callable[[], pl.Series]] = {
    "date, year 10183": lambda: _counts("date", [0, 3_000_000]),
    "date before year 1": lambda: _counts("date", [0, -720_000]),
    "us, year 11476": lambda: _counts("us", [0, 300_000_000_000_000_000]),
    "ms, year 285000": lambda: _counts("ms", [0, 9_000_000_000_000_000]),
    "ms in UTC, year 285000": lambda: _counts("ms UTC", [0, 9_000_000_000_000_000]),
}
_PAST_IN_LISTS: dict[str, Callable[[], pl.Series]] = {
    "list[date], year 10183": lambda: _listed("date", [0], [1, 3_000_000]),
    "list[ms], year 285000": lambda: _listed("ms", [0], [1, 9_000_000_000_000_000]),
}


@pytest.mark.parametrize("what", [*_PAST, *_PAST_IN_LISTS])
def test_a_join_payload_past_the_calendar_is_stated_unavailable(
    what: str, warnings_said: list[str]
) -> None:
    document = _join_document({**_PAST, **_PAST_IN_LISTS}[what]())
    entry = _entry(document, "join")

    assert entry["payload"] == {"omitted": "unavailable"}
    assert any(
        "column 'c' holds a date outside the years 1 to 9999" in said
        for said in warnings_said
    )


@pytest.mark.parametrize("what", list(_PAST))
def test_a_table_payload_past_the_calendar_is_stated_unavailable(
    what: str, warnings_said: list[str]
) -> None:
    document, table = _table_document(_PAST[what]())
    entry = _entry(document, "table")

    assert entry["fingerprint"] == table.fingerprint()
    assert entry["payload"] == {"omitted": "unavailable"}
    assert any(
        "column 'c' holds a date outside the years 1 to 9999" in said
        for said in warnings_said
    )


def test_a_zoned_timestamp_in_a_list_is_stated_unavailable(
    warnings_said: list[str],
) -> None:
    document = _join_document(_listed("ms Pacific/Auckland", [5], [6]))
    entry = _entry(document, "join")

    assert entry["payload"] == {"omitted": "unavailable"}
    assert any(
        "column 'c' holds timestamps in the zone" in said for said in warnings_said
    )
