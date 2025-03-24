import polars as pl
from gaspatchio_core.assumptions import table_registry

# Try to import numba, but make it optional
try:
    import numba

    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

    # Define empty functions as placeholders
    class numba:
        @staticmethod
        def vectorize(func):
            return func

        @staticmethod
        def njit(func):
            return func


from gaspatchio_core.dsl.core import (
    ActuarialFrame,
)


def test_lookup_table_vector_column_preservation():
    """Test that vector lookup preserves original column structure and doesn't add tracking columns"""
    # Create test data with vector columns
    df = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "age_last": [
                [30, 31, 32],  # First policy age progression
                [30, 31, 32],  # Second policy age progression
            ],
            "gender": ["M", "F"],
        }
    )

    # Create mortality rates table
    mortality_df = pl.DataFrame(
        {
            "age_last": list(range(30, 33)),  # Ages 30-32
            "gender": ["M"] * 3 + ["F"] * 3,  # Repeat for each gender
            "mortality_rate": [0.001629, 0.00171, 0.001796]
            + [0.08073, 0.084767, 0.089005],
        }
    )

    # Create KeySpec for the mortality table
    key_spec = table_registry.KeySpec(
        source_cols=["age_last", "gender"], table_cols=["age_last", "gender"]
    )

    # Register the mortality table
    table_registry.py_register_table("mortality_rates", mortality_df, key_spec)

    # Perform vector lookup
    af = ActuarialFrame(df)
    result = af.lookup_table_vector("mortality_rates").collect()

    # Verify the structure of the result
    assert "policy_id" in result.columns
    assert "age_last" in result.columns
    assert "gender" in result.columns
    assert "mortality_rate" in result.columns

    # Verify no internal tracking columns are present
    assert "__row_idx" not in result.columns
    assert "__proj_idx" not in result.columns

    # Verify the gender column remains unchanged (not converted to list)
    assert result.schema["gender"] == pl.Utf8

    # Verify the policy_id column remains unchanged (not converted to list)
    assert result.schema["policy_id"] == pl.Int64

    # Verify the vector columns
    assert result.schema["age_last"].inner == pl.Int64
    assert result.schema["mortality_rate"].inner == pl.Float64

    # Verify specific values
    first_row = result.row(0)
    assert first_row["policy_id"] == 1
    assert first_row["gender"] == "M"
    assert first_row["age_last"] == [30, 31, 32]
    assert first_row["mortality_rate"] == [0.001629, 0.00171, 0.001796]

    second_row = result.row(1)
    assert second_row["policy_id"] == 2
    assert second_row["gender"] == "F"
    assert second_row["age_last"] == [30, 31, 32]
    assert second_row["mortality_rate"] == [0.08073, 0.084767, 0.089005]
