# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every document the Audit View is tested against is one the format accepts.

The viewer's committed fixtures are the files its page is opened on in every
end-to-end run: exports of the tutorial models, and two built from the
published conformance corpus. A reader only ever opens a document a producer
wrote, so a fixture the schema refuses -- written before a member the format
now requires, say -- tests the page against a file no conforming producer
writes, and a behaviour that depends on the member goes untested. This reads
each committed fixture as the validator does. The ones the browser suite
writes for itself as it runs, which its ignore file names, are edits made on
purpose and are not read here.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph import validate_artifact

_VIEWER = Path(__file__).resolve().parents[4] / "viewer"


def _written_by_the_suite(name: str) -> bool:
    """Return whether the browser suite writes this file for itself."""
    ignore = _VIEWER / ".gitignore"
    patterns = [
        line.strip()
        for line in ignore.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("fixtures/")
    ]
    return any(fnmatch.fnmatch(f"fixtures/{name}", pattern) for pattern in patterns)


def _committed_documents() -> list[Path]:
    """Return every committed fixture that is a document rather than a report."""
    fixtures = _VIEWER / "fixtures"
    if not fixtures.is_dir():
        return []
    return sorted(
        path
        for path in fixtures.glob("*.json")
        if not _written_by_the_suite(path.name)
        and "schema" in json.loads(path.read_text(encoding="utf-8"))
    )


@pytest.mark.skipif(
    not (_VIEWER / "fixtures").is_dir(),
    reason="needs this repository's viewer/ tree",
)
def test_the_page_is_tested_against_every_fixture_it_ships() -> None:
    """The walk finds the fixtures, so a quiet empty list cannot pass for green."""
    assert len(_committed_documents()) >= 18


@pytest.mark.parametrize("fixture", _committed_documents(), ids=lambda path: path.stem)
def test_every_committed_fixture_is_a_document_the_schema_accepts(
    fixture: Path,
) -> None:
    """Schema and structure both, and the book every document now states."""
    verdict = validate_artifact(fixture)

    assert verdict.ok, [f"{one.where}: {one.message}" for one in verdict.findings]
    assert "book" in json.loads(fixture.read_text(encoding="utf-8"))


_RECORD = _VIEWER / "fixtures" / "record"


@pytest.mark.skipif(
    not (_RECORD / "model.py").is_file(),
    reason="needs this repository's viewer/ tree",
)
def test_the_record_fixture_samples_the_results_file_digit_for_digit(
    tmp_path: Path,
) -> None:
    """Every value the record page quotes is the value the results file holds.

    The page's selected cell, and the clipboard a copied cell fills, write the
    record's own tokens (``e2e/record.spec.ts``). This holds those tokens to
    the results Parquet an export of the same model writes: the committed
    document is exported again from the files beside it, outside any
    repository as its generator exports it, and every sampled value of the
    policy the document carries must equal that policy's row of the results
    file exactly and be written as ``repr`` writes it. It also holds the
    committed document to the export, so the page is tested against what this
    model's record says: the same graph, the same modules, the same tables.
    """
    for name in (
        "model.py",
        "loadings.py",
        "mortality.csv",
        "lapse.csv",
        "model_points.csv",
    ):
        (tmp_path / name).write_bytes((_RECORD / name).read_bytes())
    exported = CliRunner().invoke(
        app,
        [
            "calc-graph",
            str(tmp_path / "model.py"),
            str(tmp_path / "model_points.csv"),
            "--artifact",
            str(tmp_path / "record.json"),
            "--results",
            str(tmp_path / "results.parquet"),
            "--no-versions",
        ],
    )
    assert exported.exit_code == 0, exported.output

    text = (_VIEWER / "fixtures" / "record.json").read_text(encoding="utf-8")
    committed = json.loads(text)
    again = json.loads((tmp_path / "record.json").read_text(encoding="utf-8"))
    assert committed["graph_fingerprint"] == again["graph_fingerprint"]
    assert committed["model"]["modules"] == again["model"]["modules"]
    assert committed["assumptions"] == again["assumptions"]

    policy = committed["policies"][0]["policy_id"]
    results = pl.read_parquet(tmp_path / "results.parquet")
    held = results.filter(pl.col("policy_id").cast(pl.String) == policy).row(
        0, named=True
    )
    compared = 0
    for node in committed["nodes"]:
        column = node["column"]
        if column not in held or "value_sample" not in node:
            continue
        sample = node["value_sample"]
        value = held[column]
        written = value.isoformat() if hasattr(value, "isoformat") else value
        assert sample == written, column
        for one in sample if isinstance(sample, list) else [sample]:
            if isinstance(one, float):
                assert repr(one) in text, column
        compared += 1
    assert compared >= 8


_SCENARIOS = _VIEWER / "fixtures" / "scenarios.json"
_SCENARIO_RECORD = _VIEWER / "fixtures" / "scenarios.run.audit.json"


@pytest.mark.skipif(
    not _SCENARIO_RECORD.is_file(),
    reason="needs this repository's viewer/ tree",
)
def test_the_scenario_fixture_names_its_runs_record_and_neither_names_a_machine() -> (
    None
):
    """The two records of one run are committed together, and both withhold.

    ``viewer/fixtures/scenarios/export.py`` writes the pair with
    ``--no-versions``: the document's ``producer.versions`` and every version
    key of the run's own ``run_metadata`` are section 6.1's withheld form, so
    neither moves with the machine that regenerated it, and the document
    names the record where it is committed, by the digest of its bytes.
    """
    document = json.loads(_SCENARIOS.read_text(encoding="utf-8"))
    record = _SCENARIO_RECORD.read_bytes()
    audit = document["model"]["audit"]
    assert audit["path"].endswith("viewer/fixtures/scenarios.run.audit.json")
    assert audit["fingerprint"] == f"sha256:{hashlib.sha256(record).hexdigest()}"
    withheld = {"omitted": "withheld"}
    assert document["producer"]["versions"] == withheld
    metadata = json.loads(record)["run_metadata"]
    for key in (
        "core_version",
        "extension_version",
        "extension_sha256",
        "polars_version",
        "python_version",
        "platform",
        "ddsketch_version",
    ):
        assert metadata[key] == withheld, key
