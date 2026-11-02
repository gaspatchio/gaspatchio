# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The setup step that rebuilds the frame from a bare constructor.

Collect, rename in Polars, hand the DataFrame back to ``ActuarialFrame(mp)``:
the model template teaches it, models are written that way, and nothing about
it is going to be refused. What it costs is the log. The rebuilt frame holds
columns an earlier frame calculated and columns a Polars statement created,
and it has no record of either -- so every one of them looks exactly like a
field that arrived with the policy data.

The producer must not say that. Section 8's ``model_points`` is "the policy
data the model was run over", and a column that data never carried has no
business claiming it. What the producer can see is the whole of what it
says: the run began over a file whose columns it knows, this frame arrived
holding names that file did not carry, and no record on this frame accounts
for them. That is section 7.1's first hole, word for word -- "a column that
is on the frame with no account of itself anywhere in what the model
logged". The frame says which of the two each is: the column the earlier
frame calculated is still that frame's memory when the new one is built, so
it is ``rebuilt``; the column the Polars statement made holds an arriving
column's memory, which is the data's, so it is ``unrecorded``.

The other door is still open and still says more: ``ActuarialFrame(mp,
continue_from=af)`` keeps the lineage and records the boundary, and the
second test here is that this change left it exactly where it was.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph import validate_artifact

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# The model of the gap this file is about. ``expected_claims`` is struck
# before the rebuild and ``premium`` is created by the Polars statement in
# the middle of it; neither is a column of the file, and after the bare
# constructor neither has a record anywhere.
REBUILT_MODEL_SRC = """
import polars as pl
from gaspatchio import ActuarialFrame, when


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.expected_claims = af.sum_assured * af.mortality_rate
    mp = af.collect()
    mp = mp.with_columns(pl.col("annual_premium").alias("premium"))
    af = ActuarialFrame(mp)
    af.expenses = af.premium * af.expense_rate
    af.profit = af.premium - af.expenses - af.expected_claims
    af.is_profitable = when(af.profit > 0).then("Yes").otherwise("No")
    return af
"""

# The same model through the door that was built for it.
CONTINUED_MODEL_SRC = REBUILT_MODEL_SRC.replace(
    "ActuarialFrame(mp)", "ActuarialFrame(mp, continue_from=af)"
)

# What the file carries, and nothing else. The seven columns are the ones a
# reader is entitled to see ``model_points`` against.
FILE_COLUMNS = (
    "policy_id",
    "age",
    "sex",
    "sum_assured",
    "annual_premium",
    "mortality_rate",
    "expense_rate",
)


def _artifact(tmp_path: Path, source: str) -> dict[str, Any]:
    """Run ``source`` over three model points and return the exported artifact."""
    document, _output = _exported(tmp_path, source)
    return document


def _exported(tmp_path: Path, source: str) -> tuple[dict[str, Any], str]:
    """Run ``source`` over three model points; return the artifact and what printed."""
    model_path = tmp_path / "model.py"
    model_path.write_text(source)
    points_path = tmp_path / "model_points.parquet"
    pl.DataFrame(
        {
            "policy_id": [1, 2, 3],
            "age": [35, 45, 55],
            "sex": ["M", "F", "M"],
            "sum_assured": [100_000.0, 250_000.0, 500_000.0],
            "annual_premium": [500.0, 1_200.0, 3_000.0],
            "mortality_rate": [0.001, 0.002, 0.005],
            "expense_rate": [0.05, 0.05, 0.05],
        }
    ).write_parquet(points_path)
    out = tmp_path / "graph.json"

    result = runner.invoke(
        app, ["calc-graph", str(model_path), str(points_path), "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    document: dict[str, Any] = json.loads(out.read_text())
    return document, result.output


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def test_a_bare_rebuild_never_writes_the_file_as_the_source(tmp_path: Path) -> None:
    """Neither column the file does not carry claims it did."""
    artifact = _artifact(tmp_path, REBUILT_MODEL_SRC)

    for column in ("expected_claims", "premium"):
        node = _node(artifact, column)
        assert node["kind"] == "hole", node
        assert node["provenance"] is None, node
        assert node["formula"] is None, node
        assert node["materialized_at"] is None, node

    claimed = {
        node["column"]
        for node in artifact["nodes"]
        if node["provenance"] == "model_points"
    }
    assert claimed == set(FILE_COLUMNS)


def test_a_bare_rebuild_names_what_it_could_not_account_for(tmp_path: Path) -> None:
    """The holes section carries one entry per column, and the file still validates."""
    artifact = _artifact(tmp_path, REBUILT_MODEL_SRC)

    assert {(hole["column"], hole["reason"]) for hole in artifact["holes"]} == {
        ("expected_claims", "rebuilt"),
        ("premium", "unrecorded"),
    }
    # Nothing froze and nothing came back, so there is no boundary to report.
    assert artifact["boundaries"] == []
    assert validate_artifact(artifact).ok


def test_the_file_s_own_columns_are_still_inputs(tmp_path: Path) -> None:
    """A column the data really did carry reads exactly as it always did."""
    artifact = _artifact(tmp_path, REBUILT_MODEL_SRC)

    node = _node(artifact, "sum_assured")
    assert node["kind"] == "input"
    assert node["provenance"] == "model_points"


def test_the_explicit_re_entry_is_unchanged(tmp_path: Path) -> None:
    """``continue_from=`` still keeps the lineage and still records the boundary."""
    artifact = _artifact(tmp_path, CONTINUED_MODEL_SRC)

    claim = _node(artifact, "expected_claims@1")
    assert claim["kind"] == "computed"
    assert claim["provenance"] == "assignment"
    assert claim["formula"] == "af.sum_assured * af.mortality_rate"

    premium = _node(artifact, "premium@1")
    assert premium["kind"] == "input"
    assert premium["provenance"] == "continuation"

    assert artifact["holes"] == []
    assert [boundary["ordinal"] for boundary in artifact["boundaries"]] == [0]
    assert validate_artifact(artifact).ok


def test_the_summary_names_each_column_it_cannot_account_for(tmp_path: Path) -> None:
    """The count says how many; the line under the tiers says which, and why."""
    _document, output = _exported(tmp_path, REBUILT_MODEL_SRC)

    assert "Unaccounted for: expected_claims (rebuilt), premium (unrecorded)" in output


def test_a_model_that_accounts_for_everything_prints_no_such_line(
    tmp_path: Path,
) -> None:
    _document, output = _exported(tmp_path, CONTINUED_MODEL_SRC)

    assert "Unaccounted for" not in output
