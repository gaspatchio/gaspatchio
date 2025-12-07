# ABOUTME: Tests for batch_scenarios() helper for memory-efficient scenario processing.
# ABOUTME: Verifies batching of scenario IDs for large stochastic runs.

"""Tests for batch_scenarios() helper function."""

import pytest

from gaspatchio_core.scenarios import batch_scenarios


class TestBatchScenariosBasic:
    """Basic tests for batch_scenarios() function."""

    def test_yields_batches_of_correct_size(self):
        """Scenario IDs should be yielded in batches of specified size."""
        # Arrange
        scenario_ids = list(range(1, 11))  # 10 scenarios

        # Act
        batches = list(batch_scenarios(scenario_ids, batch_size=3))

        # Assert
        assert len(batches) == 4  # ceil(10/3) = 4 batches
        assert batches[0] == [1, 2, 3]
        assert batches[1] == [4, 5, 6]
        assert batches[2] == [7, 8, 9]
        assert batches[3] == [10]  # Last batch has remainder

    def test_handles_exact_division(self):
        """When scenario count divides evenly by batch_size."""
        # Arrange
        scenario_ids = list(range(1, 13))  # 12 scenarios

        # Act
        batches = list(batch_scenarios(scenario_ids, batch_size=4))

        # Assert
        assert len(batches) == 3
        assert all(len(b) == 4 for b in batches)

    def test_single_batch_when_fewer_than_batch_size(self):
        """Single batch when scenario count is less than batch_size."""
        # Arrange
        scenario_ids = ["A", "B", "C"]

        # Act
        batches = list(batch_scenarios(scenario_ids, batch_size=100))

        # Assert
        assert len(batches) == 1
        assert batches[0] == ["A", "B", "C"]

    def test_preserves_order(self):
        """Scenario IDs should maintain their original order."""
        # Arrange
        scenario_ids = ["BASE", "UP", "DOWN", "EXTREME"]

        # Act
        batches = list(batch_scenarios(scenario_ids, batch_size=2))

        # Assert
        assert batches[0] == ["BASE", "UP"]
        assert batches[1] == ["DOWN", "EXTREME"]

    def test_is_lazy_generator(self):
        """batch_scenarios should return a generator, not a list."""
        # Arrange
        scenario_ids = list(range(1, 101))

        # Act
        result = batch_scenarios(scenario_ids, batch_size=10)

        # Assert - should be a generator/iterator
        assert hasattr(result, "__iter__")
        assert hasattr(result, "__next__")


class TestBatchScenariosTypes:
    """Tests for different scenario ID types."""

    def test_works_with_integer_ids(self):
        """Integer scenario IDs should batch correctly."""
        # Arrange
        scenario_ids = [100, 200, 300, 400, 500]

        # Act
        batches = list(batch_scenarios(scenario_ids, batch_size=2))

        # Assert
        assert batches[0] == [100, 200]
        assert batches[1] == [300, 400]
        assert batches[2] == [500]

    def test_works_with_string_ids(self):
        """String scenario IDs should batch correctly."""
        # Arrange
        scenario_ids = ["SCEN_001", "SCEN_002", "SCEN_003"]

        # Act
        batches = list(batch_scenarios(scenario_ids, batch_size=2))

        # Assert
        assert batches[0] == ["SCEN_001", "SCEN_002"]
        assert batches[1] == ["SCEN_003"]


class TestBatchScenariosDefaults:
    """Tests for default parameter values."""

    def test_default_batch_size_is_1000(self):
        """Default batch_size should be 1000."""
        # Arrange
        scenario_ids = list(range(1, 2501))  # 2500 scenarios

        # Act
        batches = list(batch_scenarios(scenario_ids))

        # Assert
        assert len(batches) == 3  # ceil(2500/1000) = 3
        assert len(batches[0]) == 1000
        assert len(batches[1]) == 1000
        assert len(batches[2]) == 500


class TestBatchScenariosValidation:
    """Tests for input validation."""

    def test_empty_list_yields_nothing(self):
        """Empty scenario list should yield no batches."""
        # Arrange
        scenario_ids: list[str] = []

        # Act
        batches = list(batch_scenarios(scenario_ids))

        # Assert
        assert batches == []

    def test_batch_size_must_be_positive(self):
        """batch_size must be > 0."""
        # Arrange
        scenario_ids = [1, 2, 3]

        # Act & Assert
        with pytest.raises(ValueError, match="batch_size must be positive"):
            list(batch_scenarios(scenario_ids, batch_size=0))

        with pytest.raises(ValueError, match="batch_size must be positive"):
            list(batch_scenarios(scenario_ids, batch_size=-5))


class TestBatchScenariosIntegration:
    """Integration tests with with_scenarios."""

    def test_full_batch_workflow(self):
        """Test complete workflow: batch scenarios, process, aggregate."""
        import polars as pl

        from gaspatchio_core import ActuarialFrame
        from gaspatchio_core.scenarios import with_scenarios

        # Arrange - Small model point set
        model_points = ActuarialFrame({"policy_id": [1], "premium": [100.0]})
        scenario_ids = list(range(1, 11))  # 10 scenarios

        # Act - Process in batches of 3
        all_results = []
        for batch in batch_scenarios(scenario_ids, batch_size=3):
            expanded = with_scenarios(model_points, batch)
            result_df = expanded.collect()
            all_results.append(result_df)

        # Combine results
        combined = pl.concat(all_results)

        # Assert
        assert len(combined) == 10  # 1 policy x 10 scenarios
        assert set(combined["scenario_id"].to_list()) == set(range(1, 11))


def test_import_from_scenarios_module():
    """batch_scenarios should be importable from gaspatchio_core.scenarios."""
    from gaspatchio_core.scenarios import batch_scenarios

    assert callable(batch_scenarios)


def test_import_from_top_level():
    """batch_scenarios should be importable from gaspatchio_core."""
    from gaspatchio_core import batch_scenarios

    assert callable(batch_scenarios)
