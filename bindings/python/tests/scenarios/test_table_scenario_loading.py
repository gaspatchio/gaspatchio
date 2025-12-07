# ABOUTME: Tests for loading assumption tables from per-scenario files.
# ABOUTME: Verifies Table.from_scenario_files() concatenates scenario files correctly.

"""Tests for Table.from_scenario_files() classmethod."""

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table


class TestTableFromScenarioFiles:
    """Tests for Table.from_scenario_files() classmethod."""

    @pytest.fixture
    def scenario_files(self, tmp_path: Path) -> dict[str, Path]:
        """Create temporary scenario files for testing."""
        # BASE scenario
        base_df = pl.DataFrame(
            {
                "year": [1, 2, 3],
                "rate": [0.03, 0.035, 0.04],
            }
        )
        base_path = tmp_path / "base_rates.parquet"
        base_df.write_parquet(base_path)

        # UP scenario (+50bps)
        up_df = pl.DataFrame(
            {
                "year": [1, 2, 3],
                "rate": [0.035, 0.04, 0.045],
            }
        )
        up_path = tmp_path / "up_rates.parquet"
        up_df.write_parquet(up_path)

        # DOWN scenario (-50bps)
        down_df = pl.DataFrame(
            {
                "year": [1, 2, 3],
                "rate": [0.025, 0.03, 0.035],
            }
        )
        down_path = tmp_path / "down_rates.parquet"
        down_df.write_parquet(down_path)

        return {
            "BASE": base_path,
            "UP": up_path,
            "DOWN": down_path,
        }

    def test_concatenates_scenario_files(self, scenario_files):
        """Should create a single table with all scenarios concatenated."""
        # Arrange & Act
        table = Table.from_scenario_files(
            scenario_files=scenario_files,
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates",
        )

        # Assert
        result_df = table.to_dataframe()
        assert len(result_df) == 9  # 3 scenarios x 3 years
        assert "scenario_id" in result_df.columns
        assert set(result_df["scenario_id"].unique().to_list()) == {
            "BASE",
            "UP",
            "DOWN",
        }

    def test_scenario_column_becomes_dimension(self, scenario_files):
        """scenario_column should be added to dimensions."""
        # Arrange & Act
        table = Table.from_scenario_files(
            scenario_files=scenario_files,
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates",
        )

        # Assert
        assert "scenario_id" in table.dimensions

    def test_lookup_with_scenario_dimension(self, scenario_files):
        """Lookup should work with scenario_id as a dimension."""
        from gaspatchio_core import ActuarialFrame

        # Arrange
        table = Table.from_scenario_files(
            scenario_files=scenario_files,
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates_lookup",
        )

        af = ActuarialFrame(
            {
                "scenario_id": ["BASE", "UP", "DOWN"],
                "year": [1, 1, 1],
            }
        )

        # Act
        af.rate = table.lookup(scenario_id=af.scenario_id, year=af.year)
        result_df = af.collect()

        # Assert: BASE year 1 = 0.03, UP year 1 = 0.035, DOWN year 1 = 0.025
        assert result_df["rate"].to_list() == pytest.approx([0.03, 0.035, 0.025])

    def test_accepts_string_paths(self, scenario_files):
        """Should accept string paths as well as Path objects."""
        # Arrange
        string_paths = {k: str(v) for k, v in scenario_files.items()}

        # Act
        table = Table.from_scenario_files(
            scenario_files=string_paths,
            scenario_column="scenario_id",
            dimensions={"year": "year"},
            value="rate",
            name="discount_rates_strings",
        )

        # Assert
        assert len(table.to_dataframe()) == 9
