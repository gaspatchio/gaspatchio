# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Levels 4 and 5 end to end, against the producer's own every-node answers.

The two shipped models, at a thousand policies each, through this engine and
through Polars, compared node by node under the agreement rule. This is the
engine's acceptance and it is a *measurement*: what is asserted is that every
value-bearing node the artifact carries is in both results and that every line
agrees, and the run prints the compared set's size and the worst ratio so a
reader of the log has the number rather than a claim about it.

**The reference is taken fresh, and the command is named.** From
``bindings/python``'s own model file through the engine venv's own ``gspio``::

    gspio run-model --every-node <tutorial model.py> <model_points_1k.parquet> -o <file>

That writes one column per value-bearing node, keyed by node id -- two
accounts of one column are two columns -- with the result manifest in the
Parquet file's own metadata. The frozen exports under ``viewer/fixtures`` are
deliberately not regenerated and are never read here.

**The compared set is computed from the artifact, never listed here.** A test
that hard-coded a column list would pass while the engine quietly stopped
answering for a node the artifact carries.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.engines import engine_named
from gaspatchio.engines.compare import compare_results
from gaspatchio.engines.protocol import VALUE_BEARING, FrameSink, read_manifest
from tests.conftest import JAGGED_POLICIES, PROJECT
from tests.helpers import Watched

if TYPE_CHECKING:
    from gaspatchio.engines.protocol import ResultManifest

MODELS = PROJECT / "tests/models"
GSPIO = PROJECT / ".venv/bin/gspio"

# The reference is taken with the **core** venv, from ``bindings/python``, on
# the tutorials in the tree -- which is the command the acceptance names, and
# the only one whose fingerprint guard guards anything: the wheel inside this
# project's venv carries a frozen copy of the tutorials, so a reference taken
# from it would agree with the committed artifact for ever, including after
# the tree's model had moved out from under it.
CORE = PROJECT.parents[1] / "bindings/python"
CORE_GSPIO = CORE / ".venv/bin/gspio"
TUTORIALS = Path("gaspatchio/tutorials")

# The tutorial each committed artifact was exported from, and the book both
# sides read. Named here so a reference taken at test time is taken from the
# model the artifact is of.
FOLDER = {"level-4": "level-4-lifelib", "level-5": "level-5-scenarios"}
BOOK = "model_points_1k.parquet"

# What the two artifacts carry, measured at the keyboard and stated so that a
# model that quietly shrank fails here rather than passing on a smaller set.
NODES = {"level-4": 128, "level-5": 125}


def _tutorials() -> Path:
    """Return the tutorials as the tree carries them, not as a wheel froze them."""
    return CORE / TUTORIALS


def value_bearing_node_ids(document: dict[str, object]) -> set[str]:
    """Return every node id an ``every-node`` result is required to carry.

    Computed from the artifact rather than listed: an input node, a computed
    one and a compiled rollforward's extracted balance are values, and a bare
    rollforward structural node is one compilation that every extraction from
    it reads rather than a value of its own.
    """
    return {
        str(node["id"])
        for node in document.get("nodes") or []
        if isinstance(node, dict) and node.get("kind") in VALUE_BEARING
    }


@pytest.fixture(scope="module")
def references(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Return each model's fresh every-node Polars answers, by node id."""
    written = tmp_path_factory.mktemp("references")
    tutorials = _tutorials()
    for model, folder in FOLDER.items():
        out = written / f"{model}.parquet"
        finished = subprocess.run(  # noqa: S603 -- the core's own venv and tutorials
            [
                str(CORE_GSPIO),
                "run-model",
                "--every-node",
                str(tutorials / folder / "base/model.py"),
                str(tutorials / folder / "base" / BOOK),
                "-o",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
            cwd=CORE,
        )
        assert finished.returncode == 0, finished.stdout + finished.stderr
        assert out.exists()
    return {model: written / f"{model}.parquet" for model in FOLDER}


def _artifact(model: str) -> dict[str, object]:
    """Return one committed executable artifact."""
    read: dict[str, object] = json.loads(
        (MODELS / f"{model}.artifact.json").read_text(encoding="utf-8")
    )
    return read


def _book(model: str) -> pl.DataFrame:
    """Return the thousand-policy book both sides read."""
    return pl.read_parquet(MODELS / f"{model}.book.parquet")


@pytest.mark.parametrize("model", ["level-4", "level-5"])
def test_the_compared_node_set_is_the_value_bearing_set_and_every_line_agrees(
    model: str, references: dict[str, Path]
) -> None:
    """Every value-bearing node of the artifact, on both engines, agreeing.

    And a **ratchet on the worst line**, not only on the rule's own bound. The
    rule admits anything inside 1e-12 and this run is four orders inside it, so a
    landing that moved a model's worst line from 2.5e-14 to 9e-13 would pass
    the clause and pass unnoticed. ``agreement.json``'s ``models`` section
    records which node is worst and by how much, with the reason; this asserts
    the tree still agrees with that record. A move needs the number changed
    there and a reason written beside it, which is the point.
    """
    artifact = _artifact(model)
    reference = pl.read_parquet(references[model])
    manifest: ResultManifest = read_manifest(references[model])
    result = engine_named("jax").run(
        artifact, _book(model), FrameSink(), every_node=True
    )
    expected_ids = value_bearing_node_ids(artifact)
    assert set(result.manifest.columns) == expected_ids
    assert set(manifest.columns) == expected_ids
    assert len(expected_ids) == NODES[model]
    report = compare_results(
        artifact,
        reference,
        result.columns,
        before_manifest=manifest,
        after_manifest=result.manifest,
    )
    assert report.missing == ()
    assert report.same_inputs
    disagreeing = [one for one in report.lines if one.verdict != "agree"]
    assert report.verdict == "agree", disagreeing
    at = max(report.lines, key=lambda line: line.max_ratio or 0.0)
    worst = at.max_ratio or 0.0
    print(  # noqa: T201 -- the measurement is the point of this test
        f"{model}: {len(report.lines)} lines, scope {report.scope}, rows by "
        f"{report.rows_matched_by}, worst ratio {worst:.6e} at {at.node_id} "
        f"(max_abs {at.max_abs:.6e}, scale {at.scale:.6e})"
    )
    assert worst < 1e-12
    recorded = _recorded_model_ratio(model)
    assert at.node_id == recorded["node"], (at.node_id, recorded["node"])
    assert worst <= recorded["ratio"], (worst, recorded["ratio"])


@pytest.mark.parametrize("model", ["level-4", "level-5"])
def test_the_change_report_names_this_engine_and_holds_its_moves_inside_the_band(
    model: str, references: dict[str, Path], tmp_path: Path
) -> None:
    """``gspio diff`` over one audit file and the two engines' results files.

    The comparison of two versions, read on the pair whose definitions are
    one: every line that moved moved under a definition that did not, the
    record names the producer as what moved under it, and every one of those
    moves is inside section 11.1.12's band -- the last places two correct
    implementations part in, labelled as such and never drift. Asked each way
    round, because a comparison that reads one way only is two comparisons.
    """
    from gaspatchio.engines.protocol import ParquetSink
    from gaspatchio.frame.graph import diff_with_results

    artifact = _artifact(model)
    out = tmp_path / "jax.parquet"
    engine_named("jax").run(artifact, _book(model), ParquetSink(out), every_node=True)

    for before, after in ((references[model], out), (out, references[model])):
        report = diff_with_results(artifact, artifact, before, after)
        values = report.values
        assert values is not None
        moved = [line for line in values.lines if line.moved]
        assert report.calculations == ()
        assert values.rows.paired == _book(model).height
        assert values.cause == "producer"
        # Now that every product is rounded before it is read, the two
        # engines answer these models to the bit on darwin;
        # where a platform's maths call parts them by a place, the move is the
        # producer's and inside the band.
        assert all(line.change is None for line in moved)
        assert all(line.within_band is True for line in moved), [
            (line.node, line.max_relative) for line in moved if not line.within_band
        ]
        assert report.drift is False


def _recorded_model_ratio(model: str) -> dict[str, object]:
    """Return what ``agreement.json`` records as this model's worst line."""
    read: dict[str, dict[str, dict[str, object]]] = json.loads(
        (PROJECT / "agreement.json").read_text(encoding="utf-8")
    )
    return read["models"][model]


@pytest.mark.parametrize("model", ["level-4", "level-5"])
def test_the_file_door_runs_the_same_model_in_a_fresh_process(
    model: str, tmp_path: Path
) -> None:
    """``gspio run-artifact --engine jax``, with nothing imported beforehand.

    The final schema rather than every node: what the file door publishes is
    the model's own columns, and what this pins is that a whole shipped model
    reaches the engine through provider discovery and publishes a result with
    its manifest bound to the artifact.
    """
    out = tmp_path / f"{model}.parquet"
    finished = subprocess.run(  # noqa: S603 -- this project's own venv and fixtures
        [
            str(GSPIO),
            "run-artifact",
            str(MODELS / f"{model}.artifact.json"),
            str(MODELS / f"{model}.book.parquet"),
            "--engine",
            "jax",
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    published = pl.read_parquet(out)
    assert published.height == _book(model).height
    manifest = read_manifest(out)
    assert manifest.producer == "jax"
    assert manifest.scope == "final-schema"
    assert manifest.graph_fingerprint == _artifact(model)["graph_fingerprint"]
    # The book the artifact says it was built over, and the book the result
    # says it was produced over, are one digest by one rule: a filing and a
    # result are matched by the data they were made from, not by file names.
    book = _artifact(model)["book"]
    assert isinstance(book, dict)
    assert manifest.inputs_digest == book["digest"]


@pytest.mark.parametrize("model", ["level-4", "level-5"])
def test_the_frame_door_runs_the_same_model_in_a_fresh_process(
    model: str, tmp_path: Path
) -> None:
    """``af.collect(engine="jax")`` on the live tutorial frame, end to end.

    A fresh process again, and the model built by its own code rather than by
    this test: the frame door folds the executable document itself, and what
    it is handed is whatever the tutorial's ``main`` returns.
    """
    script = tmp_path / "frame_door.py"
    script.write_text(
        _FRAME_DOOR.format(folder=FOLDER[model], book=BOOK), encoding="utf-8"
    )
    finished = subprocess.run(  # noqa: S603 -- this project's own venv and fixtures
        [str(PROJECT / ".venv/bin/python"), str(script)],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    read = json.loads(finished.stdout.strip().splitlines()[-1])
    assert read["rows"] == _book(model).height
    assert read["columns"] > 0
    # Evidence the door went through the engine rather than round it: the
    # provider module is in the process only because discovery imported it,
    # and the engine's own name comes off the registered object rather than
    # out of the script.
    assert read["provider_imported"] is True
    assert read["registered"] == "jax"


_FRAME_DOOR = """
import importlib.util, json, sys
from pathlib import Path

import polars as pl

import gaspatchio
from gaspatchio import ActuarialFrame

base = Path(gaspatchio.__file__).resolve().parent / "tutorials/{folder}/base"
spec = importlib.util.spec_from_file_location("tutorial_model", base / "model.py")
module = importlib.util.module_from_spec(spec)
sys.modules["tutorial_model"] = module
sys.path.insert(0, str(base))
spec.loader.exec_module(module)

frame = ActuarialFrame(pl.read_parquet(base / "{book}"))
finished = module.main(frame)
answered = finished.collect(engine="jax")

from gaspatchio.engines import engine_named

print(json.dumps({{
    "rows": answered.height,
    "columns": len(answered.columns),
    "provider_imported": "gaspatchio_jax" in sys.modules,
    "registered": engine_named("jax").name,
}}))
"""


@pytest.mark.parametrize("model", ["level-4", "level-5"])
def test_the_axis_stage_runs_and_answers_for_every_node_of_the_pre_axis(
    model: str,
) -> None:
    """The subgraph the period count stands on, settled before the main pass.

    On both shipped models the horizon is a column and five scalar nodes stand
    between the book and it -- one of them a date parsed on the host, which is
    why the host settlement has to run first. What is asserted is that the
    stage produced a value for every node of the subgraph: an empty dictionary
    is what an inert stage returns, and an inert stage is a stage that cannot
    be jitted against.
    """
    from gaspatchio_jax.plan import ExecutionPlan

    artifact = _artifact(model)
    plan = ExecutionPlan.stage_inspect(artifact, every_node=True)
    assert plan.pre_axis == (
        "entry_date",
        "policy_term",
        "entry_date_parsed@1",
        "duration_mth_init@1",
        "term_months_left@1",
        "remaining_term_months@1",
    )
    prepared = plan.stage_prepare(plan.stage_validate_inputs(_book(model)))
    assert set(prepared.axis) == set(plan.pre_axis)
    # The horizon column itself, and the parsed date it stands on: values, not
    # an empty stage.
    horizon = prepared.axis["remaining_term_months@1"]
    assert horizon.carrier == "i64"
    assert int(horizon.array.max()) == 82
    assert prepared.axis["entry_date_parsed@1"].carrier == "date"


def test_a_refusal_in_the_axis_stage_is_a_refusal() -> None:
    """And is reported with the rest of the stage's findings, not swallowed.

    The stage used to answer an empty dictionary to any refusal, which made
    every defect in the subgraph invisible and the stage itself a no-op.
    """
    from gaspatchio.engines.report import EngineRefusal
    from gaspatchio_jax.plan import ExecutionPlan

    artifact = _artifact("level-4")
    plan = ExecutionPlan.stage_inspect(artifact, every_node=True)
    prepared = plan.stage_validate_inputs(_book("level-4"))
    # A date the stated format does not fit, in the one node of the subgraph
    # that parses one. Nothing else about the book changes.
    broken = prepared.frame.with_columns(
        pl.Series("entry_date", ["not a date"] * prepared.frame.height)
    )
    with pytest.raises(EngineRefusal) as refusal:
        engine_named("jax").run(artifact, broken, FrameSink())
    assert "str.to_date.strict" in refusal.value.report.render()


# The miniature jagged book's shape (``tests/conftest.py`` exports it): the
# same seven terms as the ten-thousand-policy one, so the same four widths
# and the same four programs.
JAGGED_GROUPS = 4
JAGGED_WIDTHS = (12, 24, 36, 48)


def test_the_jagged_book_is_four_widths_four_programs_and_the_book_s_own_order(
    jagged_book: tuple[dict, pl.DataFrame],
) -> None:
    """The one shipped-shape book whose policies do not share a timeline.

    Level 4 and level 5 are rectangles: every policy of them takes the same
    eighty-three boundaries, so nothing in them exercises the grouping. This
    one carries seven terms whose boundary counts, after each policy's own
    offset from the valuation date, run from 1 to 46 cells -- four widths on
    the grid, four groups, four compiled programs, and the rows coming back
    where their policies stood, each cut to its own timeline.
    """
    from gaspatchio_jax.batching import grouped
    from gaspatchio_jax.horizon import bucket_of
    from gaspatchio_jax.plan import ExecutionPlan

    artifact, book = jagged_book
    plan = ExecutionPlan.stage_inspect(artifact, every_node=True)
    prepared = plan.stage_prepare(plan.stage_validate_inputs(book))
    widths = next(iter(prepared.widths.values()))
    assert tuple(sorted({bucket_of(int(one)) for one in widths})) == JAGGED_WIDTHS
    groups = grouped(prepared.widths, prepared.inputs.rows)
    assert len(groups) == JAGGED_GROUPS
    assert sum(len(one) for one in groups) == JAGGED_POLICIES

    sink = Watched()
    streamed = plan.stage_stream(prepared, sink)
    assert len(plan.programs) == JAGGED_GROUPS
    assert len(sink.handed) == JAGGED_GROUPS
    result = plan.stage_complete(streamed, sink, prepared)
    answered, manifest = result.columns, result.manifest
    assert answered.height == JAGGED_POLICIES
    # The engine computed them grouped by width; a reader is owed them in the
    # order the book handed them in.
    assert answered["point_id"].to_list() == book["point_id"].to_list()
    # And each policy's own timeline is its own, not the widest one's. The
    # node id rather than the column name: an every-node result keys by node,
    # because two accounts of one column are two columns.
    in_force = next(
        node_id
        for node_id, record in plan.records.items()
        if record.column == "pols_if" and node_id in manifest.columns
    )
    lengths = answered[in_force].list.len().to_list()
    assert lengths == [int(one) for one in widths]
    assert len(set(lengths)) > 1


def test_the_jagged_book_through_the_file_door_is_polars_own_answer_in_order(
    jagged_book: tuple[dict, pl.DataFrame], tmp_path: Path
) -> None:
    """Four horizon groups staged as four parts, and merged back in book order.

    The file sink holds nothing of a batch but where each of its rows stands,
    so the four groups of this book are four part files on disk; the terms
    interleave row by row, so every block of publication draws on all four.
    What comes out is held to Polars' own every-node answers for the same
    book, within the agreement band -- the merge has to put every policy back
    exactly where the book had it for a single line to agree.
    """
    from gaspatchio.engines.protocol import ParquetSink

    artifact, book = jagged_book
    held = tmp_path / "book.parquet"
    book.write_parquet(held)
    reference = tmp_path / "reference.parquet"
    finished = subprocess.run(  # noqa: S603 -- the core's own venv and tutorials
        [
            str(CORE_GSPIO),
            "run-model",
            "--every-node",
            str(_tutorials() / FOLDER["level-4"] / "base/model.py"),
            str(held),
            "-o",
            str(reference),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
        cwd=CORE,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    out = tmp_path / "jax.parquet"

    engine_named("jax").run(artifact, book, ParquetSink(out), every_node=True)

    published = pl.read_parquet(out)
    assert published["point_id"].to_list() == book["point_id"].to_list()
    report = compare_results(
        artifact,
        pl.read_parquet(reference),
        published,
        before_manifest=read_manifest(reference),
        after_manifest=read_manifest(out),
    )
    assert report.missing == ()
    assert report.same_inputs
    disagreeing = [one for one in report.lines if one.verdict != "agree"]
    assert report.verdict == "agree", disagreeing
    assert sorted(one.name for one in tmp_path.iterdir()) == [
        "book.parquet",
        "jax.parquet",
        "reference.parquet",
    ]
