# ABOUTME: Tests for describe_scenarios() audit trail function.
# ABOUTME: Verifies human-readable scenario descriptions for governance.

"""Tests for describe_scenarios() audit trail function."""

from gaspatchio_core.scenarios import describe_scenarios
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
)


class TestDescribeScenarios:
    """Tests for describe_scenarios() function."""

    def test_describe_single_shock(self):
        """Describe a single shock scenario."""
        # Arrange
        shocks = {"STRESSED": [MultiplicativeShock(factor=1.2, table="mortality")]}

        # Act
        description = describe_scenarios(shocks)

        # Assert
        assert "STRESSED" in description
        assert "mortality" in description
        assert "1.2" in description

    def test_describe_multiple_shocks(self):
        """Describe scenario with multiple shocks."""
        # Arrange
        shocks = {
            "ADVERSE": [
                MultiplicativeShock(factor=1.3, table="mortality"),
                AdditiveShock(delta=0.01, table="discount"),
            ]
        }

        # Act
        description = describe_scenarios(shocks)

        # Assert
        assert "ADVERSE" in description
        assert "mortality" in description
        assert "discount" in description
        assert "1.3" in description
        assert "0.01" in description

    def test_describe_multiple_scenarios(self):
        """Describe multiple scenarios."""
        # Arrange
        shocks = {
            "BASE": [],  # No shocks
            "UP": [MultiplicativeShock(factor=1.1, table="mortality")],
            "DOWN": [MultiplicativeShock(factor=0.9, table="mortality")],
        }

        # Act
        description = describe_scenarios(shocks)

        # Assert
        assert "BASE" in description
        assert "UP" in description
        assert "DOWN" in description

    def test_describe_empty_scenarios_dict(self):
        """Empty scenarios dict produces minimal description."""
        # Arrange
        shocks: dict = {}

        # Act
        description = describe_scenarios(shocks)

        # Assert
        assert isinstance(description, str)

    def test_returns_markdown_format(self):
        """Description should be markdown-formatted."""
        # Arrange
        shocks = {"STRESSED": [MultiplicativeShock(factor=1.2, table="mortality")]}

        # Act
        description = describe_scenarios(shocks)

        # Assert - Should contain markdown elements
        assert "#" in description or "-" in description or "*" in description


class TestDescribeScenariosFormats:
    """Tests for different output formats."""

    def test_as_dict_format(self):
        """Can output as dictionary for programmatic access."""
        # Arrange
        shocks = {"UP": [MultiplicativeShock(factor=1.1, table="mortality")]}

        # Act
        result = describe_scenarios(shocks, output_format="dict")

        # Assert
        assert isinstance(result, dict)
        assert "UP" in result

    def test_as_text_format(self):
        """Can output as plain text."""
        # Arrange
        shocks = {"UP": [MultiplicativeShock(factor=1.1, table="mortality")]}

        # Act
        result = describe_scenarios(shocks, output_format="text")

        # Assert
        assert isinstance(result, str)


def test_import_describe_scenarios():
    """describe_scenarios should be importable from scenarios module."""
    from gaspatchio_core.scenarios import describe_scenarios as ds

    assert callable(ds)
