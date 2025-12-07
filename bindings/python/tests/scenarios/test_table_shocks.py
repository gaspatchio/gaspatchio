# ABOUTME: Tests for applying shocks to assumption Tables.
# ABOUTME: Verifies Table.with_shock() returns modified tables for scenarios.
# ruff: noqa: SLF001

"""Tests for applying shocks to assumption Tables."""

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
    OverrideShock,
)


@pytest.fixture
def mortality_table(tmp_path: Path) -> Table:
    """Create a simple mortality table for testing."""
    mortality_df = pl.DataFrame(
        {
            "age": [30, 40, 50, 60],
            "qx": [0.001, 0.002, 0.005, 0.012],
        }
    )
    path = tmp_path / "mortality.parquet"
    mortality_df.write_parquet(path)
    return Table(
        name="mortality_test",
        source=path,
        dimensions={"age": "age"},
        value="qx",
    )


class TestTableWithShock:
    """Tests for Table.with_shock() method."""

    def test_multiplicative_shock_creates_modified_table(self, mortality_table):
        """with_shock() should return a table with shocked values."""
        # Arrange
        shock = MultiplicativeShock(factor=1.2)

        # Act
        shocked_table = mortality_table.with_shock(shock)

        # Assert
        shocked_df = shocked_table.to_dataframe()
        original_df = mortality_table.to_dataframe()

        # Values should be 1.2x original
        assert shocked_df["qx"].to_list() == pytest.approx(
            [v * 1.2 for v in original_df["qx"].to_list()]
        )

    def test_additive_shock_creates_modified_table(self, mortality_table):
        """Additive shock should add delta to values."""
        # Arrange
        shock = AdditiveShock(delta=0.001)

        # Act
        shocked_table = mortality_table.with_shock(shock)

        # Assert
        shocked_df = shocked_table.to_dataframe()
        original_df = mortality_table.to_dataframe()

        assert shocked_df["qx"].to_list() == pytest.approx(
            [v + 0.001 for v in original_df["qx"].to_list()]
        )

    def test_override_shock_replaces_values(self, mortality_table):
        """Override shock should replace all values."""
        # Arrange
        shock = OverrideShock(value=0.0)

        # Act
        shocked_table = mortality_table.with_shock(shock)

        # Assert
        shocked_df = shocked_table.to_dataframe()
        assert all(v == 0.0 for v in shocked_df["qx"].to_list())

    def test_shocked_table_preserves_dimensions(self, mortality_table):
        """Shocked table should preserve dimension columns."""
        # Arrange
        shock = MultiplicativeShock(factor=1.5)

        # Act
        shocked_table = mortality_table.with_shock(shock)

        # Assert
        shocked_df = shocked_table.to_dataframe()
        original_df = mortality_table.to_dataframe()

        assert shocked_df["age"].to_list() == original_df["age"].to_list()

    def test_shocked_table_is_new_instance(self, mortality_table):
        """with_shock() should return a new table, not modify original."""
        # Arrange
        shock = MultiplicativeShock(factor=2.0)
        original_values = mortality_table.to_dataframe()["qx"].to_list()

        # Act
        shocked_table = mortality_table.with_shock(shock)

        # Assert - original unchanged
        assert mortality_table.to_dataframe()["qx"].to_list() == original_values
        assert shocked_table is not mortality_table

    def test_shocked_table_is_usable_for_lookup(self, mortality_table):
        """Shocked table should work with lookup()."""
        # Arrange
        shock = MultiplicativeShock(factor=1.2)
        shocked_table = mortality_table.with_shock(shock)

        # Act - Use the shocked table for lookup
        test_df = pl.DataFrame({"age": [30, 50]})
        result = test_df.select(
            shocked_table.lookup(age=pl.col("age")).alias("shocked_qx")
        )

        # Assert
        assert result["shocked_qx"].to_list() == pytest.approx([0.0012, 0.006])


class TestTableWithShockNaming:
    """Tests for shocked table naming and metadata."""

    def test_shocked_table_name_reflects_shock(self, mortality_table):
        """Shocked table should have descriptive name."""
        # Arrange
        shock = MultiplicativeShock(factor=1.2)

        # Act
        shocked_table = mortality_table.with_shock(shock)

        # Assert - Name should indicate it's shocked
        assert "mortality" in shocked_table._name.lower()

    def test_can_specify_custom_name(self, mortality_table):
        """Can provide custom name for shocked table."""
        # Arrange
        shock = MultiplicativeShock(factor=1.2)

        # Act
        shocked_table = mortality_table.with_shock(shock, name="mortality_stressed")

        # Assert
        assert shocked_table._name == "mortality_stressed"


class TestChainedShocks:
    """Tests for applying multiple shocks."""

    def test_multiple_shocks_chain(self, mortality_table):
        """Can chain multiple shocks together."""
        # Arrange
        shock1 = MultiplicativeShock(factor=2.0)  # Double
        shock2 = AdditiveShock(delta=0.001)  # Then add 0.1%

        # Act
        shocked = mortality_table.with_shock(shock1).with_shock(shock2)

        # Assert
        shocked_df = shocked.to_dataframe()

        # First value: 0.001 * 2 + 0.001 = 0.003
        assert shocked_df["qx"][0] == pytest.approx(0.003)
