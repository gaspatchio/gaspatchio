# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A modeller's results file compares against an engine's results of the same model.

``gspio run-model --results`` writes the finished frame under the columns the
model wrote, with a final-schema manifest naming the node each column
carries. An engine's file door writes a final-schema run the same way, so
``gspio compare`` lines the two up node by node and reports whether they
agree. Where the two cannot be compared -- two scopes, a file with no
manifest, results of another model -- it says why in a sentence and exits 2,
never with a traceback.

The engine here is a stand-in with the model's arithmetic written into it,
reached through ``gspio run-artifact`` as any engine is: what is under test
is the comparison of the files, not a second implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.engines import register_engine
from gaspatchio.engines.protocol import (
    EngineResult,
    NodeStatus,
    ResultManifest,
    Sink,
    digest_of_inputs,
)
from gaspatchio.engines.report import RunReport
from gaspatchio.frame.graph.artifact import book_columns

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

MODEL_SRC = "def main(af):\n    af.result = af.amount * 2\n    return af\n"


class _TwinEngine:
    """An engine for one model, writing a final-schema result as a file door does.

    The model's own column names, a manifest naming the node each carries in
    the type the node declares, and the digest of the inputs it was handed.
    ``factor`` is the arithmetic, so a twin that parts from the model can be
    built as easily as one that agrees.
    """

    name = "twin"
    version = "0.0.0-test"

    def __init__(self, factor: float) -> None:
        self.factor = factor

    def validate_tree(self, document: dict[str, Any]) -> tuple[NodeStatus, ...]:  # noqa: ARG002 -- the protocol's parameter; this stand-in answers about no node
        return ()

    def run(
        self,
        document: dict[str, Any],
        inputs: pl.DataFrame,
        sink: Sink,
        *,
        every_node: bool = False,  # noqa: ARG002 -- this stand-in writes the final schema only
    ) -> EngineResult:
        schema = [node for node in document["nodes"] if node.get("in_final_schema")]
        sink.open(
            ResultManifest(
                scope="final-schema",
                columns={node["id"]: node["column"] for node in schema},
                dtypes={node["id"]: node["dtype"] for node in schema},
                row_identity=None,
                graph_fingerprint=document["graph_fingerprint"],
                inputs_digest=digest_of_inputs(inputs, book_columns(document["nodes"])),
                producer=self.name,
                versions={"engine_version": self.version},
            )
        )
        sink.write_batch(
            inputs.select("policy_id", "amount").with_columns(
                (inputs.get_column("amount") * self.factor).alias("result")
            )
        )
        return sink.publish(RunReport(refusals=()))


def _model_and_book(
    tmp_path: Path, source: str = MODEL_SRC, name: str = "model.py"
) -> tuple[Path, Path]:
    model = tmp_path / name
    model.write_text(source)
    points = tmp_path / "book.parquet"
    pl.DataFrame(
        {"policy_id": ["P-1", "P-2", "P-3"], "amount": [2.0, 3.0, 17_000.25]}
    ).write_parquet(points)
    return model, points


def _invoked(*arguments: str | Path) -> tuple[int, str]:
    result = runner.invoke(app, [str(argument) for argument in arguments])
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        result.output
    )
    return result.exit_code, " ".join(result.output.split())


def _artifact_and_results(tmp_path: Path) -> tuple[Path, Path, Path]:
    model, points = _model_and_book(tmp_path)
    artifact = tmp_path / "artifact.json"
    status, said = _invoked(
        "calc-graph", model, points, "--profile", "executable", "-o", artifact
    )
    assert status == 0, said
    results = tmp_path / "polars.parquet"
    status, said = _invoked("run-model", model, points, "--results", results)
    assert status == 0, said
    return artifact, points, results


@pytest.mark.parametrize(
    ("factor", "exit_code", "verdict"), [(2.0, 0, "agree"), (2.5, 1, "disagree")]
)
def test_run_model_results_compare_against_an_engine_s_results_of_the_same_model(
    tmp_path: Path, factor: float, exit_code: int, verdict: str
) -> None:
    artifact, points, results = _artifact_and_results(tmp_path)
    register_engine("twin", lambda: _TwinEngine(factor))
    engine = tmp_path / "twin.parquet"
    status, said = _invoked(
        "run-artifact", artifact, points, "--engine", "twin", "--results", engine
    )
    assert status == 0, said

    status, said = _invoked("compare", artifact, results, engine)

    assert status == exit_code, said
    assert f"polars.parquet and twin.parquet {verdict}" in said
    assert (
        "final-schema · rows matched by identity on policy_id · the same book" in said
    )
    assert "polars → twin" in said
    assert "Lines: 3 nodes" in said
    line = said[said.index("result@1 · max |a-b|") :]
    assert line.split(" · ")[4] == verdict


def test_a_results_file_beside_an_every_node_file_is_refused_in_a_sentence(
    tmp_path: Path,
) -> None:
    artifact, points, results = _artifact_and_results(tmp_path)
    every = tmp_path / "every.parquet"
    status, said = _invoked(
        "run-model", tmp_path / "model.py", points, "--every-node", "-o", every
    )
    assert status == 0, said

    status, said = _invoked("compare", artifact, results, every)

    assert status == 2, said
    assert "These two results cannot be compared" in said
    assert "different scopes: final-schema and every-node" in said


def test_a_file_with_no_manifest_is_refused_naming_the_commands_that_write_one(
    tmp_path: Path,
) -> None:
    artifact, _, results = _artifact_and_results(tmp_path)
    plain = tmp_path / "plain.parquet"
    pl.read_parquet(results).write_parquet(plain)

    status, said = _invoked("compare", artifact, results, plain)

    assert status == 2, said
    assert "carries no 'gaspatchio.scope'" in said
    assert "gspio run-model --results" in said


@pytest.mark.parametrize("command", ["compare", "diff"])
def test_a_manifest_member_of_the_wrong_shape_is_refused_in_a_sentence(
    tmp_path: Path, command: str
) -> None:
    """A list where the columns' mapping belongs is named, exit 2, no traceback."""
    artifact, _, results = _artifact_and_results(tmp_path)
    damaged = tmp_path / "damaged.parquet"
    metadata = dict(pl.read_parquet_metadata(results))
    metadata["gaspatchio.columns"] = '["a", "b"]'
    pl.read_parquet(results).write_parquet(damaged, metadata=metadata)

    arguments = (
        ("compare", artifact, results, damaged)
        if command == "compare"
        else ("diff", artifact, artifact, "--results", results, damaged)
    )
    status, said = _invoked(*arguments)

    assert status == 2, said
    assert "result manifest is damaged: gaspatchio.columns is a list" in said
    assert "Traceback" not in said


def test_results_of_another_model_are_refused_in_a_sentence(tmp_path: Path) -> None:
    artifact, points, results = _artifact_and_results(tmp_path)
    other, _ = _model_and_book(tmp_path, MODEL_SRC.replace("* 2", "* 3"), "other.py")
    theirs = tmp_path / "theirs.parquet"
    status, said = _invoked("run-model", other, points, "--results", theirs)
    assert status == 0, said

    status, said = _invoked("compare", artifact, results, theirs)

    assert status == 2, said
    assert "The results are not of this artifact" in said
    # The command's own opening says "These two results"; the reason does not
    # open the same way again.
    assert "These results" not in said
