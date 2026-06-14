# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: SLF001, PD901, D103
"""Test stack_shocked_table for batched per-scenario shocks."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios._stack import stack_shocked_table
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
)


@pytest.fixture
def mortality_table() -> Table:
    df = pl.DataFrame(
        {
            "age": [30, 31, 32],
            "rate": [0.001, 0.0012, 0.0015],
        }
    )
    return Table(
        name="mortality_stack_fixture",
        source=df,
        dimensions={"age": "age"},
        value="rate",
    )


def test_stack_adds_scenario_id_dimension(mortality_table: Table) -> None:
    per_scenario = {
        "BASE": [],
        "STRESS": [MultiplicativeShock(factor=1.5)],
    }
    stacked = stack_shocked_table(mortality_table, per_scenario)

    assert "scenario_id" in stacked._dimensions
    df = stacked._materialised_df()
    assert set(df["scenario_id"].unique().to_list()) == {"BASE", "STRESS"}
    assert df.height == 6  # 3 ages x 2 scenarios


def test_stack_applies_per_scenario_shock(mortality_table: Table) -> None:
    per_scenario = {
        "BASE": [],
        "STRESS": [MultiplicativeShock(factor=2.0)],
    }
    stacked = stack_shocked_table(mortality_table, per_scenario)
    df = stacked._materialised_df().sort(["scenario_id", "age"])

    base = df.filter(pl.col("scenario_id") == "BASE")["rate"].to_list()
    stress = df.filter(pl.col("scenario_id") == "STRESS")["rate"].to_list()

    assert base == [0.001, 0.0012, 0.0015]
    assert stress == [pytest.approx(0.002), pytest.approx(0.0024), pytest.approx(0.003)]


def test_stack_heterogeneous_shocks(mortality_table: Table) -> None:
    per_scenario = {
        "A": [MultiplicativeShock(factor=1.5)],
        "B": [AdditiveShock(delta=0.001)],
        "C": [],
    }
    stacked = stack_shocked_table(mortality_table, per_scenario)
    df = stacked._materialised_df().sort(["scenario_id", "age"])

    a = df.filter(pl.col("scenario_id") == "A")["rate"].to_list()
    b = df.filter(pl.col("scenario_id") == "B")["rate"].to_list()
    c = df.filter(pl.col("scenario_id") == "C")["rate"].to_list()

    assert a == [pytest.approx(0.0015), pytest.approx(0.0018), pytest.approx(0.00225)]
    assert b == [pytest.approx(0.002), pytest.approx(0.0022), pytest.approx(0.0025)]
    assert c == [0.001, 0.0012, 0.0015]


def test_stack_preserves_value_column(mortality_table: Table) -> None:
    per_scenario: dict[str, list] = {"X": []}
    stacked = stack_shocked_table(mortality_table, per_scenario)
    assert stacked._value == "rate"
