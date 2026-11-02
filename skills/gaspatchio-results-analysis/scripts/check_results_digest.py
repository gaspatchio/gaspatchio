# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: INP001 - standalone utilities inside a skill payload, not a
# package. The skill directory is copied verbatim into an editor's plugin
# cache, where an __init__.py would claim a package that nothing imports.

"""Check that a results file is the one its artifact was written against.

``model.results`` names the output file the run wrote, by path and by content
hash. The path is relative to the model's root -- the directory the model file
sits in, or the root of the repository it sits in where the envelope carries a
``git`` block -- and the hash is SHA-256 over the file's own bytes.

So the two can part company. A later run overwrites the Parquet and leaves the
artifact behind; a file is copied without its artifact; two quarters end up in
one directory. Each of those produces a chart drawn from one run and labelled
with another's identity, and nothing on the chart says so.

This is the check that refuses. A mismatch exits non-zero: it is a stop, not a
warning, and no number should be quoted from a file that failed it.

Run it::

    bindings/python/.venv/bin/python check_results_digest.py graph.json
    bindings/python/.venv/bin/python check_results_digest.py graph.json \
        --root path/to/model/root

Exit status: 0 the file matches, 1 the digests differ, 2 there is nothing to
check -- the artifact names no results file, or the file it names is not there.

Import it::

    from check_results_digest import check, file_digest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Sequence

MATCHED = 0
"""Exit status: the file on disk is the one the artifact was written against."""

DIFFERED = 1
"""Exit status: the file is there and it is a different file."""

UNCHECKABLE = 2
"""Exit status: nothing to compare -- no ``results`` block, or no such file."""

READ_BLOCK = 1 << 20
"""Bytes per read, so a hundred-megabyte results file is not held in memory."""

SHA256_PREFIX = "sha256:"
"""The prefix every content stamp in the artifact is written with."""


@dataclass(frozen=True, slots=True)
class Outcome:
    """What the comparison found.

    Attributes:
        status: The exit status, one of ``MATCHED``, ``DIFFERED``,
            ``UNCHECKABLE``.
        message: One sentence in the framework's voice saying what was found
            and what to do about it.
        stated: The digest the artifact states, or None where it states none.
        found: The digest of the file on disk, or None where there is no file.
        path: The results file the artifact names, resolved against the root,
            or None where the artifact names none.

    """

    status: int
    message: str
    stated: str | None = None
    found: str | None = None
    path: Path | None = None


def read_artifact(path: Path) -> dict[str, Any]:
    """Return the artifact document at ``path``.

    Args:
        path: The JSON file ``gspio calc-graph -o`` wrote.

    Returns:
        The parsed document.

    Raises:
        TypeError: If the file does not hold a JSON object.

    """
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        message = f"{path} does not hold a calculation-graph artifact"
        raise TypeError(message)
    return document


def file_digest(path: Path) -> str:
    """Return ``sha256:<hex>`` over a file's own bytes.

    The bytes as written, not a re-serialisation of what was parsed out of
    them: a digest over a re-write moves whenever the library that writes the
    format changes, and an identity that moves on a dependency upgrade is an
    identity nobody can compare across quarters.

    Args:
        path: The file to hash.

    Returns:
        The content stamp, in the artifact's own form.

    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(READ_BLOCK), b""):
            digest.update(block)
    return f"{SHA256_PREFIX}{digest.hexdigest()}"


def check(document: dict[str, Any], root: Path) -> Outcome:
    """Compare the results file on disk with the digest the artifact states.

    Args:
        document: A parsed artifact.
        root: The model's root, which every path in the artifact is written
            relative to.

    Returns:
        What was found, with both digests where both exist.

    """
    results = (document.get("model") or {}).get("results")
    if not results:
        return Outcome(
            status=UNCHECKABLE,
            message=(
                "this artifact names no results file, so there is nothing to "
                "check; re-export with `gspio calc-graph model.py "
                "points.parquet --output-file results.parquet` to have the "
                "run's output named and stamped"
            ),
        )
    path = root / results["path"]
    stated = results.get("fingerprint")
    if not path.is_file():
        return Outcome(
            status=UNCHECKABLE,
            message=(
                f"the artifact names {results['path']} as its results file and "
                f"it is not at {path}; pass --root with the directory the "
                f"model file sits in"
            ),
            stated=stated,
            path=path,
        )
    found = file_digest(path)
    if found != stated:
        return Outcome(
            status=DIFFERED,
            message=(
                f"{path} is not the file this artifact was written against: it "
                f"states {stated} and the file is {found}. Quote no number "
                f"from it -- re-export the artifact beside this results file, "
                f"or find the results file this artifact names"
            ),
            stated=stated,
            found=found,
            path=path,
        )
    return Outcome(
        status=MATCHED,
        message=f"{path} is the file this artifact was written against: {found}",
        stated=stated,
        found=found,
        path=path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Check an artifact's results file and say what was found.

    Args:
        argv: Command-line arguments, the program name excluded.

    Returns:
        The process exit status: 0 matched, 1 differed, 2 nothing to check.

    """
    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description=(
            "Check that the results Parquet an artifact names is the file it "
            "was written against. A mismatch is a stop, not a warning."
        ),
        epilog="exit status: 0 matched, 1 differed, 2 nothing to check",
    )
    parser.add_argument("artifact", type=Path, help="the artifact JSON to read")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help=(
            "the model's root, which every path in the artifact is relative "
            "to: the directory the model file sits in, or the repository root "
            "where the artifact carries a git block (default: the artifact's "
            "own directory)"
        ),
    )
    args = parser.parse_args(argv)

    if args.root is None:
        logger.warning(
            "no --root given, so the artifact's own directory is read as the "
            "model's root: {root}",
            root=args.artifact.parent,
        )
    root = args.root if args.root is not None else args.artifact.parent
    outcome = check(read_artifact(args.artifact), root)
    sys.stdout.write(f"{outcome.message}\n")
    return outcome.status


if __name__ == "__main__":
    raise SystemExit(main())
