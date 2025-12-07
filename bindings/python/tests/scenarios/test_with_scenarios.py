# ABOUTME: Tests for scenario expansion functionality.
# ABOUTME: Verifies with_scenarios() cross-joins ActuarialFrame with scenario IDs.

"""Tests for scenario expansion functionality."""

import polars as pl
import pytest

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


class TestWithScenariosPerformance:
    """Tests for scenario ID encoding and performance features."""

    def test_integer_scenario_ids(self):
        """Integer scenario IDs for stochastic runs."""
        # Arrange
        af = ActuarialFrame({"x": [1]})

        # Act
        result = with_scenarios(af, [1, 2, 3, 4, 5])

        # Assert
        result_df = result.collect()
        assert len(result_df) == 5
        assert result_df["scenario_id"].dtype == pl.Int64
        assert set(result_df["scenario_id"].to_list()) == {1, 2, 3, 4, 5}

    def test_categorical_encoding(self):
        """Categorical encoding for string scenario IDs."""
        # Arrange
        af = ActuarialFrame({"x": [1]})

        # Act
        result = with_scenarios(af, ["A", "B", "C"], categorical=True)

        # Assert
        result_df = result.collect()
        assert result_df["scenario_id"].dtype == pl.Categorical

    def test_categorical_not_applied_to_integers(self):
        """Categorical flag should not affect integer IDs."""
        # Arrange
        af = ActuarialFrame({"x": [1]})

        # Act
        result = with_scenarios(af, [1, 2, 3], categorical=True)

        # Assert
        result_df = result.collect()
        # Integer IDs stay as integers even with categorical=True
        assert result_df["scenario_id"].dtype == pl.Int64

    def test_custom_scenario_column_name(self):
        """Custom scenario column name."""
        # Arrange
        af = ActuarialFrame({"x": [1]})

        # Act
        result = with_scenarios(af, ["A", "B"], scenario_column="scen")

        # Assert
        result_df = result.collect()
        assert "scen" in result_df.columns
        assert "scenario_id" not in result_df.columns


class TestWithScenariosPreservation:
    """Tests for ActuarialFrame property preservation."""

    def test_preserves_mode(self):
        """Mode should be preserved from input ActuarialFrame."""
        # Arrange
        af = ActuarialFrame({"x": [1]}, mode="optimize")

        # Act
        result = with_scenarios(af, ["A"])

        # Assert
        assert result._mode == "optimize"  # noqa: SLF001

    def test_preserves_verbose(self):
        """Verbose flag should be preserved."""
        # Arrange
        af = ActuarialFrame({"x": [1]}, verbose=True)

        # Act
        result = with_scenarios(af, ["A"])

        # Assert
        assert result._verbose is True  # noqa: SLF001

    def test_preserves_all_original_columns(self):
        """All original columns should be present in result."""
        # Arrange
        af = ActuarialFrame(
            {
                "policy_id": [1],
                "sum_assured": [100000],
                "age": [35],
                "sex": ["M"],
            }
        )

        # Act
        result = with_scenarios(af, ["BASE"])

        # Assert
        result_df = result.collect()
        assert set(result_df.columns) == {
            "policy_id",
            "sum_assured",
            "age",
            "sex",
            "scenario_id",
        }


class TestWithScenariosLazyMode:
    """Tests for lazy mode support in with_scenarios()."""

    def test_works_with_lazy_input(self):
        """with_scenarios should work when given a lazy ActuarialFrame."""
        # Arrange
        lf = pl.LazyFrame({"x": [1, 2, 3]})
        af = ActuarialFrame(lf, mode="optimize")

        # Act
        result = with_scenarios(af, ["A", "B"])

        # Assert - Should produce 6 rows when collected
        result_df = result.collect()
        assert len(result_df) == 6

    def test_scan_parquet_workflow(self, tmp_path):
        """Test the lazy loading pattern from RFC."""
        # Arrange - Create a test parquet file
        test_df = pl.DataFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})
        test_path = tmp_path / "model_points.parquet"
        test_df.write_parquet(test_path)

        # Load lazily
        af = ActuarialFrame(pl.scan_parquet(test_path))

        # Act - Expand
        af = with_scenarios(af, ["BASE", "STRESS"])

        # Assert - Collect
        result_df = af.collect()
        assert len(result_df) == 4  # 2 policies x 2 scenarios


class TestWithScenariosValidation:
    """Tests for input validation and error messages."""

    def test_empty_scenario_list_raises(self):
        """Empty scenario list should raise ValueError."""
        # Arrange
        af = ActuarialFrame({"x": [1]})

        # Act & Assert
        with pytest.raises(ValueError, match="at least one scenario"):
            with_scenarios(af, [])

    def test_duplicate_scenarios_raises(self):
        """Duplicate scenario IDs should raise ValueError."""
        # Arrange
        af = ActuarialFrame({"x": [1]})

        # Act & Assert
        with pytest.raises(ValueError, match="duplicate"):
            with_scenarios(af, ["A", "B", "A"])

    def test_scenario_column_conflict_raises(self):
        """Should raise if scenario_column already exists in frame."""
        # Arrange
        af = ActuarialFrame({"scenario_id": [1], "x": [2]})

        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            with_scenarios(af, ["A", "B"])


def test_import_from_top_level():
    """with_scenarios should be importable from gaspatchio_core."""
    from gaspatchio_core import with_scenarios

    assert callable(with_scenarios)
