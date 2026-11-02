# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A frame built from another frame's collected values, without ``continue_from=``.

``ActuarialFrame(af.collect())`` starts a new calculation log, and every
column arrives as if the data had supplied it. A column whose values a
calculation on the other frame produced is not the data's, and the frame now
says so: it recognises that column by its memory, while the values are still
held, and reports it as a ``rebuilt`` hole naming the definition the values
came from and ``continue_from=``, the construction that keeps it.

Three things it must not do. It must not speak on the model template's own
setup step -- collect, rename in Polars, build the frame again, before any
calculation -- nor on a column a calculation merely handed back unchanged,
whose values are the data's. And it must not search the book the framework
itself was handed to run: the command line's run, a batched run and a
scenario axis build their frames over the caller's data, which is the run's
data on the caller's word.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame import base
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.execution import inspect_execution
from gaspatchio.scenarios import Sum, run_aggregated, run_to_parquet, with_scenarios

_HERE = Path(__file__).name

_BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "issue_age": [35, 45, 55],
        "premium": [100.0, 200.0, 300.0],
    }
)


def _line_after() -> int:
    """Return the number of the line after the caller's."""
    caller = inspect.currentframe()
    assert caller is not None
    assert caller.f_back is not None
    return caller.f_back.f_lineno + 1


def _valued() -> tuple[ActuarialFrame, int]:
    """Return a frame that calculated a reserve, and the line it did it on."""
    af = ActuarialFrame(_BOOK)
    line = _line_after()
    af.reserve = af.premium * 0.5
    return af, line


def _reasons(af: ActuarialFrame) -> list[tuple[str, str]]:
    return [(hole.column, hole.reason) for hole in af.graph.holes()]


@pytest.fixture
def checks(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record the columns of every DataFrame searched for another frame's values."""
    seen: list[list[str]] = []
    index = base._COMPUTED_VALUES  # noqa: SLF001 -- the process's own index
    computed = index.computed

    def spied(data: pl.DataFrame) -> dict[str, Any]:
        seen.append(list(data.columns))
        return computed(data)

    monkeypatch.setattr(index, "computed", spied)
    return seen


# --- the issue's own example ----------------------------------------------------


def test_a_column_another_frame_calculated_is_a_rebuilt_hole() -> None:
    """``reserve`` arrives looking like data, and the frame says where it was made."""
    af, line = _valued()
    wrapped = ActuarialFrame(af.collect())
    wrapped.total = wrapped.reserve + 1.0

    holes = wrapped.graph.holes()

    assert [(hole.column, hole.reason) for hole in holes] == [("reserve", "rebuilt")]
    hint = holes[0].hint.replace(str(Path(__file__)), _HERE)
    assert f"reserve@1 calculated on another frame at {_HERE}:{line}" in hint
    assert "ActuarialFrame(df, continue_from=af)" in hint


def test_the_export_holds_the_column_as_a_hole_and_not_as_the_data() -> None:
    """No ``model_points`` claim for it, an unversioned hole, and a valid file."""
    af, _line = _valued()
    wrapped = ActuarialFrame(af.collect())
    wrapped.total = wrapped.reserve + 1.0

    document = json.loads(GraphExporter(wrapped).export())
    nodes = {node["id"]: node for node in document["nodes"]}

    assert (nodes["reserve"]["kind"], nodes["reserve"]["version"]) == ("hole", None)
    assert nodes["total@1"]["reads"] == ["reserve"]
    assert {
        node["column"]
        for node in document["nodes"]
        if node["provenance"] == "model_points"
    } == {"policy_id", "issue_age", "premium"}
    assert document["holes"][0]["reason"] == "rebuilt"
    assert validate_artifact(document).ok


def test_a_column_renamed_in_polars_names_the_definition_it_came_from() -> None:
    af, _line = _valued()
    renamed = ActuarialFrame(af.collect().rename({"reserve": "opening_reserve"}))

    holes = renamed.graph.holes()

    assert [(hole.column, hole.reason) for hole in holes] == [
        ("opening_reserve", "rebuilt")
    ]
    assert "reserve@1" in holes[0].hint


def test_a_definition_that_hands_back_an_input_holds_the_data_s_values() -> None:
    """``af.age = af.issue_age`` produced the book's own numbers: no hole."""
    af = ActuarialFrame(_BOOK)
    af.age = af.issue_age
    af.reserve = af.premium * 0.5

    assert _reasons(ActuarialFrame(af.collect())) == [("reserve", "rebuilt")]


def _hands_back_the_age_and_drops_it() -> ActuarialFrame:
    """Return a frame whose one calculation is an input handed back, then dropped."""
    af = ActuarialFrame(_BOOK)
    af.age = af.issue_age
    return af.drop("issue_age")


def test_an_input_handed_back_then_dropped_is_still_the_data_s() -> None:
    """The book is the data, though the values no longer hold the input itself.

    ``age`` holds the memory of the book's ``issue_age``, and the values the
    collect handed back no longer hold ``issue_age`` beside it. The book the
    frame was built over still does, so a frame built over that book again
    is built over data, not over a calculation.
    """
    af = _hands_back_the_age_and_drops_it()
    values = af.collect(engine="in-memory")

    assert _reasons(ActuarialFrame(_BOOK)) == []
    assert values.columns == ["policy_id", "premium", "age"]


def test_an_input_handed_back_by_a_frame_now_gone_is_still_the_data_s() -> None:
    """The frame was a temporary; the values its collect handed back are not."""
    values = _hands_back_the_age_and_drops_it().collect(engine="in-memory")

    assert _reasons(ActuarialFrame(_BOOK)) == []
    assert values.columns == ["policy_id", "premium", "age"]


def test_the_template_s_setup_step_says_nothing() -> None:
    """Collect, alias in Polars, build again: nothing was calculated before it."""
    af = ActuarialFrame(_BOOK)
    mp = af.collect().with_columns(pl.col("issue_age").alias("age"))
    rebuilt = ActuarialFrame(mp)
    rebuilt.reserve = rebuilt.premium * 0.5

    assert rebuilt.graph.holes() == []


def test_continue_from_keeps_the_calculation_and_finds_nothing() -> None:
    af, _line = _valued()
    continued = ActuarialFrame(af.collect(), continue_from=af)
    continued.total = continued.reserve + 1.0

    document = json.loads(GraphExporter(continued).export())

    assert continued.graph.holes() == []
    assert "reserve@1" in {node["id"] for node in document["nodes"]}


def test_a_frame_built_from_a_temporary_frame_s_values_is_found() -> None:
    """The earlier frame is gone; the DataFrame its collect handed back is not."""

    def model() -> ActuarialFrame:
        af, _line = _valued()
        return af

    assert _reasons(ActuarialFrame(model().collect())) == [("reserve", "rebuilt")]


def test_values_the_caller_holds_are_found_after_the_frame_moves_on() -> None:
    """The frame lets its copy go at its next assignment; the caller's hold does not."""
    af, _line = _valued()
    values = af.collect()
    af.total = af.reserve + 1.0

    assert _reasons(ActuarialFrame(values)) == [("reserve", "rebuilt")]


def test_values_rebuilt_twice_still_name_where_they_were_made() -> None:
    """A rebuilt frame's own collect carries the first frame's definition on."""
    af, line = _valued()
    once = ActuarialFrame(af.collect())
    once.total = once.reserve + 1.0
    twice = ActuarialFrame(once.collect())
    del af, once

    holes = twice.graph.holes()

    assert [(hole.column, hole.reason) for hole in holes] == [
        ("reserve", "rebuilt"),
        ("total", "rebuilt"),
    ]
    assert f"{_HERE}:{line}" in holes[0].hint.replace(str(Path(__file__)), _HERE)


def test_a_rebuilt_column_renamed_through_the_frame_stays_rebuilt() -> None:
    """The new name is the hole the old one was, and what read the old one reads it.

    A rename logs nothing for a column nothing on the frame accounts
    for, so there is no move to follow: each name stands as its own hole,
    and both say where the values were made.
    """
    af, _line = _valued()
    wrapped = ActuarialFrame(af.collect())
    wrapped.total = wrapped.reserve + 1.0
    wrapped = wrapped.rename({"reserve": "opening_reserve"})

    document = json.loads(GraphExporter(wrapped).export())
    nodes = {node["id"]: node for node in document["nodes"]}

    assert nodes["total@1"]["reads"] == ["reserve"]
    assert _reasons(wrapped) == [
        ("opening_reserve", "rebuilt"),
        ("reserve", "rebuilt"),
    ]
    assert validate_artifact(document).ok


def test_a_rebuilt_column_dropped_later_is_still_what_was_read() -> None:
    af, _line = _valued()
    wrapped = ActuarialFrame(af.collect())
    wrapped.total = wrapped.reserve + 1.0
    wrapped = wrapped.drop("reserve")

    document = json.loads(GraphExporter(wrapped).export())
    nodes = {node["id"]: node for node in document["nodes"]}

    assert nodes["total@1"]["reads"] == ["reserve"]
    assert (nodes["reserve"]["kind"], nodes["reserve"]["in_final_schema"]) == (
        "hole",
        False,
    )
    assert _reasons(wrapped) == [("reserve", "rebuilt")]


def test_a_rebuilt_column_calculated_again_unread_is_no_longer_a_hole() -> None:
    """The frame accounts for the column again, and nothing read what it replaced."""
    af, _line = _valued()
    wrapped = ActuarialFrame(af.collect())
    wrapped.reserve = wrapped.premium * 0.5

    assert _reasons(wrapped) == []


def test_a_rebuilt_column_dropped_unread_is_no_longer_a_hole() -> None:
    """The frame no longer holds the column, and nothing read it."""
    af, _line = _valued()
    wrapped = ActuarialFrame(af.collect())
    wrapped = wrapped.drop("reserve")

    assert _reasons(wrapped) == []


def test_a_rebuilt_column_read_and_then_calculated_again_stays_what_was_read() -> None:
    """The total was taken on the rebuilt values, so those stay a hole behind it."""
    af, _line = _valued()
    wrapped = ActuarialFrame(af.collect())
    wrapped.total = wrapped.reserve + 1.0
    wrapped.reserve = wrapped.premium * 0.5

    document = json.loads(GraphExporter(wrapped).export())
    nodes = {node["id"]: node for node in document["nodes"]}

    assert nodes["total@1"]["reads"] == ["reserve"]
    assert (nodes["reserve"]["kind"], nodes["reserve"]["in_final_schema"]) == (
        "hole",
        False,
    )
    assert nodes["reserve@1"]["in_final_schema"] is True
    assert _reasons(wrapped) == [("reserve", "rebuilt")]
    assert validate_artifact(document).ok


def test_a_column_under_a_working_prefix_is_refused_before_anything_is_searched(
    checks: list[list[str]],
) -> None:
    """The arrival refusal comes first: a frame that is not built has no columns."""
    af = ActuarialFrame(_BOOK)
    af.reserve = af.premium * 0.5
    af.reserve = af.premium * 0.6
    plan = af._df  # noqa: SLF001 -- the plan, working columns and all
    assert plan is not None
    raw = plan.collect()
    assert any(name.startswith("__gaspatchio_retained__") for name in raw.columns)
    checks.clear()

    with pytest.raises(ValueError, match="Rename it before building the frame"):
        ActuarialFrame(raw)
    assert checks == []


# --- what is searched ------------------------------------------------------------


def test_a_model_s_own_construction_is_searched(checks: list[list[str]]) -> None:
    af, _line = _valued()
    checks.clear()

    ActuarialFrame(af.collect())

    assert checks == [["policy_id", "issue_age", "premium", "reserve"]]


def test_the_framework_s_own_constructions_over_the_book_are_not_searched(
    checks: list[list[str]], tmp_path: Path
) -> None:
    """The book a caller hands a run is the run's data, calculated or not.

    A batched run to files, a batched run folded to totals, a scenario axis,
    and the command line's export and run of a model file, each over a book
    holding a column a frame calculated before it.
    """
    af, _line = _valued()
    book = af.collect()
    scenario_base = af
    model_path = tmp_path / "model.py"
    model_path.write_text(
        "def main(af):\n    af.total = af.reserve + af.premium\n    return af\n"
    )
    points = tmp_path / "points.parquet"
    book.write_parquet(points)

    def model(frame: ActuarialFrame) -> ActuarialFrame:
        frame.total = frame.reserve + frame.premium
        return frame

    checks.clear()
    run_to_parquet(model, book, tmp_path / "spilled", batch_size=book.height)
    run_aggregated(model, book, [Sum("total").alias("total")], batch_size=2)
    with_scenarios(scenario_base, ["BASE", "UP"])
    result = CliRunner().invoke(
        app,
        ["calc-graph", str(model_path), str(points), "-o", str(tmp_path / "g.json")],
    )
    assert result.exit_code == 0, result.output
    ran = CliRunner().invoke(app, ["run-model", str(model_path), str(points)])
    assert ran.exit_code == 0, ran.output

    assert checks == []


# --- the second engine ----------------------------------------------------------


def test_a_second_engine_is_told_to_build_the_frame_with_continue_from() -> None:
    """The line reading the column cannot run, and the move that fixes it is named."""
    af, _line = _valued()
    wrapped = ActuarialFrame(af.collect())
    wrapped.total = wrapped.reserve + 1.0

    document = json.loads(GraphExporter(wrapped).export(profile="executable"))
    findings = [
        finding
        for finding in inspect_execution(document).findings
        if finding.code == "unavailable_calculation"
    ]

    assert [finding.where for finding in findings] == ["/nodes/reserve"]
    assert findings[0].move is not None
    assert "ActuarialFrame(df, continue_from=af)" in findings[0].move
