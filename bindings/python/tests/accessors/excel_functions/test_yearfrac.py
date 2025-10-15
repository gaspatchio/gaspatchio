"""ABOUTME: Tests for yearfrac Python-Rust interface - type marshalling and parameter validation.
ABOUTME: Does not test Excel calculation logic which is handled by Rust tests."""

import datetime
from typing import Any

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.accessors.excel_functions.yearfrac import BasisType, yearfrac


class TestYearfracInterface:
    """Test the Python-Rust interface for yearfrac function."""

    def test_yearfrac_scalar_columns(self):
        """Test yearfrac with scalar column inputs."""
        af = ActuarialFrame(
            {
                "start": [datetime.date(2020, 1, 1)],
                "end": [datetime.date(2020, 7, 1)],
            }
        )

        # Test that the function executes and returns a float
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"], basis="act/act").alias("year_frac")
        )
        result = res_af.collect()["year_frac"][0]
        assert isinstance(result, float)

    def test_yearfrac_vector_columns(self):
        """Test yearfrac with vector column inputs."""
        start_dates = [
            datetime.date(2020, 1, 1),
            datetime.date(2021, 1, 1),
            datetime.date(2022, 1, 1),
        ]
        end_dates = [
            datetime.date(2020, 7, 1),
            datetime.date(2021, 7, 1),
            datetime.date(2022, 7, 1),
        ]
        
        af = ActuarialFrame({"start": start_dates, "end": end_dates})

        # Test that vector operations work
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"], basis="act/act").alias("year_frac")
        )
        results = res_af.collect()["year_frac"]
        
        # Should have same length as input
        assert len(results) == len(start_dates)
        # All results should be floats
        assert all(isinstance(r, float) for r in results)

    def test_yearfrac_with_nulls(self):
        """Test yearfrac handles null values properly."""
        af = ActuarialFrame(
            {
                "start": [
                    datetime.date(2020, 1, 1),
                    None,
                    datetime.date(2022, 1, 1),
                ],
                "end": [
                    datetime.date(2020, 7, 1),
                    datetime.date(2021, 7, 1),
                    None,
                ],
            }
        )

        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"], basis="act/act").alias("year_frac")
        )
        results = res_af.collect()["year_frac"]
        
        # First result should be a float, others should be null
        assert isinstance(results[0], float)
        assert results[1] is None
        assert results[2] is None

    def test_yearfrac_returns_expression_proxy(self):
        """Test that yearfrac returns an ExpressionProxy that can be chained."""
        af = ActuarialFrame(
            {
                "start": [datetime.date(2020, 1, 1)],
                "end": [datetime.date(2020, 7, 1)],
            }
        )

        # Test chaining operations
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"]).alias("year_frac")
        ).with_columns(
            (pl.col("year_frac") * 12).alias("months")  # Should be able to use result in further ops
        )
        
        result = res_af.collect()
        assert "year_frac" in result.columns
        assert "months" in result.columns
        assert isinstance(result["months"][0], float)

    def test_yearfrac_date_type_conversion(self):
        """Test that yearfrac properly converts various date input types."""
        # Test with string dates that get converted
        df = pl.DataFrame({
            "start_str": ["2020-01-01"],
            "end_str": ["2020-07-01"]
        }).with_columns([
            pl.col("start_str").str.to_date().alias("start_date"),
            pl.col("end_str").str.to_date().alias("end_date")
        ])
        
        af = ActuarialFrame(df)
        
        res_af = af.with_columns(
            af["start_date"].excel.yearfrac(af["end_date"]).alias("year_frac")
        )
        result = res_af.collect()["year_frac"][0]
        assert isinstance(result, float)

    def test_yearfrac_datetime_to_date_conversion(self):
        """Test that datetime values are properly converted to dates."""
        # Create with datetime values
        af = ActuarialFrame({
            "start": [datetime.datetime(2020, 1, 1, 10, 30)],
            "end": [datetime.datetime(2020, 7, 1, 15, 45)]
        })
        
        # Should work - datetime should be cast to date
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"]).alias("year_frac")
        )
        result = res_af.collect()["year_frac"][0]
        assert isinstance(result, float)

    def test_yearfrac_list_columns_integration(self):
        """Test yearfrac with list columns - integration test."""
        # Test list vs list
        af = ActuarialFrame({
            "start_dates": [[datetime.date(2020, 1, 1), datetime.date(2020, 6, 1)]],
            "end_dates": [[datetime.date(2021, 1, 1), datetime.date(2021, 6, 1)]]
        })
        
        res_af = af.with_columns(
            af["start_dates"].excel.yearfrac(af["end_dates"], basis="act/act").alias("year_fracs")
        )
        result = res_af.collect()["year_fracs"]
        
        # Should return list of floats
        assert result.dtype == pl.List(pl.Float64)
        values = result[0]
        assert len(values) == 2
        assert all(abs(v - 1.0) < 0.01 for v in values)  # Both should be ~1 year


class TestBasisParameterValidation:
    """Test basis parameter validation and conversion."""

    def test_basis_string_to_int_conversion(self):
        """Test that string basis values are properly converted to integers."""
        af = ActuarialFrame(
            {
                "start": [datetime.date(2020, 1, 1)],
                "end": [datetime.date(2020, 7, 1)],
            }
        )

        # Test various string basis formats
        basis_mappings = {
            "act/act": 1,
            "actual/actual": 1,
            "us_nasd_30_360": 0,
            "30/360": 0,
            "actual/360": 2,
            "actual_360": 2,
            "actual/365": 3,
            "actual_365": 3,
            "european_30_360": 4,
            "30e/360": 4,
        }

        # Test that all string formats work
        for basis_str in basis_mappings:
            res_af = af.with_columns(
                af["start"].excel.yearfrac(af["end"], basis=basis_str).alias("year_frac")
            )
            result = res_af.collect()["year_frac"][0]
            assert isinstance(result, float)

    def test_basis_case_insensitive(self):
        """Test that basis strings are case insensitive."""
        af = ActuarialFrame(
            {
                "start": [datetime.date(2020, 1, 1)],
                "end": [datetime.date(2020, 7, 1)],
            }
        )

        # Test mixed case
        for basis in ["ACT/ACT", "Act/Act", "ACTUAL/ACTUAL"]:
            res_af = af.with_columns(
                af["start"].excel.yearfrac(af["end"], basis=basis).alias("year_frac")
            )
            result = res_af.collect()["year_frac"][0]
            assert isinstance(result, float)

    def test_basis_integer_values(self):
        """Test that integer basis values work correctly."""
        af = ActuarialFrame(
            {
                "start": [datetime.date(2020, 1, 1)],
                "end": [datetime.date(2020, 7, 1)],
            }
        )

        # Test all valid integer basis values
        for basis_int in range(5):
            res_af = af.with_columns(
                af["start"].excel.yearfrac(af["end"], basis=basis_int).alias("year_frac")
            )
            result = res_af.collect()["year_frac"][0]
            assert isinstance(result, float)

    def test_invalid_basis_string(self):
        """Test that invalid basis strings raise appropriate errors."""
        af = ActuarialFrame(
            {
                "start": [datetime.date(2020, 1, 1)],
                "end": [datetime.date(2020, 7, 1)],
            }
        )

        with pytest.raises(ValueError, match="Invalid basis"):
            res_af = af.with_columns(
                af["start"].excel.yearfrac(af["end"], basis="invalid_basis").alias("year_frac")
            )
            res_af.collect()

    def test_invalid_basis_int(self):
        """Test that invalid basis integers raise appropriate errors."""
        af = ActuarialFrame(
            {
                "start": [datetime.date(2020, 1, 1)],
                "end": [datetime.date(2020, 7, 1)],
            }
        )

        # Test out of range integer
        with pytest.raises(ValueError, match="Invalid basis"):
            res_af = af.with_columns(
                af["start"].excel.yearfrac(af["end"], basis=99).alias("year_frac")
            )
            res_af.collect()

        # Test negative integer
        with pytest.raises(ValueError, match="Invalid basis"):
            res_af = af.with_columns(
                af["start"].excel.yearfrac(af["end"], basis=-1).alias("year_frac")
            )
            res_af.collect()

    def test_basis_number_and_string_equivalence(self):
        """Test that numeric and string basis specifications produce identical results."""
        start_date = datetime.date(2020, 1, 1)
        end_date = datetime.date(2021, 1, 1)

        # Create a simple ActuarialFrame with the test dates
        af = ActuarialFrame({"start": [start_date], "end": [end_date]})

        # Test all basis equivalences
        basis_pairs = [
            (0, "us_nasd_30_360"),
            (0, "30/360"),
            (1, "act/act"),
            (1, "actual/actual"),
            (2, "actual/360"),
            (2, "actual_360"),
            (3, "actual/365"),
            (3, "actual_365"),
            (4, "european_30_360"),
            (4, "30e/360"),
        ]

        for basis_int, basis_str in basis_pairs:
            # Test basis specified as number
            result_num = af.with_columns(
                af["start"].excel.yearfrac(af["end"], basis=basis_int).alias("year_frac_num")
            ).collect()["year_frac_num"][0]

            # Test basis specified as string
            result_str = af.with_columns(
                af["start"]
                .excel.yearfrac(af["end"], basis=basis_str)
                .alias("year_frac_str")
            ).collect()["year_frac_str"][0]

            # Results should be identical
            assert result_num == result_str


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error conditions."""

    def test_yearfrac_list_columns_now_supported(self):
        """Test that list columns are now supported with broadcasting."""
        # Create list column of dates
        df = pl.DataFrame(
            {"start_list": [[datetime.date(2020, 1, 1), datetime.date(2020, 6, 1)]]},
            schema={"start_list": pl.List(pl.Date)},
        )
        af = ActuarialFrame(df)

        # This should now work with broadcasting
        res_af = af.with_columns(
            af["start_list"].excel.yearfrac(datetime.date(2021, 1, 1)).alias("year_frac")
        )
        result = res_af.collect()["year_frac"]
        
        # Should return a list of float values
        assert result.dtype == pl.List(pl.Float64)
        values = result[0]
        assert len(values) == 2
        assert all(v > 0 for v in values)

    def test_yearfrac_with_invalid_date_types(self):
        """Test yearfrac with invalid date column types."""
        # Test with non-date columns
        af = ActuarialFrame({
            "not_a_date": ["2020-01-01"],  # String, not converted
            "number": [42],
        })
        
        # String column should fail
        with pytest.raises(Exception):  # Rust will handle the actual error
            res_af = af.with_columns(
                af["not_a_date"].excel.yearfrac(datetime.date(2020, 7, 1)).alias("year_frac")
            )
            res_af.collect()

    def test_yearfrac_negative_duration(self):
        """Test yearfrac with end date before start date (negative duration)."""
        af = ActuarialFrame({
            "start": [datetime.date(2020, 7, 1)],
            "end": [datetime.date(2020, 1, 1)]
        })
        
        # Should work and return negative value
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"]).alias("year_frac")
        )
        result = res_af.collect()["year_frac"][0]
        assert isinstance(result, float)
        assert result < 0  # Should be negative

    def test_yearfrac_same_dates(self):
        """Test yearfrac when start and end dates are the same."""
        af = ActuarialFrame({
            "start": [datetime.date(2020, 1, 1)],
            "end": [datetime.date(2020, 1, 1)]
        })
        
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"]).alias("year_frac")
        )
        result = res_af.collect()["year_frac"][0]
        assert isinstance(result, float)
        assert result == 0.0


class TestDirectFunctionAPI:
    """Test the direct yearfrac function (not through accessor)."""

    def test_direct_yearfrac_function(self):
        """Test using yearfrac function directly without accessor."""
        # Create expressions
        start_expr = pl.col("start")
        end_expr = pl.col("end")
        
        # Call yearfrac directly
        result_expr = yearfrac(start_expr, end_expr, basis=1)
        
        # Use in a DataFrame context
        df = pl.DataFrame({
            "start": [datetime.date(2020, 1, 1)],
            "end": [datetime.date(2020, 7, 1)]
        })
        
        result = df.select(result_expr.alias("year_frac"))["year_frac"][0]
        assert isinstance(result, float)

    def test_direct_yearfrac_with_literals(self):
        """Test direct yearfrac function with literal values."""
        # This tests the low-level API
        start_expr = pl.col("start")
        end_literal = pl.lit(datetime.date(2020, 7, 1))
        
        result_expr = yearfrac(start_expr, end_literal, basis="act/act")
        
        df = pl.DataFrame({
            "start": [datetime.date(2020, 1, 1)]
        })
        
        result = df.select(result_expr.alias("year_frac"))["year_frac"][0]
        assert isinstance(result, float)