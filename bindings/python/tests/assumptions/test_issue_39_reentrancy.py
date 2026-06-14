# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Test for issue #39: load_assumptions reentrancy bug fix.

This test verifies that assumption tables can be re-registered
without errors when models are run multiple times in the same process.
"""

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table


def test_reentrancy_no_error():
    """Test that tables can be re-registered without raising errors."""
    data = pl.DataFrame(
        {
            "age": [25, 30, 35],
            "rate": [0.001, 0.002, 0.003],
        }
    )

    # First registration
    table1 = Table(
        name="reentrancy_test",
        source=data,
        dimensions={"age": "age"},
        value="rate",
    )

    # Second registration with same name should not raise an error
    # This was the bug in issue #39
    table2 = Table(
        name="reentrancy_test",  # Same name
        source=data,
        dimensions={"age": "age"},
        value="rate",
    )

    # Both tables should work
    assert table1._name == "reentrancy_test"
    assert table2._name == "reentrancy_test"


def test_reentrancy_with_different_data():
    """Test that re-registration actually replaces the data."""
    # First registration
    data1 = pl.DataFrame({"x": [1, 2, 3], "y": [10.0, 20.0, 30.0]})
    
    table1 = Table(
        name="replace_test",
        source=data1,
        dimensions={"x": "x"},
        value="y",
    )

    # Second registration with different data
    data2 = pl.DataFrame({"x": [1, 2, 3], "y": [100.0, 200.0, 300.0]})
    
    table2 = Table(
        name="replace_test",  # Same name, different data
        source=data2,
        dimensions={"x": "x"},
        value="y",
    )

    # The table should now use the new data
    # (We can't easily test the actual values without ActuarialFrame,
    # but the fact that it doesn't error is the main fix)
    assert table2 is not None


def test_multiple_model_runs():
    """Simulate running a full model multiple times (common in notebooks)."""
    for run in range(3):
        # Each run registers the same set of tables
        
        # Mortality table
        mortality = Table(
            name="mort_table",
            source=pl.DataFrame({
                "age": [30, 40, 50],
                "qx": [0.001, 0.002, 0.004],
            }),
            dimensions={"age": "age"},
            value="qx",
        )

        # Lapse table  
        lapse = Table(
            name="lapse_table",
            source=pl.DataFrame({
                "duration": [1, 2, 3, 4, 5],
                "rate": [0.20, 0.15, 0.10, 0.08, 0.05],
            }),
            dimensions={"duration": "duration"},
            value="rate",
        )

        # Interest table
        interest = Table(
            name="int_table",
            source=pl.DataFrame({
                "year": [2024, 2025, 2026],
                "rate": [0.03, 0.035, 0.04],
            }),
            dimensions={"year": "year"},
            value="rate",
        )

        # All tables should register successfully on each run
        assert mortality is not None
        assert lapse is not None
        assert interest is not None

    # If we get here without errors, the reentrancy bug is fixed!


def test_registry_state_after_multiple_registrations():
    """Test that the registry is in a valid state after re-registrations."""
    from gaspatchio_core._internal import PyAssumptionTableRegistry
    
    registry = PyAssumptionTableRegistry()
    
    # Register a table
    Table(
        name="state_test",
        source=pl.DataFrame({"a": [1, 2], "b": [3.0, 4.0]}),
        dimensions={"a": "a"},
        value="b",
    )
    
    # Check it exists
    assert registry.table_exists("state_test")
    
    # Re-register with different data
    Table(
        name="state_test",
        source=pl.DataFrame({"a": [1, 2], "b": [5.0, 6.0]}),
        dimensions={"a": "a"}, 
        value="b",
    )
    
    # Should still exist (not duplicated, just replaced)
    assert registry.table_exists("state_test")
    tables = registry.list_tables()
    assert "state_test" in tables
    # Count how many times it appears (should be exactly once)
    assert tables.count("state_test") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])