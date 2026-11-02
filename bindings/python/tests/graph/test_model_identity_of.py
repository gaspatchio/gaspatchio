# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The version block a Python export writes, filled in from the model file.

``gspio calc-graph`` has always said which model an audit file is an account
of: the file, its bytes, the revision it sat at and the policy data it was
run over. A model exported from Python said none of it unless the caller
built the block by hand, so the audit file a notebook wrote carried a block of
nulls and nothing a reviewer could check it against.

``ModelIdentity.of`` is the one helper both routes now call, so the two write
the same block. The export then writes every node's location against the
root the block's own paths were written against, so a Python export states
no absolute path either -- which is what the format has always required of
every document.
"""

from __future__ import annotations

import doctest
import hashlib
import importlib.util
import io
import json
from typing import TYPE_CHECKING, Any, cast

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import (
    SOURCE_DIRECTORY,
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    payload_file_name,
)
from tests.graph.test_relative_paths import (
    CLAIMS_LINE,
    _a_model_at,
    _a_repository_at,
    _git,
    _located,
    _naming,
)

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _bytes_digest(path: Path) -> str:
    """Return the stamp over a file's own bytes, the way the block takes it."""
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _a_checkout_at(repository: Path) -> tuple[Path, Path]:
    """Commit a model in ``models/`` and its policy data in ``data/``.

    Python caches the model's bytecode beside it the moment the model is
    imported, and an untracked cache is an uncommitted change to a tree
    whose state the block reports. The checkout ignores it, as a real one
    would, so the tree is clean because nothing in it moved.
    """
    model = repository / "models" / "model.py"
    points = repository / "data" / "points.parquet"
    _a_model_at(model, points)
    (repository / ".gitignore").write_text("__pycache__/\n")
    _a_repository_at(repository)
    return model, points


def _run_from_python(model: Path, points: Path) -> tuple[ActuarialFrame, pl.DataFrame]:
    """Run the model the way a notebook does: import it, hand it the book, collect."""
    spec = importlib.util.spec_from_file_location("model_run_from_python", model)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    frame = cast("ActuarialFrame", module.main(ActuarialFrame(pl.read_parquet(points))))
    return frame, frame.collect()


def _exported_from_python(model: Path, points: Path) -> dict[str, Any]:
    """Export from Python with the one line the block asks of a caller."""
    frame, result = _run_from_python(model, points)
    config = GraphExportConfig(model=ModelIdentity.of(model, model_points=points))
    return cast(
        "dict[str, Any]", json.loads(GraphExporter(frame).export(result, config))
    )


def _exported_from_the_command_line(
    model: Path, points: Path, out: Path, *options: str
) -> dict[str, Any]:
    """Export the same model through ``gspio calc-graph`` and read it back."""
    out.parent.mkdir(parents=True, exist_ok=True)
    result = runner.invoke(
        app, ["calc-graph", str(model), str(points), "-o", str(out), *options]
    )
    assert result.exit_code == 0, result.output
    return cast("dict[str, Any]", json.loads(out.read_text()))


def _locations_by_node(document: dict[str, Any]) -> dict[str, str]:
    """Return each located node's ``source_location``, keyed by its id."""
    return {
        node["id"]: node["source_location"]
        for node in document["nodes"]
        if node.get("source_location") is not None
    }


# --- what the helper reads off the model file --------------------------------


def test_of_reads_the_model_file_its_bytes_and_its_revision(tmp_path: Path) -> None:
    """Every member a model file can answer, answered from that file."""
    model, _ = _a_checkout_at(tmp_path)

    identity = ModelIdentity.of(model)

    assert identity.source_path == "models/model.py"
    assert identity.source_sha == _bytes_digest(model)
    assert identity.git == {
        "commit": _git(tmp_path, "rev-parse", "HEAD"),
        "dirty": False,
    }
    assert identity.label is None
    assert identity.model_points is None


def test_each_named_file_is_stamped_by_path_and_by_its_bytes(tmp_path: Path) -> None:
    """The policy data, the results and the run's own record, stamped one way."""
    model, points = _a_checkout_at(tmp_path / "repository")
    results = tmp_path / "out" / "results.parquet"
    results.parent.mkdir()
    pl.DataFrame({"death_claims": [123.0]}).write_parquet(results)

    identity = ModelIdentity.of(model, model_points=points, results=results)

    assert identity.model_points == {
        "path": "data/points.parquet",
        "fingerprint": _bytes_digest(points),
    }
    assert identity.results == {
        "path": "../out/results.parquet",
        "fingerprint": _bytes_digest(results),
    }
    assert identity.audit is None


def test_a_model_file_that_does_not_exist_is_refused_by_name(tmp_path: Path) -> None:
    """The one thing the helper cannot leave null is which file it was asked about."""
    with pytest.raises(FileNotFoundError, match=r"no_such_model\.py"):
        ModelIdentity.of(tmp_path / "no_such_model.py")


def test_a_member_the_file_cannot_answer_stays_null(tmp_path: Path) -> None:
    """Outside revision control there is no revision, and saying so is the answer."""
    model = tmp_path / "project" / "model.py"
    _a_model_at(model, tmp_path / "project" / "points.parquet")

    identity = ModelIdentity.of(model)

    assert identity.git is None
    assert identity.model_points is None
    assert identity.source_path == "model.py"


@pytest.mark.parametrize("member", ["model_points", "results", "audit"])
def test_a_named_file_that_is_not_there_is_refused_by_name(
    tmp_path: Path, member: str
) -> None:
    """A typo is not a run that wrote no file, and the block must not say it was.

    Left out, ``results`` says the run wrote no results file at all -- and a
    reader who then runs ``gspio verify`` is told to name the very file the
    caller did name.
    """
    model = tmp_path / "project" / "model.py"
    _a_model_at(model, tmp_path / "project" / "points.parquet")
    typo = tmp_path / "project" / "typo.parquet"

    with pytest.raises(FileNotFoundError, match=rf"{member}=.*typo\.parquet"):
        ModelIdentity.of(model, **{member: typo})


def test_a_directory_named_as_a_file_is_refused(tmp_path: Path) -> None:
    model = tmp_path / "project" / "model.py"
    _a_model_at(model, tmp_path / "project" / "points.parquet")

    with pytest.raises(FileNotFoundError, match="model_points"):
        ModelIdentity.of(model, model_points=tmp_path / "project")


def _commit_everything(repository: Path, message: str) -> None:
    """Commit the checkout as it stands, signed by nobody, as the fixture does."""
    _git(repository, "add", "--all")
    _git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--message",
        message,
    )


def test_a_model_the_commit_does_not_hold_is_recorded_dirty(tmp_path: Path) -> None:
    """A model in an ignored directory is not in the commit the block names.

    git reports such a tree as clean -- an ignored file is no change to it --
    so the commit alone would claim to hold a model it never saw. The block
    says the tree was dirty instead, which is what a reader needs to hear:
    the commit does not hold the model as it ran.
    """
    model, _ = _a_checkout_at(tmp_path)
    (tmp_path / ".gitignore").write_text("__pycache__/\nscratch/\n")
    _commit_everything(tmp_path, "keep scratch work out of the repository")
    scratch = tmp_path / "scratch" / "model.py"
    scratch.parent.mkdir()
    scratch.write_bytes(model.read_bytes())

    identity = ModelIdentity.of(scratch)

    assert _git(tmp_path, "status", "--porcelain") == ""
    assert identity.git is not None
    assert identity.git["dirty"] is True


def test_dirty_describes_the_whole_working_tree(tmp_path: Path) -> None:
    """A note beside the model marks the tree dirty: the conservative reading."""
    model, _ = _a_checkout_at(tmp_path)
    (tmp_path / "notes.txt").write_text("nothing the model reads")

    identity = ModelIdentity.of(model)

    assert identity.git is not None
    assert identity.git["dirty"] is True


# --- what a Python export writes -----------------------------------------------


def test_a_python_export_in_a_checkout_says_which_model_and_which_commit(
    tmp_path: Path,
) -> None:
    """The block a notebook's audit file carries, with no field of it built by hand."""
    model, points = _a_checkout_at(tmp_path)

    block = _exported_from_python(model, points)["model"]

    assert block["source_path"] == "models/model.py"
    assert block["source_sha"] == _bytes_digest(model)
    assert block["git"] == {
        "commit": _git(tmp_path, "rev-parse", "HEAD"),
        "dirty": False,
    }


def test_the_command_line_and_python_write_one_block_and_one_set_of_locations(
    tmp_path: Path,
) -> None:
    """Two routes to one model, one account of it, apart from the file the CLI wrote."""
    model, points = _a_checkout_at(tmp_path / "repository")
    out = tmp_path / "out"

    from_cli = _exported_from_the_command_line(
        model, points, out / "cli.json", "--results", str(out / "results.parquet")
    )
    from_python = _exported_from_python(model, points)

    assert "results" in from_cli["model"]
    cli_block = {
        k: v for k, v in from_cli["model"].items() if k not in {"results", "audit"}
    }
    assert from_python["model"] == cli_block
    assert _locations_by_node(from_python) == _locations_by_node(from_cli)
    assert _locations_by_node(from_python) == {
        "death_claims@1": f"models/model.py:{CLAIMS_LINE}"
    }
    assert [entry["path"] for entry in from_python["sources"]] == [
        entry["path"] for entry in from_cli["sources"]
    ]


def test_neither_route_writes_an_absolute_path(tmp_path: Path) -> None:
    """The format's rule, held over every string in both documents."""
    model, points = _a_checkout_at(tmp_path / "repository")

    from_cli = _exported_from_the_command_line(model, points, tmp_path / "cli.json")
    from_python = _exported_from_python(model, points)

    assert _naming(from_cli, tmp_path) == []
    assert _naming(from_python, tmp_path) == []


def test_outside_git_paths_are_written_against_the_model_s_own_directory(
    tmp_path: Path,
) -> None:
    """The other base the format defines, and a null revision beside it."""
    model = tmp_path / "project" / "model.py"
    points = tmp_path / "project" / "points.parquet"
    _a_model_at(model, points)

    document = _exported_from_python(model, points)

    assert document["model"]["git"] is None
    assert document["model"]["source_path"] == "model.py"
    assert document["model"]["model_points"]["path"] == "points.parquet"
    assert _located(document) == [f"model.py:{CLAIMS_LINE}"]
    assert _naming(document, tmp_path) == []


# --- an identity is its fields -------------------------------------------------


def test_an_identity_equals_itself_read_back_from_its_fields(tmp_path: Path) -> None:
    """Equality is the claims the block makes, never where they were read from."""
    model, points = _a_checkout_at(tmp_path)
    identity = ModelIdentity.of(model, model_points=points)

    assert identity == ModelIdentity.model_validate(identity.model_dump())


def test_of_takes_the_label_the_block_carries(tmp_path: Path) -> None:
    """A label is the one member the files cannot answer, so the caller says it."""
    model, points = _a_checkout_at(tmp_path)
    frame, result = _run_from_python(model, points)
    config = GraphExportConfig(
        model=ModelIdentity.of(model, model_points=points, label="term-assurance")
    )

    document = json.loads(GraphExporter(frame).export(result, config))

    assert document["model"]["label"] == "term-assurance"
    assert _locations_by_node(document) == {
        "death_claims@1": f"models/model.py:{CLAIMS_LINE}"
    }


def test_a_copy_of_an_identity_keeps_its_root(tmp_path: Path) -> None:
    """``model_copy`` is how a block is edited, and it keeps where paths go."""
    model, points = _a_checkout_at(tmp_path / "repository")
    frame, result = _run_from_python(model, points)
    copied = ModelIdentity.of(model).model_copy(update={"label": "term-assurance"})

    document = json.loads(
        GraphExporter(frame).export(result, GraphExportConfig(model=copied))
    )

    assert document["model"]["label"] == "term-assurance"
    assert _naming(document, tmp_path) == []


def test_an_identity_rebuilt_from_its_fields_is_refused_without_a_root(
    tmp_path: Path,
) -> None:
    """A relative source_path beside absolute locations is two bases in one file.

    The root is not a field, so a block rebuilt from its fields carries none.
    Exported as it stands, its source_path would be relative and every node
    location absolute; the export refuses it and names both ways to a root.
    """
    model, points = _a_checkout_at(tmp_path / "repository")
    frame, result = _run_from_python(model, points)
    rebuilt = ModelIdentity(**ModelIdentity.of(model).model_dump())

    with pytest.raises(ValueError, match=r"ModelIdentity\.of.*source_root"):
        GraphExporter(frame).export(result, GraphExportConfig(model=rebuilt))


def test_a_config_read_back_from_json_is_refused_without_a_root(
    tmp_path: Path,
) -> None:
    model, points = _a_checkout_at(tmp_path / "repository")
    frame, result = _run_from_python(model, points)
    stored = GraphExportConfig(model=ModelIdentity.of(model)).model_dump_json()

    with pytest.raises(ValueError, match="source_root"):
        GraphExporter(frame).export(
            result, GraphExportConfig.model_validate_json(stored)
        )


def test_a_rebuilt_identity_exports_against_the_root_it_is_given(
    tmp_path: Path,
) -> None:
    """Naming the root is the other way, and it writes what the helper would."""
    repository = tmp_path / "repository"
    model, points = _a_checkout_at(repository)
    frame, result = _run_from_python(model, points)
    rebuilt = ModelIdentity(**ModelIdentity.of(model).model_dump())

    document = json.loads(
        GraphExporter(frame).export(
            result, GraphExportConfig(model=rebuilt), source_root=repository
        )
    )

    assert _locations_by_node(document) == {
        "death_claims@1": f"models/model.py:{CLAIMS_LINE}"
    }
    assert _naming(document, tmp_path) == []


# --- one root per document -----------------------------------------------------


def test_a_source_root_spelled_in_another_case_is_the_same_directory(
    tmp_path: Path,
) -> None:
    """On a filesystem that ignores case, two spellings of one directory are one."""
    repository = tmp_path / "repository"
    model, points = _a_checkout_at(repository)
    shouted = repository.parent / repository.name.upper()
    if not shouted.exists():
        pytest.skip("this filesystem tells the two spellings apart")
    frame, result = _run_from_python(model, points)
    config = GraphExportConfig(model=ModelIdentity.of(model, model_points=points))

    document = json.loads(
        GraphExporter(frame).export(result, config, source_root=shouted)
    )

    assert _locations_by_node(document) == {
        "death_claims@1": f"models/model.py:{CLAIMS_LINE}"
    }


def test_a_source_root_that_names_another_directory_is_refused(tmp_path: Path) -> None:
    """A document naming a commit writes its paths against that commit's checkout.

    The identity's paths are written against the checkout. A second root for
    the node locations would put two bases in one document, and a reader
    resolving one from the other would reach files that are not there.
    """
    model, points = _a_checkout_at(tmp_path / "repository")
    frame, result = _run_from_python(model, points)
    config = GraphExportConfig(model=ModelIdentity.of(model, model_points=points))

    with pytest.raises(ValueError, match="source_root"):
        GraphExporter(frame).export(result, config, source_root=tmp_path / "elsewhere")


def test_a_source_root_naming_the_same_directory_is_the_same_document(
    tmp_path: Path,
) -> None:
    """Saying the root the identity already carries changes nothing."""
    repository = tmp_path / "repository"
    model, points = _a_checkout_at(repository)
    frame, result = _run_from_python(model, points)
    config = GraphExportConfig(model=ModelIdentity.of(model, model_points=points))
    exporter = GraphExporter(frame)

    stated = json.loads(exporter.export(result, config, source_root=repository))
    taken = json.loads(exporter.export(result, config))

    assert _locations_by_node(stated) == _locations_by_node(taken)
    assert stated["model"] == taken["model"]


def test_the_sidecar_filing_reads_the_source_back_against_the_identity_root(
    tmp_path: Path,
) -> None:
    """The filing resolves a relative path against the root it was written against."""
    model, points = _a_checkout_at(tmp_path / "repository")
    frame, result = _run_from_python(model, points)
    config = GraphExportConfig(model=ModelIdentity.of(model, model_points=points))
    filing = tmp_path / "filed"

    document = json.loads(
        GraphExporter(frame).export_with_sidecar(filing, result, config)
    )

    entry = {entry["path"]: entry for entry in document["sources"]}["models/model.py"]
    beside = filing / SOURCE_DIRECTORY / payload_file_name(entry["fingerprint"])
    assert json.loads(beside.read_text("utf-8"))["text"] == model.read_text()


# --- the documented example ----------------------------------------------------


def test_the_documented_example_runs() -> None:
    """The one line a Python caller writes is shown, and it is executed here."""
    found = [
        test
        for test in doctest.DocTestFinder().find(
            ModelIdentity.of.__func__, "ModelIdentity.of", globs={}
        )
        if test.examples
    ]
    assert found, "ModelIdentity.of carries no runnable example"
    report = io.StringIO()
    doctest_runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for test in found:
        doctest_runner.run(test, out=report.write)

    assert doctest_runner.failures == 0, report.getvalue()
