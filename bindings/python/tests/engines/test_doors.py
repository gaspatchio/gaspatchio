# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The three doors an engine is reached through, and what they leave behind.

``af.collect(engine=...)`` is the frame door, ``gspio run-artifact`` the file
door, and ``gspio validate --engine`` the inputs-free half of the first
group of refusals. All three are exercised here with no engine installed --
which is the state of this venv and the state every core installation starts
in -- and with a stub standing in for one.

The completion hook is the load-bearing part. A collect on an engine has to
leave the frame in exactly the state a collect on Polars leaves it in, or
``continue_from=`` cannot verify a returning column and a superseded
definition loses its values.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.engines import EngineNotInstalledError, register_engine
from gaspatchio.engines.protocol import (
    EngineResult,
    NodeStatus,
    ResultManifest,
    Sink,
    write_with_manifest,
)
from gaspatchio.engines.reference import _reference_from_collection, polars_reference
from gaspatchio.engines.report import RunReport
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

FINGERPRINT = "sha256:" + "ab" * 32

# A provider module for the fresh-subprocess test: it registers an engine
# that echoes the artifact's input nodes back as results. What is under test
# is discovery in a process that imported nothing first, so the engine's own
# arithmetic is deliberately none.
PROVIDER_SOURCE = '''
import polars as pl

from gaspatchio.engines import register_engine
from gaspatchio.engines.protocol import NodeStatus, ResultManifest, digest_of_inputs
from gaspatchio.engines.report import RunReport


class StubEngine:
    """An engine that hands the arriving columns back under their node ids."""

    name = "stub"
    version = "0.0.0-test"

    def validate_tree(self, document):
        return tuple(
            NodeStatus(
                node_id=node["id"],
                status="lowered" if node["kind"] == "input" else "refused",
                condition=(
                    None
                    if node["kind"] == "input"
                    else "this stub computes nothing"
                ),
                clause=None,
            )
            for node in document["nodes"]
        )

    def run(self, document, inputs, sink, *, every_node=False):
        arriving = [node for node in document["nodes"] if node["kind"] == "input"]
        columns = {node["id"]: node["id"] for node in arriving}
        manifest = ResultManifest(
            scope="every-node" if every_node else "final-schema",
            columns=columns,
            dtypes={node["id"]: node["dtype"] for node in arriving},
            row_identity=None,
            graph_fingerprint=document["graph_fingerprint"],
            inputs_digest=digest_of_inputs(inputs, [n["column"] for n in arriving]),
            producer="stub",
            versions={"engine_version": "0.0.0-test"},
        )
        sink.open(manifest)
        sink.write_batch(
            inputs.select(
                [pl.col(node["column"]).alias(node["id"]) for node in arriving]
            )
        )
        return sink.publish(RunReport(refusals=(), notes=()))


register_engine("stub", StubEngine)
'''


class _EchoEngine:
    """An engine handed the answer in advance, so the door can be tested alone."""

    name = "echo"
    version = "0.0.0-test"

    def __init__(self, frame: pl.DataFrame, manifest: ResultManifest) -> None:
        self._frame = frame
        self._manifest = manifest
        self.report = RunReport(refusals=(), notes=())
        self.asked_for_every_node: bool | None = None
        self.inputs: pl.DataFrame | None = None

    def validate_tree(self, document: dict[str, Any]) -> tuple[NodeStatus, ...]:  # noqa: ARG002 -- the protocol's parameter; this stub answers about no node
        return ()

    def run(
        self,
        document: dict[str, Any],  # noqa: ARG002 -- the answer was handed over in advance
        inputs: pl.DataFrame,
        sink: Sink,
        *,
        every_node: bool = False,
    ) -> EngineResult:
        self.asked_for_every_node = every_node
        self.inputs = inputs
        sink.open(self._manifest)
        sink.write_batch(self._frame)
        return sink.publish(self.report)


def _two_definitions() -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}))
    af.result = af.amount + 1
    af.result = af.result * 2
    return af


def _what_a_collect_left(af: ActuarialFrame) -> tuple[Any, ...]:
    retained = af._retained_values  # noqa: SLF001 -- the contract under test
    return (
        af._collected_values is not None,  # noqa: SLF001
        sorted(retained.columns) if retained is not None else None,
        af._window_start == len(af._calculations),  # noqa: SLF001
    )


def test_the_frame_door_refuses_an_absent_provider_by_name() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "amount": [1.0]}))
    af.result = af.amount + 1

    with pytest.raises(EngineNotInstalledError) as caught:
        af.collect(engine="jax")

    assert 'pip install "gaspatchio[jax]"' in str(caught.value)


def test_the_frame_door_leaves_the_polars_engines_alone() -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "amount": [1.0]}))
    af.result = af.amount + 1

    for engine in ("streaming", "in-memory", "auto"):
        assert af.collect(engine=engine)["result"].to_list() == [2.0]


def test_the_completion_hook_is_one_function_both_paths_call() -> None:
    on_polars = _two_definitions()
    on_polars.collect()
    expected = _what_a_collect_left(on_polars)

    # The answer is built from a SECOND frame of the same model. Built from
    # `af` itself it would have collected `af` on Polars first, and every
    # assertion below would then be about what that collect left behind
    # rather than about what the engine door did.
    answer, manifest = polars_reference(_two_definitions(), every_node=True)
    af = _two_definitions()
    engine = _EchoEngine(answer, manifest)
    engine.report = RunReport(refusals=(), notes=("Sparse lookup path used.",))
    register_engine("echo", lambda: engine)

    frame = af.collect(engine="echo")

    assert frame.columns == ["policy_id", "amount", "result"]
    assert frame["result"].to_list() == [202.0, 402.0]
    assert engine.asked_for_every_node is True
    summary = af.graph.last_run
    assert summary is not None
    assert (summary.engine, summary.polars_mode, summary.profiled) == (
        "echo",
        None,
        False,
    )
    assert (summary.rows, summary.columns) == (2, 3)
    assert summary.report is engine.report
    assert summary.report.notes == ("Sparse lookup path used.",)
    with pytest.raises(ValueError, match="no completed Polars collection"):
        _reference_from_collection(af)
    # The witness for `continue_from=`, asserted before the state tuple below
    # because it is the claim a reader can act on: a frame derived from what
    # the engine handed back re-enters through the door that verifies it,
    # which only works because the values this collect produced are the ones
    # the frame is holding.
    derived = ActuarialFrame(frame, continue_from=af)
    assert derived.collect()["result"].to_list() == [202.0, 402.0]
    assert _what_a_collect_left(af) == expected


def test_an_engine_run_states_the_versions_its_own_manifest_names() -> None:
    answer, manifest = polars_reference(_two_definitions(), every_node=True)
    stated = {"engine_version": "0.0.0-test", "backend": "cpu"}
    engine = _EchoEngine(answer, dataclasses.replace(manifest, versions=stated))
    register_engine("echo", lambda: engine)
    af = _two_definitions()

    af.collect(engine="echo")

    summary = af.graph.last_run
    assert summary is not None
    assert summary.engine == "echo"
    assert summary.versions == stated
    # Still a value: it hashes and compares as it did before it named what
    # produced it, and an edit to one reading of the versions is the
    # caller's own.
    assert hash(summary) == hash(summary)
    assert {summary: "run"}[summary] == "run"
    edited = summary.versions
    edited["engine_version"] = "edited"
    assert summary.versions == stated


def test_the_frame_door_hands_the_engine_the_arriving_columns() -> None:
    # A second frame for the answer, for the reason above: what is under test
    # is what the door reads off a frame nothing has collected.
    answer, manifest = polars_reference(_two_definitions(), every_node=True)
    af = _two_definitions()
    engine = _EchoEngine(answer, manifest)
    register_engine("echo", lambda: engine)

    af.collect(engine="echo")

    assert engine.inputs is not None
    assert sorted(engine.inputs.columns) == ["amount", "policy_id"]
    assert engine.inputs["amount"].to_list() == [100.0, 200.0]


def _at_signs() -> ActuarialFrame:
    """Return a model whose column names carry the character node ids join on."""
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "spot@rate": [2.0, 3.0]}))
    af["net@fx"] = af["spot@rate"] * 2
    return af


def test_a_column_whose_name_carries_an_at_sign_comes_back() -> None:
    # `spot@rate` is the input node's id AND its column; the computed node is
    # `net@fx@1`. Split the id on the first `@` and both columns vanish
    # without a word, which is the one thing a door may not do.
    answer, manifest = polars_reference(_at_signs(), every_node=True)
    af = _at_signs()
    register_engine("echo", lambda: _EchoEngine(answer, manifest))

    frame = af.collect(engine="echo")

    assert sorted(frame.columns) == ["net@fx", "policy_id", "spot@rate"]
    assert frame["net@fx"].to_list() == [4.0, 6.0]
    assert frame["spot@rate"].to_list() == [2.0, 3.0]


def test_a_node_the_document_does_not_carry_is_refused_not_dropped() -> None:
    from gaspatchio.engines.report import EngineRefusal

    answer, manifest = polars_reference(_two_definitions(), every_node=True)
    invented = ResultManifest(
        scope=manifest.scope,
        columns={**manifest.columns, "reserve@1": "result@2"},
        dtypes={**manifest.dtypes, "reserve@1": "f64"},
        row_identity=manifest.row_identity,
        graph_fingerprint=manifest.graph_fingerprint,
        inputs_digest=manifest.inputs_digest,
        producer="echo",
        versions=manifest.versions,
    )
    af = _two_definitions()
    register_engine("echo", lambda: _EchoEngine(answer, invented))

    with pytest.raises(EngineRefusal) as caught:
        af.collect(engine="echo")

    assert "reserve@1" in str(caught.value)
    assert "has no such node" in str(caught.value)
    # A completion refusal, not a tree one: `engine.run` has returned by the
    # time the door places a column, so the work was done and what is being
    # withheld is the publication of it.
    assert "At completion, with every output withheld:" in str(caught.value)
    assert "No results were published." in str(caught.value)
    assert caught.value.report.refusals[0].group == "completion"


def test_an_engine_that_publishes_no_batch_is_one_refusal_not_one_per_column() -> None:
    from gaspatchio.engines.report import EngineRefusal

    class _SilentEngine:
        """Opens the sink, publishes, and never writes a batch."""

        name = "silent"
        version = "0.0.0-test"

        def __init__(self, manifest: ResultManifest) -> None:
            self._manifest = manifest

        def validate_tree(self, document: dict[str, Any]) -> tuple[NodeStatus, ...]:  # noqa: ARG002 -- the protocol's parameter
            return ()

        def run(
            self,
            document: dict[str, Any],  # noqa: ARG002 -- nothing is computed here
            inputs: pl.DataFrame,  # noqa: ARG002 -- nor read
            sink: Sink,
            *,
            every_node: bool = False,  # noqa: ARG002 -- the protocol's parameter
        ) -> EngineResult:
            sink.open(self._manifest)
            return sink.publish(RunReport(refusals=(), notes=()))

    _, manifest = polars_reference(_two_definitions(), every_node=True)
    af = _two_definitions()
    register_engine("silent", lambda: _SilentEngine(manifest))

    with pytest.raises(EngineRefusal) as caught:
        af.collect(engine="silent")

    # One refusal naming the engine, not four naming the columns it did not
    # write -- "named this column and wrote none" is true of every name here
    # and describes none of what happened.
    refusals = caught.value.report.refusals
    assert len(refusals) == 1
    assert refusals[0].group == "completion"
    assert refusals[0].where == "silent"
    assert "published no batch" in refusals[0].what
    assert "at least one batch" in refusals[0].move
    assert "No results were published." in str(caught.value)
    # The door returned nothing, and settled nothing.
    assert af._collected_values is None  # noqa: SLF001 -- the contract under test


def test_an_arriving_column_the_frame_no_longer_holds_is_refused_by_name() -> None:
    from gaspatchio.engines.report import EngineRefusal

    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "amount": [100.0]}))
    af.result = af.amount + 1
    # The arriving definition of `amount` is gone: the plan holds the column
    # the model wrote over it, and no engine may be handed that under the
    # arrival's name.
    af.amount = af.amount * 2
    register_engine("echo", lambda: _EchoEngine(pl.DataFrame(), _blank_manifest()))

    with pytest.raises(EngineRefusal) as caught:
        af.collect(engine="echo")

    assert "amount" in str(caught.value)
    assert "Nothing was computed." in str(caught.value)


def _blank_manifest() -> ResultManifest:
    return ResultManifest(
        scope="final-schema",
        columns={},
        dtypes={},
        row_identity=None,
        graph_fingerprint=FINGERPRINT,
        inputs_digest="sha256:0",
        producer="echo",
        versions={},
    )


def _artifact_and_book(tmp_path: Path) -> tuple[Path, Path]:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}))
    af.result = af.amount + 1
    artifact = tmp_path / "artifact.json"
    artifact.write_text(GraphExporter(af).export(profile="executable"))
    book = tmp_path / "book.parquet"
    pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}).write_parquet(book)
    return artifact, book


def test_run_artifact_refuses_by_name_and_exits_unreadable(tmp_path: Path) -> None:
    artifact, book = _artifact_and_book(tmp_path)
    out = tmp_path / "results.parquet"

    result = runner.invoke(
        app,
        [
            "run-artifact",
            str(artifact),
            str(book),
            "--engine",
            "jax",
            "-o",
            str(out),
        ],
    )

    assert result.exit_code == 2
    assert "gaspatchio[jax]" in result.output
    assert not out.exists()


@pytest.mark.parametrize("output_flag", ["--results", "--output", "-o"])
def test_run_artifact_in_a_fresh_subprocess_discovers_a_stub_provider(
    tmp_path: Path,
    output_flag: str,
) -> None:
    artifact, book = _artifact_and_book(tmp_path)
    (tmp_path / "stub_provider.py").write_text(PROVIDER_SOURCE)
    out = tmp_path / "results.parquet"

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(tmp_path), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    environment["GASPATCHIO_ENGINE_PROVIDERS"] = "stub=stub_provider"

    finished = subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [
            sys.executable,
            "-m",
            "gaspatchio.cli",
            "run-artifact",
            str(artifact),
            str(book),
            "--engine",
            "stub",
            output_flag,
            str(out),
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert finished.returncode == 0, finished.stdout + finished.stderr
    assert out.exists()
    written = pl.read_parquet(out)
    assert sorted(written.columns) == ["amount", "policy_id"]
    assert not list(tmp_path.glob("*.unpublished*"))


SILENT_PROVIDER_SOURCE = '''
from gaspatchio.engines import register_engine
from gaspatchio.engines.protocol import ResultManifest


class SilentEngine:
    """Opens the sink, publishes, and never writes a batch."""

    name = "silent"
    version = "0.0.0-test"

    def validate_tree(self, document):
        return ()

    def run(self, document, inputs, sink, *, every_node=False):
        sink.open(
            ResultManifest(
                scope="final-schema",
                columns={},
                dtypes={},
                row_identity=None,
                graph_fingerprint=document["graph_fingerprint"],
                inputs_digest="sha256:0",
                producer="silent",
                versions={},
            )
        )
        from gaspatchio.engines.report import RunReport

        return sink.publish(RunReport(refusals=(), notes=()))


register_engine("silent", SilentEngine)
'''


def test_the_file_sink_refuses_a_publication_with_no_batch(tmp_path: Path) -> None:
    """The file door gets the frame door's refusal, rather than an empty file."""
    from gaspatchio.engines.protocol import ParquetSink
    from gaspatchio.engines.report import EngineRefusal

    destination = tmp_path / "results.parquet"
    sink = ParquetSink(destination)
    sink.open(_blank_manifest())

    with pytest.raises(EngineRefusal) as caught:
        sink.publish(RunReport(refusals=(), notes=()))

    refusals = caught.value.report.refusals
    assert len(refusals) == 1
    assert refusals[0].group == "completion"
    assert refusals[0].where == "echo"
    assert "published no batch" in refusals[0].what
    assert "No results were published." in str(caught.value)
    # Nothing visible remains -- not the destination, and not the working file.
    assert not destination.exists()
    assert not list(tmp_path.glob("*.unpublished*"))


def test_run_artifact_on_a_silent_engine_writes_nothing(tmp_path: Path) -> None:
    artifact, book = _artifact_and_book(tmp_path)
    (tmp_path / "silent_provider.py").write_text(SILENT_PROVIDER_SOURCE)
    out = tmp_path / "results.parquet"

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(tmp_path), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    environment["GASPATCHIO_ENGINE_PROVIDERS"] = "silent=silent_provider"

    finished = subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [
            sys.executable,
            "-m",
            "gaspatchio.cli",
            "run-artifact",
            str(artifact),
            str(book),
            "--engine",
            "silent",
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert "published no batch" in finished.stdout + finished.stderr
    assert not out.exists()
    assert not list(tmp_path.glob("*.unpublished*"))


def _result_file(  # noqa: PLR0913 -- one parameter per field the written manifest states
    path: Path,
    frame: pl.DataFrame,
    fingerprint: str,
    *,
    book: str = "sha256:book",
    producer: str = "polars",
    dtype: str = "f64",
) -> None:
    write_with_manifest(
        frame,
        ResultManifest(
            scope="final-schema",
            columns={name: name for name in frame.columns},
            dtypes={
                name: "i64" if name == "policy_id" else dtype for name in frame.columns
            },
            row_identity=("policy_id",),
            graph_fingerprint=fingerprint,
            inputs_digest=book,
            producer=producer,
            versions={},
        ),
        path,
    )


def test_compare_command_prints_and_exits_by_verdict(tmp_path: Path) -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}))
    af.result = af.amount + 1
    artifact = tmp_path / "artifact.json"
    document = json.loads(GraphExporter(af).export(profile="executable"))
    artifact.write_text(json.dumps(document))
    fingerprint = document["graph_fingerprint"]

    values = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "amount": [100.0, 200.0],
            "result@1": [101.0, 201.0],
        }
    )
    before = tmp_path / "before.parquet"
    same = tmp_path / "same.parquet"
    apart = tmp_path / "apart.parquet"
    short = tmp_path / "short.parquet"
    _result_file(before, values, fingerprint)
    _result_file(same, values, fingerprint, producer="jax")
    _result_file(
        apart,
        values.with_columns(pl.Series("result@1", [101.5, 201.0])),
        fingerprint,
        producer="jax",
    )
    _result_file(
        short,
        values.drop("result@1"),
        fingerprint,
        book="sha256:other",
        producer="jax",
    )

    agreed = runner.invoke(app, ["compare", str(artifact), str(before), str(same)])
    assert agreed.exit_code == 0
    assert "agree" in agreed.output
    assert "same book" in agreed.output

    disagreed = runner.invoke(app, ["compare", str(artifact), str(before), str(apart)])
    assert disagreed.exit_code == 1

    undecided = runner.invoke(app, ["compare", str(artifact), str(before), str(short)])
    assert undecided.exit_code == 4
    assert "two books" in undecided.output


def test_an_exact_line_prints_no_magnitude(tmp_path: Path) -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2], "lives": [10, 20]}))
    af.deaths = af.lives * 2
    artifact = tmp_path / "artifact.json"
    document = json.loads(GraphExporter(af).export(profile="executable"))
    artifact.write_text(json.dumps(document))

    counts = pl.DataFrame(
        {"policy_id": [1, 2], "lives": [10, 20], "deaths@1": [20, 40]}
    )
    before = tmp_path / "before.parquet"
    after = tmp_path / "after.parquet"
    _result_file(before, counts, document["graph_fingerprint"], dtype="i64")
    _result_file(
        after,
        counts.with_columns(pl.Series("deaths@1", [20, 41])),
        document["graph_fingerprint"],
        dtype="i64",
        producer="jax",
    )

    result = runner.invoke(app, ["compare", str(artifact), str(before), str(after)])

    assert result.exit_code == 1
    assert "deaths@1 · max |a-b| - ·" in result.output
    assert "parted on i64, which is exact" in result.output


def test_validate_engine_prints_node_status_only_when_the_engine_loads(
    tmp_path: Path,
) -> None:
    artifact, _ = _artifact_and_book(tmp_path)
    document = json.loads(artifact.read_text())

    silent = runner.invoke(app, ["validate", str(artifact), "--engine", "jax"])
    assert silent.exit_code == 0
    assert "No engine named jax is available here" in silent.output
    assert "result@1" not in silent.output

    class Reading:
        name = "reading"
        version = "0.0.0-test"

        def validate_tree(self, document: dict[str, Any]) -> tuple[NodeStatus, ...]:
            return tuple(
                NodeStatus(
                    node_id=node["id"],
                    status="lowered" if node["kind"] == "input" else "refused",
                    condition=None
                    if node["kind"] == "input"
                    else "this engine lowers no arithmetic",
                    clause="11.1.25",
                )
                for node in document["nodes"]
            )

        def run(self, *args: object, **kwargs: object) -> EngineResult:
            raise NotImplementedError

    register_engine("reading", Reading)

    read = runner.invoke(app, ["validate", str(artifact), "--engine", "reading"])

    assert read.exit_code == 1
    assert "result@1" in read.output
    assert "refused" in read.output
    assert str(len(document["nodes"])) in read.output


def test_validate_engine_puts_the_same_reading_in_the_json_document(
    tmp_path: Path,
) -> None:
    artifact, _ = _artifact_and_book(tmp_path)
    document = json.loads(artifact.read_text())

    class Reading:
        name = "writing"
        version = "0.0.0-test"

        def validate_tree(self, document: dict[str, Any]) -> tuple[NodeStatus, ...]:
            return tuple(
                NodeStatus(
                    node_id=node["id"],
                    status="lowered" if node["kind"] == "input" else "refused",
                    condition=None
                    if node["kind"] == "input"
                    else "this engine lowers no arithmetic",
                    clause="11.1.25",
                )
                for node in document["nodes"]
            )

        def run(self, *args: object, **kwargs: object) -> EngineResult:
            raise NotImplementedError

    register_engine("writing", Reading)
    stored = tmp_path / "validation.json"

    result = runner.invoke(
        app,
        ["validate", str(artifact), "--engine", "writing", "-o", str(stored)],
    )

    # The status says something refused, so the document has to say what.
    assert result.exit_code == 1
    reading = json.loads(stored.read_text())["engine"]
    assert reading["name"] == "writing"
    assert reading["available"] is True
    assert reading["refused"] == 1
    assert {one["node_id"] for one in reading["nodes"]} == {
        node["id"] for node in document["nodes"]
    }
    assert [one for one in reading["nodes"] if one["status"] == "refused"] == [
        {
            "node_id": "result@1",
            "status": "refused",
            "condition": "this engine lowers no arithmetic",
            "clause": "11.1.25",
        }
    ]


def test_validate_names_an_absent_engine_in_the_json_document(
    tmp_path: Path,
) -> None:
    artifact, _ = _artifact_and_book(tmp_path)
    stored = tmp_path / "validation.json"

    result = runner.invoke(
        app,
        ["validate", str(artifact), "--engine", "jax", "--json", "-o", str(stored)],
    )

    assert result.exit_code == 0
    reading = json.loads(stored.read_text())["engine"]
    assert reading["available"] is False
    assert reading["nodes"] == []
    assert "gaspatchio[jax]" in reading["why"]


def test_run_model_every_node_writes_the_manifest_into_the_file(
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.py"
    model.write_text(
        "from gaspatchio import ActuarialFrame\n"
        "\n"
        "\n"
        "def main(af: ActuarialFrame) -> ActuarialFrame:\n"
        "    af.result = af.amount + 1\n"
        "    af.result = af.result * 2\n"
        "    return af\n"
    )
    book = tmp_path / "book.parquet"
    pl.DataFrame({"policy_id": [1, 2], "amount": [100.0, 200.0]}).write_parquet(book)
    out = tmp_path / "every.parquet"

    result = runner.invoke(
        app,
        ["run-model", str(model), str(book), "--every-node", "-o", str(out)],
    )

    assert result.exit_code == 0, result.output
    written = pl.read_parquet(out)
    assert "result@1" in written.columns
    assert "result@2" in written.columns
    assert written["result@1"].to_list() == [101.0, 201.0]

    from gaspatchio.engines.protocol import read_manifest

    manifest = read_manifest(out)
    assert manifest.scope == "every-node"
    assert manifest.producer == "polars"
    assert set(manifest.columns) >= {"result@1", "result@2"}
