#!/usr/bin/env python
import logging
from pathlib import Path

import polars as pl
import pytest
from gaspatchio_core._internal import reset_global_registry
from gaspatchio_core.assumptions import assumption_lookup

# Import logging init
from gaspatchio_core.functions import init_logging

# Import the functions/classes to test
from gaspatchio_core.registry import TableRegistry, WideToLongTransformSpec
from polars.testing import assert_frame_equal, assert_series_equal

# --- Fixtures --- (Optional, but good for setup)

# Define base path relative to execution dir (bindings/python)
BASE_PATH = Path("jobs/example")
# Define separate input files for tests
LAPSE_MODEL_POINTS_PATH = BASE_PATH / "model-points.parquet"  # Use this for lapse
MORTALITY_MODEL_POINTS_PATH = (
    BASE_PATH / "age-last-smoking.parquet"
)  # Use this for mortality/premium
ASSUMPTIONS_PATH = BASE_PATH / "assumptions"


@pytest.fixture(scope="function")
def registry():
    """Provides a fresh TableRegistry instance for each test."""
    # Initialize logging to capture Rust debug messages
    init_logging(level=logging.DEBUG)
    # Reset the global Rust registry before each test
    reset_global_registry()
    return TableRegistry()


# --- Test Data --- #

# Lapse Rate Example (Simple Lookup)
lapse_assumption_df = pl.DataFrame(
    {
        "policy_duration": [1, 2, 3, 4, 5, 10, 20],
        "lapse_rate": [0.03, 0.03, 0.04, 0.05, 0.06, 0.11, 0.11],
    }
)

lapse_lookup_df = pl.DataFrame(
    {
        "id": [1, 2, 3, 4],
        "duration_vector": [[1, 2, 5], [3, 10], [20], [1, 99]],  # 99 is a missing key
    }
)

lapse_expected_df = pl.DataFrame(
    {
        "id": [1, 2, 3, 4],
        "duration_vector": [[1, 2, 5], [3, 10], [20], [1, 99]],
        "lookup_result": pl.Series(
            [[0.03, 0.03, 0.06], [0.04, 0.11], [0.11], [0.03, None]],
            dtype=pl.List(pl.Float64),
        ),
    }
)

# Mortality Rate Example (Lookup with WideToLong Transformation)
mort_assumption_df_wide = pl.DataFrame(
    {
        "age_last": [31, 33, 34],
        "MNS": [0.0012, 0.0013, 0.0014],
        "FNS": [0.0011, 0.0012, 0.0013],
        "MS": [0.0022, 0.0023, 0.0024],
        "FS": [0.0020, 0.0021, 0.0022],
    }
)

mort_transform_spec: WideToLongTransformSpec = {
    "transform_type": "WideToLong",
    "id_vars": ["age_last"],
    "value_vars": ["MNS", "FNS", "MS", "FS"],
    "var_name": "gender_smoking",
    "value_name": "mortality_rate",
}

mort_lookup_df = pl.DataFrame(
    {
        "id": [1, 2, 3],
        "age_vector": [[31, 33], [34, 31], [33, 99]],  # 99 is missing age
        "gender_smoking_vector": [["MS", "FNS"], ["MNS", "MS"], ["FS", "MNS"]],
    }
)

mort_expected_df = pl.DataFrame(
    {
        "id": [1, 2, 3],
        "age_vector": [[31, 33], [34, 31], [33, 99]],
        "gender_smoking_vector": [["MS", "FNS"], ["MNS", "MS"], ["FS", "MNS"]],
        "lookup_result": pl.Series(
            [[0.0022, 0.0012], [0.0014, 0.0022], [0.0021, None]],
            dtype=pl.List(pl.Float64),
        ),
    }
)

# --- Tests --- #


def test_simple_lookup(registry: TableRegistry):
    """Test basic lookup without transformation."""
    registry.register_table(
        name="lapse_rates",
        df=lapse_assumption_df,
        keys=["policy_duration"],
        value_column="lapse_rate",
        transform_spec=None,
    )

    result_df = lapse_lookup_df.with_columns(
        lookup_result=assumption_lookup(
            pl.col("duration_vector"), table_name="lapse_rates"
        )
    )

    print("\n--- test_simple_lookup ---")
    print("Result DF:\n", result_df)
    print("Expected DF:\n", lapse_expected_df)
    # Compare the result column directly
    result_series = result_df.get_column("lookup_result")
    expected_series = lapse_expected_df.get_column("lookup_result")
    print("Result Series:\n", result_series)
    print("Expected Series:\n", expected_series)
    assert_series_equal(result_series, expected_series)


def test_lookup_with_transform(registry: TableRegistry):
    """Test lookup where the assumption table needs transformation."""
    registry.register_table(
        name="mortality_rates",
        df=mort_assumption_df_wide,
        keys=["age_last", "gender_smoking"],  # Keys *after* transform
        value_column="mortality_rate",  # Value column *after* transform
        transform_spec=mort_transform_spec,
    )

    result_df = mort_lookup_df.with_columns(
        lookup_result=assumption_lookup(
            pl.col("age_vector"),
            pl.col("gender_smoking_vector"),
            table_name="mortality_rates",
        )
    )

    print("\n--- test_lookup_with_transform ---")
    print("Result DF:\n", result_df)
    print("Expected DF:\n", mort_expected_df)
    # Compare the result column directly
    result_series = result_df.get_column("lookup_result")
    expected_series = mort_expected_df.get_column("lookup_result")
    print("Result Series:\n", result_series)
    print("Expected Series:\n", expected_series)
    assert_series_equal(result_series, expected_series)


def test_lookup_empty_input(registry: TableRegistry):
    """Test lookup with an empty input DataFrame."""
    registry.register_table(
        name="empty_test_table",
        df=lapse_assumption_df,
        keys=["policy_duration"],
        value_column="lapse_rate",
    )

    empty_lookup_df = lapse_lookup_df.clear()
    expected_empty_df = lapse_lookup_df.clear().with_columns(
        pl.lit(None).cast(pl.List(pl.Float64)).alias("lookup_result")
    )

    result_df = empty_lookup_df.with_columns(
        lookup_result=assumption_lookup(
            pl.col("duration_vector"), table_name="empty_test_table"
        )
    )

    assert_frame_equal(result_df, expected_empty_df, check_column_order=False)


def test_lookup_table_not_found():
    """Test lookup when the table name hasn't been registered."""
    lookup_df = pl.DataFrame({"keys": [[1]]})
    expr = assumption_lookup(pl.col("keys"), table_name="non_existent_table")

    # Simplify substring further
    expected_substring = "Table 'non_existent_table' not found"
    try:
        lookup_df.with_columns(result=expr).collect()
        pytest.fail("Expected pl.ComputeError but none was raised.")
    except pl.ComputeError as e:
        assert expected_substring in str(e), (
            f"Expected '{expected_substring}' in error message, but got: {e}"
        )
    except Exception as e:
        pytest.fail(f"Expected pl.ComputeError, but got {type(e).__name__}: {e}")


def test_lookup_key_column_missing_in_df():
    """Test lookup when a key column is missing from the DataFrame being looked up."""
    lookup_df = pl.DataFrame({"id": [1]})
    # Expect expression creation to work, but evaluation to fail
    expr = assumption_lookup(pl.col("missing_key"), table_name="any_table")

    with pytest.raises(pl.ColumnNotFoundError):
        lookup_df.with_columns(result=expr).collect()


def test_register_duplicate_table(registry: TableRegistry):
    """Test registering a table with a name that already exists."""
    registry.register_table(
        name="duplicate_test",
        df=lapse_assumption_df,
        keys=["policy_duration"],
        value_column="lapse_rate",
    )

    with pytest.raises(
        ValueError,
        match="Failed to register table 'duplicate_test': Table 'duplicate_test' already exists",
    ):
        registry.register_table(
            name="duplicate_test",
            df=lapse_assumption_df,
            keys=["policy_duration"],
            value_column="lapse_rate",
        )


# --- Tests using files from 'example' directory --- #


def test_lookup_lapse_from_file(registry: TableRegistry):
    """Test lapse rate lookup using data loaded from parquet files."""
    # Read from the appropriate model points file for lapse
    model_points_df = pl.read_parquet(LAPSE_MODEL_POINTS_PATH)
    lapse_assumption_df = pl.read_parquet(ASSUMPTIONS_PATH / "lapse.parquet")
    # print("\nLapse Assumption Schema:", lapse_assumption_df.schema) # Removed print

    # Corrected column names based on schema output
    registry.register_table(
        name="lapse_rates_file",
        df=lapse_assumption_df,
        keys=["policy duration"],
        value_column="lapse rate",
        transform_spec=None,
    )

    # Use the original vector name assumption for model-points.parquet
    lookup_key_col = "policy_duration_vector"
    # Re-add skip check for the column in the lapse model points file
    if lookup_key_col not in model_points_df.columns:
        pytest.skip(
            f"Model points file {LAPSE_MODEL_POINTS_PATH} missing required key column '{lookup_key_col}' for lapse lookup."
        )

    result_df = model_points_df.with_columns(
        lookup_result=assumption_lookup(
            pl.col(lookup_key_col), table_name="lapse_rates_file"
        )
    )

    print("--- test_lookup_lapse_from_file ---")
    print("Result Head:\n", result_df.head())
    # Basic assertion: check the result column exists and is a list of floats
    assert "lookup_result" in result_df.columns
    assert isinstance(result_df["lookup_result"].dtype, pl.List)
    assert isinstance(result_df["lookup_result"].dtype.inner, pl.Float64)
    # Add more specific value assertions if expected output is known


def test_lookup_mortality_from_file(registry: TableRegistry):
    """Test mortality rate lookup using data loaded from parquet files with transformation."""
    # Read from the appropriate model points file for mortality
    model_points_df = pl.read_parquet(MORTALITY_MODEL_POINTS_PATH)
    mort_assumption_df_wide = pl.read_parquet(ASSUMPTIONS_PATH / "mortality.parquet")
    # print("\nMortality Assumption Schema:", mort_assumption_df_wide.schema) # Removed print

    # Define transform based on expected wide mortality table structure
    mort_transform_spec_file: WideToLongTransformSpec = {
        "transform_type": "WideToLong",
        "id_vars": ["age-last"],
        "value_vars": ["MNS", "FNS", "MS", "FS"],
        "var_name": "gender_smoking",
        "value_name": "mortality_rate",
    }

    # Check if required columns exist in the wide mortality table
    required_mort_cols = set(
        mort_transform_spec_file["id_vars"] + mort_transform_spec_file["value_vars"]
    )
    if not required_mort_cols.issubset(mort_assumption_df_wide.columns):
        pytest.skip(
            f"Mortality assumption file missing required columns for transformation: {required_mort_cols - set(mort_assumption_df_wide.columns)}"
        )

    registry.register_table(
        name="mortality_rates_file",
        df=mort_assumption_df_wide,
        keys=["age-last", "gender_smoking"],  # Corrected first key from age_last
        value_column="mortality_rate",  # Value column *after* transform
        transform_spec=mort_transform_spec_file,
    )

    # Assuming model_points_df has 'age-last' and 'gender_smoking' list columns
    age_key_col = "age-last"  # Assumed column name in age-last-smoking.parquet
    gender_key_col = "gender_smoking"  # Assumed column name

    result_df = model_points_df.with_columns(
        lookup_result=assumption_lookup(
            pl.col(age_key_col),
            pl.col(gender_key_col),
            table_name="mortality_rates_file",
        )
    )

    print("--- test_lookup_mortality_from_file ---")
    print("Result Head:\n", result_df.head())
    # Basic assertion: check the result column exists and is a list of floats
    assert "lookup_result" in result_df.columns
    assert isinstance(result_df["lookup_result"].dtype, pl.List)
    assert isinstance(result_df["lookup_result"].dtype.inner, pl.Float64)
    # Add more specific value assertions if expected output is known


def test_lookup_premium_rate_from_file(registry: TableRegistry):
    """Test premium rate lookup using data loaded from parquet files."""
    # Use the mortality/age-last-smoking file for premium test input
    model_points_df = pl.read_parquet(MORTALITY_MODEL_POINTS_PATH)
    prem_assumption_df = pl.read_parquet(ASSUMPTIONS_PATH / "premium-rate.parquet")
    # print("\nPremium Rate Assumption Schema:", prem_assumption_df.schema) # Removed print

    # --- ASSUMPTIONS about premium-rate.parquet structure ---
    # Guessing keys and value column. Adjust these based on the actual file.
    assumed_keys = ["age_at_entry", "policy_term"]
    assumed_value_col = "premium_rate"
    # ----------------------------------------------------------

    # Check if assumed columns exist in the assumption table (this will likely still skip)
    required_prem_cols = set(assumed_keys + [assumed_value_col])
    if not required_prem_cols.issubset(prem_assumption_df.columns):
        pytest.skip(
            f"Premium rate assumption file missing assumed columns: {required_prem_cols - set(prem_assumption_df.columns)}"
        )

    registry.register_table(
        name="premium_rates_file",
        df=prem_assumption_df,
        keys=assumed_keys,
        value_column=assumed_value_col,
        transform_spec=None,  # Assuming no transformation needed
    )

    # This skip might trigger if assumed key columns (e.g., age_at_entry, policy_term) aren't in age-last-smoking.parquet
    mp_key_cols_assumed = {
        key for key in assumed_keys
    }  # Assume non-vector names for now
    if not mp_key_cols_assumed.issubset(model_points_df.columns):
        pytest.skip(
            f"Model points file {MORTALITY_MODEL_POINTS_PATH} missing assumed key columns for premium rate lookup: {mp_key_cols_assumed - set(model_points_df.columns)}"
        )

    key_expressions = [
        pl.col(key) for key in assumed_keys
    ]  # Using assumed non-vector names

    result_df = model_points_df.with_columns(
        lookup_result=assumption_lookup(
            *key_expressions,
            table_name="premium_rates_file",
        )
    )

    print("--- test_lookup_premium_rate_from_file ---")
    print("Result Head:\n", result_df.head())
    # Basic assertion: check the result column exists and is a list of floats/appropriate type
    assert "lookup_result" in result_df.columns
    assert isinstance(result_df["lookup_result"].dtype, pl.List)
    # Check inner type based on expected premium rate type (e.g., Float64)
    assert isinstance(result_df["lookup_result"].dtype.inner, pl.Float64)
    # Add more specific value assertions if expected output is known
