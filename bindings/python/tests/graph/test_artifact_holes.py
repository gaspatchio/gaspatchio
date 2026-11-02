# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The section of the artifact that states what the model cannot account for.

A reader asking "can this model account for every column it holds?" should
answer it by reading one array, not by walking every node and classifying
it. That is what the holes section is for, and the empty array is the claim
worth making: a model that accounts for everything says so positively.

The section restates what the hole nodes already say, and the duplication is
deliberate -- the same reason the model's one digest restates the assumption
tables its lookup nodes already carry. These tests hold both halves to
agreeing, because two places that can disagree about what a model failed to
explain is worse than either place on its own.
"""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

# Where a reader who meets an unaccounted-for column is pointed. Written out
# here rather than imported from the producer: the URI is part of what the
# format promises a consumer, so a test that read it from the same constant
# the export writes would agree with any value at all.
_CLOSES_WITH = "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3#holes"


def _artifact_for_a_two_column_model() -> dict[str, Any]:
    """Return the artifact for a model whose every column has an account of itself."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export())
    return artifact


def _artifact_for_a_model_that_writes_past_the_recording_door() -> dict[str, Any]:
    """Return the artifact for a model holding one column nothing accounts for.

    ``reserve_override`` lands in the query plan, and so in the schema the
    plan resolves to, without the framework ever seeing an assignment to
    record. It is the one way a user reaches this state on purpose, and it
    is also what an unrecorded step inside the framework would look like.
    """
    frame = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0, 250_000.0]}))
    frame.death_claims = frame.sum_assured * 0.001_23
    frame._df = frame._df.with_columns(  # noqa: SLF001 — writing the plan past every recording door is what mints a hole
        (pl.col("sum_assured") * 0.02).alias("reserve_override")
    )
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export())
    return artifact


def test_a_model_that_accounts_for_everything_makes_the_empty_claim() -> None:
    """The empty holes array is the claim worth making, not an unasked question."""
    artifact = _artifact_for_a_two_column_model()

    assert artifact["holes"] == []


def test_a_column_written_straight_into_the_plan_is_a_hole_the_section_names() -> None:
    """An unaccounted-for column is answered by reading one array.

    The entry names the column, gives the one reason a producer can defend,
    and points at documentation describing what closes the hole -- so a
    reader who meets one is told what to do about it rather than only that
    it is there.
    """
    artifact = _artifact_for_a_model_that_writes_past_the_recording_door()

    assert artifact["holes"] == [
        {
            "column": "reserve_override",
            "reason": "unrecorded",
            "closes_with": _CLOSES_WITH,
        }
    ]


def test_the_section_and_the_nodes_agree() -> None:
    """The restatement has to restate: same columns, both halves of the document.

    The section exists so the question is answered by one array rather than
    by a walk over every node. That is only true while the two agree, and a
    document whose section and nodes named different columns would be worse
    than one carrying neither.
    """
    artifact = _artifact_for_a_model_that_writes_past_the_recording_door()

    from_nodes = sorted(
        node["column"] for node in artifact["nodes"] if node["kind"] == "hole"
    )

    assert from_nodes == sorted(hole["column"] for hole in artifact["holes"])
    assert from_nodes == ["reserve_override"]


def test_the_empty_section_and_the_empty_node_set_agree_too() -> None:
    """Both halves are silent on the model that accounts for everything."""
    artifact = _artifact_for_a_two_column_model()

    assert [node for node in artifact["nodes"] if node["kind"] == "hole"] == []
    assert artifact["holes"] == []


def test_the_hole_node_the_section_names_claims_no_source() -> None:
    """A hole names no source, because the absence of one is its whole content.

    An input's ``source`` is a positive claim about where the values came
    from. The column this section names is one nothing in the model accounts
    for, so every such claim is one the producer cannot make.
    """
    artifact = _artifact_for_a_model_that_writes_past_the_recording_door()

    (hole,) = [node for node in artifact["nodes"] if node["kind"] == "hole"]

    assert hole["column"] == "reserve_override"
    assert hole["provenance"] is None
    assert hole["formula"] is None
    assert hole["reads"] == []
