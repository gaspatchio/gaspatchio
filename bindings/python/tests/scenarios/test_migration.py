# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Pins the v0.1 -> v0.2 migration error path for ScenarioRun YAML reloads.
"""Test that loading a v0.1-shaped plan YAML raises a pointed migration error."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from gaspatchio_core.scenarios._config import parse_aggregations

if TYPE_CHECKING:
    from pathlib import Path


def test_v01_dict_aggregations_raises_migration_error() -> None:
    """v0.1 used aggregations: {alias: {kind: ..., ...}}; v0.2 needs list-of-dict."""
    v01_spec = {
        "scr": {"kind": "Sum", "column": "loss"},
        "be": {"kind": "Mean", "column": "loss"},
    }
    with pytest.raises(ValueError, match="v0.1 plan format detected"):
        parse_aggregations(v01_spec)  # type: ignore[arg-type]


def test_v02_list_aggregations_parses() -> None:
    """v0.2 list-of-dict shape parses successfully (sanity check)."""
    v02_spec = [
        {"kind": "Sum", "alias": "total_loss", "column": "loss"},
    ]
    aggs = parse_aggregations(v02_spec)
    assert len(aggs) == 1
    # alias_ is the dataclass field set by .alias(); canonical_form fallback is safe too
    assert aggs[0].alias_ == "total_loss"  # type: ignore[union-attr]


def test_v01_yaml_file_round_trip_raises(tmp_path: Path) -> None:
    """A YAML file written in v0.1 shape raises when aggregations slice is parsed."""
    v01_yaml = tmp_path / "old_plan.yaml"
    v01_yaml.write_text(
        yaml.safe_dump({
            "aggregations": {"x": {"kind": "Sum", "column": "loss"}},
        })
    )
    loaded = yaml.safe_load(v01_yaml.read_text())
    with pytest.raises(ValueError, match="v0.1 plan format detected"):
        parse_aggregations(loaded["aggregations"])
