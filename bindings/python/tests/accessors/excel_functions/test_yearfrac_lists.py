# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for yearfrac function with list column support and broadcasting
# ABOUTME: Validates scalar/scalar, list/list, scalar/list, and list/scalar combinations

from __future__ import annotations

import datetime
from typing import Any

import polars as pl
import pytest
from polars.testing import assert_series_equal
from polars.exceptions import ComputeError

from gaspatchio_core import ActuarialFrame


class TestYearfracListColumns:
    """Test yearfrac with list columns and broadcasting behavior."""

    def test_scalar_vs_scalar_baseline(self) -> None:
        """Test basic scalar functionality remains unchanged."""
        af = ActuarialFrame({
            "start": [datetime.date(2023, 1, 1), datetime.date(2023, 6, 1)],
            "end": [datetime.date(2024, 1, 1), datetime.date(2024, 6, 1)],
        })
        
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"], basis=1).alias("yearfrac")
        )
        result = res_af.collect()
        
        # Both should be exactly 1 year
        expected = pl.Series("yearfrac", [1.0, 1.0], dtype=pl.Float64)
        assert_series_equal(result["yearfrac"], expected)

    def test_list_vs_list_pairwise(self) -> None:
        """Test list columns with pairwise calculations."""
        # Create list columns with multiple dates
        start_dates = [
            [datetime.date(2023, 1, 1), datetime.date(2023, 6, 1), datetime.date(2023, 9, 1)],
            [datetime.date(2022, 1, 1), datetime.date(2022, 6, 1), datetime.date(2022, 9, 1)],
        ]
        end_dates = [
            [datetime.date(2024, 1, 1), datetime.date(2024, 6, 1), datetime.date(2024, 9, 1)],
            [datetime.date(2023, 1, 1), datetime.date(2023, 6, 1), datetime.date(2023, 9, 1)],
        ]
        
        af = ActuarialFrame({
            "policy_id": [1, 2],
            "start_dates": start_dates,
            "end_dates": end_dates,
        })
        
        res_af = af.with_columns(
            af["start_dates"].excel.yearfrac(af["end_dates"], basis=1).alias("yearfrac_list")
        )
        result = res_af.collect()
        
        # Each element should be 1 year
        assert result["yearfrac_list"].dtype == pl.List(pl.Float64)
        assert len(result) == 2
        
        # Check first row
        first_row_values = result["yearfrac_list"][0]
        assert len(first_row_values) == 3
        assert all(abs(v - 1.0) < 0.0001 for v in first_row_values)
        
        # Check second row
        second_row_values = result["yearfrac_list"][1]
        assert len(second_row_values) == 3
        assert all(abs(v - 1.0) < 0.0001 for v in second_row_values)

    def test_scalar_vs_list_broadcasting(self) -> None:
        """Test broadcasting scalar start date to list of end dates."""
        # Single valuation date
        valuation_date = datetime.date(2024, 1, 1)
        
        # Multiple projection dates per policy
        projection_dates = [
            [datetime.date(2024, i, 1) for i in range(1, 7)],  # Jan-Jun 2024
            [datetime.date(2024, i, 1) for i in range(7, 13)], # Jul-Dec 2024
        ]
        
        af = ActuarialFrame({
            "policy_id": [1, 2],
            "valuation_date": valuation_date,  # Scalar column
            "projection_dates": projection_dates,
        })
        
        res_af = af.with_columns(
            af["valuation_date"].excel.yearfrac(
                af["projection_dates"], 
                basis="30/360"
            ).alias("time_from_valuation")
        )
        result = res_af.collect()
        
        # Result should be list of float64
        assert result["time_from_valuation"].dtype == pl.List(pl.Float64)
        
        # First policy: Jan-Jun should have increasing fractions
        first_values = result["time_from_valuation"][0]
        assert len(first_values) == 6
        assert first_values[0] == 0.0  # Jan 1 to Jan 1
        assert all(first_values[i] < first_values[i+1] for i in range(5))
        
        # Second policy: Jul-Dec should also increase
        second_values = result["time_from_valuation"][1]
        assert len(second_values) == 6
        assert all(second_values[i] < second_values[i+1] for i in range(5))

    def test_list_vs_scalar_broadcasting(self) -> None:
        """Test broadcasting list of start dates to scalar end date."""
        # Multiple issue dates per policy (e.g., premium payment dates)
        issue_dates = [
            [datetime.date(2020, i, 1) for i in range(1, 5)],  # Q1 2020
            [datetime.date(2021, i, 1) for i in range(1, 5)],  # Q1 2021
        ]
        
        # Single maturity date for all
        maturity_date = datetime.date(2030, 1, 1)
        
        af = ActuarialFrame({
            "policy_id": [1, 2],
            "issue_dates": issue_dates,
            "maturity_date": maturity_date,  # Scalar column
        })
        
        res_af = af.with_columns(
            af["issue_dates"].excel.yearfrac(
                af["maturity_date"], 
                basis="act/365"
            ).alias("time_to_maturity")
        )
        result = res_af.collect()
        
        # Result should be list of float64
        assert result["time_to_maturity"].dtype == pl.List(pl.Float64)
        
        # First policy: Later issue dates should have less time to maturity
        first_values = result["time_to_maturity"][0]
        assert len(first_values) == 4
        assert all(first_values[i] > first_values[i+1] for i in range(3))
        
        # Second policy: 2021 dates should have less time than 2020
        second_values = result["time_to_maturity"][1]
        assert all(second_values[i] < first_values[i] for i in range(4))

    def test_null_handling_in_lists(self) -> None:
        """Test null handling within list columns."""
        # Lists with some null dates
        start_dates = [
            [datetime.date(2023, 1, 1), None, datetime.date(2023, 3, 1)],
            [None, datetime.date(2023, 2, 1), None],
        ]
        end_dates = [
            [datetime.date(2024, 1, 1), datetime.date(2024, 2, 1), None],
            [datetime.date(2024, 1, 1), None, datetime.date(2024, 3, 1)],
        ]
        
        af = ActuarialFrame({
            "start_dates": start_dates,
            "end_dates": end_dates,
        })
        
        res_af = af.with_columns(
            af["start_dates"].excel.yearfrac(af["end_dates"], basis=1).alias("yearfrac")
        )
        result = res_af.collect()
        
        # Check null propagation
        first_row = result["yearfrac"][0]
        assert first_row[0] is not None  # Valid pair
        assert first_row[1] is None       # One null
        assert first_row[2] is None       # One null
        
        second_row = result["yearfrac"][1]
        assert second_row[0] is None      # One null
        assert second_row[1] is None      # One null
        assert second_row[2] is None      # Both null

    def test_empty_lists(self) -> None:
        """Test handling of empty lists."""
        af = ActuarialFrame({
            "start_dates": [[], [datetime.date(2023, 1, 1)]],
            "end_dates": [[], [datetime.date(2024, 1, 1)]],
        })
        
        res_af = af.with_columns(
            af["start_dates"].excel.yearfrac(af["end_dates"], basis=1).alias("yearfrac")
        )
        result = res_af.collect()
        
        # First row should be empty list
        assert len(result["yearfrac"][0]) == 0
        
        # Second row should have one value
        assert len(result["yearfrac"][1]) == 1
        assert abs(result["yearfrac"][1][0] - 1.0) < 0.0001

    def test_mismatched_list_lengths(self) -> None:
        """Test error handling for mismatched list lengths."""
        af = ActuarialFrame({
            "start_dates": [[datetime.date(2023, 1, 1), datetime.date(2023, 2, 1)]],
            "end_dates": [[datetime.date(2024, 1, 1)]],  # Different length
        })
        
        # This should raise an error
        with pytest.raises(ComputeError, match="must have the same length"):
            res_af = af.with_columns(
                af["start_dates"].excel.yearfrac(af["end_dates"], basis=1).alias("yearfrac")
            )
            res_af.collect()

    def test_actuarial_projection_pattern(self) -> None:
        """Test typical actuarial projection pattern with monthly dates."""
        from datetime import date
        from dateutil.relativedelta import relativedelta
        
        # Create 120 monthly projection dates (10 years)
        base_date = date(2024, 1, 1)
        projection_months = 120
        
        # Generate projection dates for multiple policies
        projection_dates = []
        for policy in range(3):
            dates = [base_date + relativedelta(months=i) for i in range(projection_months)]
            projection_dates.append(dates)
        
        # Each policy has its own maturity date
        maturity_dates = [
            date(2034, 1, 1),   # 10 years
            date(2039, 1, 1),   # 15 years
            date(2044, 1, 1),   # 20 years
        ]
        
        af = ActuarialFrame({
            "policy_id": [1, 2, 3],
            "projection_dates": projection_dates,
            "maturity_date": maturity_dates,
        })
        
        # Calculate time to maturity for each projection month
        res_af = af.with_columns(
            af["projection_dates"].excel.yearfrac(
                af["maturity_date"], 
                basis="act/act"
            ).alias("time_to_maturity")
        )
        result = res_af.collect()
        
        # Verify structure
        assert result["time_to_maturity"].dtype == pl.List(pl.Float64)
        
        # Each policy should have 120 values
        for i in range(3):
            values = result["time_to_maturity"][i]
            assert len(values) == 120
            
            # Time to maturity should decrease over projection
            assert all(values[j] > values[j+1] for j in range(119))
            
            # First value should be approximately the policy term
            if i == 0:  # 10-year policy
                assert 9.9 < values[0] < 10.1
            elif i == 1:  # 15-year policy
                assert 14.9 < values[0] < 15.1
            else:  # 20-year policy
                assert 19.9 < values[0] < 20.1

    def test_all_basis_types_with_lists(self) -> None:
        """Test all basis types work with list columns."""
        start_dates = [[datetime.date(2023, 1, 1), datetime.date(2023, 6, 1)]]
        end_dates = [[datetime.date(2024, 1, 1), datetime.date(2024, 6, 1)]]
        
        af = ActuarialFrame({
            "start": start_dates,
            "end": end_dates,
        })
        
        # Test all basis types
        basis_types = [0, 1, 2, 3, 4, "30/360", "act/act", "actual/360", "actual/365", "european_30_360"]
        
        for basis in basis_types:
            res_af = af.with_columns(
                af["start"].excel.yearfrac(af["end"], basis=basis).alias("yearfrac")
            )
            result = res_af.collect()
            
            # Should return list of two values
            values = result["yearfrac"][0]
            assert len(values) == 2
            assert all(v > 0 for v in values)  # All positive