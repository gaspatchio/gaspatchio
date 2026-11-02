# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A workbook of one policy, from the command line.

Two ways in. ``gspio calc-graph ... --xlsx policy.xlsx`` lays out the record it
has just written, as ``--html`` writes the page; ``gspio sheet audit.json``
lays out a record already on disk, or one a revision committed. Both reach
``render_xlsx``, so what is asserted here is the command's half: the file is
written, the results file is checked and the README says so, and each refusal
arrives with its own exit status. ``run-single-policy --help`` names the way to
a spreadsheet, because that is where somebody looking for one starts.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from tests.test_cli_artifact import _needle, _unwrapped

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

MODEL_SRC = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.death_claims = af.sum_assured * 0.00123
    af.loaded = af.death_claims * (1.0 + 0.1 + 0.2)
    return af
"""

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _model_and_points(tmp_path: Path) -> tuple[Path, Path]:
    model_path = tmp_path / "model.py"
    model_path.write_text(MODEL_SRC)
    points_path = tmp_path / "model_points.parquet"
    pl.DataFrame(
        {"policy_id": ["A", "B", "C"], "sum_assured": [100_000.0, 2.5e5, 1 / 3]}
    ).write_parquet(points_path)
    return model_path, points_path


def _readme(workbook: Path) -> dict[str, str]:
    """Return the README's items and values, read straight out of the file."""
    with zipfile.ZipFile(io.BytesIO(workbook.read_bytes())) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))  # noqa: S314
    readme: dict[str, str] = {}
    for row in root.iter(f"{_MAIN}row"):
        texts = ["".join(cell.itertext()) for cell in row.iter(f"{_MAIN}c")]
        if len(texts) == 2:  # an item and its value
            readme.setdefault(texts[0], texts[1])
    return readme


def _sheets(workbook: Path) -> list[str]:
    with zipfile.ZipFile(workbook) as archive:
        book = ET.fromstring(archive.read("xl/workbook.xml"))  # noqa: S314
    return [sheet.get("name", "") for sheet in book.iter(f"{_MAIN}sheet")]


def test_calc_graph_lays_the_record_it_wrote_out_beside_it(tmp_path: Path) -> None:
    model_path, points_path = _model_and_points(tmp_path)
    artifact = tmp_path / "model.audit.json"
    workbook = tmp_path / "policy.xlsx"

    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            "-o",
            str(artifact),
            "--results",
            str(tmp_path / "results.parquet"),
            "--policies",
            "id:B",
            "--xlsx",
            str(workbook),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Workbook saved to" in result.output
    document = json.loads(artifact.read_text())
    readme = _readme(workbook)
    assert readme["document_digest"] == document["document_digest"]
    assert readme["policy"] == "B"
    assert readme["check: results"].startswith("agree")
    assert _sheets(workbook) == [
        "README",
        "Timeline",
        "Scalars",
        "Nodes",
        "Edges",
        "Assumptions",
    ]


def test_calc_graph_gives_each_policy_a_timeline(tmp_path: Path) -> None:
    model_path, points_path = _model_and_points(tmp_path)
    workbook = tmp_path / "book.xlsx"

    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            "-o",
            str(tmp_path / "model.audit.json"),
            "--policies",
            ":3",
            "--xlsx",
            str(workbook),
        ],
    )

    assert result.exit_code == 0, result.output
    assert _sheets(workbook)[1:4] == ["Timeline A", "Timeline B", "Timeline C"]


def _exported(tmp_path: Path) -> Path:
    model_path, points_path = _model_and_points(tmp_path)
    artifact = tmp_path / "model.audit.json"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            "-o",
            str(artifact),
            "--results",
            str(tmp_path / "results.parquet"),
            "--policies",
            ":2",
        ],
    )
    assert result.exit_code == 0, result.output
    return artifact


def test_sheet_lays_out_one_policy_of_a_record_on_disk(tmp_path: Path) -> None:
    artifact = _exported(tmp_path)
    workbook = tmp_path / "b.xlsx"

    result = runner.invoke(
        app,
        [
            "sheet",
            str(artifact),
            "-o",
            str(workbook),
            "--policy",
            "B",
            "--results",
            str(tmp_path / "results.parquet"),
        ],
    )

    assert result.exit_code == 0, result.output
    readme = _readme(workbook)
    assert readme["policy"] == "B"
    assert readme["check: results"].startswith("agree")
    assert _sheets(workbook)[1] == "Timeline"


def test_sheet_names_its_workbook_after_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _exported(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["sheet", str(artifact)])

    assert result.exit_code == 0, result.output
    assert _sheets(tmp_path / "model.audit.xlsx")[1:3] == ["Timeline A", "Timeline B"]


def test_sheet_refuses_a_policy_the_record_does_not_carry(tmp_path: Path) -> None:
    artifact = _exported(tmp_path)

    result = runner.invoke(
        app, ["sheet", str(artifact), "-o", str(tmp_path / "x.xlsx"), "-p", "C"]
    )

    assert result.exit_code == 3, result.output
    assert "'C' is not on the record's axis" in result.output
    assert not (tmp_path / "x.xlsx").exists()


def test_sheet_refuses_a_record_whose_seal_does_not_hold(tmp_path: Path) -> None:
    artifact = _exported(tmp_path)
    document = json.loads(artifact.read_text())
    document["created_at"] = "2030-01-01T00:00:00Z"
    artifact.write_text(json.dumps(document))

    result = runner.invoke(
        app, ["sheet", str(artifact), "-o", str(tmp_path / "x.xlsx")]
    )

    assert result.exit_code == 1, result.output
    assert "seal does not hold" in result.output


def test_sheet_cannot_read_what_is_not_a_record(tmp_path: Path) -> None:
    path = tmp_path / "notes.json"
    path.write_text("[]")

    result = runner.invoke(app, ["sheet", str(path)])

    assert result.exit_code == 2, result.output


def test_run_single_policy_points_to_the_workbook() -> None:
    result = runner.invoke(app, ["run-single-policy", "--help"])

    assert result.exit_code == 0
    assert "--xlsx" in result.output


# --- an output into a directory that is not there ---------------------------------


def test_sheet_refuses_a_workbook_in_a_missing_directory(tmp_path: Path) -> None:
    """``-o report/policy.xlsx`` with no ``report/`` raised; now it is refused."""
    artifact = _exported(tmp_path)
    workbook = tmp_path / "report" / "policy.xlsx"

    result = runner.invoke(app, ["sheet", str(artifact), "-o", str(workbook)])

    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    said = _unwrapped(result.output)
    assert _needle(f"--output names policy.xlsx in {tmp_path / 'report'}") in said
    assert _needle("which does not exist, so nothing was written") in said
    assert _needle(f"mkdir -p {tmp_path / 'report'}") in said
    assert not (tmp_path / "report").exists()


def test_sheet_refuses_a_workbook_under_a_file(tmp_path: Path) -> None:
    """A path whose parent is a file is named as one, with no ``mkdir`` to suggest."""
    artifact = _exported(tmp_path)

    result = runner.invoke(
        app, ["sheet", str(artifact), "-o", str(artifact / "policy.xlsx")]
    )

    assert result.exit_code == 2, result.output
    said = _unwrapped(result.output)
    assert _needle("which is a file rather than a directory") in said
    assert _needle("mkdir") not in said


@pytest.mark.parametrize("flag", ["--artifact", "--results", "--html", "--xlsx"])
def test_calc_graph_refuses_any_output_in_a_missing_directory_before_writing(
    tmp_path: Path, flag: str
) -> None:
    """No file is written and the model never runs: the artifact is not left behind."""
    model_path, points_path = _model_and_points(tmp_path)
    artifact = tmp_path / "model.audit.json"
    missing = tmp_path / "report" / "out.file"
    outputs = {"--artifact": missing} | (
        {} if flag == "--artifact" else {"--artifact": artifact, flag: missing}
    )

    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            *(part for option, path in outputs.items() for part in (option, str(path))),
        ],
    )

    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    said = _unwrapped(result.output)
    assert _needle(f"{flag} names out.file in {tmp_path / 'report'}") in said
    assert not artifact.exists()
    assert not (tmp_path / "report").exists()
