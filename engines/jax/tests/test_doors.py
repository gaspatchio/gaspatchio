# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Both doors on a tiny model, and what the frame door does about its inputs.

The first two run in *fresh processes*. Discovery that only a process which
had already imported the engine could arrange would not be discovery, and the
whole point of the provider seam is that ``--engine jax`` finds the package
without anybody importing it first.

The five frame-door cases after them are the frame door's acceptance list:
rename, overwrite, drop, ``materialize()`` and ``continue_from=``. What they
pin is that an input the frame no longer holds is refused *by name* rather
than filled from a Polars calculation -- which would put a computed number
into an engine under the name of a model-point field and make the run
impossible to attribute.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.protocol import read_manifest
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter
from tests.conftest import PROJECT

PYTHON = PROJECT / ".venv/bin/python"
GSPIO = PROJECT / ".venv/bin/gspio"

BOOK = {"a": [1.0, 2.0, 3.0], "b": [10.0, 20.0, 30.0]}


def _model() -> ActuarialFrame:
    af = ActuarialFrame(pl.DataFrame(BOOK))
    af.total = af.a + af.b
    return af


@pytest.fixture
def artifact(tmp_path: Path) -> tuple[Path, Path]:
    """Return a tiny executable artifact and the book it reads."""
    document = GraphExporter(_model()).export(profile="executable")
    written = tmp_path / "artifact.json"
    written.write_text(document, encoding="utf-8")
    book = tmp_path / "book.parquet"
    pl.DataFrame(BOOK).write_parquet(book)
    return written, book


def test_the_file_door_writes_a_result_with_its_manifest_in_a_fresh_process(
    artifact, tmp_path: Path
) -> None:
    document, book = artifact
    out = tmp_path / "jax.parquet"
    finished = subprocess.run(  # noqa: S603 -- this project's own venv and fixtures
        [
            str(GSPIO),
            "run-artifact",
            str(document),
            str(book),
            "--engine",
            "jax",
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    written = pl.read_parquet(out)
    assert written["total"].to_list() == [11.0, 22.0, 33.0]
    manifest = read_manifest(out)
    assert manifest.producer == "jax"
    assert manifest.scope == "final-schema"
    assert (
        manifest.graph_fingerprint
        == json.loads(document.read_text(encoding="utf-8"))["graph_fingerprint"]
    )
    assert not list(tmp_path.glob("*.unpublished*"))


def test_the_frame_door_returns_the_same_columns_in_a_fresh_process() -> None:
    script = textwrap.dedent(
        """
        import polars as pl
        from gaspatchio import ActuarialFrame
        book = {"a": [1.0, 2.0, 3.0], "b": [10.0, 20.0, 30.0]}
        af = ActuarialFrame(pl.DataFrame(book))
        af.total = af.a + af.b
        frame = af.collect(engine="jax")
        print(frame.columns, frame["total"].to_list())
        """
    )
    finished = subprocess.run(  # noqa: S603 -- as above
        [str(PYTHON), "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr
    assert "[11.0, 22.0, 33.0]" in finished.stdout
    assert "'total'" in finished.stdout


def test_the_engine_answers_the_same_values_polars_does() -> None:
    af = _model()
    assert af.collect(engine="jax")["total"].to_list() == [11.0, 22.0, 33.0]
    assert _model().collect()["total"].to_list() == [11.0, 22.0, 33.0]


def test_the_frame_door_leaves_the_book_digest_to_the_engine_which_records_it() -> None:
    """The door hands over no digest of the book; the engine's manifest carries one.

    The engine digests the inputs it runs over into its result manifest --
    the record of what it ran over -- so the document it is handed takes none,
    and what the engine records is the book it was handed.
    """
    from gaspatchio.engines import engine_named
    from gaspatchio.engines.protocol import FrameSink, digest_of_inputs
    from gaspatchio.frame.graph import inspect_execution

    document, inputs = _model()._for_an_engine()  # noqa: SLF001 -- the door under test
    assert document["book"]["digest"]["omitted"] == "unavailable"
    assert "engine" in document["book"]["digest"]["detail"]
    required = [one.column for one in inspect_execution(document).required_inputs]

    result = engine_named("jax").run(document, inputs, FrameSink())

    assert result.manifest.inputs_digest == digest_of_inputs(
        pl.DataFrame(BOOK), required
    )


def test_an_engine_handed_the_book_itself_records_the_book_s_digest() -> None:
    """A filed document's book digest is the manifest's, the book being handed."""
    from gaspatchio.engines import engine_named
    from gaspatchio.engines.protocol import FrameSink

    document = json.loads(GraphExporter(_model()).export(profile="executable"))

    result = engine_named("jax").run(document, pl.DataFrame(BOOK), FrameSink())

    assert result.manifest.inputs_digest == document["book"]["digest"]


def test_an_engine_handed_the_book_crossed_with_scenarios_records_another_digest() -> (
    None
):
    """A scenario axis is part of what the engine is handed, and of what it records.

    The book's digest is a result manifest's only where the engine was handed
    the book itself. Crossed with a scenario axis, the engine is handed a
    column the book does not hold on rows the book does not have, and its
    manifest records a digest of those: the two differ, and each describes
    the rows it was taken over.
    """
    from gaspatchio.engines import engine_named
    from gaspatchio.engines.protocol import FrameSink, digest_of_inputs
    from gaspatchio.frame.graph import inspect_execution
    from gaspatchio.scenarios import with_scenarios

    af = with_scenarios(ActuarialFrame(pl.DataFrame(BOOK)), ["BASE", "UP"])
    af.total = af.a + af.b
    crossed = af.collect()
    document = json.loads(GraphExporter(af).export(profile="executable"))
    required = [one.column for one in inspect_execution(document).required_inputs]

    handed = crossed.select(required)
    result = engine_named("jax").run(document, handed, FrameSink())

    assert "scenario_id" in required
    assert "scenario_id" not in document["book"]["columns"]
    assert result.manifest.inputs_digest == digest_of_inputs(crossed, required)
    assert result.manifest.inputs_digest != document["book"]["digest"]


def test_a_renamed_input_is_refused_by_name_rather_than_filled() -> None:
    af = _model()
    af = af.rename({"a": "premium"})
    with pytest.raises(EngineRefusal) as refused:
        af.collect(engine="jax")
    assert refused.value.report.refusals[0].where == "a"
    assert refused.value.report.refusals[0].group == "inputs"


def test_an_input_the_model_wrote_over_is_refused_with_the_count() -> None:
    af = _model()
    af.a = af.a * 2
    with pytest.raises(EngineRefusal) as refused:
        af.collect(engine="jax")
    assert refused.value.report.refusals[0].where == "a"
    assert refused.value.report.refusals[0].count == 1


def test_a_dropped_input_is_refused_by_name() -> None:
    af = _model()
    af = af.drop("b")
    with pytest.raises(EngineRefusal) as refused:
        af.collect(engine="jax")
    assert "b" in {one.where for one in refused.value.report.refusals}


def test_a_select_that_writes_over_an_input_is_refused_rather_than_answered() -> None:
    """The select's line is recorded, so the engine cannot answer from the book's a."""
    af = _model()
    af = af.select(pl.all().exclude("a"), (pl.col("a") * 10).alias("a"))
    assert af.collect()["a"].to_list() == [10.0, 20.0, 30.0]

    with pytest.raises(EngineRefusal) as refused:
        af.collect(engine="jax")

    assert any(
        one.where in {"a", "/nodes/a@1", "/nodes/a@1/expr"}
        for one in refused.value.report.refusals
    )


def test_a_select_that_calculates_a_new_column_answers_as_polars_does() -> None:
    af = _model()
    af = af.select(pl.all(), doubled=af.total * 2)

    assert af.collect(engine="jax")["doubled"].to_list() == [22.0, 44.0, 66.0]
    assert af.collect()["doubled"].to_list() == [22.0, 44.0, 66.0]


def test_a_select_that_only_marks_an_input_sorted_answers_as_polars_does() -> None:
    """A column only marked sorted keeps its values, so nothing is written over it."""
    af = _model()
    af = af.select(pl.all().exclude("a"), pl.col("a").set_sorted())

    assert af.collect(engine="jax").to_dict(as_series=False) == af.collect().to_dict(
        as_series=False
    )


def test_a_select_that_casts_an_input_to_its_own_type_answers_as_polars_does() -> None:
    af = _model()
    af = af.select(pl.all().exclude("b"), pl.col("b").cast(pl.Float64, strict=False))

    assert af.collect(engine="jax").to_dict(as_series=False) == af.collect().to_dict(
        as_series=False
    )


def test_a_select_that_writes_over_a_rollforward_input_is_refused() -> None:
    """Polars ran the rollforward over the input before the select wrote it."""
    from datetime import date

    from gaspatchio import compile_rollforward

    af = ActuarialFrame(
        pl.DataFrame(
            {"av_init": [1000.0], "fund_return": [[0.01] * 3], "fee": [[5.0] * 3]}
        )
    )
    af = af.projection.set(
        start_date=date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    b = af.projection.rollforward(states={"av": af["av_init"]})
    b["av"].grow(af["fund_return"])
    b["av"].subtract(af["fee"])
    af.av = compile_rollforward(b).expr_for("av")
    af = af.select(
        pl.all().exclude("fund_return"),
        (pl.col("fund_return") * 10).alias("fund_return"),
    )
    assert af.collect()["av"].to_list()[0] == pytest.approx(
        [1005.0, 1010.05, 1015.1505]
    )

    with pytest.raises(EngineRefusal):
        af.collect(engine="jax")


def test_a_materialised_frame_still_runs_on_the_engine() -> None:
    af = _model().materialize()
    assert af.collect(engine="jax")["total"].to_list() == [11.0, 22.0, 33.0]


def test_continue_from_is_accepted_after_an_engine_collect() -> None:
    af = _model()
    values = af.collect(engine="jax")
    carried = ActuarialFrame(values, continue_from=af)
    carried.doubled = carried.total * 2
    assert carried.collect()["doubled"].to_list() == [22.0, 44.0, 66.0]


def test_the_fold_the_frame_door_pays_for_is_measured_rather_than_assumed() -> None:
    """The fold the frame door pays for is measured here rather than assumed.

    Not a threshold -- a fold that got slower would be a fact about the
    exporter and not about this engine -- but a measurement printed to the
    log, taken on the door's own path.
    """
    af = _model()
    started = time.perf_counter()
    document = GraphExporter(af).export(profile="executable", include_source=False)
    elapsed = time.perf_counter() - started
    assert json.loads(document)["profile"] == "executable"
    print(f"fold of a three-node model: {elapsed * 1000:.1f} ms")  # noqa: T201


def test_the_engine_suite_runs_on_this_project_s_own_interpreter() -> None:
    assert Path(sys.prefix).resolve() == (PROJECT / ".venv").resolve()
