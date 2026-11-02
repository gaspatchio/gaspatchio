# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: The git:REV:path operand: an audit file as a past revision committed it.
# ABOUTME: Read with git, without a checkout; each way it fails is a plain sentence.
"""An audit file as a revision committed it, named on a command line ``git:REV:path``.

A team that commits the audit file beside the model -- written by CI on merge,
say -- already holds every quarter's audit file in the repository's history.
``gspio diff git:v2026.Q2:model.audit.json model.audit.json`` reads the earlier
one straight out of it: no checkout, and no second run of the model.

**The operand means what it says.** ``git:`` begins it, the revision runs to the
next colon outside braces -- where git itself splits ``REV:path`` -- and the path
is the rest. The revision is looked up in the repository the current directory
sits in. The path is read from that repository's root, as ``git show REV:path``
reads it, and a path that begins ``./`` or ``../`` is read from the current
directory instead. That is git's own rule, so the operand names the file the
same words name to git, and a reviewer can check what was read with ``git show``.
From a subdirectory, a plain path that also names a file there -- at the
revision or on disk -- is refused rather than read from the root, because the
person typing it may mean the one beside them; the refusal gives the ``./``
and ``../`` spellings that name each.

**A file on disk whose name begins** ``git:`` **is not consulted.** What a
comparison read has to be plain from the command line that asked for it, not
from whichever files sat beside it that day. ``./git:...`` names such a file.

**The bytes are the blob the revision holds**, as ``git cat-file blob`` hands
them over and ``git show`` prints them, with no filter run over them. Replace
refs are not followed: a blob swapped for another reads as the one committed,
and a revision reached across a graft (``git replace --graft``) goes through
the commit's recorded parents.

**Reading runs git and nothing else.** Nothing is fetched -- a file a partial
clone left out is reported as left out, with the ``git show`` that fetches
it -- so no transport, helper or command a repository configures is run;
nobody is asked for a password; and a git that does not answer is stopped
with whatever it started. The repository is the current directory's, even
where the environment names another, as a git hook's does.

**Running an old revision's model is not what this does.** A model that imports
sibling modules and reads data files needs its whole tree, which ``git worktree
add`` gives it. This reads a file the revision already holds.

Each way the operand can fail to name a file is refused with a plain sentence
naming the revision, the path and the next move:

- an operand missing either part, or naming a revision that begins with a
  hyphen;
- git that cannot be run, or does not answer;
- a directory outside any repository;
- a revision git does not know -- saying so where the clone is shallow --
  resolves only with a warning, or names a tree rather than a commit;
- a path the revision holds no file at, or that runs into a submodule;
- a directory, a submodule or a symbolic link where a file was named;
- a file a partial clone left out.

Whether the file it does hold is an audit file is the command's question,
answered as it is for a file on disk.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

__all__ = [
    "GIT_OPERAND",
    "CommittedFile",
    "CommittedFileError",
    "is_git_operand",
    "read_committed",
    "split_operand",
]

GIT_OPERAND: Final[str] = "git:"
"""What an operand begins with when it names a file as a revision committed it."""

# How long git is given to answer one question before the reading decides it
# cannot.
_GIT_TIMEOUT_SECONDS: Final[int] = 10

# The two starts git reads a path from the current directory by, rather than
# from the repository's root.
_FROM_HERE: Final[tuple[str, str]] = ("./", "../")

# The variables that tell git where a repository's work tree, shared files and
# index are. A command run from a git hook or a git alias inherits them, and git
# would follow them elsewhere than the repository the current directory sits in,
# which is the one the operand names. GIT_DIR is kept where it names that very
# repository -- see _environment -- and the two variables that add objects to
# it are kept always: a hook's quarantine reaches its pushed objects through
# GIT_OBJECT_DIRECTORY and GIT_ALTERNATE_OBJECT_DIRECTORIES, they add objects
# and never refs, and an object's content is fixed by its id.
_ELSEWHERE: Final[frozenset[str]] = frozenset(
    {"GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"}
)

# The variable that names the repository outright.
_GIT_DIR: Final[str] = "GIT_DIR"

# What every question is asked under. Reading a file a revision holds fetches
# nothing, so it runs no transport a repository configures: GIT_NO_LAZY_FETCH
# stops git 2.44 and later fetching an object a partial clone left out, and an
# empty GIT_ALLOW_PROTOCOL leaves an older git no transport to fetch it with.
# It reads the objects the revision committed: GIT_NO_REPLACE_OBJECTS turns off
# replace refs, which swap one object for another -- a file's bytes, or through
# a graft a commit's parents -- in everything git reads. It asks nobody for a
# password. And it writes no trace: the reading takes anything on git's stderr
# for a warning, so the GIT_TRACE* variables are left out and the trace2 ones,
# which a global config can also turn on, are turned off.
_UNATTENDED: Final[dict[str, str]] = {
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_ALLOW_PROTOCOL": "",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_TRACE2": "0",
    "GIT_TRACE2_PERF": "0",
    "GIT_TRACE2_EVENT": "0",
}

# What every variable that turns on one of git's traces begins with.
_TRACE: Final[str] = "GIT_TRACE"

# The modes a tree entry is written with, for each thing a revision can hold
# at a path. Only the mode tells a symbolic link from a file: both are blobs.
_FILE: Final[str] = "100644"
_SYMLINK: Final[str] = "120000"
_SUBMODULE: Final[str] = "160000"
_DIRECTORY: Final[str] = "040000"


class CommittedFileError(ValueError):
    """A ``git:REV:path`` operand that names no file this can read.

    The message is the whole answer: it names the revision and the path, says
    what is wrong, and says what to do next.
    """


@dataclass(frozen=True, slots=True)
class CommittedFile:
    """One file as one revision committed it.

    Attributes:
        revision: The revision, as the operand wrote it.
        path: The path, as the operand wrote it.
        data: The file's bytes, as the revision holds them.

    """

    revision: str
    path: str
    data: bytes

    @property
    def named(self) -> str:
        """Return the path and the revision, as a sentence about the file names it."""
        return f"{self.path} at {self.revision}"

    @property
    def name(self) -> str:
        """Return the file's own name and the revision, as a report heads it."""
        return f"{PurePosixPath(self.path).name} at {self.revision}"

    @property
    def stem(self) -> str:
        """Return the file's name less its suffix, and the revision."""
        return f"{PurePosixPath(self.path).stem} at {self.revision}"

    @property
    def show(self) -> str:
        """Return the git show that prints this file, quoted for a shell."""
        return f"git show {_at(self.revision, self.path)}"


def _operand(revision: str, path: str) -> str:
    """Return the operand git:REV:path, quoted as a shell needs it to be.

    Every operand and command a refusal suggests is quoted, so that one with a
    space in it pastes into a shell whole.
    """
    return shlex.quote(f"{GIT_OPERAND}{revision}:{path}")


def _at(revision: str, path: str) -> str:
    """Return REV:path, the object git show names, quoted as a shell needs it."""
    return shlex.quote(f"{revision}:{path}")


def is_git_operand(operand: str) -> bool:
    """Return whether ``operand`` names a file a revision committed.

    It is decided by what the operand says and nothing else: one that begins
    ``git:`` is read from the repository whether or not a file of that name
    sits in the current directory, and ``./git:...`` names that file.

    Examples:
        >>> is_git_operand("git:v2026.Q2:model.audit.json")
        True
        >>> is_git_operand("./git:v2026.Q2:model.audit.json")
        False

    """
    return operand.startswith(GIT_OPERAND)


def split_operand(operand: str) -> tuple[str, str]:
    """Return the revision and the path a ``git:REV:path`` operand names.

    The revision runs to the first colon outside braces, which is where git
    splits ``REV:path`` itself, so ``v2026.Q2^{/fix: rounding}`` -- the newest
    commit the tag reaches whose message matches ``fix: rounding`` -- is one
    revision. The path is everything after that colon, colons and all.

    A revision that begins with a hyphen is refused here: no branch or tag
    name may begin with one, and git would read it as one of its own options
    rather than as a revision.

    Args:
        operand: The operand as the command line gave it, ``git:`` and all.

    Returns:
        The revision and the path.

    Raises:
        CommittedFileError: If the operand names no revision, or no path, or
            a revision that begins with a hyphen.

    Examples:
        >>> split_operand("git:v2026.Q2:model.audit.json")
        ('v2026.Q2', 'model.audit.json')
        >>> split_operand("git:v2026.Q2^{/fix: rounding}:audit/model.audit.json")
        ('v2026.Q2^{/fix: rounding}', 'audit/model.audit.json')

    """
    spec = operand.removeprefix(GIT_OPERAND)
    depth = 0
    end = len(spec)
    for at, character in enumerate(spec):
        if character == "{":
            depth += 1
        elif character == "}" and depth:
            depth -= 1
        elif character == ":" and not depth:
            end = at
            break
    revision, path = spec[:end], spec[end + 1 :]
    if not revision:
        msg = (
            f"{operand} names no revision. Write the operand as git:REV:path, "
            "for example git:v2026.Q2:model.audit.json."
        )
        raise CommittedFileError(msg)
    if revision.startswith("-"):
        msg = (
            f"{operand} names {revision} as its revision, and no revision begins "
            "with a hyphen. Write the operand as git:REV:path, for example "
            f"{_operand('v2026.Q2', path or 'model.audit.json')}."
        )
        raise CommittedFileError(msg)
    if not path:
        # git:model.audit.json is the likeliest way to get here: a file named,
        # and no revision, so the file's name is read as the revision.
        msg = (
            f"{operand} names the revision {revision} and no path. Write the "
            f"operand as git:REV:path: {_operand(revision, 'model.audit.json')} for "
            f"a file at {revision}, or {_operand('HEAD', revision)} for the file "
            f"{revision} as the current commit holds it."
        )
        raise CommittedFileError(msg)
    return revision, path


def read_committed(operand: str, directory: Path) -> CommittedFile:
    """Return the file a ``git:REV:path`` operand names, as the revision holds it.

    git is run in ``directory``, so the revision is looked up in the repository
    ``directory`` sits in, and a path that begins ``./`` starts there. On a
    command line that is the current directory.

    Args:
        operand: The operand, ``git:`` and all.
        directory: The directory whose repository the file is read from.

    Returns:
        The file, with the revision and the path it was named by.

    Raises:
        CommittedFileError: If the operand names no file git can hand over.
            The message names the revision and the path and says what to do
            next. Where a file of the operand's own name sits in
            ``directory``, it also says how to compare that file instead.

    Examples:
        An operand naming no path is refused before git is asked anything:

        >>> from pathlib import Path
        >>> try:
        ...     read_committed("git:v2026.Q2", Path.cwd())
        ... except CommittedFileError as refused:
        ...     print(refused)  # doctest: +ELLIPSIS
        git:v2026.Q2 names the revision v2026.Q2 and no path. Write the operand...

    """
    try:
        return _read(operand, directory)
    except CommittedFileError as refused:
        # os.path, which answers False for a name too long to be a file, where
        # Path.is_file raises.
        if not os.path.isfile(directory / operand):  # noqa: PTH113
            raise
        msg = (
            f"{refused} A file named {operand} sits in this directory too, and an "
            f"operand that begins git: is read from the repository: write "
            f"{shlex.quote(f'./{operand}')} to compare that file instead."
        )
        raise CommittedFileError(msg) from None


@dataclass(frozen=True, slots=True)
class _Reading:
    """One operand being read: the directory it is read in, and what it names.

    Every question about the operand is asked of git through :meth:`ask`, so
    each is asked the same way, and every refusal can name the revision and
    the path.
    """

    directory: Path
    revision: str
    path: str
    environment: dict[str, str]

    @property
    def named(self) -> str:
        """Return the path and the revision, as a refusal names them."""
        return f"{self.path} at {self.revision}"

    def ask(self, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        """Return what git answers ``arguments`` with, in the operand's directory."""
        return _git(self.directory, self.named, self.environment, *arguments)

    def resolve(self, name: str) -> str | None:
        """Return the object id ``name`` resolves to, or None where it resolves none."""
        found = self.ask("rev-parse", "--verify", "--quiet", name)
        return found.stdout.decode().strip() if found.returncode == 0 else None


def _read(operand: str, directory: Path) -> CommittedFile:
    """Return the file ``operand`` names, asking git one question at a time.

    Each question is the one that tells a reader which part of the operand to
    fix: whether there is a repository here, whether the revision is in it,
    and what the revision holds at the path, if anything.
    """
    revision, path = split_operand(operand)
    named = f"{path} at {revision}"
    reading = _Reading(directory, revision, path, _environment(directory, named))
    prefix = _prefix(reading)
    commit = _commit_of(reading)

    # The path is resolved from the trees alone, which even a partial clone
    # holds, so finding out whether the file is there fetches nothing.
    entry = _entry(reading, commit, path)
    if entry is None:
        raise CommittedFileError(_no_file_at(reading, commit, prefix))
    if prefix and not path.startswith(_FROM_HERE):
        _refuse_two_files(reading, commit, prefix)
    _refuse_what_is_not_a_file(reading, entry)

    held = reading.ask("cat-file", "blob", entry.oid)
    if held.returncode == 0:
        return CommittedFile(revision=revision, path=path, data=held.stdout)
    raise CommittedFileError(_not_held(reading, held))


@dataclass(frozen=True, slots=True)
class _Entry:
    """What a revision's tree holds at a path: its mode, and the object it names."""

    mode: str
    oid: str


def _entry(reading: _Reading, commit: str, path: str) -> _Entry | None:
    """Return what ``commit``'s tree holds at ``path``, or None where it holds nothing.

    git resolves the path, so it is found as ``git show`` finds it -- from the
    root, or from the current directory after ``./`` -- and from the trees
    alone. The mode is read off the listing of the directory that holds the
    entry, because a symbolic link and a file are both blobs and only the mode
    tells them apart.
    """
    oid = reading.resolve(f"{commit}:{path}")
    if oid is None:
        return None
    head, _, leaf = path.rstrip("/").rpartition("/")
    if leaf in {"", ".", ".."}:
        # The path names a directory itself, as ./ and ../ do.
        return _Entry(_DIRECTORY, oid)
    if head in {".", ".."}:
        # git reads ./ and ../ from the current directory, and . as a name.
        head += "/"
    listing = reading.ask("ls-tree", "-z", "--full-tree", f"{commit}:{head}")
    entries = [_listed(line) for line in listing.stdout.split(b"\0") if b"\t" in line]
    by_name = [mode for mode, _, name in entries if name == os.fsencode(leaf)]
    if len(by_name) == 1:
        return _Entry(by_name[0], oid)
    # A name the listing spells otherwise -- composed and decomposed accents,
    # say -- is found by the object git resolved it to instead.
    by_oid = {mode for mode, listed, _ in entries if listed == oid}
    return _Entry(by_oid.pop() if len(by_oid) == 1 else _FILE, oid)


def _listed(line: bytes) -> tuple[str, str, bytes]:
    """Return the mode, object and name of one ``ls-tree -z`` line."""
    meta, _, name = line.partition(b"\t")
    mode, _, rest = meta.decode().partition(" ")
    _, _, oid = rest.partition(" ")
    return mode, oid, name


def _refuse_what_is_not_a_file(reading: _Reading, entry: _Entry) -> None:
    """Refuse a path at which the revision holds something other than a file.

    A directory, a submodule and a symbolic link each get the sentence that
    says what they are and what to name instead. Read as text, a link is the
    path it points to, and a submodule is a commit of another repository.
    """
    named, revision, path = reading.named, reading.revision, reading.path
    if entry.mode == _DIRECTORY:
        msg = (
            f"{named} is a directory, not a file: name the audit file inside it. "
            f"git ls-tree --name-only {_at(revision, path)} lists what it holds."
        )
    elif entry.mode == _SUBMODULE:
        msg = (
            f"{named} is a submodule, not a file: its files are in the "
            f"submodule's own repository, at the commit {entry.oid[:12]} that "
            f"{revision} records. Run the command from inside {path}, where "
            f"git:{entry.oid[:12]}:PATH reads a file at that commit"
            f"{_checked_out_first(path)}"
        )
    elif entry.mode == _SYMLINK:
        target = reading.ask("cat-file", "blob", entry.oid)
        points = target.stdout.decode(errors="replace")
        to = f" to {points}" if target.returncode == 0 and points else ""
        msg = (
            f"{named} is a symbolic link{to}, not a file: git holds the link, not "
            "the file it points to. Name the file it points to instead."
        )
    else:
        return
    raise CommittedFileError(msg)


def _checked_out_first(submodule: str) -> str:
    """Return the clause that ends a submodule's sentence: how to check it out.

    A submodule that was never checked out is an empty directory of the outer
    repository, and an operand read from there reads the outer repository,
    which does not hold the submodule's commits.
    """
    return (
        f"; if {submodule} is not checked out, git submodule update --init "
        f"{shlex.quote(submodule)} checks it out first."
    )


def _submodule_above(reading: _Reading, commit: str) -> tuple[str, str] | None:
    """Return the submodule the operand's path runs into, and its commit, if any.

    git does not look inside a submodule, so a path through one names nothing
    in this repository, and the submodule is what the refusal should name.
    """
    parts = reading.path.split("/")
    for depth in range(1, len(parts)):
        above = "/".join(parts[:depth])
        if not above.strip("./"):
            continue
        entry = _entry(reading, commit, above)
        if entry is None:
            return None
        if entry.mode == _SUBMODULE:
            return above, entry.oid
        if entry.mode != _DIRECTORY:
            return None
    return None


def _prefix(reading: _Reading) -> str:
    """Return where the operand's directory sits in its repository, or refuse.

    ``models/term/`` from that directory of a checkout, and the empty string at
    its top or in a bare repository. Outside any repository there is nothing
    to read the revision from, and that is the refusal.
    """
    found = reading.ask("rev-parse", "--git-dir", "--show-prefix")
    if found.returncode != 0:
        raise CommittedFileError(_no_repository(reading, found))
    answers = found.stdout.decode(errors="replace").splitlines()
    return answers[1] if len(answers) > 1 else ""


def _no_repository(reading: _Reading, found: subprocess.CompletedProcess[bytes]) -> str:
    """Return the sentence for a directory git will not read a repository from.

    Two of git's safety settings refuse a repository that is there, and each
    gets its own sentence, picked by the setting git names -- a config key,
    which git never translates. Otherwise there is no repository here.
    """
    named, directory, said = reading.named, reading.directory, _git_said(found)
    if b"safe.directory" in found.stderr:
        return (
            f"{named} could not be read: another user owns the repository at "
            f"{directory}, so git will not read it until it is marked safe, with "
            f"the command git gives.{said}"
        )
    if b"safe.bareRepository" in found.stderr:
        return (
            f"{named} could not be read: the repository at {directory} is bare, "
            "and git reads a bare repository only when it is named "
            "(safe.bareRepository is explicit). Run the command with GIT_DIR set "
            f"to it.{said}"
        )
    return (
        f"{named} could not be read: git found no repository it can read at "
        f"{directory}, and the revision is looked up in the repository the "
        f"current directory sits in. Run the command from inside that repository."
        f"{said}"
    )


def _commit_of(reading: _Reading) -> str:
    """Return the commit the revision names, or refuse where it names none plainly.

    Resolved to its commit once, so that every question after this one is
    asked of one commit even if a branch moves while they are asked.

    Asked without ``--quiet``, because git answers some revisions with a
    warning and a commit that is not the one asked for. ``main@{2026-07-01}``
    is read from this clone's own reflog, and a date before that reflog
    begins is answered with its oldest entry; a name that is both a branch
    and a tag is answered with one of them. The warning is the only sign, so
    a warning is a refusal, in git's own words.
    """
    revision, path = reading.revision, reading.path
    resolved = reading.ask("rev-parse", "--verify", f"{revision}^{{commit}}")
    peeled = None if resolved.returncode == 0 else reading.resolve(f"{revision}^{{}}")
    if peeled is not None:
        kind = reading.ask("cat-file", "-t", peeled).stdout.decode().strip()
        msg = (
            f"{revision} names a {kind or 'object'} rather than a commit, so "
            f"{path} could not be read at it: a git: operand reads a file as a "
            "commit holds it. Name a commit, or a tag of one; git log lists the "
            "commits."
        )
        raise CommittedFileError(msg)
    if resolved.returncode != 0:
        msg = (
            f"git knows no revision {revision} in this repository, so {path} "
            "could not be read at it. git tag and git log list the revisions it "
            "holds, and a tag made in another clone arrives with git fetch --tags."
        )
        # CI checks a repository out shallow unless told otherwise, and a
        # shallow clone holds only the latest commits.
        shallow = reading.ask("rev-parse", "--is-shallow-repository")
        if shallow.stdout.strip() == b"true":
            msg += (
                " This clone is shallow, so it holds only the latest history: git "
                "fetch --unshallow fetches the rest, and in CI a checkout with "
                "fetch-depth: 0 makes a full clone."
            )
        raise CommittedFileError(msg)
    if not resolved.stderr.strip():
        return resolved.stdout.decode().strip()
    msg = f"git resolved {revision} only with a warning, so {path} was not read at it."
    if "@{" in revision:
        msg += (
            " A revision written with @{...} is read from this clone's own reflog "
            "-- where its branches pointed in this clone, and when -- which begins "
            "when the clone was made, not with the repository's history. Name a "
            "tag or a commit instead: git log -1 --until=DATE BRANCH gives the "
            "last commit made before a date."
        )
    else:
        msg += (
            f" Name the revision so that git reads it without one: refs/tags/"
            f"{revision} for a tag, refs/heads/{revision} for a branch."
        )
    msg += _git_said(resolved)
    raise CommittedFileError(msg)


def _no_file_at(reading: _Reading, commit: str, prefix: str) -> str:
    """Return the sentence for a path the revision holds no file at.

    It says which directory the path was read from, because that is the usual
    reason: a path written from a subdirectory, read from the repository's
    root. Where that is what happened, it gives the operand that reads the
    path from the current directory instead, as git's own hint does.

    A partial clone may have left out the directories that would say whether
    the file is there, and this reading does not fetch them, so there the
    sentence claims only what the clone can tell.
    """
    revision, path = reading.revision, reading.path
    inside = _submodule_above(reading, commit)
    if inside is not None:
        submodule, oid = inside
        rest = path[len(submodule) :].lstrip("/")
        return (
            f"{path} is inside {submodule}, which is a submodule at {revision}: "
            "its files are in the submodule's own repository, at the commit "
            f"{oid[:12]} that {revision} records. Run the command from inside "
            f"{submodule}, as {_operand(oid[:12], rest)}"
            f"{_checked_out_first(submodule)}"
        )
    if _partial(reading):
        return (
            f"{reading.named} could not be found in this clone, which is partial: "
            "the revision may hold no file there, or this clone may have left out "
            "the directories that would say. This reading never fetches; git show "
            f"{_at(revision, path)} > file fetches it if it is there, and that file "
            "can be compared."
        )
    if "\\" in path:
        slashed = path.replace("\\", "/")
        return (
            f"{revision} holds no file at {path}, and git writes the paths it holds "
            f"with /, not \\: write {_operand(revision, slashed)}."
        )
    if path.startswith(_FROM_HERE):
        return (
            f"{revision} holds no file at {path}, read from the current directory. "
            f"git ls-tree -r --name-only {shlex.quote(revision)} lists the files it "
            "holds here."
        )
    said = (
        f"{revision} holds no file at {path}. The path is read from the "
        "repository's root, as git show reads it, and git ls-tree -r --name-only "
        f"--full-tree {shlex.quote(revision)} lists every file that revision holds."
    )
    if not prefix:
        return said
    return (
        f"{said} To read the path from the current directory, {prefix}, begin it "
        f"with ./, as in {_operand(revision, f'./{path}')}."
    )


def _refuse_two_files(reading: _Reading, commit: str, prefix: str) -> None:
    """Refuse a path that names one file to git and another to the reader.

    From a subdirectory git reads a plain path from the repository's root, so
    ``git:REV:model.audit.json`` run in ``models/term`` reads the root's audit
    file -- another model's -- wherever the root has one. Where the current
    directory holds a file of that name too, at the revision or on disk, the
    operand does not say which is meant, so it is refused with the spelling
    that reads each.
    """
    revision, path = reading.revision, reading.path
    beside = _entry(reading, commit, f"./{path}")
    at_revision = beside is not None and beside.mode != _DIRECTORY
    # os.path, which answers False for a name too long to be a file, where
    # Path.is_file raises.
    on_disk = os.path.isfile(reading.directory / path)  # noqa: PTH113
    if not at_revision and not on_disk:
        return
    up = "../" * prefix.count("/")
    root = f"{_operand(revision, f'{up}{path}')} for {path} at the root"
    if at_revision:
        there = f"is at {revision} too"
        each = f"{_operand(revision, f'./{path}')} for {prefix}{path}, or {root}"
    else:
        # The revision has no file beside the reader to offer, so the spelling
        # that reads the one on disk is the file's own path.
        there = f"is on disk here, though not at {revision}"
        each = f"{root}, or {shlex.quote(path)} on its own for the file on disk"
    msg = (
        f"From {prefix}, git:{revision}:{path} could name two files: git reads it "
        f"as {path} at the repository's root, and {prefix}{path} {there}. Write "
        f"{each}."
    )
    raise CommittedFileError(msg)


def _not_held(reading: _Reading, held: subprocess.CompletedProcess[bytes]) -> str:
    """Return the sentence for a file the revision holds that git did not hand over.

    In a partial clone that is the usual reason, and a true one: the revision
    has the file, and this clone left its contents out to fetch when asked.
    This reading never asks, so the sentence names the command that does.
    """
    if _partial(reading):
        return (
            f"{reading.named} is not in this clone: it is a partial clone, which "
            "fetches a file's contents only when they are asked for, and this "
            f"reading never fetches. git show {_at(reading.revision, reading.path)} "
            "> file fetches it; then compare that file."
        )
    return f"{reading.named} could not be read.{_git_said(held)}"


def _partial(reading: _Reading) -> bool:
    """Return whether this clone is partial: one that leaves objects out to fetch.

    ``git clone --filter`` writes ``extensions.partialClone``; a remote set up
    by hand to supply what is missing is marked ``promisor``. Either way git
    would fetch a missing object rather than say it is missing.
    """
    clone = reading.ask("config", "--get", "extensions.partialclone")
    if clone.returncode == 0 and clone.stdout.strip():
        return True
    promisors = reading.ask(
        "config", "--bool", "--get-regexp", r"^remote\..*\.promisor$"
    )
    return any(line.endswith(b" true") for line in promisors.stdout.splitlines())


def _environment(directory: Path, named: str) -> dict[str, str]:
    """Return the environment every question about one operand is asked in.

    The process's own, under :data:`_UNATTENDED`, less every trace variable and
    the variables in :data:`_ELSEWHERE`. GIT_DIR stays where it names the
    repository ``directory`` sits in, as a git hook's does: there it is how
    git finds a bare repository that safe.bareRepository lets git use only
    when named. Where it names another repository it is left out, so the
    repository read is the current directory's, as the help says.
    """
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in _ELSEWHERE and name != _GIT_DIR and not name.startswith(_TRACE)
    }
    environment.update(_UNATTENDED)
    git_dir = os.environ.get(_GIT_DIR)
    if git_dir is None:
        return environment
    kept = {**environment, _GIT_DIR: git_dir}
    named_dir = _git(directory, named, kept, "rev-parse", "--absolute-git-dir")
    if named_dir.returncode != 0:
        return environment
    found = _git(directory, named, environment, "rev-parse", "--absolute-git-dir")
    if found.returncode == 0:
        this_repository = found.stdout.strip() == named_dir.stdout.strip()
    else:
        # Not found unnamed, as safe.bareRepository=explicit has it: GIT_DIR
        # names this repository where it names the directory itself, which is
        # where a bare repository's hooks run.
        try:
            this_repository = Path(named_dir.stdout.decode().strip()).samefile(
                directory
            )
        except OSError:
            this_repository = False
    return kept if this_repository else environment


def _git(
    directory: Path, named: str, environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[bytes]:
    """Return what git answered in ``directory``, or refuse where it could not be run.

    git is resolved on PATH rather than at an absolute path, as the revision a
    model sits at is: the repository is the user's, read by the user's own git.

    It is asked in ``environment``, which :func:`_environment` makes, with
    stdin empty, and in a process group of its own, so that a git that does
    not answer, or a reading that is interrupted, stops git together with
    whatever it started.
    """
    command = ["git", "-C", str(directory), *arguments]
    try:
        with subprocess.Popen(  # noqa: S603 — a fixed argument list, run without a shell
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            start_new_session=True,
        ) as running:
            try:
                out, err = running.communicate(timeout=_GIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                _stop(running)
                msg = (
                    f"{named} could not be read: git did not answer within "
                    f"{_GIT_TIMEOUT_SECONDS} seconds, and was stopped. Write the "
                    "file out with git show and give its path instead."
                )
                raise CommittedFileError(msg) from None
            except KeyboardInterrupt:
                # A terminal's Ctrl-C reaches its own process group, and git
                # runs in a session of its own, so git is stopped here before
                # the interrupt goes on.
                _stop(running)
                raise
    except OSError as error:
        msg = (
            f"{named} could not be read, because git could not be run: {error}. "
            "Install git, or give the path of an audit file on disk instead."
        )
        raise CommittedFileError(msg) from error
    return subprocess.CompletedProcess(command, running.returncode, out, err)


def _stop(running: subprocess.Popen[bytes]) -> None:
    """Stop git and every process it started, which share its process group.

    Stopping git alone would leave a transport or a helper it started running
    on, as an orphan. Windows has no process groups to stop, so there git
    alone is stopped.
    """
    if sys.platform == "win32":
        running.kill()
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(running.pid, signal.SIGKILL)


def _git_said(answer: subprocess.CompletedProcess[bytes]) -> str:
    """Return what git wrote to stderr, as a clause to end a sentence with."""
    said = answer.stderr.decode(errors="replace").strip()
    return f" git said: {said}" if said else ""
