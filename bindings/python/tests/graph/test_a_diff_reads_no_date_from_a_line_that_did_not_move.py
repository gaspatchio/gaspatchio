# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A diff refuses a date past the calendar only where it reads one.

``gspio diff --results`` refused any compared column holding a date outside
the years 1 to 9999, a line whose values did not move included. Such a line
is measured by equality as the two files hold it -- no cell of it is read as
a value, written as a worst cell or read for the declared policy -- so the
refusal blocked a whole diff over a column the diff never writes. It now
fires on a line that moved, and on a timeline start that moved, and not on
one that held. The identity column is always read, for the policies' names,
and still refuses.
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

# (unit or "date", zone, a count past the calendar in that unit)
_KINDS: dict[str, tuple[str, str | None, int]] = {
    "ms, year 285000": ("ms", None, 9_000_000_000_000_000),
    "us, year 11476": ("us", None, 300_000_000_000_000_000),
    "ms before year 1": ("ms", None, -9_000_000_000_000_000),
    "ms in Auckland": ("ms", "Pacific/Auckland", 9_000_000_000_000_000),
    "date, year 10183": ("date", None, 3_000_000),
}


def _held(name: str, kind: tuple[str, str | None, int], counts: list[int]) -> pl.Series:
    unit, zone, _ = kind
    if unit == "date":
        return pl.Series(name, counts, dtype=pl.Int32).cast(pl.Date)
    return pl.Series(name, counts, dtype=pl.Int64).cast(pl.Datetime(unit, zone))  # type: ignore[arg-type]


def _run(folder: Path, name: str, frame: pl.DataFrame) -> dict[str, Any]:
    af = ActuarialFrame(frame)
    af.d = af.v
    af.x = af.r * 2.0
    results, manifest = polars_reference(af, row_identity="policy_id")
    write_with_manifest(results, manifest, folder / f"{name}.parquet")
    document: dict[str, Any] = json.loads(GraphExporter(af).export())
    (folder / f"{name}.json").write_text(json.dumps(document))
    return document


def _two_runs(
    folder: Path, kind: tuple[str, str | None, int], *, shape: str, v_moves: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Both runs hold the date past the calendar in ``v``'s row 1; ``r`` moves.

    Row 0 stays in the calendar: it is the row the record samples, and the
    export refuses a date past the calendar there before any diff is run.
    """
    count = kind[2]
    documents = []
    for name, rate, last in (("a", 1.0, count), ("b", 1.5, 0 if v_moves else count)):
        frame = pl.DataFrame(
            {
                "policy_id": ["P1", "P2"],
                "v": _held("v", kind, [0, last]),
                "r": [0.5, rate],
            }
        )
        if shape == "per period":
            frame = frame.with_columns(pl.concat_list("v", "v").alias("v"))
        documents.append(_run(folder, name, frame))
    return documents[0], documents[1]


def _diff(folder: Path, documents: tuple[dict[str, Any], dict[str, Any]]) -> Any:  # noqa: ANN401
    return diff_with_results(
        documents[0], documents[1], folder / "a.parquet", folder / "b.parquet"
    )


@pytest.mark.parametrize("shape", ["per policy", "per period"])
@pytest.mark.parametrize("kind", list(_KINDS))
def test_a_line_that_held_is_compared_and_the_moved_line_measured(
    tmp_path: Path, kind: str, shape: str
) -> None:
    report = _diff(
        tmp_path, _two_runs(tmp_path, _KINDS[kind], shape=shape, v_moves=False)
    )
    lines = {line.node: line for line in report.values.lines}

    assert lines["d@1"].compared
    assert not lines["d@1"].moved
    assert lines["d@1"].worst is None
    assert lines["x@1"].moved
    assert lines["x@1"].worst.policy == "P2"
    if report.values.declared is not None:
        assert "d@1" not in [one.node for one in report.values.declared.lines]


@pytest.mark.parametrize("shape", ["per policy", "per period"])
@pytest.mark.parametrize("kind", list(_KINDS))
def test_the_cli_compares_past_a_line_that_held(
    tmp_path: Path, kind: str, shape: str
) -> None:
    _two_runs(tmp_path, _KINDS[kind], shape=shape, v_moves=False)
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
    assert ran.exit_code != 2, said
    assert "outside the years 1 to 9999" not in said


@pytest.mark.parametrize("shape", ["per policy", "per period"])
@pytest.mark.parametrize("kind", list(_KINDS))
def test_the_same_line_moving_is_still_refused_by_its_column(
    tmp_path: Path, kind: str, shape: str
) -> None:
    documents = _two_runs(tmp_path, _KINDS[kind], shape=shape, v_moves=True)
    with pytest.raises(
        ValueError,
        match=r"The (earlier|later) results hold a date outside the years 1 to "
        r"9999 in column '[vd]'",
    ):
        _diff(tmp_path, documents)


@pytest.mark.parametrize("kind", list(_KINDS))
def test_a_timeline_start_that_held_is_not_read(tmp_path: Path, kind: str) -> None:
    held = _KINDS[kind]
    documents = []
    for name, rate in (("a", 1.0), ("b", 1.5)):
        frame = pl.DataFrame(
            {
                "policy_id": ["P1", "P2"],
                "v": [1.0, 2.0],
                "r": [0.5, rate],
                "projection_start_date": _held("s", held, [0, held[2]]),
            }
        )
        documents.append(_run(tmp_path, name, frame))
    report = _diff(tmp_path, (documents[0], documents[1]))
    assert report.values.periods.aligned
    assert "x@1" in {line.node for line in report.values.lines if line.moved}
