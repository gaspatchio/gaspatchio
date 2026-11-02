# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: No file that ships names a private issue id (gsp and a number, any case).
# ABOUTME: Reads the package and tutorials, skills, spec, the JAX engine, the viewer.
"""No file that ships names an issue in the private tracker.

``GSP-`` and a number is an issue in a tracker no reader of the package can
open. 1.0.0's tutorials ended "Reference: ... (GSP-89 / PR #111)", the
docstring checker cited GSP-152 to GSP-154 for why it reads ruff the way it
does, and four scenario modules opened on GSP-101: each sends a reader
nowhere at the place the reason is wanted. The same id turned up lower case
too -- a stress report printed the branch ``gsp-92-...`` and the sketch cited a
scratch script under ``gsp101_...`` -- so the match ignores case and takes the
hyphen or not. The reason is written out in words instead; a public reference
-- ``gh#128``, ``PR #111`` -- may stay, because anyone can follow it.

**What is read.** Every tracked file, whole, under what ships: the Python
package (``bindings/python/gaspatchio``, its tutorials and docstring examples
included), ``skills``, ``spec``, ``engines/jax/src`` and ``viewer/python``.
A file that is not UTF-8 text is a binary and is skipped, and a ``base64,``
payload inside a text file -- the fonts ``viewer/build.mjs`` inlines into
``fonts.css`` -- is bytes rather than text and is not read: its alphabet spells
``GSP79`` by chance.

**Generated files.** ``viewer/python``'s bundle is built from ``viewer/src``
by ``viewer/build.mjs`` and ``gaspatchio/column/_generated_proxy.py`` by
``scripts/generate_proxy_surface.py``. They are read, because they ship, and a
match in one is fixed in its source and regenerated, never edited by hand.

The tests, the ``ref/`` records and the changelog's history are not read: they
do not ship. A line that matches and is not a citation is allowed by name in
``_NOT_A_CITATION``, with the reason; an allowance whose line has gone fails
``test_every_allowed_line_still_matches`` and is removed, not kept in case.
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
from pathlib import Path
from typing import Final

import pytest

REPO: Final = Path(__file__).resolve().parents[3]
GIT: Final = shutil.which("git")
pytestmark = pytest.mark.skipif(
    not (REPO / ".git").exists() or GIT is None, reason="requires checkout"
)

# The tracker's id in any case, with its hyphen or without: GSP-101, gsp-92,
# gsp101. No word boundary in front, so ``test_smoke_gsp92`` is caught too.
_PRIVATE_ISSUE: Final = re.compile(r"gsp-?[0-9]+", re.IGNORECASE)
# A data URI's payload: bytes written in base64's alphabet, never text.
_BASE64_PAYLOAD: Final = re.compile(r"base64,[A-Za-z0-9+/=]+")

# A file and one of its lines, stripped, that matches and cites nothing.
_NOT_A_CITATION: Final[dict[tuple[str, str], str]] = {
    (
        "bindings/python/gaspatchio/scenarios/_for_each.py",
        'payload = f"gsp-100|{master_seed}|{scenario_id}".encode()',
    ): (
        "The salt every scenario's seed is derived from. It is data, not a "
        "citation: changing it would change every derived seed, and with them "
        "every stochastic scenario's numbers."
    ),
}
_SHIPPED: Final = (
    "bindings/python/gaspatchio",
    "skills",
    "spec",
    "engines/jax/src",
    "viewer/python",
)


@functools.cache
def _shipped_files() -> tuple[str, ...]:
    """Return every tracked file under what ships, repository-relative."""
    listed = subprocess.run(  # noqa: S603 -- git's own path and a fixed command
        [str(GIT), "ls-files", "-z", "--", *_SHIPPED],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return tuple(sorted(path for path in listed.split("\0") if path))


def _text(path: str) -> str | None:
    """Return a file's text, or None where it is not UTF-8 text."""
    try:
        return (REPO / path).read_text("utf-8")
    except UnicodeDecodeError:
        return None


@functools.cache
def _all_hits() -> tuple[tuple[str, int, str, str], ...]:
    """Return (path, line number, match, stripped line) for every match that ships."""
    return tuple(
        (path, number, match.group(), line.strip())
        for path in _shipped_files()
        if (text := _text(path)) is not None and _PRIVATE_ISSUE.search(text)
        for number, line in enumerate(text.splitlines(), start=1)
        for match in _PRIVATE_ISSUE.finditer(_BASE64_PAYLOAD.sub("base64,", line))
    )


def test_no_shipped_file_names_a_private_issue() -> None:
    found = [
        f"{path}:{number}: {token}"
        for path, number, token, line in _all_hits()
        if (path, line) not in _NOT_A_CITATION
    ]

    assert found == [], (
        "A file that ships names an issue in the private tracker, which no "
        "reader of the package can open. Write what it stands for in words; a "
        "public reference (gh#N, PR #N) may stay. In a generated file, fix the "
        "source and regenerate:\n  " + "\n  ".join(found)
    )


def test_every_allowed_line_still_matches() -> None:
    """An allowance whose line has gone is removed, not kept in case."""
    matched = {(path, line) for path, _, _, line in _all_hits()}

    assert set(_NOT_A_CITATION) <= matched, set(_NOT_A_CITATION) - matched


def test_the_scan_reads_every_shipped_tree() -> None:
    files = _shipped_files()

    assert len(files) > 500, "the scan found almost nothing to read"
    for tree in _SHIPPED:
        assert any(path.startswith(f"{tree}/") for path in files), tree
    assert {
        "bindings/python/gaspatchio/scenarios/_for_each.py",
        "bindings/python/gaspatchio/examples/docstrings/models.py",
        "bindings/python/gaspatchio/tutorials/patterns/aggregate-at-scale/README.md",
        "skills/gaspatchio-model-building/SKILL.md",
        "viewer/python/gaspatchio_viewer/assets/viewer.js",
        "viewer/python/gaspatchio_viewer/assets/fonts.css",
    } <= set(files)
