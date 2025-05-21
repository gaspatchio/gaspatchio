import polars as pl
import pytest
from gaspatchio_core import ActuarialFrame

# @pytest.mark.parametrize(
#    "example",
#    find_examples(
#        "gaspatchio_core/column/namespaces/dt_proxy.py",
#    ),
#    ids=str,
# )
# def test_docstrings(example: CodeExample, eval_example: EvalExample):
#    eval_example.lint(example)
#    eval_example.run_print_check(example)


@pytest.mark.example(ns="excel.yearfrac")  # <── our marker
def test_yearfrac_example():
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "start": ["2020-01-01", "2021-06-15"],
                "end": ["2021-01-01", "2022-06-15"],
            }
        )
    )
    af["yearfrac"] = af["start"].excel.yearfrac(af["end"])

    result = af.collect()
    print(result)


@pytest.mark.example(ns="dt.year")
def test_dt_year_example():
    """Test the .dt.year accessor and method."""
    from gaspatchio_core.column.expression_proxy import (
        ExpressionProxy,  # For type checking
    )
    from gaspatchio_core.column.namespaces.dt_proxy import (
        DtNamespaceProxy,  # For type checking
    )

    data = {
        "policy_id": [1, 2, 3],
        "inception_date": pl.Series(
            ["2020-03-15", "2021-07-20", "2022-11-01"]
        ).str.to_date(format="%Y-%m-%d"),
    }
    af = ActuarialFrame(data)

    # Test that accessing .dt returns a DtNamespaceProxy
    assert isinstance(af["inception_date"].dt, DtNamespaceProxy)

    # Apply the .dt.year() method
    year_expr = af["inception_date"].dt.year()
    af["inception_year"] = year_expr

    # Check the type of the resulting expression proxy before collecting
    assert isinstance(year_expr, ExpressionProxy)

    result_df = af.collect()

    expected_years = pl.Series("inception_year", [2020, 2021, 2022], dtype=pl.Int32)

    # Print for debugging in case of failure
    print("Result DataFrame:")
    print(result_df)
    print("Expected Years Series:")
    print(expected_years)

    actual_years_list = result_df["inception_year"].to_list()
    expected_years_list = expected_years.to_list()

    assert actual_years_list == expected_years_list, (
        f"Expected years {expected_years_list} but got {actual_years_list}"
    )

    # Test _call_dt_method indirectly via another dt method, e.g., month
    af["inception_month"] = af["inception_date"].dt.month()
    result_month_df = af.collect()
    expected_months = pl.Series("inception_month", [3, 7, 11], dtype=pl.Int32)

    actual_months_list = result_month_df["inception_month"].to_list()
    expected_months_list = expected_months.to_list()
    assert actual_months_list == expected_months_list, (
        f"Expected months {expected_months_list} but got {actual_months_list}"
    )

    # Test explicit dt.day()
    af["inception_day"] = af["inception_date"].dt.day()
    result_day_df = af.collect()
    expected_days = pl.Series("inception_day", [15, 20, 1], dtype=pl.Int32)
    actual_days_list = result_day_df["inception_day"].to_list()
    expected_days_list = expected_days.to_list()
    assert actual_days_list == expected_days_list, (
        f"Expected days {expected_days_list} but got {actual_days_list}"
    )

    # Test __getattr__ with dt.hour() (dates need to be cast to datetime first)
    af["inception_hour"] = af["inception_date"].cast(pl.Datetime).dt.hour()
    result_hour_df = af.collect()
    expected_hours = pl.Series("inception_hour", [0, 0, 0], dtype=pl.Int32)
    actual_hours_list = result_hour_df["inception_hour"].to_list()
    expected_hours_list = expected_hours.to_list()
    assert actual_hours_list == expected_hours_list, (
        f"Expected hours {expected_hours_list} but got {actual_hours_list}"
    )
