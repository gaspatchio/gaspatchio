from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from gaspatchio_core import (
    ActuarialFrame,
    ColumnProxy,
)

# Import error handler to potentially mock it


@pytest.fixture
def sample_lazy_frame() -> pl.LazyFrame:
    """Provides a sample Polars LazyFrame for testing."""
    return pl.LazyFrame({"a": [1, 2, 3], "b": [4, 5, 6]})


@pytest.fixture
def sample_eager_frame() -> pl.DataFrame:
    """Provides a sample Polars Eager DataFrame for testing."""
    return pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})


# Test Initialization
def test_init_with_lazyframe(sample_lazy_frame):
    af = ActuarialFrame(sample_lazy_frame)
    assert isinstance(af._df, pl.LazyFrame)
    assert af.get_column_order() == ["a", "b"]
    assert af._mode == "debug"  # Default mode


def test_init_with_eagerframe(sample_eager_frame):
    af = ActuarialFrame(sample_eager_frame)
    assert isinstance(af._df, pl.LazyFrame)
    assert af.get_column_order() == ["a", "b"]


def test_init_with_dict():
    data = {"x": [10], "y": ["hello"]}
    af = ActuarialFrame(data)
    assert isinstance(af._df, pl.LazyFrame)
    assert af.get_column_order() == ["x", "y"]


def test_init_with_invalid_data():
    with pytest.raises(TypeError):
        ActuarialFrame([1, 2, 3])


def test_init_with_custom_mode():
    af = ActuarialFrame(mode="optimize", verbose=False)
    assert af._mode == "optimize"
    assert af._verbose is False


# Test __getitem__
def test_getitem_returns_column_proxy(sample_lazy_frame):
    af = ActuarialFrame(sample_lazy_frame)
    proxy = af["a"]
    assert isinstance(proxy, ColumnProxy)
    assert proxy.name == "a"
    assert proxy._parent is af


def test_getitem_invalid_type(sample_lazy_frame):
    af = ActuarialFrame(sample_lazy_frame)
    with pytest.raises(TypeError):
        af[0]  # Indexing with int is not supported


# Test __setitem__
def test_setitem_adds_column(sample_lazy_frame):
    # Arrange - create ActuarialFrame in optimize mode to test direct execution
    af = ActuarialFrame(sample_lazy_frame, mode="optimize")
    
    # Act
    af["c"] = af["a"] + 1

    # Assert - should execute immediately in optimize mode
    assert "c" in af.get_column_order()  # Check tracked order
    collected = af.collect()
    assert "c" in collected.columns  # Should be executed immediately
    # Check values are correct
    assert collected["c"].to_list() == [2, 3, 4]  # a was [1, 2, 3], so a+1 should be [2, 3, 4]


def test_setitem_modifies_existing(sample_lazy_frame):
    # Arrange - create ActuarialFrame in optimize mode to test direct execution
    af = ActuarialFrame(sample_lazy_frame, mode="optimize")

    # Act
    af["a"] = af["a"] * 2

    # Assert
    assert af.get_column_order() == ["a", "b"]  # Order should be preserved
    collected = af.collect()
    assert collected["a"].to_list() == [2, 4, 6]  # Original [1, 2, 3] * 2 = [2, 4, 6]


# Test with_columns
def test_with_columns_adds_expressions(sample_lazy_frame):
    # Arrange - create ActuarialFrame in optimize mode to test direct execution
    af = ActuarialFrame(sample_lazy_frame, mode="optimize")

    # Act
    result_af = af.with_columns(
        (pl.col("a") + 1).alias("c"),
        pl.col("b").alias("d"),  # Use Polars expressions directly
    )

    # Assert
    assert result_af is af  # Should return self
    assert af.get_column_order() == ["a", "b", "c", "d"]
    collected = af.collect()
    assert "c" in collected.columns
    assert "d" in collected.columns
    assert collected["c"].to_list() == [2, 3, 4]  # a + 1
    assert collected["d"].to_list() == [4, 5, 6]  # b values


# Test collect / profile (mocking underlying call and error handling)
@patch("polars.LazyFrame.collect")
@patch("gaspatchio_core.errors._handle_execution_error")
def test_collect_calls_polars_collect(
    mock_handle_error, mock_collect, sample_lazy_frame
):
    # Arrange
    mock_result = MagicMock(spec=pl.DataFrame)
    mock_collect.return_value = mock_result
    af = ActuarialFrame(sample_lazy_frame)

    # Act
    result = af.collect()

    # Assert
    mock_collect.assert_called_once()
    mock_handle_error.assert_not_called()
    assert result is mock_result


@patch("polars.LazyFrame.collect")
def test_collect_handles_polars_error(mock_collect, sample_lazy_frame):
    # Arrange
    test_exception = pl.exceptions.ComputeError("Polars failed")
    mock_collect.side_effect = test_exception
    af = ActuarialFrame(sample_lazy_frame)

    # Act & Assert
    # Expect the framework's handler to catch and re-raise the error
    with pytest.raises(
        pl.exceptions.ComputeError, match="Polars failed"
    ):  # Check formatted message
        af.collect()  # Call collect, error handling is internal

    mock_collect.assert_called_once()


# Test profile (basic behavior - current impl collects)
@patch("polars.LazyFrame.profile")
def test_profile_calls_collect(mock_profile, sample_lazy_frame):
    # Arrange
    test_exception = pl.exceptions.ComputeError("Polars failed")
    mock_profile.side_effect = test_exception
    af = ActuarialFrame(sample_lazy_frame)

    # Act & Assert
    with pytest.raises(
        pl.exceptions.ComputeError, match="Polars failed"
    ):  # Check formatted message
        af.profile()

    mock_profile.assert_called_once()


# Test pipe
def test_pipe_applies_function(sample_lazy_frame):
    af = ActuarialFrame(sample_lazy_frame)

    def add_col_c(frame: ActuarialFrame) -> ActuarialFrame:
        frame["c"] = frame["a"] + frame["b"]
        return frame

    result_af = af.pipe(add_col_c)

    assert result_af is af  # Function modified in place
    assert "c" in af.get_column_order()  # Should be in column order
    
    # In debug/tracing mode, column only exists after collection
    collected = af.collect()
    assert "c" in collected.columns  # Should exist after collection
    assert collected["c"].to_list() == [5, 7, 9]  # a + b = [1,2,3] + [4,5,6] = [5,7,9]


def test_pipe_returns_self_if_func_returns_none(sample_lazy_frame):
    af = ActuarialFrame(sample_lazy_frame)

    def no_return(frame: ActuarialFrame):
        frame["c"] = 1  # Modify

    result_af = af.pipe(no_return)
    assert result_af is af
    assert "c" in af.get_column_order()


def test_pipe_raises_if_func_returns_wrong_type(sample_lazy_frame):
    af = ActuarialFrame(sample_lazy_frame)

    def wrong_return(frame: ActuarialFrame):
        return 123  # Not an ActuarialFrame

    with pytest.raises(TypeError):
        af.pipe(wrong_return)


# Test get_column_order
def test_get_column_order_reflects_setitem(sample_lazy_frame):
    af = ActuarialFrame(sample_lazy_frame)
    af["c"] = 1
    af["d"] = 2
    assert af.get_column_order() == ["a", "b", "c", "d"]


def test_get_column_order_reflects_with_columns(sample_lazy_frame):
    af = ActuarialFrame(sample_lazy_frame)
    af = af.with_columns((pl.col("a") + 1).alias("c"))
    assert af.get_column_order() == ["a", "b", "c"]
