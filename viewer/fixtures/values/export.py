# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Export the values vector: two versions of one model, their results, and the report.

``before.py`` and ``after.py`` are one model a fee rate apart, run over
``before.csv`` and over ``after.csv`` -- a book in which one policy's premium was
revised, one policy left and one joined. Each version is exported with ``gspio
calc-graph --results``, and ``gspio diff``'s report over the two, values read
from the two results files, is written beside them. That is the vector both
readings are held to:

- ``tests/graph/test_diff_values.py`` computes the report again from the
  committed documents and results files and requires it to be the committed
  report, byte for byte;
- ``viewer/test/compare.test.ts`` derives the page's own comparison from the two
  committed documents and requires its reading of the one policy they carry to
  be the report's ``values.declared``, line for line.

``values-movement.json`` is the same ``values`` member as ``gspio diff --html``
carries it into a page, compact, which ``pack.mjs --movement`` packs for the
end-to-end tests.

Run from ``bindings/python`` with the core's venv, which is where the producer
lives::

    .venv/bin/python ../../viewer/fixtures/values/export.py

**Where it is exported.** Each version runs in a directory of its own outside
any repository, as ``model.py`` over ``model_points.csv``, so the two documents
name one model file and every path in them is written against the model's own
directory. **How it is stamped.** The library versions are withheld
(``--no-versions``), as every committed document's are. The producer stamp is
the version of the core that ran, and this script refuses to export unless that
is this tree's own version, as ``bindings/python/pyproject.toml`` states it --
the rule the tiers and record fixtures' exporters keep. Without it the two
documents were once stamped 0.9.0 from a venv whose installed metadata lagged
the tree.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from importlib.metadata import version as installed_version
from pathlib import Path

from gaspatchio.frame.graph import diff_with_results

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent
PYPROJECT = HERE.parents[2] / "bindings" / "python" / "pyproject.toml"

# The two versions, as the vector names them: the model file, the book, and
# where the document, the results file and the report are kept.
VERSIONS = ("before", "after")
REPORT = FIXTURES / "values-report.json"
# The report's values member as ``gspio diff --html`` carries it into a page:
# compact JSON, which ``pack.mjs --movement values-movement`` packs.
MOVEMENT = FIXTURES / "values-movement.json"


def document(version: str) -> Path:
    """Return where one version's committed document is kept."""
    return FIXTURES / f"values-{version}.json"


def results(version: str) -> Path:
    """Return where one version's committed results file is kept."""
    return HERE / f"{version}.parquet"


def export(version: str) -> None:
    """Run ``gspio calc-graph`` over one version, outside any repository."""
    with tempfile.TemporaryDirectory() as scratch:
        where = Path(scratch)
        shutil.copyfile(HERE / f"{version}.py", where / "model.py")
        shutil.copyfile(HERE / f"{version}.csv", where / "model_points.csv")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "gaspatchio.cli",
                "calc-graph",
                "model.py",
                "model_points.csv",
                "--artifact",
                "model.audit.json",
                "--results",
                "results.parquet",
                "--no-versions",
            ],
            cwd=where,
            check=True,
            capture_output=True,
        )
        written = json.loads((where / "model.audit.json").read_text("utf-8"))
        document(version).write_text(json.dumps(written, indent=2) + "\n", "utf-8")
        shutil.copyfile(where / "results.parquet", results(version))


def report() -> dict[str, object]:
    """Return ``gspio diff``'s report over the committed vector, values read.

    The two results files are named relative to this directory, so the paths
    the report records are the same wherever the repository is checked out.
    """
    before, after = (
        json.loads(document(version).read_text("utf-8")) for version in VERSIONS
    )
    here = Path.cwd()
    os.chdir(HERE)
    try:
        written = diff_with_results(
            before, after, Path("before.parquet"), Path("after.parquet")
        )
    finally:
        os.chdir(here)
    return written.to_dict()


def main() -> None:
    """Export both versions, then write the report over them, and its page block."""
    tree = tomllib.loads(PYPROJECT.read_text("utf-8"))["project"]["version"]
    installed = installed_version("gaspatchio")
    if installed != tree:
        msg = (
            f"The installed core is {installed} and this tree is {tree}, so the "
            "documents would be stamped with a version that did not write them. "
            "Install this tree's core, then export the vector again."
        )
        raise SystemExit(msg)
    for version in VERSIONS:
        export(version)
    written = report()
    REPORT.write_text(json.dumps(written, indent=2) + "\n", "utf-8")
    MOVEMENT.write_text(
        json.dumps(written["values"], separators=(",", ":")) + "\n", "utf-8"
    )


if __name__ == "__main__":
    main()
