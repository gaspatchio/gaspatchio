# ABOUTME: Tests for runner.py - model execution utilities.
# ABOUTME: Validates policy ID type casting for run_single_policy.
"""Tests for model runner utilities."""

import pytest
import polars as pl
from pathlib import Path
import tempfile

from gaspatchio_core.runner import _cast_policy_id, run_single_policy, ModelRunConfig


class TestCastPolicyId:
    """Tests for _cast_policy_id helper function."""

    def test_cast_string_to_int64(self):
        """String policy ID is cast to int when column is Int64."""
        result = _cast_policy_id("123", pl.Int64)
        assert result == 123
        assert isinstance(result, int)

    def test_cast_string_to_int32(self):
        """String policy ID is cast to int when column is Int32."""
        result = _cast_policy_id("456", pl.Int32)
        assert result == 456
        assert isinstance(result, int)

    def test_cast_string_to_uint64(self):
        """String policy ID is cast to int when column is UInt64."""
        result = _cast_policy_id("789", pl.UInt64)
        assert result == 789
        assert isinstance(result, int)

    def test_cast_keeps_string_for_string_column(self):
        """String policy ID stays as string when column is String/Utf8."""
        result = _cast_policy_id("POL001", pl.String)
        assert result == "POL001"
        assert isinstance(result, str)

    def test_cast_keeps_string_for_categorical(self):
        """String policy ID stays as string when column is Categorical."""
        result = _cast_policy_id("CAT123", pl.Categorical)
        assert result == "CAT123"
        assert isinstance(result, str)

    def test_cast_invalid_int_raises_error(self):
        """Non-numeric string raises ValueError when column expects int."""
        with pytest.raises(ValueError, match="cannot be converted to integer"):
            _cast_policy_id("ABC", pl.Int64)

    def test_cast_float_string_raises_error(self):
        """Float string raises ValueError when column expects int."""
        with pytest.raises(ValueError, match="cannot be converted to integer"):
            _cast_policy_id("12.34", pl.Int64)


class TestRunSinglePolicyTypeCasting:
    """Integration tests for run_single_policy with different column types."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def int_policy_id_parquet(self, temp_dir):
        """Create parquet file with integer policy_id column."""
        df = pl.DataFrame({
            "policy_id": [1, 2, 3],
            "value": [100.0, 200.0, 300.0],
        })
        path = temp_dir / "int_policies.parquet"
        df.write_parquet(path)
        return path

    @pytest.fixture
    def string_policy_id_parquet(self, temp_dir):
        """Create parquet file with string policy_id column."""
        df = pl.DataFrame({
            "policy_id": ["POL001", "POL002", "POL003"],
            "value": [100.0, 200.0, 300.0],
        })
        path = temp_dir / "string_policies.parquet"
        df.write_parquet(path)
        return path

    @pytest.fixture
    def simple_model(self, temp_dir):
        """Create a simple model file."""
        model_code = '''
from gaspatchio_core import ActuarialFrame

def main(af: ActuarialFrame) -> ActuarialFrame:
    """Simple model that doubles the value."""
    af.result = af.value * 2
    return af
'''
        path = temp_dir / "model.py"
        path.write_text(model_code)
        return path

    def test_run_single_policy_with_integer_column(
        self, temp_dir, int_policy_id_parquet, simple_model
    ):
        """run_single_policy works with integer policy_id column."""
        config = ModelRunConfig(
            directory=temp_dir,
            model_file="model.py",
            model_points_file="int_policies.parquet",
            id_column_name="policy_id",
        )

        # CLI passes "2" as string, but column is Int64
        result = run_single_policy(config, "2")

        assert result.status == "success"
        assert result.result is not None
        assert len(result.result) == 1
        assert result.result["policy_id"][0] == 2
        assert result.result["value"][0] == 200.0

    def test_run_single_policy_with_string_column(
        self, temp_dir, string_policy_id_parquet, simple_model
    ):
        """run_single_policy works with string policy_id column."""
        config = ModelRunConfig(
            directory=temp_dir,
            model_file="model.py",
            model_points_file="string_policies.parquet",
            id_column_name="policy_id",
        )

        result = run_single_policy(config, "POL002")

        assert result.status == "success"
        assert result.result is not None
        assert len(result.result) == 1
        assert result.result["policy_id"][0] == "POL002"
        assert result.result["value"][0] == 200.0

    def test_run_single_policy_not_found_int_column(
        self, temp_dir, int_policy_id_parquet, simple_model
    ):
        """run_single_policy raises error when policy not found (int column)."""
        config = ModelRunConfig(
            directory=temp_dir,
            model_file="model.py",
            model_points_file="int_policies.parquet",
            id_column_name="policy_id",
        )

        with pytest.raises(ValueError, match="not found in column"):
            run_single_policy(config, "999")

    def test_run_single_policy_not_found_string_column(
        self, temp_dir, string_policy_id_parquet, simple_model
    ):
        """run_single_policy raises error when policy not found (string column)."""
        config = ModelRunConfig(
            directory=temp_dir,
            model_file="model.py",
            model_points_file="string_policies.parquet",
            id_column_name="policy_id",
        )

        with pytest.raises(ValueError, match="not found in column"):
            run_single_policy(config, "NONEXISTENT")

    def test_run_single_policy_invalid_int_for_int_column(
        self, temp_dir, int_policy_id_parquet, simple_model
    ):
        """run_single_policy raises error for non-numeric ID with int column."""
        config = ModelRunConfig(
            directory=temp_dir,
            model_file="model.py",
            model_points_file="int_policies.parquet",
            id_column_name="policy_id",
        )

        with pytest.raises(ValueError, match="cannot be converted to integer"):
            run_single_policy(config, "ABC")
