# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The timeline a per-period node carries, and the results file beside it.

Two statements an artifact could not make. A per-period column's
``value_sample`` was the first five periods and an ellipsis, while the
envelope beside it said ``periods: null`` -- every period was taken -- so
the document described a run it did not carry. A reviewer asking "what was
the account value at month 84, and the month 83 it rolled from?" was asking
for two adjacent cells of one column for one policy, and the file held
months 0 to 4.

And nothing in the envelope named the numbers. ``model.model_points`` pins
the data the run consumed by digest; the output the same run wrote was
pinned by nothing, so an artifact and a results file were joined on a
column name with no statement anywhere that the two came from one run.

The tests here hold both halves: the declared policy's every period under
the envelope's context, with the pinned-period reading unchanged beside it,
and ``model.results`` written on exactly the model-points pattern when an
output file was written.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import TYPE_CHECKING, Any

import polars as pl
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph.calc_graph import GraphExporter
from gaspatchio.frame.graph.graph_models import GraphExportConfig
from gaspatchio.frame.graph.validate import validate_artifact

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# Six months asked for gives seven periods -- month 0 through month 6 --
# and the number is written here rather than measured off the artifact, so
# that a change in how the timeline is laid out fails this file rather than
# agreeing with itself.
_PERIODS = 7

MODEL_SRC = """
from gaspatchio import ActuarialFrame
import datetime


def main(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    af.claims = af.sum_assured * 0.001 * (af.month + 1)
    return af
"""


def _a_projection_of_seven_periods() -> ActuarialFrame:
    """Return a one-policy projection whose claims run month 0 to month 6."""
    frame = ActuarialFrame(pl.DataFrame({"policy_id": [1], "sum_assured": [100_000.0]}))
    frame = frame.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=6,
        frequency="monthly",
    )
    frame.claims = frame.sum_assured * 0.001 * (frame.month + 1)
    return frame


def _artifact(
    af: ActuarialFrame, config: GraphExportConfig | None = None
) -> dict[str, Any]:
    """Export the frame's graph against its own collected values."""
    frame = af.collect()
    return json.loads(GraphExporter(af).export(frame, config))  # type: ignore[no-any-return]


def _node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in document["nodes"] if node["id"] == node_id)


# --- the vector -------------------------------------------------------------


def test_a_per_period_sample_carries_every_period_of_the_declared_timeline() -> None:
    """The envelope says every period was taken; the node has to hold them.

    ``periods: null`` is the format's way of saying no period was pinned,
    and a node carrying five values and an ellipsis under that statement is
    a document describing a run it does not carry.
    """
    claims = _node(_artifact(_a_projection_of_seven_periods()), "claims@1")

    assert claims["shape"] == "list"
    assert len(claims["value_sample"]) == _PERIODS
    assert claims["value_sample"] == [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0]


def test_a_per_period_sample_ends_at_a_value_and_not_at_an_ellipsis() -> None:
    """No window means no marker saying a window was taken."""
    document = _artifact(_a_projection_of_seven_periods())

    for node in document["nodes"]:
        sample = node.get("value_sample")
        if isinstance(sample, list):
            assert "..." not in sample, node["id"]


def test_the_declared_context_is_what_the_vector_is_read_under() -> None:
    """The vector is one policy's, and the envelope is where that is stated."""
    document = _artifact(_a_projection_of_seven_periods())

    assert document["enrichment"]["periods"] is None
    assert document["enrichment"]["aggregation"] is None


def test_a_pinned_period_still_gives_the_one_scalar() -> None:
    """The CLI's debugging read is untouched: a period pinned is a number."""
    document = _artifact(_a_projection_of_seven_periods(), GraphExportConfig(period=3))

    assert _node(document, "claims@1")["value_sample"] == 400.0
    assert document["enrichment"]["periods"] == [3]


def test_the_validator_accepts_the_vector_beside_the_trace() -> None:
    """A trace's last line is the run's first value, and still is.

    The walk-through is of one period and the sample is now the whole run,
    so what the reading compares is the trace's result against the sample's
    first entry -- the same comparison it made against the window's first
    entry, over a longer list of the same shape.
    """
    document = _artifact(_a_projection_of_seven_periods())
    claims = _node(document, "claims@1")

    assert claims["trace"][-1]["result"] == claims["value_sample"][0]
    verdict = validate_artifact(document, deep=True)
    assert verdict.ok, [finding.message for finding in verdict.findings]


# --- the results file -------------------------------------------------------


def _model_and_points(tmp_path: Path) -> tuple[Path, Path]:
    model_path = tmp_path / "model.py"
    model_path.write_text(MODEL_SRC)
    points_path = tmp_path / "model_points.parquet"
    pl.DataFrame({"policy_id": ["A"], "sum_assured": [100_000.0]}).write_parquet(
        points_path
    )
    return model_path, points_path


def _exported_from_the_command_line(tmp_path: Path, *options: str) -> dict[str, Any]:
    """Run ``calc-graph`` over the model above and read the artifact back."""
    model_path, points_path = _model_and_points(tmp_path)
    out = tmp_path / "graph.json"

    result = runner.invoke(
        app,
        ["calc-graph", str(model_path), str(points_path), "-o", str(out), *options],
    )

    assert result.exit_code == 0, result.output
    return json.loads(out.read_text())  # type: ignore[no-any-return]


def test_an_output_file_asked_for_is_written_as_parquet(tmp_path: Path) -> None:
    """One run produces both the account and the numbers it is an account of."""
    results_path = tmp_path / "results.parquet"

    _exported_from_the_command_line(tmp_path, "--output-file", str(results_path))

    assert results_path.is_file()
    assert "claims" in pl.read_parquet(results_path).columns


def test_the_envelope_names_the_results_file_by_path_and_digest(
    tmp_path: Path,
) -> None:
    """The join between the account and the numbers, made by content.

    The fingerprint is the same content stamp ``model_points`` carries --
    ``sha256:`` over the file's own bytes -- so a reader holding the two
    files can check that the numbers came out of the run the artifact is an
    account of, rather than trusting two file names to agree.

    The path is the same relative path every other path in the artifact is,
    written against the model's root, and it is checked here by resolving it
    back to the file the digest was taken over rather than by reading the
    string alone.
    """
    results_path = tmp_path / "results.parquet"

    document = _exported_from_the_command_line(
        tmp_path, "--output-file", str(results_path)
    )

    results = document["model"]["results"]
    stamp = hashlib.sha256(results_path.read_bytes()).hexdigest()
    assert results["path"] == "results.parquet"
    assert (tmp_path / results["path"]).resolve() == results_path.resolve()
    assert results["fingerprint"] == f"sha256:{stamp}"
    assert set(results) == set(document["model"]["model_points"])


def test_no_output_file_leaves_the_results_absent_and_not_null(
    tmp_path: Path,
) -> None:
    """Absent is the claim: this run wrote no numbers anybody can point at.

    A null would say the run had results the producer could not identify,
    which is a different statement and a false one.
    """
    document = _exported_from_the_command_line(tmp_path)

    assert "results" not in document["model"]
    assert document["model"]["model_points"] is not None


def test_the_artifact_that_names_its_results_is_held_to_every_reading(
    tmp_path: Path,
) -> None:
    """A new envelope member has to pass the schema it is published under."""
    document = _exported_from_the_command_line(
        tmp_path, "--output-file", str(tmp_path / "results.parquet")
    )

    verdict = validate_artifact(document, deep=True)

    assert verdict.ok, [finding.message for finding in verdict.findings]
