# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test for issue #39: load_assumptions reentrancy bug fix."""

import polars as pl
import pytest

from gaspatchio_core.assumptions import Table


def test_table_reentrancy():
    """Test that tables can be re-registered without errors (issue #39)."""
    # Create test data
    data = pl.DataFrame(
        {
            "age": [25, 30, 35, 40, 45],
            "mortality_rate": [0.001, 0.002, 0.003, 0.004, 0.005],
        }
    )

    # First registration
    table1 = Table(
        name="mortality_test",
        source=data,
        dimensions={"age": "age"},
        value="mortality_rate",
    )

    # Verify lookup works
    lookup_expr = table1.lookup(age=pl.col("age"))
    assert isinstance(lookup_expr, pl.Expr)

    # Second registration with same name (simulating model re-run)
    # This should not raise an error anymore
    table2 = Table(
        name="mortality_test",  # Same name
        source=data,
        dimensions={"age": "age"},
        value="mortality_rate",
    )

    # Verify second table also works
    lookup_expr2 = table2.lookup(age=pl.col("age"))
    assert isinstance(lookup_expr2, pl.Expr)

    # Test with different data to ensure replacement works
    new_data = pl.DataFrame(
        {
            "age": [25, 30, 35, 40, 45],
            "mortality_rate": [0.002, 0.003, 0.004, 0.005, 0.006],  # Different values
        }
    )

    table3 = Table(
        name="mortality_test",  # Same name again
        source=new_data,
        dimensions={"age": "age"},
        value="mortality_rate",
    )

    # Test that the new values are used
    test_df = pl.DataFrame({"age": [25, 35, 45]})
    result = test_df.select(mortality=table3.lookup(age=pl.col("age")))

    # The lookup returns f64 values
    assert result["mortality"].to_list() == [0.002, 0.004, 0.006]


def test_multiple_tables_reentrancy():
    """Test reentrancy with multiple tables (simulating full model setup)."""
    # Simulate running a model setup multiple times
    for iteration in range(3):
        # Mortality table
        mortality_data = pl.DataFrame(
            {
                "age": [30, 35, 40],
                "rate": [0.001 * (iteration + 1), 0.002 * (iteration + 1), 0.003 * (iteration + 1)],
            }
        )

        mortality_table = Table(
            name="mortality_multi",
            source=mortality_data,
            dimensions={"age": "age"},
            value="rate",
        )

        # Lapse table
        lapse_data = pl.DataFrame(
            {
                "duration": [1, 2, 3, 4, 5],
                "lapse_rate": [0.1, 0.08, 0.06, 0.04, 0.02],
            }
        )

        lapse_table = Table(
            name="lapse_multi",
            source=lapse_data,
            dimensions={"duration": "duration"},
            value="lapse_rate",
        )

        # Interest table
        interest_data = pl.DataFrame(
            {
                "year": [2024, 2025, 2026],
                "interest_rate": [0.03, 0.035, 0.04],
            }
        )

        interest_table = Table(
            name="interest_multi",
            source=interest_data,
            dimensions={"year": "year"},
            value="interest_rate",
        )

        # Verify all tables work
        assert mortality_table.lookup(age=pl.col("age")) is not None
        assert lapse_table.lookup(duration=pl.col("duration")) is not None
        assert interest_table.lookup(year=pl.col("year")) is not None

        # Test actual lookup for mortality (values should match iteration)
        test_df = pl.DataFrame({"age": [30]})
        result = test_df.select(rate=mortality_table.lookup(age=pl.col("age")))
        expected_rate = 0.001 * (iteration + 1)
        # Get the scalar value
        actual_rate = result["rate"][0]
        assert abs(actual_rate - expected_rate) < 1e-10


def test_notebook_simulation():
    """Simulate notebook usage where cells might be re-executed."""
    # Cell 1: Load assumptions
    def load_assumptions():
        data = pl.DataFrame(
            {
                "age": list(range(20, 71)),
                "qx": [0.0001 + age * 0.00001 for age in range(20, 71)],
            }
        )
        return Table(
            name="notebook_mortality",
            source=data,
            dimensions={"age": "age"},
            value="qx",
        )

    # Execute "cell" multiple times
    for _ in range(5):
        table = load_assumptions()
        # Each execution should work without errors
        assert table is not None
        assert table._name == "notebook_mortality"

    # Verify final table works correctly
    test_df = pl.DataFrame({"age": [25, 40, 55]})
    result = test_df.select(qx=table.lookup(age=pl.col("age")))
    assert len(result) == 3
    # Get the scalar values
    qx_values = result["qx"].to_list()
    assert qx_values[0] > 0  # Just verify we got valid values


if __name__ == "__main__":
    pytest.main([__file__, "-v"])