# ABOUTME: Integration tests for complete scenario workflows.
# ABOUTME: Tests the full pattern: model points + scenarios + lookups + aggregation.

"""Integration tests for complete scenario workflows."""

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios import with_scenarios


class TestScenarioWorkflowIntegration:
    """End-to-end tests for scenario-aware model execution."""

    @pytest.fixture
    def scenario_rates_table(self, tmp_path: Path) -> Table:
        """Create a discount rates table with scenario dimension."""
        scenarios = {
            "BASE": [0.03, 0.035, 0.04],
            "UP": [0.04, 0.045, 0.05],
            "DOWN": [0.02, 0.025, 0.03],
        }

        for scenario_id, rates in scenarios.items():
            scenario_df = pl.DataFrame(
                {
                    "year": [1, 2, 3],
                    "rate": rates,
                }
            )
            scenario_df.write_parquet(tmp_path / f"{scenario_id}_rates.parquet")

        return Table.from_scenario_files(
            scenario_files={
                "BASE": tmp_path / "BASE_rates.parquet",
                "UP": tmp_path / "UP_rates.parquet",
                "DOWN": tmp_path / "DOWN_rates.parquet",
            },
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates_integration",
        )

    def test_full_scenario_workflow(self, scenario_rates_table):
        """Test: model points x scenarios -> lookup -> aggregate by scenario."""
        # === 1. Create model points ===
        model_points = {
            "policy_id": [1, 2],
            "premium": [1000.0, 2000.0],
            "year": [1, 2],
        }
        af = ActuarialFrame(model_points)

        # === 2. Expand across scenarios ===
        af = with_scenarios(af, ["BASE", "UP", "DOWN"])

        # Should have 2 policies x 3 scenarios = 6 rows
        assert len(af.collect()) == 6

        # === 3. Lookup scenario-varying rates ===
        af.disc_rate = scenario_rates_table.lookup(
            scenario_id=af.scenario_id,
            year=af.year,
        )

        # === 4. Simple calculation ===
        af.discounted_premium = af.premium * (1 - af.disc_rate)

        # === 5. Verify results ===
        result_df = af.collect()

        # Check we have all scenarios
        assert set(result_df["scenario_id"].unique().to_list()) == {
            "BASE",
            "UP",
            "DOWN",
        }

        # Check lookup worked correctly
        base_p1 = result_df.filter(
            (pl.col("scenario_id") == "BASE") & (pl.col("policy_id") == 1)
        )
        assert base_p1["disc_rate"].item() == pytest.approx(0.03)
        assert base_p1["discounted_premium"].item() == pytest.approx(1000.0 * 0.97)

    def test_scenario_aggregation(self, scenario_rates_table):
        """Test: aggregate results by scenario for risk metrics."""
        # Arrange
        af = ActuarialFrame(
            {
                "policy_id": [1, 2, 3],
                "premium": [100.0, 200.0, 300.0],
                "year": [1, 1, 1],
            }
        )

        # Act
        af = with_scenarios(af, ["BASE", "UP", "DOWN"])
        af.disc_rate = scenario_rates_table.lookup(
            scenario_id=af.scenario_id,
            year=af.year,
        )
        af.pv_premium = af.premium * (1 - af.disc_rate)

        result_df = af.collect()
        by_scenario = result_df.group_by("scenario_id").agg(
            [
                pl.col("pv_premium").sum().alias("total_pv_premium"),
            ]
        )

        # Assert: BASE year 1 rate = 0.03, sum = 600 * (1 - 0.03) = 582
        base_total = by_scenario.filter(pl.col("scenario_id") == "BASE")[
            "total_pv_premium"
        ].item()
        assert base_total == pytest.approx(582.0)

    def test_scenario_ready_by_default_pattern(self, scenario_rates_table):
        """Test: single scenario model uses same pattern as multi-scenario."""
        # Arrange
        af = ActuarialFrame(
            {
                "policy_id": [1],
                "premium": [1000.0],
                "year": [1],
            }
        )

        # Act
        af = with_scenarios(af, ["BASE"])
        af.disc_rate = scenario_rates_table.lookup(
            scenario_id=af.scenario_id,
            year=af.year,
        )
        af.result = af.premium * (1 - af.disc_rate)

        # Assert
        result_df = af.collect()
        assert len(result_df) == 1
        assert result_df["scenario_id"].item() == "BASE"
        assert result_df["result"].item() == pytest.approx(970.0)
