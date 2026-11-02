# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``verify`` and ``diff`` state the library versions, and decide nothing on them.

A record now says which library produced its values. ``gspio verify`` holds
that against what this process runs, and against a results file's own
manifest, on a ``versions`` line that is evidence: a library that moved is
the reason to compare two runs' numbers, never a sign that these are the
wrong files, so whatever it finds it moves no exit status. ``gspio
diff`` names a library that moved between two documents in one context line,
with no data entry and no change of exit status.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph import (
    DOCUMENT_DIGEST_FIELD,
    document_digest_of,
    verify_artifact,
)
from gaspatchio.frame.graph import verify as verify_module

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from gaspatchio.frame.graph import Check

runner = CliRunner()

_MODEL = """\
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.claims = af.sum_assured * 0.00123
    return af
"""


def _a_run(folder: Path, *, results: bool = True) -> tuple[Path, Path]:
    """Export a one-line model with ``calc-graph``; return the audit file, results."""
    folder.mkdir(parents=True, exist_ok=True)
    model = folder / "model.py"
    model.write_text(_MODEL)
    points = folder / "points.parquet"
    pl.DataFrame({"policy_id": ["P1"], "sum_assured": [1e5]}).write_parquet(points)
    audit, written = folder / "model.audit.json", folder / "results.parquet"
    arguments = ["calc-graph", str(model), str(points), "-o", str(audit)]
    if results:
        arguments += ["--results", str(written)]
    ran = runner.invoke(app, arguments)
    assert ran.exit_code == 0, ran.output
    return audit, written


def _doctored(audit: Path, **versions: object) -> dict[str, Any]:
    """Rewrite the record's versions and seal it again, as another exporter would."""
    document: dict[str, Any] = json.loads(audit.read_text())
    document["producer"]["versions"].update(versions)
    del document[DOCUMENT_DIGEST_FIELD]
    document[DOCUMENT_DIGEST_FIELD] = document_digest_of(document)
    audit.write_text(json.dumps(document, indent=2))
    return document


def _line(audit: Path, **given: Path) -> tuple[Check, str]:
    report = verify_artifact(audit, **given)
    versions = next(check for check in report.checks if check.name == "versions")
    return versions, report.verdict


def test_versions_that_agree_are_stated(tmp_path: Path) -> None:
    audit, results = _a_run(tmp_path)

    line, verdict = _line(audit, results=results)

    assert line.against == "producer.versions"
    assert line.outcome == "agree"
    assert "this process runs the same" in line.detail
    assert "manifest states the same versions" in line.detail
    assert verdict == "agree"


def test_a_record_from_another_library_is_stated_and_moves_no_exit_status(
    tmp_path: Path,
) -> None:
    audit, results = _a_run(tmp_path)
    _doctored(audit, polars_version="0.0.1")

    line, verdict = _line(audit, results=results)
    ran = runner.invoke(app, ["verify", str(audit), "--results", str(results)])

    assert line.outcome == "disagree"
    assert f"Polars 0.0.1 recorded, {pl.__version__} here" in line.detail
    assert "moves no exit status" in line.detail
    assert verdict == "agree"
    assert ran.exit_code == 0, ran.output


def test_a_record_and_its_manifest_that_disagree_are_stated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One run states one set; two that differ say the files are of two runs."""
    audit, results = _a_run(tmp_path)
    document = _doctored(audit, polars_version="0.0.1")
    recorded = {
        key: value
        for key, value in document["producer"]["versions"].items()
        if key != "imports"
    }
    monkeypatch.setattr(verify_module, "versions_in_this_process", lambda: recorded)

    line, verdict = _line(audit, results=results)

    assert line.outcome == "disagree"
    assert "this process runs the same" in line.detail
    assert (
        f"manifest states otherwise: Polars 0.0.1 recorded, {pl.__version__} "
        "in the manifest"
    ) in line.detail
    assert verdict == "agree"


def test_an_imported_package_not_installed_here_is_named(tmp_path: Path) -> None:
    audit, _ = _a_run(tmp_path, results=False)
    _doctored(audit, imports={"acme-actuarial": "2.3.1"})

    line, verdict = _line(audit)

    assert line.outcome == "disagree"
    assert "acme-actuarial 2.3.1 recorded, not installed here" in line.detail
    assert verdict == "agree"


def test_a_record_that_states_no_versions_is_not_asked(tmp_path: Path) -> None:
    audit, _ = _a_run(tmp_path, results=False)
    document: dict[str, Any] = json.loads(audit.read_text())
    del document["producer"]["versions"]
    del document[DOCUMENT_DIGEST_FIELD]
    document[DOCUMENT_DIGEST_FIELD] = document_digest_of(document)
    audit.write_text(json.dumps(document))

    line, verdict = _line(audit)

    assert line.outcome == "not_asked"
    assert "records no library versions" in line.detail
    assert verdict == "agree"


def test_a_record_that_withheld_its_versions_is_not_asked(tmp_path: Path) -> None:
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "model.py").write_text(_MODEL)
    pl.DataFrame({"sum_assured": [1e5]}).write_parquet(folder / "points.parquet")
    audit = folder / "model.audit.json"
    ran = runner.invoke(
        app,
        [
            "calc-graph",
            str(folder / "model.py"),
            str(folder / "points.parquet"),
            "-o",
            str(audit),
            "--no-versions",
        ],
    )
    assert ran.exit_code == 0, ran.output

    line, _ = _line(audit)

    assert line.outcome == "not_asked"
    assert "withheld" in line.detail


# --- diff ------------------------------------------------------------------------


def test_diff_names_a_library_that_moved_and_exits_as_nothing_moved(
    tmp_path: Path,
) -> None:
    """One graph fingerprint on a new library is no drift: it is why compare exists."""
    before, _ = _a_run(tmp_path / "q1", results=False)
    after, _ = _a_run(tmp_path / "q2", results=False)
    _doctored(after, polars_version="9.9.9", extension_sha256="sha256:" + "0" * 64)

    said = runner.invoke(app, ["diff", str(before), str(after)])
    stored = runner.invoke(app, ["diff", str(before), str(after), "--json"])

    assert said.exit_code == 0, said.output
    assert "nothing moved" in said.output
    assert (
        f"library: polars {pl.__version__} → 9.9.9; extension sha differs"
        in said.output
    )
    report = json.loads(stored.stdout)
    assert report["drift"] is False
    assert report["data"] == []
    assert stored.exit_code == 0


def test_diff_says_nothing_of_the_library_where_it_did_not_move(
    tmp_path: Path,
) -> None:
    before, _ = _a_run(tmp_path / "q1", results=False)
    after, _ = _a_run(tmp_path / "q2", results=False)

    said = runner.invoke(app, ["diff", str(before), str(after)])

    assert said.exit_code == 0, said.output
    assert "library:" not in said.output
