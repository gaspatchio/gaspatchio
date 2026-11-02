# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Where a model froze its plan, and which columns were frozen when it did.

Freezing a plan keeps every formula and turns every value into data. That
is the one event in a model's history that changes what a column *is*
without changing what it says: downstream of the freeze a computed reserve
behaves like a figure the model was handed, and a reviewer reading only the
number would take it for one. These tests hold the export to saying both
halves -- where each freeze happened, and which definitions it settled.
"""

from __future__ import annotations

import json
from inspect import currentframe
from typing import TYPE_CHECKING, Any, NamedTuple

import polars as pl

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    import pytest


class _FrozenModel(NamedTuple):
    """One exported artifact, and the line in this file its model froze on.

    The line travels with the artifact because that is what the assertion
    is about: a boundary that cannot be pointed back at the statement that
    caused it is a boundary a reviewer cannot check.
    """

    artifact: dict[str, Any]
    freeze_line: int


def _artifact(frame: ActuarialFrame) -> dict[str, Any]:
    """Return ``frame``'s exported artifact, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export())
    return artifact


def _node(artifact: dict[str, Any], node_id: str) -> dict[str, Any]:
    """Return the one node of ``artifact`` carrying ``node_id``."""
    found = [node for node in artifact["nodes"] if node["id"] == node_id]
    assert found, f"{node_id!r} is not in {[n['id'] for n in artifact['nodes']]}"
    return found[0]


def _policy_frame() -> ActuarialFrame:
    """Return two arriving columns a claim can be struck from."""
    return ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )


def _artifact_for_a_two_column_model() -> dict[str, Any]:
    """Return the artifact for a model that never froze its plan."""
    frame = _policy_frame()
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return _artifact(frame)


def _model_that_freezes_once() -> _FrozenModel:
    """Return a model that freezes one claim column and then writes a reserve."""
    frame = _policy_frame()
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    freeze_line = currentframe().f_lineno + 1
    frame = frame.materialize()
    frame.reserve = frame.death_claims * 0.9
    return _FrozenModel(_artifact(frame), freeze_line)


def _artifact_for_a_model_that_redefines_after_freezing() -> dict[str, Any]:
    """Return the artifact for a model that rewrites one column after the freeze."""
    frame = ActuarialFrame(
        pl.DataFrame({"opening_policies": [1000.0, 500.0], "lapse_rate": [0.05, 0.07]})
    )
    frame.policies_in_force = frame.opening_policies * (1 - frame.lapse_rate)
    frame = frame.materialize()
    frame.policies_in_force = frame.policies_in_force * 0.99
    return _artifact(frame)


def _artifact_for_a_model_that_freezes_twice() -> dict[str, Any]:
    """Return the artifact for a model with a freeze either side of one column."""
    frame = _policy_frame()
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    frame = frame.materialize()
    frame.acquisition_expenses = frame.sum_assured * 0.01
    frame = frame.materialize()
    return _artifact(frame)


def _punch_a_hole(frame: ActuarialFrame) -> None:
    """Write ``lapse_reserve`` straight into the plan, past every recording door.

    The framework never sees the assignment, so nothing records it: the
    column is in the plan, and in the schema the plan resolves to, and
    nowhere the producer can read an account of it from.
    """
    plan = frame._df  # noqa: SLF001 -- the bypass a hole is made of
    assert plan is not None
    frame._df = plan.with_columns(  # noqa: SLF001
        (pl.col("sum_assured") * 0.02).alias("lapse_reserve")
    )


def _artifact_for_a_model_holed_before_the_freeze() -> dict[str, Any]:
    """Return the artifact for a model whose hole was on the frame when it froze."""
    frame = _policy_frame()
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    _punch_a_hole(frame)
    return _artifact(frame.materialize())


def _artifact_for_a_model_holed_after_the_freeze() -> dict[str, Any]:
    """Return the artifact for a model whose hole was punched after the freeze."""
    frame = _policy_frame()
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    frame = frame.materialize()
    frame.reserve = frame.death_claims * 0.9
    _punch_a_hole(frame)
    return _artifact(frame)


# --- the section itself ------------------------------------------------------


def test_a_model_that_never_froze_its_plan_has_no_boundaries() -> None:
    """The empty section is the claim: every value here is still a recipe."""
    artifact = _artifact_for_a_two_column_model()

    assert artifact["boundaries"] == []
    assert all(node["materialized_at"] is None for node in artifact["nodes"])


def test_a_frozen_plan_is_a_boundary_the_artifact_can_point_at() -> None:
    """A freeze a reviewer cannot locate is a freeze they cannot check."""
    model = _model_that_freezes_once()

    (boundary,) = model.artifact["boundaries"]

    assert boundary["ordinal"] == 0
    assert boundary["source_location"] == (
        f"bindings/python/tests/graph/test_artifact_boundaries.py:{model.freeze_line}"
    )


def test_a_boundary_says_where_in_the_model_s_own_steps_it_fell() -> None:
    """Which definitions fell before the freeze is read off its position."""
    model = _model_that_freezes_once()

    (boundary,) = model.artifact["boundaries"]

    assert boundary["position"] == 1


def test_two_freezes_are_two_boundaries_numbered_in_the_order_they_happened() -> None:
    """The ordinal counts from zero, which is what a node's stamp names.

    The positions are pinned alongside, because they are what a reader
    sorts the model's steps by and an ordinal alone would not catch a
    producer that mislocated either freeze.
    """
    artifact = _artifact_for_a_model_that_freezes_twice()

    assert [boundary["ordinal"] for boundary in artifact["boundaries"]] == [0, 1]
    # The second freeze is at 3, not 2: the record of the model's steps is
    # one entry per event, and the first boundary is an event of its own.
    # So the count runs claim, freeze, expense, freeze.
    assert [boundary["position"] for boundary in artifact["boundaries"]] == [1, 3]


def test_the_boundary_the_producer_writes_is_the_boundary_the_format_defines() -> None:
    """The section's shape lives in the published schema, not only in prose."""
    import jsonschema

    from gaspatchio.schemas import load_schema

    validator = jsonschema.Draft202012Validator(load_schema()["$defs"]["boundary"])
    boundaries = _model_that_freezes_once().artifact["boundaries"]

    assert boundaries
    for boundary in boundaries:
        assert not list(validator.iter_errors(boundary))


def test_a_freeze_the_producer_could_not_locate_reports_no_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A null says the producer looked and found nothing, never that it guessed."""
    monkeypatch.setenv("GASPATCHIO_SOURCE_SPANS", "off")

    (boundary,) = _model_that_freezes_once().artifact["boundaries"]

    assert boundary["source_location"] is None
    assert boundary["ordinal"] == 0


# --- which columns the freeze settled ----------------------------------------


def test_every_column_live_at_the_freeze_says_it_was_frozen() -> None:
    """A frozen computed column is data downstream, and the node says which it is."""
    artifact = _model_that_freezes_once().artifact

    assert _node(artifact, "death_claims@1")["materialized_at"] == 0
    assert _node(artifact, "reserve@1")["materialized_at"] is None


def test_a_column_the_data_arrived_with_was_settled_by_the_freeze_too() -> None:
    """Every column live at the freeze was frozen, whatever account it gives."""
    artifact = _model_that_freezes_once().artifact

    assert _node(artifact, "sum_assured")["materialized_at"] == 0


def test_a_column_redefined_after_the_freeze_carries_it_on_the_old_version() -> None:
    """The definition that was frozen is the one that was live when it happened."""
    artifact = _artifact_for_a_model_that_redefines_after_freezing()

    assert _node(artifact, "policies_in_force@1")["materialized_at"] == 0
    assert _node(artifact, "policies_in_force@2")["materialized_at"] is None


def test_a_column_live_at_two_freezes_reports_the_later_one() -> None:
    """One number per node, and the useful one is the last freeze it survived."""
    artifact = _artifact_for_a_model_that_freezes_twice()

    assert _node(artifact, "death_claims@1")["materialized_at"] == 1
    assert _node(artifact, "acquisition_expenses@1")["materialized_at"] == 1


def test_a_hole_on_the_frame_when_it_froze_still_reports_no_freeze() -> None:
    """A producer that cannot account for a value cannot date it either.

    The column was on the frame when the plan was frozen, so a freeze did
    settle whatever it held. But nothing in the model accounts for the
    column, and that is exactly what leaves the producer unable to tell
    this case from the one below it. Reporting the ordinal here would put
    the order the producer happened to seed the hole in front of a reader
    as though it were something observed, and would give two situations it
    cannot distinguish two different answers. Null says the producer looked
    and had nothing to go on, which is the truth in both.
    """
    artifact = _artifact_for_a_model_holed_before_the_freeze()

    hole = _node(artifact, "lapse_reserve")

    assert hole["kind"] == "hole"
    assert hole["materialized_at"] is None
    # Skipping the hole is the only exclusion: everything else the freeze
    # settled still says so.
    assert _node(artifact, "death_claims@1")["materialized_at"] == 0
    assert _node(artifact, "sum_assured")["materialized_at"] == 0


def test_a_hole_punched_after_the_freeze_reports_no_freeze_either() -> None:
    """The freeze was over, and the column the plan then gained is not its doing.

    Written straight into the plan two statements past the freeze, so no
    freeze can have settled it -- and the producer, which never saw the
    write, has no way of knowing that. Every hole is seeded before the log
    is walked, which puts this column in the frame's live set at the freeze
    exactly as the one above sits there. Null is the answer both cases have
    to give, and the reader tells them apart from a frozen input by reading
    ``kind`` alongside.
    """
    artifact = _artifact_for_a_model_holed_after_the_freeze()

    hole = _node(artifact, "lapse_reserve")

    assert hole["kind"] == "hole"
    assert hole["materialized_at"] is None
    assert _node(artifact, "reserve@1")["materialized_at"] is None
