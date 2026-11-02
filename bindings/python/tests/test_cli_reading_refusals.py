# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A command that reaches no answer says so on stderr, and stdout stays empty.

stdout carries the command's own document and nothing else, with ``--json``
and without, so a pipeline that reads it reads a document or nothing. A
refusal is one sentence on stderr with exit 2 -- as click's own refusal of a
file that does not exist already is. validate, verify, diff and compare read
an artifact through one gate, and every way a file can fail to be read leaves
by that rule; so do the refusals each command makes of its own.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph import FINGERPRINT_ALGORITHM
from tests.test_cli_artifact import _needle, _unwrapped, _valuation

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import Result

runner = CliRunner()

# What a checkout made without Git LFS holds in place of the file: no JSON,
# so no artifact, whichever way it is recognised.
_POINTER = (
    "version https://git-lfs.github.com/spec/v1\n"
    f"oid sha256:{'4d7a' * 16}\n"
    "size 38826\n"
)


def _refused_on_stderr(result: Result, named: str) -> None:
    """Assert a refusal: exit 2, nothing on stdout, and the sentence on stderr."""
    assert result.exit_code == 2, result.output
    assert result.stdout == "", result.stdout
    assert _needle(named) in _unwrapped(result.stderr), result.stderr


def _artifact(path: Path) -> Path:
    path.write_text(json.dumps(_valuation()))
    return path


@pytest.mark.parametrize("command", ["validate", "verify", "diff", "compare"])
@pytest.mark.parametrize(
    "content", ["this is not an artifact", _POINTER], ids=["unreadable", "pointer"]
)
def test_an_artifact_that_cannot_be_read_is_refused_on_stderr(
    tmp_path: Path, command: str, content: str
) -> None:
    unread = tmp_path / "artifact.json"
    unread.write_text(content)
    other = _artifact(tmp_path / "other.json")
    results = tmp_path / "results.parquet"
    results.write_bytes(b"")
    arguments = {
        "validate": ["validate", str(unread)],
        "verify": ["verify", str(unread)],
        "diff": ["diff", str(unread), str(other)],
        "compare": ["compare", str(unread), str(results), str(results)],
    }[command]

    result = runner.invoke(app, [*arguments, "--json"])

    _refused_on_stderr(result, unread.name)


def test_diff_refuses_a_file_that_is_not_there_as_click_would(tmp_path: Path) -> None:
    """The diff command reads its own operands, so it refuses as click would."""
    missing = tmp_path / "missing.json"
    other = _artifact(tmp_path / "other.json")

    result = runner.invoke(app, ["diff", str(missing), str(other), "--json"])

    _refused_on_stderr(result, missing.name)


def test_two_artifacts_diff_cannot_compare_are_refused_on_stderr(
    tmp_path: Path,
) -> None:
    before = _artifact(tmp_path / "before.json")
    later = _valuation()
    later["fingerprint_algorithm"] = f"{FINGERPRINT_ALGORITHM}-and-a-half"
    after = tmp_path / "after.json"
    after.write_text(json.dumps(later))

    result = runner.invoke(app, ["diff", str(before), str(after), "--json"])

    _refused_on_stderr(result, "These two artifacts cannot be compared")


def test_a_results_file_compare_cannot_read_is_refused_on_stderr(
    tmp_path: Path,
) -> None:
    artifact = _artifact(tmp_path / "artifact.json")
    results = tmp_path / "results.parquet"
    results.write_bytes(b"not parquet")

    result = runner.invoke(
        app, ["compare", str(artifact), str(results), str(results), "--json"]
    )

    _refused_on_stderr(result, "is not a result this can read")


def test_policy_data_verify_cannot_read_is_refused_on_stderr(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "artifact.json")
    points = tmp_path / "model_points.parquet"
    points.write_bytes(b"not parquet")

    result = runner.invoke(
        app, ["verify", str(artifact), "--model-points", str(points), "--json"]
    )

    _refused_on_stderr(result, "could not be read as policy data")


def test_a_report_that_cannot_be_stored_leaves_stdout_the_document(
    tmp_path: Path,
) -> None:
    """The report is stdout's, whole; the storing that failed is said on stderr."""
    artifact = _artifact(tmp_path / "artifact.json")
    nowhere = tmp_path / "no_such_directory" / "report.json"

    result = runner.invoke(
        app, ["validate", str(artifact), "--json", "-o", str(nowhere)]
    )

    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["ok"] is True
    assert _needle("not stored") in _unwrapped(result.stderr)


def test_a_page_diff_cannot_write_leaves_stdout_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the viewer, --json is still the report, and the refusal is stderr's."""
    monkeypatch.setitem(sys.modules, "gaspatchio_viewer", None)
    before = _artifact(tmp_path / "before.json")
    after = _artifact(tmp_path / "after.json")

    result = runner.invoke(
        app,
        ["diff", str(before), str(after), "--json", "--html", str(tmp_path / "p.html")],
    )

    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["drift"] is False
    assert _needle('pip install "gaspatchio[viewer]"') in _unwrapped(result.stderr)


@pytest.mark.skipif(
    importlib.util.find_spec("gaspatchio_viewer") is None,
    reason="the page is the gaspatchio-viewer distribution's; install viewer/python",
)
def test_a_page_diff_writes_beside_json_is_said_on_stderr(tmp_path: Path) -> None:
    """With --json, stdout is the report alone, and saying the page went is stderr's."""
    before = _artifact(tmp_path / "before.json")
    after = _artifact(tmp_path / "after.json")
    page = tmp_path / "drift.html"

    result = runner.invoke(
        app, ["diff", str(before), str(after), "--json", "--html", str(page)]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["drift"] is False
    assert _needle("Page saved to") in _unwrapped(result.stderr)
    assert page.is_file()


def test_a_pointer_on_disk_says_how_to_fetch_the_file(tmp_path: Path) -> None:
    """A checkout made without Git LFS left the pointer where the file should be.

    A file that only begins like a pointer -- a CSV whose header starts with
    the version line -- is read as the file it is, and refused as that.
    """
    pointer = tmp_path / "model.audit.json"
    pointer.write_text(_POINTER)
    near = tmp_path / "notes.audit.json"
    near.write_text("version https://git-lfs.github.com/spec/v1x,notes\n1,a\n")

    result = runner.invoke(app, ["validate", str(pointer)])
    near_result = runner.invoke(app, ["validate", str(near)])

    _refused_on_stderr(result, "is a Git LFS pointer, not the file it stands for")
    said = _unwrapped(result.stderr)
    assert _needle(f"sha256 {'4d7a' * 16}, 38826 bytes") in said
    assert _needle("checked out without Git LFS, and git lfs pull fetches it") in said
    _refused_on_stderr(near_result, "could not be read as an artifact document")
    assert "Git LFS" not in near_result.stderr
