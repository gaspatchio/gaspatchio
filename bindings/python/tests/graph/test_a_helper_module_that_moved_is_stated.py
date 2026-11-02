# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A helper module whose bytes moved is named in the change report's ``source``.

A model imports helpers -- an accessor, a constants file -- and the record
lists each under ``model.modules`` with a stamp of its bytes. ``gspio diff``
compared the model file's own stamp and never the helpers', so a comment in a
helper, which moves no calculation, was seen nowhere, and a constant edited in
one was reported as a changed calculation with no line naming the file it came
from. ``source`` now carries ``modules``: each helper whose stamp moved, stated
on its own line and never counted as drift, so a reviewer sees which file to
open without an alarm over an edit that cannot move a number.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import TYPE_CHECKING, Any

import polars as pl
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import (
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    ModuleMoved,
    diff_artifacts,
)

if TYPE_CHECKING:
    from pathlib import Path

_MODEL = (
    "from helper import FACTOR\n\n\n"
    "def main(af):\n    af.fee = af.premium * FACTOR\n    return af\n"
)
_HELPER = "FACTOR = 0.5\n"
_REVIEWED = _HELPER + "# reviewed\n"


def _stamp(text: str) -> str:
    """Return the SHA-256 of a file's bytes, by hand, as the record spells it."""
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _run(folder: Path, *, helper: str, factor: float) -> dict[str, Any]:
    """Write the model and its helper, and export the run it describes."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "model.py").write_text(_MODEL)
    (folder / "helper.py").write_text(helper)
    af = ActuarialFrame(pl.DataFrame({"premium": [100.0, 400.0]}))
    af.fee = af.premium * factor
    identity = ModelIdentity.of(folder / "model.py")
    document: dict[str, Any] = json.loads(
        GraphExporter(af).export(config=GraphExportConfig(model=identity))
    )
    return document


def test_a_comment_in_a_helper_is_stated_and_moves_nothing(tmp_path: Path) -> None:
    before = _run(tmp_path / "q1", helper=_HELPER, factor=0.5)
    after = _run(tmp_path / "q2", helper=_REVIEWED, factor=0.5)

    report = diff_artifacts(before, after)

    assert report.calculations == ()
    assert report.data == ()
    assert report.drift is False
    assert report.source is not None
    assert report.source.modules == (
        ModuleMoved("helper.py", _stamp(_HELPER), _stamp(_REVIEWED)),
    )
    model_file = _stamp(_MODEL)
    assert (report.source.path, report.source.before, report.source.after) == (
        "model.py",
        model_file,
        model_file,
    )


def test_a_helper_constant_names_the_helper_beside_the_calculation(
    tmp_path: Path,
) -> None:
    before = _run(tmp_path / "q1", helper=_HELPER, factor=0.5)
    after = _run(tmp_path / "q2", helper="FACTOR = 0.6\n", factor=0.6)

    report = diff_artifacts(before, after)

    assert [(c.node, c.change_origin) for c in report.calculations] == [
        ("fee@1", "self")
    ]
    assert report.source is not None
    assert report.source.modules == (
        ModuleMoved("helper.py", _stamp(_HELPER), _stamp("FACTOR = 0.6\n")),
    )
    assert report.to_dict()["source"]["modules"] == [
        {
            "path": "helper.py",
            "before": _stamp(_HELPER),
            "after": _stamp("FACTOR = 0.6\n"),
        }
    ]


def test_an_unmoved_helper_writes_no_source(tmp_path: Path) -> None:
    before = _run(tmp_path / "q1", helper=_HELPER, factor=0.5)
    after = _run(tmp_path / "q2", helper=_HELPER, factor=0.5)

    assert diff_artifacts(before, after).source is None


def test_a_helper_only_one_run_imports_is_named_with_its_missing_side() -> None:
    before: dict[str, Any] = {
        "fingerprint_algorithm": "x",
        "model": {"source_path": "m/model.py", "source_sha": "sha256:m", "modules": []},
    }
    after = copy.deepcopy(before)
    after["model"]["modules"] = [{"path": "m/rates.py", "fingerprint": "sha256:r"}]

    source = diff_artifacts(before, after).source
    assert source is not None
    assert source.modules == (ModuleMoved("m/rates.py", None, "sha256:r"),)
    reverse = diff_artifacts(after, before).source
    assert reverse is not None
    assert reverse.modules == (ModuleMoved("m/rates.py", "sha256:r", None),)


def test_a_model_copied_to_another_directory_pairs_its_helpers() -> None:
    """Paths are written from the repository root, so a copy's helpers differ."""

    def run(home: str, helper: str) -> dict[str, Any]:
        return {
            "fingerprint_algorithm": "x",
            "model": {
                "source_path": f"{home}/model.py",
                "source_sha": "sha256:m",
                "modules": [
                    {"path": f"{home}/helper.py", "fingerprint": helper},
                    {"path": "shared/curves.py", "fingerprint": "sha256:c"},
                ],
            },
        }

    assert diff_artifacts(run("q1", "sha256:h"), run("q2", "sha256:h")).source is None
    moved = diff_artifacts(run("q1", "sha256:h"), run("q2", "sha256:k")).source
    assert moved is not None
    assert moved.modules == (ModuleMoved("q2/helper.py", "sha256:h", "sha256:k"),)


def test_a_document_listing_no_modules_compares_none() -> None:
    before: dict[str, Any] = {
        "fingerprint_algorithm": "x",
        "model": {"source_path": "model.py", "source_sha": "sha256:m"},
    }
    after = copy.deepcopy(before)
    after["model"]["modules"] = [{"path": "helper.py", "fingerprint": "sha256:h"}]

    assert diff_artifacts(before, after).source is None


def test_the_command_prints_the_helper_and_exits_zero(tmp_path: Path) -> None:
    earlier, later = tmp_path / "q1.json", tmp_path / "q2.json"
    earlier.write_text(json.dumps(_run(tmp_path / "q1", helper=_HELPER, factor=0.5)))
    later.write_text(json.dumps(_run(tmp_path / "q2", helper=_REVIEWED, factor=0.5)))

    result = CliRunner().invoke(app, ["diff", str(earlier), str(later)])

    assert result.exit_code == 0, result.output
    text = " ".join(result.output.split())
    assert "nothing moved between q1.json and q2.json" in text
    assert (
        f"helper module helper.py moved: {_stamp(_HELPER)} → {_stamp(_REVIEWED)}"
    ) in text
    assert "model source" not in text
