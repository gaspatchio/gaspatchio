import datetime
from pathlib import Path

import polars as pl
import pytest
from datacompy import PolarsCompare
from dateutil.relativedelta import relativedelta
from gaspatchio_core.dates import create_projection_timeline, generate_projection_dates
from gaspatchio_core.dsl.core import ActuarialFrame


def test_fixture_load():
    # Load fixture CSV and ensure it loads correctly
    fixture = Path(__file__).parent / "fixtures" / "age-dates-test.csv"
    df = pl.read_csv(fixture.as_posix(), infer_schema_length=10000)
    # Assert expected columns and row count
    assert "age" in df.columns
    assert df.height > 0
    assert len(df.columns) == 5


# === Pytest Tests for create_projection_timeline ===


def test_create_projection_timeline_max_age_monthly():
    # Setup input with issue age 99 (1 year to project)
    df = pl.DataFrame({"Policyholder issue age": [99]})
    af = ActuarialFrame(df, mode="debug")
    valuation_date = datetime.date(2020, 1, 15)

    # Run timeline creation matching model_calculation.py params
    result_af = create_projection_timeline(
        af=af,
        valuation_date=valuation_date,
        projection_end_type="maximum_age",
        projection_end_value=100,
        issue_age_column="Policyholder issue age",
        projection_frequency="monthly",
        projection_start_offset_months=12,
        store_start_date=True,
        store_end_date=True,
        output_column="proj_months",
    )
    df_out = result_af.collect()

    # Expected start and end dates
    expected_start = datetime.date(2021, 1, 15)
    expected_end = datetime.date(2022, 1, 15)

    # Assert columns exist
    assert "projection_start_date" in df_out.columns
    assert "projection_end_date" in df_out.columns
    assert "proj_months" in df_out.columns

    # Check start and end values
    assert df_out["projection_start_date"][0] == expected_start
    assert df_out["projection_end_date"][0] == expected_end

    # Check projection list
    proj_list = df_out["proj_months"][0]
    # Should be a Polars Series of dates
    assert isinstance(proj_list, pl.Series)
    # intervals = 12, length = 13
    assert len(proj_list) == 13
    # first equals start, last equals start + 12*30 days
    assert proj_list[0] == expected_start
    # last date should be start + 12 months
    assert proj_list[-1] == expected_start + relativedelta(months=12)


def test_term_years_quarterly():
    df = pl.DataFrame({"id": [1]})  # No age dependency
    af = ActuarialFrame(df, mode="debug")
    valuation_date = datetime.date(2021, 3, 1)

    result_af = create_projection_timeline(
        af=af,
        valuation_date=valuation_date,
        projection_end_type="term_years",
        projection_end_value=2,  # Project for 2 years
        issue_age_column="Policyholder issue age",  # Not used but required
        projection_frequency="quarterly",
        projection_start_offset_months=0,
        store_start_date=True,
        store_end_date=True,
        output_column="proj_quarters",
    )
    df_out = result_af.collect()

    expected_start = datetime.date(2021, 3, 1)
    expected_end = datetime.date(2023, 3, 1)

    assert df_out["projection_start_date"][0] == expected_start
    assert df_out["projection_end_date"][0] == expected_end

    proj_list = df_out["proj_quarters"][0]
    assert isinstance(proj_list, pl.Series)
    # 2 years * 4 quarters = 8 intervals -> length 9
    assert len(proj_list) == 9
    assert proj_list[0] == expected_start
    # 8 intervals * 91 days/quarter
    assert proj_list[-1] == expected_start + relativedelta(months=8 * 3)


def test_term_months_semi_annual():
    df = pl.DataFrame({"id": [1]})
    af = ActuarialFrame(df, mode="debug")
    valuation_date = datetime.date(2022, 7, 1)

    result_af = create_projection_timeline(
        af=af,
        valuation_date=valuation_date,
        projection_end_type="term_months",
        projection_end_value=18,  # Project for 18 months
        issue_age_column="Policyholder issue age",
        projection_frequency="semi-annual",
        projection_start_offset_months=3,  # Offset start by 3 months
        store_start_date=True,
        store_end_date=True,
        output_column="proj_semi_annual",
    )
    df_out = result_af.collect()

    expected_start = datetime.date(2022, 10, 1)
    expected_end = datetime.date(2024, 4, 1)

    assert df_out["projection_start_date"][0] == expected_start
    assert df_out["projection_end_date"][0] == expected_end

    proj_list = df_out["proj_semi_annual"][0]
    assert isinstance(proj_list, pl.Series)
    # 18 months / 6 months/interval = 3 intervals -> length 4
    assert len(proj_list) == 4
    assert proj_list[0] == expected_start
    # 3 intervals * 182 days/semi-annual
    assert proj_list[-1] == expected_start + relativedelta(months=3 * 6)


def test_fixed_date_annual():
    df = pl.DataFrame({"id": [1]})
    af = ActuarialFrame(df, mode="debug")
    valuation_date = datetime.date(2020, 1, 1)
    fixed_end_date = datetime.date(2023, 1, 1)

    result_af = create_projection_timeline(
        af=af,
        valuation_date=valuation_date,
        projection_end_type="fixed_date",
        projection_end_value=fixed_end_date,
        issue_age_column="Policyholder issue age",
        projection_frequency="annual",
        projection_start_offset_months=0,
        store_start_date=True,
        store_end_date=True,
        output_column="proj_annual",
    )
    df_out = result_af.collect()

    expected_start = datetime.date(2020, 1, 1)
    # End date for fixed_date is the specified value
    expected_end = fixed_end_date

    assert df_out["projection_start_date"][0] == expected_start
    assert df_out["projection_end_date"][0] == expected_end

    proj_list = df_out["proj_annual"][0]
    assert isinstance(proj_list, pl.Series)
    # 2023 - 2020 = 3 year intervals -> length 4
    assert len(proj_list) == 4
    assert proj_list[0] == expected_start
    # 3 intervals * 365 days/year
    assert proj_list[-1] == expected_start + relativedelta(years=3)


def test_invalid_frequency():
    df = pl.DataFrame({"Policyholder issue age": [50]})
    af = ActuarialFrame(df, mode="debug")
    valuation_date = datetime.date(2020, 1, 1)

    with pytest.raises(
        ValueError, match="Invalid projection frequency"
    ):  # Check the error message
        create_projection_timeline(
            af=af,
            valuation_date=valuation_date,
            projection_end_type="maximum_age",
            projection_end_value=100,
            issue_age_column="Policyholder issue age",
            projection_frequency="bi-weekly",  # Invalid frequency
            projection_start_offset_months=0,
            store_start_date=True,
            store_end_date=True,
            output_column="proj_invalid",
        )


def test_invalid_end_type():
    df = pl.DataFrame({"Policyholder issue age": [50]})
    af = ActuarialFrame(df, mode="debug")
    valuation_date = datetime.date(2020, 1, 1)

    with pytest.raises(
        ValueError, match="Invalid projection end type"
    ):  # Check error message
        create_projection_timeline(
            af=af,
            valuation_date=valuation_date,
            projection_end_type="until_further_notice",  # Invalid end type
            projection_end_value=100,
            issue_age_column="Policyholder issue age",
            projection_frequency="monthly",
            projection_start_offset_months=0,
            store_start_date=True,
            store_end_date=True,
            output_column="proj_invalid",
        )


# === Direct test for generate_projection_dates ===


def test_generate_projection_dates_month_end():
    # Test monthly frequency starting at month end
    start_date = datetime.date(2026, 1, 31)
    # Project for 2 months
    end_date = start_date.replace(month=3)
    row = {"projection_start_date": start_date, "projection_end_date": end_date}

    # Call the function directly
    proj_dates = generate_projection_dates(row, projection_frequency="monthly")

    # Expected dates (using proper month increments)
    expected_dates = [
        datetime.date(2026, 1, 31),
        datetime.date(2026, 2, 28),
        datetime.date(2026, 3, 31),
    ]

    # This assertion will likely fail with the current implementation
    assert proj_dates == expected_dates


def test_generate_projection_dates_matches_fixture():
    # Load fixture CSV, reading date column as String initially
    fixture_path = Path(__file__).parent / "fixtures" / "age-dates-test.csv"
    expected_df = pl.read_csv(
        fixture_path.as_posix(),
        # Read date as string first
        schema_overrides={"date": pl.String},
        infer_schema_length=10000,
    )

    # Explicitly parse the string date column
    expected_df = expected_df.with_columns(
        pl.col("date").str.to_date("%d/%m/%Y", strict=True).alias("date_parsed")
    )

    # Extract expected dates and start/end
    expected_dates_series = expected_df["date_parsed"]
    start_date = expected_dates_series.min()
    end_date = expected_dates_series.max()

    # Prepare row for generate_projection_dates
    row = {"projection_start_date": start_date, "projection_end_date": end_date}

    # Call the function directly
    generated_dates_list = generate_projection_dates(
        row, projection_frequency="monthly"
    )

    # Convert generated list to Polars Series for comparison
    generated_dates_series = pl.Series("generated", generated_dates_list, dtype=pl.Date)

    # Compare the generated dates with the fixture dates
    pl.testing.assert_series_equal(
        generated_dates_series,
        expected_dates_series,
        check_names=False,
        check_dtypes=True,
    )


def test_timeline_generation_matches_reconciliation_fixture():
    """Verify create_projection_timeline output matches age-dates.csv for the first model point."""
    base_path = Path(__file__).parent
    recon_fixture_path = base_path / "fixtures" / "age-dates-test.csv"
    mpf_fixture_path = base_path / "fixtures" / "model-points-test.parquet"

    # 1. Load expected dates from age-dates.csv and add row number
    expected_df = pl.read_csv(
        recon_fixture_path.as_posix(),
        schema_overrides={"date": pl.String},  # Read as string first
        infer_schema_length=10000,
    ).with_row_count("row_nr")  # Add row number as join key

    # Explicitly parse the string date column
    expected_df = expected_df.with_columns(
        pl.col("date")
        .str.to_date("%d/%m/%Y", strict=True)
        .alias("date")  # Rename parsed col to 'date'
    )

    # 2. Load the first model point
    input_df = pl.read_parquet(mpf_fixture_path).head(1)

    # 3. Prepare ActuarialFrame and parameters
    af_input = ActuarialFrame(input_df, mode="debug")
    valuation_date = datetime.date(2024, 12, 31)
    issue_age_col = "Policyholder issue age"  # From model_calculation.py context
    # Ensure the required column exists in the parquet file
    assert issue_age_col in input_df.columns

    # 4. Run create_projection_timeline with model_calculation.py params
    af_output = create_projection_timeline(
        af=af_input,
        valuation_date=valuation_date,
        projection_end_type="maximum_age",
        projection_end_value=100,
        issue_age_column=issue_age_col,
        projection_frequency="monthly",
        projection_start_offset_months=12,
        store_start_date=True,  # Keep these to ensure the columns exist for generate_projection_dates
        store_end_date=True,
        output_column="generated_proj_dates",
    )

    # 5. Extract generated dates and create DataFrame with row number
    df_out = af_output.collect()

    print(df_out)

    generated_dates_list = df_out["generated_proj_dates"][0]
    generated_df = pl.DataFrame(
        {"date": generated_dates_list}  # Use common column name 'date'
    ).with_row_count("row_nr")  # Add row number as join key

    print(generated_df)

    # 6. Compare using DataComPy
    # If lengths match, perform detailed comparison
    compare = PolarsCompare(
        generated_df,
        expected_df,
        join_columns=["row_nr"],  # Join on the row number
        df1_name="Generated",
        df2_name="Expected (CSV)",
    )

    # Always run the comparison, even if lengths differ, to get the report
    if not compare.matches(
        ignore_extra_columns=True
    ):  # Ignore length differences for matching logic
        print("\nDataComPy Report:")
        print(compare.report())

        # Try to find the first mismatch in the intersecting rows
        first_mismatch_info = "Could not determine first mismatch row."
        if (
            not compare.intersect_rows.is_empty()
            and "date_match" in compare.intersect_rows.columns
        ):
            mismatched_rows = compare.intersect_rows.filter(
                pl.col("date_match") == False
            )
            if not mismatched_rows.is_empty():
                first_mismatch_row_nr = mismatched_rows["row_nr"].min()
                first_mismatch_gen = generated_df.filter(
                    pl.col("row_nr") == first_mismatch_row_nr
                )["date"][0]
                first_mismatch_exp = expected_df.filter(
                    pl.col("row_nr") == first_mismatch_row_nr
                )["date"][0]
                first_mismatch_info = (
                    f"First mismatch occurred at row number (0-based): {first_mismatch_row_nr}\n"
                    f"  Generated Date: {first_mismatch_gen}\n"
                    f"  Expected Date:  {first_mismatch_exp}"
                )

        print(f"\n{first_mismatch_info}")
        pytest.fail(
            "Generated dates do not match expected dates. See report and first mismatch above."
        )


def test_error_when_start_date_not_stored():
    """Verify dates are generated but start date column is absent if store_start_date=False."""
    df = pl.DataFrame({"Policyholder issue age": [50]})
    af = ActuarialFrame(df, mode="debug")
    valuation_date = datetime.date(2020, 1, 1)

    af_output = create_projection_timeline(
        af=af,
        valuation_date=valuation_date,
        projection_end_type="maximum_age",
        projection_end_value=100,
        issue_age_column="Policyholder issue age",
        projection_frequency="monthly",
        store_start_date=False,  # Explicitly don't store start date
        store_end_date=True,
        output_column="proj_dates",
    )

    # Collect should now succeed
    df_out = af_output.collect()

    # Assert proj_dates exists and has expected length (50 years * 12 + 1)
    assert "proj_dates" in df_out.columns
    assert len(df_out["proj_dates"][0]) == (100 - 50) * 12 + 1

    # Assert start date column is NOT present, but end date IS present
    assert "projection_start_date" not in df_out.columns
    assert "projection_end_date" in df_out.columns


def test_error_when_end_date_not_stored():
    """Verify dates are generated but end date column is absent if store_end_date=False."""
    df = pl.DataFrame({"Policyholder issue age": [50]})
    af = ActuarialFrame(df, mode="debug")
    valuation_date = datetime.date(2020, 1, 1)

    af_output = create_projection_timeline(
        af=af,
        valuation_date=valuation_date,
        projection_end_type="maximum_age",
        projection_end_value=100,
        issue_age_column="Policyholder issue age",
        projection_frequency="monthly",
        store_start_date=True,
        store_end_date=False,  # Explicitly don't store end date
        output_column="proj_dates",
    )

    # Collect should now succeed
    df_out = af_output.collect()

    # Assert proj_dates exists and has expected length (50 years * 12 + 1)
    assert "proj_dates" in df_out.columns
    assert len(df_out["proj_dates"][0]) == (100 - 50) * 12 + 1

    # Assert end date column is NOT present, but start date IS present
    assert "projection_end_date" not in df_out.columns
    assert "projection_start_date" in df_out.columns
