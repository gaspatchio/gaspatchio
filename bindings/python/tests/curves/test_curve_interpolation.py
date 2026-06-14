# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Linear interpolation + flat extrapolation tests."""

from __future__ import annotations

import pytest

from gaspatchio_core.curves._interpolation import linear_interpolate


class TestLinearInterpolate:
    """Tests for linear_interpolate over sorted knot grids."""

    def test_exact_knot_recovery(self) -> None:
        """Values at knot points are returned exactly."""
        knots_x = [1.0, 2.0, 5.0, 10.0]
        knots_y = [0.03, 0.04, 0.05, 0.06]
        for x, expected in zip(knots_x, knots_y, strict=True):
            assert linear_interpolate(x, knots_x, knots_y) == pytest.approx(expected)

    def test_midpoint(self) -> None:
        """Midpoint between two knots returns the arithmetic mean."""
        knots_x = [1.0, 2.0]
        knots_y = [0.03, 0.05]
        assert linear_interpolate(1.5, knots_x, knots_y) == pytest.approx(0.04)

    def test_quarter_point(self) -> None:
        """Quarter-point on a unit interval returns 0.25."""
        knots_x = [0.0, 1.0]
        knots_y = [0.0, 1.0]
        assert linear_interpolate(0.25, knots_x, knots_y) == pytest.approx(0.25)

    def test_extrapolate_below_first_knot_returns_first_value(self) -> None:
        """Flat extrapolation below the first knot returns the first rate."""
        knots_x = [1.0, 5.0]
        knots_y = [0.03, 0.05]
        assert linear_interpolate(0.0, knots_x, knots_y) == pytest.approx(0.03)
        assert linear_interpolate(0.5, knots_x, knots_y) == pytest.approx(0.03)

    def test_extrapolate_above_last_knot_returns_last_value(self) -> None:
        """Flat extrapolation above the last knot returns the last rate."""
        knots_x = [1.0, 5.0]
        knots_y = [0.03, 0.05]
        assert linear_interpolate(10.0, knots_x, knots_y) == pytest.approx(0.05)
        assert linear_interpolate(50.0, knots_x, knots_y) == pytest.approx(0.05)

    def test_handles_non_uniform_grid(self) -> None:
        """Interpolation on a non-uniform grid selects the correct interval."""
        knots_x = [1.0, 2.0, 5.0, 10.0]
        knots_y = [0.03, 0.04, 0.05, 0.06]
        assert linear_interpolate(7.5, knots_x, knots_y) == pytest.approx(0.055)
