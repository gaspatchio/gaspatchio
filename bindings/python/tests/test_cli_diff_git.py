# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio diff`` reading an audit file as a past revision committed it.

A team that commits the audit file beside the model holds every quarter's in
the repository's history, and ``git:REV:path`` reads one from there: no
checkout, and no second run of the model. Each test runs the command inside a
repository holding the audit file of one model at two revisions, with its
factor edited between them, and holds the answer to the one two files on disk
give.

Every way the operand can name nothing is no answer -- exit 2, the status kept
for a comparison that could not be made -- in a sentence naming the revision
and the path, never a traceback and never a finding against a model.
"""

from __future__ import annotations

import contextlib
import doctest
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from typer.testing import CliRunner

import gaspatchio
from gaspatchio.cli import app
from gaspatchio.frame.graph import diff_artifacts
from tests.graph.test_relative_paths import _git
from tests.test_cli_artifact import (
    MODEL_SRC,
    _needle,
    _reached_no_answer,
    _unwrapped,
    _valuation,
)

runner = CliRunner()

AUDIT = "model.audit.json"

# What a repository that keeps the audit file in Git LFS commits in its place,
# and a file that only begins like that.
_POINTER_OID = "4d7a" * 16
_POINTER = (
    "version https://git-lfs.github.com/spec/v1\n"
    f"oid sha256:{_POINTER_OID}\n"
    "size 38826\n"
)
_NEAR_MISS = "version https://git-lfs.github.com/spec/v1x,notes\n1,a reserve note\n"


@dataclass(frozen=True)
class _History:
    """A repository holding one model's audit file at two revisions.

    Attributes:
        root: The repository's top, which the test is run from.
        q2: The audit file ``v2026.Q2`` committed, parsed.
        q3: The audit file the next commit holds, as the working tree does.
        committed: The text ``v2026.Q2`` committed it as.

    """

    root: Path
    q2: dict[str, Any]
    q3: dict[str, Any]
    committed: str


def _fed(repository: Path, fed: str, *arguments: str) -> str:
    """Run git in ``repository`` with ``fed`` on its stdin, and return what it said."""
    completed = subprocess.run(  # noqa: S603 — a fixed argument list, run without a shell
        ["git", "-C", str(repository), *arguments],  # noqa: S607 — resolved on PATH
        input=fed,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _commit(repository: Path, message: str) -> None:
    """Commit the checkout as it stands, signed by nobody, as the fixtures do."""
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


@pytest.fixture(scope="module")
def recorded_history(tmp_path_factory: pytest.TempPathFactory) -> _History:
    """Return a repository whose audit file moved between two revisions.

    ``v2026.Q2`` holds the audit file of the factor 0.00123, beside the other
    things an audit file's path might wrongly name: the model source, a policy
    data file, a JSON array and a directory. The commit after it holds the
    audit file of the factor 0.00456 -- and, under ``term/``, the tag never
    held, a second model's audit files: ``term.audit.json``, and one named
    ``model.audit.json`` as the root's is, of the factor 0.00789. The working
    tree is that commit.

    Built once, because every git command is a process: each test runs in a
    copy of its own, which ``history`` makes.
    """
    root = tmp_path_factory.mktemp("history") / "repository"
    root.mkdir()
    q2, q3 = _valuation(0.00123), _valuation(0.00456)
    committed = json.dumps(q2, indent=2)
    (root / AUDIT).write_text(committed)
    (root / "model.py").write_text(MODEL_SRC)
    pl.DataFrame({"policy_id": ["A"], "sum_assured": [100_000.0]}).write_parquet(
        root / "model_points.parquet"
    )
    (root / "list.json").write_text("[]")
    (root / "q2 pointer.audit.json").write_text(_POINTER)
    (root / "notes.audit.json").write_text(_NEAR_MISS)
    (root / "audits q2").mkdir()
    (root / "audits q2" / AUDIT).write_text(committed)
    (root / "assumptions").mkdir()
    (root / "assumptions" / "mortality.csv").write_text("age,rate\n40,0.00123\n")
    _git(root, "-c", "init.defaultBranch=main", "init")
    _commit(root, "the second quarter")
    _git(root, "-c", "tag.gpgsign=false", "tag", "v2026.Q2")

    (root / AUDIT).write_text(json.dumps(q3, indent=2))
    (root / "term").mkdir()
    (root / "term" / "term.audit.json").write_text(json.dumps(q3, indent=2))
    (root / "term" / AUDIT).write_text(json.dumps(_valuation(0.00789), indent=2))
    _commit(root, "the third quarter")

    # What a revision can hold at a path besides a file, built with git's
    # plumbing so the working tree is untouched: a symbolic link and a
    # submodule, at the tag "edges", and a tag of a tree, "v-tree".
    identity = ("-c", "user.name=Test", "-c", "user.email=test@example.com")
    link = _fed(root, AUDIT, "hash-object", "-w", "--stdin")
    tree = _fed(
        root,
        f"100644 blob {_git(root, 'rev-parse', f'v2026.Q2:{AUDIT}')}\t{AUDIT}\n"
        f"120000 blob {link}\tlink.audit.json\n"
        f"160000 commit {_git(root, 'rev-parse', 'v2026.Q2')}\tsub\n",
        "mktree",
    )
    edges = _git(
        root,
        *identity,
        "-c",
        "commit.gpgsign=false",
        "commit-tree",
        tree,
        "-m",
        "a symbolic link and a submodule",
    )
    _git(root, "-c", "tag.gpgsign=false", "tag", "edges", edges)
    _git(
        root,
        *identity,
        "-c",
        "tag.gpgsign=false",
        "tag",
        "-a",
        "-m",
        "a tree, not a commit",
        "v-tree",
        tree,
    )
    return _History(root=root, q2=q2, q3=q3, committed=committed)


@pytest.fixture
def history(
    recorded_history: _History, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _History:
    """Return a copy of the repository for one test, and run the test from its top."""
    root = tmp_path / "repository"
    shutil.copytree(recorded_history.root, root, symlinks=True)
    monkeypatch.chdir(root)
    return replace(recorded_history, root=root)


# --- reading the file a revision committed ---------------------------------


def test_the_audit_file_a_revision_committed_is_compared_without_a_checkout(
    history: _History,
) -> None:
    """The repro: the tag's audit file against the working tree's, one command."""
    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT])

    assert result.exit_code == 1, result.output
    printed = _unwrapped(result.output)
    assert _needle(f"something moved between {AUDIT} at v2026.Q2 and {AUDIT}") in (
        printed
    )
    assert _needle("changed death_claims@1 (self)") in printed
    # Read out of the history: nothing was checked out, and the tree is as it was.
    assert _git(history.root, "status", "--porcelain") == ""
    assert len(_git(history.root, "worktree", "list").splitlines()) == 1


@pytest.mark.usefixtures("history")
def test_a_revision_that_committed_the_same_audit_file_is_nothing_moved() -> None:
    result = runner.invoke(app, ["diff", f"git:HEAD:{AUDIT}", AUDIT])

    assert result.exit_code == 0, result.output
    assert _needle(f"nothing moved between {AUDIT} at HEAD and {AUDIT}") in (
        _unwrapped(result.output)
    )


@pytest.mark.usefixtures("history")
def test_both_sides_can_be_revisions() -> None:
    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", f"git:HEAD:{AUDIT}"])

    assert result.exit_code == 1, result.output
    assert _needle(f"between {AUDIT} at v2026.Q2 and {AUDIT} at HEAD") in (
        _unwrapped(result.output)
    )


def test_the_json_report_is_the_one_the_two_documents_give(history: _History) -> None:
    """The report is the documents' own: the operand adds nothing to it.

    ``compared`` says which two documents were read by what they say about
    themselves, so what it says of the committed one is what two files on disk
    would give -- its fingerprint, its seal and when it was written.
    """
    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT, "--json"])

    assert result.exit_code == 1, result.output
    report = json.loads(result.stdout)
    assert report == diff_artifacts(history.q2, history.q3).to_dict()
    before = report["compared"]["before"]
    assert before["graph_fingerprint"] == history.q2["graph_fingerprint"]
    assert before["created_at"] == history.q2["created_at"]


@pytest.mark.skipif(
    importlib.util.find_spec("gaspatchio_viewer") is None,
    reason="the page is the gaspatchio-viewer distribution's; install viewer/python",
)
def test_the_page_carries_the_committed_bytes(history: _History) -> None:
    """The earlier block is the blob the revision holds, byte for byte."""
    page = history.root.parent / "drift.html"

    result = runner.invoke(
        app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT, "--html", str(page)]
    )

    assert result.exit_code == 1, result.output
    html = page.read_text()
    blocks = re.findall(
        r'<script type="application/json" id="artifact"'
        r'(?: data-label="[^"]*")?>(.*?)</script>',
        html,
        re.DOTALL,
    )
    # Built rather than written, for the reason test_cli_artifact gives.
    escape = chr(92) + "u003c"
    assert [block.replace(escape, "<") for block in blocks] == [
        (history.root / AUDIT).read_text(),
        history.committed,
    ]
    assert "<title>model.audit vs model.audit at v2026.Q2</title>" in html
    # Each side is named on the page as the command line named it, the
    # revision's with the revision, so a reader handed the page alone can
    # tell which audit file is which.
    labels = re.findall(r'id="artifact" data-label="([^"]*)"', html)
    assert labels == [AUDIT, f"{AUDIT} at v2026.Q2"]


def test_a_replace_ref_does_not_change_the_bytes_read(history: _History) -> None:
    """The bytes are the ones the revision committed, whatever replace refs say.

    git replace swaps one object for another in everything git reads, so with
    the second quarter's audit file replaced by the third's, a reading that
    honoured it compared the swap: two revisions that differ, as nothing moved.
    """
    root = history.root
    q2_blob = _git(root, "rev-parse", f"v2026.Q2:{AUDIT}")
    _git(root, "replace", q2_blob, _git(root, "rev-parse", f"HEAD:{AUDIT}"))

    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", f"git:HEAD:{AUDIT}"])

    assert result.exit_code == 1, result.output
    assert _needle("changed death_claims@1 (self)") in _unwrapped(result.output)


def test_a_revision_across_a_graft_is_read_through_the_recorded_parents(
    history: _History,
) -> None:
    """A graft gives a commit other parents for git; the reading keeps the real ones.

    HEAD is grafted onto a commit of no history holding the third quarter's
    audit file, so through the graft HEAD~1 holds what HEAD does. Read as
    committed, HEAD~1 is the second quarter.
    """
    root = history.root
    identity = ("-c", "user.name=Test", "-c", "user.email=test@example.com")
    orphan = _git(
        root,
        *identity,
        "-c",
        "commit.gpgsign=false",
        "commit-tree",
        _git(root, "rev-parse", "HEAD^{tree}"),
        "-m",
        "a commit of no history",
    )
    _git(root, *identity, "replace", "--graft", "HEAD", orphan)

    result = runner.invoke(app, ["diff", f"git:HEAD~1:{AUDIT}", AUDIT, "--json"])

    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout) == diff_artifacts(history.q2, history.q3).to_dict()


# --- where the path is read from -------------------------------------------


def test_a_path_is_read_from_the_root_and_dot_slash_reads_it_from_here(
    history: _History, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule is git's own, so the operand names what ``git show`` would show."""
    monkeypatch.chdir(history.root / "term")

    result = runner.invoke(
        app, ["diff", "git:HEAD:./term.audit.json", "git:HEAD:term/term.audit.json"]
    )

    assert result.exit_code == 0, result.output


def test_a_path_written_from_a_subdirectory_is_refused_with_the_operand_that_reads_it(
    history: _History, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read from the root, the path names nothing; the refusal gives the fix."""
    monkeypatch.chdir(history.root / "term")

    result = runner.invoke(app, ["diff", "git:HEAD:term.audit.json", f"../{AUDIT}"])

    _reached_no_answer(result, "HEAD holds no file at term.audit.json")
    assert _needle("read from the repository's root") in _unwrapped(result.output)
    assert _needle("git:HEAD:./term.audit.json") in _unwrapped(result.output)


@pytest.mark.parametrize(
    ("revision", "there", "beside"),
    [
        (
            "HEAD",
            f"term/{AUDIT} is at HEAD too",
            f"git:HEAD:./{AUDIT} for term/{AUDIT}",
        ),
        (
            "v2026.Q2",
            f"term/{AUDIT} is on disk here, though not at v2026.Q2",
            f"{AUDIT} on its own for the file on disk",
        ),
    ],
)
def test_a_path_that_names_a_file_both_ways_from_a_subdirectory_is_refused(
    history: _History,
    monkeypatch: pytest.MonkeyPatch,
    revision: str,
    there: str,
    beside: str,
) -> None:
    """From term/, model.audit.json is the root's to git and term/'s to a reader.

    git reads a plain path from the root, so the help's own example, run from
    a model's directory, compared the root's audit file -- another model's --
    with that model's own. Where the current directory holds a file of the
    name too, at the revision or on disk, the operand does not say which is
    meant, and it is refused with a spelling that reads each. A file there on
    disk alone is read as the file it is: the revision has no such file to
    offer for ./.
    """
    monkeypatch.chdir(history.root / "term")

    result = runner.invoke(app, ["diff", f"git:{revision}:{AUDIT}", AUDIT])

    _reached_no_answer(
        result, f"From term/, git:{revision}:{AUDIT} could name two files"
    )
    said = _unwrapped(result.output)
    assert _needle(there) in said
    assert _needle(beside) in said
    assert _needle(f"git:{revision}:../{AUDIT} for {AUDIT} at the root") in said
    if revision == "v2026.Q2":
        assert _needle(f"git:{revision}:./{AUDIT}") not in said


def test_each_spelling_from_a_subdirectory_reads_its_own_file(
    history: _History, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two spellings the refusal gives read the two files it names."""
    monkeypatch.chdir(history.root / "term")

    here = runner.invoke(app, ["diff", f"git:HEAD:./{AUDIT}", AUDIT])
    root = runner.invoke(app, ["diff", f"git:HEAD:../{AUDIT}", f"../{AUDIT}"])

    assert here.exit_code == 0, here.output
    assert root.exit_code == 0, root.output


# --- every way of naming nothing is no answer ------------------------------


@pytest.mark.usefixtures("history")
def test_a_revision_git_does_not_know_is_no_answer() -> None:
    result = runner.invoke(app, ["diff", f"git:v2026.Q9:{AUDIT}", AUDIT])

    _reached_no_answer(
        result, f"git knows no revision v2026.Q9 in this repository, so {AUDIT}"
    )
    assert _needle("git fetch --tags") in _unwrapped(result.output)


def test_a_revision_beyond_a_shallow_clone_says_the_clone_is_shallow(
    history: _History, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI checks out one commit by default, and an earlier revision is not in it."""
    shallow = tmp_path / "shallow"
    _git(
        tmp_path,
        "-c",
        "protocol.file.allow=always",
        "clone",
        "--quiet",
        "--depth",
        "1",
        history.root.as_uri(),
        str(shallow),
    )
    monkeypatch.chdir(shallow)

    result = runner.invoke(app, ["diff", f"git:HEAD~1:{AUDIT}", AUDIT])

    _reached_no_answer(
        result, f"git knows no revision HEAD~1 in this repository, so {AUDIT}"
    )
    said = _unwrapped(result.output)
    assert _needle("This clone is shallow") in said
    assert _needle("git fetch --unshallow") in said
    assert _needle("fetch-depth: 0") in said


@pytest.mark.usefixtures("history")
def test_a_refusal_of_the_operand_is_said_on_stderr() -> None:
    """With --json, stdout is a report or nothing, and a refusal is stderr's."""
    result = runner.invoke(app, ["diff", f"git:v2026.Q9:{AUDIT}", AUDIT, "--json"])

    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    assert _needle("git knows no revision v2026.Q9") in _unwrapped(result.stderr)


@pytest.mark.usefixtures("history")
def test_a_revision_git_resolves_only_with_a_warning_is_no_answer() -> None:
    """A date before this clone's reflog begins is answered with another commit.

    ``main@{date}`` reads where ``main`` pointed in this clone, and a date
    before the branch began here is answered with the oldest entry there is,
    and a warning. Hidden, the warning left a reading of a commit nobody asked
    for, reported as the answer. It is quoted instead, and nothing is read.
    """
    revision = "main@{2001-01-01}"

    result = runner.invoke(app, ["diff", f"git:{revision}:{AUDIT}", AUDIT])

    _reached_no_answer(
        result,
        f"git resolved {revision} only with a warning, so {AUDIT} was not read at it",
    )
    said = _unwrapped(result.output)
    assert _needle("this clone's own reflog") in said
    assert _needle("Name a tag or a commit instead") in said


def test_a_path_missing_at_that_revision_is_no_answer(history: _History) -> None:
    """The file is there now and was not then: the revision is what decides."""
    assert (history.root / "term" / "term.audit.json").is_file()

    result = runner.invoke(app, ["diff", "git:v2026.Q2:term/term.audit.json", AUDIT])

    _reached_no_answer(result, "v2026.Q2 holds no file at term/term.audit.json")


def test_a_directory_outside_any_repository_is_no_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The search for a repository stops at the test's own directory."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    after = elsewhere / AUDIT
    after.write_text(json.dumps(_valuation()))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.resolve()))
    monkeypatch.chdir(elsewhere)

    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT])

    _reached_no_answer(result, f"{AUDIT} at v2026.Q2 could not be read")
    assert _needle("git found no repository it can read") in _unwrapped(result.output)


@pytest.mark.parametrize(
    ("held", "said"),
    [
        ("model.py", "could not be read as an artifact document"),
        ("model_points.parquet", "holds bytes rather than text"),
        ("list.json", "holds a JSON array, and an artifact is a JSON object"),
    ],
)
@pytest.mark.usefixtures("history")
def test_a_file_there_that_is_not_an_audit_file_is_no_answer(
    held: str, said: str
) -> None:
    """Held to what a file on disk is held to, and named with its revision."""
    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{held}", AUDIT])

    _reached_no_answer(result, f"{held} at v2026.Q2 {said}")


@pytest.mark.usefixtures("history")
def test_a_pointer_a_revision_committed_says_how_to_fetch_the_file() -> None:
    """The revision keeps the audit file in Git LFS and holds a pointer to it.

    Read as an artifact the pointer is no JSON, which names the wrong problem;
    the refusal says it is a pointer and how to write the file out. A file that
    only begins like a pointer is read as the file it is.
    """
    result = runner.invoke(app, ["diff", "git:v2026.Q2:q2 pointer.audit.json", AUDIT])
    near = runner.invoke(app, ["diff", "git:v2026.Q2:notes.audit.json", AUDIT])

    _reached_no_answer(
        result,
        "q2 pointer.audit.json at v2026.Q2 is a Git LFS pointer, not the file it "
        "stands for: that revision stores the file in Git LFS",
    )
    said = _unwrapped(result.output)
    assert _needle(f"sha256 {_POINTER_OID}, 38826 bytes") in said
    # Quoted, so the command pastes whole into a shell, space and all.
    assert _needle("git show 'v2026.Q2:q2 pointer.audit.json' | git lfs smudge") in (
        said
    )
    _reached_no_answer(
        near, "notes.audit.json at v2026.Q2 could not be read as an artifact document"
    )
    assert "Git LFS" not in near.output


@pytest.mark.usefixtures("history")
def test_a_command_a_refusal_suggests_pastes_whole_into_a_shell() -> None:
    """A path with a space in it is quoted, as a shell needs it to be."""
    result = runner.invoke(app, ["diff", "git:v2026.Q2:audits q2", AUDIT])

    _reached_no_answer(result, "audits q2 at v2026.Q2 is a directory, not a file")
    assert _needle("git ls-tree --name-only 'v2026.Q2:audits q2'") in _unwrapped(
        result.output
    )


def test_an_operand_a_refusal_suggests_pastes_whole_into_a_shell(
    history: _History, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(history.root / "term")

    result = runner.invoke(app, ["diff", "git:HEAD:term notes.audit.json", AUDIT])

    _reached_no_answer(result, "HEAD holds no file at term notes.audit.json")
    assert _needle("as in 'git:HEAD:./term notes.audit.json'") in _unwrapped(
        result.output
    )


@pytest.mark.usefixtures("history")
def test_a_directory_the_revision_holds_is_not_a_file() -> None:
    result = runner.invoke(app, ["diff", "git:v2026.Q2:assumptions", AUDIT])

    _reached_no_answer(result, "assumptions at v2026.Q2 is a directory, not a file")


@pytest.mark.parametrize(
    ("operand", "said"),
    [
        (
            "git:edges:link.audit.json",
            f"link.audit.json at edges is a symbolic link to {AUDIT}, not a file",
        ),
        ("git:edges:sub", "sub at edges is a submodule, not a file"),
        (f"git:v-tree:{AUDIT}", "v-tree names a tree rather than a commit"),
    ],
)
@pytest.mark.usefixtures("history")
def test_what_a_revision_holds_that_is_not_a_file_is_named(
    operand: str, said: str
) -> None:
    """A link, a submodule and a tag of a tree, each called what it is.

    A link had been read as the text of its target, refused as no JSON; a
    submodule as a file git could not hand over; and a tag of a tree as a
    revision git did not know.
    """
    result = runner.invoke(app, ["diff", operand, AUDIT])

    _reached_no_answer(result, said)


@pytest.mark.usefixtures("history")
def test_a_path_inside_a_submodule_names_the_submodule() -> None:
    """A submodule's files are its own repository's, so the submodule is named."""
    result = runner.invoke(app, ["diff", f"git:edges:sub/{AUDIT}", AUDIT])

    _reached_no_answer(
        result, f"sub/{AUDIT} is inside sub, which is a submodule at edges"
    )
    said = _unwrapped(result.output)
    assert _needle("Run the command from inside sub") in said
    # Run from a submodule never checked out, the operand reads the outer
    # repository, which does not hold the submodule's commits.
    assert _needle("git submodule update --init sub checks it out first") in said


@pytest.mark.usefixtures("history")
def test_a_submodule_named_as_a_file_says_how_to_check_it_out() -> None:
    result = runner.invoke(app, ["diff", "git:edges:sub", AUDIT])

    _reached_no_answer(result, "sub at edges is a submodule, not a file")
    assert _needle("git submodule update --init sub checks it out first") in (
        _unwrapped(result.output)
    )


@pytest.mark.parametrize(
    ("operand", "said"),
    [
        ("git:v2026.Q2", "git:v2026.Q2 names the revision v2026.Q2 and no path"),
        (f"git::{AUDIT}", f"git::{AUDIT} names no revision"),
        # Never handed to git, which would read it as one of its own options.
        (f"git:--all:{AUDIT}", "no revision begins with a hyphen"),
    ],
)
@pytest.mark.usefixtures("history")
def test_an_operand_not_written_git_rev_path_says_the_form(
    operand: str, said: str
) -> None:
    result = runner.invoke(app, ["diff", operand, AUDIT])

    _reached_no_answer(result, said)
    assert _needle("Write the operand as git:REV:path") in _unwrapped(result.output)


@pytest.mark.usefixtures("history")
def test_an_operand_that_names_only_a_file_suggests_the_current_commit() -> None:
    """git:model.audit.json reads as a revision named model.audit.json, and no path."""
    result = runner.invoke(app, ["diff", f"git:{AUDIT}", AUDIT])

    _reached_no_answer(result, f"git:{AUDIT} names the revision {AUDIT} and no path")
    assert _needle(f"or git:HEAD:{AUDIT} for the file {AUDIT}") in _unwrapped(
        result.output
    )


@pytest.mark.parametrize(
    ("path", "meant"),
    [("term\\term.audit.json", "term/term.audit.json"), (f".\\{AUDIT}", f"./{AUDIT}")],
)
@pytest.mark.usefixtures("history")
def test_a_path_written_with_backslashes_says_git_writes_slashes(
    path: str, meant: str
) -> None:
    """A Windows path names nothing a revision holds: git writes every path with /."""
    result = runner.invoke(app, ["diff", f"git:HEAD:{path}", AUDIT])

    _reached_no_answer(result, f"HEAD holds no file at {path}")
    said = _unwrapped(result.output)
    assert _needle("git writes the paths it holds with /") in said
    assert _needle(f"write git:HEAD:{meant}") in said


@pytest.mark.usefixtures("history")
def test_git_that_cannot_be_run_is_no_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A machine without git: the operand says so, and what to pass instead."""
    monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))

    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT])

    _reached_no_answer(result, f"{AUDIT} at v2026.Q2 could not be read")
    said = _unwrapped(result.output)
    assert _needle("because git could not be run") in said
    assert _needle("Install git, or give the path of an audit file on disk") in said


# --- reading runs nothing but git, and fetches nothing ---------------------


def test_a_partial_clone_is_read_without_fetching(history: _History) -> None:
    """A file a partial clone left out is not fetched in order to read it.

    Fetching runs the transport the repository configures -- here an ssh
    command that leaves a mark -- and reading a committed file must run none.
    The path is found from the trees, which the clone holds, and the refusal
    says what is true: the revision has the file, this clone does not.
    """
    root = history.root
    mark = root.parent / "fetched"
    blob = _git(root, "rev-parse", f"v2026.Q2:{AUDIT}")
    (root / ".git" / "objects" / blob[:2] / blob[2:]).unlink()
    touch = shlex.quote(f"touch {shlex.quote(str(mark))}; exit 1")
    for key, value in (
        ("core.repositoryformatversion", "1"),
        ("extensions.partialclone", "origin"),
        ("remote.origin.url", "ssh://example.invalid/model.git"),
        ("remote.origin.promisor", "true"),
        ("core.sshCommand", f"sh -c {touch}"),
    ):
        _git(root, "config", key, value)

    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT])

    _reached_no_answer(result, f"{AUDIT} at v2026.Q2 is not in this clone")
    said = _unwrapped(result.output)
    assert _needle("it is a partial clone") in said
    assert _needle(f"git show v2026.Q2:{AUDIT} > file fetches it") in said
    assert not mark.exists(), "reading the operand ran the configured transport"


@pytest.mark.parametrize("variable", ["GIT_DIR", "GIT_WORK_TREE"])
def test_the_environment_does_not_choose_the_repository(
    history: _History, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    """The repository read is the one the current directory sits in.

    A command run from a git hook or a git alias inherits these, and git
    follows them: to another repository's history, or to a work tree the
    current directory is not inside, from which ``../`` means something else.
    """
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _git(elsewhere, "-c", "init.defaultBranch=main", "init")
    pointed = elsewhere / ".git" if variable == "GIT_DIR" else elsewhere
    monkeypatch.setenv(variable, str(pointed))
    monkeypatch.chdir(history.root / "term")

    result = runner.invoke(
        app, ["diff", f"git:v2026.Q2:../{AUDIT}", "git:HEAD:./term.audit.json"]
    )

    assert result.exit_code == 1, result.output
    assert _needle("changed death_claims@1 (self)") in _unwrapped(result.output)


@pytest.mark.parametrize("traced", ["GIT_TRACE", "GIT_TRACE2_PERF", "trace2 config"])
def test_git_tracing_does_not_read_as_a_warning(
    history: _History, monkeypatch: pytest.MonkeyPatch, traced: str
) -> None:
    """Tracing writes to stderr, where the reading looks for git's warnings.

    Turned on in the environment, or for trace2 in the global config, it made
    every revision read as one git resolved only with a warning.
    """
    if traced == "trace2 config":
        config = history.root.parent / "traced.gitconfig"
        config.write_text("[trace2]\n\tnormalTarget = 2\n")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    else:
        monkeypatch.setenv(traced, "1")

    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT])

    assert result.exit_code == 1, result.output
    assert _needle("changed death_claims@1 (self)") in _unwrapped(result.output)


# A server's hook that compares the audit file a push moves, as a team might
# gate merges on it: what the branch held before against what it holds now.
_HOOK = """\
#!/bin/sh
read old new ref
gspio="import sys; sys.argv[0] = 'gspio'; from gaspatchio.cli import app; app()"
"{python}" -c "$gspio" diff "git:$old:model.audit.json" "git:$new:model.audit.json" \\
    > "{record}" 2>&1
echo "exit $?" >> "{record}"
"""


@pytest.mark.parametrize("hook", ["pre-receive", "post-receive"])
def test_a_server_hook_reads_the_commit_a_push_brings(
    history: _History, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hook: str
) -> None:
    """A hook runs with GIT_DIR naming its repository, and objects git adds to it.

    Before a push lands, git holds what it brought in quarantine and hands the
    pre-receive hook GIT_OBJECT_DIRECTORY and GIT_ALTERNATE_OBJECT_DIRECTORIES
    to read it through: they add objects and never refs, and an object's
    content is fixed by its id. After it lands, a bare repository is found
    only through GIT_DIR where safe.bareRepository is explicit. Left out, the
    pushed commit was a revision git did not know in the first, and the
    repository was not found in the second -- while git show read both.
    """
    server = tmp_path / "server.git"
    client = tmp_path / "client"
    _git(tmp_path, "clone", "--quiet", "--bare", str(history.root), str(server))
    _git(tmp_path, "clone", "--quiet", str(server), str(client))
    (client / AUDIT).write_text(json.dumps(_valuation(0.00999), indent=2))
    _commit(client, "the fourth quarter")
    record = tmp_path / "hook.log"
    gate = server / "hooks" / hook
    gate.write_text(_HOOK.format(python=sys.executable, record=record))
    gate.chmod(0o755)
    monkeypatch.setenv("PYTHONPATH", str(Path(gaspatchio.__file__).parents[1]))
    if hook == "post-receive":
        # In a global config, which git hands on to the hooks of a local push
        # as it does not hand on a -c or GIT_CONFIG_COUNT setting.
        explicit = tmp_path / "explicit.gitconfig"
        explicit.write_text("[safe]\n\tbareRepository = explicit\n")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(explicit))

    _git(client, "push", "--quiet", "origin", "main")

    said = record.read_text()
    assert said.endswith("exit 1\n"), said
    assert _needle("changed death_claims@1 (self)") in _unwrapped(said)


# A stand-in for git: a Python script, run through a shell script named git
# that is put first on PATH, so that what git would be handed can be seen.
_UNIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="process groups and an executable shell script named git are POSIX",
)

_RECORDING_GIT = """\
import json, os, sys

with open(os.environ["FAKE_GIT_RECORD"], "a") as record:
    record.write(json.dumps({
        "GIT_TERMINAL_PROMPT": os.environ.get("GIT_TERMINAL_PROMPT"),
        "GIT_NO_LAZY_FETCH": os.environ.get("GIT_NO_LAZY_FETCH"),
        "GIT_ALLOW_PROTOCOL": os.environ.get("GIT_ALLOW_PROTOCOL"),
        "GIT_NO_REPLACE_OBJECTS": os.environ.get("GIT_NO_REPLACE_OBJECTS"),
        "GIT_WORK_TREE": os.environ.get("GIT_WORK_TREE"),
        "GIT_TRACE": os.environ.get("GIT_TRACE"),
        "stdin_is_null": os.path.samestat(os.fstat(0), os.stat(os.devnull)),
        "leads_its_group": os.getpgid(0) == os.getpid(),
    }) + "\\n")
sys.exit(128)
"""

# A shell script that starts a process of its own, as a fetch starts its
# transport, writes down that process's id, and then never answers. Asked for
# its version it answers at once, so the test can run it once first: a script
# run for the first time can be slow to start while the system vets it, and
# this one has to have started its process before it is timed out.
_HANGING_GIT = """\
#!/bin/sh
[ "$1" = "--version" ] && exit 0
sleep 60 >/dev/null 2>&1 &
echo $! > "$FAKE_GIT_CHILD"
exec sleep 60
"""


def _gone(pid: int) -> bool:
    """Return whether process ``pid`` has ended, allowing a moment for reaping.

    A process that has ended but has not been reaped -- a zombie, which is
    what an orphan stays in a container with no init to reap it -- has ended,
    and counts as gone.
    """
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        if _zombie(pid):
            return True
        time.sleep(0.05)
    return False


def _zombie(pid: int) -> bool:
    """Return whether process ``pid`` has ended and waits only to be reaped.

    Read from /proc where there is one, and from ps where there is not.
    """
    with contextlib.suppress(OSError):
        # The state follows the command name, which is in parentheses.
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rpartition(")")[2].split()[0] == "Z"
    with contextlib.suppress(OSError):
        state = subprocess.run(  # noqa: S603 — a fixed argument list, run without a shell
            ["ps", "-o", "stat=", "-p", str(pid)],  # noqa: S607 — resolved on PATH
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return state.strip().startswith("Z")
    return False


def _git_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    """Put a git that is ``script`` first on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git = bin_dir / "git"
    git.write_text(script)
    git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def _python_git(tmp_path: Path, source: str) -> str:
    """Return a shell script that runs ``source`` as git, with this interpreter."""
    script = tmp_path / "git.py"
    script.write_text(source)
    return f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n'


# What git says, word for word, of a repository another user owns.
_DUBIOUS_GIT = """\
#!/bin/sh
echo "fatal: detected dubious ownership in repository at '/srv/models'" >&2
echo "To add an exception for this directory, call:" >&2
echo "" >&2
echo "	git config --global --add safe.directory /srv/models" >&2
exit 128
"""


@_UNIX_ONLY
@pytest.mark.usefixtures("history")
def test_a_repository_another_user_owns_is_said_to_be_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The repository is there; git reads it once it is marked safe, as git says."""
    _git_on_path(tmp_path, monkeypatch, _DUBIOUS_GIT)

    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT])

    _reached_no_answer(result, f"{AUDIT} at v2026.Q2 could not be read")
    said = _unwrapped(result.output)
    assert _needle("another user owns the repository at") in said
    assert _needle("git config --global --add safe.directory /srv/models") in said
    assert _needle("Run the command from inside that repository") not in said


def test_a_bare_repository_git_reads_only_when_named_says_so(
    history: _History, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under safe.bareRepository=explicit, GIT_DIR is what lets git read it."""
    bare = tmp_path / "server.git"
    _git(tmp_path, "clone", "--quiet", "--bare", str(history.root), str(bare))
    explicit = tmp_path / "explicit.gitconfig"
    explicit.write_text("[safe]\n\tbareRepository = explicit\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(explicit))
    monkeypatch.chdir(bare)

    result = runner.invoke(
        app, ["diff", f"git:v2026.Q2:{AUDIT}", str(history.root / AUDIT)]
    )

    _reached_no_answer(result, f"{AUDIT} at v2026.Q2 could not be read")
    said = _unwrapped(result.output)
    assert _needle("git reads a bare repository only when it is named") in said
    assert _needle("with GIT_DIR set to it") in said


@_UNIX_ONLY
@pytest.mark.usefixtures("history")
def test_git_is_asked_with_no_one_to_answer_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No prompt, no stdin, no fetch, no repository but this one, a group of its own.

    A password prompt would wait for an answer nobody gives, and a fetch would
    run a transport; the group is what lets a git that never answers be
    stopped together with what it started.
    """
    record = tmp_path / "record.jsonl"
    monkeypatch.setenv("FAKE_GIT_RECORD", str(record))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("GIT_TRACE", "1")
    _git_on_path(tmp_path, monkeypatch, _python_git(tmp_path, _RECORDING_GIT))

    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT])

    assert result.exit_code == 2, result.output
    asked = json.loads(record.read_text().splitlines()[0])
    assert asked == {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_ALLOW_PROTOCOL": "",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_WORK_TREE": None,
        "GIT_TRACE": None,
        "stdin_is_null": True,
        "leads_its_group": True,
    }


@_UNIX_ONLY
@pytest.mark.usefixtures("history")
def test_a_git_that_does_not_answer_is_stopped_with_what_it_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The timeout stops git's whole process group, not git alone."""
    from gaspatchio import _git_operand

    child = tmp_path / "child.pid"
    monkeypatch.setenv("FAKE_GIT_CHILD", str(child))
    monkeypatch.setattr(_git_operand, "_GIT_TIMEOUT_SECONDS", 3)
    _git_on_path(tmp_path, monkeypatch, _HANGING_GIT)
    subprocess.run(["git", "--version"], check=True)  # noqa: S607 — the stand-in

    result = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT])

    _reached_no_answer(result, f"{AUDIT} at v2026.Q2 could not be read")
    assert _needle("git did not answer within") in _unwrapped(result.output)
    assert child.exists(), "git was timed out before it started its process"
    pid = int(child.read_text())
    try:
        assert _gone(pid), "a process git started outlived the timeout"
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


@_UNIX_ONLY
def test_an_interrupted_read_stops_git_with_what_it_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C reaches the terminal's process group, and git runs in its own.

    So an interrupt that reached only the reading would leave git running,
    with whatever it had started. It is stopped first, and the interrupt goes
    on as an interrupt.
    """
    from gaspatchio._git_operand import _git as ask_git

    child = tmp_path / "child.pid"
    monkeypatch.setenv("FAKE_GIT_CHILD", str(child))
    _git_on_path(tmp_path, monkeypatch, _HANGING_GIT)
    subprocess.run(["git", "--version"], check=True)  # noqa: S607 — the stand-in

    def interrupted(_self: subprocess.Popen[bytes], **_: object) -> None:
        deadline = time.monotonic() + 10
        while not child.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        raise KeyboardInterrupt

    with monkeypatch.context() as patched:
        patched.setattr(subprocess.Popen, "communicate", interrupted)
        with pytest.raises(KeyboardInterrupt):
            ask_git(tmp_path, "x", dict(os.environ), "rev-parse")

    assert child.exists(), "git was interrupted before it started its process"
    pid = int(child.read_text())
    try:
        assert _gone(pid), "a process git started outlived the interrupt"
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


# --- a file on disk whose name begins git: ---------------------------------

_NO_COLONS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="a Windows file name cannot hold a colon, so none can begin git:",
)


@_NO_COLONS
def test_the_operand_reads_the_revision_and_dot_slash_reads_the_file(
    history: _History,
) -> None:
    """What was compared is plain from the command line, whatever sits beside it.

    A file in the working tree is named exactly as the operand is, and holds
    a third audit file. The operand still reads the revision's: a command
    whose meaning turned on which files happened to be there could not be read
    back from a log. ``./`` names the file on disk, as it would for any path.
    """
    on_disk = _valuation(0.00789)
    (history.root / f"git:v2026.Q2:{AUDIT}").write_text(json.dumps(on_disk))

    from_git = runner.invoke(app, ["diff", f"git:v2026.Q2:{AUDIT}", AUDIT, "--json"])
    from_disk = runner.invoke(app, ["diff", f"./git:v2026.Q2:{AUDIT}", AUDIT, "--json"])

    assert from_git.exit_code == 1, from_git.output
    assert (
        json.loads(from_git.stdout) == diff_artifacts(history.q2, history.q3).to_dict()
    )
    assert from_disk.exit_code == 1, from_disk.output
    assert json.loads(from_disk.stdout) == diff_artifacts(on_disk, history.q3).to_dict()


@_NO_COLONS
def test_a_refusal_beside_a_file_of_that_name_says_how_to_name_the_file(
    history: _History,
) -> None:
    """Where the operand names nothing, the file it may have meant is named."""
    operand = f"git:v2026.Q9:{AUDIT}"
    (history.root / operand).write_text(json.dumps(_valuation()))

    result = runner.invoke(app, ["diff", operand, AUDIT])

    _reached_no_answer(result, "git knows no revision v2026.Q9")
    assert _needle(f"write ./{operand} to compare that file instead") in (
        _unwrapped(result.output)
    )


@pytest.mark.usefixtures("history")
def test_a_name_too_long_to_be_a_file_is_no_answer() -> None:
    """A name longer than the file system allows is a refusal, not a traceback.

    Whether a file of the operand's own name sits beside it is asked of the
    file system, which answers a name that long with an error rather than no.
    """
    operand = f"git:v2026.Q9:{'a' * 300}.audit.json"

    result = runner.invoke(app, ["diff", operand, AUDIT])

    _reached_no_answer(result, "git knows no revision v2026.Q9")


# --- the help and the module's own examples --------------------------------


def test_the_help_names_the_operand_and_gives_an_example() -> None:
    result = runner.invoke(app, ["diff", "--help"], env={"COLUMNS": "200"})

    assert result.exit_code == 0, result.output
    said = _unwrapped(result.output)
    assert _needle("git:REV:path") in said
    assert _needle(f"gspio diff git:v2026.Q2:{AUDIT} {AUDIT}") in said


def test_the_documented_examples_run() -> None:
    """Every example in the module is executed, not merely displayed."""
    from gaspatchio import _git_operand

    found = [
        test for test in doctest.DocTestFinder().find(_git_operand) if test.examples
    ]
    assert len(found) >= 3, "the module's examples were not found"
    report = io.StringIO()
    doctest_runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for test in found:
        doctest_runner.run(test, out=report.write)

    assert doctest_runner.failures == 0, report.getvalue()
