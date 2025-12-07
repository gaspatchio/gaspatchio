# ABOUTME: Integration tests for shock scenarios with Table operations.
# ABOUTME: Verifies Table.from_shocks() creates scenario-specific assumption tables.

"""Integration tests for shock scenarios with Table operations."""

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios import sensitivity_analysis
from gaspatchio_core.scenarios.shocks import (
    MultiplicativeShock,
)


@pytest.fixture
def base_mortality_table(tmp_path: Path) -> Table:
    """Create a base mortality table for testing."""
    mortality_df = pl.DataFrame(
        {
            "age": [30, 40, 50],
            "rate": [0.001, 0.002, 0.005],
        }
    )
    path = tmp_path / "mortality.parquet"
    mortality_df.write_parquet(path)
    return Table(
        name="mortality",
        source=path,
        dimensions={"age": "age"},
        value="rate",
    )


class TestTableFromShocks:
    """Tests for Table.from_shocks() classmethod."""

    def test_creates_tables_from_shock_dict(self, base_mortality_table):
        """Create multiple shocked tables from a base table and shocks dict."""
        # Arrange
        shocks = {
            "BASE": [],
            "UP": [MultiplicativeShock(factor=1.2, table="mortality")],
            "DOWN": [MultiplicativeShock(factor=0.8, table="mortality")],
        }

        # Act
        tables = Table.from_shocks(base_mortality_table, shocks, value_column="rate")

        # Assert
        assert "BASE" in tables
        assert "UP" in tables
        assert "DOWN" in tables

    def test_base_scenario_unchanged(self, base_mortality_table):
        """BASE scenario with no shocks returns original values."""
        # Arrange
        shocks = {"BASE": []}

        # Act
        tables = Table.from_shocks(base_mortality_table, shocks, value_column="rate")

        # Assert
        base_data = tables["BASE"].to_dataframe()
        assert base_data.filter(pl.col("age") == 30)["rate"][0] == pytest.approx(0.001)

    def test_shock_applied_to_values(self, base_mortality_table):
        """Shocks are correctly applied to the value column."""
        # Arrange
        shocks = {"STRESSED": [MultiplicativeShock(factor=2.0, table="mortality")]}

        # Act
        tables = Table.from_shocks(base_mortality_table, shocks, value_column="rate")

        # Assert
        stressed_data = tables["STRESSED"].to_dataframe()
        assert stressed_data.filter(pl.col("age") == 30)["rate"][0] == pytest.approx(
            0.002
        )
        assert stressed_data.filter(pl.col("age") == 40)["rate"][0] == pytest.approx(
            0.004
        )

    def test_each_scenario_is_independent_table(self, base_mortality_table):
        """Each scenario returns an independent Table instance."""
        # Arrange
        shocks = {
            "A": [MultiplicativeShock(factor=1.1, table="mortality")],
            "B": [MultiplicativeShock(factor=1.2, table="mortality")],
        }

        # Act
        tables = Table.from_shocks(base_mortality_table, shocks, value_column="rate")

        # Assert
        assert tables["A"] is not tables["B"]
        assert tables["A"] is not base_mortality_table


class TestTableFromShocksWithSensitivity:
    """Tests for integration with sensitivity_analysis()."""

    def test_works_with_sensitivity_analysis_output(self, base_mortality_table):
        """Can use output from sensitivity_analysis() directly."""
        # Arrange
        shocks = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=[0.9, 1.0, 1.1],
        )

        # Act
        tables = Table.from_shocks(base_mortality_table, shocks, value_column="rate")

        # Assert
        assert len(tables) == 3
        assert "mortality_0.9" in tables
        assert "mortality_1.0" in tables
        assert "mortality_1.1" in tables

    def test_sensitivity_sweep_values_correct(self, tmp_path):
        """Values from sensitivity sweep are correctly applied."""
        # Arrange
        rates_df = pl.DataFrame({"term": [1, 2], "rate": [0.10, 0.10]})
        path = tmp_path / "rates.parquet"
        rates_df.write_parquet(path)
        base_table = Table(
            name="rates", source=path, dimensions={"term": "term"}, value="rate"
        )

        shocks = sensitivity_analysis(
            table="rates",
            shock_type="additive",
            values=[-0.01, 0.0, 0.01],
        )

        # Act
        tables = Table.from_shocks(base_table, shocks, value_column="rate")

        # Assert
        down_data = tables["rates_-0.01"].to_dataframe()
        base_data = tables["rates_0.0"].to_dataframe()
        up_data = tables["rates_0.01"].to_dataframe()

        assert down_data["rate"][0] == pytest.approx(0.09)
        assert base_data["rate"][0] == pytest.approx(0.10)
        assert up_data["rate"][0] == pytest.approx(0.11)


class TestTableFromShocksValidation:
    """Tests for input validation."""

    def test_empty_shocks_dict_returns_empty(self, base_mortality_table):
        """Empty shocks dict returns empty dict of tables."""
        # Act
        tables = Table.from_shocks(base_mortality_table, {}, value_column="rate")

        # Assert
        assert tables == {}

    def test_invalid_value_column_raises(self, base_mortality_table):
        """Invalid value column should raise ValueError."""
        # Arrange
        shocks = {"STRESSED": [MultiplicativeShock(factor=1.2)]}

        # Act / Assert
        with pytest.raises(ValueError, match="value_column"):
            Table.from_shocks(base_mortality_table, shocks, value_column="nonexistent")


def test_table_from_shocks_exists():
    """Table.from_shocks should be available as a classmethod."""
    assert hasattr(Table, "from_shocks")
    assert callable(Table.from_shocks)
