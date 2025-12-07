# ABOUTME: End-to-end integration test for the complete shock workflow.
# ABOUTME: Tests sensitivity_analysis -> Table.from_shocks -> describe_scenarios.

"""End-to-end integration test for the complete shock workflow."""

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core import (
    ActuarialFrame,
    Table,
    describe_scenarios,
    sensitivity_analysis,
    with_scenarios,
)
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
)


class TestFullShockWorkflow:
    """End-to-end tests for complete shock workflow."""

    def test_sensitivity_analysis_to_shocked_tables(self, tmp_path: Path):
        """Full workflow: sensitivity_analysis -> from_shocks -> lookups."""
        # Step 1: Create base mortality assumption table
        mortality_df = pl.DataFrame(
            {
                "age": [30, 40, 50, 60],
                "qx": [0.001, 0.002, 0.005, 0.012],
            }
        )
        mortality_path = tmp_path / "mortality.parquet"
        mortality_df.write_parquet(mortality_path)

        base_mortality = Table(
            name="mortality",
            source=mortality_path,
            dimensions={"age": "age"},
            value="qx",
        )

        # Step 2: Generate shock specifications using sensitivity_analysis
        shocks = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=[0.8, 1.0, 1.2],
            include_base=True,
        )

        # Step 3: Create shocked tables
        mortality_tables = Table.from_shocks(base_mortality, shocks, value_column="qx")

        # Step 4: Verify we have the right tables
        assert len(mortality_tables) == 4  # BASE + 3 sensitivity scenarios
        assert "BASE" in mortality_tables
        assert "mortality_0.8" in mortality_tables
        assert "mortality_1.0" in mortality_tables
        assert "mortality_1.2" in mortality_tables

        # Step 5: Verify shocked values are correct
        base_data = mortality_tables["mortality_1.0"].to_dataframe()
        up_data = mortality_tables["mortality_1.2"].to_dataframe()
        down_data = mortality_tables["mortality_0.8"].to_dataframe()

        # At age 30: base=0.001, up=0.0012, down=0.0008
        assert base_data.filter(pl.col("age") == 30)["qx"][0] == pytest.approx(0.001)
        assert up_data.filter(pl.col("age") == 30)["qx"][0] == pytest.approx(0.0012)
        assert down_data.filter(pl.col("age") == 30)["qx"][0] == pytest.approx(0.0008)

    def test_shocked_tables_work_with_lookups(self, tmp_path: Path):
        """Shocked tables can be used for assumption lookups."""
        # Create base table
        rates_df = pl.DataFrame(
            {
                "term": [1, 2, 3, 4, 5],
                "rate": [0.05, 0.06, 0.07, 0.08, 0.09],
            }
        )
        rates_path = tmp_path / "rates.parquet"
        rates_df.write_parquet(rates_path)

        base_rates = Table(
            name="rates",
            source=rates_path,
            dimensions={"term": "term"},
            value="rate",
        )

        # Create stressed version
        shock = MultiplicativeShock(factor=1.5)
        stressed_rates = base_rates.with_shock(shock)

        # Use both tables in lookups
        test_df = pl.DataFrame({"term": [1, 3, 5]})

        base_lookup = test_df.select(
            base_rates.lookup(term=pl.col("term")).alias("base_rate")
        )
        stressed_lookup = test_df.select(
            stressed_rates.lookup(term=pl.col("term")).alias("stressed_rate")
        )

        assert base_lookup["base_rate"].to_list() == pytest.approx([0.05, 0.07, 0.09])
        assert stressed_lookup["stressed_rate"].to_list() == pytest.approx(
            [0.075, 0.105, 0.135]
        )

    def test_describe_scenarios_generates_audit_trail(self):
        """describe_scenarios produces audit trail from sensitivity_analysis."""
        # Generate shocks
        shocks = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=[0.9, 1.0, 1.1],
        )

        # Generate audit trail
        description = describe_scenarios(shocks)

        # Verify audit content
        assert "mortality_0.9" in description
        assert "mortality_1.0" in description
        assert "mortality_1.1" in description
        assert "mortality" in description.lower()
        assert "0.9" in description

        # Also test dict format
        dict_result = describe_scenarios(shocks, output_format="dict")
        assert len(dict_result) == 3
        assert all(isinstance(v, list) for v in dict_result.values())


class TestShockWorkflowWithScenarios:
    """Tests combining shocks with scenario expansion."""

    def test_shocked_tables_with_scenario_expansion(self, tmp_path: Path):
        """Use shocked tables with ActuarialFrame scenario expansion."""
        # Create base mortality table
        mortality_df = pl.DataFrame(
            {
                "age": [30, 40, 50],
                "qx": [0.001, 0.002, 0.005],
            }
        )
        mortality_path = tmp_path / "mortality.parquet"
        mortality_df.write_parquet(mortality_path)

        base_mortality = Table(
            name="mortality",
            source=mortality_path,
            dimensions={"age": "age"},
            value="qx",
        )

        # Create policy data
        policies = pl.DataFrame(
            {
                "policy_id": ["P001", "P002"],
                "age": [30, 50],
            }
        )

        # Create ActuarialFrame with scenarios
        af = ActuarialFrame(policies)
        af_with_scenarios = with_scenarios(af, ["BASE", "STRESSED"])

        # Create scenario-specific tables
        shocks = {
            "BASE": [],
            "STRESSED": [MultiplicativeShock(factor=1.5)],
        }
        mortality_tables = Table.from_shocks(base_mortality, shocks, value_column="qx")

        # Verify frame has scenarios
        result_df = af_with_scenarios.collect()
        assert "scenario_id" in result_df.columns
        assert len(result_df) == 4  # 2 policies * 2 scenarios

        # Verify both tables are usable
        assert mortality_tables["BASE"] is not None
        assert mortality_tables["STRESSED"] is not None

    def test_multiple_shocked_tables_for_scenarios(self, tmp_path: Path):
        """Create multiple shocked assumption tables for different scenarios."""
        # Create mortality table
        mort_df = pl.DataFrame({"age": [30, 40], "qx": [0.001, 0.002]})
        mort_path = tmp_path / "mort.parquet"
        mort_df.write_parquet(mort_path)
        base_mortality = Table(
            name="mortality", source=mort_path, dimensions={"age": "age"}, value="qx"
        )

        # Create lapse table
        lapse_df = pl.DataFrame({"year": [1, 2], "rate": [0.10, 0.08]})
        lapse_path = tmp_path / "lapse.parquet"
        lapse_df.write_parquet(lapse_path)
        base_lapse = Table(
            name="lapse", source=lapse_path, dimensions={"year": "year"}, value="rate"
        )

        # Define scenarios with different shocks to different tables
        mortality_shocks = {
            "BASE": [],
            "MORTALITY_UP": [MultiplicativeShock(factor=1.3)],
            "MORTALITY_DOWN": [MultiplicativeShock(factor=0.7)],
        }
        lapse_shocks = {
            "BASE": [],
            "LAPSE_UP": [AdditiveShock(delta=0.05)],
            "LAPSE_DOWN": [AdditiveShock(delta=-0.05)],
        }

        # Create all shocked tables
        mort_tables = Table.from_shocks(base_mortality, mortality_shocks, "qx")
        lapse_tables = Table.from_shocks(base_lapse, lapse_shocks, "rate")

        # Verify
        assert len(mort_tables) == 3
        assert len(lapse_tables) == 3

        # Check values
        mort_up = mort_tables["MORTALITY_UP"].to_dataframe()
        assert mort_up.filter(pl.col("age") == 30)["qx"][0] == pytest.approx(0.0013)

        lapse_up = lapse_tables["LAPSE_UP"].to_dataframe()
        assert lapse_up.filter(pl.col("year") == 1)["rate"][0] == pytest.approx(0.15)


class TestAuditTrailIntegration:
    """Tests for audit trail generation in workflow."""

    def test_complete_audit_trail(self):
        """Generate complete audit trail for all scenario configurations."""
        # Define multiple scenarios with different shock types
        scenarios = {
            "BASE": [],
            "MORT_UP_20": [MultiplicativeShock(factor=1.2, table="mortality")],
            "MORT_DOWN_20": [MultiplicativeShock(factor=0.8, table="mortality")],
            "RATES_UP_100BP": [AdditiveShock(delta=0.01, table="discount_rates")],
            "COMBINED_STRESS": [
                MultiplicativeShock(factor=1.3, table="mortality"),
                AdditiveShock(delta=0.02, table="discount_rates"),
            ],
        }

        # Generate audit trail
        audit = describe_scenarios(scenarios)

        # Verify all scenarios documented
        assert "BASE" in audit
        assert "MORT_UP_20" in audit
        assert "MORT_DOWN_20" in audit
        assert "RATES_UP_100BP" in audit
        assert "COMBINED_STRESS" in audit

        # Verify shock details included
        assert "1.2" in audit  # Mortality up factor
        assert "0.8" in audit  # Mortality down factor
        assert "0.01" in audit  # Rates delta
        assert "1.3" in audit  # Combined mortality
        assert "0.02" in audit  # Combined rates

        # Verify table names included
        assert "mortality" in audit
        assert "discount_rates" in audit

    def test_audit_trail_text_format(self):
        """Audit trail in text format is readable."""
        shocks = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=[0.9, 1.0, 1.1],
        )

        text_audit = describe_scenarios(shocks, output_format="text")

        assert isinstance(text_audit, str)
        assert "Scenario Configuration" in text_audit
        assert "mortality_0.9" in text_audit


def test_workflow_imports():
    """All workflow functions are importable from top level."""
    from gaspatchio_core import (
        Table,
        describe_scenarios,
        sensitivity_analysis,
        with_scenarios,
    )

    assert callable(sensitivity_analysis)
    assert callable(describe_scenarios)
    assert callable(with_scenarios)
    assert hasattr(Table, "from_shocks")
    assert hasattr(Table, "with_shock")
