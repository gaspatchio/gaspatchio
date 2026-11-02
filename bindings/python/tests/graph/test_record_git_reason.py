# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A record with no git revision says why.

``model.git`` was null whether the model sat outside any repository or git
was there and could not answer -- missing from ``PATH``, refusing a shared
drive as "dubious ownership", never replying -- so an audit file could not
tell "not under revision control" from "git could not be read". Null now
has the first meaning only; every other case is section 6.1's
``unavailable`` form, with git's own reason as ``detail``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import (
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    _model_files,
    validate_artifact,
    verify_artifact,
)
from tests.graph.test_model_identity_of import _a_checkout_at

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()

_DUBIOUS = "fatal: detected dubious ownership in repository at '{where}'"


def _a_model(folder: Path) -> Path:
    """Write a model file outside any repository."""
    folder.mkdir(parents=True, exist_ok=True)
    model = folder / "model.py"
    model.write_text("RATE = 0.00123\n")
    return model


def _a_git_that(folder: Path, script: str) -> Path:
    """Write a ``git`` on a directory of its own that runs ``script``, and return it."""
    bin_dir = folder / "fake-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    git = bin_dir / "git"
    git.write_text(f"#!/bin/sh\n{script}\n")
    git.chmod(0o755)
    return bin_dir


def _exported(model: Path) -> dict[str, Any]:
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
    af.claims = af.sum_assured * 0.00123
    config = GraphExportConfig(model=ModelIdentity.of(model))
    document: dict[str, Any] = json.loads(
        GraphExporter(af).export(af.collect(), config)
    )
    return document


# --- each cause told apart --------------------------------------------------------


def test_a_model_in_a_checkout_records_its_commit(tmp_path: Path) -> None:
    model, _ = _a_checkout_at(tmp_path / "repository")

    git = ModelIdentity.of(model).git

    assert git is not None
    assert set(git) == {"commit", "dirty"}


def test_a_model_outside_any_repository_records_null(tmp_path: Path) -> None:
    """The one thing null means: git ran and found no working tree."""
    assert ModelIdentity.of(_a_model(tmp_path / "plain")).git is None


def test_a_path_without_git_records_that_there_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _a_model(tmp_path / "plain")
    nowhere = tmp_path / "empty-bin"
    nowhere.mkdir()
    monkeypatch.setenv("PATH", str(nowhere))

    assert ModelIdentity.of(model).git == {
        "omitted": "unavailable",
        "detail": "no git executable on PATH",
    }


def test_a_git_that_refuses_the_directory_is_recorded_in_its_own_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared-drive case, and the path git names in it is not absolute."""
    model = _a_model(tmp_path / "share" / "q3")
    refusing = _a_git_that(
        tmp_path,
        f'echo "{_DUBIOUS.format(where=model.parent.parent)}" >&2\nexit 128',
    )
    monkeypatch.setenv("PATH", f"{refusing}:/usr/bin:/bin")

    git = ModelIdentity.of(model).git

    assert git == {
        "omitted": "unavailable",
        "detail": _DUBIOUS.format(where=".."),
    }


def test_no_absolute_path_git_names_reaches_the_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path git names without quotes is no more the machine's than a quoted one.

    git's first line can name a file bare -- "could not lock config file
    /home/<name>/.gitconfig: Permission denied" -- and on Windows by drive.
    One under the model's parent is written against the model's directory;
    one under an unrelated root, or on another drive, has no relative spelling
    that does not climb to the root and name the machine, and is written as a
    placeholder. Neither absolute string is in the document.
    """
    model = _a_model(tmp_path / "share" / "q3")
    beside = model.parent.parent / ".gitconfig"
    windows = "C:\\Users\\someone\\.gitconfig"
    said = (
        f"error: could not lock config file {beside}: Permission denied, "
        f"nor /etc/gitconfig, nor {windows}"
    )
    refusing = _a_git_that(tmp_path, f"printf '%s\\n' '{said}' >&2\nexit 128")
    monkeypatch.setenv("PATH", f"{refusing}:/usr/bin:/bin")

    document = _exported(model)
    written = json.dumps(document)

    assert document["model"]["git"] == {
        "omitted": "unavailable",
        "detail": (
            "error: could not lock config file ../.gitconfig: Permission denied, "
            "nor <a path outside the model's directory>, "
            "nor <a path outside the model's directory>"
        ),
    }
    for absolute in (str(beside), str(tmp_path), "/etc/gitconfig", "C:\\Users"):
        assert absolute not in written
        assert json.dumps(absolute)[1:-1] not in written


def test_a_git_that_never_answers_is_recorded_as_not_answering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _a_model(tmp_path / "plain")
    sleeping = _a_git_that(tmp_path, "exec sleep 5")
    monkeypatch.setenv("PATH", f"{sleeping}:/usr/bin:/bin")
    monkeypatch.setattr(_model_files, "_GIT_TIMEOUT_SECONDS", 1)

    assert ModelIdentity.of(model).git == {
        "omitted": "unavailable",
        "detail": "git did not answer within 1 s",
    }


def test_a_record_carrying_the_reason_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _a_model(tmp_path / "plain")
    nowhere = tmp_path / "empty-bin"
    nowhere.mkdir()
    monkeypatch.setenv("PATH", str(nowhere))

    document = _exported(model)

    assert document["model"]["git"]["omitted"] == "unavailable"
    assert validate_artifact(document).ok


# --- said at export ----------------------------------------------------------------


def test_the_export_says_once_that_no_revision_was_recorded(tmp_path: Path) -> None:
    """The actuary learns it as the file is written, not at audit."""
    model = _a_model(tmp_path / "plain")
    heard: list[str] = []
    logger.enable("gaspatchio")
    sink = logger.add(heard.append, level="INFO", format="{message}")
    try:
        _exported(model)
    finally:
        logger.remove(sink)

    said = [line.strip() for line in heard if "model.git" in line]
    assert said == ["model.git not recorded: model.py is not in a git working tree"]


# --- what verify makes of it ----------------------------------------------------------


def test_verify_reads_a_git_that_could_not_answer_as_indeterminate_and_moves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _a_model(tmp_path / "plain")
    nowhere = tmp_path / "empty-bin"
    nowhere.mkdir()
    with monkeypatch.context() as patched:
        patched.setenv("PATH", str(nowhere))
        document = _exported(model)
    audit = tmp_path / "model.audit.json"
    audit.write_text(json.dumps(document, indent=2))

    report = verify_artifact(audit, model=model)
    ran = runner.invoke(app, ["verify", str(audit), "--model", str(model)])

    git = next(check for check in report.checks if check.name == "git")
    assert git.outcome == "indeterminate"
    assert "no git executable on PATH" in git.detail
    # The one line left open is the graph, which this frame-built record
    # cannot be rebuilt for (no policy data is given): git holds nothing open.
    held_open = [
        check.name for check in report.checks if check.outcome == "indeterminate"
    ]
    assert held_open == ["graph", "git"]
    without_the_graph = [check for check in report.checks if check.name != "graph"]
    assert all(check.outcome != "disagree" for check in without_the_graph)
    assert report.verdict == "indeterminate"
    assert ran.exit_code == 4, ran.output


def test_verify_reads_a_null_git_as_a_model_outside_a_working_tree(
    tmp_path: Path,
) -> None:
    model = _a_model(tmp_path / "plain")
    audit = tmp_path / "model.audit.json"
    audit.write_text(json.dumps(_exported(model)))

    git = next(
        check
        for check in verify_artifact(audit, model=model).checks
        if check.name == "git"
    )

    assert git.outcome == "not_asked"
    assert "exported outside a git working tree" in git.detail
    assert "could not be read" not in git.detail
