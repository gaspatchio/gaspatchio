# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A plan YAML cannot hold refuses before it touches the file.

``ScenarioRun.to_yaml`` opened its path for writing and only then built the
recipe, so a plan the recipe had no form for left a 0-byte file behind -- or
truncated the one already there. The refusal now comes first and leaves the
file as it was. Every shock kind has a recipe form now, so what a recipe
cannot hold is an aggregator built with ``.of(expr)``: a Polars expression
does not round-trip through YAML.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.scenarios import ScenarioRun, Sum
from gaspatchio.scenarios.shocks import ClipShock, MultiplicativeShock

if TYPE_CHECKING:
    from pathlib import Path


def _plan(*, expression_aggregator: bool = True) -> ScenarioRun:
    total = Sum("value").alias("total")
    return ScenarioRun(
        shocks={
            "BASE": [],
            "UP": [MultiplicativeShock(factor=1.5, table="yaml_refusal_mortality")],
            "CAPPED": [ClipShock(max_value=0.001, table="yaml_refusal_mortality")],
        },
        aggregations=(
            Sum.of(pl.col("value") * 2).alias("total")
            if expression_aggregator
            else total,
        ),
    )


def test_unwritable_plan_creates_no_file(tmp_path: Path) -> None:
    """No 0-byte file is left where the plan could not be written."""
    out = tmp_path / "plan.yaml"
    with pytest.raises(NotImplementedError):
        _plan().to_yaml(out)
    assert not out.exists()


def test_unwritable_plan_leaves_an_existing_file_alone(tmp_path: Path) -> None:
    """A recipe already on disk is not truncated by a refused write."""
    out = tmp_path / "plan.yaml"
    out.write_text("scenarios: []\n", encoding="utf-8")
    with pytest.raises(NotImplementedError):
        _plan().to_yaml(out)
    assert out.read_text(encoding="utf-8") == "scenarios: []\n"


def test_the_refusal_names_the_expression_aggregator() -> None:
    """The message names what a recipe cannot hold, in the user's terms."""
    with pytest.raises(NotImplementedError) as info:
        _plan().to_dict()
    msg = str(info.value)
    assert ".of(expr)" in msg
    assert "_agg_to_dict" not in msg
    assert "v0.2" not in msg


def test_a_clip_shock_is_written_and_read_back_to_the_same_plan(tmp_path: Path) -> None:
    """The shock a recipe used to refuse is written, and keeps the plan's SHA."""
    plan = _plan(expression_aggregator=False)
    out = tmp_path / "plan.yaml"
    plan.to_yaml(out)
    assert ScenarioRun.from_yaml(out).source_sha() == plan.source_sha()
