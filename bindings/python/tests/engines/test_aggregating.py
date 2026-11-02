# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Folding on a second engine: the seam, the two doors, and what they leave behind.

``run_aggregated(engine=...)`` and ``gspio run-artifact --aggregate`` hand the
executable artifact, the book and the caller's own aggregators to an engine
that folds. Every test here runs with no engine installed -- a stub
stands in for one -- because what is under test is the door: what the engine
is handed, what is refused before it is asked, and what the audit record says
about totals that arrive without their rows.

The engine's own arithmetic is held to Polars, to 1e-12 of each line's scale,
in the engine's suite.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from importlib import import_module
from pathlib import Path as PathType
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

import gaspatchio.engines.aggregation as door
from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.engines import register_engine
from gaspatchio.engines.aggregation import AggregatingEngine, aggregating
from gaspatchio.engines.protocol import NodeStatus, Producer
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.scenarios import (
    ArgMax,
    Count,
    Mean,
    PeriodSum,
    Sum,
    parse_aggregations,
    run_aggregated,
)
from gaspatchio.scenarios._aggregated import (
    AggregatedResult,
    _check_document_origin,
)
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# By module path, for the reason test_format.py gives: a package re-export
# can shadow a module of the same name.
_aggregated = import_module("gaspatchio.scenarios._aggregated")
_fold = import_module("gaspatchio.scenarios._fold")
_metric = import_module("gaspatchio.scenarios._metric")
_period = import_module("gaspatchio.scenarios._period_aggregators")

VERSIONS = {"engine_version": "0.0.0-test", "jax_version": "none"}


def _book() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "policy_id": [1, 2, 3, 4],
            "product": ["A", "A", "B", "B"],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af.pv = af.value * 2
    return af


@dataclass
class _FoldingEngine:
    """An engine handed the answer in advance, so the door can be tested alone."""

    name: str = "folding"
    version: str = "0.0.0-test"
    asked: dict[str, Any] | None = None

    def validate_tree(self, document: dict[str, object]) -> tuple[NodeStatus, ...]:  # noqa: ARG002 -- the protocol's parameter
        return ()

    def run(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError  # never reached by the fold doors

    def aggregate(
        self,
        document: dict[str, object],
        inputs: pl.DataFrame,
        aggregations: list[Any],
        *,
        batch: int | None = None,
    ) -> AggregatedResult:
        self.asked = {
            "document": document,
            "inputs": inputs,
            "aggregations": aggregations,
            "batch": batch,
        }
        return AggregatedResult(
            aggregations={
                door.alias_of(one): float(len(aggregations)) for one in aggregations
            },
            n_policies=inputs.height,
            n_periods=0,
            batch_size=batch or inputs.height,
            wall_time_s=0.0,
            peak_rss_mb=None,
            produced_by=Producer(
                engine=self.name,
                versions=dict(VERSIONS),
                graph_fingerprint=str(document["graph_fingerprint"]),
                inputs_digest="sha256:" + "cd" * 32,
                notes=("batching: 1 batches in 1 horizon groups",),
            ),
        )


class _RunningEngine:
    """An engine that runs a model and cannot fold one."""

    name = "running"
    version = "0.0.0-test"

    def validate_tree(self, document: dict[str, object]) -> tuple[NodeStatus, ...]:  # noqa: ARG002 -- the protocol's parameter
        return ()

    def run(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError


# ---------------------------------------------------------------------------
# The door an engine reads the aggregation contract through
# ---------------------------------------------------------------------------


def test_every_name_the_door_publishes_is_the_producer_s_own() -> None:
    assert door.AggregatedResult is _aggregated.AggregatedResult
    assert door.fold_per_policy is _aggregated._fold_per_policy  # noqa: SLF001 -- identity is the point
    assert door.alias_of is _aggregated._alias_of  # noqa: SLF001
    assert door.reject_scenario_axis_only is _aggregated._reject_scenario_axis_only  # noqa: SLF001
    assert door.reject_multi_level_over is _aggregated._reject_multi_level_over  # noqa: SLF001
    assert door.extract_outputs is _fold._extract_outputs  # noqa: SLF001
    assert door.inner_of is _fold._inner  # noqa: SLF001
    assert door.Partitioned is _metric._Partitioned  # noqa: SLF001
    for name in (
        "PeriodCount",
        "PeriodMax",
        "PeriodMean",
        "PeriodMin",
        "PeriodStd",
        "PeriodSum",
        "PeriodVariance",
    ):
        assert getattr(door, name) is getattr(_period, name), name
    assert [name for name in door.__all__ if not hasattr(door, name)] == []


def test_the_door_s_fold_is_the_per_policy_half_and_refuses_a_per_period_kind() -> None:
    """An engine cannot ask Polars for per-period partials through the door.

    The door's fold is the Polars path's own per-policy fold, and the Polars
    batch fold still uses it -- so the two answer alike -- but a per-period
    kind, whose partial the Polars path would explode and group, is refused
    before anything is folded.
    """
    frame = pl.DataFrame(
        {"pv": [1.0, 2.0, 3.0], "g": ["a", "a", "b"], "cf": [[1.0], [2.0], [3.0]]}
    )
    aggregations = [Sum("pv").alias("total"), Sum("pv").alias("by_g").over("g")]
    through_door: dict[str, Any] = {
        door.alias_of(one): one.create_accumulator() for one in aggregations
    }
    through_polars: dict[str, Any] = {
        door.alias_of(one): one.create_accumulator() for one in aggregations
    }
    door.fold_per_policy(frame, aggregations, through_door)
    _aggregated._fold_batch(frame, aggregations, through_polars)  # noqa: SLF001 -- the Polars path
    assert (
        door.extract_outputs(["total", "by_g"], aggregations, through_door)["total"]
        == 6.0
    )
    assert through_door["total"] == through_polars["total"]
    assert through_door["by_g"].keys() == through_polars["by_g"].keys()

    mixed = [Sum("pv").alias("total"), PeriodSum("cf").alias("cf")]
    held = {door.alias_of(one): one.create_accumulator() for one in mixed}
    with pytest.raises(TypeError, match="PeriodSum folds one value per period"):
        door.fold_per_policy(frame, mixed, held)
    # Refused before anything was folded: the per-policy total is untouched.
    assert held["total"] == Sum("pv").create_accumulator()


def test_discovering_an_engine_does_not_load_the_aggregation_door() -> None:
    code = (
        "import gaspatchio, gaspatchio.engines, gaspatchio.cli, sys; "
        "print('gaspatchio.engines.aggregation' in sys.modules)"
    )
    out = subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.strip() == "False"


def test_an_engine_that_folds_is_taken_at_its_word() -> None:
    engine = _FoldingEngine()
    taken: AggregatingEngine = aggregating(engine, "folding")
    assert taken is engine


def test_an_engine_that_cannot_fold_is_refused_by_name() -> None:
    with pytest.raises(EngineRefusal) as refused:
        aggregating(_RunningEngine(), "running")
    report = refused.value.report
    # No clause: the specification leaves every aggregate out of the artifact.
    assert [(one.group, one.where, one.clause) for one in report.refusals] == [
        ("tree", "running", None)
    ]
    assert "aggregate" in report.refusals[0].what
    assert report.closing_sentence() == "Nothing was computed."


# ---------------------------------------------------------------------------
# The core door: run_aggregated with an engine named
# ---------------------------------------------------------------------------


def test_the_engine_is_handed_the_artifact_the_book_and_the_aggregators() -> None:
    engine = _FoldingEngine()
    register_engine("folding", lambda: engine)
    book = _book()
    aggregations = [Sum("pv").alias("bel"), PeriodSum("pv").alias("ignored")]

    result = run_aggregated(_model, book, aggregations, engine="folding")

    assert engine.asked is not None
    document = engine.asked["document"]
    assert document["profile"] == "executable"
    assert (
        document["graph_fingerprint"]
        == _model(ActuarialFrame(book)).graph.fingerprint()
    )
    # The book the frame door hands an engine: the columns the frame arrived
    # with, as the document's input nodes name them -- one method for both.
    _document, frame_door_inputs = _model(ActuarialFrame(book))._for_an_engine()  # noqa: SLF001 -- the door under test
    assert engine.asked["inputs"].equals(frame_door_inputs)
    assert engine.asked["inputs"].select(book.columns).equals(book)
    assert all(
        one is two
        for one, two in zip(engine.asked["aggregations"], aggregations, strict=True)
    )
    # "auto" leaves the batch to the engine.
    assert engine.asked["batch"] is None
    assert result.bel == 2.0
    assert result.produced_by is not None
    assert result.produced_by.engine == "folding"
    # The door's own wall, not the engine's: the engine answered 0.0.
    assert result.wall_time_s > 0.0


def test_an_integer_batch_size_becomes_the_engine_s_batch() -> None:
    engine = _FoldingEngine()
    register_engine("folding", lambda: engine)
    result = run_aggregated(
        _model, _book(), [Sum("pv").alias("bel")], batch_size=3, engine="folding"
    )
    assert engine.asked is not None
    assert engine.asked["batch"] == 3
    assert result.batch_size == 3


def test_an_engine_that_cannot_fold_is_refused_before_the_model_is_built() -> None:
    register_engine("running", _RunningEngine)
    built: list[bool] = []

    def model(af: ActuarialFrame) -> ActuarialFrame:
        built.append(True)
        return _model(af)

    with pytest.raises(EngineRefusal, match="running"):
        run_aggregated(model, _book(), [Sum("pv").alias("bel")], engine="running")
    assert built == []


def test_an_empty_book_is_refused_as_polars_refuses_it_before_any_engine_is_found() -> (
    None
):
    empty = _book().clear()
    for engine in (None, "no-such-engine"):
        with pytest.raises(ValueError, match="model_points is empty"):
            run_aggregated(_model, empty, [Sum("pv").alias("bel")], engine=engine)


@pytest.mark.parametrize(
    "refused",
    [
        Count("pv").alias("n"),
        ArgMax("pv").alias("worst"),
        Sum.of(pl.lit(1)).alias("of"),
    ],
    ids=["Count", "ArgMax", "of"],
)
def test_the_policy_axis_refuses_the_same_aggregators_whichever_engine(
    refused: Any,  # noqa: ANN401 -- an aggregator of any kind
) -> None:
    engine = _FoldingEngine()
    register_engine("folding", lambda: engine)
    refusal = "run_aggregated|policy axis"
    with pytest.raises(ValueError, match=refusal) as on_polars:
        run_aggregated(_model, _book(), [refused])
    with pytest.raises(ValueError, match=refusal) as on_engine:
        run_aggregated(_model, _book(), [refused], engine="folding")
    assert str(on_engine.value) == str(on_polars.value)
    assert engine.asked is None


def test_an_inception_aligned_model_is_refused_on_an_engine_as_on_polars() -> None:
    engine = _FoldingEngine()
    register_engine("folding", lambda: engine)

    @dataclass
    class _Schedule:
        _kind: str

    def model(af: ActuarialFrame) -> ActuarialFrame:
        out = _model(af)
        object.__setattr__(out, "_projection", _Schedule("from_inception"))
        return out

    with pytest.raises(ValueError, match="DURATION"):
        run_aggregated(model, _book(), [Sum("pv").alias("bel")], engine="folding")
    assert engine.asked is None


def test_the_audit_record_names_the_engine_and_every_version_it_ran_under(
    tmp_path: Path,
) -> None:
    engine = _FoldingEngine()
    register_engine("folding", lambda: engine)
    aggregations = [Sum("pv").alias("bel"), Mean("pv").alias("average").over("product")]

    on_engine = run_aggregated(
        _model, _book(), aggregations, engine="folding", audit=tmp_path / "engine.json"
    )
    on_polars = run_aggregated(
        _model, _book(), aggregations, audit=tmp_path / "polars.json"
    )

    assert on_engine.audit_path == tmp_path / "engine.json"
    record = json.loads((tmp_path / "engine.json").read_text())
    polars_record = json.loads((tmp_path / "polars.json").read_text())
    metadata = record["run_metadata"]
    assert metadata["engine"] == "folding"
    assert metadata["engine_versions"] == VERSIONS
    assert metadata["inputs_digest"] == "sha256:" + "cd" * 32
    assert metadata["engine_notes"] == ["batching: 1 batches in 1 horizon groups"]
    # The same recipe and the same graph, so the two records are of one run.
    assert record["source_sha"] == polars_record["source_sha"]
    assert record["graph_fingerprint"] == polars_record["graph_fingerprint"]
    assert record["input_data_fingerprint"] == polars_record["input_data_fingerprint"]
    # And the Polars record is exactly what it was: no engine keys.
    assert not {"engine", "engine_versions", "inputs_digest", "engine_notes"} & set(
        polars_record["run_metadata"]
    )
    assert on_polars.produced_by is None


def test_a_document_is_refused_for_inception_alignment_as_a_frame_is() -> None:
    inception = {
        "assumptions": [{"kind": "schedule", "payload": {"kind": "from_inception"}}]
    }
    grid = {
        "assumptions": [{"kind": "schedule", "payload": {"kind": "per_policy_grid"}}]
    }
    with pytest.raises(ValueError, match="DURATION"):
        _check_document_origin(inception, None)
    with pytest.raises(ValueError, match="DURATION"):
        _check_document_origin(inception, "calendar")
    _check_document_origin(inception, "duration")
    _check_document_origin(grid, None)
    _check_document_origin({}, None)


def _from_inception(*, reads_the_schedule: bool) -> dict[str, Any]:
    """Return the executable artifact of a model projected from each inception."""
    book = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "policy_inception": [date(2020, 3, 1), date(2021, 7, 1)],
            "premium": [100.0, 200.0],
        }
    )
    af = ActuarialFrame(book)
    af = af.projection.set(
        schedule=Schedule.from_inception(
            inception_column="policy_inception", n_periods=6, frequency="1M"
        )
    )
    af.cf = af.premium * 1.0
    if reads_the_schedule:
        af.t = af.projection.t_years()
    document: dict[str, Any] = json.loads(
        GraphExporter(af).export(profile="executable", include_source=False)
    )
    return document


@pytest.mark.parametrize(
    "reads_the_schedule", [True, False], ids=["reads-it", "never-reads-it"]
)
def test_an_inception_aligned_artifact_is_refused_whether_or_not_it_reads_its_schedule(
    *, reads_the_schedule: bool
) -> None:
    """The schedule's payload travels only when a node reads it; the axis always does.

    A from_inception model that never reads its schedule carries no schedule
    entry at all, and a guard that looked only there passed it -- to be
    summed by index across policies whose indices are durations.
    """
    document = _from_inception(reads_the_schedule=reads_the_schedule)
    carried = [
        entry
        for entry in document.get("assumptions") or []
        if entry.get("kind") == "schedule"
    ]
    assert bool(carried) is reads_the_schedule
    with pytest.raises(ValueError, match="DURATION"):
        _check_document_origin(document, None)
    _check_document_origin(document, "duration")


def test_a_calendar_axis_is_not_mistaken_for_an_inception_one() -> None:
    book = pl.DataFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})
    for configure in (
        lambda af: af.projection.set(
            schedule=Schedule.from_calendar_grid(
                start_date=date(2024, 1, 31), n_periods=6, frequency="1M"
            )
        ),
        lambda af: af.projection.set(
            start_date=date(2024, 1, 31), n_periods=6, frequency="monthly"
        ),
        lambda af: af.projection.set(
            valuation_date=date(2024, 1, 1),
            until="term_months",
            until_value=6,
            frequency="monthly",
        ),
    ):
        af = configure(ActuarialFrame(book))
        af.cf = af.premium * 1.0
        _check_document_origin(
            json.loads(GraphExporter(af).export(profile="executable")), None
        )


# ---------------------------------------------------------------------------
# The spec: canonical forms, an alias, and over
# ---------------------------------------------------------------------------


def test_over_partitions_an_entry_as_the_method_does() -> None:
    parsed = parse_aggregations(
        [
            {"kind": "Sum", "alias": "bel", "column": "pv"},
            {"kind": "PeriodSum", "alias": "cf", "column": "cf", "over": "product"},
            {"kind": "Mean", "alias": "m", "column": "pv", "over": ["product", "sex"]},
        ]
    )
    assert parsed[0] == Sum("pv").alias("bel")
    assert parsed[1] == PeriodSum("cf").alias("cf").over("product")
    assert parsed[2] == Mean("pv").alias("m").over(("product", "sex"))


def test_a_spec_is_the_canonical_form_beside_its_alias() -> None:
    aggregations = [Sum("pv").alias("bel"), PeriodSum("cf").alias("cf")]
    written = [
        {**one.canonical_form(), "alias": door.alias_of(one)} for one in aggregations
    ]
    assert list(parse_aggregations(written)) == aggregations


@pytest.mark.parametrize(
    ("entry", "said"),
    [
        ("Sum", "must be an object"),
        ({"alias": "p", "kind": "_Partitioned", "by": ["g"]}, "carries 'by'"),
        (
            {"alias": "p", "kind": "_Partitioned", "inner": {"kind": "Sum"}},
            "carries 'by'",
        ),
    ],
    ids=["not-an-object", "no-inner", "no-by"],
)
def test_a_malformed_recipe_is_a_value_error_naming_what_is_wrong(
    entry: object, said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        parse_aggregations([entry])  # type: ignore[list-item]


def test_over_names_columns_and_nothing_else() -> None:
    with pytest.raises(ValueError, match="over"):
        parse_aggregations([{"kind": "Sum", "alias": "b", "column": "pv", "over": 3}])


# ---------------------------------------------------------------------------
# The file door: gspio run-artifact --aggregate
# ---------------------------------------------------------------------------


def _artifact(tmp_path: Path) -> tuple[Path, Path]:
    book = _book()
    af = _model(ActuarialFrame(book))
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        GraphExporter(af).export(profile="executable", include_source=False)
    )
    written = tmp_path / "book.parquet"
    book.write_parquet(written)
    return artifact, written


def _spec(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(entries))
    return spec


def test_the_file_door_writes_the_totals_and_the_record_that_places_them(
    tmp_path: Path,
) -> None:
    engine = _FoldingEngine()
    register_engine("folding", lambda: engine)
    artifact, book = _artifact(tmp_path)
    spec = _spec(
        tmp_path,
        [
            {"alias": "bel", "kind": "Sum", "column": "pv"},
            {"alias": "by_product", "kind": "Sum", "column": "pv", "over": ["product"]},
        ],
    )
    out = tmp_path / "totals.json"

    finished = runner.invoke(
        app,
        [
            "run-artifact",
            str(artifact),
            str(book),
            "--engine",
            "folding",
            "--aggregate",
            str(spec),
            "--results",
            str(out),
        ],
    )

    assert finished.exit_code == 0, finished.output
    assert "Aggregates saved to" in finished.output
    record = json.loads(out.read_text())
    document = json.loads(artifact.read_text())
    assert record["aggregator_outputs"] == {"bel": 2.0, "by_product": 2.0}
    assert record["aggregator_identity"]["by_product"] == {
        "kind": "_Partitioned",
        "by": ["product"],
        "inner": {"kind": "Sum", "column": "pv", "within": "sum"},
    }
    assert record["graph_fingerprint"] == document["graph_fingerprint"]
    assert record["run_metadata"]["engine"] == "folding"
    assert record["run_metadata"]["engine_versions"] == VERSIONS
    assert engine.asked is not None
    assert engine.asked["batch"] is None


def test_the_file_door_refuses_rows_and_totals_asked_for_together(
    tmp_path: Path,
) -> None:
    register_engine("folding", _FoldingEngine)
    artifact, book = _artifact(tmp_path)
    spec = _spec(tmp_path, [{"alias": "bel", "kind": "Sum", "column": "pv"}])
    finished = runner.invoke(
        app,
        [
            "run-artifact",
            str(artifact),
            str(book),
            "--engine",
            "folding",
            "--aggregate",
            str(spec),
            "--every-node",
        ],
    )
    assert finished.exit_code == 2, finished.output
    assert "--every-node" in finished.output


def test_the_file_door_refuses_an_engine_that_cannot_fold_and_prints_why(
    tmp_path: Path,
) -> None:
    register_engine("running", _RunningEngine)
    artifact, book = _artifact(tmp_path)
    spec = _spec(tmp_path, [{"alias": "bel", "kind": "Sum", "column": "pv"}])
    out = tmp_path / "totals.json"
    finished = runner.invoke(
        app,
        [
            "run-artifact",
            str(artifact),
            str(book),
            "--engine",
            "running",
            "--aggregate",
            str(spec),
            "--results",
            str(out),
        ],
    )
    assert finished.exit_code == 1, finished.output
    assert "Nothing was computed." in finished.output
    assert not out.exists()


@pytest.mark.parametrize(
    "written",
    [
        "not json at all",
        json.dumps([{"alias": "bel", "kind": "NoSuchKind", "column": "pv"}]),
        json.dumps({"bel": {"kind": "Sum", "column": "pv"}}),
        json.dumps(["Sum"]),
        json.dumps([{"alias": "bel", "kind": "_Partitioned", "by": ["product"]}]),
    ],
    ids=[
        "unreadable",
        "unregistered-kind",
        "not-a-list",
        "an-entry-that-is-not-an-object",
        "a-partitioned-entry-without-inner",
    ],
)
def test_the_file_door_refuses_a_spec_it_cannot_read(
    tmp_path: Path, written: str
) -> None:
    register_engine("folding", _FoldingEngine)
    artifact, book = _artifact(tmp_path)
    spec = tmp_path / "spec.json"
    spec.write_text(written)
    finished = runner.invoke(
        app,
        [
            "run-artifact",
            str(artifact),
            str(book),
            "--engine",
            "folding",
            "--aggregate",
            str(spec),
        ],
    )
    assert finished.exit_code == 2, finished.output
    assert "list of aggregators" in finished.output


def test_the_file_door_guards_an_inception_aligned_artifact_as_the_frame_does(
    tmp_path: Path,
) -> None:
    engine = _FoldingEngine()
    register_engine("folding", lambda: engine)
    artifact, book = _artifact(tmp_path)
    document = json.loads(artifact.read_text())
    document["assumptions"] = [
        *document.get("assumptions", []),
        {"kind": "schedule", "payload": {"kind": "from_inception"}},
    ]
    artifact.write_text(json.dumps(document))
    spec = _spec(tmp_path, [{"alias": "bel", "kind": "Sum", "column": "pv"}])
    common = [
        "run-artifact",
        str(artifact),
        str(book),
        "--engine",
        "folding",
        "--aggregate",
        str(spec),
        "--results",
        str(tmp_path / "totals.json"),
    ]

    refused = runner.invoke(app, common)
    assert refused.exit_code == 1, refused.output
    assert "DURATION" in refused.output
    assert engine.asked is None

    by_duration = runner.invoke(app, [*common, "--align", "duration"])
    assert by_duration.exit_code == 0, by_duration.output
    assert engine.asked is not None

    misspelled = runner.invoke(app, [*common, "--align", "months"])
    assert misspelled.exit_code == 2, misspelled.output


def test_the_file_door_refuses_an_inception_aligned_artifact_that_never_reads_it(
    tmp_path: Path,
) -> None:
    engine = _FoldingEngine()
    register_engine("folding", lambda: engine)
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps(_from_inception(reads_the_schedule=False)))
    book = tmp_path / "book.parquet"
    pl.DataFrame(
        {
            "policy_id": [1, 2],
            "policy_inception": [date(2020, 3, 1), date(2021, 7, 1)],
            "premium": [100.0, 200.0],
        }
    ).write_parquet(book)
    spec = _spec(tmp_path, [{"alias": "bel", "kind": "Sum", "column": "cf"}])
    finished = runner.invoke(
        app,
        [
            "run-artifact",
            str(artifact),
            str(book),
            "--engine",
            "folding",
            "--aggregate",
            str(spec),
            "--results",
            str(tmp_path / "totals.json"),
        ],
    )
    assert finished.exit_code == 1, finished.output
    assert "DURATION" in finished.output
    assert engine.asked is None


def test_align_without_aggregate_is_a_usage_error(tmp_path: Path) -> None:
    register_engine("folding", _FoldingEngine)
    artifact, book = _artifact(tmp_path)
    finished = runner.invoke(
        app,
        [
            "run-artifact",
            str(artifact),
            str(book),
            "--engine",
            "folding",
            "--align",
            "duration",
            "--results",
            str(tmp_path / "rows.parquet"),
        ],
    )
    assert finished.exit_code == 2, finished.output
    assert "--align" in finished.output
    assert not (tmp_path / "rows.parquet").exists()


def test_the_record_is_written_whole_or_not_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record is renamed into place, so a reader never meets half of one.

    A write that fails part way leaves whatever stood at the path before --
    here an earlier record -- and no working file beside it.
    """
    engine = _FoldingEngine()
    register_engine("folding", lambda: engine)
    destination = tmp_path / "record.json"
    run_aggregated(
        _model, _book(), [Sum("pv").alias("bel")], engine="folding", audit=destination
    )
    first = destination.read_text()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["record.json"]

    written = PathType.write_text

    def half_written(self: PathType, data: str, *args: Any, **kwargs: Any) -> int:  # noqa: ANN401 -- write_text's own signature
        if not self.name.endswith(".unpublished"):
            return written(self, data, *args, **kwargs)
        written(self, data[: len(data) // 2], *args, **kwargs)
        message = "the disk filled"
        raise OSError(message)

    monkeypatch.setattr(PathType, "write_text", half_written)
    with pytest.raises(OSError, match="the disk filled"):
        run_aggregated(
            _model,
            _book(),
            [Sum("pv").alias("bel")],
            engine="folding",
            audit=destination,
        )
    assert destination.read_text() == first
    assert sorted(path.name for path in tmp_path.iterdir()) == ["record.json"]
