# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for shock specification data model and application.
# ABOUTME: Verifies MultiplicativeShock, AdditiveShock, and OverrideShock behavior.

"""Tests for shock specification data model."""

import polars as pl
import pytest

from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
    OverrideShock,
    Shock,
)


class TestMultiplicativeShock:
    """Tests for MultiplicativeShock data class."""

    def test_create_multiplicative_shock(self):
        """Create a multiplicative shock with factor."""
        # Act
        shock = MultiplicativeShock(factor=1.2)

        # Assert
        assert shock.factor == 1.2
        assert isinstance(shock, Shock)

    def test_multiplicative_shock_description(self):
        """Shock should have descriptive representation."""
        # Arrange
        shock = MultiplicativeShock(factor=1.5)

        # Act
        desc = shock.describe()

        # Assert
        assert "1.5" in desc
        assert "multiply" in desc.lower() or "x" in desc.lower()

    def test_multiplicative_shock_to_expression(self):
        """Shock should produce a Polars expression."""
        # Arrange
        shock = MultiplicativeShock(factor=2.0)
        values = pl.Series("rate", [0.01, 0.02, 0.03])

        # Act
        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("shocked"))

        # Assert
        assert result["shocked"].to_list() == [0.02, 0.04, 0.06]


class TestAdditiveShock:
    """Tests for AdditiveShock data class."""

    def test_create_additive_shock(self):
        """Create an additive shock with delta."""
        # Act
        shock = AdditiveShock(delta=0.005)

        # Assert
        assert shock.delta == 0.005
        assert isinstance(shock, Shock)

    def test_additive_shock_description(self):
        """Shock should have descriptive representation."""
        # Arrange
        shock = AdditiveShock(delta=0.01)

        # Act
        desc = shock.describe()

        # Assert
        assert "0.01" in desc or "1%" in desc
        assert "add" in desc.lower() or "+" in desc

    def test_additive_shock_to_expression(self):
        """Shock should produce a Polars expression."""
        # Arrange
        shock = AdditiveShock(delta=0.01)
        values = pl.Series("rate", [0.03, 0.04, 0.05])

        # Act
        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("shocked"))

        # Assert
        assert result["shocked"].to_list() == pytest.approx([0.04, 0.05, 0.06])


class TestOverrideShock:
    """Tests for OverrideShock data class."""

    def test_create_override_shock(self):
        """Create an override shock with value."""
        # Act
        shock = OverrideShock(value=0.0)

        # Assert
        assert shock.value == 0.0
        assert isinstance(shock, Shock)

    def test_override_shock_description(self):
        """Shock should have descriptive representation."""
        # Arrange
        shock = OverrideShock(value=0.5)

        # Act
        desc = shock.describe()

        # Assert
        assert "0.5" in desc
        assert "override" in desc.lower() or "set" in desc.lower() or "=" in desc

    def test_override_shock_to_expression(self):
        """Shock should produce a Polars expression."""
        # Arrange
        shock = OverrideShock(value=0.0)
        values = pl.Series("rate", [0.01, 0.02, 0.03])

        # Act
        expr = shock.to_expression(pl.col("rate"))
        result = pl.DataFrame({"rate": values}).select(expr.alias("shocked"))

        # Assert
        assert result["shocked"].to_list() == [0.0, 0.0, 0.0]


class TestShockWithName:
    """Tests for named shocks targeting specific tables/columns."""

    def test_shock_with_table_name(self):
        """Shock can target a specific table."""
        # Act
        shock = MultiplicativeShock(factor=1.2, table="mortality")

        # Assert
        assert shock.table == "mortality"

    def test_shock_with_column_name(self):
        """Shock can target a specific column."""
        # Act
        shock = AdditiveShock(delta=0.01, column="rate")

        # Assert
        assert shock.column == "rate"


class TestShockEquality:
    """Tests for shock equality and hashing."""

    def test_same_shocks_are_equal(self):
        """Identical shocks should be equal."""
        # Arrange
        shock1 = MultiplicativeShock(factor=1.2)
        shock2 = MultiplicativeShock(factor=1.2)

        # Assert
        assert shock1 == shock2

    def test_different_shocks_not_equal(self):
        """Different shocks should not be equal."""
        # Arrange
        shock1 = MultiplicativeShock(factor=1.2)
        shock2 = MultiplicativeShock(factor=1.3)

        # Assert
        assert shock1 != shock2

    def test_different_types_not_equal(self):
        """Different shock types should not be equal."""
        # Arrange
        shock1 = MultiplicativeShock(factor=1.1)
        shock2 = AdditiveShock(delta=0.1)

        # Assert
        assert shock1 != shock2


def test_import_shocks():
    """Shocks should be importable from scenarios.shocks."""
    from gaspatchio_core.scenarios.shocks import (
        AdditiveShock,
        MultiplicativeShock,
        OverrideShock,
        Shock,
    )

    assert Shock is not None
    assert MultiplicativeShock is not None
    assert AdditiveShock is not None
    assert OverrideShock is not None
