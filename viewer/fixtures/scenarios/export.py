# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Export ``viewer/fixtures/scenarios.json`` and its run's own record from level 5.

The viewer's scenario fixture is the level-5 tutorial's base model run
through its own plan: ``gspio calc-graph model.py model_points.parquet
--scenarios run_scenarios.py --policies :3``, which writes two records of one
run -- the calculation-graph document, and the run's own record beside it,
``scenarios.run.audit.json``, which the document names in ``model.audit``.
Both are written again here from the model as the tutorial ships it today, so
the fixture describes today's level-5 model rather than the one it was first
exported from. Run from ``bindings/python`` with the core's venv, which is
where the producer lives::

    .venv/bin/python ../../viewer/fixtures/scenarios/export.py

**Where it is exported.** The tutorial's ``base`` directory and an empty
``viewer/fixtures`` are laid out in a scratch directory outside any
repository, at the depths they sit at here, and ``calc-graph`` runs in the
model's directory there. So the document states no git revision, every path
in it is written against the model's own directory as section 7 asks where
no revision is stated, and ``model.audit.path`` reaches the run's record
where it is committed -- ``../../../../../../viewer/fixtures/`` from the
tutorial's model.

**How it is stamped.** ``--no-versions`` withholds the library versions in
both records: in the document's ``producer.versions`` and under each version
key of the run's ``run_metadata``. They name one machine's build, and a
committed document must not move with it. The producer stamp is the version
of the core that ran, and this script refuses to export unless that is this
tree's own version, as ``bindings/python/pyproject.toml`` states it.

The two are read back before they are kept: the document must validate, must
name the record by the digest of its bytes, and neither may carry a version
string. What the run's record also says about the run -- its wall time and
what each batch size it tried cost -- is a measurement of the run and is
kept, as every scenario record keeps it.

After it, write the census the page is held to again, ``python -m
tests.graph.test_tier_census`` from ``bindings/python``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from importlib.metadata import version
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent
ROOT = HERE.parents[2]
PYPROJECT = ROOT / "bindings" / "python" / "pyproject.toml"
TUTORIAL = Path("bindings/python/gaspatchio/tutorials/level-5-scenarios/base")
DOCUMENT = "scenarios.json"
RECORD = "scenarios.run.audit.json"
# The record the export used to be written beside, under the name the
# scenario door gave a run's record before it was renamed.
SUPERSEDED = "scenarios.audit.json"
WITHHELD = {"omitted": "withheld"}
VERSION_KEYS = (
    "core_version",
    "extension_version",
    "extension_sha256",
    "polars_version",
    "python_version",
    "platform",
    "ddsketch_version",
)


def export(scratch: Path) -> Path:
    """Run ``gspio calc-graph --scenarios`` over level 5, laid out as it is here.

    A process of its own, because the plan registers its stacked tables as
    it runs, and a registration made inside the caller would outlive the
    export. Returns the directory the two records were written to.
    """
    model = scratch / TUTORIAL
    shutil.copytree(
        ROOT / TUTORIAL, model, ignore=shutil.ignore_patterns("__pycache__")
    )
    written = scratch / "viewer" / "fixtures"
    written.mkdir(parents=True)
    subprocess.run(  # noqa: S603 -- this interpreter, this package's own command
        [
            sys.executable,
            "-m",
            "gaspatchio.cli",
            "calc-graph",
            "model.py",
            "model_points.parquet",
            "--scenarios",
            "run_scenarios.py",
            "--policies",
            ":3",
            "--no-versions",
            "--artifact",
            str(written / DOCUMENT),
        ],
        cwd=model,
        check=True,
        capture_output=True,
    )
    return written


def _refusals(document: dict, record: bytes) -> list[str]:
    """Return each way the two records fall short of a committed pair."""
    from gaspatchio.frame.graph import validate_artifact  # noqa: PLC0415

    said = []
    if not validate_artifact(document).ok:
        said.append(f"{DOCUMENT} does not validate")
    audit = document["model"].get("audit", {})
    if not str(audit.get("path", "")).endswith(f"viewer/fixtures/{RECORD}"):
        said.append(f"{DOCUMENT} does not name {RECORD} where it is committed")
    if audit.get("fingerprint") != f"sha256:{hashlib.sha256(record).hexdigest()}":
        said.append(f"{DOCUMENT} does not name {RECORD} by its bytes")
    if document["producer"].get("versions") != WITHHELD:
        said.append(f"{DOCUMENT} states its library versions")
    metadata = json.loads(record)["run_metadata"]
    stated = [key for key in VERSION_KEYS if metadata.get(key) != WITHHELD]
    if stated:
        said.append(f"{RECORD} states {', '.join(stated)}")
    return said


def main() -> None:
    """Export the pair, stamped with this tree's version, and read it back."""
    tree = tomllib.loads(PYPROJECT.read_text("utf-8"))["project"]["version"]
    installed = version("gaspatchio")
    if installed != tree:
        msg = (
            f"The installed core is {installed} and this tree is {tree}, so the "
            "documents would be stamped with a version that did not write them. "
            "Install this tree's core, then export the fixture again."
        )
        raise SystemExit(msg)
    with tempfile.TemporaryDirectory() as scratch:
        written = export(Path(scratch))
        document = json.loads((written / DOCUMENT).read_text("utf-8"))
        record = (written / RECORD).read_bytes()
        refused = _refusals(document, record)
        if refused:
            raise SystemExit("; ".join(refused))
        for name in (DOCUMENT, RECORD):
            shutil.copyfile(written / name, FIXTURES / name)
    (FIXTURES / SUPERSEDED).unlink(missing_ok=True)
    stamp = document["producer"]["version"]
    print(f"{DOCUMENT} and {RECORD}: producer {stamp}")  # noqa: T201


if __name__ == "__main__":
    main()
