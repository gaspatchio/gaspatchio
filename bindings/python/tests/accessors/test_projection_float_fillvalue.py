# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Test for previous_period/next_period with float columns
# ABOUTME: Reproduces issue where Polars rejects integer fill_value
# ruff: noqa: S101, PLR2004, ANN201
# type: ignore[attr-defined]

"""Test that time-shifting methods handle float columns with integer fill_value."""

import pytest

from gaspatchio_core import ActuarialFrame


class TestFloatColumnIntegerFillValue:
    """Test time-shifting methods with float columns and default integer fill_value."""

    def test_previous_period_float_column_default_fill(self):
        """Test previous_period with float column and default fill_value=0.

        This reproduces the issue where Polars rejects integer fill_value
        for float list columns.
        """
        # Create data with float values (like pols_if)
        data = {"pols_if": [[1000.0, 990.5, 980.2]]}
        af = ActuarialFrame(data)

        # This should work but currently fails with:
        # "fill value '0' is not supported" from Polars
        af.pols_if_prev = af.pols_if.projection.previous_period()

        result = af.collect()
        pols_if_prev = result["pols_if_prev"][0]

        # Should shift: [1000.0, 990.5, 980.2] -> [0.0, 1000.0, 990.5]
        assert pytest.approx(pols_if_prev[0], abs=1e-6) == 0.0
        assert pytest.approx(pols_if_prev[1], abs=1e-6) == 1000.0
        assert pytest.approx(pols_if_prev[2], abs=1e-6) == 990.5

    def test_next_period_float_column_default_fill(self):
        """Test next_period with float column and default fill_value=0."""
        data = {"cashflow": [[1000.0, 1100.5, 1200.75]]}
        af = ActuarialFrame(data)

        af.cf_next = af.cashflow.projection.next_period()

        result = af.collect()
        cf_next = result["cf_next"][0]

        # Should shift: [1000.0, 1100.5, 1200.75] -> [1100.5, 1200.75, 0.0]
        assert pytest.approx(cf_next[0], abs=1e-6) == 1100.5
        assert pytest.approx(cf_next[1], abs=1e-6) == 1200.75
        assert pytest.approx(cf_next[2], abs=1e-6) == 0.0

    def test_at_period_float_column_default_fill(self):
        """Test at_period with float column and default fill_value=0."""
        data = {"reserve": [[950.5, 1900.75, 2850.25]]}
        af = ActuarialFrame(data)

        af.reserve_prev = af.reserve.projection.at_period(-1)

        result = af.collect()
        reserve_prev = result["reserve_prev"][0]

        # Should shift: [950.5, 1900.75, 2850.25] -> [0.0, 950.5, 1900.75]
        assert pytest.approx(reserve_prev[0], abs=1e-6) == 0.0
        assert pytest.approx(reserve_prev[1], abs=1e-6) == 950.5
        assert pytest.approx(reserve_prev[2], abs=1e-6) == 1900.75

    def test_previous_period_float_fill_explicit(self):
        """Test that explicitly passing fill_value=0.0 works."""
        data = {"pols_if": [[1000.0, 990.5, 980.2]]}
        af = ActuarialFrame(data)

        # Explicitly passing 0.0 should work
        af.pols_if_prev = af.pols_if.projection.previous_period(fill_value=0.0)

        result = af.collect()
        pols_if_prev = result["pols_if_prev"][0]

        assert pytest.approx(pols_if_prev[0], abs=1e-6) == 0.0
        assert pytest.approx(pols_if_prev[1], abs=1e-6) == 1000.0
        assert pytest.approx(pols_if_prev[2], abs=1e-6) == 990.5
