# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A column the frame accounted for, written over straight in its query plan.

A model can assign ``af._df`` itself. Where that write defines a column the
frame had accounted for -- a calculation it logged, or a column the data
arrived with -- the frame's account of the column stops being true: the
column holds what the write computed, and the calculation log still shows
what it replaced. The frame now reads the write as it takes it, logs each
such column as overwritten at the line of the write, and the calculation
graph reports it as a hole, versioned and located, which every later
calculation reads.

What it must not do is say more than it saw. A column the write adds under a
new name is still unrecorded; a join brings columns in under new names and
overwrites nothing; a plan that does not resolve is left for ``collect()`` to
refuse; and a write it cannot read is reported as overwriting every column it
accounted for that the plan still holds, rather than guessed at.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame import plan_writes
from gaspatchio.frame.calculations import OverwriteRecord
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.execution import inspect_execution

_HERE = Path(__file__).name

_BOOK = pl.DataFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})


def _line_after() -> int:
    """Return the number of the line after the caller's."""
    caller = inspect.currentframe()
    assert caller is not None
    assert caller.f_back is not None
    return caller.f_back.f_lineno + 1


def _commission_overwritten() -> tuple[ActuarialFrame, int, int]:
    """Return the issue's frame, and the lines of the calculation and the write."""
    af = ActuarialFrame(_BOOK)
    calculated = _line_after()
    af.commission = af.premium * 0.1
    written = _line_after()
    af._df = af._df.with_columns(pl.lit(0.0).alias("commission"))  # noqa: SLF001
    return af, calculated, written


def _document(af: ActuarialFrame, **options: Any) -> dict[str, Any]:  # noqa: ANN401
    """Return ``af``'s exported audit file."""
    document: dict[str, Any] = json.loads(GraphExporter(af).export(**options))
    return document


def _node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``document`` carrying ``node_id``."""
    found = [node for node in document["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in document['nodes']]}"
    return found[0]


# --- the issue's own example ---------------------------------------------------


def test_a_recorded_column_overwritten_in_the_plan_is_a_hole() -> None:
    """The log said ``premium * 0.1``; the column holds 0.0; the frame says so."""
    af, calculated, written = _commission_overwritten()

    holes = af.graph.holes()

    assert [(hole.column, hole.reason) for hole in holes] == [
        ("commission", "overwritten")
    ]
    hint = holes[0].hint
    assert f"{_HERE}:{written}" in hint
    assert f"commission@1, af.premium * 0.1, at {_HERE}:{calculated}" in hint.replace(
        str(Path(__file__)), _HERE
    )
    assert "af.commission = ..." in hint
    assert af.collect()["commission"].to_list() == [0.0, 0.0]


def test_the_export_states_the_overwrite_as_a_located_definition() -> None:
    """A hole under the next ordinal, at the write's line; the formula is history."""
    af, _calculated, written = _commission_overwritten()

    document = _document(af)

    recorded = _node(document, "commission@1")
    assert (recorded["kind"], recorded["in_final_schema"]) == ("computed", False)
    hole = _node(document, "commission@2")
    assert (hole["kind"], hole["version"], hole["in_final_schema"]) == (
        "hole",
        2,
        True,
    )
    assert (hole["formula"], hole["provenance"], hole["reads"]) == (None, None, [])
    assert hole["source_location"].endswith(f"{_HERE}:{written}")
    assert [(entry["column"], entry["reason"]) for entry in document["holes"]] == [
        ("commission", "overwritten")
    ]
    assert validate_artifact(document).ok


def test_a_calculation_written_after_the_overwrite_reads_the_hole() -> None:
    """What the later line reads is the write's column, so that is its edge."""
    af, _calculated, _written = _commission_overwritten()
    af.net = af.premium - af.commission

    document = _document(af)

    assert _node(document, "net@1")["reads"] == ["premium", "commission@2"]


def test_an_arriving_column_overwritten_is_a_hole_of_its_own() -> None:
    """The input stays the field the data supplied; the frame holds the write."""
    af = ActuarialFrame(_BOOK)
    af._df = af._df.with_columns(pl.col("premium") * 2)  # noqa: SLF001
    af.tax = af.premium * 0.2

    holes = af.graph.holes()
    document = _document(af)

    assert [(hole.column, hole.reason) for hole in holes] == [
        ("premium", "overwritten")
    ]
    assert "arrived as an input" in holes[0].hint
    assert _node(document, "premium")["kind"] == "input"
    assert _node(document, "premium@1")["kind"] == "hole"
    assert _node(document, "tax@1")["reads"] == ["premium@1"]


def test_a_new_name_written_into_the_plan_is_still_unrecorded() -> None:
    """Nothing accounted for it before the write, so nothing was overwritten."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df.with_columns(pl.lit(1.0).alias("sneaky"))  # noqa: SLF001

    assert [(hole.column, hole.reason) for hole in af.graph.holes()] == [
        ("sneaky", "unrecorded")
    ]
    assert not any(isinstance(entry, OverwriteRecord) for entry in af._calculations)  # noqa: SLF001


def test_the_join_the_extending_skill_teaches_overwrites_nothing() -> None:
    """``af.join(rules_df, ...)`` brings its columns in under names of their own."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    rules = pl.DataFrame({"policy_id": [1, 2], "expense_loading": [0.05, 0.08]})

    af = af.join(rules, on="policy_id", how="left")
    raw = ActuarialFrame(_BOOK)
    raw.commission = raw.premium * 0.1
    raw._df = raw._df.join(rules.lazy(), on="policy_id", how="left")  # noqa: SLF001

    assert af.graph.holes() == []
    assert [(hole.column, hole.reason) for hole in raw.graph.holes()] == [
        ("expense_loading", "unrecorded")
    ]
    for frame in (af, raw):
        assert not any(
            isinstance(entry, OverwriteRecord)
            for entry in frame._calculations  # noqa: SLF001
        )


def test_a_name_dropped_and_joined_back_in_one_write_is_overwritten() -> None:
    """The join brings a column in under a name the write had just freed."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    replacement = pl.DataFrame({"policy_id": [1, 2], "premium": [7.0, 8.0]})
    af._df = af._df.drop("premium").join(  # noqa: SLF001
        replacement.lazy(), on="policy_id", how="left"
    )

    assert [(hole.column, hole.reason) for hole in af.graph.holes()] == [
        ("premium", "overwritten")
    ]


def test_a_plan_rebuilt_in_the_same_shape_vouches_for_nothing() -> None:
    """The same steps over the same data, with another formula, are another plan."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = _BOOK.lazy().with_columns(  # noqa: SLF001
        (pl.col("premium") * 0.5).alias("commission")
    )

    holes = af.graph.holes()

    assert [(hole.column, hole.reason) for hole in holes] == [
        ("policy_id", "overwritten"),
        ("premium", "overwritten"),
        ("commission", "overwritten"),
    ]
    assert all("could not read" in hole.hint for hole in holes)
    assert af.collect()["commission"].to_list() == [50.0, 100.0]


def test_a_whole_frame_turned_upside_down_overwrites_nothing() -> None:
    """Every row moves, and every column with it: each row still holds its own."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df.reverse()  # noqa: SLF001

    assert af.graph.holes() == []
    assert af.collect()["commission"].to_list() == [20.0, 10.0]


@pytest.mark.parametrize("strict", [True, False])
def test_a_column_cast_to_its_own_type_overwrites_nothing(strict: bool) -> None:  # noqa: FBT001
    """A cast to the type a column already has leaves every value where it was."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df.with_columns(  # noqa: SLF001
        pl.col("commission").cast(pl.Float64, strict=strict)
    )

    assert af.graph.holes() == []


def test_a_column_cast_to_another_type_is_overwritten() -> None:
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df.with_columns(pl.col("commission").cast(pl.Float32))  # noqa: SLF001

    assert [(hole.column, hole.reason) for hole in af.graph.holes()] == [
        ("commission", "overwritten")
    ]


def test_a_column_marked_sorted_overwrites_nothing() -> None:
    """The mark is about order, and leaves every value where it was."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df.with_columns(pl.col("commission").set_sorted())  # noqa: SLF001

    assert af.graph.holes() == []


def test_a_plan_rebuilt_over_other_injected_values_vouches_for_nothing() -> None:
    """The text prints a column of values by its name alone; its values differ."""
    af = ActuarialFrame(_BOOK)
    af["shock"] = pl.Series("shock", [0.01, 0.02])
    af._df = _BOOK.lazy().with_columns(  # noqa: SLF001
        pl.lit(pl.Series("shock", [0.5, 0.6])).alias("shock")
    )

    holes = af.graph.holes()

    assert [(hole.column, hole.reason) for hole in holes] == [
        ("policy_id", "overwritten"),
        ("premium", "overwritten"),
        ("shock", "overwritten"),
    ]
    assert all("could not read" in hole.hint for hole in holes)


def test_a_write_the_frame_cannot_read_reports_every_column_it_accounted_for() -> None:
    """It cannot say which columns moved, so it vouches for none the plan holds."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df.map_batches(lambda frame: frame)  # noqa: SLF001

    holes = af.graph.holes()

    assert [(hole.column, hole.reason) for hole in holes] == [
        ("policy_id", "overwritten"),
        ("premium", "overwritten"),
        ("commission", "overwritten"),
    ]
    assert all("could not read" in hole.hint for hole in holes)


def test_values_handed_back_as_the_plan_are_told_to_materialize() -> None:
    """A collect handed back as the plan is a freeze the frame could not see."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df.collect().lazy()  # noqa: SLF001

    holes = af.graph.holes()

    assert [(hole.column, hole.reason) for hole in holes] == [
        ("policy_id", "overwritten"),
        ("premium", "overwritten"),
        ("commission", "overwritten"),
    ]
    assert all("af.materialize()" in hole.hint for hole in holes)
    assert all("continue_from=af" in hole.hint for hole in holes)


def test_a_plan_that_does_not_resolve_overwrites_nothing() -> None:
    """``collect()`` refuses such a plan, so there is no column anybody could read."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df.select(pl.col("absent"))  # noqa: SLF001

    assert not any(isinstance(entry, OverwriteRecord) for entry in af._calculations)  # noqa: SLF001


def test_handing_back_the_plan_the_frame_holds_overwrites_nothing() -> None:
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df  # noqa: SLF001

    assert af.graph.holes() == []


def test_a_second_write_over_an_overwritten_column_adds_nothing() -> None:
    """The frame already says it cannot account for the column after the first."""
    af, _calculated, written = _commission_overwritten()
    af._df = af._df.with_columns(pl.lit(1.0).alias("commission"))  # noqa: SLF001

    overwrites = [
        entry
        for entry in af._calculations  # noqa: SLF001
        if isinstance(entry, OverwriteRecord)
    ]
    assert [(entry.column, entry.ordinal) for entry in overwrites] == [
        ("commission", 2)
    ]
    assert f"{_HERE}:{written}" in af.graph.holes()[0].hint


def test_an_assignment_after_the_overwrite_leaves_the_write_as_history() -> None:
    """The frame holds the new calculation; the write stays a hole a reader can see."""
    af, _calculated, _written = _commission_overwritten()
    af.commission = af.premium * 0.2

    document = _document(af)

    assert _node(document, "commission@3")["in_final_schema"] is True
    assert _node(document, "commission@2")["in_final_schema"] is False
    assert [(entry["column"], entry["reason"]) for entry in document["holes"]] == [
        ("commission", "overwritten")
    ]
    assert validate_artifact(document).ok


def test_two_overwrites_of_one_column_are_one_unaccounted_name() -> None:
    """Two hole nodes, one entry, and a graph fingerprint the validator reproduces."""
    af, _calculated, _written = _commission_overwritten()
    af.commission = af.premium * 0.2
    af._df = af._df.with_columns(pl.lit(2.0).alias("commission"))  # noqa: SLF001

    document = _document(af)

    holes = [node["id"] for node in document["nodes"] if node["kind"] == "hole"]
    assert holes == ["commission@2", "commission@4"]
    assert [entry["column"] for entry in document["holes"]] == ["commission"]
    assert validate_artifact(document).ok


# --- what reading a write costs -------------------------------------------------


@pytest.fixture
def plans_read(monkeypatch: pytest.MonkeyPatch) -> list[pl.LazyFrame]:
    """Record every plan the frame reads to tell what a write defined."""
    read: list[pl.LazyFrame] = []
    reading = plan_writes.read_plan

    def counted(plan: pl.LazyFrame) -> plan_writes.PlanReading:
        read.append(plan)
        return reading(plan)

    monkeypatch.setattr(plan_writes, "read_plan", counted)
    return read


def test_a_write_after_a_write_reads_only_the_new_plan(
    plans_read: list[pl.LazyFrame],
) -> None:
    """The plan the first write left was read then, and is not read again."""
    af, _calculated, _written = _commission_overwritten()
    plans_read.clear()

    af._df = af._df.with_columns(pl.lit(1.0).alias("premium"))  # noqa: SLF001

    assert len(plans_read) == 1
    assert [hole.column for hole in af.graph.holes()] == ["commission", "premium"]


def test_a_write_after_another_door_reads_both_plans(
    plans_read: list[pl.LazyFrame],
) -> None:
    """A plan the frame set through its own door was never read, so it is read now."""
    af, _calculated, _written = _commission_overwritten()
    af.loading = af.premium * 0.05
    plans_read.clear()

    af._df = af._df.with_columns(pl.lit(1.0).alias("loading"))  # noqa: SLF001

    assert len(plans_read) == 2
    assert [hole.column for hole in af.graph.holes()] == ["commission", "loading"]


# --- what a write the frame cannot see stays ------------------------------------


def test_a_write_around_the_frame_s_own_handle_is_not_seen() -> None:
    """The limit stated on ``holes()``: storage written directly is not read."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    plan = af._df  # noqa: SLF001
    assert plan is not None
    object.__setattr__(
        af,
        "_ActuarialFrame__df",
        plan.with_columns(pl.lit(0.0).alias("commission")),
    )

    assert af.graph.holes() == []


# --- the second engine ----------------------------------------------------------


def test_a_second_engine_is_told_the_line_that_wrote_the_column() -> None:
    """The refusal names the write's line and the assignment that would record it."""
    af, _calculated, written = _commission_overwritten()
    af.net = af.premium - af.commission

    document = json.loads(GraphExporter(af).export(profile="executable"))
    findings = [
        finding
        for finding in inspect_execution(document).findings
        if finding.code == "unavailable_calculation"
    ]

    assert [finding.where for finding in findings] == ["/nodes/commission@2"]
    assert f"{_HERE}:{written}" in findings[0].message
    assert findings[0].move is not None
    assert "af['commission'] = ..." in findings[0].move
