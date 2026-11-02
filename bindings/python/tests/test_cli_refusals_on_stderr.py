# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every command says a refusal on stderr, and keeps stdout for its own output.

A pipeline reads a command's stdout as the command's answer, so a refusal
printed there is read as one. Each refusal below is one sentence on stderr,
with the command's status; stdout holds none of it. The artifact readers --
validate, verify, diff and compare -- are held to this by
``test_cli_reading_refusals.py``; this file holds every other command that
refuses: run-artifact, calc-graph, run-model, run-single-policy, docs and
knowledge.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import cli
from gaspatchio.api.client import APIConnectionError
from gaspatchio.cli import app
from gaspatchio.engines import REGISTERED_ENGINES, register_engine
from gaspatchio.frame.graph import GraphExporter
from tests.engines.test_aggregating import (
    _artifact,
    _FoldingEngine,
    _from_inception,
    _spec,
)
from tests.test_cli_artifact import (
    FAILING_MODEL_SRC,
    _model_and_points,
    _needle,
    _unwrapped,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from click.testing import Result

runner = CliRunner()


def _refused_on_stderr(result: Result, status: int, sentence: str) -> None:
    """Assert a refusal: its status, its sentence on stderr, and none on stdout."""
    assert result.exit_code == status, result.output
    assert _needle(sentence) in _unwrapped(result.stderr), result.stderr
    assert _needle(sentence) not in _unwrapped(result.stdout), result.stdout


# --- run-artifact ----------------------------------------------------------


@pytest.fixture
def folding() -> Iterator[None]:
    """Register a stub engine that folds for one test, and forget it afterwards."""
    engines = dict(REGISTERED_ENGINES)
    register_engine("folding", _FoldingEngine)
    yield
    REGISTERED_ENGINES.clear()
    REGISTERED_ENGINES.update(engines)


def _run_artifact(tmp_path: Path, case: str) -> list[str]:
    """Return a run-artifact command line that meets the refusal ``case`` names."""
    artifact, book = _artifact(tmp_path)
    spec = _spec(tmp_path, [{"alias": "bel", "kind": "Sum", "column": "pv"}])
    folding = [str(artifact), str(book), "--engine", "folding"]
    if case == "book":
        book.write_bytes(b"not parquet")
    if case == "spec":
        spec.write_text("not json at all")
    if case == "inception":
        artifact.write_text(json.dumps(_from_inception(reads_the_schedule=False)))
        pl.DataFrame(
            {"policy_id": [1], "policy_inception": [None], "premium": [1.0]}
        ).write_parquet(book)
        spec = _spec(tmp_path, [{"alias": "bel", "kind": "Sum", "column": "cf"}])
    aggregate = ["--aggregate", str(spec)]
    return {
        "align": [*folding, "--align", "calendar"],
        "book": folding,
        "engine": [str(artifact), str(book), "--engine", "no-such-engine"],
        "rows and totals": [*folding, *aggregate, "--every-node"],
        "misspelled align": [*folding, *aggregate, "--align", "months"],
        "spec": [*folding, *aggregate],
        "inception": [*folding, *aggregate],
    }[case]


@pytest.mark.parametrize(
    ("case", "status", "sentence"),
    [
        ("align", 2, "there is no --aggregate here"),
        ("book", 2, "could not be read as a book"),
        ("engine", 2, "No engine named 'no-such-engine' is known here"),
        ("rows and totals", 2, "ask for one of the two"),
        ("misspelled align", 2, "--align is 'calendar' or 'duration'"),
        ("spec", 2, "could not be read as a list of aggregators"),
        ("inception", 1, "DURATION"),
    ],
)
@pytest.mark.usefixtures("folding")
def test_run_artifact_refuses_on_stderr(
    tmp_path: Path, case: str, status: int, sentence: str
) -> None:
    result = runner.invoke(app, ["run-artifact", *_run_artifact(tmp_path, case)])

    _refused_on_stderr(result, status, sentence)


# --- calc-graph ------------------------------------------------------------


def _calc_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> list[str]:
    """Return a calc-graph command line that meets the refusal ``case`` names."""
    model, points = _model_and_points(tmp_path)
    written = ["-o", str(tmp_path / "graph.json")]
    exported = GraphExporter.export

    def without_a_tier(self: GraphExporter, *args: object, **kwargs: object) -> str:
        document = json.loads(exported(self, *args, **kwargs))
        for node in document["nodes"]:
            if node["kind"] == "computed":
                node["tier"] = None
        return json.dumps(document)

    def broken(*_args: object, **_kwargs: object) -> str:
        message = "the exporter broke"
        raise RuntimeError(message)

    if case == "model":
        model.write_text(FAILING_MODEL_SRC)
    if case == "tier":
        monkeypatch.setattr(GraphExporter, "export", without_a_tier)
    if case == "export":
        monkeypatch.setattr(GraphExporter, "export", broken)
    if case == "page":
        monkeypatch.setitem(sys.modules, "gaspatchio_viewer", None)
    scenarios = tmp_path / "scenarios.py"
    scenarios.write_text("")
    return {
        "scenarios": [*written, "--scenarios", str(scenarios), "--portfolio"],
        "policy": [*written, "--policies", "NOT-A-POLICY"],
        "model": written,
        "ceiling": [*written, "--max-size", "10"],
        "tier": written,
        "export": written,
        "page": [*written, "--html", str(tmp_path / "graph.html")],
    }[case] + [str(model), str(points)]


@pytest.mark.parametrize(
    ("case", "status", "sentence"),
    [
        ("scenarios", 3, "--scenarios already folds the book"),
        ("policy", 3, "NOT-A-POLICY"),
        ("model", 1, "Error running model"),
        ("ceiling", 3, "--max-size"),
        ("tier", 1, "is a calculation and carries no tier"),
        ("export", 1, "Unexpected error building graph"),
        ("page", 2, 'pip install "gaspatchio[viewer]"'),
    ],
)
def test_calc_graph_refuses_on_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    status: int,
    sentence: str,
) -> None:
    arguments = _calc_graph(tmp_path, monkeypatch, case)

    result = runner.invoke(app, ["calc-graph", *arguments])

    _refused_on_stderr(result, status, sentence)


# --- run-model -------------------------------------------------------------


def test_run_model_refuses_every_node_without_the_frame_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that hands back no frame has no log to name every node from."""
    model, points = _model_and_points(tmp_path)
    ran = cli.run_model_func

    def without_the_frame(*args: object, **kwargs: object) -> object:
        return ran(*args, **kwargs).model_copy(update={"frame": None})

    monkeypatch.setattr(cli, "run_model_func", without_the_frame)

    result = runner.invoke(
        app,
        [
            "run-model",
            str(model),
            str(points),
            "--every-node",
            "--results",
            str(tmp_path / "results.parquet"),
        ],
    )

    _refused_on_stderr(result, 2, "did not hand back the frame it finished on")


def test_run_model_says_on_stderr_that_a_manifest_could_not_be_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The results are saved, and why they carry no manifest is stderr's."""
    model, points = _model_and_points(tmp_path)

    def broken(*_args: object, **_kwargs: object) -> object:
        message = "the manifest broke"
        raise RuntimeError(message)

    monkeypatch.setattr(cli, "_final_schema_manifest", broken)
    results = tmp_path / "results.parquet"

    result = runner.invoke(
        app, ["run-model", str(model), str(points), "--results", str(results)]
    )

    _refused_on_stderr(result, 0, "Saved without a manifest: building it failed")
    assert results.is_file()


# --- run-single-policy -----------------------------------------------------


@pytest.mark.parametrize(
    ("book", "asked", "flag", "sentence"),
    [
        # A workbook's scenario column and a variant label are not read as a
        # policy identity by guess: the refusal names what was looked for,
        # what the book holds, and the flag that names the column.
        ({"scenario": ["BASE", "Lapse Shock"]}, "BASE", [], "--policy-id-column"),
        ({"variant_id": ["v1", "v2"]}, "v1", [], "['variant_id', 'sum_assured']"),
        ({"scenario": ["BASE"]}, "BASE", [], "looked for ['policy_id'"),
        ({"policy_id": ["A"]}, "B", [], "Policy ID 'B' not found"),
        ({"policy_id": ["A"]}, "A", ["--policy-id-column", "nope"], "'nope' not found"),
    ],
)
def test_run_single_policy_refuses_a_policy_it_cannot_find_on_stderr(
    tmp_path: Path,
    book: dict[str, list[str]],
    asked: str,
    flag: list[str],
    sentence: str,
) -> None:
    """No identifier column, or an id it does not hold, is a refusal, not a stack.

    The model never started, so the status is calc-graph's for a selection
    that names nothing, and the sentence is on stderr with nothing of a
    traceback through the runner around it.
    """
    model, _ = _model_and_points(tmp_path)
    points = tmp_path / "book.parquet"
    rows = len(next(iter(book.values())))
    pl.DataFrame({**book, "sum_assured": [100_000.0] * rows}).write_parquet(points)

    result = runner.invoke(
        app, ["run-single-policy", str(model), str(points), asked, *flag]
    )

    _refused_on_stderr(result, 3, sentence)
    assert "Traceback" not in result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)


# --- docs and knowledge ----------------------------------------------------


@pytest.mark.parametrize(
    ("command", "method"), [("docs", "search_docs"), ("knowledge", "search_knowledge")]
)
def test_a_search_the_api_cannot_answer_is_refused_on_stderr(
    monkeypatch: pytest.MonkeyPatch, command: str, method: str
) -> None:
    client = MagicMock()
    getattr(client, method).side_effect = APIConnectionError("API unavailable")
    monkeypatch.setattr(cli, "KnowledgeAPIClient", MagicMock(return_value=client))

    result = runner.invoke(app, [command, "reserves"])

    _refused_on_stderr(result, 1, "API unavailable")
