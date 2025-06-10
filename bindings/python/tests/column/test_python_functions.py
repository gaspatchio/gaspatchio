import math
from collections.abc import Sequence

import numpy as np
import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


class TestPolarsFunctions:
    """Tests to understand how Polars itself handles function application."""

    def test_polars_map_elements(self):
        """Verify Polars map_elements behavior for element-wise operations."""
        # Create a DataFrame directly with Polars
        df = pl.DataFrame(
            {"age": [30, 40, 50, 60, 70], "weight": [70, 80, 90, 100, 110]},
        )

        # Define a simple function
        def square(x):
            return x * x

        # Test direct Polars map_elements
        result = df.with_columns(
            age_squared=pl.col("age").map_elements(square, return_dtype=pl.Int64),
        )

        # Verify results
        expected = [900, 1600, 2500, 3600, 4900]
        assert result["age_squared"].to_list() == expected

    def test_polars_map_batches(self):
        """Verify Polars map_batches behavior for batch operations."""
        # Create a DataFrame directly with Polars
        df = pl.DataFrame(
            {
                "age": [30, 40, 50, 60, 70],
            },
        )

        # Define a batch function that works on the whole Series at once
        def batch_square(s: pl.Series) -> pl.Series:
            # Convert to numpy, square values, and return as a new Series
            arr = s.to_numpy()
            return pl.Series(arr * arr)

        # Test direct Polars map_batches
        result = df.with_columns(
            age_squared=pl.col("age").map_batches(batch_square, return_dtype=pl.Int64),
        )

        # Verify results
        expected = [900, 1600, 2500, 3600, 4900]
        assert result["age_squared"].to_list() == expected

    def test_polars_multi_column_map_batches(self):
        """Verify Polars pl.map_batches for multi-column operations."""
        df = pl.DataFrame(
            {
                "a": [10, 20, 30],
                "b": [1, 2, 3],
            },
        )

        # Function that takes multiple columns as input
        def sum_columns(columns: Sequence[pl.Series]) -> pl.Series:
            return columns[0] + columns[1]

        # Test direct Polars map_batches for multiple columns
        result = df.with_columns(
            sum_ab=pl.map_batches([pl.col("a"), pl.col("b")], sum_columns),
        )

        # Verify results
        expected = [11, 22, 33]
        assert result["sum_ab"].to_list() == expected

    def test_polars_numpy_functions(self):
        """Verify Polars working with NumPy functions."""
        df = pl.DataFrame(
            {
                "angle": [0, 30, 45, 60, 90],
            },
        )

        # Test direct Polars with NumPy functions using map_batches for efficiency
        def sin_degrees_batch(s: pl.Series) -> pl.Series:
            arr = s.to_numpy()
            return pl.Series(np.sin(np.radians(arr)))

        # Using map_batches is more efficient for NumPy operations
        result = df.with_columns(
            sin_value=pl.col("angle").map_batches(
                sin_degrees_batch,
                return_dtype=pl.Float64,
            ),
        )

        # For comparison, also test element-wise with map_elements
        def sin_degrees_elem(x):
            return np.sin(np.radians(x))

        result_elem = df.with_columns(
            sin_value_elem=pl.col("angle").map_elements(
                sin_degrees_elem,
                return_dtype=pl.Float64,
            ),
        )

        # Verify results
        expected = [np.sin(np.radians(x)) for x in [0, 30, 45, 60, 90]]
        np.testing.assert_almost_equal(result["sin_value"].to_list(), expected)
        np.testing.assert_almost_equal(
            result_elem["sin_value_elem"].to_list(),
            expected,
        )


class TestActuarialFrameApply:
    """Tests for the apply function in ColumnProxy."""

    def test_basic_apply(self):
        """Test basic function application."""
        # First test with native Polars
        pdf = pl.DataFrame(
            {
                "age": [30, 40, 50, 60, 70],
            },
        )

        def square(x):
            return x * x

        # Execute with Polars directly
        polars_result = pdf.with_columns(
            age_squared=pl.col("age").map_elements(square, return_dtype=pl.Int64),
        )

        # Now test with ActuarialFrame
        af = ActuarialFrame(pdf.clone(), mode="debug")

        # Apply function using our implementation
        af["age_squared"] = af["age"].map_elements(square)
        actf_result = af.collect()

        # Verify results match Polars native implementation
        np.testing.assert_array_equal(
            polars_result["age_squared"].to_list(),
            actf_result["age_squared"].to_list(),
        )

    def test_apply_with_return_dtype(self):
        """Test apply with explicit return dtype."""
        # First test with native Polars
        pdf = pl.DataFrame(
            {
                "age": [30, 40, 50, 60, 70],
            },
        )

        # Execute with Polars directly
        polars_result = pdf.with_columns(
            age_sqrt=pl.col("age").map_elements(math.sqrt, return_dtype=pl.Float64),
        )

        # Now test with ActuarialFrame
        af = ActuarialFrame(pdf.clone(), mode="debug")

        # Apply function using our implementation
        af["age_sqrt"] = af["age"].map_elements(math.sqrt, return_dtype=pl.Float64)
        actf_result = af.collect()

        # Verify results match Polars native implementation
        np.testing.assert_almost_equal(
            polars_result["age_sqrt"].to_list(),
            actf_result["age_sqrt"].to_list(),
        )

    def test_apply_with_numpy_functions(self):
        """Test apply with numpy functions."""
        # First test with native Polars
        pdf = pl.DataFrame(
            {
                "angle": [0, 30, 45, 60, 90],
            },
        )

        def sin_degrees(x):
            return np.sin(np.radians(x))

        # Execute with Polars directly
        polars_result = pdf.with_columns(
            sin_value=pl.col("angle").map_elements(
                sin_degrees,
                return_dtype=pl.Float64,
            ),
        )

        # Now test with ActuarialFrame
        af = ActuarialFrame(pdf.clone(), mode="debug")

        # Apply function using our implementation
        af["sin_value"] = af["angle"].map_elements(sin_degrees, return_dtype=pl.Float64)
        actf_result = af.collect()

        # Verify results match Polars native implementation
        np.testing.assert_almost_equal(
            polars_result["sin_value"].to_list(),
            actf_result["sin_value"].to_list(),
        )

    def test_apply_with_string_manipulation(self):
        """Test apply with string manipulation functions."""
        # First test with native Polars
        pdf = pl.DataFrame(
            {
                "name": ["john", "JANE", "Mike", "ANNA", "tom"],
            },
        )

        def capitalize(x):
            return x.capitalize()

        # Execute with Polars directly
        polars_result = pdf.with_columns(
            name_capitalized=pl.col("name").map_elements(capitalize),
        )

        # Now test with ActuarialFrame
        af = ActuarialFrame(pdf.clone(), mode="debug")

        # Apply function using our implementation
        af["name_capitalized"] = af["name"].map_elements(capitalize)
        actf_result = af.collect()

        # Verify results match Polars native implementation
        assert (
            polars_result["name_capitalized"].to_list()
            == actf_result["name_capitalized"].to_list()
        )

    def test_map_batches_with_numpy(self):
        """Test map_batches for efficient batch operations."""
        # First test with native Polars
        pdf = pl.DataFrame(
            {
                "angle": [0, 30, 45, 60, 90],
            },
        )

        # Define a batch function that works on the entire Series
        def sin_degrees_batch(s: pl.Series) -> pl.Series:
            arr = s.to_numpy()
            return pl.Series(np.sin(np.radians(arr)))

        # Execute with Polars directly
        polars_result = pdf.with_columns(
            sin_batch=pl.col("angle").map_batches(
                sin_degrees_batch,
                return_dtype=pl.Float64,
            ),
        )

        # Now test with ActuarialFrame
        af = ActuarialFrame(pdf.clone(), mode="debug")

        # Apply batch function using our implementation
        af["sin_batch"] = af["angle"].map_batches(
            sin_degrees_batch,
            return_dtype=pl.Float64,
        )
        actf_result = af.collect()

        # Verify results match Polars native implementation
        np.testing.assert_almost_equal(
            polars_result["sin_batch"].to_list(),
            actf_result["sin_batch"].to_list(),
        )

    def test_map_batches_vs_apply_performance(self):
        """Compare map_batches versus apply for the same operation."""
        # Create a larger DataFrame to better see performance differences
        data = list(range(1000))
        pdf = pl.DataFrame({"value": data})

        # Define both element-wise and batch functions
        def square_elem(x):
            return x * x

        def square_batch(s: pl.Series) -> pl.Series:
            arr = s.to_numpy()
            return pl.Series(arr * arr)

        # Test with ActuarialFrame
        af = ActuarialFrame(pdf.clone(), mode="debug")

        # Apply both functions - for a real test, you'd want to time these
        af["squared_elem"] = af["value"].map_elements(
            square_elem,
            return_dtype=pl.Int64,
        )
        af["squared_batch"] = af["value"].map_batches(
            square_batch,
            return_dtype=pl.Int64,
        )
        result = af.collect()

        # Verify both methods produce the same result
        np.testing.assert_array_equal(
            result["squared_elem"].to_list(),
            result["squared_batch"].to_list(),
        )


if __name__ == "__main__":
    pytest.main(["-v", __file__])
