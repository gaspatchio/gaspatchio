# ABOUTME: Tests for scenario expansion functionality.
# ABOUTME: Verifies with_scenarios() cross-joins ActuarialFrame with scenario IDs.

"""Tests for scenario expansion functionality."""

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import with_scenarios


class TestWithScenariosBasic:
    """Basic tests for with_scenarios() function."""

    def test_expands_single_row_to_multiple_scenarios(self):
        """One model point x 3 scenarios = 3 rows."""
        # Arrange
        af = ActuarialFrame({"policy_id": [1], "premium": [100.0]})

        # Act
        result = with_scenarios(af, ["BASE", "UP", "DOWN"])

        # Assert
        result_df = result.collect()
        assert len(result_df) == 3
        assert "scenario_id" in result_df.columns
        assert set(result_df["scenario_id"].to_list()) == {"BASE", "UP", "DOWN"}
        assert result_df["policy_id"].to_list() == [1, 1, 1]
        assert result_df["premium"].to_list() == [100.0, 100.0, 100.0]

    def test_expands_multiple_rows_to_scenarios(self):
        """3 model points x 2 scenarios = 6 rows."""
        # Arrange
        af = ActuarialFrame(
            {
                "policy_id": [1, 2, 3],
                "premium": [100.0, 200.0, 300.0],
            }
        )

        # Act
        result = with_scenarios(af, ["BASE", "STRESS"])

        # Assert
        result_df = result.collect()
        assert len(result_df) == 6
        assert set(result_df["scenario_id"].to_list()) == {"BASE", "STRESS"}

    def test_returns_actuarial_frame(self):
        """Result should be an ActuarialFrame, not a DataFrame."""
        # Arrange
        af = ActuarialFrame({"x": [1]})

        # Act
        result = with_scenarios(af, ["A"])

        # Assert
        assert isinstance(result, ActuarialFrame)

    def test_single_scenario_deterministic(self):
        """Single scenario is valid - the scenario-ready-by-default pattern."""
        # Arrange
        af = ActuarialFrame({"policy_id": [1, 2]})

        # Act
        result = with_scenarios(af, ["DETERMINISTIC"])

        # Assert
        result_df = result.collect()
        assert len(result_df) == 2
        assert result_df["scenario_id"].to_list() == ["DETERMINISTIC", "DETERMINISTIC"]
