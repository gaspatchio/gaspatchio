# ABOUTME: Tests for sensitivity_analysis() parameter sweep function.
# ABOUTME: Verifies generation of shock configurations across value ranges.

"""Tests for sensitivity_analysis() parameter sweep function."""

from gaspatchio_core.scenarios import sensitivity_analysis
from gaspatchio_core.scenarios.shocks import (
    AdditiveShock,
    MultiplicativeShock,
    OverrideShock,
)


class TestSensitivityAnalysisMultiplicative:
    """Tests for multiplicative shock sweeps."""

    def test_generates_multiplicative_shocks_for_values(self):
        """Generate multiplicative shocks for a range of factors."""
        # Arrange
        values = [0.9, 1.0, 1.1]

        # Act
        result = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=values,
        )

        # Assert
        assert len(result) == 3
        for shocks in result.values():
            assert len(shocks) == 1
            assert isinstance(shocks[0], MultiplicativeShock)
            assert shocks[0].table == "mortality"

    def test_scenario_ids_include_table_and_value(self):
        """Scenario IDs should be descriptive."""
        # Arrange
        values = [0.9, 1.0, 1.1]

        # Act
        result = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=values,
        )

        # Assert
        assert "mortality_0.9" in result
        assert "mortality_1.0" in result
        assert "mortality_1.1" in result

    def test_shock_factors_match_input_values(self):
        """Each shock should have the corresponding factor."""
        # Arrange
        values = [0.8, 1.2]

        # Act
        result = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=values,
        )

        # Assert
        assert result["mortality_0.8"][0].factor == 0.8
        assert result["mortality_1.2"][0].factor == 1.2


class TestSensitivityAnalysisAdditive:
    """Tests for additive shock sweeps."""

    def test_generates_additive_shocks_for_values(self):
        """Generate additive shocks for a range of deltas."""
        # Arrange
        values = [-0.01, 0.0, 0.01]

        # Act
        result = sensitivity_analysis(
            table="discount",
            shock_type="additive",
            values=values,
        )

        # Assert
        assert len(result) == 3
        for shocks in result.values():
            assert len(shocks) == 1
            assert isinstance(shocks[0], AdditiveShock)
            assert shocks[0].table == "discount"

    def test_additive_scenario_ids(self):
        """Additive scenario IDs should be descriptive."""
        # Arrange
        values = [-0.01, 0.0, 0.01]

        # Act
        result = sensitivity_analysis(
            table="discount",
            shock_type="additive",
            values=values,
        )

        # Assert
        assert "discount_-0.01" in result
        assert "discount_0.0" in result
        assert "discount_0.01" in result


class TestSensitivityAnalysisOverride:
    """Tests for override shock sweeps."""

    def test_generates_override_shocks_for_values(self):
        """Generate override shocks for a range of values."""
        # Arrange
        values = [0.0, 0.5, 1.0]

        # Act
        result = sensitivity_analysis(
            table="lapse",
            shock_type="override",
            values=values,
        )

        # Assert
        assert len(result) == 3
        for shocks in result.values():
            assert len(shocks) == 1
            assert isinstance(shocks[0], OverrideShock)
            assert shocks[0].table == "lapse"


class TestSensitivityAnalysisCustomFormat:
    """Tests for custom scenario ID formatting."""

    def test_custom_scenario_format(self):
        """Can provide custom scenario ID format."""
        # Arrange
        values = [0.9, 1.1]

        # Act
        result = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=values,
            scenario_format="scen_{value}",
        )

        # Assert
        assert "scen_0.9" in result
        assert "scen_1.1" in result

    def test_format_with_table_placeholder(self):
        """Format string can include table name."""
        # Arrange
        values = [1.1]

        # Act
        result = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=values,
            scenario_format="{table}_stressed_{value}",
        )

        # Assert
        assert "mortality_stressed_1.1" in result


class TestSensitivityAnalysisColumnTarget:
    """Tests for column-specific shocks."""

    def test_can_target_specific_column(self):
        """Shocks can target a specific column within table."""
        # Arrange
        values = [0.9, 1.1]

        # Act
        result = sensitivity_analysis(
            table="mortality",
            column="rate",
            shock_type="multiplicative",
            values=values,
        )

        # Assert
        for shocks in result.values():
            assert shocks[0].column == "rate"


class TestSensitivityAnalysisValidation:
    """Tests for input validation."""

    def test_empty_values_raises(self):
        """Empty values list should raise ValueError."""
        # Arrange / Act / Assert
        import pytest

        with pytest.raises(ValueError, match="values"):
            sensitivity_analysis(
                table="mortality",
                shock_type="multiplicative",
                values=[],
            )

    def test_invalid_shock_type_raises(self):
        """Invalid shock type should raise ValueError."""
        # Arrange / Act / Assert
        import pytest

        with pytest.raises(ValueError, match="shock_type"):
            sensitivity_analysis(
                table="mortality",
                shock_type="invalid_type",
                values=[1.0],
            )


class TestSensitivityAnalysisWorkflow:
    """Tests for integration with other scenario functions."""

    def test_output_compatible_with_describe_scenarios(self):
        """Output can be passed directly to describe_scenarios."""
        # Arrange
        from gaspatchio_core.scenarios import describe_scenarios

        values = [0.9, 1.0, 1.1]

        # Act
        shocks_dict = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=values,
        )
        description = describe_scenarios(shocks_dict)

        # Assert
        assert "mortality_0.9" in description
        assert "mortality_1.0" in description
        assert "mortality_1.1" in description

    def test_includes_base_case_when_requested(self):
        """Can include a base case scenario with no shocks."""
        # Arrange
        values = [0.9, 1.1]

        # Act
        result = sensitivity_analysis(
            table="mortality",
            shock_type="multiplicative",
            values=values,
            include_base=True,
        )

        # Assert
        assert "BASE" in result
        assert result["BASE"] == []  # Base case has no shocks


def test_import_sensitivity_analysis():
    """sensitivity_analysis should be importable from scenarios module."""
    from gaspatchio_core.scenarios import sensitivity_analysis as sa

    assert callable(sa)
