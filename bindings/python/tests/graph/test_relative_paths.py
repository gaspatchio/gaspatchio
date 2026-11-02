# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every path an exported artifact carries, written against one stated root.

An artifact is a document other people read. A path in it that names the
directory the export happened to run in resolves on exactly one machine,
tells everybody it is shared with how that machine's disk is laid out, and
compares unequal between two runs of one model that never moved. So the
producer states one root -- the model file's directory, or the repository
the model sits in where the envelope names a revision -- and writes every
path relative to it: the location on each node, the model source, the policy
data, and the results file the run wrote.

The root itself is not in the file. It does not need to be: a reader holding
the artifact holds the model file too, the envelope says which of the two
bases applied by whether it carries a ``git`` block, and the paths resolve
from there.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
from typing import TYPE_CHECKING, Any, cast

import polars as pl
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()

MODEL_SRC = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.death_claims = af.sum_assured * 0.00123
    return af
"""

# The line of the one calculation in MODEL_SRC, counted from the leading
# newline the triple-quoted string opens with, so a node's location can be
# asserted in full rather than only up to its colon.
CLAIMS_LINE = 6


def _a_model_at(model_path: Path, points_path: Path) -> None:
    """Write the one-line model and the policy data it is run over."""
    model_path.parent.mkdir(parents=True, exist_ok=True)
    points_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(MODEL_SRC)
    pl.DataFrame({"policy_id": ["A"], "sum_assured": [100_000.0]}).write_parquet(
        points_path
    )


def _exported(model_path: Path, points_path: Path, *options: str) -> dict[str, Any]:
    """Export from the command line, where the root is decided, and read it back."""
    out = model_path.parent / "graph.json"
    result = runner.invoke(
        app,
        ["calc-graph", str(model_path), str(points_path), "-o", str(out), *options],
    )
    assert result.exit_code == 0, result.output
    return cast("dict[str, Any]", json.loads(out.read_text()))


def _strings_in(document: Any) -> list[str]:  # noqa: ANN401 — any JSON value
    """Return every string anywhere in a document, at any depth."""
    if isinstance(document, dict):
        return [
            found
            for key, value in document.items()
            for found in (*_strings_in(key), *_strings_in(value))
        ]
    if isinstance(document, list):
        return [found for value in document for found in _strings_in(value)]
    return [document] if isinstance(document, str) else []


def _naming(document: dict[str, Any], directory: Path) -> list[str]:
    """Return every string in ``document`` that names ``directory`` on this disk."""
    absolute = {str(directory), str(directory.resolve())}
    return [
        found
        for found in _strings_in(document)
        if any(machine in found for machine in absolute)
    ]


def _located(document: dict[str, Any]) -> list[str]:
    """Return the source location of every node that has one."""
    return [
        node["source_location"]
        for node in document["nodes"]
        if node.get("source_location") is not None
    ]


def _git(directory: Path, *arguments: str) -> str:
    """Run git in ``directory`` and return what it said."""
    completed = subprocess.run(  # noqa: S603 — a fixed argument list, run without a shell
        ["git", "-C", str(directory), *arguments],  # noqa: S607 — resolved on PATH
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _a_repository_at(directory: Path) -> None:
    """Make ``directory`` a repository with everything in it committed.

    Signing and the committer's identity are set on the call rather than
    read from whatever the machine running the tests has configured, so that
    this repository comes into existence the same way everywhere.
    """
    _git(directory, "-c", "init.defaultBranch=main", "init")
    _git(directory, "add", "--all")
    _git(
        directory,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--message",
        "the model and its policy data",
    )


# --- the model's own directory, where there is no repository ---------------


def test_a_model_outside_a_repository_is_written_against_its_own_directory(
    tmp_path: Path,
) -> None:
    """The base when the envelope names no revision, and nothing else to use.

    The model file's directory is what a reader holding the model file holds,
    which is the whole test of a base: it is knowable to the reader without
    the document telling them.
    """
    _a_model_at(tmp_path / "model.py", tmp_path / "model_points.parquet")

    document = _exported(tmp_path / "model.py", tmp_path / "model_points.parquet")

    assert document["model"]["git"] is None
    assert document["model"]["source_path"] == "model.py"
    assert document["model"]["model_points"]["path"] == "model_points.parquet"
    assert _located(document) == [f"model.py:{CLAIMS_LINE}"]


def test_no_string_anywhere_in_the_document_names_the_exporting_directory(
    tmp_path: Path,
) -> None:
    """The claim the root is for, made over the whole file rather than a field.

    Not "the fields we thought of are relative" but "the machine's directory
    is not in this document" -- which is the claim a person sharing an
    artifact outside their own organisation is relying on, and the only one
    that a new field carrying a path could not quietly break.
    """
    _a_model_at(tmp_path / "model.py", tmp_path / "model_points.parquet")

    document = _exported(tmp_path / "model.py", tmp_path / "model_points.parquet")

    assert _naming(document, tmp_path) == []


# --- the repository, where the envelope names a revision -------------------


def test_a_model_in_a_repository_is_written_against_the_repository_root(
    tmp_path: Path,
) -> None:
    """The wider base, so that a model reading a sibling directory stays inside.

    A model in ``models/`` reading its policy data from ``data/`` is the
    ordinary layout, and against the model's own directory both paths would
    need ``..`` to reach anything. Against the checkout they are the paths
    somebody who cloned that repository would type.
    """
    _a_model_at(tmp_path / "models" / "model.py", tmp_path / "data" / "points.parquet")
    _a_repository_at(tmp_path)

    document = _exported(
        tmp_path / "models" / "model.py", tmp_path / "data" / "points.parquet"
    )

    assert document["model"]["git"]["commit"] == _git(tmp_path, "rev-parse", "HEAD")
    assert document["model"]["source_path"] == "models/model.py"
    assert document["model"]["model_points"]["path"] == "data/points.parquet"
    assert _located(document) == [f"models/model.py:{CLAIMS_LINE}"]
    assert _naming(document, tmp_path) == []


# --- a file outside the root ------------------------------------------------


def test_a_results_file_outside_the_root_is_written_with_dot_dot_segments(
    tmp_path: Path,
) -> None:
    """Where the run wrote its numbers is a fact, and ``..`` is how it is kept.

    Left absolute this one field would put the exporting machine's layout
    back into every artifact whose output directory sits beside the model
    rather than under it -- which is where a valuation run usually writes.
    The content stamp is over the file's own bytes and does not move for any
    of this: the two answer different questions, and a reader resolving the
    path from the root reaches the file the fingerprint was taken over.
    """
    _a_model_at(
        tmp_path / "project" / "model.py", tmp_path / "project" / "points.parquet"
    )
    results = tmp_path / "elsewhere" / "results.parquet"
    results.parent.mkdir()

    document = _exported(
        tmp_path / "project" / "model.py",
        tmp_path / "project" / "points.parquet",
        "--output-file",
        str(results),
    )

    assert document["model"]["results"]["path"] == "../elsewhere/results.parquet"
    root = tmp_path / "project"
    written = (root / document["model"]["results"]["path"]).resolve()
    assert written == results.resolve()
    assert document["model"]["results"]["fingerprint"] == (
        f"sha256:{hashlib.sha256(written.read_bytes()).hexdigest()}"
    )
    assert _naming(document, tmp_path) == []


# --- the identity the root must not touch ----------------------------------


def _level_4() -> ActuarialFrame:
    """Return the reconciled lifelib model, run over its own policy data."""
    from gaspatchio.tutorials import get_tutorials_dir

    path = get_tutorials_dir() / "level-4-lifelib" / "base" / "model.py"
    spec = importlib.util.spec_from_file_location("level_4_for_paths", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    points = pl.read_parquet(path.parent / "model_points.parquet")
    return cast("ActuarialFrame", module.main(ActuarialFrame(points)))


def test_the_root_moves_no_fingerprint_in_the_largest_model_shipped(
    tmp_path: Path,
) -> None:
    """The identity of a model is the calculation, and a path is not one.

    114 locations move here and not one digest may. If a node's fingerprint
    took in where it was written, every artifact's identity would change with
    its directory: the same model, cloned to a second machine, would compare
    as a different model, and the quarter-over-quarter comparison the
    fingerprints exist for would be worthless.
    """
    frame = _level_4()
    exporter = GraphExporter(frame)

    unrooted = json.loads(exporter.export())
    from_the_package = json.loads(exporter.export(source_root=tmp_path))

    assert [node["source_location"] for node in unrooted["nodes"]] != [
        node["source_location"] for node in from_the_package["nodes"]
    ]
    assert unrooted["graph_fingerprint"] == from_the_package["graph_fingerprint"]
    assert [node["fingerprint"] for node in unrooted["nodes"]] == [
        node["fingerprint"] for node in from_the_package["nodes"]
    ]
    assert [node["local_fingerprint"] for node in unrooted["nodes"]] == [
        node["local_fingerprint"] for node in from_the_package["nodes"]
    ]


# --- locations that are not paths under the root -----------------------------


def _a_frame() -> ActuarialFrame:
    """Return a one-policy frame for a calculation to be written onto."""
    return ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))


def _exported_under_a_root(frame: ActuarialFrame, model: Path) -> dict[str, Any]:
    """Export ``frame`` with the version block read off ``model``'s own directory."""
    from gaspatchio.frame.graph import GraphExportConfig, ModelIdentity

    config = GraphExportConfig(model=ModelIdentity.of(model))
    return cast(
        "dict[str, Any]", json.loads(GraphExporter(frame).export(config=config))
    )


def test_a_location_that_names_no_file_is_written_as_it_was_recorded(
    tmp_path: Path,
) -> None:
    """A notebook cell is a place, not a path, and no root can move it.

    Written against a root, "Jupyter Cell 3" became "models/Jupyter Cell 3" --
    a file under the root that nobody wrote.
    """
    import linecache

    model = tmp_path / "project" / "model.py"
    _a_model_at(model, tmp_path / "project" / "points.parquet")
    cell = "<ipython-input-3-a1b2c3>"
    source = "af.death_claims = af.sum_assured * 0.00123\n"
    linecache.cache[cell] = (len(source), None, [source], cell)
    frame = _a_frame()
    try:
        exec(compile(source, cell, "exec"), {"af": frame})  # noqa: S102 -- a notebook cell, run as a notebook runs one
        document = _exported_under_a_root(frame, model)
    finally:
        linecache.cache.pop(cell, None)

    assert _located(document) == ["Jupyter Cell 3:1"]
    assert [entry["path"] for entry in document["sources"]] == ["Jupyter Cell 3"]


def test_a_location_in_a_temporary_file_names_the_file_and_no_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A notebook kernel keeps each cell in a temporary file, named and not climbed to.

    Written as a climb out of the root, the cell's location became
    ``../../../../var/folders/...`` -- an absolute path spelled relatively,
    which names the exporting machine's temporary directory and resolves for
    nobody. A file under the temporary directory, where the root is not, is
    named by its own name in the angle brackets Python uses for code with no
    file a reader can open, and its sources entry is unavailable, as any
    file outside the root is.
    """
    temporary = tmp_path / "temporary"
    monkeypatch.setattr(tempfile, "tempdir", str(temporary))
    model = tmp_path / "project" / "model.py"
    _a_model_at(model, tmp_path / "project" / "points.parquet")
    cell = temporary / "ipykernel_4242" / "2863477632.py"
    cell.parent.mkdir(parents=True)
    cell.write_text(
        "def add_claims(af):\n    af.death_claims = af.sum_assured * 0.00123\n"
        "    return af\n"
    )
    spec = importlib.util.spec_from_file_location("a_kernel_cell", cell)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    document = _exported_under_a_root(module.add_claims(_a_frame()), model)

    assert _located(document) == ["<2863477632.py>:2"]
    (entry,) = document["sources"]
    assert entry["path"] == "<2863477632.py>"
    assert entry["fingerprint"] is None
    assert entry["payload"] == {"omitted": "unavailable"}
    assert _naming(document, tmp_path) == []
    assert not any(found.startswith("..") for found in _strings_in(document))


def test_a_file_outside_the_root_elsewhere_keeps_its_climb(tmp_path: Path) -> None:
    """A helper in a sibling directory resolves for anybody with that layout."""
    model = tmp_path / "project" / "model.py"
    _a_model_at(model, tmp_path / "project" / "points.parquet")
    helpers = tmp_path / "shared" / "helpers.py"
    helpers.parent.mkdir()
    helpers.write_text(
        "def add_claims(af):\n    af.death_claims = af.sum_assured * 0.00123\n"
        "    return af\n"
    )
    spec = importlib.util.spec_from_file_location("a_shared_helper", helpers)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    document = _exported_under_a_root(module.add_claims(_a_frame()), model)

    assert _located(document) == ["../shared/helpers.py:2"]
    assert _naming(document, tmp_path) == []
