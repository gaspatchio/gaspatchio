# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio diff`` and the comparison page refuse the same pair, and only it.

The page refused two artifacts whose ``model.source_path`` differed while
``gspio diff`` compared them: the two readings of one comparison disagreed at
the first question. The page is held to the report's refusal -- two
fingerprint algorithms, between which there is no translation (section 14.2)
-- in ``viewer/test/compare.test.ts``, ``viewer/test/parse.test.ts`` and
``viewer/e2e/refusals.spec.ts``. This file pins the report's side over the
same committed fixtures the page's tests read: a differing model path is
compared, line for line as the unmoved pair, and a differing grammar is
refused, whatever the path says.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph.diff import diff_artifacts

_FIXTURES = Path(__file__).resolve().parents[4] / "viewer" / "fixtures"

pytestmark = pytest.mark.skipif(
    not (_FIXTURES / "compare-before.json").is_file(),
    reason="the viewer's committed fixtures are not in this tree",
)


def _fixture(name: str) -> dict[str, Any]:
    """Return one of the page's committed comparison fixtures."""
    loaded: dict[str, Any] = json.loads((_FIXTURES / name).read_text("utf-8"))
    return loaded


def _with(document: dict[str, Any], **model: object) -> dict[str, Any]:
    """Return ``document`` with its ``model`` block members replaced."""
    derived = copy.deepcopy(document)
    derived["model"] = {**derived["model"], **model}
    return derived


def test_a_differing_model_path_is_compared_line_for_line() -> None:
    """Last quarter's model copied into a new folder of one repository.

    The path is written relative to the repository's root, so it moves; the
    model did not, and the report reads the same lines as for the unmoved
    pair.
    """
    before, after = _fixture("compare-before.json"), _fixture("compare-after.json")
    moved = _with(after, source_path="q4/model.py")
    assert moved["model"]["source_path"] != before["model"]["source_path"]

    report = diff_artifacts(before, moved).to_dict()
    unmoved = diff_artifacts(before, after).to_dict()

    assert report["calculations"] == unmoved["calculations"]
    assert report["calculations"], "the fixture pair moved nothing to compare"


def test_a_differing_grammar_is_refused_whatever_the_path_says() -> None:
    """The one refusal the report makes, and so the one the page makes."""
    before = _fixture("compare-before.json")
    other = f"{before['fingerprint_algorithm']}-and-a-half"
    after = _fixture("compare-after.json") | {"fingerprint_algorithm": other}

    with pytest.raises(ValueError, match="Cannot compare"):
        diff_artifacts(before, after)
    with pytest.raises(ValueError, match="Cannot compare"):
        diff_artifacts(before, _with(after, source_path=before["model"]["source_path"]))


def test_the_command_compares_the_one_pair_and_refuses_the_other(
    tmp_path: Path,
) -> None:
    """``gspio diff`` exits 1 with the changes over the moved pair, 2 over the other."""
    before = tmp_path / "before.json"
    moved = tmp_path / "moved.json"
    regrammared = tmp_path / "regrammared.json"
    earlier = _fixture("compare-before.json")
    before.write_text(json.dumps(earlier), "utf-8")
    later = _fixture("compare-after.json")
    moved.write_text(json.dumps(_with(later, source_path="q4/model.py")), "utf-8")
    regrammared.write_text(
        json.dumps(
            later | {"fingerprint_algorithm": f"{earlier['fingerprint_algorithm']}-x"}
        ),
        "utf-8",
    )
    runner = CliRunner()

    compared = runner.invoke(app, ["diff", str(before), str(moved), "--no-results"])
    refused = runner.invoke(
        app, ["diff", str(before), str(regrammared), "--no-results"]
    )

    assert compared.exit_code == 1, compared.output
    assert "Calculations:" in compared.output
    assert refused.exit_code == 2, refused.output
    assert "cannot be compared" in refused.output
