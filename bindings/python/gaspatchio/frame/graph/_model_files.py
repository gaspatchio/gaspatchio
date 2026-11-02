# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What the files a run was given say about themselves, taken one way.

An audit file names the model source it is an account of, the policy data the
model was run over and the results it wrote, and it names each one twice:
where the file sits, and what its bytes hash to. It also says which revision
the model was at, and it writes every path against one root -- the checkout
the model sits in, or the model file's own directory.

This module is where all of that is taken, so every digest of a file the
block names is taken by one function: when the block is written, and again
when a reviewer holds a file against it. Two such digests can then only
differ because the file did.

**A revision that is not recorded says why.** ``git: null`` has one meaning:
git ran beside the model and found no working tree. Every other way git can
fail to answer -- no git on ``PATH``, a refusal such as git's "dubious
ownership" of a shared drive, an answer that never came -- is section 6.1's
``unavailable`` form, carrying git's own first line or what happened, so a
reviewer can tell "not under revision control" from "git could not be read"
a quarter later.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING, Any, Final

from gaspatchio._identity import SHA256_PREFIX
from gaspatchio.util import read_model_points

from .graph_utils import relative_to_root

if TYPE_CHECKING:
    import polars as pl

__all__ = [
    "GitRefusal",
    "Revision",
    "book_from_file",
    "file_sha",
    "git_asked",
    "git_output",
    "revision_notice",
    "revision_of",
    "stamped_file",
]

# How much of a file is hashed at a time when stamping its content identity.
_SHA_READ_BLOCK: Final[int] = 1 << 20

# How long git is given to answer before the run decides it cannot.
_GIT_TIMEOUT_SECONDS: Final[int] = 10

# What git says, in its untranslated messages, where the directory it was run
# in is in no working tree. Read in the C locale (see ``git_asked``), so the
# one refusal that means "not under revision control" is told from the rest
# whatever language the user's own git speaks.
_NOT_A_REPOSITORY: Final[str] = "not a git repository"

# Section 6.1's reason, and the member carrying git's sentence beside it.
_UNAVAILABLE: Final[str] = "unavailable"
_DETAIL: Final[str] = "detail"

# The paths git names in its first line, quoted -- "dubious ownership in
# repository at '/Volumes/share/models'" -- or bare -- "could not lock config
# file /home/<name>/.gitconfig: Permission denied", or a Windows drive path.
# Each is rewritten before it is recorded, because no path in a document is
# absolute (section 7). A bare one starts the line or follows a space, an
# opening bracket or an equals sign, starts at ``/`` or at a drive, and runs to
# the space, or the punctuation before one, that ends the word.
_QUOTED: Final[re.Pattern[str]] = re.compile(r"'([^']+)'")
_BARE: Final[re.Pattern[str]] = re.compile(
    r"""(?:^|(?<=[\s(=]))((?:/|[A-Za-z]:[\\/])[^\s'"]+?)(?=[.:,;]?(?:\s|$)|[)'"])"""
)

# What stands for a path no relative spelling can name without naming the
# machine: one whose only directory in common with the model's is the root of
# the filesystem, or that sits on another drive. A climb of ``..`` to the root
# and back down is an absolute path spelled relatively, and would carry a home
# directory into the document as surely as the absolute one.
_ELSEWHERE: Final[str] = "<a path outside the model's directory>"


def file_sha(path: Path) -> str | None:
    """Return ``sha256:<hex>`` over a file's own bytes, or None if it cannot be read.

    The file's bytes, not a re-serialisation of what was parsed out of them:
    a digest over a re-write moves whenever the library that writes the format
    changes, and an identity that moves on a dependency upgrade is an identity
    nobody can compare across quarters.
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(_SHA_READ_BLOCK), b""):
                digest.update(block)
    except OSError:
        return None
    return f"{SHA256_PREFIX}{digest.hexdigest()}"


@dataclass(frozen=True, slots=True)
class GitRefusal:
    """Why git gave no answer beside a model, in one sentence.

    Attributes:
        detail: git's own first line where it ran and refused, or what
            happened where it did not run or did not finish -- "no git
            executable on PATH", "git did not answer within 10 s".
        outside_a_repository: Whether the refusal was git saying the
            directory is in no working tree, the one refusal that is an
            answer: the model is not under revision control.

    """

    detail: str
    outside_a_repository: bool


def git_asked(directory: Path, *arguments: str) -> str | GitRefusal:
    """Return what git says in ``directory``, or why it said nothing.

    git is resolved on PATH rather than at an absolute path: the revision a
    model sits at is the one the user's own git reports, whichever git that
    is. It runs in the C locale, so its messages are git's own untranslated
    words: the refusal saying the directory is in no repository is told from
    the rest by them, and a recorded detail reads the same on every machine.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — a fixed argument list, run without a shell
            ["git", "-C", str(directory), *arguments],  # noqa: S607 — resolved on PATH
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            env={**os.environ, "LC_ALL": "C"},
        )
    except FileNotFoundError:
        return GitRefusal("no git executable on PATH", outside_a_repository=False)
    except subprocess.TimeoutExpired:
        return GitRefusal(
            f"git did not answer within {_GIT_TIMEOUT_SECONDS} s",
            outside_a_repository=False,
        )
    except (OSError, subprocess.SubprocessError) as failed:
        reason = getattr(failed, "strerror", None) or type(failed).__name__
        return GitRefusal(f"git could not be run: {reason}", outside_a_repository=False)
    if completed.returncode != 0:
        said = [line.strip() for line in completed.stderr.splitlines() if line.strip()]
        first = said[0] if said else f"git exited with status {completed.returncode}"
        return GitRefusal(
            first, outside_a_repository=_NOT_A_REPOSITORY in completed.stderr.lower()
        )
    return completed.stdout.strip()


def git_output(directory: Path, *arguments: str) -> str | None:
    """Return what git says in ``directory``, or None where it cannot answer."""
    answer = git_asked(directory, *arguments)
    return None if isinstance(answer, GitRefusal) else answer


def stamped_file(path: Path | None, root: Path) -> dict[str, str] | None:
    """Return ``{path, fingerprint}`` for a file, or None where it has none.

    The one shape the version block uses for a data file it names, written
    once so that the policy data and the results the run wrote are stamped
    the same way. The fingerprint is :func:`file_sha` -- the content stamp
    over the file's own bytes -- because a reader comparing two quarters
    needs the two digests to have been taken the same way.

    The path is written against ``root`` and the fingerprint is taken over
    the bytes at ``path``: one is where the file sits in a tree anybody can
    hold, the other is what is in it, and neither answer moves because the
    other did.
    """
    if path is None:
        return None
    stamp = file_sha(path)
    if stamp is None:
        return None
    return {"path": relative_to_root(path, root), "fingerprint": stamp}


@dataclass(frozen=True, slots=True)
class Revision:
    """The revision a model file sits at, and the root its paths are written to.

    The two are decided in one breath because the second follows the first:
    the root is the repository the model sits in where the block states a
    revision, and the model file's own directory where it does not. Asking
    git separately for each is what would let the two disagree -- an envelope
    naming a commit while its paths were written against some directory
    inside that checkout, which no reader could resolve.

    Attributes:
        git: ``{"commit", "dirty"}``; None where git found no working tree
            beside the model; or section 6.1's ``{"omitted": "unavailable",
            "detail": ...}`` where git could not answer, saying why.
        root: The directory every path in the document is written against.

    """

    git: dict[str, Any] | None
    root: Path


def revision_of(model_file: Path) -> Revision:
    """Return the revision ``model_file`` sits at, and the root decided with it.

    The repository the model sits in where there is one, and the model file's
    own directory otherwise -- the two bases the format defines, and a reader
    holding the artifact and the model file knows which applied because the
    envelope's ``git`` block says so.

    The repository is preferred where it exists because it is the wider of
    the two: a model that reads its assumptions from a sibling directory of
    the same checkout writes those paths without leaving the root, and the
    artifact then resolves for anybody who has cloned it.

    ``dirty`` describes the whole working tree, not the model file alone. It
    is ``git status --porcelain`` run beside the model, so anything
    uncommitted anywhere in that checkout makes it true -- the conservative
    reading, and the only one a reader should take from it. It is true as
    well where the commit does not hold the model file at all -- untracked,
    or in an ignored directory, which git counts as no change -- because the
    commit then does not hold the model as it ran.

    A revision is stated only where git answers all three questions -- the
    commit, the state of the tree and where the checkout's top is -- so a
    block naming a commit always has its paths written against that commit's
    checkout.

    **Where it is not stated, the block says why.** None says git found no
    working tree beside the model. Any other failure -- no git on ``PATH``,
    git refusing the directory, a repository with no commit yet, an answer
    that did not come in time -- is the ``unavailable`` form with git's first
    line, or what happened, as its ``detail``; every absolute path git names
    in it, quoted or bare, is written against the model's directory, as every
    path in the document is, or as a placeholder where no relative spelling
    avoids naming the machine.

    Args:
        model_file: The model source, resolved.

    Returns:
        The revision, the reason there is none, or none, and the root that
        goes with it.

    """
    directory = model_file.parent
    toplevel = git_asked(directory, "rev-parse", "--show-toplevel")
    if isinstance(toplevel, GitRefusal) and toplevel.outside_a_repository:
        return Revision(git=None, root=directory)
    commit = git_asked(directory, "rev-parse", "HEAD")
    status = git_asked(directory, "status", "--porcelain")
    for answer in (toplevel, commit, status):
        if isinstance(answer, GitRefusal):
            return Revision(git=_unavailable(answer, directory), root=directory)
    if (
        not isinstance(commit, str)
        or not isinstance(status, str)
        or not isinstance(toplevel, str)
        or not toplevel
    ):
        refused = GitRefusal(
            "git named no top level for the working tree", outside_a_repository=False
        )
        return Revision(git=_unavailable(refused, directory), root=directory)
    # Whether the commit holds the model file itself: an ignored file is no
    # change to the tree, so status alone would call such a checkout clean.
    held = git_output(
        directory, "ls-tree", "--name-only", "HEAD", "--", model_file.name
    )
    return Revision(
        git={"commit": commit, "dirty": bool(status) or not held},
        root=Path(toplevel).resolve(),
    )


def _unavailable(refusal: GitRefusal, directory: Path) -> dict[str, str]:
    """Return section 6.1's form for a revision git could not state, saying why.

    Every absolute path git names, quoted or bare, is written against the
    model's directory, the root the document's other paths are written
    against where no revision is stated -- or, where it shares nothing with
    that directory but the root of the filesystem, as a placeholder -- so the
    sentence names no directory of the machine that wrote it.
    """

    def quoted(found: re.Match[str]) -> str:
        spelled = _without_the_machine(found.group(1), directory)
        return found.group(0) if spelled is None else f"'{spelled}'"

    def bare(found: re.Match[str]) -> str:
        spelled = _without_the_machine(found.group(1), directory)
        return found.group(0) if spelled is None else spelled

    said = _BARE.sub(bare, _QUOTED.sub(quoted, refusal.detail))
    return {"omitted": _UNAVAILABLE, _DETAIL: said}


def _without_the_machine(named: str, directory: Path) -> str | None:
    """Return an absolute path as the document may write it, or None if not absolute.

    Relative to ``directory`` where the two share a directory below the
    filesystem's root -- ``..`` for the repository a shared drive's model sits
    in, ``../.gitconfig`` beside it -- and :data:`_ELSEWHERE` otherwise: a path
    on another drive, or one whose only climb from the model reaches the root.
    """
    windows = PureWindowsPath(named)
    if windows.drive and windows.is_absolute() and not Path(named).is_absolute():
        # A drive path read on a machine whose paths have no drives: there is
        # no climb from the model's directory to it at all.
        return _ELSEWHERE
    path = Path(named)
    if not path.is_absolute():
        return None
    shared = 0
    for own, theirs in zip(path.parts, directory.parts, strict=False):
        if own != theirs:
            break
        shared += 1
    if shared <= 1:
        return _ELSEWHERE
    return relative_to_root(path, directory)


def revision_notice(model: Mapping[str, Any] | None) -> str | None:
    """Return the one line an export says where it records no revision, or None.

    Read off the document's own ``model`` block, so the line says what the
    file says: that the model file is in no git working tree, or that git
    could not answer beside it, and why. None where a revision is recorded,
    or where the block names no model file, since then there was nothing to
    ask git about.
    """
    if not isinstance(model, Mapping):
        return None
    named = model.get("source_path")
    if not isinstance(named, str) or "git" not in model:
        return None
    file = Path(named).name
    git = model["git"]
    if git is None:
        return f"model.git not recorded: {file} is not in a git working tree"
    if isinstance(git, Mapping) and git.get("omitted") == _UNAVAILABLE:
        said = git.get(_DETAIL)
        why = said if isinstance(said, str) and said else "no reason was given"
        return f"model.git not recorded: git could not answer beside {file}: {why}"
    return None


def book_from_file(path: Path) -> pl.DataFrame:
    """Return the policy data a model points file holds, read as every command reads it.

    Through ``read_model_points``, the reader ``gspio run-model`` uses, so a
    run, an export and a verification of one file hold one book. The book's
    digest is taken over the frame the model was handed, and a CSV read with
    another reader's type inference is other data: a column empty for its
    first rows reads as text to a reader that looks at a hundred rows and as
    numbers to one that looks at ten thousand, and the two digest apart.

    Args:
        path: The model points file, ``.parquet`` or ``.csv``.

    Returns:
        The policy data.

    Raises:
        ValueError: If the file is neither Parquet nor CSV by its suffix.

    """
    return read_model_points(path).collect()
