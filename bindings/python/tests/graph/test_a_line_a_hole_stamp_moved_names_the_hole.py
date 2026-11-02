# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A line whose numbers moved because a hole's stamp moved says so, naming the hole.

The 0.9 setup step joins a side file in plain Polars and rebuilds the frame,
so the joined column is a hole carrying a stamp of what it held. Edit the file
and the change report names the hole as data that moved; read the two results
files beside it and every line under the hole moves under a definition that
did not. Those lines were labelled ``unexplained`` -- the label for a column
written around the frame's account of it -- though the report itself said
what moved under them. Each such line now carries ``cause: "hole"`` and the
holes it reads, while a line that moved without reading a moved hole keeps
the comparison's own cause. A book that moved outranks a hole, because it
moves every line.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
from typer.testing import CliRunner

from gaspatchio.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_MODEL = """import datetime
from pathlib import Path

import polars as pl

from gaspatchio import ActuarialFrame

HERE = Path(__file__).parent


def main(af):
    mp = af.collect()
    loads = pl.read_parquet(HERE / "loads.parquet")
    mp = mp.join(loads, on="product", how="left", maintain_order="left")
    af = ActuarialFrame(mp)
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=3,
        frequency="monthly",
    )
    af.prem = af.premium * af["load"] + af.month * 0.0
    af.pv_prem = af.prem.list.sum()
    af._df = af._df.with_columns(pl.lit({extra}).alias("extra"))
    af.fee = af.premium * af["extra"]
    return af
"""


def _run(
    folder: Path, *, load_a: float, extra: float = 0.5, last_premium: float = 300.0
) -> tuple[Path, pl.DataFrame]:
    """Run the 0.9 template with ``calc-graph``, its results file named."""
    folder.mkdir()
    (folder / "model.py").write_text(_MODEL.format(extra=extra))
    pl.DataFrame(
        {
            "policy_id": [1, 2, 3],
            "premium": [100.0, 400.0, last_premium],
            "product": ["A", "B", "A"],
        }
    ).write_parquet(folder / "book.parquet")
    pl.DataFrame({"product": ["A", "B"], "load": [load_a, 1.0]}).write_parquet(
        folder / "loads.parquet"
    )
    audit, results = folder / "audit.json", folder / "results.parquet"
    ran = runner.invoke(
        app,
        [
            "calc-graph",
            str(folder / "model.py"),
            str(folder / "book.parquet"),
            "-o",
            str(audit),
            "--results",
            str(results),
        ],
    )
    assert ran.exit_code == 0, ran.output
    return audit, pl.read_parquet(results)


def _diff(before: Path, after: Path) -> dict[str, Any]:
    ran = runner.invoke(app, ["diff", str(before), str(after), "--json"])
    assert ran.exit_code == 1, ran.output
    report: dict[str, Any] = json.loads(ran.stdout)
    return report


def _moved(report: dict[str, Any]) -> dict[str, tuple[str | None, Any]]:
    return {
        line["node"]: (line["cause"], line["holes"])
        for line in report["values"]["lines"]
        if line["moved"]
    }


def test_the_lines_under_an_edited_side_file_name_the_hole(tmp_path: Path) -> None:
    q1, first = _run(tmp_path / "q1", load_a=1.0)
    q2, second = _run(tmp_path / "q2", load_a=1.1)
    # By hand: four periods of premium x load. Policy 1's load moved 1.0 -> 1.1,
    # and 100 x 1.1 is 110.00000000000001 in doubles; policy 3 is 300 x 1.1 x 4.
    assert first["pv_prem"].to_list() == [400.0, 1600.0, 1200.0]
    assert second["pv_prem"].to_list() == [440.00000000000006, 1600.0, 1320.0]

    for report in (_diff(q1, q2), _diff(q2, q1)):
        assert (report["data"][0]["kind"], report["data"][0]["name"]) == (
            "hole",
            "load",
        )
        assert _moved(report) == {
            "load": ("hole", ["load"]),
            "prem@1": ("hole", ["load"]),
            "pv_prem@1": ("hole", ["load"]),
        }
        unmoved = report["values"]["headline"]["unmoved_definitions"]
        assert unmoved == {
            "book": [],
            "hole": ["load", "prem@1", "pv_prem@1"],
            "producer": [],
            "unexplained": [],
        }


def test_a_line_that_reads_no_moved_hole_keeps_its_cause(tmp_path: Path) -> None:
    q1, _ = _run(tmp_path / "q1", load_a=1.0, extra=0.5)
    q2, second = _run(tmp_path / "q2", load_a=1.1, extra=0.6)
    assert second["fee"].to_list() == [60.0, 240.0, 180.0]

    report = _diff(q1, q2)

    assert _moved(report) == {
        "load": ("hole", ["load"]),
        "extra": ("unexplained", None),
        "prem@1": ("hole", ["load"]),
        "pv_prem@1": ("hole", ["load"]),
        "fee@1": ("unexplained", None),
    }
    still = [line for line in report["values"]["lines"] if not line["moved"]]
    assert all(line["cause"] is None and line["holes"] is None for line in still)


def test_a_book_that_moved_outranks_the_hole(tmp_path: Path) -> None:
    q1, _ = _run(tmp_path / "q1", load_a=1.0)
    q2, second = _run(tmp_path / "q2", load_a=1.1, last_premium=350.0)
    assert second["pv_prem"].to_list() == [
        440.00000000000006,
        1600.0,
        1540.0000000000002,
    ]

    report = _diff(q1, q2)

    assert {cause for cause, _ in _moved(report).values()} == {"book"}
    assert report["values"]["headline"]["unmoved_definitions"]["hole"] == []


def test_the_command_counts_the_lines_by_cause_naming_the_hole(tmp_path: Path) -> None:
    q1, _ = _run(tmp_path / "q1", load_a=1.0, extra=0.5)
    q2, _ = _run(tmp_path / "q2", load_a=1.1, extra=0.6)

    ran = runner.invoke(app, ["diff", str(q1), str(q2)])

    text = " ".join(ran.output.split())
    assert (
        "unmoved definitions: 5 moved, the cause the record states: "
        "hole load (3); unexplained (2)"
    ) in text
    assert "extra, fee@1 moved under definitions that did not" in text
