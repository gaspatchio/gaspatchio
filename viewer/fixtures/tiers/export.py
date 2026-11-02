# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Export ``viewer/fixtures/tiers.json`` from the model and the points beside this file.

The one committed viewer fixture with a calculation at each of the three
tiers, which is what the page's tier census is tested at: ``model.py`` writes
five lines in the framework's own terms, two in Polars' own expression
language and one through an operation nothing has classified, over the three
policies of ``model_points.csv``. Run from ``bindings/python`` with the core's
venv, which is where the producer lives::

    .venv/bin/python ../../viewer/fixtures/tiers/export.py

**Where it is exported.** The two files are copied to a directory outside
any repository and ``gspio calc-graph`` runs there, so the document states no
git revision and every path in it is written against the model's own
directory, as section 7 of the specification asks where no revision is
stated: a revision of this repository would name a commit that a squash
removes.

**How it is stamped.** The library versions are withheld (``--no-versions``):
they name one machine's build, and a committed document must not move with
it. The producer stamp is the version of the core that
ran, and this script refuses to export unless that is this tree's own
version, as ``bindings/python/pyproject.toml`` states it: the stamp is never
a number typed here, and never an older install's -- the rule every other
committed document's stamp was taken under. A checkout whose core is
installed from it satisfies it as it stands.

The export is read back before it is kept: it must validate, and its census
must be the three tiers this fixture exists for. After it, write the census
the page is held to again, ``python -m tests.graph.test_tier_census`` from
``bindings/python``; ``tests/graph/test_tier_census.py`` holds the committed
document to an export of this model, whole but for when it was written and
its seal.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "tiers.json"
PYPROJECT = HERE.parents[2] / "bindings" / "python" / "pyproject.toml"

# What the model and its points are called, in the directory it runs in and
# in the document it writes.
MODEL = "model.py"
POINTS = "model_points.csv"


def export(destination: Path) -> None:
    """Run ``gspio calc-graph`` over the model, outside any repository.

    A process of its own, because the model registers an operation as it is
    read, and a registration made inside the caller would outlive the export.
    """
    with tempfile.TemporaryDirectory() as scratch:
        for name in (MODEL, POINTS):
            shutil.copyfile(HERE / name, Path(scratch) / name)
        subprocess.run(  # noqa: S603 -- this interpreter, this package's own command
            [
                sys.executable,
                "-m",
                "gaspatchio.cli",
                "calc-graph",
                MODEL,
                POINTS,
                "--artifact",
                str(destination),
                "--no-versions",
            ],
            cwd=scratch,
            check=True,
            capture_output=True,
        )


def main() -> None:
    """Export the fixture, stamped with this tree's version, and read it back."""
    from gaspatchio.frame.graph import validate_artifact  # noqa: PLC0415
    from gaspatchio.frame.graph.tiers import _census_of_document  # noqa: PLC0415

    tree = tomllib.loads(PYPROJECT.read_text("utf-8"))["project"]["version"]
    installed = version("gaspatchio")
    if installed != tree:
        msg = (
            f"The installed core is {installed} and this tree is {tree}, so the "
            "document would be stamped with a version that did not write it. "
            "Install this tree's core, then export the fixture again."
        )
        raise SystemExit(msg)
    export(FIXTURE)
    document = json.loads(FIXTURE.read_text("utf-8"))
    if not validate_artifact(document).ok:
        msg = f"{FIXTURE.name} does not validate; it was not meant to be edited"
        raise SystemExit(msg)
    counts = _census_of_document(document["nodes"]).counts
    stamp = document["producer"]["version"]
    print(f"{FIXTURE.name}: producer {stamp}, census {counts}")  # noqa: T201


if __name__ == "__main__":
    main()
