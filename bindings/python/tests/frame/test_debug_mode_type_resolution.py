"""Test debug vs optimize mode type resolution differences."""

import pytest
import polars as pl
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.util import set_default_mode, get_default_mode


@pytest.fixture(autouse=True)
def reset_mode():
    """Reset mode after each test."""
    original_mode = get_default_mode()
    yield
    set_default_mode(original_mode)


@pytest.mark.xfail(reason="Known issue with fill_null on list columns in optimize mode")
def test_fill_null_list_column_optimize_mode():
    """Test that fill_null works with list columns in optimize mode."""
    set_default_mode("optimize")
    
    # Create test data with list column and a null value
    data = {
        "policy_id": [1, 2, 3],
        "monthly_values": [[1.0, 2.0, 3.0], None, [4.0, 5.0, 6.0]]
    }
    af = ActuarialFrame(data)
    
    # Apply operations similar to the model
    af["filled_values"] = af["monthly_values"].fill_null(pl.lit([0.0, 0.0, 0.0]))
    
    # Should work without error
    result = af.collect()
    assert result.shape[0] == 3


@pytest.mark.xfail(reason="Known issue with fill_null on list columns in debug mode")
def test_fill_null_list_column_debug_mode():
    """Test that fill_null works with list columns in debug mode."""
    set_default_mode("debug")
    
    # Create test data with list column and a null value
    data = {
        "policy_id": [1, 2, 3],
        "monthly_values": [[1.0, 2.0, 3.0], None, [4.0, 5.0, 6.0]]
    }
    af = ActuarialFrame(data)
    
    # Apply operations similar to the model
    af["filled_values"] = af["monthly_values"].fill_null(pl.lit([0.0, 0.0, 0.0]))
    
    # This should work without error (but currently fails)
    result = af.collect()
    assert result.shape[0] == 3


def test_scalar_fill_null_optimize_mode():
    """Test that fill_null works with scalar columns in optimize mode."""
    set_default_mode("optimize")
    
    data = {
        "policy_id": [1, 2],
        "value": [1.0, 2.0]
    }
    af = ActuarialFrame(data)
    
    af["shifted_value"] = af["value"].shift(1).fill_null(0.0)
    
    result = af.collect()
    assert result.shape[0] == 2


def test_scalar_fill_null_debug_mode():
    """Test that fill_null works with scalar columns in debug mode."""
    set_default_mode("debug")
    
    data = {
        "policy_id": [1, 2],
        "value": [1.0, 2.0]
    }
    af = ActuarialFrame(data)
    
    af["shifted_value"] = af["value"].shift(1).fill_null(0.0)
    
    result = af.collect()
    assert result.shape[0] == 2


@pytest.mark.xfail(reason="Known issue with complex expression chains on list columns in optimize mode")
def test_complex_expression_chain_optimize_mode():
    """Test complex expression chains work in optimize mode."""
    set_default_mode("optimize")
    
    data = {
        "policy_id": [1, 2],
        "monthly_persist": [[0.9, 0.8, 0.7], [0.95, 0.85, 0.75]]
    }
    af = ActuarialFrame(data)
    
    # Mimic the model's P[IF] calculation
    af["P[IF]"] = af["monthly_persist"].cum_prod().shift(1).fill_null(pl.lit([1.0]))
    
    result = af.collect()
    assert result.shape[0] == 2


@pytest.mark.xfail(reason="Known issue with complex expression chains on list columns in debug mode")
def test_complex_expression_chain_debug_mode():
    """Test complex expression chains work in debug mode."""
    set_default_mode("debug")
    
    data = {
        "policy_id": [1, 2],
        "monthly_persist": [[0.9, 0.8, 0.7], [0.95, 0.85, 0.75]]
    }
    af = ActuarialFrame(data)
    
    # Mimic the model's P[IF] calculation
    af["P[IF]"] = af["monthly_persist"].cum_prod().shift(1).fill_null(pl.lit([1.0]))
    
    result = af.collect()
    assert result.shape[0] == 2


@pytest.mark.xfail(reason="Known issue with traced functions handling list columns")
def test_traced_function_execution():
    """Test that traced functions work correctly in debug mode."""
    set_default_mode("debug")
    
    data = {
        "policy_id": [1, 2],
        "mortality_rate": [[0.01, 0.02, 0.03], [0.015, 0.025, 0.035]]
    }
    af = ActuarialFrame(data)
    
    @af.trace
    def calculate_probabilities(frame):
        # Operations similar to the failing model
        frame["monthly_persist"] = [[0.99, 0.98, 0.97], [0.985, 0.975, 0.965]]
        frame["P[IF]"] = frame["monthly_persist"].cum_prod().shift(1).fill_null(pl.lit([1.0]))
        frame["P[death]"] = frame["P[IF]"] * (frame["mortality_rate"] / 12).shift(1).fill_null(pl.lit([0.0]))
        return frame
    
    result_af = calculate_probabilities(af)
    result = result_af.collect()
    assert result.shape[0] == 2


# if __name__ == "__main__":
#     # Run a quick test to see the failure
#     test_fill_null_list_column_debug_mode()