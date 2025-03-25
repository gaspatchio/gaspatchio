import polars as pl
from gaspatchio_core.assumptions import table_registry
from loguru import logger

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
            "smoking_status": ["NS", "S"],  # NS = Non-smoker, S = Smoker
            "gender_smoking_status": ["MNS", "FS"],
        }
    )

    # Create mortality rates table matching parquet format
    mortality_df = pl.DataFrame(
        {
            "age_last": list(range(30, 33)),  # Ages 30-32
            "MNS": [0.0011, 0.0012, 0.0013],  # Male Non-Smoker
            "FNS": [0.001067, 0.001164, 0.001261],  # Female Non-Smoker
            "MS": [0.00132, 0.00144, 0.00156],  # Male Smoker
            "FS": [0.0012804, 0.0013968, 0.0015132],  # Female Smoker
        }
    )

    transform_spec = table_registry.TransformSpec(
        id_vars=["age_last"],  # Columns to keep as identifiers
        value_vars=["MNS", "FNS", "MS", "FS"],  # Columns to unpivot
        var_name="gender_smoking_status",  # Name for the column that will contain the unpivoted column names
        value_name="mortality_rate",  # Name for the column that will contain the values
    )

    # Create KeySpec and TransformSpec for the mortality table
    key_spec = table_registry.KeySpec(
        source_cols=["age_last", "gender_smoking_status"],
        table_cols=["age_last", "gender_smoking_status"],
    )

    # Register the mortality table with transform
    af_mortality = ActuarialFrame(mortality_df)
    af_mortality.register_table_with_transform(
        "mortality_rates", key_spec, transform_spec
    )

    # Perform vector lookup
    af = ActuarialFrame(df)
    result = af.lookup_table_vector("mortality_rates").collect()

    logger.debug("OG Dataframe")
    logger.debug(df)

    logger.debug("Mortality Rates DF")
    logger.debug(result)

    # Verify the structure of the result
    assert "policy_id" in result.columns
    assert "age_last" in result.columns
    assert "gender" in result.columns
    assert "smoking_status" in result.columns
    assert "mortality_rate" in result.columns

    # Verify no internal tracking columns are present
    assert "__row_idx" not in result.columns
    assert "__proj_idx" not in result.columns

    # Verify the gender column remains unchanged (not converted to list)
    assert result.schema["gender"] == pl.Utf8
    assert result.schema["smoking_status"] == pl.Utf8

    # Verify the policy_id column remains unchanged (not converted to list)
    assert result.schema["policy_id"] == pl.Int64

    # Verify the vector columns
    assert result.schema["age_last"].inner == pl.Int64
    assert result.schema["mortality_rate"].inner == pl.Float64

    # Verify specific mortality_rates
    # Get values for first row
    assert result.get_column("policy_id")[0] == 1
    assert result.get_column("gender")[0] == "M"
    assert result.get_column("smoking_status")[0] == "NS"
    assert result.get_column("age_last")[0].to_list() == [30, 31, 32]
    assert result.get_column("mortality_rate")[0].to_list() == [
        0.0011,
        0.0012,
        0.0013,
    ]  # Male Non-Smoker rates

    # Get values for second row
    assert result.get_column("policy_id")[1] == 2
    assert result.get_column("gender")[1] == "F"
    assert result.get_column("smoking_status")[1] == "S"
    assert result.get_column("age_last")[1].to_list() == [30, 31, 32]
    assert result.get_column("mortality_rate")[1].to_list() == [
        0.0012804,
        0.0013968,
        0.0015132,
    ]  # Female Smoker rates


def test_lookup_table_with_nulls():
    """Test lookup behavior with null values in the source data"""
    # Create test data with null values
    df_with_nulls = pl.DataFrame(
        {"policy_id": [1], "age_last": [None], "gender": ["M"]}
    ).with_columns([pl.col("age_last").cast(pl.Int64)])

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

    # Create ActuarialFrame and perform lookup
    af_nulls = ActuarialFrame(df_with_nulls)
    result = af_nulls.lookup_table("mortality_rates")
    result_value = result.collect()["mortality_rate"][0]

    # Verify that null input leads to null output
    assert result_value is None


def test_lookup_table_vector():
    """Test vector lookup functionality with mortality rates"""
    # Create test data with vector columns
    df = pl.DataFrame(
        {
            "policy_id": [1, 2],
            "age_last": [
                [30, 31, 32],  # First policy age progression
                [30, 31, 32],  # Second policy age progression (same ages)
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

    # Create ActuarialFrame and perform vector lookup
    af = ActuarialFrame(df)
    result = af.lookup_table_vector("mortality_rates").collect()

    # Verify the structure of the result
    assert len(result) == 2  # Should have 2 policies
    assert "mortality_rate" in result.columns

    # Get the mortality rates
    rates = result["mortality_rate"]

    # Verify each policy has the correct number of rates
    assert len(rates[0]) == 3  # First policy should have 3 rates
    assert len(rates[1]) == 3  # Second policy should have 3 rates

    # Verify rates are non-negative
    for policy_rates in rates:
        assert all(rate >= 0 for rate in policy_rates), (
            "All mortality rates should be non-negative"
        )

    # Verify rates increase with age (mortality should increase as people get older)
    assert all(rates[0][i] <= rates[0][i + 1] for i in range(len(rates[0]) - 1)), (
        "Mortality rates should increase with age"
    )
    assert all(rates[1][i] <= rates[1][i + 1] for i in range(len(rates[1]) - 1)), (
        "Mortality rates should increase with age"
    )

    # Verify specific values
    assert rates[0] == [0.001629, 0.00171, 0.001796]  # Male rates
    assert rates[1] == [0.08073, 0.084767, 0.089005]  # Female rates
