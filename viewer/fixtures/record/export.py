# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Export ``viewer/fixtures/record.json`` from the model and the files beside this one.

The one committed viewer fixture whose record names what the model rests on
beside its own file, which is what the page's Model tab and Table header are
tested at: ``model.py`` imports ``loadings.py`` beside it (``model.modules``),
reads ``mortality.csv`` through a recipe that renames its ``Age`` column
(``source_file`` with a non-empty ``shaped_by``), reads ``lapse.csv`` as it
stands (a plain read), and builds a third table from a frame written in its
code (``source_file`` null). Its rates are divided by twelve, so the values it
samples run to every digit a double holds -- what the page is held to quote
when a reader selects a cell and copies it. Run from ``bindings/python`` with
the core's venv, which is where the producer lives::

    .venv/bin/python ../../viewer/fixtures/record/export.py

**Where it is exported.** The files are copied to a directory outside any
repository and ``gspio calc-graph`` runs there, so the document states no git
revision and every path in it is written against the model's own directory,
as section 7 of the specification asks where no revision is stated. The
results file is written beside the model in that directory and not kept: the
record names it by path and digest, and ``tests/graph/test_viewer_fixtures.py``
exports this model again and holds every sampled value in the committed
document to the results file that export writes.

**How it is stamped.** The library versions are withheld (``--no-versions``):
they name one machine's build, and a committed document must not move with
it. The producer stamp is the version of the core that ran, and this script
refuses to export unless that is this tree's own version, as
``bindings/python/pyproject.toml`` states it -- the rule every other committed
document's stamp was taken under.

The export is read back before it is kept: it must validate, and it must carry
the members this fixture exists for.
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
FIXTURE = HERE.parent / "record.json"
PYPROJECT = HERE.parents[2] / "bindings" / "python" / "pyproject.toml"

# What the model and its points are called, in the directory it runs in and
# in the document it writes.
MODEL = "model.py"
POINTS = "model_points.csv"
RESULTS = "results.parquet"
BESIDE = ("loadings.py", "mortality.csv", "lapse.csv")


def export(destination: Path) -> None:
    """Run ``gspio calc-graph`` over the model, outside any repository.

    A process of its own, because the model registers three tables as it
    runs, and a registration made inside the caller would outlive the export.
    """
    with tempfile.TemporaryDirectory() as scratch:
        for name in (MODEL, POINTS, *BESIDE):
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
                "--results",
                RESULTS,
                "--no-versions",
            ],
            cwd=scratch,
            check=True,
            capture_output=True,
        )


def _what_it_is_for(document: dict) -> list[str]:
    """Return each member this fixture exists for that the export does not carry."""
    missing = []
    if [module["path"] for module in document["model"].get("modules", [])] != [
        "loadings.py"
    ]:
        missing.append("model.modules naming loadings.py")
    tables = {entry["name"]: entry for entry in document["assumptions"]}
    if tables.get("record_mortality", {}).get("shaped_by") in (None, []):
        missing.append("record_mortality with a shaped_by")
    if tables.get("record_lapse", {}).get("source_file") != "lapse.csv":
        missing.append("record_lapse read from lapse.csv")
    if "source_file" not in tables.get("record_expense", {"source_file": 0}) or (
        tables["record_expense"]["source_file"] is not None
    ):
        missing.append("record_expense built from a frame")
    if document["producer"].get("versions") != {"omitted": "withheld"}:
        missing.append("producer.versions withheld")
    return missing


def main() -> None:
    """Export the fixture, stamped with this tree's version, and read it back."""
    from gaspatchio.frame.graph import validate_artifact  # noqa: PLC0415

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
    missing = _what_it_is_for(document)
    if missing:
        msg = f"{FIXTURE.name} carries no {', '.join(missing)}"
        raise SystemExit(msg)
    stamp = document["producer"]["version"]
    print(f"{FIXTURE.name}: producer {stamp}")  # noqa: T201


if __name__ == "__main__":
    main()
