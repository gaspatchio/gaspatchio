# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A file outside the model's root is named, never climbed to from ``/``.

Inside the root a path is written relative to it, and a file beside the root
keeps its ``..`` segments, as it always did. A file whose only climb from the
root reaches the filesystem's root -- policy data on a shared volume, results
under ``/tmp``, a helper on another drive -- was written as that climb:
``../../../../../tmp/run-42/inforce_2026Q3.parquet``,
an absolute path spelled relatively, which names the machine in a document
the author sends to a reviewer. On Windows across drives the absolute path
itself survived. Now such a file is its name under
``<outside the model's root>``, the rule the git detail writer already applies
to the paths git names, with the name kept so the record still says which file
the run read. ``gspio verify`` and ``gspio diff`` read either form, because
neither resolves these paths: verify finds the files from its own arguments.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.cli import app
from gaspatchio.frame.graph import (
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    graph_models,
    validate_artifact,
)
from gaspatchio.frame.graph._model_files import Revision, stamped_file
from gaspatchio.frame.graph.graph_utils import relative_to_root
from tests.graph.test_model_identity_of import _a_checkout_at, _run_from_python

runner = CliRunner()

# The words a document carries in place of the directories above such a file.
OUTSIDE_THE_ROOT = "<outside the model's root>"

# A root that shares nothing with any test's files but the filesystem's root:
# a top-level directory nobody has, which no path is ever resolved against.
_ELSEWHERE = Path("/gaspatchio-a-root-elsewhere")

_ROOT = Path("/work/someone/projects/my-model")


def test_inside_and_beside_the_root_are_written_as_they_were() -> None:
    assert (
        relative_to_root(_ROOT / "models" / "mp.parquet", _ROOT) == "models/mp.parquet"
    )
    assert (
        relative_to_root("/work/someone/projects/shared/mp.parquet", _ROOT)
        == "../shared/mp.parquet"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/srv/results/inforce_2026Q3.parquet",
        "/Volumes/SHARED/books/inforce_2026Q3.parquet",
    ],
)
def test_a_climb_to_the_filesystem_root_is_the_file_name_outside_the_root(
    path: str,
) -> None:
    written = relative_to_root(path, _ROOT)
    assert written == f"{OUTSIDE_THE_ROOT}/inforce_2026Q3.parquet"
    assert ".." not in written
    assert not written.startswith("/")


def test_a_second_drive_is_the_file_name_and_never_the_absolute_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # What os.path.relpath does on Windows across drives (ntpath raises).
    def across_drives(*_args: object) -> str:
        msg = "path is on mount 'D:', start on mount 'C:'"
        raise ValueError(msg)

    monkeypatch.setattr(os.path, "relpath", across_drives)
    written = relative_to_root("/books/inforce_2026Q3.parquet", _ROOT)
    assert written == f"{OUTSIDE_THE_ROOT}/inforce_2026Q3.parquet"


def test_policy_data_outside_the_root_is_stamped_by_name(tmp_path: Path) -> None:
    points = tmp_path / "inforce_2026Q3.parquet"
    points.write_bytes(b"not really parquet")
    stamped = stamped_file(points, _ELSEWHERE)
    assert stamped is not None
    assert stamped["path"] == f"{OUTSIDE_THE_ROOT}/inforce_2026Q3.parquet"
    assert stamped["fingerprint"].startswith("sha256:")


def _a_helper_at(path: Path) -> Any:  # noqa: ANN401 -- a module loaded by path
    path.parent.mkdir(parents=True)
    path.write_text(
        "def add_loading(af):\n    af.loaded = af.sum_assured * 1.1\n    return af\n"
    )
    spec = importlib.util.spec_from_file_location("w5s_outside_helper", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _strings_in(document: Any) -> list[str]:  # noqa: ANN401 -- any JSON value
    if isinstance(document, dict):
        return [
            s for k, v in document.items() for s in (*_strings_in(k), *_strings_in(v))
        ]
    if isinstance(document, list):
        return [s for value in document for s in _strings_in(value)]
    return [document] if isinstance(document, str) else []


def test_a_helper_outside_the_root_is_located_by_name_and_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not under the temporary directory, which has its own rule (a cell file).
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "temporary"))
    helpers = _a_helper_at(tmp_path / "w5sec-helper" / "w5sec_helpers.py")
    frame = helpers.add_loading(ActuarialFrame({"sum_assured": [100.0]}))

    document = json.loads(GraphExporter(frame).export(source_root=_ELSEWHERE))

    named = f"{OUTSIDE_THE_ROOT}/w5sec_helpers.py"
    located = [n["source_location"] for n in document["nodes"] if n["source_location"]]
    assert located == [f"{named}:2"]
    (entry,) = document["sources"]
    assert entry["path"] == named
    assert entry["payload"] == {"omitted": "unavailable"}
    found = _strings_in(document)
    assert not any(str(tmp_path) in s or str(tmp_path.resolve()) in s for s in found)
    assert not any(s.startswith("../") for s in found)
    assert validate_artifact(document).ok


def test_an_assumption_file_outside_the_root_is_its_source_file_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "temporary"))
    basis = tmp_path / "bases" / "mortality_2026.parquet"
    basis.parent.mkdir()
    pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0011]}).write_parquet(basis)
    table = Table(
        name="w5s_outside_basis", source=basis, dimensions={"age": "age"}, value="rate"
    )
    frame = ActuarialFrame({"age": [30]})
    frame.q = table.lookup(age=frame.age)

    document = json.loads(GraphExporter(frame).export(source_root=_ELSEWHERE))

    (entry,) = document["assumptions"]
    assert entry["source_file"] == f"{OUTSIDE_THE_ROOT}/mortality_2026.parquet"


def _filed_outside(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Run and file a model whose root shares only ``/`` with its files."""
    model, points = _a_checkout_at(tmp_path / "repository")
    frame, result = _run_from_python(model, points)
    results = tmp_path / "out" / "results_2026Q3.parquet"
    results.parent.mkdir()
    result.write_parquet(results)
    monkeypatch.setattr(
        graph_models, "revision_of", lambda _model: Revision(git=None, root=_ELSEWHERE)
    )
    identity = ModelIdentity.of(model, model_points=points, results=results)
    audit = tmp_path / "out" / "share.audit.json"
    audit.write_text(
        GraphExporter(frame).export(result, GraphExportConfig(model=identity))
    )
    return {"model": model, "points": points, "results": results, "audit": audit}


def test_the_record_names_its_files_and_no_directory_of_the_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filed = _filed_outside(tmp_path, monkeypatch)
    document = json.loads(filed["audit"].read_text())
    model = document["model"]
    assert model["source_path"] == f"{OUTSIDE_THE_ROOT}/{filed['model'].name}"
    assert model["model_points"]["path"] == f"{OUTSIDE_THE_ROOT}/{filed['points'].name}"
    assert model["results"]["path"] == f"{OUTSIDE_THE_ROOT}/results_2026Q3.parquet"
    found = _strings_in(document)
    assert not any(str(tmp_path.resolve()) in s or str(tmp_path) in s for s in found)
    assert validate_artifact(document).ok


def test_verify_and_diff_read_a_record_that_names_files_outside_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filed = _filed_outside(tmp_path, monkeypatch)
    verified = runner.invoke(
        app,
        [
            "verify",
            str(filed["audit"]),
            "--model",
            str(filed["model"]),
            "--model-points",
            str(filed["points"]),
            "--results",
            str(filed["results"]),
        ],
    )
    assert verified.exit_code == 0, verified.output
    diffed = runner.invoke(app, ["diff", str(filed["audit"]), str(filed["audit"])])
    assert diffed.exit_code == 0, diffed.output
