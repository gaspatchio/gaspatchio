# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A change report over a date past the calendar refuses by its column, never a panic.

``gspio diff --results`` reads the two results files' cells as values to
write the cell that ranks a moved line, the policy the record declares, the
policies' names and their timelines' start dates. A date or a timestamp
outside the years 1 to 9999 there either panicked inside the engine's own
conversion -- an exception no ``except Exception`` catches -- or raised the
host language's "year 10183 is out of range", naming no column. It is now
judged on its count before it is read, as the export judges the row it
samples, and refused naming the side and the column.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.engines.protocol import write_with_manifest
from gaspatchio.engines.reference import polars_reference
from gaspatchio.frame.graph import GraphExporter, diff_with_results

if TYPE_CHECKING:
    from pathlib import Path

_PAST = r"The (earlier|later) results hold a date outside the years 1 to 9999 in column '{}'"

# (unit or "date", zone, a count past the calendar in that unit)
_KINDS: dict[str, tuple[str, str | None, int]] = {
    "ms, year 285000": ("ms", None, 9_000_000_000_000_000),
    "us, i64 max": ("us", None, 9_223_372_036_854_775_807),
    "us, year 11476": ("us", None, 300_000_000_000_000_000),
    "ms before year 1": ("ms", None, -9_000_000_000_000_000),
    "ms in UTC": ("ms", "UTC", 9_000_000_000_000_000),
    "ms in Auckland": ("ms", "Pacific/Auckland", 9_000_000_000_000_000),
    "us in Auckland, year 11476": ("us", "Pacific/Auckland", 300_000_000_000_000_000),
    "date, i32 max": ("date", None, 2_147_483_647),
    "date, year 10183": ("date", None, 3_000_000),
}
_IN_RANGE: dict[str, tuple[str, str | None, int]] = {
    "ns, i64 max": ("ns", None, 9_223_372_036_854_775_807),
    "ms, 2025": ("ms", None, 1_735_689_600_000),
    "date, 9999-12-31": ("date", None, 2_932_896),
}


def _counts(name: str, kind: tuple[str, str | None, int], moved: bool) -> pl.Series:  # noqa: FBT001
    unit, zone, count = kind
    values = [0, count if moved else 1]
    if unit == "date":
        return pl.Series(name, values, dtype=pl.Int32).cast(pl.Date)
    return pl.Series(name, values, dtype=pl.Int64).cast(pl.Datetime(unit, zone))  # type: ignore[arg-type]


def _run(folder: Path, name: str, frame: pl.DataFrame, identity: str) -> dict[str, Any]:
    af = ActuarialFrame(frame)
    af.d = af.v
    results, manifest = polars_reference(af, row_identity=identity)
    write_with_manifest(results, manifest, folder / f"{name}.parquet")
    document: dict[str, Any] = json.loads(GraphExporter(af).export())
    (folder / f"{name}.json").write_text(json.dumps(document))
    return document


def _pair(
    folder: Path, kind: tuple[str, str | None, int], door: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write two runs whose later one holds the count in row 1 of the door's column."""
    documents = []
    for name, moved in (("a", False), ("b", True)):
        frame = pl.DataFrame(
            {"policy_id": ["P1", "P2"], "v": _counts("v", kind, moved)}
        )
        identity = "policy_id"
        if door == "per period":
            frame = frame.with_columns(pl.concat_list("v", "v").alias("v"))
        elif door == "identity":
            frame = frame.with_columns(
                when=_counts("when", kind, moved=True), v=pl.Series([1.0, 2.0])
            )
            identity = "when"
        elif door == "start":
            frame = frame.with_columns(
                projection_start_date=_counts("s", kind, moved), v=pl.Series([1.0, 1.0])
            )
        documents.append(_run(folder, name, frame, identity))
    return documents[0], documents[1]


def _diff(folder: Path, documents: tuple[dict[str, Any], dict[str, Any]]) -> object:
    return diff_with_results(
        documents[0], documents[1], folder / "a.parquet", folder / "b.parquet"
    )


@pytest.mark.parametrize("door", ["per policy", "per period", "identity", "start"])
@pytest.mark.parametrize("kind", list(_KINDS))
def test_a_date_past_the_calendar_is_refused_by_its_column(
    tmp_path: Path, kind: str, door: str
) -> None:
    documents = _pair(tmp_path, _KINDS[kind], door)
    column = {"identity": "when", "start": "projection_start_date"}.get(door, "v")
    with pytest.raises(ValueError, match=_PAST.format(column)):
        _diff(tmp_path, documents)


@pytest.mark.parametrize("door", ["per policy", "per period"])
@pytest.mark.parametrize("kind", list(_KINDS))
def test_the_cli_says_the_refusal_and_exits_unreadable(
    tmp_path: Path, kind: str, door: str
) -> None:
    _pair(tmp_path, _KINDS[kind], door)
    ran = CliRunner().invoke(
        app,
        [
            "diff",
            str(tmp_path / "a.json"),
            str(tmp_path / "b.json"),
            "--results",
            str(tmp_path / "a.parquet"),
            str(tmp_path / "b.parquet"),
        ],
    )
    said = " ".join(ran.output.split())
    assert ran.exit_code == 2, said
    assert "outside the years 1 to 9999 in column 'v'" in said


@pytest.mark.parametrize("door", ["per policy", "per period"])
@pytest.mark.parametrize("kind", list(_IN_RANGE))
def test_a_date_the_calendar_holds_is_compared(
    tmp_path: Path, kind: str, door: str
) -> None:
    documents = _pair(tmp_path, _IN_RANGE[kind], door)
    report = _diff(tmp_path, documents)
    (line,) = [one for one in report.values.lines if one.node == "d@1"]  # type: ignore[attr-defined]
    assert line.moved
    assert line.worst.policy == "P2"
    assert isinstance(line.worst.to_dict()["after"], str)
