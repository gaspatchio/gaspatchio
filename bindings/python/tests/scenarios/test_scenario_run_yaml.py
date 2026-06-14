# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""GSP-101 ScenarioRun YAML round-trip."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest
import yaml

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios._aggregators import CTE, ArgMax, Mean, Sum
from gaspatchio_core.scenarios._run import ScenarioRun
from gaspatchio_core.scenarios.shocks import MultiplicativeShock

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def mortality_table() -> Table:
    """Tiny mortality table used as the base table across round-trip tests."""
    source = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.0012]})
    return Table(
        name="mortality",
        source=source,
        dimensions={"age": "age"},
        value="rate",
    )


def test_dict_round_trip(mortality_table: Table) -> None:
    """to_dict / from_dict round-trip preserves source_sha."""
    plan = ScenarioRun(
        shocks={
            "BASE": [],
            "STRESS": [MultiplicativeShock(factor=1.5, table="mortality")],
        },
        base_tables={"mortality": mortality_table},
        aggregations=(
            Sum("value").alias("total"),
            CTE("value", level=0.005, direction="upper").alias("scr"),
        ),
        master_seed=42,
    )
    d = plan.to_dict()
    reloaded = ScenarioRun.from_dict(d, base_tables={"mortality": mortality_table})
    assert reloaded.source_sha() == plan.source_sha()


def test_yaml_round_trip(tmp_path: Path, mortality_table: Table) -> None:
    """to_yaml / from_yaml round-trip preserves source_sha through a file."""
    plan = ScenarioRun(
        shocks={"BASE": []},
        base_tables={"mortality": mortality_table},
        aggregations=(
            Sum("value").alias("total"),
            Mean("value").alias("avg"),
        ),
    )
    out = tmp_path / "plan.yaml"
    plan.to_yaml(out)
    assert out.exists()
    reloaded = ScenarioRun.from_yaml(out, base_tables={"mortality": mortality_table})
    assert reloaded.source_sha() == plan.source_sha()


def test_yaml_round_trip_with_partitioned(
    tmp_path: Path,
    mortality_table: Table,
) -> None:
    """Partitioned aggregators (.over) round-trip recursively through YAML."""
    plan = ScenarioRun(
        shocks={"BASE": []},
        base_tables={"mortality": mortality_table},
        aggregations=(
            Sum("value").alias("total"),
            ArgMax("value").alias("worst_per_lob").over("lob"),
        ),
    )
    out = tmp_path / "plan.yaml"
    plan.to_yaml(out)
    reloaded = ScenarioRun.from_yaml(out, base_tables={"mortality": mortality_table})
    assert reloaded.source_sha() == plan.source_sha()


def test_unknown_kind_raises(tmp_path: Path, mortality_table: Table) -> None:
    """Loading YAML with an unregistered aggregator kind raises helpfully."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        yaml.safe_dump(
            {
                "scenarios": [{"id": "BASE"}],
                "aggregations": [
                    {"kind": "Mystery", "column": "v", "alias": "foo"},
                ],
            },
        ),
    )
    with pytest.raises(ValueError, match="Mystery"):
        ScenarioRun.from_yaml(bad_yaml, base_tables={"mortality": mortality_table})


def test_v0_1_format_raises(tmp_path: Path, mortality_table: Table) -> None:
    """Loading a v0.1-shaped YAML (aggregations is a dict) raises clearly."""
    v01_yaml = tmp_path / "v01.yaml"
    v01_yaml.write_text(
        yaml.safe_dump(
            {
                "scenarios": [{"id": "BASE"}],
                "aggregations": {"total": {"kind": "Sum"}},  # dict, not list
            },
        ),
    )
    with pytest.raises(ValueError, match="v0.1 plan format"):
        ScenarioRun.from_yaml(v01_yaml, base_tables={"mortality": mortality_table})
