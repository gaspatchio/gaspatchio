# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario run's door to an artifact, and what the axis column is.

The model reads ``scenario_id`` and dispatches on it; the *plan* is what
cross-joins the axis, stacks the shocked bases and folds each scenario's
total. So ``calc-graph`` running the model alone could write no account of a
scenario run at all, and ``--scenarios run_scenarios.py`` is the door that
runs the plan the modeller already wrote.

Four things are held to here, and each is a claim a reader of a sensitivity
pack acts on.

**The totals are the plan's own.** Every per-scenario fold below is checked
against the same plan run through ``ScenarioRun.run`` in this process, not
against a number written into this file. A producer that re-summed the handful
of rows the document samples would publish a figure that is nobody's under a
name saying it is the book's.

**Every entry names its scenario.** A cross-join gives one policy one row per
scenario, so three entries can read ``policy 1`` and differ in nothing a
reader can see. ``filter`` is what separates them, on the policies and on the
folds alike.

**The axis column is `injected`, at the plan's own line.** The model-points
file never held ``scenario_id``; the framework put it there. §8 has the word
for a whole column handed to the model at a known line, and the node carries
that word and the line.

**A refusal names the move.** A script declaring no plan, an id a cross-joined
frame answers to three times, a second fold asked for beside the plan's own:
each is refused with a sentence, and each sentence is read here rather than
only the exit code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app

if TYPE_CHECKING:
    from collections.abc import Sequence

runner = CliRunner()

# The exit code a refused command line carries, shared with the selector and
# the fold: the model never started, so this is not a run that failed.
_REFUSED = 3

# The model the plan is run against. `shocked_rate` dispatches on the axis
# column, which is the ordinary shape of a scenario model and the reason the
# axis has to be answerable at all.
_MODEL = """
import polars as pl

from gaspatchio import ActuarialFrame


def main(af, params=None):
    del params
    af.shocked_rate = af.base_rate * pl.when(
        pl.col("scenario_id") == "STRESS"
    ).then(1.5).otherwise(1.0)
    af.loss = af.sum_assured * af.shocked_rate
    return af
"""

# The run script, in the shape a modeller writes: a plan declared at module
# level under the name the door reads, with the model function beside it.
_SCRIPT = """
from gaspatchio import ActuarialFrame, ScenarioRun
from gaspatchio.scenarios import Sum

import model


{declaration}
MODEL_FN = model.main
"""

_DECLARES = """SCENARIO_RUN = ScenarioRun(
    shocks={"BASE": [], "STRESS": []},
    aggregations=(Sum("loss").alias("loss").over("scenario_id"),),
)
"""

_DECLARES_A_MAKER = """def SCENARIO_RUN():
    return ScenarioRun(
        shocks={"BASE": [], "STRESS": []},
            aggregations=(Sum("loss").alias("loss").over("scenario_id"),),
    )
"""

_DECLARES_THE_WRONG_THING = 'SCENARIO_RUN = {"BASE": [], "STRESS": []}\n'


@pytest.fixture
def book(tmp_path: Path) -> Path:
    """Write a two-policy book and return its path."""
    written = tmp_path / "book.parquet"
    pl.DataFrame(
        {
            "Policy number": ["P1", "P2"],
            "sum_assured": [100_000.0, 250_000.0],
            "base_rate": [0.001, 0.002],
        }
    ).write_parquet(written)
    return written


@pytest.fixture
def model(tmp_path: Path) -> Path:
    """Write the model and return its path."""
    written = tmp_path / "model.py"
    written.write_text(_MODEL)
    return written


@pytest.fixture
def script(tmp_path: Path, model: Path) -> Path:
    """Write the run script declaring the plan, and return its path."""
    del model  # the script imports it, so it has to exist first
    return _script_declaring(tmp_path, _DECLARES)


def _script_declaring(tmp_path: Path, declaration: str) -> Path:
    """Write a run script with one declaration in it, and return its path."""
    written = tmp_path / "run_scenarios.py"
    written.write_text(_SCRIPT.format(declaration=declaration))
    return written


def _export(model: Path, book: Path, out: Path, *extra: str) -> Any:  # noqa: ANN401 -- the runner's own result
    """Run ``calc-graph`` and return the runner result, whatever it was."""
    return runner.invoke(
        app,
        ["calc-graph", str(model), str(book), "-o", str(out), *extra],
    )


def _exported(model: Path, book: Path, script: Path, *extra: str) -> dict[str, Any]:
    """Export through the door and return the document, refusing to guess."""
    out = script.parent / "graph.json"
    result = _export(model, book, out, "--scenarios", str(script), *extra)
    assert result.exit_code == 0, result.output
    document: dict[str, Any] = json.loads(out.read_text())
    return document


def _refusal(model: Path, book: Path, out: Path, *extra: str) -> str:
    """Return the sentence one refused export was refused with."""
    result = _export(model, book, out, *extra)
    assert result.exit_code == _REFUSED, result.output
    return " ".join(result.output.split())


def _entries(document: dict[str, Any]) -> Sequence[dict[str, Any]]:
    """Return the document's policy axis."""
    axis: Sequence[dict[str, Any]] = document["policies"]
    return axis


def _node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return one node of the document by id."""
    for node in document["nodes"]:
        if node["id"] == node_id:
            found: dict[str, Any] = node
            return found
    message = f"no node {node_id} in {[n['id'] for n in document['nodes']]}"
    raise AssertionError(message)


def test_the_fold_entries_are_the_plans_own_totals(
    model: Path, book: Path, script: Path
) -> None:
    """The scenario totals in the document are the ones the script prints.

    Run here rather than quoted: the plan is executed a second time in this
    process, through the same ``ScenarioRun.run`` the modeller calls, and the
    document's entries are held to what it produced. Equal on the wire, which
    is where the producer rounds every value it writes.
    """
    from gaspatchio import ActuarialFrame
    from gaspatchio.scenarios._graph_export import (
        open_the_script,
    )
    from gaspatchio.frame.graph.value_extractor import (
        one_value_on_the_wire,
    )

    document = _exported(model, book, script)
    declared = open_the_script(script)
    own = declared.plan.run(
        ActuarialFrame(pl.read_parquet(book)), declared.model_fn
    ).aggregations["loss"]
    theirs = {row["scenario_id"]: row["loss"] for row in own.iter_rows(named=True)}

    sample = _node(document, "loss@1")["value_sample"]
    folds = [
        (entry["filter"], sample[at])
        for at, entry in enumerate(_entries(document))
        if entry["aggregation"] is not None
    ]
    assert len(folds) == len(theirs)
    for cut, value in folds:
        scenario = cut.split('"')[1]
        assert value == one_value_on_the_wire(theirs[scenario])


def test_every_entry_of_the_axis_names_its_scenario(
    model: Path, book: Path, script: Path
) -> None:
    """Folds and policies alike, because a row of a cross-join is in one cut."""
    axis = _entries(_exported(model, book, script, "--policies", "all"))

    assert all(entry["filter"].startswith("scenario_id == ") for entry in axis)
    folds = [entry for entry in axis if entry["aggregation"] is not None]
    policies = [entry for entry in axis if entry["aggregation"] is None]
    assert [entry["filter"] for entry in folds] == [
        'scenario_id == "BASE"',
        'scenario_id == "STRESS"',
    ]
    # Two policies against two scenarios is four rows, and no two entries of
    # the axis read the same. Without the cut, P1 would be on the axis twice
    # with nothing between the two.
    assert len(policies) == 4
    assert len({(entry["policy_id"], entry["filter"]) for entry in policies}) == 4


def test_the_scenario_axis_is_injected_at_the_plans_own_line(
    model: Path, book: Path, script: Path
) -> None:
    """The book never held the column, and the node stops saying it did."""
    axis = _node(_exported(model, book, script), "scenario_id@1")

    assert axis["kind"] == "input"
    assert axis["provenance"] == "injected"
    assert axis["source_location"] is not None
    where, _, line = axis["source_location"].rpartition(":")
    assert where.endswith("run_scenarios.py")
    # The line the script binds the plan on, which is what a reader opening
    # the file at that line finds.
    assert script.read_text().splitlines()[int(line) - 1].startswith("SCENARIO_RUN")


def test_a_plan_declared_as_a_function_is_read_the_same_way(
    tmp_path: Path, model: Path, book: Path
) -> None:
    """Either form declares a plan; a script building one in a function has a door."""
    made = _script_declaring(tmp_path, _DECLARES_A_MAKER)
    axis = _node(_exported(model, book, made), "scenario_id@1")

    assert axis["provenance"] == "injected"
    where, _, line = axis["source_location"].rpartition(":")
    assert where.endswith("run_scenarios.py")
    assert made.read_text().splitlines()[int(line) - 1].startswith("def SCENARIO_RUN")


def test_the_document_names_the_runs_own_record_by_path_and_digest(
    model: Path, book: Path, script: Path
) -> None:
    """The artifact and the sidecar are two records of one run, tied by content."""
    from gaspatchio._identity import SHA256_PREFIX

    document = _exported(model, book, script)
    named = document["model"]["audit"]
    beside = script.parent / Path(named["path"]).name

    assert beside.exists()
    assert named["fingerprint"].startswith(SHA256_PREFIX)
    # The sidecar is the plan's, and it names the plan the artifact is an
    # account of running.
    assert json.loads(beside.read_text())["source_sha"] is not None


def test_a_run_that_wrote_no_record_names_none(model: Path, book: Path) -> None:
    """Absent rather than null, on the reading ``results`` already has.

    A plain export asked for no scenario run and wrote no sidecar. A null
    would say there was a record it could not identify, and what is true is
    that there was none to identify.
    """
    plain = model.parent / "plain_model.py"
    plain.write_text(
        "def main(af, params=None):\n"
        "    del params\n"
        "    af.doubled = af.base_rate * 2\n"
        "    return af\n"
    )
    out = model.parent / "plain.json"
    assert _export(plain, book, out).exit_code == 0

    assert "audit" not in json.loads(out.read_text())["model"]


def test_an_id_a_cross_joined_frame_answers_to_twice_is_refused(
    model: Path, book: Path, script: Path
) -> None:
    """A non-unique id is refused, and the sentence names the two ways through.

    Taking the first row would put BASE's numbers under a name STRESS answers
    to as well. A row position reaches a row and ``--filter`` narrows to the
    scenario meant, and the refusal says both before a reader has to work
    them out.
    """
    sentence = _refusal(
        model,
        book,
        script.parent / "graph.json",
        "--scenarios",
        str(script),
        "--policies",
        "P1",
    )

    assert "more than one answer" in sentence
    assert "':N' slice" in sentence
    assert "--filter" in sentence


def test_the_refusals_own_filter_is_a_command_that_works(
    model: Path, book: Path, script: Path
) -> None:
    """The refusal's advice is executed, and it succeeds.

    The refusal used to recommend ``--filter`` while the command resolved
    the id before the filter reached it, so a reader who took the advice met
    the same refusal. The cut is now made first and the sentence names an
    expression it has checked against the rows -- so this runs the exact
    expression printed and holds the result to exit 0 and to the policy that
    was asked for.
    """
    sentence = _refusal(
        model,
        book,
        script.parent / "graph.json",
        "--scenarios",
        str(script),
        "--policies",
        "P1",
    )
    _, _, rest = sentence.partition("--filter ")
    advised = rest.split('"')[1]

    document = _exported(model, book, script, "--policies", "P1", "--filter", advised)

    policies = [entry for entry in _entries(document) if entry["policy_id"]]
    assert [entry["policy_id"] for entry in policies] == ["P1"]
    assert "rows" in policies[0]["why"]


def test_a_second_fold_beside_the_plans_own_is_refused(
    model: Path, book: Path, script: Path
) -> None:
    """Two folds of one book would be two answers to one question."""
    sentence = _refusal(
        model,
        book,
        script.parent / "graph.json",
        "--scenarios",
        str(script),
        "--portfolio",
    )

    assert "--scenarios already folds the book" in sentence
    assert "aggregations=" in sentence


def test_a_script_declaring_no_plan_is_refused_by_name(
    tmp_path: Path, model: Path, book: Path
) -> None:
    """Which scenarios and which totals is the modeller's decision."""
    silent = _script_declaring(tmp_path, "")
    sentence = _refusal(
        model, book, tmp_path / "graph.json", "--scenarios", str(silent)
    )

    assert "declares no SCENARIO_RUN" in sentence
    assert "ScenarioRun(" in sentence
    assert "__main__" in sentence


def test_a_plan_declared_as_something_else_is_refused_by_what_it_is(
    tmp_path: Path, model: Path, book: Path
) -> None:
    """A dict of shocks is not a plan, and the sentence says which it got."""
    wrong = _script_declaring(tmp_path, _DECLARES_THE_WRONG_THING)
    sentence = _refusal(model, book, tmp_path / "graph.json", "--scenarios", str(wrong))

    assert "declares SCENARIO_RUN as dict" in sentence
    assert "ScenarioRun(...)" in sentence


def test_a_script_that_will_not_import_is_refused_with_the_reason(
    tmp_path: Path, model: Path, book: Path
) -> None:
    """A plan is a Python object, so reaching it runs the line that builds it."""
    broken = tmp_path / "run_scenarios.py"
    broken.write_text("raise RuntimeError('the sweep fell over')\n")
    sentence = _refusal(
        model, book, tmp_path / "graph.json", "--scenarios", str(broken)
    )

    assert "could not be imported" in sentence
    assert "the sweep fell over" in sentence
    assert "__main__" in sentence
