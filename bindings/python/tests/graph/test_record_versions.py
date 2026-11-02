# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The audit file says which library produced its numbers.

A reviewer holding an audit file a quarter later asks whether this library
would give the same number. The record used to state the package's version
and nothing else -- the extension, Polars, Python and the platform were only
in a results file's Parquet footer -- so a record-only export could not
answer, and an editable install over an older extension read as a release.
``producer.versions`` states the six keys a results file's manifest does,
and ``imports`` the installed packages the model imports.
"""

from __future__ import annotations

import json
import pickle
import platform
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
import pytest
from typer.testing import CliRunner

import gaspatchio._internal as extension
from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.engines import report
from gaspatchio.engines._versions import versions_in_this_process
from gaspatchio.engines.protocol import read_manifest
from gaspatchio.frame.graph import (
    DOCUMENT_DIGEST_FIELD,
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    document_digest_of,
    validate_artifact,
)
from gaspatchio.frame.graph import artifact as artifact_module
from gaspatchio.scenarios._audit import library_versions

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# The six keys a result manifest states, in its own spelling.
_MANIFEST_KEYS = {
    "core_version",
    "extension_version",
    "extension_sha256",
    "polars_version",
    "python_version",
    "platform",
}

_MODEL = """\
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.claims = af.sum_assured * 0.00123
    return af
"""


def _a_model(folder: Path, text: str = _MODEL) -> tuple[Path, Path]:
    """Write a one-line model and its book outside any repository."""
    folder.mkdir(parents=True, exist_ok=True)
    model = folder / "model.py"
    model.write_text(text)
    points = folder / "points.parquet"
    pl.DataFrame({"policy_id": ["P1", "P2"], "sum_assured": [1e5, 2e5]}).write_parquet(
        points
    )
    return model, points


def _frame() -> tuple[ActuarialFrame, pl.DataFrame]:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
    af.claims = af.sum_assured * 0.00123
    return af, af.collect()


def _versions(document: dict[str, Any]) -> dict[str, Any]:
    stated: dict[str, Any] = document["producer"]["versions"]
    return stated


# --- what the record states ----------------------------------------------------


def test_one_calc_graph_run_states_one_set_in_the_record_and_the_manifest(
    tmp_path: Path,
) -> None:
    """The record and the results file of one run state the same six keys."""
    model, points = _a_model(tmp_path)
    audit, results = tmp_path / "model.audit.json", tmp_path / "results.parquet"

    ran = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(points),
            "-o",
            str(audit),
            "--results",
            str(results),
        ],
    )

    assert ran.exit_code == 0, ran.output
    stated = _versions(json.loads(audit.read_text()))
    manifest = read_manifest(results)
    assert {key: stated[key] for key in _MANIFEST_KEYS} == manifest.versions
    assert set(stated) == {*_MANIFEST_KEYS, "imports"}


def test_the_record_states_the_core_and_its_extension_each_as_it_is() -> None:
    """An editable install over an older extension shows as two numbers.

    In a development venv the core is installed as 0.9.0 over an extension built
    as 1.0.0; a release wheel states one number twice. Either way each key
    says what it names, read from its own source.
    """
    af, result = _frame()

    stated = _versions(json.loads(GraphExporter(af).export(result)))

    assert stated["core_version"] == version("gaspatchio")
    assert stated["extension_version"] == extension.__version__
    assert stated["polars_version"] == pl.__version__
    assert stated["python_version"] == platform.python_version()
    assert stated["extension_sha256"].startswith("sha256:")


def test_a_python_export_with_no_results_file_carries_the_versions() -> None:
    """The case gmdb's hand-written provenance script existed for."""
    af, _ = _frame()

    document = json.loads(GraphExporter(af).export())

    assert set(_versions(document)) == _MANIFEST_KEYS
    assert validate_artifact(document).ok


def test_a_frame_computed_elsewhere_states_the_versions_it_was_computed_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A frame pickled back from a worker states the worker's library.

    The run summary takes its versions as it is pickled, in the process that
    ran it; the export states those, not the exporting process's own.
    """
    af, result = _frame()
    worker = {**versions_in_this_process(), "polars_version": "worker-polars"}
    parent = {**versions_in_this_process(), "polars_version": "parent-polars"}
    monkeypatch.setattr(report, "versions_in_this_process", lambda: dict(worker))
    carried = pickle.dumps(af)
    monkeypatch.setattr(report, "versions_in_this_process", lambda: dict(parent))
    monkeypatch.setattr(
        artifact_module, "versions_in_this_process", lambda: dict(parent)
    )
    restored = pickle.loads(carried)  # noqa: S301 -- a pickle this test just wrote

    stated = _versions(json.loads(GraphExporter(restored).export(result)))

    assert stated["polars_version"] == "worker-polars"


def test_the_installed_packages_the_model_and_its_helpers_import_are_named(
    tmp_path: Path,
) -> None:
    """An installed package is as much the model as a helper is.

    ``numpy`` reached through a helper and ``polars`` from the model are
    named by version; the standard library, the helper itself and this
    package are not.
    """
    folder = tmp_path / "model"
    model, _ = _a_model(
        folder,
        "import json\nimport polars\nimport helpers\nimport gaspatchio\n" + _MODEL,
    )
    (folder / "helpers.py").write_text("import numpy as np\nimport os.path\n")
    af, result = _frame()
    config = GraphExportConfig(model=ModelIdentity.of(model))

    stated = _versions(json.loads(GraphExporter(af).export(result, config)))

    assert stated["imports"] == {"numpy": np.__version__, "polars": pl.__version__}


def test_an_export_asked_to_withhold_the_versions_says_so(tmp_path: Path) -> None:
    """A golden is exported without one machine's strings, and the file says why."""
    af, result = _frame()
    model, _ = _a_model(tmp_path)
    config = GraphExportConfig(model=ModelIdentity.of(model))

    document = json.loads(GraphExporter(af).export(result, config, versions="withheld"))

    assert document["producer"]["versions"] == {"omitted": "withheld"}
    assert validate_artifact(document).ok


def test_a_versions_setting_that_is_neither_is_refused() -> None:
    af, result = _frame()

    with pytest.raises(ValueError, match="not a setting"):
        GraphExporter(af).export(result, versions="none")  # type: ignore[arg-type]


def test_calc_graph_no_versions_records_them_as_withheld(tmp_path: Path) -> None:
    model, points = _a_model(tmp_path)
    audit = tmp_path / "model.audit.json"

    ran = runner.invoke(
        app,
        ["calc-graph", str(model), str(points), "-o", str(audit), "--no-versions"],
    )

    assert ran.exit_code == 0, ran.output
    assert json.loads(audit.read_text())["producer"]["versions"] == {
        "omitted": "withheld"
    }


def _resealed(document: dict[str, Any]) -> dict[str, Any]:
    """Return ``document`` sealed again, as its producer would have sealed it."""
    document.pop(DOCUMENT_DIGEST_FIELD, None)
    document[DOCUMENT_DIGEST_FIELD] = document_digest_of(document)
    return document


def test_a_document_without_the_member_still_validates() -> None:
    af, result = _frame()
    document = json.loads(GraphExporter(af).export(result))
    del document["producer"]["versions"]

    assert validate_artifact(_resealed(document)).ok


def test_the_schema_refuses_a_reason_versions_cannot_carry() -> None:
    """Withheld is the one reason: the versions are never weighed or unread."""
    af, result = _frame()
    document = json.loads(GraphExporter(af).export(result))
    document["producer"]["versions"] = {"omitted": "size", "bytes": 10}

    findings = validate_artifact(_resealed(document)).findings
    assert findings
    assert {finding.where for finding in findings} == {"/producer/versions"}


# --- the scenario sidecar ---------------------------------------------------------


def test_the_scenario_sidecar_states_the_records_keys_and_its_sketch() -> None:
    """One fact, one spelling: the sidecar's keys are the manifest's, plus one."""
    stated = library_versions()

    assert set(stated) == {*_MANIFEST_KEYS, "ddsketch_version"}
    assert {key: stated[key] for key in _MANIFEST_KEYS} == versions_in_this_process()
