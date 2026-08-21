# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: SLF001, PD901, D103
"""Test stack_shocked_table for batched per-scenario shocks."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio.assumptions import Table
from gaspatchio.scenarios._stack import stack_shocked_table
from gaspatchio.scenarios.shocks import (
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


class TestScenarioAxisGuard:
    """A base table already carrying scenario_id is refused, not collapsed (#52).

    Stacking stamps ``pl.lit(sid)`` over ``scenario_id`` — a table that
    already carries one as a dimension would have every original scenario's
    rows silently collapsed onto the batch key. Pre-#17 strict builds this
    produced silently wrong numbers (the shipped scenarios docs example
    priced every scenario at the UP rate); after, a confusing
    ``Duplicate key combination`` error far from the cause. Per *Sharp
    knives, no magic*: refuse at the boundary, naming the axis and both
    remedies.
    """

    @pytest.fixture
    def scenario_keyed_table(self) -> Table:
        """Build a table whose rows are keyed by an existing scenario axis."""
        df = pl.DataFrame(
            {
                "scenario_id": ["BASE", "UP"],
                "year": [0, 0],
                "rate": [0.03, 0.05],
            }
        )
        return Table(
            name="disc_rates_axis_guard_fixture",
            source=df,
            dimensions={"scenario_id": "scenario_id", "year": "year"},
            value="rate",
        )

    def test_scenario_keyed_base_table_is_refused(
        self, scenario_keyed_table: Table
    ) -> None:
        """Stacking a scenario_id-carrying table raises instead of collapsing."""
        with pytest.raises(ValueError, match="scenario_id"):
            stack_shocked_table(scenario_keyed_table, {"BASE": [], "UP": []})

    def test_error_names_table_and_both_remedies(
        self, scenario_keyed_table: Table
    ) -> None:
        """The refusal names the table, the axis, and the two ways out."""
        with pytest.raises(ValueError, match="scenario_id") as excinfo:
            stack_shocked_table(scenario_keyed_table, {"BASE": [], "UP": []})
        msg = str(excinfo.value)
        assert "disc_rates_axis_guard_fixture" in msg
        assert "scenario-invariant" in msg
        assert "id-list" in msg or "drivers" in msg

    def test_scenario_invariant_table_still_stacks(
        self, mortality_table: Table
    ) -> None:
        """The guard leaves the contract's happy path untouched."""
        stacked = stack_shocked_table(mortality_table, {"BASE": [], "UP": []})
        assert "scenario_id" in stacked._dimensions

    def test_scenario_run_surfaces_the_guard(self) -> None:
        """ScenarioRun raises the guard, not a deep duplicate-key error."""
        from gaspatchio.scenarios import ScenarioRun, Sum

        disc_rates = Table(
            name="disc_rates_axis_guard_e2e",
            source=pl.DataFrame(
                {
                    "scenario_id": ["BASE", "UP"],
                    "year": [0, 0],
                    "rate": [0.03, 0.05],
                }
            ),
            dimensions={"scenario_id": "scenario_id", "year": "year"},
            value="rate",
        )
        from gaspatchio import ActuarialFrame

        policies = ActuarialFrame(pl.DataFrame({"policy_id": [1], "premium": [100.0]}))

        def model(af, params=None, tables=None):  # noqa: ANN202, ARG001
            af.pv = af.premium * 1.0
            return af

        with pytest.raises(ValueError, match="scenario_id") as excinfo:
            ScenarioRun(
                shocks={"BASE": [], "UP": []},
                base_tables={"disc_rates": disc_rates},
                aggregations=(Sum("pv").alias("total_pv"),),
            ).run(policies, model, batch_size=1)
        assert "Duplicate key" not in str(excinfo.value)
